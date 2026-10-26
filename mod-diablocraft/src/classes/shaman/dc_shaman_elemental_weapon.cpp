/*
 * Elemental Weapon and its five runes. The imbue is the rune of the skill on the bar, always on (its passive); a cast
 * spends the Maelstrom the record charges and activates it for a few seconds. Here: which imbue is in force, the damage
 * factors and Maelstrom it gives, Flametongue's burn, Frostbrand's chill and freeze, Windfury's strike again,
 * Rockbiter's Armor, Maelstrom Weapon's free Secondary cast and richer Primaries, the sheet numbers an imbue puts on
 * the character and the buffs that show it.
 */

#include "dc_shaman_elemental_weapon.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"

#include <algorithm>
#include <mutex>
#include <set>
#include <unordered_map>

namespace DC::Combat::Shaman::ElementalWeapon
{
    namespace
    {
        constexpr std::string_view Skill = "Elemental Weapon";

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        // The buff the bar shows for an imbue.
        char const* BuffName(Rune rune)
        {
            switch (rune)
            {
                case Rune::Flametongue:
                    return "Elemental Weapon - Flametongue - buff";
                case Rune::Frostbrand:
                    return "Elemental Weapon - Frostbrand - buff";
                case Rune::Windfury:
                    return "Elemental Weapon - Windfury - buff";
                case Rune::Rockbiter:
                    return "Elemental Weapon - Rockbiter - buff";
                case Rune::MaelstromWeapon:
                    return "Elemental Weapon - Maelstrom Weapon - buff";
                default:
                    return "Elemental Weapon - buff";
            }
        }

        constexpr char const* ImbueBuffs[] = {
            "Elemental Weapon - buff",
            "Elemental Weapon - Flametongue - buff",
            "Elemental Weapon - Frostbrand - buff",
            "Elemental Weapon - Windfury - buff",
            "Elemental Weapon - Rockbiter - buff",
            "Elemental Weapon - Maelstrom Weapon - buff",
        };
        // Maelstrom Weapon's next Secondary skill is free.
        constexpr char const* FreeBuff = "Elemental Weapon - Maelstrom Weapon - free";

        struct State
        {
            Rune rune = Rune::Off;
            std::uint32_t spellId = 0;      // the record of the imbue on the bar
            std::uint64_t until = 0;        // the activation's end
            unsigned windfury = 0;          // Lightning hits since the last strike again
            unsigned primaries = 0;         // Primary casts since the last free Secondary
            bool free = false;              // the next Secondary costs nothing
            std::set<std::uint64_t> frozen; // enemies Frostbrand froze in this activation
            Rune sheetRune = Rune::Off;     // what the character sheet holds
            bool sheetActive = false;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        std::uint32_t Millis(double seconds)
        {
            return std::uint32_t(seconds * 1000.0 + 0.5);
        }

        // A number the imbue's record states itself: the qualified one, else the unqualified one, else nothing (a rune
        // that does not restate a number would otherwise answer with the base skill's).
        double Own(std::uint32_t spellId, char const* token, char const* qualifier)
        {
            auto const qualified = Numbers::Own(spellId, token, qualifier);
            return qualified ? *qualified : Numbers::Own(spellId, token).value_or(0.0);
        }

        // The record of Elemental Weapon on one of the player's skill buttons; 0 when none is.
        std::uint32_t Slotted(Player* player)
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill)
                    for (unsigned slot = 0; slot < Classes::ActiveSlots(); ++slot)
                        if (ActionButton const* button = player->GetActionButton(std::uint8_t(slot)))
                            if (button->GetType() == ACTION_BUTTON_SPELL && button->GetAction() == row.id)
                                return row.id;
            return 0;
        }

        // The element the player's hit of `spellId` deals, as the engine resolves it.
        Attunement::Element DealtBy(Player* player, std::uint32_t spellId)
        {
            return DealtElement(DC::Combat::Shaman::Element(player, spellId), Attunement::ElementOf(spellId));
        }

        bool Active(State const& state, std::uint64_t now)
        {
            return state.rune != Rune::Off && state.until > now;
        }

        // What an imbue puts on the sheet, in step with the imbue and its activation.
        void PutOnSheet(Player* player, Rune rune, std::uint32_t spellId, bool active)
        {
            std::uint64_t const guid = Key(player);
            for (char const* name : ImbueBuffs)
            {
                std::uint32_t const id = BuffId(name);
                Stats::RemoveContribution(guid, Source::Temporary, Stat::Armor, id);
                Stats::RemoveContribution(guid, Source::Temporary, Stat::AttackSpeed, id);
            }
            if (rune != Rune::Off)
            {
                std::uint32_t const id = BuffId(BuffName(rune));
                Sheet const sheet =
                    SheetOf(rune, active, Own(spellId, "armor_pct", "passive"), Own(spellId, "armor_pct", "activate"),
                            Own(spellId, "attack_speed_pct", ""));
                if (sheet.armorPct != 0)
                    Stats::AddContribution(guid, {Source::Temporary, Stat::Armor, id, sheet.armorPct, Bucket::Percent});
                if (sheet.attackSpeedPct != 0)
                    Stats::AddContribution(
                        guid, {Source::Temporary, Stat::AttackSpeed, id, sheet.attackSpeedPct, Bucket::Flat});
            }
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The cast hits nothing: Windfury's and Flametongue's `damage_pct` are the strike again's and the burn's.
        return RowOf(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!IsShaman(player))
            return;
        std::string const category = Classes::CategoryOf(spellId);
        if (auto const* row = RowOf(spellId))
        {
            // The Maelstrom is paid by the record; here the imbue is activated for the sheet's seconds, a new
            // activation starting the window over.
            Rune const rune = RuneOf(row->rune);
            double const seconds =
                Combat::ModifiedDurationSeconds(player, spellId, Own(spellId, "duration_seconds", ""));
            std::uint64_t const until = Now() + Millis(seconds);
            {
                std::lock_guard<std::mutex> guard(mutex);
                State& state = states[Key(player)];
                if (state.rune != rune || state.spellId != spellId)
                {
                    state = State{};
                    state.rune = rune;
                    state.spellId = spellId;
                }
                state.until = until;
                state.frozen.clear();
            }
            Upkeep(player);
            return;
        }
        if (category != "Primary" && category != "Secondary")
            return;
        double refund = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = states.find(Key(player));
            if (found == states.end() || found->second.rune != Rune::MaelstromWeapon)
                return;
            State& state = found->second;
            if (category == "Primary")
            {
                // "Every {trigger_count}th Primary skill cast makes your next Secondary skill free."
                if (Reached(state.primaries, unsigned(Own(state.spellId, "trigger_count", ""))))
                    state.free = true;
            }
            else if (state.free)
            {
                state.free = false;
                refund = Numbers::Num(spellId, "cost_resource") * Combat::CostReductionFactor(player, spellId);
            }
        }
        // The core charged the record's cost when the skill began; the free cast gives it back.
        Gain(player, spellId, refund);
        Upkeep(player);
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!IsShaman(player) || !Shells::FindAbility(spellId) || RowOf(spellId))
            return;
        Rune rune;
        std::uint32_t imbue;
        bool active;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = states.find(Key(player));
            if (found == states.end())
                return;
            rune = found->second.rune;
            imbue = found->second.spellId;
            active = Active(found->second, Now());
        }
        Bonus const bonus =
            DamageBonus(rune, DealtBy(player, spellId), active, Own(imbue, "damage_bonus_pct", "passive"),
                        Own(imbue, "damage_bonus_pct", "activate"));
        if (bonus.passivePct)
            AddFactor(out, "Elemental Weapon", bonus.passivePct);
        if (bonus.activePct)
            AddFactor(out, "Elemental Weapon (activated)", bonus.activePct);
    }

    double GenerationPct(Player* player, std::uint32_t spellId)
    {
        if (!IsShaman(player))
            return 0.0;
        Rune rune;
        std::uint32_t imbue;
        bool active;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = states.find(Key(player));
            if (found == states.end())
                return 0.0;
            rune = found->second.rune;
            imbue = found->second.spellId;
            active = Active(found->second, Now());
        }
        return DC::Combat::Shaman::ElementalWeapon::GenerationPct(
            rune, active, Classes::CategoryOf(spellId) == "Primary", Own(imbue, "regen_pct", ""));
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!IsShaman(player) || !target || !Shells::FindAbility(spellId) || RowOf(spellId))
            return;
        Rune rune;
        std::uint32_t imbue;
        bool active;
        unsigned every = 0;
        bool strike = false;
        bool freeze = false;
        Effect effect;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = states.find(Key(player));
            if (found == states.end())
                return;
            State& state = found->second;
            rune = state.rune;
            imbue = state.spellId;
            active = Active(state, Now());
            effect = EffectOf(rune, DealtBy(player, spellId), active);
            if (effect.echo)
            {
                every = unsigned(Own(imbue, "trigger_count", active ? "activate" : "passive"));
                strike = Reached(state.windfury, every);
            }
            // "once per enemy per activation"
            freeze = effect.freeze && state.frozen.insert(target->GetGUID().GetRawValue()).second;
        }
        char const* const qualifier = active ? "activate" : "passive";
        if (effect.burn)
            PeriodicStrike::Start(player, target, imbue, Own(imbue, "damage_pct", qualifier),
                                  Own(imbue, "dot_duration_seconds", qualifier),
                                  Tunable("elemental_weapon_burn_tick_seconds"));
        if (effect.chill)
            Shaman::Slow(player, target, Own(imbue, "chill_pct", ""), Own(imbue, "chill_duration_seconds", ""));
        if (freeze)
            Shaman::Freeze(player, target, Own(imbue, "freeze_duration_seconds", "") * ItemPowers::StunFactor(player));
        // "strikes the target again for {damage_pct} weapon damage as Lightning (a free cast echo)"
        if (strike && target->IsAlive())
            Combat::Strike(player, target, imbue, Own(imbue, "damage_pct", ""));
    }

    void Upkeep(Player* player)
    {
        if (!IsShaman(player))
            return;
        std::uint32_t const slotted = Slotted(player);
        std::uint64_t const now = Now();
        Rune rune = Rune::Off;
        std::uint32_t imbue = 0;
        bool active = false, changed = false, free = false;
        double seconds = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[Key(player)];
            auto const* row = slotted ? RowOf(slotted) : nullptr;
            Rune const wanted = row ? RuneOf(row->rune) : Rune::Off;
            // Another rune on the bar, or none, replaces the imbue and what it was counting.
            if (wanted != state.rune || (row && state.spellId != slotted))
            {
                state = State{};
                state.rune = wanted;
                state.spellId = row ? slotted : 0;
            }
            if (state.rune != Rune::MaelstromWeapon)
                state.free = false;
            free = state.free;
            active = Active(state, now);
            if (!active)
                state.until = 0;
            rune = state.rune;
            imbue = state.spellId;
            seconds = active ? double(state.until - now) / 1000.0 : 0.0;
            changed = state.sheetRune != rune || state.sheetActive != active;
        }
        if (changed)
        {
            PutOnSheet(player, rune, imbue, active);
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[Key(player)];
            state.sheetRune = rune;
            state.sheetActive = active;
        }
        char const* const worn = BuffName(rune);
        for (char const* name : ImbueBuffs)
            BuffValues::Show(player, BuffId(name), rune != Rune::Off && std::string_view(name) == worn ? 1 : 0, seconds);
        BuffValues::Show(player, BuffId(FreeBuff), free ? 1 : 0);
    }

    void Forget(Player* player)
    {
        std::uint64_t const guid = Key(player);
        for (char const* name : ImbueBuffs)
        {
            std::uint32_t const id = BuffId(name);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::Armor, id);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::AttackSpeed, id);
        }
        std::lock_guard<std::mutex> guard(mutex);
        states.erase(guid);
    }
} // namespace DC::Combat::Shaman::ElementalWeapon

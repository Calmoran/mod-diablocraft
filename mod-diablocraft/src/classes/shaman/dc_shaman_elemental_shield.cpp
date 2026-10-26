/*
 * Elemental Shield and its five runes. The cast is the engine's self cast (a record and the sheet's numbers) that hits
 * nothing; here: the shield the Shaman wears (charges, seconds, one at a time), the hit it lowers and answers, each
 * rune's part (Lightning Shield's Maelstrom and charges from Primary hits, Stoneskin's Armor and absorb, Water Shield's
 * heal, Maelstrom and chill, Flame Shield's burn and fiery answer), and the buffs that show it on the bar. Totemic Ward
 * waits on the Totems.
 */

#include "dc_shaman_elemental_shield.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "ObjectAccessor.h"
#include "SpellAuraEffects.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <map>
#include <mutex>
#include <random>

namespace DC::Combat::Shaman::ElementalShield
{
    namespace
    {
        constexpr std::string_view Skill = "Elemental Shield";

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        // The buff the bar shows for a rune's shield; Totemic Ward and the plain skill wear the skill's.
        char const* BuffName(Rune rune)
        {
            switch (rune)
            {
                case Rune::LightningShield:
                    return "Elemental Shield - Lightning Shield - buff";
                case Rune::Stoneskin:
                    return "Elemental Shield - Stoneskin - buff";
                case Rune::WaterShield:
                    return "Elemental Shield - Water Shield - buff";
                case Rune::FlameShield:
                    return "Elemental Shield - Flame Shield - buff";
                default:
                    return "Elemental Shield - buff";
            }
        }

        constexpr char const* ShieldBuffs[] = {
            "Elemental Shield - buff",
            "Elemental Shield - Lightning Shield - buff",
            "Elemental Shield - Stoneskin - buff",
            "Elemental Shield - Water Shield - buff",
            "Elemental Shield - Flame Shield - buff",
        };
        // Stoneskin's absorb: a record of every school the core drains itself, on every hit that lands.
        constexpr char const* AbsorbBuff = "Elemental Shield - Stoneskin - shield";

        struct State
        {
            Shield shield;
            Pending pending;
            bool armored = false; // the sheet holds Stoneskin's Armor
        };
        std::mutex mutex;
        std::map<std::uint64_t, State> states;
        std::uint64_t stamps = 0;

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        std::uint32_t Millis(double seconds)
        {
            return std::uint32_t(seconds * 1000.0 + 0.5);
        }

        double Roll()
        {
            static thread_local std::mt19937 engine{std::random_device{}()};
            return std::uniform_real_distribution<double>(0.0, 100.0)(engine);
        }

        // The charges a cast of `spellId` puts on: the skill's, or the rune's own (Stoneskin).
        unsigned ChargesOf(std::uint32_t spellId)
        {
            return unsigned(
                Numbers::Get(spellId, "charge_count", "new").value_or(Numbers::Num(spellId, "charge_count")));
        }

        // What the shield does for the charge a hit used, away from the damage calculation that spent it.
        void Answer(Player* player, std::uint32_t spellId, Rune rune, ObjectGuid attacker, bool strike)
        {
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            Unit* enemy = attacker ? ObjectAccessor::GetUnit(*player, attacker) : nullptr;
            if (rune == Rune::LightningShield || rune == Rune::WaterShield)
                Gain(player, spellId, Numbers::Num(spellId, "gain_resource"));
            if (rune == Rune::WaterShield)
            {
                Shaman::Heal(player, spellId, player->GetMaxHealth() * Numbers::Num(spellId, "heal_pct") / 100.0);
                if (enemy)
                    Shaman::Slow(player, enemy, Numbers::Num(spellId, "chill_pct"),
                                 Numbers::Num(spellId, "chill_duration_seconds"));
            }
            if (!strike || !enemy || !enemy->IsAlive())
                return;
            if (rune == Rune::FlameShield)
                Combat::StrikeArea(player, spellId, enemy->GetPosition(), Numbers::Num(spellId, "radius_yards", "hit"),
                                   Numbers::Num(spellId, "damage_pct", "hit"));
            else
                Combat::Strike(player, enemy, spellId, Numbers::Get(spellId, "damage_pct"));
        }

        // Flame Shield's burn: every tick, while the shield stands with a charge, what is within the radius burns.
        void Burn(Player* player, std::uint64_t stamp, std::uint32_t spellId)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = states.find(Key(player));
                if (found == states.end() || found->second.shield.stamp != stamp ||
                    !Active(found->second.shield, Now()))
                    return;
            }
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            double const tick = Tunable("elemental_shield_burn_tick_seconds");
            Combat::StrikeArea(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards", "aura"),
                               TickPct(Numbers::Num(spellId, "damage_pct", "burn"), tick), true);
            player->m_Events.AddEventAtOffset([player, stamp, spellId] { Burn(player, stamp, spellId); },
                                              std::chrono::milliseconds(Millis(tick)));
        }

        // Stoneskin's Armor on the sheet while a charge remains, in step with the shield.
        void Armor(Player* player, bool wanted)
        {
            std::uint64_t const guid = Key(player);
            std::uint32_t const id = BuffId(BuffName(Rune::Stoneskin));
            bool held;
            double pct = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                State& state = states[guid];
                held = state.armored;
                if (wanted)
                    pct = Numbers::Num(state.shield.spellId, "armor_pct");
                if (wanted == held)
                    return;
                state.armored = wanted;
            }
            if (wanted)
                Stats::AddContribution(guid, {Source::Temporary, Stat::Armor, id, pct, Bucket::Percent});
            else
                Stats::RemoveContribution(guid, Source::Temporary, Stat::Armor, id);
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId);
        if (!player || !row)
            return;
        Rune const rune = RuneOf(row->rune);
        double const seconds =
            Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(spellId, "duration_seconds"));
        std::uint64_t stamp;
        {
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[Key(player)];
            state.shield = {};
            state.shield.spellId = spellId;
            state.shield.rune = rune;
            state.shield.charges = ChargesOf(spellId);
            state.shield.until = Now() + Millis(seconds);
            state.shield.stamp = stamp = ++stamps;
        }
        if (rune == Rune::FlameShield)
            Burn(player, stamp, spellId);
        Upkeep(player);
    }

    double Reduce(Unit* victim, Unit* attacker, double damage)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (!IsShaman(player) || damage <= 0)
            return damage;
        std::uint64_t const now = Now();
        std::lock_guard<std::mutex> guard(mutex);
        auto const found = states.find(Key(player));
        if (found == states.end() || !Active(found->second.shield, now))
            return damage;
        State& state = found->second;
        // Only the hit's size is worked out here. The core mitigates a swing before it rolls it, so the charge is paid when the hit
        // lands (Damaged), not when it is mitigated.
        Note(state.pending, attacker ? attacker->GetGUID().GetRawValue() : 0, now, true);
        return Lowered(damage, Numbers::Num(state.shield.spellId, "damage_reduction_pct"));
    }

    void Damaged(Unit* attacker, Unit* victim, std::uint32_t)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (!IsShaman(player))
            return;
        std::uint64_t const now = Now();
        Spent spent;
        std::uint32_t spellId = 0;
        Rune rune = Rune::None;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = states.find(Key(player));
            if (found == states.end())
                return;
            State& state = found->second;
            auto const paid = Claim(state.pending, attacker ? attacker->GetGUID().GetRawValue() : 0, now);
            if (!paid || !paid->charge || !Active(state.shield, now))
                return;
            spellId = state.shield.spellId;
            rune = state.shield.rune;
            spent = Hit(state.shield, now, Millis(Numbers::Num(spellId, "interval_seconds")));
        }
        // Stoneskin: when the last charge breaks, an absorb of the share of the maximum Life the sheet states, which the core drains.
        if (spent.broke && rune == Rune::Stoneskin)
        {
            double const share = Numbers::Num(spellId, "absorb_capacity_life_pct") / 100;
            double const amount = player->GetMaxHealth() * share * ItemPowers::ShieldFactor(player);
            double const seconds = Numbers::Num(spellId, "absorb_duration_seconds");
            player->RemoveAurasDueToSpell(BuffId(AbsorbBuff));
            if (Aura* aura = player->AddAura(BuffId(AbsorbBuff), player))
            {
                if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                    effect->ChangeAmount(int32(std::min(amount, double(INT32_MAX))));
                aura->SetMaxDuration(int32(Millis(seconds)));
                aura->SetDuration(int32(Millis(seconds)));
            }
        }
        if (spent.used)
        {
            ObjectGuid const from = attacker ? attacker->GetGUID() : ObjectGuid::Empty;
            player->m_Events.AddEventAtOffset(
                [player, spellId, rune, from, strike = spent.strike] { Answer(player, spellId, rune, from, strike); },
                std::chrono::milliseconds(std::uint32_t(Tunable("elemental_shield_strike_delay_ms"))));
        }
    }

    void Landed(Player* player, std::uint32_t spellId)
    {
        if (!IsShaman(player) || Classes::CategoryOf(spellId) != "Primary")
            return;
        std::lock_guard<std::mutex> guard(mutex);
        auto const found = states.find(Key(player));
        if (found == states.end() || found->second.shield.rune != Rune::LightningShield)
            return;
        std::uint32_t const shield = found->second.shield.spellId;
        if (Rolled(Roll(), Numbers::Num(shield, "proc_chance_pct")))
            AddCharge(found->second.shield, Now(), unsigned(Numbers::Num(shield, "max_count")));
    }

    void Upkeep(Player* player)
    {
        if (!IsShaman(player))
            return;
        std::uint64_t const now = Now();
        Rune rune = Rune::None;
        unsigned charges = 0;
        double seconds = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = states.find(Key(player));
            if (found != states.end())
            {
                State& state = found->second;
                if (Active(state.shield, now))
                {
                    rune = state.shield.rune;
                    charges = state.shield.charges;
                    seconds = double(state.shield.until - now) / 1000.0;
                }
            }
        }
        Armor(player, rune == Rune::Stoneskin && charges > 0);
        char const* const worn = BuffName(rune);
        for (char const* name : ShieldBuffs)
            BuffValues::Show(player, BuffId(name), charges && std::string_view(name) == worn ? charges : 0, seconds);
    }

    void Forget(Player* player)
    {
        Armor(player, false);
        std::lock_guard<std::mutex> guard(mutex);
        states.erase(Key(player));
    }
} // namespace DC::Combat::Shaman::ElementalShield

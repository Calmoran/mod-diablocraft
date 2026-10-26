// The Monk's four Mantras: one aura mechanism, and what each Mantra's passive and activation do on it.
//
// A Mantra is an aura: its passive is on while the skill is on the bar and is the Mantra in force (dc_monk_mantras.h:
// the one cast last, or every slotted one before any cast). The aura pulses; a pulse starts from the always-on hook at
// the bottom, a cast or a hit, and stops by itself when the Mantra leaves the bar or another one is cast. The press
// makes the Mantra the one in force and opens its boost window. What a pulse gives is module state, no aura records:
// stat contributions, the Monk's timed effects and stock carrier auras.

#include "dc_monk_mantras_cast.h"
#include "../dc_level_heal.h"
#include "dc_monk_common.h"
#include "dc_monk_crippling_wave.h"
#include "dc_monk_mantra_of_conviction.h"
#include "dc_monk_mantra_of_healing.h"
#include "dc_monk_mantra_of_retribution.h"
#include "dc_monk_mantra_of_salvation.h"
#include "dc_monk_mantras.h"
#include "dc_monk_spirit.h"
#include "../dc_resources.h"
#include "../../combat/dc_item_powers.h"
#include "../../stats/dc_resource_pulse.h"
#include "../../stats/dc_stats.h"
#include "Group.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Util.h"

#include <cmath>
#include <map>
#include <optional>
#include <set>
#include <unordered_set>
#include <utility>

namespace DC::Combat::Monk::Mantras
{
    namespace
    {
        // One Mantra to the mechanism: its skill's name in the sheets; the tunable holding the seconds between two
        // pulses; whether its press opens a boost window of the skill's duration_seconds; whether the slotted record
        // runs a pulse; whether the pulse goes on for this Monk now; one pulse; what comes off when the pulse stops;
        // and what the press itself does to the targets the cast resolved.
        struct Flavour
        {
            std::string_view skill;
            char const* period;
            bool boosts;
            bool (*runs)(std::uint32_t slotted);
            bool (*keeps)(Player* owner);
            void (*pulse)(Player* owner, std::uint32_t slotted);
            void (*stop)(Player* owner);
            void (*activate)(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
        };

        Shells::Ability const* Row(std::string_view skill, std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::string_view skill, std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Row(skill, spellId);
            return row && rune == row->rune;
        }

        std::uint32_t RuneId(std::string_view skill, std::string_view rune)
        {
            for (auto const& row : Shells::Abilities)
                if (skill == row.skill && rune == row.rune)
                    return row.id;
            return 0;
        }

        // The skill itself: its id carries the rows every rune reads and keys the "only one Mantra" state.
        std::uint32_t BaseId(std::string_view skill)
        {
            return RuneId(skill, "");
        }

        // The skill or rune of the Mantra on one of the player's skill buttons; 0 when none is.
        std::uint32_t Slotted(Player* player, std::string_view skill)
        {
            for (auto const& row : Shells::Abilities)
                if (skill == row.skill)
                    for (unsigned slot = 0; slot < Classes::ActiveSlots(); ++slot)
                        if (ActionButton const* button = player->GetActionButton(uint8(slot)))
                            if (button->GetType() == ACTION_BUTTON_SPELL && button->GetAction() == row.id)
                                return row.id;
            return 0;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;
        }

        // The Monk and its group within the skill's radius: "you and your allies within {radius_yards} yards". The
        // Monk first.
        std::vector<Player*> InAura(Player* owner, std::string_view skill)
        {
            std::vector<Player*> holders{owner};
            Group* group = owner->GetGroup();
            if (!group)
                return holders;
            double const radius = Numbers::Num(BaseId(skill), "radius_yards");
            for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                if (Player* member = ref->GetSource())
                    if (member != owner && member->IsAlive() && member->IsInWorld() &&
                        member->GetMap() == owner->GetMap() && owner->GetExactDist(member) <= radius)
                        holders.push_back(member);
            return holders;
        }

        // A stock carrier aura of the Monk's on `target` for `seconds`, its first effect at `amount` when one is given;
        // the Monk's earlier one comes off first. Nothing on a dead target or for no time.
        void Hold(Player* player, Unit* target, std::uint32_t aura, double seconds, std::optional<int> amount = {})
        {
            if (seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(aura, player->GetGUID());
            if (Aura* held = player->AddAura(aura, target))
            {
                if (amount)
                    if (AuraEffect* effect = held->GetEffect(EFFECT_0))
                        effect->ChangeAmount(*amount);
                held->SetMaxDuration(int32(seconds * 1000));
                held->SetDuration(int32(seconds * 1000));
            }
        }

        // Per Mantra and Monk, the pulse: `generation` tells a stopped loop's beat from the running one's (0: none
        // runs), `beat` is when it last ran, so a loop that stopped beating (a Monk who logged out) is started again.
        struct Loop
        {
            std::uint64_t generation = 0;
            std::uint64_t beat = 0;
        };
        std::mutex loopMutex;
        std::map<std::pair<Flavour const*, std::uint64_t>, Loop> loops;
        std::uint64_t generations = 0;

        bool Running(Flavour const& flavour, std::uint64_t monk)
        {
            std::lock_guard<std::mutex> guard(loopMutex);
            auto const found = loops.find({&flavour, monk});
            return found != loops.end() && found->second.generation;
        }

        // One beat: while the Mantra is slotted, is the one in force and the flavour keeps it, one pulse, and the next
        // one a period later; otherwise the loop stops and the flavour takes off what it put on.
        void Beat(Flavour const& flavour, Player* owner, std::uint64_t generation)
        {
            std::uint64_t const guid = owner->GetGUID().GetRawValue();
            std::uint32_t const slotted = Slotted(owner, flavour.skill);
            double const period = Tune(flavour.period);
            bool const on =
                flavour.runs(slotted) && period > 0 && Mantras::On(guid, BaseId(flavour.skill)) && flavour.keeps(owner);
            {
                std::lock_guard<std::mutex> guard(loopMutex);
                Loop& loop = loops[{&flavour, guid}];
                if (loop.generation != generation)
                    return;
                if (on)
                    loop.beat = Now();
                else
                    loop.generation = 0;
            }
            if (!on)
            {
                flavour.stop(owner);
                return;
            }
            flavour.pulse(owner, slotted);
            owner->m_Events.AddEventAtOffset([&flavour, owner, generation] { Beat(flavour, owner, generation); },
                                             Milliseconds(Millis(period)));
        }

        // Starts the Mantra's pulse when the skill is on the bar, is the one in force and no loop runs; a loop whose
        // last beat is three periods old has stopped beating and is replaced.
        void StartPulse(Flavour const& flavour, Player* player)
        {
            if (!player)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> guard(loopMutex);
                Loop const& loop = loops[{&flavour, guid}];
                if (loop.generation && Now() < loop.beat + 3 * Millis(Tune(flavour.period)))
                    return;
            }
            if (!Mantras::On(guid, BaseId(flavour.skill)) || !flavour.runs(Slotted(player, flavour.skill)))
                return;
            std::uint64_t generation;
            {
                std::lock_guard<std::mutex> guard(loopMutex);
                Loop& loop = loops[{&flavour, guid}];
                loop.generation = generation = ++generations;
                loop.beat = Now();
            }
            Beat(flavour, player, generation);
        }

        // The press: "Only one Mantra may be active at a time", so this one is now the one in force, and its boost
        // window runs the skill's duration_seconds; then the activation's own effect, and the pulse if none runs.
        void Press(Flavour const& flavour, Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
        {
            if (!player || !Row(flavour.skill, spellId))
                return;
            std::uint32_t const base = BaseId(flavour.skill);
            Mantras::Cast(player->GetGUID().GetRawValue(), base, Now(),
                          flavour.boosts ? Millis(Numbers::Num(base, "duration_seconds")) : 0);
            flavour.activate(player, spellId, targets);
            StartPulse(flavour, player);
        }
    } // namespace
} // namespace DC::Combat::Monk::Mantras

// Mantra of Salvation. Power/X1_Monk_MantraOfEvasion_v2.pow (D3 renamed the skill; the sheet's numbers are Evasion's):
// the aura hands every ally within SF_0 60 yards a short buff every SF_15 1 second (SF_11 1.2 seconds long), and the
// activation adds resistance for 3 seconds on top. The numbers are stat contributions (and a dodge number the hit path
// reads), rebuilt from one table by Rebuild, so what a holder wears is always what the table says is still running.
namespace DC::Combat::Monk::Salvation
{
    namespace
    {
        constexpr std::string_view Skill = "Mantra of Salvation";

        // What one holder (a Monk or an ally of one) wears, and when each number ends. `readyAt` is Divine Protection's
        // internal cooldown for this holder; it outlives the rest.
        struct Held
        {
            Timed resist, active, armor, speed, dodge, shield, protect;
            std::uint32_t protectId = 0; // Divine Protection's rune, while the aura arms it
            std::uint64_t readyAt = 0;
            bool watching = false; // a Lapse event is waiting for this holder
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Held> held;

        // The stat contributions all carry the skill's own id; a holder has one mantra aura at a time.
        std::uint64_t Key()
        {
            return Mantras::BaseId(Skill);
        }

        // Puts back exactly what the table says is running: takes the aura's contributions off, reads what the holder
        // resists without it, and adds the resistance, armor, speed and damage reduction that are still live.
        void Rebuild(Player* holder)
        {
            Held snap;
            std::uint64_t const guid = holder->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = held.find(guid);
                if (found != held.end())
                    snap = found->second;
            }
            std::uint64_t const now = Mantras::Now();
            for (unsigned e = 0; e < ElementCount; ++e)
                Stats::RemoveContribution(guid, Source::Temporary, Stat::SingleResistance, Key() * ElementCount + e);
            for (Stat stat : {Stat::Armor, Stat::MovementSpeed, Stat::SpecificReduction})
                Stats::RemoveContribution(guid, Source::Temporary, stat, Key());
            Stats::Recompute(holder);

            double const resist = TotalResistancePct(snap.resist.Of(now), snap.active.Of(now));
            if (resist > 0)
                if (auto const baseline = Stats::Get(guid))
                    for (unsigned e = 0; e < ElementCount; ++e)
                        if (double const gain = ResistanceGain(baseline->resistance[e], resist); gain > 0)
                            Stats::AddContribution(guid,
                                                   {Source::Temporary, Stat::SingleResistance, Key() * ElementCount + e,
                                                    gain, Bucket::Flat, static_cast<Element>(e)});
            if (double const pct = snap.armor.Of(now); pct > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::Armor, Key(), pct, Bucket::Percent});
            if (double const pct = snap.speed.Of(now); pct > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::MovementSpeed, Key(), pct, Bucket::Uncapped});
            if (double const pct = snap.shield.Of(now); pct > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::SpecificReduction, Key(), pct, Bucket::Flat});
            Stats::Recompute(holder);
        }

        // One event per holder at a time: when every number has run out, the contributions come off.
        void Lapse(Player* holder)
        {
            std::uint64_t const guid = holder->GetGUID().GetRawValue();
            std::uint64_t const now = Mantras::Now();
            std::uint64_t latest = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                Held& h = held[guid];
                for (Timed const* timed : {&h.resist, &h.active, &h.armor, &h.speed, &h.dodge, &h.shield, &h.protect})
                    latest = std::max(latest, timed->until);
                if (!Live(now, latest))
                    h.watching = false;
            }
            if (Live(now, latest))
            {
                holder->m_Events.AddEventAtOffset([holder] { Lapse(holder); }, Milliseconds(latest - now + 50));
                return;
            }
            Rebuild(holder);
            std::lock_guard<std::mutex> guard(mutex);
            if (now >= held[guid].readyAt)
                held.erase(guid);
        }

        void Watch(Player* holder)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                Held& h = held[holder->GetGUID().GetRawValue()];
                if (h.watching)
                    return;
                h.watching = true;
            }
            holder->m_Events.AddEventAtOffset(
                [holder] { Lapse(holder); }, Milliseconds(Millis(Mantras::Tune("mantra_salvation_hold_seconds")) + 50));
        }

        // Gives `holder` what the aura of `runeId` (the skill or the rune on the Monk's bar) hands out for one pulse;
        // an active cast adds its resistance for the skill's seconds.
        void Give(Player* holder, std::uint32_t runeId, bool cast)
        {
            std::uint32_t const base = Mantras::BaseId(Skill);
            std::uint64_t const now = Mantras::Now();
            std::uint64_t const until = now + Millis(Mantras::Tune("mantra_salvation_hold_seconds"));
            // "Passive: ... gain {resistance_pct:passive} increased resistance": the skill's, or Perseverance's own.
            double const passive =
                PassivePct(Numbers::Num(base, "resistance_pct", "passive"), Numbers::Own(runeId, "resistance_pct"));
            {
                std::lock_guard<std::mutex> guard(mutex);
                Held& h = held[holder->GetGUID().GetRawValue()];
                h.resist = {passive, until};
                h.armor = {Numbers::Own(runeId, "armor_pct").value_or(0), until};
                h.speed = {Numbers::Own(runeId, "movement_speed_pct").value_or(0), until};
                h.dodge = {Numbers::Own(runeId, "dodge_pct").value_or(0), until};
                h.protect = {};
                h.protectId = 0;
                if (Numbers::Own(runeId, "life_threshold_pct"))
                {
                    h.protect = {1, until};
                    h.protectId = runeId;
                }
                if (cast)
                    h.active = {Numbers::Num(base, "resistance_pct", "active"),
                                now + Millis(Numbers::Num(base, "duration_seconds"))};
            }
            Rebuild(holder);
            Watch(holder);
        }

        Mantras::Flavour const flavour{
            .skill = Skill,
            .period = "mantra_salvation_pulse_seconds",
            .boosts = true,
            .runs = [](std::uint32_t slotted) { return slotted != 0; },
            .keeps = [](Player*) { return true; },
            // The aura handed out again to the Monk and its group within the radius; a dead Monk hands out nothing,
            // and what it handed out lapses.
            .pulse =
                [](Player* owner, std::uint32_t runeId)
            {
                if (owner->IsAlive())
                    for (Player* holder : Mantras::InAura(owner, Skill))
                        Give(holder, runeId, false);
            },
            .stop = [](Player*) {},
            // "You and nearby allies gain an additional {resistance_pct:active} increased resistance to all elements
            // for {duration_seconds} seconds": the targets the cast resolved (self_allies).
            .activate =
                [](Player*, std::uint32_t spellId, std::vector<Unit*> const& targets)
            {
                for (Unit* unit : targets)
                    if (Player* ally = unit->ToPlayer(); ally && ally->IsAlive())
                        Give(ally, spellId, true);
            },
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Mantras::Row(Skill, spellId) != nullptr;
    }

    void Touch(Player* player)
    {
        Mantras::StartPulse(flavour, player);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        Mantras::Press(flavour, player, spellId, targets);
    }

    double Dodge(Unit const* unit)
    {
        if (!unit || !unit->IsPlayer())
            return 0;
        std::uint64_t const now = Mantras::Now();
        double dodge = 0;
        bool opened = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = held.find(unit->GetGUID().GetRawValue());
            if (found == held.end())
                return 0;
            Held& h = found->second;
            dodge = h.dodge.Of(now);
            // Divine Protection: the hit that finds the holder below the threshold opens the shield, which reduces
            // what comes after it (the stats are rebuilt on the holder's next update, not inside this hit).
            if (h.protect.Of(now) > 0 &&
                ShieldOpens(unit->GetHealthPct(), Numbers::Num(h.protectId, "life_threshold_pct"), now, h.readyAt))
            {
                h.shield = {Numbers::Num(h.protectId, "damage_reduction_pct"),
                            now + Millis(Numbers::Num(h.protectId, "duration_seconds"))};
                h.readyAt = now + Millis(Numbers::Num(h.protectId, "internal_cooldown_seconds"));
                opened = true;
            }
        }
        if (opened)
            if (Player* player = const_cast<Unit*>(unit)->ToPlayer())
                player->m_Events.AddEventAtOffset(
                    [player]
                    {
                        Rebuild(player);
                        Watch(player);
                    },
                    Milliseconds(0));
        return dodge;
    }
} // namespace DC::Combat::Monk::Salvation

// Mantra of Healing. Power/X1_Monk_MantraOfHealing_v2.pow: the aura heals the Monk and its group within SF_0 60 yards
// every SF_18 1 second, and the activation shrouds them in an absorb for 3 seconds. The Life percent and the damage
// reduction are stat contributions put on a holder at each pulse and taken off when the holder leaves the aura or the
// pulse stops.
namespace DC::Combat::Monk::Healing
{
    namespace
    {
        constexpr std::string_view Skill = "Mantra of Healing";
        // Stock "Power Word: Shield" (rank 1): one SCHOOL_ABSORB effect of every school; the amount and the time are
        // set on the aura (the carrier Serenity's absorb uses too).
        constexpr std::uint32_t Shield = 17;

        // What one holder wears from the aura now, so a pulse changes the stats only when it must.
        struct Worn
        {
            double lifePct = 0, reduction = 0;
        };

        std::mutex mutex;
        // Per Monk: the holders of the last pulse.
        std::unordered_map<std::uint64_t, std::set<std::uint64_t>> members;
        // What each holder wears from each Monk (the Monk, the holder): two Monks on different runes both reach one
        // ally.
        std::map<std::pair<std::uint64_t, std::uint64_t>, Worn> worn;

        void Heal(Player* healer, Unit* target, std::uint32_t spellId, double amount)
        {
            auto const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info || !target->IsAlive() || amount <= 0)
                return;
            HealInfo heal(healer, target, uint32(std::min(amount, double(UINT32_MAX))), info, SPELL_SCHOOL_MASK_HOLY);
            healer->HealBySpell(heal);
        }

        // The absorb on `target`: `amount` of damage of any school for `seconds`.
        void Shroud(Player* player, Unit* target, double seconds, std::int32_t amount)
        {
            if (Aura* aura = player->AddAura(Shield, target))
            {
                aura->SetMaxDuration(int32(seconds * 1000));
                aura->SetDuration(int32(seconds * 1000));
                if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                    effect->ChangeAmount(amount);
            }
        }

        // What the aura puts on a holder's stats now: Heavenly Body's maximum Life and Time of Need's reduction, which
        // applies only while the holder is below the threshold.
        void Wear(Player* owner, Player* holder, std::uint32_t runeId)
        {
            std::uint64_t const guid = holder->GetGUID().GetRawValue();
            std::uint64_t const key = Mantras::Key(owner->GetGUID().GetRawValue(), Mantras::BaseId(Skill));
            auto const pair = std::make_pair(owner->GetGUID().GetRawValue(), guid);
            Worn want;
            if (Mantras::IsRune(Skill, runeId, "Heavenly Body"))
                want.lifePct = Numbers::Num(runeId, "max_life_pct");
            if (Mantras::IsRune(Skill, runeId, "Time of Need") &&
                BelowThreshold(holder->GetHealthPct(), Numbers::Num(runeId, "life_threshold_pct")))
                want.reduction = Numbers::Num(runeId, "damage_reduction_pct");
            Worn had;
            {
                std::lock_guard<std::mutex> guard(mutex);
                had = worn[pair];
                if (had.lifePct == want.lifePct && had.reduction == want.reduction)
                    return;
                worn[pair] = want;
            }
            Stats::RemoveContribution(guid, Source::Temporary, Stat::LifePercent, key);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::SpecificReduction, key);
            if (want.lifePct > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::LifePercent, key, want.lifePct, Bucket::Flat});
            if (want.reduction > 0)
                Stats::AddContribution(guid,
                                       {Source::Temporary, Stat::SpecificReduction, key, want.reduction, Bucket::Flat});
            Stats::Recompute(holder);
        }

        void Release(std::uint64_t owner, std::uint64_t guid)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = worn.find({owner, guid});
                if (found == worn.end())
                    return;
                worn.erase(found);
            }
            std::uint64_t const key = Mantras::Key(owner, Mantras::BaseId(Skill));
            Stats::RemoveContribution(guid, Source::Temporary, Stat::LifePercent, key);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::SpecificReduction, key);
            if (Player* holder = ObjectAccessor::FindPlayer(ObjectGuid(guid)))
                Stats::Recompute(holder);
        }

        // One pulse: heal the holders, put the stats on them, and take them off whoever has left.
        void Pulse(Player* owner, std::uint32_t runeId)
        {
            std::uint64_t const guid = owner->GetGUID().GetRawValue();
            double const period = Mantras::Tune("mantra_healing_pulse_seconds");
            std::set<std::uint64_t> before;
            {
                std::lock_guard<std::mutex> guard(mutex);
                before = members[guid];
            }
            std::set<std::uint64_t> now;
            // "increase the Life regeneration granted ... to {heal_per_second_life} Life per Second. The heal amount is
            // increased by {life_per_second_share_pct} of your Life per Second": the Monk's own stat.
            double lifePerSecond = 0;
            if (auto const sheet = Stats::Get(guid))
                lifePerSecond = (*sheet)[Stat::LifeRegen];
            double const heal = PulseHeal(Classes::HealAtLevel(Numbers::Num(runeId, "heal_per_second_life"), owner->GetLevel()), lifePerSecond,
                                          Numbers::Num(runeId, "life_per_second_share_pct"), period);
            for (Player* holder : Mantras::InAura(owner, Skill))
            {
                now.insert(holder->GetGUID().GetRawValue());
                Heal(owner, holder, runeId, heal);
                Wear(owner, holder, runeId);
            }
            // Circular Breathing: "regenerates {regen_per_second_resource} Spirit per second", a pulse's worth paid as
            // a flow over the pulse.
            if (Mantras::IsRune(Skill, runeId, "Circular Breathing"))
                if (double const spirit = SpiritPerPulse(Numbers::Num(runeId, "regen_per_second_resource"), period);
                    spirit > 0)
                    Resources::Flow(owner, Resources::Spirit, spirit, std::uint32_t(Mantras::Millis(period)));
            {
                std::lock_guard<std::mutex> guard(mutex);
                members[guid] = now;
            }
            for (std::uint64_t left : Left(before, now))
                Release(guid, left);
        }

        // The pulse stopped: whoever held the aura at the last pulse loses what it wore.
        void Stop(Player* owner)
        {
            std::uint64_t const guid = owner->GetGUID().GetRawValue();
            std::set<std::uint64_t> before;
            {
                std::lock_guard<std::mutex> guard(mutex);
                before = members[guid];
                members.erase(guid);
            }
            for (std::uint64_t left : Left(before, {}))
                Release(guid, left);
        }

        Mantras::Flavour const flavour{
            .skill = Skill,
            .period = "mantra_healing_pulse_seconds",
            .boosts = false,
            .runs = [](std::uint32_t slotted) { return slotted != 0; },
            .keeps = [](Player* owner) { return owner->IsAlive(); },
            .pulse = Pulse,
            .stop = Stop,
            // "Shroud you and your allies with a mystical shield that absorbs up to {absorb_life} damage for
            // {absorb_duration_seconds} seconds. Absorb amount is increased by {healing_bonus_share_pct} of your Health
            // Globe Healing Bonus": the Monk and the targets the cast resolved (self_allies). The globe bonus has no
            // stat yet: 0.
            .activate =
                [](Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
            {
                double const amount =
                    Absorb(Classes::HealAtLevel(Numbers::Num(spellId, "absorb_life"), player->GetLevel()), Numbers::Num(spellId, "healing_bonus_share_pct"), 0.0);
                double const seconds = Numbers::Num(spellId, "absorb_duration_seconds");
                std::set<Unit*> shrouded{player};
                for (Unit* unit : targets)
                    if (Player* ally = unit->ToPlayer(); ally && ally->IsAlive())
                        shrouded.insert(ally);
                for (Unit* unit : shrouded)
                    if (unit->IsAlive())
                        Shroud(player, unit, seconds, std::int32_t(std::min(amount, 2147483000.0)));
            },
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Mantras::Row(Skill, spellId) != nullptr;
    }

    void Touch(Player* player)
    {
        Mantras::StartPulse(flavour, player);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        Mantras::Press(flavour, player, spellId, targets);
    }

    void Landed(Player* player, std::uint32_t)
    {
        if (!player || !player->IsAlive())
            return;
        std::uint32_t const runeId = Mantras::Slotted(player, Skill);
        if (!runeId || !Mantras::IsRune(Skill, runeId, "Boon of Inspiration"))
            return;
        if (!Mantras::On(player->GetGUID().GetRawValue(), Mantras::BaseId(Skill)))
            return;
        // "Mantra of Healing also heals {heal_per_hit_life} Life when hitting an enemy. Heal amount is increased by
        // {life_per_hit_share_pct} of your Life per Hit."
        double lifePerHit = 0;
        if (auto const sheet = Stats::Get(player->GetGUID().GetRawValue()))
            lifePerHit = (*sheet)[Stat::LifePerHit];
        double const heal = HitHeal(Classes::HealAtLevel(Numbers::Num(runeId, "heal_per_hit_life"), player->GetLevel()), lifePerHit,
                                    Numbers::Num(runeId, "life_per_hit_share_pct"));
        for (Player* holder : Mantras::InAura(player, Skill))
            Heal(player, holder, runeId, heal);
    }
} // namespace DC::Combat::Monk::Healing

// Mantra of Retribution. Power/X1_Monk_MantraOfRetribution_v2.pow: an aura of 60 yards whose passive hits back at
// attackers; the activation raises the damage for 3 seconds. The hit is read where damage is taken (Monk::Taken from
// the combat engine); the pulse carries Transgression's attack speed.
namespace DC::Combat::Monk::Retribution
{
    namespace
    {
        constexpr std::string_view Skill = "Mantra of Retribution";
        // Stock "Ice Blast": one instant MOD_STUN effect, the hold Monk::Stun puts on an enemy (see dc_monk.cpp).
        constexpr std::uint32_t StunHold = 15878;

        std::mutex mutex;
        // Per Monk: who carries Transgression's speed from it now.
        std::unordered_map<std::uint64_t, std::unordered_set<std::uint64_t>> buffed;
        // A reflected hit that kills or hurts a Monk who also stands under a Mantra must not reflect back.
        thread_local bool reflecting = false;

        // The Monk and its group members within the aura's reach of the Monk, alive.
        std::vector<Player*> Allies(Player* monk)
        {
            std::vector<Player*> members;
            if (Group* group = monk->GetGroup())
            {
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource())
                        members.push_back(member);
            }
            else
                members.push_back(monk);
            std::vector<Player*> in;
            for (Player* member : members)
                if (member->IsAlive() &&
                    monk->IsWithinDistInMap(member, Numbers::Num(Mantras::BaseId(Skill), "radius_yards")))
                    in.push_back(member);
            return in;
        }

        // One Monk's passive answering a hit `victim` took from `attacker`.
        void Reflect(Player* monk, Unit* attacker)
        {
            std::uint32_t const spellId = Mantras::Slotted(monk, Skill);
            std::uint32_t const base = Mantras::BaseId(Skill);
            if (!spellId || !monk->IsAlive() || !Mantras::On(monk->GetGUID().GetRawValue(), base) ||
                !attacker->IsAlive() || !monk->IsValidAttackTarget(attacker))
                return;
            // Retaliation states its own damage (202); every other rune keeps the skill's passive (101). The activation
            // adds what its 202 adds over the passive's 101, for the seconds of its window.
            double const passive = Mantras::IsRune(Skill, spellId, "Retaliation")
                                       ? Numbers::Num(spellId, "damage_pct")
                                       : Numbers::Num(base, "damage_pct", "passive");
            double const boost =
                Numbers::Num(base, "damage_pct", "active") - Numbers::Num(base, "damage_pct", "passive");
            bool const boosted = Mantras::Boosted(monk->GetGUID().GetRawValue(), base, Mantras::Now());
            if (!Strike(monk, attacker, spellId, MantraReflectPct(passive, boost, boosted)))
                return;
            // Indignation: "Enemies damaged by Mantra of Retribution have a {proc_chance_pct} chance to be stunned for
            // {stun_duration_seconds} seconds"; Dovu Energy Trap lengthens the stun.
            if (Mantras::IsRune(Skill, spellId, "Indignation") &&
                MantraProcs(Numbers::Num(spellId, "proc_chance_pct"), rand_chance()))
                Mantras::Hold(monk, attacker, StunHold,
                              Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(monk));
            // Against All Odds: "has a chance to restore {gain_resource} Spirit when dealing damage". The chance is on
            // no sheet and in no power file: a tunable, and the rune restores nothing while it is blank.
            if (Mantras::IsRune(Skill, spellId, "Against All Odds") &&
                DC::Tunables::Has("monk", "mantra_of_retribution_spirit_chance_pct") &&
                MantraProcs(Mantras::Tune("mantra_of_retribution_spirit_chance_pct"), rand_chance()))
                Generate(monk, Classes::ClassIdOf(monk), spellId, Numbers::Num(spellId, "gain_resource"));
            // Collateral Damage: a feedback blast "to itself and nearby enemies" (power file SF_20 'E: detonation
            // area').
            if (Mantras::IsRune(Skill, spellId, "Collateral Damage") &&
                MantraProcs(Numbers::Num(spellId, "proc_chance_pct"), rand_chance()))
                StrikeArea(monk, spellId, attacker->GetPosition(),
                           Mantras::Tune("mantra_of_retribution_detonation_radius_yards"),
                           Numbers::Num(spellId, "damage_pct"));
        }

        // Transgression's contribution on one player, keyed by the rune and the Monk who gives it: two Monks on one
        // ally are two contributions, and one Monk's release leaves the other's.
        void Give(Player* monk, Player* who, std::uint32_t runeId, bool recompute)
        {
            Stats::AddContribution(who->GetGUID().GetRawValue(),
                                   {Source::Temporary, Stat::AttackSpeed,
                                    Mantras::Key(monk->GetGUID().GetRawValue(), runeId),
                                    Numbers::Num(runeId, "attack_speed_pct"), Bucket::Flat});
            if (recompute)
                Stats::Recompute(who);
        }

        void Take(std::uint64_t monk, std::uint64_t guid, std::uint32_t runeId)
        {
            Stats::RemoveContribution(guid, Source::Temporary, Stat::AttackSpeed, Mantras::Key(monk, runeId));
            if (Player* who = ObjectAccessor::FindPlayer(ObjectGuid(guid)))
                Stats::Recompute(who);
        }

        // One beat of Transgression: the Monk and its group members within the aura carry the speed, the others lose
        // it; a dead Monk's aura carries it to nobody.
        void Pulse(Player* monk, std::uint32_t runeId)
        {
            std::uint64_t const self = monk->GetGUID().GetRawValue();
            std::unordered_set<std::uint64_t> had;
            {
                std::lock_guard<std::mutex> guard(mutex);
                had = buffed[self];
            }
            std::vector<Player*> const want = monk->IsAlive() ? Allies(monk) : std::vector<Player*>{};
            std::unordered_set<std::uint64_t> now;
            for (Player* who : want)
            {
                std::uint64_t const guid = who->GetGUID().GetRawValue();
                now.insert(guid);
                Give(monk, who, runeId, !had.count(guid));
            }
            for (std::uint64_t guid : had)
                if (!now.count(guid))
                    Take(self, guid, runeId);
            std::lock_guard<std::mutex> guard(mutex);
            buffed[self] = now;
        }

        // The pulse stopped: everyone carrying the speed from this Monk loses it.
        void Stop(Player* monk)
        {
            std::uint64_t const self = monk->GetGUID().GetRawValue();
            std::unordered_set<std::uint64_t> had;
            {
                std::lock_guard<std::mutex> guard(mutex);
                had.swap(buffed[self]);
            }
            std::uint32_t const runeId = Mantras::RuneId(Skill, "Transgression");
            for (std::uint64_t guid : had)
                Take(self, guid, runeId);
        }

        Mantras::Flavour const flavour{
            .skill = Skill,
            .period = "mantra_of_retribution_buff_tick_seconds",
            .boosts = true,
            // The passive's reflect needs no pulse: only Transgression's speed is handed out by one.
            .runs = [](std::uint32_t slotted) { return Mantras::IsRune(Skill, slotted, "Transgression"); },
            .keeps = [](Player*) { return true; },
            .pulse = Pulse,
            .stop = Stop,
            .activate = [](Player*, std::uint32_t, std::vector<Unit*> const&) {},
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Mantras::Row(Skill, spellId) != nullptr;
    }

    void Touch(Player* player)
    {
        Mantras::StartPulse(flavour, player);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        Mantras::Press(flavour, player, spellId, targets);
    }

    void Taken(Unit* victim, Unit* attacker)
    {
        if (reflecting || !victim || !attacker || victim == attacker)
            return;
        Player* hit = victim->ToPlayer();
        if (!hit)
            return;
        reflecting = true;
        for (Player* monk : Allies(hit))
            Reflect(monk, attacker);
        reflecting = false;
    }
} // namespace DC::Combat::Monk::Retribution

// Mantra of Conviction. Power/X1_Monk_MantraOfConviction_v2.pow: an aura of SF_5 30 yards that ticks every SF_4 0.5 s
// and marks the enemies in it for SF_3 0.6 s. The marks are the Monk's timed effects (dc_monk_effects: Taken for the
// damage they take, Weaken for Intimidation's), Dishearten's slow is stock Dazed and Annihilation's speed stock Speed.
namespace DC::Combat::Monk::Conviction
{
    namespace
    {
        constexpr std::string_view Skill = "Mantra of Conviction";
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, Snare mechanic; Crippling Wave's slow carrier, here
        // Dishearten's, at the sheet's slow_pct.
        constexpr std::uint32_t Dazed = 50259;
        // Stock "Speed" (14530): one MOD_INCREASE_SPEED effect on the target itself; Breath of Heaven - Zephyr's
        // carrier, here Annihilation's, at the sheet's movement_speed_pct.
        constexpr std::uint32_t Hasted = 14530;

        std::mutex mutex;
        // Per Monk: the enemies the last tick marked (Annihilation's "an enemy that is affected").
        std::unordered_map<std::uint64_t, std::unordered_set<std::uint64_t>> affected;

        // One aura tick: every enemy within the radius is marked for SF_3 seconds with what the slotted rune does.
        void Pulse(Player* player, std::uint32_t spellId)
        {
            std::uint32_t const base = Mantras::BaseId(Skill);
            double const hold = Mantras::Tune("mantra_of_conviction_hold_seconds");
            bool const boosted = Mantras::Boosted(player->GetGUID().GetRawValue(), base, Mantras::Now());
            double const passive = Mantras::IsRune(Skill, spellId, "Overawe")
                                       ? Numbers::Num(spellId, "damage_taken_pct")
                                       : Numbers::Num(base, "damage_taken_pct", "passive");
            double const taken = TakenPct(passive, Numbers::Num(base, "damage_taken_pct", "active"),
                                          Numbers::Num(base, "damage_taken_pct", "passive"), boosted);
            std::unordered_set<std::uint64_t> marked;
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(base, "radius_yards")))
            {
                marked.insert(enemy->GetGUID().GetRawValue());
                Effects::Taken(enemy, base, taken, hold);
                // Intimidation: "Enemies affected by Mantra of Conviction deal {enemy_damage_pct} less damage."
                if (Mantras::IsRune(Skill, spellId, "Intimidation"))
                    Effects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), hold);
                // Dishearten: "also slows the movement speed of enemies by {slow_pct}".
                if (Mantras::IsRune(Skill, spellId, "Dishearten"))
                    Mantras::Hold(player, enemy, Dazed, hold, Wave::SlowAmount(Numbers::Num(spellId, "slow_pct")));
                // Submission: "take {damage_pct} weapon damage per second as Holy", a damage-over-time tick.
                if (Mantras::IsRune(Skill, spellId, "Submission"))
                    Combat::Strike(player, enemy, spellId,
                                   TickPct(Numbers::Num(spellId, "damage_pct"),
                                           Mantras::Tune("mantra_of_conviction_tick_seconds")),
                                   true);
            }
            std::lock_guard<std::mutex> guard(mutex);
            affected[player->GetGUID().GetRawValue()] = std::move(marked);
        }

        // Off the bar, dead or another Mantra in force: the loop stops and the marks run out by themselves.
        void Stop(Player* player)
        {
            std::lock_guard<std::mutex> guard(mutex);
            affected[player->GetGUID().GetRawValue()].clear();
        }

        // Annihilation: "grants you and your allies {movement_speed_pct} increased movement speed for
        // {duration_seconds} seconds" - the Monk and the group members within SF_23 'D: Search Radius' of it.
        void Annihilate(Player* player, std::uint32_t spellId)
        {
            int const amount = int(std::lround(Numbers::Num(spellId, "movement_speed_pct")));
            double const seconds = Numbers::Num(spellId, "duration_seconds");
            Mantras::Hold(player, player, Hasted, seconds, amount);
            if (Group* group = player->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource();
                        member && member != player && member->IsAlive() &&
                        player->IsWithinDistInMap(member, Mantras::Tune("mantra_of_conviction_ally_radius_yards")))
                        Mantras::Hold(player, member, Hasted, seconds, amount);
        }

        Mantras::Flavour const flavour{
            .skill = Skill,
            .period = "mantra_of_conviction_tick_seconds",
            .boosts = true,
            .runs = [](std::uint32_t slotted) { return slotted != 0; },
            .keeps = [](Player* owner) { return owner->IsAlive() && owner->IsInWorld(); },
            .pulse = Pulse,
            .stop = Stop,
            .activate = [](Player*, std::uint32_t, std::vector<Unit*> const&) {},
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Mantras::Row(Skill, spellId) != nullptr;
    }

    void Touch(Player* player)
    {
        Mantras::StartPulse(flavour, player);
    }

    // "Active: Damage bonus is increased to {damage_taken_pct:active} for {duration_seconds} seconds."
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        Mantras::Press(flavour, player, spellId, targets);
    }

    void Landed(Player* player, Unit* target, std::uint32_t /*spellId*/)
    {
        if (!player || !target)
            return;
        Touch(player);
        // Annihilation: "Killing an enemy that is affected by Mantra of Conviction": the hit that landed killed one the
        // last tick marked.
        if (target->IsAlive())
            return;
        std::uint32_t const slotted = Mantras::Slotted(player, Skill);
        if (!Mantras::IsRune(Skill, slotted, "Annihilation") ||
            !Mantras::Running(flavour, player->GetGUID().GetRawValue()))
            return;
        {
            std::lock_guard<std::mutex> guard(mutex);
            if (!affected[player->GetGUID().GetRawValue()].erase(target->GetGUID().GetRawValue()))
                return;
        }
        Annihilate(player, slotted);
    }
} // namespace DC::Combat::Monk::Conviction

// The always-on hook: a Monk's slotted Mantra has its passive from the moment it is on the bar, login included. On the
// first update after login and then every poll, each Mantra's Touch starts a pulse that is not running and does nothing
// for a Mantra that is not slotted.
namespace DC::Combat::Monk::Mantras
{
    namespace
    {
        // How often the bar is looked at, in milliseconds: a Mantra slotted in play starts within this long.
        constexpr std::uint32_t PollMs = 1000;

        std::mutex waitedMutex;
        // Per player: the milliseconds since the bar was last looked at; absent at login, which looks at once.
        std::unordered_map<std::uint64_t, std::uint32_t> waited;

        void Start(Player* player)
        {
            Salvation::Touch(player);
            Retribution::Touch(player);
            Healing::Touch(player);
            Conviction::Touch(player);
        }

        class Always final : public PlayerScript
        {
        public:
            Always()
                : PlayerScript("dc_monk_mantras_always", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, std::uint32_t diff) override
            {
                if (!player || !player->IsInWorld())
                    return;
                {
                    std::lock_guard<std::mutex> guard(waitedMutex);
                    auto const found = waited.find(player->GetGUID().GetRawValue());
                    if (found == waited.end())
                        waited[player->GetGUID().GetRawValue()] = 0;
                    else if ((found->second += diff) < PollMs)
                        return;
                    else
                        found->second = 0;
                }
                Start(player);
            }

            void OnPlayerLogout(Player* player) override
            {
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                {
                    std::lock_guard<std::mutex> guard(waitedMutex);
                    waited.erase(guid);
                }
                Forget(guid);
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Always();
    }
} // namespace DC::Combat::Monk::Mantras

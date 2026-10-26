/*
 * Dashing Strike. The sheets: monk_skills.csv, monk_runes.csv, monk_skill_values.csv; the power file
 * Power/X1_Monk_DashingStrike.pow.
 *
 * The dash and its hit are the shared cast path's: the record's CHARGE_DEST moves the Monk to the point, and the line
 * (skill_targeting.csv, 50 yards long, 2 wide) hits every enemy on it at the skill's 370%. What is here is the rest:
 * the charges, Barrage's damage over time and the three runes' 4-second buffs.
 */

#include "dc_monk_common.h"
#include "dc_monk_dashing_strike.h"
#include "dc_monk_effects.h"
#include "../../combat/dc_charge_store.h"
#include "../../stats/dc_stats.h"
#include "ObjectAccessor.h"

#include <cmath>

namespace DC::Combat::Monk::DashingStrike
{
    namespace
    {
        constexpr std::string_view Skill = "Dashing Strike";

        // Per Monk: the charges, when each speed buff runs out (rune spell id -> ms) and Blinding Speed's dodge.
        struct State
        {
            ChargeStore charges;
            std::unordered_map<std::uint32_t, std::uint64_t> until;
            Book dodge;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        std::uint32_t SkillId()
        {
            for (auto const& ability : Shells::Abilities)
                if (Skill == ability.skill && !*ability.rune)
                    return ability.id;
            return 0;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(std::llround(std::max(0.0, seconds) * 1000.0));
        }

        // "Gain {x} increased ... for {duration_seconds} seconds after using Dashing Strike": a stat contribution under
        // the rune's id, taken off when its time is over; a dash inside it renews the time.
        void Buff(Player* player, std::uint32_t spellId, Stat stat, double pct, Bucket bucket)
        {
            std::uint64_t const ms = Millis(Numbers::Num(spellId, "duration_seconds"));
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> guard(mutex);
                states[guid].until[spellId] = Now() + ms;
            }
            Stats::AddContribution(guid, {Source::Temporary, stat, spellId, pct, bucket});
            Stats::Recompute(player);
            player->m_Events.AddEventAtOffset(
                [player, spellId, stat]
                {
                    std::uint64_t const id = player->GetGUID().GetRawValue();
                    {
                        std::lock_guard<std::mutex> guard(mutex);
                        auto& until = states[id].until;
                        auto found = until.find(spellId);
                        if (found == until.end() || Now() < found->second)
                            return; // renewed by a later dash: that dash's removal is the one due
                        until.erase(found);
                    }
                    Stats::RemoveContribution(id, Source::Temporary, stat, spellId);
                    Stats::Recompute(player);
                },
                Milliseconds(ms + 50));
        }

        // Barrage's ticks on one enemy, `left` of them still to come.
        void Tick(Player* player, ObjectGuid enemy, std::uint32_t spellId, double pct, unsigned left,
                  std::uint64_t every)
        {
            Unit* target = ObjectAccessor::GetUnit(*player, enemy);
            if (!target || !target->IsAlive() || !player->IsAlive())
                return;
            Combat::Strike(player, target, spellId, pct, true);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, enemy, spellId, pct, left, every]
                                                  { Tick(player, enemy, spellId, pct, left - 1, every); },
                                                  Milliseconds(every));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // Every rune dashes for the skill's 370%. Barrage's own 975% is its damage over time, not the dash's, and the
        // three buff runes state a duration (which alone would load them with no hit, dc_combat.cpp DamageWaits).
        if (!Row(spellId))
            return std::nullopt;
        return Numbers::Own(SkillId(), "damage_pct");
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        auto const* row = Row(spellId);
        if (!player || !row)
            return;
        std::string_view const rune = row->rune;

        // The charge this dash spends (Quicksilver's charge_count is its own 3, the rest inherit 2). The recharge is
        // the record's, reduced as a cooldown is (Furious Charge's: D3's fixCooldown scales both alike).
        unsigned const cap = unsigned(Numbers::Num(spellId, "charge_count"));
        std::uint32_t const period = ReducedCooldownMilliseconds(
            player, spellId, std::uint32_t(Millis(Numbers::Num(spellId, "charge_recharge_seconds"))));
        std::uint64_t wait = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            wait = states[player->GetGUID().GetRawValue()].charges.Spend(Now(), cap, period);
        }
        // The core put the record's cooldown on the button; a charge left clears it, none left holds it until the
        // next lands.
        SendSkillCooldown(player, spellId, std::uint32_t(wait));

        if (rune == "Barrage" && !targets.empty())
        {
            // "The last enemy you dash through": the one on the line farthest from where the dash began (the Monk has
            // not moved yet when the cast resolves).
            Unit* last = *std::max_element(targets.begin(), targets.end(), [player](Unit* a, Unit* b)
                                           { return player->GetExactDistSq(a) < player->GetExactDistSq(b); });
            double const tickSeconds = DC::Tunables::Get("monk", "dashing_strike_barrage_tick_seconds");
            Ticks const ticks =
                Split(Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "dot_duration_seconds"), tickSeconds);
            if (ticks.count)
            {
                std::uint64_t const every = Millis(tickSeconds);
                ObjectGuid const enemy = last->GetGUID();
                double const pct = ticks.pctEach;
                unsigned const count = ticks.count;
                player->m_Events.AddEventAtOffset([player, enemy, spellId, pct, count, every]
                                                  { Tick(player, enemy, spellId, pct, count, every); },
                                                  Milliseconds(every));
            }
        }
        else if (rune == "Way of the Falling Star")
            Buff(player, spellId, Stat::MovementSpeed, Numbers::Num(spellId, "movement_speed_pct"), Bucket::Uncapped);
        else if (rune == "Radiance")
            Buff(player, spellId, Stat::AttackSpeed, Numbers::Num(spellId, "attack_speed_pct"), Bucket::Flat);
        else if (rune == "Blinding Speed")
        {
            std::lock_guard<std::mutex> guard(mutex);
            states[player->GetGUID().GetRawValue()].dodge.Apply(spellId, Numbers::Num(spellId, "dodge_pct"), Now(),
                                                                Millis(Numbers::Num(spellId, "duration_seconds")));
        }
    }

    double Dodge(Unit const* unit)
    {
        if (!unit || !unit->IsPlayer())
            return 0;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = states.find(unit->GetGUID().GetRawValue());
        return found == states.end() ? 0 : found->second.dodge.Total(Now());
    }
} // namespace DC::Combat::Monk::DashingStrike

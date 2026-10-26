/*
 * Locust Swarm and its five runes. The cast is the engine's single-enemy cast (a spell record and the sheet's numbers:
 * the Mana cost, each rune's school); here: the swarm that damages its host tick by tick and jumps on to nearby
 * enemies, and each rune's part: Searing Locusts' larger damage, Pestilence's double jump, Cloud of Insects' weakness,
 * Devouring Swarm's Mana, Diseased Swarm's cloud.
 */

#include "dc_witch_doctor_locust_swarm.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_mana.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <functional>
#include <map>
#include <mutex>

namespace DC::Combat::WitchDoctor::LocustSwarm
{
    namespace
    {
        constexpr std::string_view Skill = "Locust Swarm";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        struct Swarm
        {
            std::uint64_t stamp = 0;
            std::uint32_t spellId = 0;
            ObjectGuid host;
            Position lastSeen;      // where the host stood when it was last struck
            double leftSeconds = 0; // what is left of the swarm on it
            bool first = false;     // the enemy the cast was aimed at
        };
        std::mutex mutex;
        std::map<std::uint64_t, std::vector<Swarm>> swarms; // by player
        std::uint64_t counter = 0;

        double Duration()
        {
            return Numbers::Num(BaseId(Skill), "dot_duration_seconds");
        }

        // Work that comes due `ms` from now, on the player's own queue, if the Witch Doctor is still there.
        void After(Player* player, std::uint32_t ms, std::function<void()> work)
        {
            player->m_Events.AddEventAtOffset(
                [player, work = std::move(work)]
                {
                    if (player->IsAlive() && player->IsInWorld())
                        work();
                },
                std::chrono::milliseconds(ms));
        }

        std::vector<ObjectGuid> Hosts(Player* player)
        {
            std::vector<ObjectGuid> out;
            std::lock_guard<std::mutex> guard(mutex);
            for (Swarm const& swarm : swarms[player->GetGUID().GetRawValue()])
                out.push_back(swarm.host);
            return out;
        }

        void Drop(Player* player, std::uint64_t stamp)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto& mine = swarms[player->GetGUID().GetRawValue()];
            mine.erase(std::remove_if(mine.begin(), mine.end(), [stamp](Swarm const& s) { return s.stamp == stamp; }),
                       mine.end());
        }

        // Diseased Swarm: "leave behind a cloud of locusts that deal {damage_pct} weapon damage as Poison over
        // {dot_duration_seconds} seconds to enemies who stand in the area": a pulse every cloud tick, each enemy in the
        // area taking an even share.
        void Cloud(Player* player, std::uint32_t spellId, Position const& where)
        {
            unsigned const pulses = PeriodicStrike::Ticks(Numbers::Num(spellId, "dot_duration_seconds"),
                                                          Tune("locust_swarm_cloud_tick_seconds"));
            double const pct = PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), pulses);
            for (unsigned pulse = 0; pulse < pulses; ++pulse)
                After(player, CloudPulseMs(pulse, Tune("locust_swarm_cloud_tick_seconds")),
                      [=]
                      {
                          for (Unit* enemy :
                               Combat::Enemies(player, spellId, where, Tune("locust_swarm_cloud_area_yards")))
                              Combat::Strike(player, enemy, spellId, pct, true);
                      });
        }

        void Infect(Player* player, std::uint32_t spellId, Unit* enemy, bool first);

        // The jump: "The locusts will jump to additional nearby enemies": the nearest enemies within the file's radius
        // that no swarm of the Witch Doctor holds, one or, for Pestilence, sometimes two.
        void Jump(Player* player, std::uint64_t stamp)
        {
            Swarm swarm;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = swarms[player->GetGUID().GetRawValue()];
                auto found =
                    std::find_if(mine.begin(), mine.end(), [stamp](Swarm const& s) { return s.stamp == stamp; });
                if (found == mine.end())
                    return;
                swarm = *found;
            }
            Unit* host = ObjectAccessor::GetUnit(*player, swarm.host);
            if (!host || !host->IsAlive())
                return;
            auto const held = Hosts(player);
            std::vector<Unit*> free;
            std::vector<double> distances;
            for (Unit* enemy :
                 Combat::Enemies(player, swarm.spellId, host->GetPosition(), Tune("locust_swarm_jump_radius_yards")))
                if (enemy != host && enemy->IsAlive() &&
                    std::find(held.begin(), held.end(), enemy->GetGUID()) == held.end())
                {
                    free.push_back(enemy);
                    distances.push_back(host->GetExactDist(enemy));
                }
            unsigned const reach =
                Jumps(RuneAt(swarm.spellId), Numbers::Get(swarm.spellId, "proc_chance_pct").value_or(0.0),
                      frand(0.0f, 100.0f));
            for (unsigned jump = 0; jump < reach; ++jump)
            {
                auto const nearest = Nearest(distances);
                if (!nearest)
                    break;
                Infect(player, swarm.spellId, free[*nearest], false);
                free.erase(free.begin() + *nearest);
                distances.erase(distances.begin() + *nearest);
            }
        }

        void Tick(Player* player, std::uint64_t stamp)
        {
            Swarm swarm;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = swarms[player->GetGUID().GetRawValue()];
                auto found =
                    std::find_if(mine.begin(), mine.end(), [stamp](Swarm const& s) { return s.stamp == stamp; });
                if (found == mine.end())
                    return;
                swarm = *found;
            }
            std::uint32_t const spellId = swarm.spellId;
            Rune const rune = RuneAt(spellId);
            double const tick = Tune("locust_swarm_tick_seconds");
            Unit* host = ObjectAccessor::GetUnit(*player, swarm.host);
            if (!host || !host->IsAlive())
            {
                if (LeavesCloud(rune, true, swarm.leftSeconds))
                    Cloud(player, spellId, swarm.lastSeen);
                Drop(player, stamp);
                return;
            }
            swarm.lastSeen = host->GetPosition();
            unsigned const ticks = PeriodicStrike::Ticks(Duration(), tick);
            double const total =
                SwarmTotal(rune, Numbers::Num(BaseId(Skill), "damage_pct"), Numbers::Num(spellId, "damage_pct"));
            Combat::Strike(player, host, spellId, PeriodicStrike::TickPct(total, ticks), true);
            // "Gain {regen_per_second_resource} Mana a second while the first enemy hit by a Locust Swarm cast is still
            // affected."
            if (rune == Rune::DevouringSwarm && swarm.first)
                Gain(player, Classes::ClassIdOf(player), spellId,
                     PerTick(Numbers::Num(spellId, "regen_per_second_resource"), tick), 1);
            swarm.leftSeconds = Left(swarm.leftSeconds, tick);
            if (swarm.leftSeconds <= 0)
            {
                Drop(player, stamp);
                return;
            }
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = swarms[player->GetGUID().GetRawValue()];
                auto found =
                    std::find_if(mine.begin(), mine.end(), [stamp](Swarm const& s) { return s.stamp == stamp; });
                if (found == mine.end())
                    return;
                *found = swarm;
            }
            After(player, std::uint32_t(tick * 1000.0 + 0.5), [player, stamp] { Tick(player, stamp); });
        }

        // The swarm settles on `enemy`: one already on it is replaced, the swarmed deal less (Cloud of Insects), and it
        // will jump.
        void Infect(Player* player, std::uint32_t spellId, Unit* enemy, bool first)
        {
            Swarm swarm;
            swarm.spellId = spellId;
            swarm.host = enemy->GetGUID();
            swarm.lastSeen = enemy->GetPosition();
            swarm.leftSeconds = Duration();
            swarm.first = first;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = swarms[player->GetGUID().GetRawValue()];
                mine.erase(
                    std::remove_if(mine.begin(), mine.end(), [&](Swarm const& s) { return s.host == swarm.host; }),
                    mine.end());
                swarm.stamp = ++counter;
                mine.push_back(swarm);
            }
            // "Enemies affected deal {enemy_damage_pct} reduced damage."
            if (RuneAt(spellId) == Rune::CloudOfInsects)
                EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), swarm.leftSeconds);
            std::uint64_t const stamp = swarm.stamp;
            After(player, std::uint32_t(Tune("locust_swarm_tick_seconds") * 1000.0 + 0.5),
                  [player, stamp] { Tick(player, stamp); });
            After(player,
                  std::uint32_t(JumpDelay(Tune("locust_swarm_jump_min_seconds"),
                                          Tune("locust_swarm_jump_delta_seconds"), frand(0.0f, 1.0f)) *
                                    1000.0 +
                                0.5),
                  [player, stamp] { Jump(player, stamp); });
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || targets.empty() || !Is(spellId))
            return;
        Infect(player, spellId, targets.front(), true);
    }
} // namespace DC::Combat::WitchDoctor::LocustSwarm

/*
 * Caltrops and its five runes. The cast is the engine's ground-aimed spell (a record and the sheet's numbers) that lays the
 * trap; here: the trap that waits for an enemy and springs, the slow it puts on the enemies in its area every tick for as
 * long as it lasts, and the rune's part: Jagged Spikes' damage, Torturous Ground's immobilize, Bait the Trap's critical hit
 * chance. Hooked Spines' stronger slow and Carved Stakes' cheaper cost are sheet numbers the same code reads.
 */

#include "dc_demon_hunter_caltrops.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <algorithm>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Caltrops
{
    namespace
    {
        constexpr std::string_view Skill = "Caltrops";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        struct Trap
        {
            std::uint32_t spellId = 0;
            Position center;
            bool sprung = false;
            double waited = 0; // ms laid and still waiting
            double left = 0;   // ms the sprung trap lasts
            double clock = 0;  // ms since the last tick
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::vector<Trap>> traps;

        // "When the trap is sprung, all enemies in the area are immobilized for {immobilize_duration_seconds} seconds."
        void Spring(Player* player, Trap& trap)
        {
            trap.sprung = true;
            trap.left = Numbers::Num(trap.spellId, "duration_seconds") * Passive::DurationFactor(player, "Caltrops") * 1000.0;
            if (RuneAt(trap.spellId) == Rune::TorturousGround)
                for (Unit* enemy : Combat::Enemies(player, trap.spellId, trap.center, Numbers::Num(trap.spellId, "radius_yards")))
                    Root(player, enemy, Numbers::Num(trap.spellId, "immobilize_duration_seconds"));
        }

        // One tick of a sprung trap: "Slow the movement of enemies within {radius_yards} yards by {slow_pct}", Jagged Spikes'
        // share of its damage, Bait the Trap's critical hit chance for a Demon Hunter in the area.
        void Tick(Player* player, Trap& trap, unsigned ticks)
        {
            std::uint32_t const spellId = trap.spellId;
            double const radius = Numbers::Num(spellId, "radius_yards");
            Rune const rune = RuneAt(spellId);
            for (unsigned i = 0; i < ticks; ++i)
                for (Unit* enemy : Combat::Enemies(player, spellId, trap.center, radius))
                {
                    Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), Tune("caltrops_slow_seconds"));
                    if (rune == Rune::JaggedSpikes)
                        Combat::Strike(player, enemy, spellId,
                                       TickPct(Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "dot_duration_seconds"),
                                               Tune("caltrops_tick_seconds")),
                                       true);
                }
            // "gaining an additional {crit_chance_pct} Critical Hit Chance" while standing in the area: checked on every tick, and
            // given for the linger time, which lapses soon after the Demon Hunter steps out.
            if (ticks && rune == Rune::BaitTheTrap && player->GetExactDist(&trap.center) <= radius)
                Buffs::Stack(player, spellId, Stat::CritChance, Bucket::Flat, Numbers::Num(spellId, "crit_chance_pct"), 1,
                             Tune("caltrops_bait_linger_seconds"));
        }

        // Whether any enemy stands in the area of the waiting trap: "activates when an enemy approaches".
        bool Approached(Player* player, Trap const& trap)
        {
            return !Combat::Enemies(player, trap.spellId, trap.center, Numbers::Num(trap.spellId, "radius_yards")).empty();
        }

        class Traps final : public PlayerScript
        {
        public:
            Traps()
                : PlayerScript("dc_demon_hunter_caltrops", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                std::vector<Trap> mine;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = traps.find(player->GetGUID().GetRawValue());
                    if (found == traps.end())
                        return;
                    mine = found->second;
                }
                if (!player->IsAlive())
                {
                    Stop(player);
                    return;
                }
                std::vector<Trap> kept;
                for (Trap& trap : mine)
                {
                    if (!trap.sprung)
                    {
                        trap.waited += diff;
                        if (WaitedOut(trap.waited, Tune("caltrops_activation_wait_seconds") * 1000.0))
                            continue;
                        if (Approached(player, trap))
                            Spring(player, trap);
                    }
                    if (trap.sprung)
                    {
                        trap.left -= diff;
                        Tick(player, trap, Due(trap.clock, diff, Tune("caltrops_tick_seconds") * 1000.0));
                        if (trap.left <= 0)
                            continue;
                    }
                    kept.push_back(trap);
                }
                std::lock_guard<std::mutex> guard(mutex);
                // Traps laid during this update were added to the stored list; keep them with what still stands.
                auto found = traps.find(player->GetGUID().GetRawValue());
                if (found == traps.end())
                    return;
                for (std::size_t i = mine.size(); i < found->second.size(); ++i)
                    kept.push_back(found->second[i]);
                found->second = std::move(kept);
            }

            void OnPlayerLogout(Player* player) override
            {
                Stop(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Stop(player);
            }

            static void Stop(Player* player)
            {
                std::lock_guard<std::mutex> guard(mutex);
                traps.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Trap trap;
        trap.spellId = spellId;
        trap.center = center;
        std::lock_guard<std::mutex> guard(mutex);
        auto& laid = traps[player->GetGUID().GetRawValue()];
        // "Max Traps": the oldest give way.
        laid.erase(laid.begin(), laid.begin() + std::ptrdiff_t(Overflow(laid.size(), std::size_t(Tune("caltrops_max_traps")))));
        laid.push_back(trap);
    }

    void RegisterScripts()
    {
        new Traps();
    }
} // namespace DC::Combat::DemonHunter::Caltrops

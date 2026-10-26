/*
 * The Demon Hunter's damage over time: ticks of average-crit damage on an enemy, one running per Demon Hunter, enemy and
 * spell.
 */

#include "dc_demon_hunter_dot.h"
#include "../../combat/dc_combat.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <map>
#include <mutex>
#include <tuple>

namespace DC::Combat::DemonHunter::Dot
{
    namespace
    {
        // The running damage: a new one takes a new stamp, and the ticks of the old one find their stamp gone and stop.
        using Key = std::tuple<std::uint64_t, std::uint64_t, std::uint32_t>;
        std::mutex mutex;
        std::map<Key, std::uint64_t> running;
        std::uint64_t stamps = 0;

        void Tick(Player* player, ObjectGuid enemy, std::uint32_t spellId, std::uint64_t stamp, unsigned left, double pct,
                  std::uint32_t intervalMs)
        {
            Key const key{player->GetGUID().GetRawValue(), enemy.GetRawValue(), spellId};
            Unit* target = ObjectAccessor::GetUnit(*player, enemy);
            bool const alive = target && target->IsAlive() && player->IsAlive();
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = running.find(key);
                if (found == running.end() || found->second != stamp)
                    return;
                if (!alive || left == 0)
                {
                    running.erase(found);
                    return;
                }
            }
            Combat::Strike(player, target, spellId, pct, true);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, enemy, spellId, stamp, left, pct, intervalMs]
                                                  { Tick(player, enemy, spellId, stamp, left - 1, pct, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
            else
            {
                std::lock_guard<std::mutex> guard(mutex);
                running.erase(key);
            }
        }
    } // namespace

    void Start(Player* player, Unit* enemy, std::uint32_t spellId, double totalPct, double seconds, double tickSeconds)
    {
        unsigned const ticks = Ticks(seconds, tickSeconds);
        if (!player || !enemy || !ticks)
            return;
        std::uint64_t stamp;
        {
            std::lock_guard<std::mutex> guard(mutex);
            stamp = ++stamps;
            running[{player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue(), spellId}] = stamp;
        }
        auto const interval = std::uint32_t(tickSeconds * 1000 + 0.5);
        double const pct = TickPct(totalPct, ticks);
        player->m_Events.AddEventAtOffset([player, guid = enemy->GetGUID(), spellId, stamp, ticks, pct, interval]
                                          { Tick(player, guid, spellId, stamp, ticks, pct, interval); },
                                          std::chrono::milliseconds(interval));
    }
} // namespace DC::Combat::DemonHunter::Dot

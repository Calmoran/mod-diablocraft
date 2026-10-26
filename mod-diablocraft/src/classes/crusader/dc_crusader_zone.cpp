/*
 * The Crusader's ground zones: ticks of damage on the enemies standing in a place.
 */

#include "dc_crusader_zone.h"
#include "dc_crusader_common.h"
#include "dc_crusader_dot.h"

namespace DC::Combat::Crusader::Zone
{
    namespace
    {
        // One tick. The ticks left bound the zone by themselves, as a pool's do: no clock test may stop the last one.
        void Tick(Player* player, std::uint32_t spellId, Position where, double radius, double pct, unsigned left,
                  std::uint32_t intervalMs)
        {
            if (!player->IsInWorld() || !player->IsAlive() || left == 0)
                return;
            for (Unit* enemy : Combat::Enemies(player, spellId, where, radius))
                Combat::Strike(player, enemy, spellId, pct, true);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, where, radius, pct, left, intervalMs]
                                                  { Tick(player, spellId, where, radius, pct, left - 1, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
        }
    } // namespace

    void Lay(Player* player, std::uint32_t spellId, Position where, double radius, double pctPerTick, double seconds,
             double tickSeconds)
    {
        unsigned const ticks = Dot::Ticks(seconds, tickSeconds);
        if (!player || radius <= 0 || !ticks)
            return;
        auto const interval = std::uint32_t(tickSeconds * 1000 + 0.5);
        player->m_Events.AddEventAtOffset([player, spellId, where, radius, pctPerTick, ticks, interval]
                                          { Tick(player, spellId, where, radius, pctPerTick, ticks, interval); },
                                          std::chrono::milliseconds(interval));
    }
} // namespace DC::Combat::Crusader::Zone

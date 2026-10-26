#pragma once
// A skill's damage over time on an enemy ("... and an additional {damage_pct} weapon damage over {dot_duration_seconds}
// seconds"): ticks of average-crit damage, one running per player, enemy, spell and slot, a new one starting it over.
// The tick arithmetic is header-only so the harness of the skills that use it compiles this exact code; Start is
// dc_periodic_strike.cpp's.
#include <cmath>
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::PeriodicStrike
{
    // The ticks that fit the duration at `tickSeconds`. No tick length, no ticks.
    inline unsigned Ticks(double seconds, double tickSeconds)
    {
        return seconds > 0 && tickSeconds > 0 ? static_cast<unsigned>(std::floor(seconds / tickSeconds + 1e-9)) : 0u;
    }

    // Each tick's share of the total.
    inline double TickPct(double totalPct, unsigned ticks)
    {
        return ticks ? totalPct / ticks : 0.0;
    }

    // `totalPct` of weapon damage as `spellId` on `enemy`, spread over `seconds` in ticks of `tickSeconds`. A skill
    // with two damages over time of one spell (Flaming Dart's poison and fire) gives each its own `slot`. Nothing for a
    // tick length of 0.
    void Start(Player* player, Unit* enemy, std::uint32_t spellId, double totalPct, double seconds, double tickSeconds,
               std::uint32_t slot = 0);
} // namespace DC::Combat::PeriodicStrike

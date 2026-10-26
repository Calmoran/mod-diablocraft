#pragma once
// Damage over time of the Crusader's runes ("catch on fire for {damage_pct} weapon damage over {dot_duration_seconds}
// seconds"): the rule that needs no core type, header-only so the harness of the skills that use it compiles this exact
// code. The production half is dc_crusader_dot.cpp.
#include <cmath>
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::Crusader::Dot
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

    // The production half (dc_crusader_dot.cpp). The burn of `spellId` on `enemy`: `totalPct` of weapon damage spread
    // over `seconds` in ticks of `tickSeconds`, one running per Crusader and enemy and spell (a new one starts it
    // over). Nothing for a tick length of 0.
    void Burn(Player* player, Unit* enemy, std::uint32_t spellId, double totalPct, double seconds, double tickSeconds);
} // namespace DC::Combat::Crusader::Dot

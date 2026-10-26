#pragma once
// Lashing Tail Kick's rules that need no core type, header-only so
// tests/monk_lashing_tail_kick compiles this exact code: the arc in radians, the column of Spinning Flame Kick, the
// ticks of Vulture Claw Kick's burn, the slow amount.
#include <cmath>

namespace DC::Combat::Monk::Kick
{
    // The front arc, in the radians the core's HasInArc takes, from degrees (Power/Monk_LashingTailKick.pow SF_7 180).
    inline double ArcRadians(double degrees)
    {
        return degrees * 3.14159265358979323846 / 180.0;
    }

    // Spinning Flame Kick: "a column of fire that burns through enemies": the strip of `width` yards that runs `length`
    // yards ahead of (fromX, fromY) along `facing` (a WoW orientation: the direction is (cos, sin)). A point behind the
    // Monk, past the end, or off to the side by more than half the width is outside; no width, no column.
    inline bool InColumn(double fromX, double fromY, double facing, double length, double width, double x, double y)
    {
        if (length <= 0 || width <= 0)
            return false;
        double const dx = x - fromX, dy = y - fromY;
        double const along = dx * std::cos(facing) + dy * std::sin(facing);
        double const across = -dx * std::sin(facing) + dy * std::cos(facing);
        return along >= 0 && along <= length && std::fabs(across) <= width / 2;
    }

    // Vulture Claw Kick: "an additional {damage_pct:dot} weapon damage as Fire over {dot_duration_seconds} seconds":
    // the ticks that fit the duration at `tickSeconds`, and each one's share of the total. No tick length, no ticks.
    inline unsigned DotTicks(double seconds, double tickSeconds)
    {
        return seconds > 0 && tickSeconds > 0 ? static_cast<unsigned>(std::floor(seconds / tickSeconds + 1e-9)) : 0u;
    }

    inline double TickPct(double totalPct, unsigned ticks)
    {
        return ticks ? totalPct / ticks : 0.0;
    }

    // The knockback: every enemy the kick struck and that still lives is thrown (a dead one has nothing to throw).
    inline bool Knocks(bool struck, bool alive)
    {
        return struck && alive;
    }

    // The core's aura amount for a slow of `pct` percent (negative: it slows).
    inline int SlowAmount(double pct)
    {
        return -static_cast<int>(std::lround(pct));
    }
} // namespace DC::Combat::Monk::Kick

#pragma once
// Wave of Light's rules that need no core type, header-only so
// tests/monk_wave_of_light compiles this exact code. Power/Monk_WaveOfLight.pow: the bell falls SF_8 yards ahead of the
// Monk, Shattering Light's wave runs along a line from SF_0 to SF_1 yards, Pillar of the Ancients' damage over time
// ticks every SF_5 seconds.
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk::WaveOfLight
{
    struct Point
    {
        double x = 0, y = 0;
    };

    // The direction (radians, WoW's orientation) from the Monk to the ground point the cast aimed at; the Monk's own
    // facing when the point is on top of the Monk.
    inline double Heading(Point monk, Point aimed, double facing)
    {
        double const dx = aimed.x - monk.x, dy = aimed.y - monk.y;
        return std::hypot(dx, dy) < 1e-6 ? facing : std::atan2(dy, dx);
    }

    // The point `yards` ahead of the Monk along `heading` (the bell, the pillar).
    inline Point Ahead(Point monk, double heading, double yards)
    {
        return {monk.x + std::cos(heading) * yards, monk.y + std::sin(heading) * yards};
    }

    inline bool InCircle(Point centre, double radiusYards, Point at)
    {
        return std::hypot(at.x - centre.x, at.y - centre.y) <= radiusYards;
    }

    // Shattering Light's line: from `startYards` to `endYards` ahead of the Monk along `heading`, `widthYards` wide.
    inline bool InLine(Point monk, double heading, double startYards, double endYards, double widthYards, Point at)
    {
        double const dx = at.x - monk.x, dy = at.y - monk.y;
        double const along = dx * std::cos(heading) + dy * std::sin(heading);
        double const across = -dx * std::sin(heading) + dy * std::cos(heading);
        return along >= startYards && along <= endYards && std::fabs(across) <= widthYards / 2;
    }

    // Pillar of the Ancients: "{damage_pct:dot} weapon damage over {dot_duration_seconds} seconds": whole ticks of
    // `tickSeconds`, each paying an equal share of the total.
    inline unsigned Ticks(double durationSeconds, double tickSeconds)
    {
        return durationSeconds > 0 && tickSeconds > 0 ? unsigned(std::floor(durationSeconds / tickSeconds + 1e-9)) : 0;
    }

    // The bell's ticks (SF_10, SF_11): `ticks` of them across 1 / attacks per second, the first at once, so the gap is that
    // second divided by the ticks. 0 for an open input.
    inline std::uint64_t TickGapMs(double attacksPerSecond, unsigned ticks)
    {
        return attacksPerSecond > 0 && ticks ? std::uint64_t(1000.0 / attacksPerSecond / ticks + 0.5) : 0;
    }

    inline double TickPct(double totalPct, unsigned ticks)
    {
        return ticks ? totalPct / ticks : 0.0;
    }
} // namespace DC::Combat::Monk::WaveOfLight

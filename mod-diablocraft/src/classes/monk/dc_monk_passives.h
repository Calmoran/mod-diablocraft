#pragma once
// Six of the Monk's passives: Resolve, Fleet Footed, Exalted Soul, Transcendence, Chant of
// Resonance, Seize the Initiative. The rules that need no core type, header-only so tests/monk_passives compiles this
// exact code; the game glue is dc_monk_passives.cpp.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::Monk::Passive
{
    // Transcendence: "Every point of Spirit spent heals you for {heal_per_hit_life} Life." Spirit has no decay or
    // regeneration of its own (monk-class.md), so between two looks a fall of the pool is Spirit spent, whatever spent
    // it (a cast, a channel tick, a mantra). A fall to a lowered maximum (Exalted Soul taken off) is no spend: only
    // what left from under the new maximum counts.
    struct SpendMeter
    {
        double last = 0; // the pool at the last look; 0 before the first, so the first look counts nothing

        // Points spent since the last look.
        double Look(double current, double maximum)
        {
            double const spent = std::max(0.0, std::min(last, maximum) - current);
            last = current;
            return spent;
        }
    };

    // The Spirit a second (Exalted Soul, Chant of Resonance), paid once a whole second has passed (the module tick,
    // monk-class.md). `clockMs` carries the rest.
    inline unsigned WholeSeconds(std::uint64_t& clockMs, std::uint64_t diffMs)
    {
        clockMs += diffMs;
        unsigned const whole = unsigned(clockMs / 1000);
        clockMs %= 1000;
        return whole;
    }

    // Seize the Initiative: "Dealing damage to enemies above {life_threshold_pct} Life".
    inline bool Above(double lifePct, double thresholdPct)
    {
        return lifePct > thresholdPct;
    }

    // What the passives keep on the stat sheet, one bit each; the tick adds what is wanted and not there and removes
    // what is there and not wanted.
    enum Bit : unsigned
    {
        FleetFooted = 1,
        ExaltedSoul = 2,
        Seize = 4,
    };
    struct Change
    {
        unsigned add = 0, remove = 0;
    };
    inline Change Reconcile(unsigned applied, unsigned wanted)
    {
        return {wanted & ~applied, applied & ~wanted};
    }

    // Chant of Resonance: "The Spirit costs of Mantra activation effects are reduced by {cost_reduction_pct}": the
    // share of what the activation paid that comes back.
    inline double PaidBack(double paidPoints, double reductionPct)
    {
        return std::max(0.0, paidPoints) * std::clamp(reductionPct, 0.0, 100.0) / 100.0;
    }
} // namespace DC::Combat::Monk::Passive

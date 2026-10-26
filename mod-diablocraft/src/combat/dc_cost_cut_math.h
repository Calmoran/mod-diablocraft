#pragma once
// The rules of a timed cut to a skill's cost that need no core type, header-only so tests/cost_cut compiles this exact
// code: a cut is a percent off what the skill costs, from one source, until a moment; cuts of different sources
// multiply, as the module's other reductions do. The production half is dc_cost_cut.cpp. No class or skill is named
// here.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::CostCut
{
    struct Held
    {
        double pct = 0;
        std::uint64_t until = 0; // ms: the cut is over from this moment on
    };

    // A cut of `pct` percent (up to the whole cost) that lasts `seconds` from `now`. No percent or no seconds, no cut.
    inline Held Given(double pct, std::uint64_t now, double seconds)
    {
        if (pct <= 0 || seconds <= 0)
            return {};
        return {std::min(pct, 100.0), now + static_cast<std::uint64_t>(seconds * 1000.0)};
    }

    // A cut that has no end while its source stands (a passive that is slotted): up to the whole cost, until the source takes it away. No percent, no cut.
    inline Held Standing(double pct)
    {
        if (pct <= 0)
            return {};
        return {std::min(pct, 100.0), UINT64_MAX};
    }

    inline bool Live(Held const& held, std::uint64_t now)
    {
        return held.pct > 0 && now < held.until;
    }

    // Two cuts together: each keeps its share of what the other leaves, so 50% and 50% leave a quarter of the cost (75%
    // off).
    inline double Combine(double aPct, double bPct)
    {
        double const a = std::clamp(aPct, 0.0, 100.0), b = std::clamp(bPct, 0.0, 100.0);
        return 100.0 * (1.0 - (1.0 - a / 100.0) * (1.0 - b / 100.0));
    }
} // namespace DC::Combat::CostCut

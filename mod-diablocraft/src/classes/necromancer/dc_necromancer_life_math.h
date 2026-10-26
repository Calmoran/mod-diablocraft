#pragma once
// The rule of the Necromancer's Life costs that needs no core type, header-only so the harnesses of the skills that spend Life
// compile this exact code. The production half is SpendLife in dc_necromancer_effects.cpp.
#include <algorithm>

namespace DC::Combat::Necromancer
{
    // "at the cost of {pct}% Health": the Life a cast takes, a share of the maximum, never so much that less than 1 is
    // left, never negative.
    inline double LifeCost(double health, double maxLife, double pct)
    {
        double const cost = maxLife > 0 && pct > 0 ? maxLife * pct / 100.0 : 0.0;
        return std::clamp(cost, 0.0, std::max(0.0, health - 1.0));
    }
} // namespace DC::Combat::Necromancer

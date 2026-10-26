/*
 * World of DiabloCraft - monster pace as auras. The pure half: dc_rift_elites.cpp
 * AddPace puts the result on a stock aura, tests/family_ai/harness.cpp compiles this on its own.
 */

#ifndef DC_RIFT_PACE_H
#define DC_RIFT_PACE_H

#include <algorithm>
#include <cmath>

namespace DC::Rifts
{
    // The percent an aura must carry so that a pace already carrying `currentPct` ends up multiplied by `ratio`. The
    // core holds an aura amount as a whole percent, so a stack of ratios is rounded to the percent at each step.
    inline int ComposePercent(int currentPct, double ratio)
    {
        return static_cast<int>(std::lround(((1.0 + currentPct / 100.0) * ratio - 1.0) * 100.0));
    }

    // Which stock speed aura a speed ratio rides. Unit::UpdateSpeed reads the increase-speed aura through
    // GetMaxPositiveAuraModifier (a negative amount counts as nothing, Unit.cpp:10900) and the slow through
    // GetMaxNegativeAuraModifier (Unit.cpp:11037), and multiplies the two. So a ratio below one (Juggernaut) has to ride a
    // decrease-speed aura, and a ratio above one the increase-speed aura; each aura composes only its own side, so Fast's
    // gain and Juggernaut's loss both survive on one monster.
    enum class SpeedAura
    {
        Increase,
        Decrease
    };
    inline SpeedAura SpeedAuraFor(double ratio)
    {
        return ratio < 1.0 ? SpeedAura::Decrease : SpeedAura::Increase;
    }

    // What UpdateSpeed makes of the two amounts: the speed factor over the creature's base (the test's model of the core).
    inline double SpeedFactor(int increasePct, int decreasePct)
    {
        return (1.0 + std::max(0, increasePct) / 100.0) * (1.0 + std::min(0, decreasePct) / 100.0);
    }
} // namespace DC::Rifts

#endif // DC_RIFT_PACE_H

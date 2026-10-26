#pragma once
// The part of a class resource change below one slot unit, carried to the next change of the same kind, so changes
// add up to D3's fractional sum at one unit a point. No core include: dc_resources.h keeps the carry per player and
// resource, and tests/cost_math compiles this beside the core's own Player::ApplySpellMod.
#include <algorithm>
#include <cmath>

namespace DC::Resources::Carry
{
    // `units` (not negative) added to what is owed: the whole units the sum reaches, the rest kept in `owed`. A
    // tolerance far under a unit keeps a float sum like 0.6 + 0.4 from falling a unit short.
    inline double Whole(double& owed, double units)
    {
        double const total = units + owed;
        double const whole = std::floor(total + 1e-9);
        owed = std::max(0.0, total - whole);
        return whole;
    }

    // What the core dropped off a cast's cost: SpellInfo::CalcPowerCost holds the cost as an integer, so the reduced
    // cost Player::ApplySpellMod gives (25 Fury at 30% off, 17.5) is charged truncated (17). `exact` is the same
    // cost worked in float, read to 1/10000 of a unit: the float's own noise (0.7f is 0.69999999) sits far under
    // that, and the whole-percent modifiers cannot make a finer part.
    inline double Dropped(double exact, double charged)
    {
        double const read = std::round(exact * 10000.0) / 10000.0;
        return read > charged ? read - charged : 0.0;
    }
} // namespace DC::Resources::Carry

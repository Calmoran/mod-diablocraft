/*
 * Issue #54: the sheet's Movement Speed, and an affix slow, as aura amounts.
 *
 * Two lines of arithmetic, in a header of their own for the same reason
 * dc_paragon_math.h exists: they are the whole of what the wiring decides, and
 * scripts/tests/stats/ compiles them on their own with no core behind them. The
 * publisher (dc_stats.cpp) and the elite affixes (dc_rift_elites.cpp) call
 * these rather than rounding in place, so a test cannot pass against a copy of
 * the rule that the server does not run.
 */

#ifndef DC_MOVEMENT_MATH_H
#define DC_MOVEMENT_MATH_H

#include <cmath>
#include <cstdint>

namespace DC::Stats
{
// The sheet's total Movement Speed as the amount of one
// SPELL_AURA_MOD_INCREASE_SPEED aura. The sheet has already added the capped
// gear and paragon share to the uncapped skill bonuses and applied
// movement_cap_pct to the first (dc_common.cpp), so this rounds and nothing
// else: an aura amount is whole percent, so at most half a percent of movement
// speed is lost, and a sheet with no bonus asks for no aura.
//
// Negative is not a movement bonus and never reaches an increase aura; the
// slows are the other function.
inline std::int32_t MovementAuraAmount(double sheetPercent)
{
    if (!(sheetPercent > 0.0))
        return 0;
    return static_cast<std::int32_t>(std::llround(sheetPercent));
}

// An affix's tuned run rate as the amount of one SPELL_AURA_MOD_DECREASE_SPEED
// aura. The rate is a multiplier of normal speed - 0.4 is "40% of normal" - and
// an aura amount is the percentage change, so it is (rate - 1) x 100, whole
// percent, at most half a percent out. A rate of 1 or more is not a slow and
// asks for no aura.
inline std::int32_t SlowAuraAmount(double rate)
{
    auto const amount = static_cast<std::int32_t>(std::lround((rate - 1.0) * 100.0));
    return amount < 0 ? amount : 0;
}
}

#endif // DC_MOVEMENT_MATH_H

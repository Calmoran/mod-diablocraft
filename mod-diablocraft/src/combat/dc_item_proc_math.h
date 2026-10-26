/*
 * World of DiabloCraft - the rules of an item's weapon-damage proc (N-WPROC; Storm Crow's fiery ball).
 *
 * No core dependency, so scripts/tests/legendaries/test_item_power_storm_crow.py compiles this exact header and drives
 * it. The cast itself is dc_item_proc.cpp.
 */

#ifndef DC_ITEM_PROC_MATH_H
#define DC_ITEM_PROC_MATH_H

#include "dc_proc_math.h"

namespace DC::Combat::ItemProc
{
    // The percent of weapon damage a hit's proc deals, 0 for none. The item's chance (a percent, rolled once per item)
    // is scaled by the proc coefficient of the hit that struck, like every chance on hit (Proc::Rolls: a hit that
    // states none never procs); a damage that is not above 0 (a blank tunable reads 0) casts nothing and rolls nothing.
    // `roll` takes a percent and answers whether it fell.
    template<class Roll>
    inline double Pct(double chancePct, double coefficient, double damagePct, Roll roll)
    {
        return damagePct > 0 && Proc::Rolls(coefficient, chancePct, roll) ? damagePct : 0.0;
    }
} // namespace DC::Combat::ItemProc

#endif

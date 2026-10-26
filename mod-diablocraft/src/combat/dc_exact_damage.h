// A hit's amount as the core carries it now: a whole number of 64 bits, not cut to 32. Header-only and free of core types, so
// tests/exact_damage compiles this exact code.
#ifndef DC_COMBAT_EXACT_DAMAGE_H
#define DC_COMBAT_EXACT_DAMAGE_H

#include <cmath>
#include <cstdint>
#include <limits>

namespace DC::Combat
{
    // The hit the formula produced, as the whole number the core deals: the amount dropped to a whole, nothing for an amount that is not above 0 (NaN too)
    // and the largest 64-bit number for one past it (the cast of a double past 2^64 is undefined).
    inline std::uint64_t ExactDamage(double amount)
    {
        if (!(amount > 0))
            return 0;
        if (amount >= 18446744073709551616.0)
            return std::numeric_limits<std::uint64_t>::max();
        return static_cast<std::uint64_t>(amount);
    }

    // The GM's dev multiplier (`.dc dmgmult`) on a player's hit, applied before the hit is made whole, so a hit the formula leaves under a line can pass it.
    // 1 is off; zero, negative, NaN and infinite values change nothing.
    inline double Boosted(double amount, double mult)
    {
        return mult > 0 && std::isfinite(mult) ? amount * mult : amount;
    }
} // namespace DC::Combat

#endif

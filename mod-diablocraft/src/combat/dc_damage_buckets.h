#pragma once
/*
 * The hit's damage buckets (docs/research/damage-buckets.md). D3: bonuses of one category add and
 * the categories multiply; a power that is "its own multiplier" is a category of its own. Step 8 of the hit is that
 * list, and every class feeds it the same way: a module pushes a named Factor, ComputeHit multiplies them in.
 * Pure arithmetic, so the test compiles this header and drives it with the generated numbers.
 */
#include <string>
#include <utility>
#include <vector>

namespace DC::Combat
{
    // One separate multiplier, named so `.dc hit` can show it as its own factor.
    using Factors = std::vector<std::pair<std::string, double>>;

    // A bonus of `pct` percent as a multiplier of its own: 40 -> 1.4.
    inline void AddFactor(Factors& out, char const* name, double pct)
    {
        out.emplace_back(name, 1.0 + pct / 100.0);
    }

    inline double Product(Factors const& factors)
    {
        double product = 1.0;
        for (auto const& factor : factors)
            product *= factor.second;
        return product;
    }

    // Step 4: the additive pool, percent in, multiplier out.
    inline double Additive(double poolPct)
    {
        return 1.0 + poolPct / 100.0;
    }

    // Steps 1-9 multiplied (the order is the formula's): `standalone` is the step 8 product, factors included.
    inline double Total(double weapon, double mainstat, double skill, double additive, double elemental, double elite,
                        double legendary, double standalone, double crit)
    {
        return weapon * mainstat * skill * additive * elemental * elite * legendary * standalone * crit;
    }
} // namespace DC::Combat

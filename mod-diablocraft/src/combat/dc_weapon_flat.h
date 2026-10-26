#ifndef DC_WEAPON_FLAT_H
#define DC_WEAPON_FLAT_H

// Step 1's flat damage: jewelry and offhand "+min-max Damage" reaches the swing as D3 adds it. The sheet holds a
// minimum (WeaponFlatDamage, added to both ends) and a delta (WeaponFlatDamageDelta, the high end only), so the
// range is [min, min + delta] (damage_formula.csv step 1).

#include <utility>

#include "../common/dc_common.h"

namespace DC::Combat
{
inline std::pair<double, double> WithFlatDamage(std::pair<double, double> weapon, StatSheet const& sheet)
{
    double const minimum = sheet[Stat::WeaponFlatDamage];
    return {weapon.first + minimum, weapon.second + minimum + sheet[Stat::WeaponFlatDamageDelta]};
}

// What the flat damage adds to the average hit: the minimum plus half the delta.
inline double FlatDamageAverage(StatSheet const& sheet)
{
    return sheet[Stat::WeaponFlatDamage] + sheet[Stat::WeaponFlatDamageDelta] / 2;
}
}

#endif

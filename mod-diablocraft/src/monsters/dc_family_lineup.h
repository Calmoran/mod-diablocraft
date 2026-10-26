/*
 * World of DiabloCraft - the family monster lineup (monster-families.md section 4 step 2).
 *
 * `.dc lineup <family>` puts a family's monsters in a row in front of the GM, so the picked looks can be
 * compared side by side. The pure part, where each one stands, is here so the test compiles it. Internal
 * to the rifts folder.
 */

#ifndef DC_FAMILY_LINEUP_H
#define DC_FAMILY_LINEUP_H

#include <cmath>

namespace DC::Rifts
{
    // Constants of the GM's test layout, not game numbers: how far in front the row stands, the gap between
    // two monsters, how many fit in one row, and how long they stay (they are summons, nothing is saved).
    constexpr float LINEUP_DISTANCE_YARDS = 8.0f;
    constexpr float LINEUP_GAP_YARDS = 4.0f;
    constexpr unsigned LINEUP_MAX = 12;
    constexpr unsigned LINEUP_SECONDS = 600;

    struct LineupSpot
    {
        float x = 0, y = 0, facing = 0;
    };

    // Monster `index` of `count`, in a row across the GM's facing `o` at (x, y): centred on the GM's line of
    // sight, left to right, every one turned to face the GM.
    inline LineupSpot LineupAt(unsigned index, unsigned count, float x, float y, float o)
    {
        float const across = (static_cast<float>(index) - (static_cast<float>(count) - 1.0f) / 2.0f) * LINEUP_GAP_YARDS;
        float const side = o + 1.57079632679f;
        return {x + std::cos(o) * LINEUP_DISTANCE_YARDS + std::cos(side) * across,
                y + std::sin(o) * LINEUP_DISTANCE_YARDS + std::sin(side) * across, o + 3.14159265359f};
    }

    void RegisterFamilyLineupScripts();
} // namespace DC::Rifts

#endif // DC_FAMILY_LINEUP_H

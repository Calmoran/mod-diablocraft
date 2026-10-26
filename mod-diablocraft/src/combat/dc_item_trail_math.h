/*
 * World of DiabloCraft - the rules of an item's burning trail (N-AREA; Fire Walkers).
 *
 * No core dependency, so scripts/tests/legendaries/test_item_power_fire_walkers.py compiles this exact header and drives
 * it. The patches' bookkeeping and the damage are dc_item_trail.cpp.
 */

#ifndef DC_ITEM_TRAIL_MATH_H
#define DC_ITEM_TRAIL_MATH_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

namespace DC::Combat::ItemTrail
{
    // One patch of fire: where it was dropped and the clock time (milliseconds, wrapping) it goes out.
    struct Patch
    {
        std::uint32_t map = 0;
        float x = 0, y = 0, z = 0;
        std::uint32_t until = 0;
    };

    // Whether the patch is still burning at `now`: the clock wraps, so the gap is read as a signed difference.
    inline bool Alive(Patch const& patch, std::uint32_t now)
    {
        return static_cast<std::int32_t>(patch.until - now) > 0;
    }

    // Takes the patches that went out off the list, then, when the wearer is moving and a patch lasts any time, drops a
    // new one where they stand. True when it dropped one.
    inline bool Drop(std::vector<Patch>& patches, std::uint32_t now, std::uint32_t patchMs, bool moving, std::uint32_t map,
                     float x, float y, float z)
    {
        patches.erase(std::remove_if(patches.begin(), patches.end(), [now](Patch const& patch) { return !Alive(patch, now); }),
                      patches.end());
        if (!moving || patchMs == 0)
            return false;
        patches.push_back({map, x, y, z, now + patchMs});
        return true;
    }

    inline double Distance(Patch const& patch, float x, float y, float z)
    {
        double const dx = patch.x - x, dy = patch.y - y, dz = patch.z - z;
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    }

    // Whether a unit at (x, y, z) of `map` stands within `radius` of a patch that is still burning.
    inline bool Burns(std::vector<Patch> const& patches, std::uint32_t now, std::uint32_t map, float x, float y, float z, double radius)
    {
        return radius > 0 && std::any_of(patches.begin(), patches.end(), [&](Patch const& patch)
                                         { return patch.map == map && Alive(patch, now) && Distance(patch, x, y, z) <= radius; });
    }

    // How far from the wearer's feet an enemy can stand and still burn: the farthest live patch of `map` plus the radius.
    // One search of this reach, filtered by Burns, stands for a search around every patch. 0 when nothing burns.
    inline double Reach(std::vector<Patch> const& patches, std::uint32_t now, std::uint32_t map, float x, float y, float z, double radius)
    {
        if (radius <= 0)
            return 0.0;
        double farthest = -1.0;
        for (Patch const& patch : patches)
            if (patch.map == map && Alive(patch, now))
                farthest = std::max(farthest, Distance(patch, x, y, z));
        return farthest < 0 ? 0.0 : farthest + radius;
    }

    // The seconds one pulse of the fire stands for: the time since the last pulse, so the item's per-second number holds
    // however the clock lands between updates. The first pulse (`last` 0) and a gap past twice the clock's period (the item
    // was taken off, a hitch) count one period: a pulse never pays for a stretch the fire did not run.
    inline double PulseSeconds(std::uint32_t last, std::uint32_t now, double periodSeconds)
    {
        if (periodSeconds <= 0)
            return 0.0;
        double const gap = last ? static_cast<std::int32_t>(now - last) / 1000.0 : 0.0;
        return gap > 0 && gap <= 2 * periodSeconds ? gap : periodSeconds;
    }

    // The percent of weapon damage one pulse deals to an enemy in the fire: the item's percent per second for the
    // seconds the pulse stands for. The enemy takes it once, however many patches cover it.
    inline double PulsePct(double perSecondPct, double seconds)
    {
        return perSecondPct > 0 && seconds > 0 ? perSecondPct * seconds : 0.0;
    }
} // namespace DC::Combat::ItemTrail

#endif

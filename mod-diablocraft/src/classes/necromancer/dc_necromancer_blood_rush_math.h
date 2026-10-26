#pragma once
// The rules of Blood Rush's runes that need no core type, header-only so tests/necromancer_blood_rush compiles this exact code: which
// rune is which, what the cast costs in Life, and which enemies the Necromancer passes through. The production half is
// dc_necromancer_blood_rush.cpp.
#include <algorithm>
#include <cmath>
#include <string_view>

namespace DC::Combat::Necromancer::BloodRush
{
    enum class Rune
    {
        None,
        Transfusion,
        Hemostasis,
        Metabolism,
        Potency,
        Molting
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Transfusion")
            return Rune::Transfusion;
        if (name == "Hemostasis")
            return Rune::Hemostasis;
        if (name == "Metabolism")
            return Rune::Metabolism;
        if (name == "Potency")
            return Rune::Potency;
        if (name == "Molting")
            return Rune::Molting;
        return Rune::None;
    }

    // The Life the cast takes, a percent of the maximum: Hemostasis "removes the health cost", Metabolism "doubles" it.
    inline double LifeCostPct(Rune rune, double basePct, double metabolismPct)
    {
        if (rune == Rune::Hemostasis)
            return 0.0;
        return std::max(0.0, rune == Rune::Metabolism ? metabolismPct : basePct);
    }

    // Whether an enemy at (ex, ey) is passed through by a rush from (sx, sy) to (dx, dy): within `radius` of the segment between them.
    inline bool PassedThrough(double sx, double sy, double dx, double dy, double ex, double ey, double radius)
    {
        double const vx = dx - sx, vy = dy - sy, wx = ex - sx, wy = ey - sy;
        double const lengthSquared = vx * vx + vy * vy;
        double const along = lengthSquared > 0 ? std::clamp((wx * vx + wy * vy) / lengthSquared, 0.0, 1.0) : 0.0;
        double const px = sx + vx * along - ex, py = sy + vy * along - ey;
        return std::sqrt(px * px + py * py) <= radius;
    }

    // Transfusion: "heals for {heal_pct} of your maximum health for every enemy passed through": the Life of the rush.
    inline double TransfusionHeal(double maxLife, double healPct, unsigned passed)
    {
        return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 * passed : 0.0;
    }
} // namespace DC::Combat::Necromancer::BloodRush

#pragma once
// The rules of Corpse Explosion's runes that need no core type, header-only so tests/necromancer_corpse_explosion
// compiles this exact code: which rune is which, where the corpses are taken from, the cone Shrapnel blows in, the
// enemy a corpse pulls itself toward and what Final Embrace costs. The production half is
// dc_necromancer_corpse_explosion.cpp; the corpses themselves are the shared combat/dc_corpses_math.h.
#include <cmath>
#include <cstddef>
#include <limits>
#include <string_view>
#include <vector>

namespace DC::Combat::Necromancer::CorpseExplosion
{
    enum class Rune
    {
        None,
        Shrapnel,
        FinalEmbrace,
        CloseQuarters,
        BloodyMess,
        DeadCold
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Shrapnel")
            return Rune::Shrapnel;
        if (name == "Final Embrace")
            return Rune::FinalEmbrace;
        if (name == "Close Quarters")
            return Rune::CloseQuarters;
        if (name == "Bloody Mess")
            return Rune::BloodyMess;
        if (name == "Dead Cold")
            return Rune::DeadCold;
        return Rune::None;
    }

    // "explodes up to 5 corpses close to you": Close Quarters takes its corpses around the Necromancer, every other
    // rune around the point aimed at.
    inline bool TakesNearTheNecromancer(Rune rune)
    {
        return rune == Rune::CloseQuarters;
    }

    // "Corpses now explode away from you, hitting all targets in a cone": whether the enemy at (ex, ey) is in the cone
    // that opens from the corpse at (cx, cy) along the unit direction (dx, dy), `degrees` wide in all. No angle stated,
    // no cone: the whole circle.
    inline bool InCone(double cx, double cy, double dx, double dy, double ex, double ey, double degrees)
    {
        if (degrees <= 0 || degrees >= 360)
            return true;
        double const rx = ex - cx, ry = ey - cy;
        double const length = std::hypot(rx, ry);
        if (length < 1e-9)
            return true;
        double const cosine = (rx * dx + ry * dy) / length;
        return cosine >= std::cos(degrees / 2.0 * 3.14159265358979323846 / 180.0) - 1e-12;
    }

    // "Corpses pull themselves towards the nearest enemy before exploding": of the enemies' distances from the corpse,
    // the index of the nearest inside `radius`, or npos when none is.
    inline std::size_t NearestWithin(std::vector<double> const& distances, double radius)
    {
        std::size_t best = std::numeric_limits<std::size_t>::max();
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] <= radius &&
                (best == std::numeric_limits<std::size_t>::max() || distances[i] < distances[best]))
                best = i;
        return best;
    }

    // "costs 2% life per corpse": the share of maximum Life a cast that exploded `corpses` corpses costs.
    inline double LifeCostPct(double perCorpsePct, std::size_t corpses)
    {
        return perCorpsePct > 0 ? perCorpsePct * double(corpses) : 0.0;
    }
} // namespace DC::Combat::Necromancer::CorpseExplosion

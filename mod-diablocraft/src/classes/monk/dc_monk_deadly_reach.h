#pragma once
// Deadly Reach's rules that need no core type, header-only so tests/monk_deadly_reach
// compiles this exact code: the longer line of the third hit, Scattered Blows' random fists, and Strike from Beyond's
// pending discount.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace DC::Combat::Monk
{
    // A point inside the capsule `width` yards wide that runs from `from` to `to` yards ahead of (ox, oy) along
    // `direction` (radians, the core's absolute angle). The third hit reaches past the 12 yards the cast's line already
    // struck, so its extra enemies are the ones between `from` = 12 and `to` = 25.
    inline bool InCapsule(double ox, double oy, double direction, double from, double to, double width, double x,
                          double y)
    {
        double const dx = x - ox, dy = y - oy;
        double const along = dx * std::cos(direction) + dy * std::sin(direction);
        double const across = std::fabs(-dx * std::sin(direction) + dy * std::cos(direction));
        return along >= from && along <= to && across <= width / 2.0;
    }

    // Piercing Trident: "the second and third hits gain increased area of effect" (+50%, a tunable). The line of those
    // two hits is `areaPct` percent wider, so its area grows by exactly that; the first hit, every other rune and a
    // blank or negative percent keep the width.
    inline double WidenedWidth(double width, double areaPct, unsigned stage, bool trident)
    {
        return trident && stage >= 2 && areaPct > 0 ? width * (1.0 + areaPct / 100.0) : width;
    }

    // Scattered Blows: `fists` fists, each on an enemy picked at random (the same enemy may be picked twice); `pick(n)`
    // returns an index below n. Nothing when there is no enemy.
    template<class Pick>
    std::vector<std::size_t> ScatterFists(std::size_t enemies, unsigned fists, Pick pick)
    {
        std::vector<std::size_t> out;
        if (!enemies)
            return out;
        for (unsigned i = 0; i < fists; ++i)
            out.push_back(std::min(enemies - 1, static_cast<std::size_t>(pick(enemies))));
        return out;
    }

    // Strike from Beyond: each enemy the third hit strikes takes `pctPerEnemy` off the Spirit cost of the next spender.
    // The core charges a cost when the cast starts, so the discount is paid back as Spirit when that spender resolves:
    // the same Spirit in the end. Capped at the whole cost.
    struct NextSpender
    {
        double pct = 0;

        void Add(double more)
        {
            pct = std::min(100.0, pct + std::max(0.0, more));
        }

        // The discount a spender cast now takes; it is spent.
        double Take()
        {
            double const taken = pct;
            pct = 0;
            return taken;
        }
    };

    // The Spirit given back for a spender that cost `costPoints`.
    inline double Refund(double costPoints, double pct)
    {
        return costPoints > 0 && pct > 0 ? costPoints * std::min(100.0, pct) / 100.0 : 0.0;
    }
} // namespace DC::Combat::Monk

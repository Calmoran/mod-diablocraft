#pragma once
// The Shaman's Maelstrom generation: what a Primary pays and how a gain splits between the bar and Overcharge. The pool, its
// maximum, the decay and Paragon's points are the registry's (the class resource sheets through dc_resources.h, the stats
// hook, the resource pulse and dc_paragon.cpp); what no data row can say is the split of a gain at the maximum, and that is
// here. Header-only so the harness in tests/shaman_maelstrom compiles the production body.
#include <algorithm>

namespace DC::Combat::Shaman::Maelstrom
{
    struct Gain
    {
        double paid = 0;     // points the bar takes
        double overflow = 0; // points that did not fit, banked as Overcharge
    };

    // A gain of `points` on a bar holding `current` of `maximum`.
    inline Gain Split(double current, double maximum, double points)
    {
        if (points <= 0)
            return {};
        double const room = std::max(0.0, maximum - current);
        double const paid = std::min(points, room);
        return {paid, points - paid};
    }

    // The Maelstrom a cast of a skill whose sheet row generates `sheet` pays: the sheet's number (a rune that states its own
    // replaces it), plus the flat points a Primary gets from gear, times the generation percent from gear. A skill that
    // generates nothing gets nothing added.
    inline double Generated(double sheet, bool primary, double primaryFlat, double percent)
    {
        if (sheet <= 0)
            return 0;
        double const flat = primary ? std::max(0.0, primaryFlat) : 0.0;
        return (sheet + flat) * (1.0 + percent / 100.0);
    }
} // namespace DC::Combat::Shaman::Maelstrom

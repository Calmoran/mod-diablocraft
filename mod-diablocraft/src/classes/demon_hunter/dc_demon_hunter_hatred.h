#pragma once
// The Demon Hunter's Hatred. The two pools, their maxima, regeneration and Paragon's +0.5 a point are the registry's
// (the class resource sheets through dc_resources.h, the stats hook, the resource pulse and dc_paragon.cpp), so the
// class needs no code for them. What no data row can say is who pays a primary's generation, and that is the one
// function here. Header-only so the harness in tests/demon_hunter_hatred compiles the production body over a shim
// Player.
#include "../dc_resources.h"

namespace DC::Combat::DemonHunter
{
    // A Demon Hunter's attack connected and its sheet says it generates `points` of Hatred ("Generate: N Hatred").
    // Paid through the core's own energize, as every module-paid class power is: it adds, clamps at the maximum and
    // sends the energize log. Another class never reaches it: the class must be the Hatred row's own.
    inline bool Generate(Player* player, std::uint32_t classId, std::uint32_t spellId, double points)
    {
        if (!player || points <= 0 || classId != Resources::Hatred.classId ||
            !Resources::Displayed(player, Resources::Hatred))
            return false;
        Resources::Energize(player, Resources::Hatred, spellId, points);
        return true;
    }
} // namespace DC::Combat::DemonHunter

#pragma once
// The Monk's Spirit. The pool, its 250 maximum, the
// absence of regeneration and decay and Paragon's +1 per point are the registry's
// (class_resources.csv through dc_resources.h, the stats hook and dc_paragon.cpp),
// so a Monk needs no code for them. What no data row can say is who pays a primary's
// generation, and that is the one function here. Header-only so the harness in
// tests/monk_spirit compiles the production body over a shim Player.
#include "../dc_resources.h"

namespace DC::Combat::Monk
{
    // A Monk's attack connected and its sheet says it generates `points` of Spirit
    // ("Generate: N Spirit per attack"). Paid through the core's own energize, as
    // the Wizard's Arcane Power is: it adds, clamps at the maximum and sends the
    // energize log. A Barbarian, whose primaries are paid in dc_primaries.cpp on
    // Rage, never reaches it: the class must be the Spirit row's own.
    // `generated` false is anything but a skill's generation (a cost given back), which the scale on what is generated (Resources::Generated) does not touch.
    inline bool Generate(Player* player, std::uint32_t classId, std::uint32_t spellId, double points, bool generated = true)
    {
        if (!player || points <= 0 || classId != Resources::Spirit.classId ||
            !Resources::Displayed(player, Resources::Spirit))
            return false;
        Resources::Energize(player, Resources::Spirit, spellId, points, generated);
        return true;
    }
} // namespace DC::Combat::Monk

#pragma once
// The Witch Doctor's Mana. Its pool, regeneration, login fill and Paragon's +4 a point are the registry's (the class
// resource sheets through dc_resources.h, the stats hook, the resource pulse and dc_paragon.cpp), and a spender's cost is
// its record's PowerType and ManaCost, so the class needs no code for them. What no data row can say is who is paid the
// Mana a hit returns, and that is the one function here. Header-only so the harness in tests/witch_doctor_mana compiles
// the production body over a shim Player.
#include "../dc_resources.h"

namespace DC::Combat::WitchDoctor
{
    // `hits` enemies were hit and the skill's sheet says each hit returns `perHit` Mana ("Gain N Mana every time ... hits").
    // Paid through the core's own energize, as every module-paid class power is: it adds, clamps at the maximum and sends
    // the energize log. Another class never reaches it: the class must be the Mana row's own, and Mana must be the
    // power it shows.
    inline bool Gain(Player* player, std::uint32_t classId, std::uint32_t spellId, double perHit, unsigned hits)
    {
        if (!player || perHit <= 0 || hits == 0 || classId != Resources::Mana.classId ||
            !Resources::Displayed(player, Resources::Mana))
            return false;
        Resources::Energize(player, Resources::Mana, spellId, perHit * hits);
        return true;
    }
} // namespace DC::Combat::WitchDoctor

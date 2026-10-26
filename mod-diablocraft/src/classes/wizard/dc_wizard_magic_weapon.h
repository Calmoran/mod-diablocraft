// Magic Weapon: the energy Conduit gives for the enemies a cast hit, Deflection's shield and Ignite's burn on a hit.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::MagicWeapon
{
    // A cast has resolved over `targets`: Conduit's resource and Deflection's shield.
    void Cast(Player* player, std::vector<Unit*> const& targets);
    // A hit with proc coefficient `proc` landed on the unit `guid`: Ignite's chance to burn it.
    void Ignite(Player* player, ObjectGuid guid, double proc);
} // namespace DC::Combat::Wizard::MagicWeapon

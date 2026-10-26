// The Armors: what Energy Armor, Ice Armor and Storm Armor do when the Wizard is hit or hits, and on their own clocks.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::Armors
{
    // The Wizard `player` was hit by `attacker`: Jagged Ice, Crystallize, Ice Reflect, Reactive Armor and Scramble.
    void ArmorsHit(Player* player, Unit* attacker, Attack kind);
    // Force Armor cuts a hit over the threshold to the cap, and what it cuts away is limited to a share of the maximum Life `maxLife`.
    void ForceArmor(Player* victim, double maxLife, std::uint32_t& damage);
    // Shocking Aspect: a critical hit on the unit `guid`, with proc coefficient `proc`, may electrocute it.
    void ShockingAspect(Player* player, ObjectGuid guid, Hit const& hit, double proc);
    // Chilling Aura: renews the chill on the enemies near the Wizard; called on the Wizard's update at time `now`.
    void ChillingAura(Player* player, uint64 now);
    // One tick of Storm Armor's shock on a nearby enemy.
    void StormArmorTick(Player* player, uint32 id);
    // One tick of Frozen Storm, `seconds` being the period.
    void FrozenStormTick(Player* player, uint32 id, double seconds);
} // namespace DC::Combat::Wizard::Armors

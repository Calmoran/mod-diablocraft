// The GM's Life and damage commands for dev checks: `.dc biglife <Life>` (the selected creature's real max Life) and `.dc dmgmult <x>` (the GM's own
// hits multiplied, to reach hits past 2^32). The core holds Life and hits in 64 bits (core patches 0027 and 0028); nothing here converts either.
#ifndef DC_COMBAT_LIFE_COMMANDS_H
#define DC_COMBAT_LIFE_COMMANDS_H

class Unit;

namespace DC::Combat
{
    // The GM's dev multiplier (`.dc dmgmult`) of the player behind `dealer` (a pet's owner); 1 when off.
    double DevMultiplier(Unit const* dealer);
    // A player's final hit multiplied by it, before the hit is made whole (ExactDamage).
    double DevBoost(Unit const* dealer, double amount);
    void RegisterLifeCommands();
} // namespace DC::Combat

#endif

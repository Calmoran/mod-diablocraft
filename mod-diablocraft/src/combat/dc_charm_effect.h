#pragma once
// A monster charmed to fight for a player for a number of seconds, for any class's skill or item that charms. The charm
// is the core's own charm aura, cast from an invisible holder summoned for it, so a player holds as many charms as
// charm and the core's one charm per player is never used. The aura owns the length and the swap of side; the charm
// ends with it, or with its master dying or leaving. What a charmed monster means to the rifts is in rifts/dc_charm.h.
// A class includes this and calls Apply; src/combat/dc_charm_effect.cpp defines it.
#include <cstdint>
#include <vector>

class Creature;
class Player;
class Unit;

namespace DC::Combat::CharmEffect
{
    // `target` charmed by `master` for `seconds`, sent at the nearest enemy near it first (`spellId` is the skill or
    // rune that charms, for the enemies' targeting rules). True when the charm took hold. Nothing, and false, for a
    // target that is not an enemy monster, a boss or a rift Guardian, one already charmed, or one the core's immunities
    // refuse (the Juggernaut elite).
    bool Apply(Player* master, Unit* target, std::uint32_t spellId, double seconds);

    // The player a monster is charmed for: the player the core's own charm names, or the player behind the holder of ours.
    // nullptr for a monster nobody has charmed, or one charmed by anything else.
    Player* MasterOf(Unit const* charmed);

    // Every monster `master` has charmed through a holder that is still charmed, alive and in the world. The core's own
    // single charm (Player::GetCharm) is not in it.
    std::vector<Creature*> CharmedBy(Player* master);
} // namespace DC::Combat::CharmEffect

/*
 * World of DiabloCraft - N-CHARM, the pure rules (docs/contracts/legendary-world-pieces.md).
 *
 * A monster a player has charmed fights for that player until the charm ends, then is an enemy again. The core marks it
 * player-controlled (Unit::IsControlledByPlayer), the same flag a player's pet, guardian or totem carries, so every
 * "not rift trash" test that reads that flag has to tell the two apart. These rules do that with no world in them;
 * dc_rift_ai.cpp builds a Body from a creature. tests/charm/harness.cpp compiles this header on its own.
 * Internal to the rifts folder.
 */

#ifndef DC_CHARM_H
#define DC_CHARM_H

namespace DC::Rifts::Charm
{
    struct Body
    {
        bool pet = false, totem = false, critter = false, guardian = false, trigger = false;
        bool controlledByPlayer = false; // Unit::IsControlledByPlayer: set for a charmed monster too
        bool charmed = false;            // Unit::IsCharmed
    };

    // A monster under a player's charm. A pet, guardian, totem, critter or trigger is never one, however it was bound.
    inline bool IsCharmedMonster(Body const& b)
    {
        return b.charmed && !b.pet && !b.totem && !b.critter && !b.guardian && !b.trigger;
    }

    // Belongs to a player and is not a monster: the creatures every rift sweep leaves alone.
    inline bool PlayerOwned(Body const& b)
    {
        return b.controlledByPlayer && !IsCharmedMonster(b);
    }

    // A Guardian's arrival despawns every hostile monster of a Greater Rift; a charmed one is hostile in all but
    // faction.
    inline bool ClearedByGuardian(bool hostileToReference, Body const& b)
    {
        return hostileToReference || IsCharmedMonster(b);
    }
} // namespace DC::Rifts::Charm

#endif // DC_CHARM_H

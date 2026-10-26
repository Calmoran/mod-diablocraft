/*
 * World of DiabloCraft - the devices a class lays on the ground, the shared piece: placed at a point, armed after a
 * delay, fired when an enemy comes within reach, when the owner detonates them, or every interval while an enemy stands
 * in range; counted and capped by kind, gone when they have fired, when their time is up, or when the owner dies,
 * leaves or changes floor. A class defines what a firing does (the callback of Place) and the numbers a device runs on
 * (Spec); nothing here names a class or a skill. The rules are dc_ground_device_math.h.
 *
 * A device is the engine's own record, not a creature: it is counted as no monster, gives no progress, no experience
 * and no loot, and is never an enemy's target. A skill that wants it seen asks for a display (Setup's display): a
 * friendly, untouchable holder wearing it for the device's life.
 */

#ifndef DC_GROUND_DEVICE_H
#define DC_GROUND_DEVICE_H

#include "dc_ground_device_math.h"
#include "Position.h"

#include <cstdint>
#include <functional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::GroundDevice
{
    // What a firing is told: the device's own place and the enemies within its radius at that moment (in line of sight,
    // the list a spell's area resolves to). A Command device that is detonated with nobody near fires with an empty
    // list.
    using Fire = std::function<void(Player*, Position const& at, std::vector<Unit*> const& enemies)>;

    struct Setup
    {
        std::uint32_t kind = 0;   // the caller's key; devices of one kind are counted, capped and detonated together
        std::uint32_t record = 0; // the spell record the enemies are searched for as (hostility, line of sight)
        Spec spec;
        std::uint32_t display = 0; // a creature display to show at the device's place for its life (0: nothing shown)
        Fire fire;
    };

    // Lays a device of `setup.kind` at `at` for `player`; the oldest of the kind give way to `setup.spec.most`.
    void Place(Player* player, Setup const& setup, Position const& at);
    // Fires every armed Command device of `kind` the player has, in the order they were laid, and takes them away. How
    // many fired.
    unsigned Detonate(Player* player, std::uint32_t kind);
    // How many devices of `kind` the player has standing.
    std::size_t Count(Player const* player, std::uint32_t kind);
    // The places of the devices of `kind` the player has standing, in the order they were laid.
    std::vector<Position> Places(Player const* player, std::uint32_t kind);
    // Takes every device of the player away.
    void Clear(Player* player);

    void RegisterScripts();
} // namespace DC::Combat::GroundDevice

#endif

#pragma once
// The corpses a kill leaves for a player's skills to read and spend, for any class's skill or passive that wants one.
// A corpse is the dead monster's own stock body where it fell, and the owner's claim on it: using the corpse, its
// lifetime running out or the cap pushing it out removes the body too (the last claim on a body takes it), and a body
// that decays or goes some other way takes the claim with it. A corpse a skill makes is given a stock dead body made where it lies (LeaveMade). The
// record is no monster, gives no progress and no loot, and it is gone with the owner's floor (the owner leaves the map
// or logs out; the bodies of that floor are left to the core's decay), after its lifetime, or past the cap. The cap and the lifetime are the combat tunables corpse_cap and corpse_lifetime_seconds; either one unset keeps
// no corpse. What leaves them is a class's own file (it calls Leave); what takes them is a skill (Count, Consume); a
// passive that reads a taken corpse registers with OnConsumed. src/combat/dc_corpses.cpp defines these.
#include "dc_corpses_math.h"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <vector>

class Player;
struct Position;

namespace DC::Combat::Corpses
{
    // `owner` has a corpse at `at` (`entry` is the creature that died there, 0 for a corpse a skill makes; `body` is that
    // creature's guid, raw, for the dead body the corpse is, 0 when there is none). False when none is kept: the owner is
    // not in a world, or the cap or the lifetime is unset; the body is then the core's own to decay.
    bool Leave(Player* owner, Position const& at, std::uint32_t entry, std::uint64_t body = 0);

    // `owner`'s skill makes a corpse at `at`: a stock dead body is made there and the corpse is left with its guid, so the body goes
    // with the corpse as any other. `entry` is what the corpse says stood there, as for Leave (0 for none); it is never the body's
    // creature, because a dead monster's own entry would run its death abilities and scripts again. The body is `skillBody`, a creature
    // with no death behaviour of its own that the skill names (the Golem's template), else the stand-in the combat tunable
    // skill_corpse_body_entry names, which then wears the look of `entry`. No loot, no credit. False when none is kept; the body is then
    // removed again.
    bool LeaveMade(Player* owner, Position const& at, std::uint32_t entry, std::uint32_t skillBody = 0);

    // The raw guid of the dead body being made right now, 0 when none: a death hook that must not count it as a kill asks.
    std::uint64_t BodyBeingMade();

    // How many of the owner's corpses lie within `radius` yards of `center` along the ground: the requirement a corpse
    // skill checks before it casts.
    std::size_t Count(Player* owner, Position const& center, float radius);

    // Up to `max` of the owner's corpses within `radius` yards of `center`, nearest first, taken out of the pile. The
    // listeners of OnConsumed hear what was taken before this returns. A taken corpse's body is removed with it.
    std::vector<Spot> Consume(Player* owner, Position const& center, float radius, std::size_t max);

    // The owner's corpse skills may be used at will until `untilMs` (the game clock, GameTime ms; 0 ends it): while it lasts,
    // Count finds at least `phantoms` corpses and Consume tops what it took up to `phantoms` (and its own maximum) with corpses
    // made at the centre (no creature, no body). The passives of OnConsumed hear only the real ones.
    void AtWill(Player* owner, std::uint64_t untilMs, std::size_t phantoms);

    // Called by Consume with the owner and every corpse a call took, when it took any. Register at startup
    // (RegisterScripts of the class that reads corpses); the list is not locked.
    using Listener = std::function<void(Player* owner, std::vector<Spot> const& taken)>;
    void OnConsumed(Listener listener);

    // The shared scripts: the owner's corpses go with the owner's map and login, and the GM commands.
    void RegisterScripts();
} // namespace DC::Combat::Corpses

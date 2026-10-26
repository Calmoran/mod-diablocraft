/*
 * World of DiabloCraft - pylons and shrines, the buffs (P1; docs/proposals/pylons.md 4.3).
 *
 * One buff record per kind (data/pylon_buffs.csv). Give() puts it on a player, as the player's own aura so the
 * floors hook keeps it (rift floors 4.7); a worn buff's stat numbers are Temporary contributions on the sheet,
 * Power is a factor of its own in step 8 of the hit, Enlightened a factor on the wearer's kill XP, Shield the stock
 * immunity auras of its record (and a name DealMonsterHit, Knockback and Vortex ask).
 *
 * P2 (pylons.md 6.9, 6.10): Conduit's strikes and Speed's knock-up, each the stock periodic dummy
 * aura on the wearer ticking into dc_pylons.cpp's dc_pylon_tick, as Wreath of Lightning's pulse does. Speed's Give
 * also puts on its knock-up aura (83512), and Speed's buff going takes it along.
 *
 * P3 (pylons.md 4.2 and 6.4): the objects. Spawn() stands one on a map; its click gives the buff to
 * whom 6.4 says, once, and the players on the map hear of it (docs/contracts/pylon-messages.md, which P4 and P5 read).
 */
#pragma once

#include "dc_damage_buckets.h"
#include "dc_pylon_math.h"

class GameObject;
class Map;
class Player;
class Unit;
struct Position;

namespace DC::Combat::Pylons
{
    // Put the buff of `kind` on `target`: a running one of the same kind restarts its time, other kinds run together.
    // Channeling also resets the cooldowns that are running. False when the record is missing, the row gives no
    // seconds, or the core refuses the aura (a shrine to a dead player).
    bool Give(Player* target, Kind kind);

    // N-PYLON: put a random shrine buff on `target` (RandomShrine(roll): Blessed, Empowered, Enlightened, Fleeting, Fortune or Frenzied), for the
    // seconds of its own row, as the shrine object's click does. False when Give refuses (a dead player, no record, no seconds).
    bool GiveRandomShrine(Player* target, double roll);

    // The player lives and wears the buff of `kind`.
    bool Wearing(Player const* player, Kind kind);

    // Shield: nothing damages or controls this unit. DealMonsterHit, Knockback and Vortex ask this first.
    bool Shielded(Unit const* unit);

    // Power's separate multiplier on the player's hits (step 8), none while it is not worn.
    void Multipliers(Player const* player, Factors& out);

    // Enlightened's percent more experience from the wearer's own kills, 0 while it is not worn.
    double ExperiencePct(Player const* player);

    // Bring the sheet in line with what the player wears (called from the update tick when a buff came, went, or the
    // player died or revived; the first call after login cleans anything a saved sheet still holds).
    void Reconcile(Player* player);

    // Stand the object of `kind` on `map` at `at` (P4's placement and `.dc pylon spawn`). It stays until it is used or
    // its map closes; every player on the map is told (DCPYLON S). Null when the core refuses (no template).
    GameObject* Spawn(Map* map, Kind kind, Position const& at);

    void RegisterScripts();
} // namespace DC::Combat::Pylons

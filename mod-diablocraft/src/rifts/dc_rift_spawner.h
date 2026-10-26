/*
 * World of DiabloCraft - the rift spawner (monster spawning S2, docs/proposals/monster-spawning.md 3.8, 3.9, 4.8
 * to 4.10, 4.13).
 *
 * When a rift floor opens, on that map's own update, this plans what stands on it (dc_rift_spawn.h: the set, the
 * anchors, the clusters, the solos, the elite packs) and puts it there with Map::SummonCreature; it refuses the
 * dungeon's own monsters before they exist (core patch 0004's hook), opens the floor's doors, and links a cluster so
 * that it fights as one. A patrol (S5) is a cluster whose leader walks a route's stock path.
 *
 * Internal to the rifts folder.
 */

#ifndef DC_RIFT_SPAWNER_H
#define DC_RIFT_SPAWNER_H

#include <cstdint>
#include <string>
#include <vector>

class Creature;
class Map;
class Unit;

namespace DC::Rifts::Spawner
{
    // A live rift floor's map update: the first one plans and places the floor; later ones return at once.
    void OpenFloor(Map* map, unsigned tier);

    // The run's seed, 0 until its first floor has opened (pylons P4 rolls its own stream from it).
    std::uint64_t RunSeed(std::uint64_t runId);

    // A floor's map is gone (its picks are forgotten); `runEnds` when it was the run's last floor.
    void FloorGone(std::uint32_t instanceId, std::uint64_t runId, bool runEnds);

    // A cluster member started fighting: every living member attacks the same target (3.9.3, the formation's own rule).
    void MemberEngaged(Creature* member, Unit* target);

    // `.dc rift picks`: what this map's floor picked and what stands where. False when the map has no picks.
    bool Report(Map const* map, std::vector<std::string>& lines);

    // `.dc patrol record` just recorded a route: the next floor to open may use it (S5).
    void AddRoute(std::string const& dungeon, std::uint32_t path, unsigned anchor, float x, float y, float z);

    // dc_rift_patrol.cpp: `.dc patrol record start|stop` (S5), registered with the spawner's scripts.
    void RegisterPatrol();

    // Reads the spawn sheets and the survey's tables again, so the next floor to open sees an edit (S4's touch-up commands). The message says
    // what loaded or what is missing; on false the sheets in use are the ones from before.
    bool Reload(std::string& message);

    // dc_rift_touchup.cpp: `.dc anchor` and `.dc area` (S4), registered with the spawner's scripts.
    void RegisterTouchUp();

    void RegisterScripts();
} // namespace DC::Rifts::Spawner

#endif // DC_RIFT_SPAWNER_H

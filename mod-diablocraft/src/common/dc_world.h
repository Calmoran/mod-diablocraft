#ifndef DC_WORLD_H
#define DC_WORLD_H
#include <string>
class Player;
class WorldLocation;
namespace DC::World
{
void RegisterScripts();
// 08 §5 character start. Split out so 11-hardcore can hold the kit back until
// the H4 mode prompt is answered and then hand the start back here.
void StartCharacter(Player* player);
// The hub, for anything that needs to put a player in town without knowing
// where town is (11 §3 respawn). False before the hub row is loaded.
bool HubLocation(WorldLocation& location);
bool HubPoint(std::string const& name, WorldLocation& location);
bool IsInHub(Player const* player);
// The Sanctum is one phase for every tier. It is
// the phase the registry gives every source spawn (dc_world_areas.cpp, dc_area_source), so the
// hub keeps its one copy of each object; it must stay inside the launch tiers' 1..N range.
constexpr unsigned SanctumPhase = 1;
}
#endif

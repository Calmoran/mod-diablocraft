#ifndef DC_DIFFICULTY_H
#define DC_DIFFICULTY_H

#include "../common/dc_tiers.h"
class Creature;
class Player;
class Map;
namespace DC::Difficulty
{
void RegisterScripts();
unsigned CurrentTier(Player const* player);
// Server validates the chooser and all online party members before any mutation.
bool SelectTier(Player* player, unsigned tier, std::string& error);
// The player-facing choice (`.dc tierselect`): SelectTier plus the G10 hub
// and cooldown gate. The start kit and the admin `.dc tier` call SelectTier.
bool ChooseTier(Player* player, unsigned tier, std::string& error);
// Queue refresh for the owning map thread, never recompute during a hit.
void RequestRefresh(Map* map);
// The damage multiplier a monster of a Greater Rift level has (the base tier's, times the level's
// bands), for the numbers other systems scale from the monster rather than read off it (elite
// affix damage). 0 when the tier data or the rifts gr_* tunables are not usable.
double GreaterRiftDamage(unsigned level);
// C8 contract for 02's future fixed-hit code: when true, bypass BOTH creature
// armor and school resistance. This is policy only; no combat consumer exists yet.
bool BypassCreatureMitigation(Creature const* creature);
}

#endif // DC_DIFFICULTY_H

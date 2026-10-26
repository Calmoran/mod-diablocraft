/*
 * World of DiabloCraft - rift AI (09-rifts F2, F5).
 *
 * What the rest of the rifts folder needs from the guardian and melee AI.
 * Split out of dc_rifts.cpp; every name here kept its spelling.
 *
 * Internal to the rifts folder. Other modules include dc_rifts.h.
 */

#ifndef DC_RIFT_AI_H
#define DC_RIFT_AI_H

#include <cstdint>
#include <vector>

class Creature;
class Map;
class Player;
class Unit;

namespace DC::Rifts
{
    struct Rift;

    // F5. Spawns the run's guardian on the player who filled the progress bar, and
    // despawns what is standing near it (09 section 2 step 4); in a Greater Rift, all of it.
    void SpawnGuardian(Player* killer, Rift& rift);

    // Greater Rift: despawns every other hostile monster on the map (the Guardian and its summons,
    // players' pets, friendly NPCs and our own scripted creatures stay). False, and nothing done,
    // for a Nephalem Rift. SpawnGuardian calls it, and the map tick again while the Guardian is up so
    // a late-loading grid or a respawn cannot bring monsters back.
    bool ClearGreaterRift(Map* map, Rift const& rift, Unit const* reference);

    // True for one of the loaded stage-1 guardian creature entries.
    bool IsGuardianEntry(std::uint32_t entry);

    // The guardian's death: claims the run, pays the guardian reward, completes
    // every enrolled quest. False when this death was not the run's guardian, or
    // when the reward did not commit.
    bool CompleteGuardianKill(Creature* dead, Unit* killer);

    // 09 F2: every rift creature is given the plain melee AI and has its native
    // casts stripped. Called from the creature script as spawns enter the map.
    void StripNativeAbilities(Creature* creature);

    // True when this creature carries the plain melee AI or the guardian's own,
// i.e. nothing native survived. The `.dc rift abilities` sweep reports on it.
bool HasPlainRiftAI(Creature const* creature);

// C3: how far an elite's single-target affix looks for its player when the affix has no reach of its own: the elite
// targeting profile's candidate radius (a tunable), the same distance the AI itself picks from.
float AffixTargetReach();

// The living monsters `source` may attack. A charmed elite's affixes aim at these (its former allies);
// docs/contracts/legendary-world-pieces.md.
std::vector<Unit*> AffixFoesOf(Unit* source);

void RegisterAIScripts();
} // namespace DC::Rifts

#endif // DC_RIFT_AI_H

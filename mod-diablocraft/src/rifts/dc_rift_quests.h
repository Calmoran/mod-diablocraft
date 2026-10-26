/*
 * World of DiabloCraft - Nephalem Rifts on the quest system.
 *
 * What the rest of the rifts folder needs from the Phase A half. Split out of
 * dc_rifts.cpp; every name kept its spelling and signature.
 *
 * Internal to the rifts folder. Other modules include dc_rifts.h.
 */

#ifndef DC_RIFT_QUESTS_H
#define DC_RIFT_QUESTS_H

#include "dc_rifts_internal.h"

#include <cstdint>
#include <string>
#include <vector>

class GameObject;
class Player;

namespace DC::Rifts
{
// 7.9.7. The obelisk offers ONE variant - the party's run, or a freshly
// reserved one - never all three count variants.
void OfferRiftQuest(Player* player, GameObject* go);

// The run this player is enrolled in, if it is still live. `enrolled` and
// `offline` both count; the login sweep decides which way an offline row goes.
bool EnrolledRun(ObjectGuid player, Rift& result);

// The live run this player's PARTY is in, if any.
bool PartyRun(Player* player, Rift& result);

// Every member still enrolled in the run (dc_rift_member state 'enrolled'), by GUID, online or not.
std::vector<ObjectGuid> EnrolledGuids(std::uint64_t runId);

// Writes or restores the (run, player, quest) association.
void EnrollMember(Rift const& rift, ObjectGuid player);

// Guardian death completes every still-enrolled member's quest (7.4).
void CompleteRunQuests(std::uint64_t runId);

// Closure removes every remaining quest and detaches every row (7.9.7).
void RemoveRunQuests(Rift const& rift);

// Puts the run's quest in one member's log (and enrols them), silently; `notice` is a chat line or null.
void GiveRunQuest(Rift const& rift, Player* member, char const* notice);

// Shares the run's quest with the creator's party, silently, on create.
void ShareRunQuest(Rift const& rift, Player* creator);

// Projects the run's capped progress into every enrolled member's quest.
void ProjectProgress(Rift const& rift);

// Adds `units` progress (and `kills` raw kills) to the open run, capped at the bar, persists and projects it, and
// spawns the Guardian, where `source` stands, when the bar fills. `source` is who earned it: a killer, or a run member
// who took an orb. One bar for the run: a kill on any floor adds to it. Nothing happens once the run has left "open".
void AddProgress(Player* source, std::uint64_t runId, unsigned units, unsigned kills);

void RegisterQuestScripts();
}

#endif // DC_RIFT_QUESTS_H

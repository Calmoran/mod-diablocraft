/*
 * World of DiabloCraft - Nephalem Rifts on the quest system (09-rifts section 7,
 * Phase A under the 7.9.7 rules).
 *
 * Split out of dc_rifts.cpp as a PURE MOVE: the obelisk's quest
 * offer, enrollment and sharing, progress projection, the guardian-gated
 * completion, the Keeper turn-in and its closing reward, and the logout/login
 * sweep. No behaviour changed.
 *
 * Internal to the rifts folder; other modules include dc_rifts.h.
 */

#include "dc_rift_quests.h"

#include "dc_rifts.h"
#include "../monsters/dc_monster_ai.h"
#include "../combat/dc_charm_effect.h"
#include "../monsters/affixes/dc_affixes.h"
#include "dc_rifts_internal.h"
#include "../difficulty/dc_difficulty.h"
#include "../paragon/dc_paragon.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_world.h"

#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "Group.h"
#include "InstanceSaveMgr.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "SpellMgr.h"
#include "ScriptedGossip.h"
#include "World.h"
#include "WorldSession.h"

#include <algorithm>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (-1.0): sentinel for an unset logout-grace tunable; Reads _global rift_logout_grace_seconds from dc_affix_tunables.

namespace DC::Rifts
{
// Used before they are defined, as they were in the single file.
void CompleteRunQuests(std::uint64_t runId);
void RemoveRunQuests(Rift const& rift);
void ShareRunQuest(Rift const& rift, Player* creator);
void SetQuestProgress(Player* member, Rift const& rift);
void GiveRunQuest(Rift const& rift, Player* member, char const* notice);
void StripRunQuest(Player* player, std::uint32_t questId);
void ClearQuestSlots(Player* player, std::uint32_t questId);

BarQuest nephalemQuest;
BarQuest greaterQuest;
std::set<std::uint32_t> riftQuests;
std::unordered_map<ObjectGuid, Reservation> reservations; // guarded by workMutex
void EnrollMember(Rift const& rift, ObjectGuid player)
{
    CharacterDatabase.Execute(
        "INSERT INTO dc_rift_member (run_id,player_guid,quest_id,state,offline_since,departure_reason) "
        "VALUES ({},{},{},'enrolled',NULL,'') "
        "ON DUPLICATE KEY UPDATE state='enrolled', offline_since=NULL, departure_reason='', quest_id={}",
        rift.id, player.GetRawValue(), rift.questId, rift.questId);
    // 7.9.8: and the cache the hub objects' visibility reads, in the same function
    // that writes the row so the two cannot disagree. A member who joins mid-rift
    // sees the portal and the rubble appear and the obelisk go, right here.
    JoinMembership(rift.id, player);
}
// Reads the run a character is currently enrolled in, if it is still live.
// `enrolled` and `offline` both count: an offline member inside the grace has
// not left, and the login sweep is what decides which way that goes.
bool EnrolledRun(ObjectGuid player, Rift& result)
{
    // Newest run that is still open. Without the join and the ORDER BY this
    // took the OLDEST matching row, so one stale association shadowed the live
    // run: the portal refused its own party, turn-in paid nobody, and the
    // quest could never complete.
    QueryResult row = CharacterDatabase.Query(
        "SELECT m.run_id FROM dc_rift_member m JOIN dc_rift r ON r.id=m.run_id "
        "WHERE m.player_guid={} AND m.state IN ('enrolled','offline') AND r.state<>'closed' "
        "ORDER BY m.run_id DESC LIMIT 1", player.GetRawValue());
    if (!row)
        return false;
    std::uint64_t const runId = (*row)[0].Get<uint64>();
    std::lock_guard<std::mutex> lock(riftMutex);
    Rift const* run = live.Find(runId);
    if (!run || run->state == "closed")
        return false;
    result = *run;
    return true;
}
// The live run this player's PARTY is in, if any. 7.9.7: the first accepter
// creates it and everyone else joins that same one, so "is there a run to join"
// is a question about the group, not about the asking player.
bool PartyRun(Player* player, Rift& result)
{
    if (!player)
        return false;
    if (EnrolledRun(player->GetGUID(), result))
        return true;
    Group* group = player->GetGroup();
    if (!group)
        return false;
    for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
        if (Player* member = ref->GetSource())
            if (member != player && EnrolledRun(member->GetGUID(), result))
                return true;
    return false;
}
// 7.9.7: the obelisk OFFERS the rift quest; it no longer teleports anyone.
//
// The menu is built here rather than left to the core's questgiver default,
// which would list every variant related to the object. 7.9 forbids that: the
// three denominators are an internal detail, and the player sees exactly one
// "Nephalem Rift". Handled gossip stops the default menu, so this is the whole
// menu the player gets.
void OfferRiftQuest(Player* player, GameObject* go)
{
    ChatHandler handler(player->GetSession());
    Rift rift;

    // A party already in a run offers that run's own variant, so a late joiner
    // accepts the quest the run is actually being played on (7.9.1 item 2).
    std::uint32_t questId = 0;
    if (PartyRun(player, rift))
    {
        if (rift.mode == "gr")
        {
            handler.SendSysMessage("Your party's Greater Rift has started. Its roster is closed.");
            return;
        }
        // 7.9.7: a newcomer cannot start a rift while the party's run is
        // closing, and the obelisk refuses until it has closed.
        bool closing = false;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            closing = pendingCloses.count(rift.id) != 0;
        }
        if (closing && !player->GetQuestStatus(rift.questId))
        {
            handler.SendSysMessage("That rift is closing. Wait for it to close before starting another.");
            return;
        }
        questId = rift.questId;
    }
    else
    {
        if (player->IsInCombat() || !DC::World::IsInHub(player))
        {
            handler.SendSysMessage("Use the obelisk from the hub while out of combat.");
            return;
        }
        // 7.2: reserve the dungeon and its variant BEFORE the quest is offered,
        // and never reroll after acceptance.
        Dungeon dungeon;
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            if (!dataReady || pool.empty() || !nephalemQuest.id)
            {
                handler.SendSysMessage("The rift pool is not loaded; see the startup log.");
                return;
            }
            dungeon = pool[std::uniform_int_distribution<std::size_t>(0, pool.size() - 1)(Engine())];
            questId = nephalemQuest.id;
        }
        std::lock_guard<std::mutex> lock(workMutex);
        reservations[player->GetGUID()] = Reservation{dungeon, questId, getMSTime()};
    }

    Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
    if (!quest)
    {
        handler.SendSysMessage("The rift quest is missing; apply rifts_0011_rift_quests.sql.");
        return;
    }
    // Already holding it: the obelisk has nothing more to say. Re-offering a
    // held quest would only re-open its accept dialog.
    if (player->GetQuestStatus(questId) == QUEST_STATUS_INCOMPLETE ||
        player->GetQuestStatus(questId) == QUEST_STATUS_COMPLETE)
    {
        handler.SendSysMessage("You are already on this rift. Use the portal beside the obelisk.");
        return;
    }
    player->PlayerTalkClass->SendQuestGiverQuestDetails(quest, go->GetGUID(), true);
}
// True for any of the fixed rift variants, Greater included: cleanup and the
// no-abandon rule have to recognise a Phase B quest that reached a log somehow,
// not just the three this phase hands out.
bool IsRiftQuest(std::uint32_t questId)
{
    if (!questId)
        return false;
    std::lock_guard<std::mutex> lock(dataMutex);
    return riftQuests.count(questId) != 0;
}
thread_local bool enrolling = false;
struct EnrollGuard
{
    bool owner;
    EnrollGuard() : owner(!enrolling) { enrolling = true; }
    ~EnrollGuard() { if (owner) enrolling = false; }
};
std::mutex reAddMutex;
std::set<ObjectGuid> pendingReAdds;

// --- the cross-map queue ----------------------------------
//
// ProjectProgress, CompleteRunQuests, RemoveRunQuests and PayClosingReward all
// used to write quest state and send packets to players who may be on ANOTHER
// map, driven from the instance map's update. That is safe only while the world
// runs one map thread, which is why the module asserts MapUpdate.Threads == 1 at
// startup. The assertion stays; this removes the need
// for it to be true.
//
// Each of the four now enqueues one item of work per player and returns. The
// work runs on that player's OWN update, which is by definition their own map's
// thread. Same visible behaviour, at most one tick later.
enum class QuestWork : std::uint8_t
{
    Progress,   // project the run's capped progress into this member's quest
    Complete,   // guardian death: top up, then complete
    Remove,     // closure: strip the quest and say so
    Reward,     // the closing reward, once per run per member
};

struct PendingWork
{
    QuestWork kind = QuestWork::Progress;
    Rift rift;                     // a copy: the run may close before this drains
    std::uint64_t xp = 0, gold = 0;   // Reward only
};

std::mutex questWorkMutex;
std::unordered_map<ObjectGuid, std::vector<PendingWork>> questWork;

// Queued by run, delivered per player. A second Progress for the same player
// replaces the first: only the newest total matters, and the counter never goes
// backwards, so collapsing them cannot lose anything.
void Enqueue(ObjectGuid player, PendingWork work)
{
    std::lock_guard<std::mutex> lock(questWorkMutex);
    auto& queue = questWork[player];
    if (work.kind == QuestWork::Progress)
        for (PendingWork& existing : queue)
            if (existing.kind == QuestWork::Progress && existing.rift.id == work.rift.id)
            {
                existing = work;
                return;
            }
    queue.push_back(work);
}

// Every enrolled member of a run, as GUIDs. Reading the table is safe from any
// thread; touching the Player objects is what had to move.
std::vector<ObjectGuid> EnrolledGuids(std::uint64_t runId)
{
    std::vector<ObjectGuid> out;
    QueryResult rows = CharacterDatabase.Query(
        "SELECT player_guid FROM dc_rift_member WHERE run_id={} AND state='enrolled'", runId);
    if (!rows)
        return out;
    do
    {
        out.push_back(ObjectGuid((*rows)[0].Get<uint64>()));
    } while (rows->NextRow());
    return out;
}
// 7.3's module-local bulk credit adapter. KilledMonsterCredit adds exactly one
// and fires achievement criteria with it, so projecting a run's progress with it
// would mean thousands of synthetic kills per update. This mirrors its counter
// work instead, through the public accessors, and does it in one step:
//
//   cap at the template count, write CreatureOrGOCount, mark the quest for
//   saving, send ONE delta, then run normal completion checking - which is what
//   carries the guardian veto in OnPlayerBeforeQuestComplete.
//
// It sets an ABSOLUTE target rather than adding a delta, because that is what
// both callers want: a member joining mid-run copies the run's total, and a
// kill projects the run's new total to everyone. It never moves backwards.
void SetQuestProgress(Player* member, Rift const& rift)
{
    if (!member || !rift.questId)
        return;
    Quest const* quest = sObjectMgr->GetQuestTemplate(rift.questId);
    if (!quest)
        return;
    QuestStatusMap& statuses = member->getQuestStatusMap();
    auto found = statuses.find(rift.questId);
    if (found == statuses.end())
        return;
    QuestStatusData& status = found->second;
    // Only an INCOMPLETE quest takes progress, exactly as the core helper does.
    // A FAILED or COMPLETE one is left alone; 7.4 wants the run's own progress
    // to carry on regardless, and it does, in dc_rift.
    if (status.Status != QUEST_STATUS_INCOMPLETE)
        return;

    // 7.3: one synthetic objective, slot 0. The rest are unused.
    uint32 const required = quest->RequiredNpcOrGoCount[0];
    uint16 const current = status.CreatureOrGOCount[0];
    uint16 const target = static_cast<uint16>(std::min<unsigned>(rift.progress, required));
    if (target <= current)
        return;
    uint16 const delta = static_cast<uint16>(target - current);
    status.CreatureOrGOCount[0] = target;
    member->GetQuestStatusSaveMap()[rift.questId] = true;
    // Empty GUID on purpose: a real one would make the core resolve that
    // creature's entry and credit against it instead (7.3).
    member->SendQuestUpdateAddCreatureOrGo(quest, ObjectGuid::Empty, 0, current, delta);
    if (member->CanCompleteQuest(rift.questId))
        member->CompleteQuest(rift.questId);
    else
        member->AdditionalSavingAddMask(ADDITIONAL_SAVING_QUEST_STATUS);
}
// 7.9.7: the server puts the quest in a member's log itself. There is no WoW
// share popup and nothing to decline - the design says "silently, with a chat
// notice", so this is an AddQuest, not Player::SendQuestConfirmAccept.
//
// `progress` is the run's current units: a member who joins a run in progress
// sees the counter the run is actually on, not 0 (7.9.1 item 3).
void GiveRunQuest(Rift const& rift, Player* member, char const* notice)
{
    if (!member || !member->GetSession() || !rift.questId)
        return;
    // AddQuestAndCheckCompletion fires OnPlayerQuestAccept, which re-enters
    // JoinOrCreateRun. Every internal add is guarded, so the coordinator runs
    // once for a real player accept and never for one of ours.
    EnrollGuard guard;
    Quest const* quest = sObjectMgr->GetQuestTemplate(rift.questId);
    if (!quest)
        return;
    QuestStatus const status = member->GetQuestStatus(rift.questId);
    if (status != QUEST_STATUS_NONE && status != QUEST_STATUS_REWARDED)
    {
        // Already holds it. Still enrol them - a member can hold the quest from
        // an earlier run of the same variant - and resynchronise the counter.
        EnrollMember(rift, member->GetGUID());
        SetQuestProgress(member, rift);
        return;
    }
    // No status, so any slot still holding the id is an orphan: it goes before the add, or the add
    // would take a second slot for the same id.
    ClearQuestSlots(member, rift.questId);
    if (!member->CanAddQuest(quest, false))
    {
        ChatHandler(member->GetSession()).SendSysMessage(
            "Your quest log is full, so the party's rift quest could not be added. "
            "Make room and take it at the obelisk.");
        return;
    }
    member->AddQuestAndCheckCompletion(quest, nullptr);
    EnrollMember(rift, member->GetGUID());
    SetQuestProgress(member, rift);
    if (notice)
        ChatHandler(member->GetSession()).SendSysMessage(notice);
}
// Pushes the run's current progress into every enrolled member's quest. 7.6:
// no kill-distance and no alive filter - a member standing in the hub or lying
// dead in the instance is still enrolled, and still watches the counter move.
void ProjectProgress(Rift const& rift)
{
    // Enqueue-only (part B). The projection itself runs on each member's own
    // map thread; see the drain in RiftPlayer::OnPlayerUpdate.
    for (ObjectGuid guid : EnrolledGuids(rift.id))
        Enqueue(guid, PendingWork{QuestWork::Progress, rift, 0, 0});
}
// How long a party member who logs out keeps their enrollment. A tunable,
// read from the same table every other rift number comes from.
unsigned LogoutGraceSeconds()
{
    std::lock_guard<std::mutex> lock(dataMutex);
    // No literal fallback: the 120 lives in the CSV and nowhere else, and a
    // copy here would quietly outvote it the day the table failed to load.
    // 0 means "no grace", which is the safe way to be wrong - a returning
    // member is detached rather than silently readmitted to a run.
    if (affixNumbers)
    {
        double const value = affixNumbers->Get("_global|rift_logout_grace_seconds", -1.0);
        if (value >= 0.0)
            return static_cast<unsigned>(value);
    }
    LOG_ERROR("server", "[DC rifts] rift_logout_grace_seconds is missing from dc_affix_tunables; "
                        "using 0. Apply rifts_0010_affix_tunables.sql.");
    return 0;
}
// Every log slot holding the quest, whatever its status says. The core's AddQuest
// never asks whether the id is already in the log: each call takes the next free slot while the
// status map keeps one entry per id. So a slot can outlive its status (a partial strip) or double
// up, and nothing status-based sees it; slots are not saved, so only a relog used to clear them.
void ClearQuestSlots(Player* player, std::uint32_t questId)
{
    for (uint16 slot = player->FindQuestSlot(questId); slot < MAX_QUEST_LOG_SIZE;
         slot = player->FindQuestSlot(questId))
        player->SetQuestSlot(slot, 0);
}
// Takes the quest out of a character's log for good. 7.5: the UI abandon
// callback is not this, and RemoveActiveQuest alone leaves the log slot set, so
// both go, in that order.
void StripRunQuest(Player* player, std::uint32_t questId)
{
    if (!player || !questId)
        return;
    // RemoveActiveQuest leaves the id in the player's timed-quest set, and SatisfyQuestTimed refuses
    // any new timed quest while that set is not empty (a Greater Rift: "you already have a timed
    // quest"). Unconditional: the set can outlive the status.
    player->RemoveTimedQuest(questId);
    if (player->GetQuestStatus(questId) != QUEST_STATUS_NONE)
    {
        player->AbandonQuest(questId);
        player->RemoveActiveQuest(questId, false);
    }
    ClearQuestSlots(player, questId);
}
// Counts who is still reachable in a run. 7.9.7: "the run closes AT ONCE when
// its last online enrolled member logs out" - the grace is for a member coming
// back to a run other people are still in, never for an empty one.
unsigned OnlineEnrolled(Rift const& rift, ObjectGuid ignore)
{
    QueryResult rows = CharacterDatabase.Query(
        "SELECT player_guid FROM dc_rift_member WHERE run_id={} AND state='enrolled'", rift.id);
    if (!rows)
        return 0;
    unsigned online = 0;
    do
    {
        ObjectGuid const guid = ObjectGuid((*rows)[0].Get<uint64>());
        if (guid != ignore && ObjectAccessor::FindPlayer(guid))
            ++online;
    } while (rows->NextRow());
    return online;
}
// Ends a member's enrollment. `reason` goes in the row so the login sweep and
// `.dc rift status` can both say what happened.
// `player` may be null: a member can be kicked while logged out, and the row
// has to go regardless or the login sweep would restore them into a party they
// are no longer in. Their quest is stripped by that same sweep instead.
void DetachMember(Rift const& rift, ObjectGuid guid, Player* player, char const* reason, char const* notice)
{
    CharacterDatabase.Execute(
        "UPDATE dc_rift_member SET state='detached', offline_since=NULL, departure_reason='{}' "
        "WHERE run_id={} AND player_guid={}", reason, rift.id, guid.GetRawValue());
    // 7.9.8, the reverse: the rubble and the portal vanish for them and the obelisk
    // comes back. Leaving the party is the only abandon (7.9.7), and a kick is a
    // leave, so this one call covers both.
    LeaveMembership(rift.id, guid);
    // A member who leaves or is kicked loses their Urshi tries and stops holding the rift open.
    UrshiMemberLeft(rift.id, guid, player);
    if (player)
    {
        StripRunQuest(player, rift.questId);
        if (notice && player->GetSession())
            ChatHandler(player->GetSession()).SendSysMessage(notice);
    }
    RescaleForHeadcount(rift.id);
}
// 7.9.7 logout. Solo closes the run at once; in a party the member goes
// `offline` and has the grace to come back. Either way the run closes the
// moment its last ONLINE enrolled member leaves - the grace exists for someone
// returning to a run others are still playing, not to hold an empty one open.
void HandleLogout(Player* player)
{
    Rift rift;
    if (!player || !EnrolledRun(player->GetGUID(), rift))
        return;
    // Logging out forfeits the member's Urshi tries.
    UrshiMemberLeft(rift.id, player->GetGUID(), nullptr);
    bool const solo = !player->GetGroup();
    bool const lastOut = OnlineEnrolled(rift, player->GetGUID()) == 0;
    if (solo || lastOut)
    {
        CharacterDatabase.Execute(
            "UPDATE dc_rift_member SET state='detached', offline_since=NULL, departure_reason='logout' "
            "WHERE run_id={}", rift.id);
        // A whole-run detach, so a whole-run clear. QueueClose below reaches
        // RemoveEntrance, which clears the same set; doing it here as well keeps the
        // rule that the cache is written by the function that writes the rows.
        ClearMembership(rift.id);
        StripRunQuest(player, rift.questId);
        QueueClose(rift);
        LOG_INFO("server", "[DC rifts] rift {} closed: {} was its last online member", rift.id, player->GetName());
        return;
    }
    // A Greater Rift is committed until the Guardian dies (7.9.2 item 7, 7.9.7): a logout is a failed
    // abandon with no grace and no re-entry, so the member is detached and the quest goes now.
    if (rift.mode == "gr")
    {
        DetachMember(rift, player->GetGUID(), player, "logout", nullptr);
        LOG_INFO("server", "[DC rifts] rift {}: {} logged out of a Greater Rift and is detached", rift.id,
                 player->GetName());
        return;
    }
    CharacterDatabase.Execute(
        "UPDATE dc_rift_member SET state='offline', offline_since=NOW(), departure_reason='logout' "
        "WHERE run_id={} AND player_guid={}", rift.id, player->GetGUID().GetRawValue());
    // The quest stays in their log while they are away; the login sweep is what
    // decides whether it is still theirs. Their seat is still counted for
    // scaling until the grace runs out.
    //
    // 7.9.8: and deliberately NO membership change. `offline` is not a leave - 7.5
    // keeps them enrolled through the grace and makes the login sweep decide - so they
    // stay in the visibility cache. They are not in the world, so that shows nobody
    // anything, and when they come back the sweep has already put them on one side or
    // the other, which is what they then see.
}
// 7.5's login sweep, and 7.9.7's "delete the stale quest, add the new one".
//
// Every rift quest in the log is checked against the member row that should own
// it: a live run inside the grace restores enrollment and resynchronises the
// counter, anything else is stale and goes. Then, if the player's party is in a
// run they are not enrolled in, they are given its quest - which is how an
// offline member who was never told about a new run finally gets it.
void SweepOnLogin(Player* player)
{
    if (!player)
        return;
    std::vector<std::uint32_t> held;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        for (std::uint32_t questId : riftQuests)
            if (player->GetQuestStatus(questId) != QUEST_STATUS_NONE)
                held.push_back(questId);
    }

    unsigned const grace = LogoutGraceSeconds();
    std::uint64_t const guid = player->GetGUID().GetRawValue();
    Rift restored;
    bool restoredAny = false;
    // When the grace has run out, only a run that STARTED AFTER this member
    // went offline may be given to them. Without that the sweep detaches from
    // the run and then immediately re-adds the same one through PartyRun.
    std::string cutoff;

    for (std::uint32_t questId : held)
    {
        // Newest LIVE run first. A character with an old detached row and a new
        // live one on the same variant was picking up the detached row, which
        // then stripped the live quest and mislabelled the live row.
        QueryResult row = CharacterDatabase.Query(
            "SELECT m.run_id, m.state, TIMESTAMPDIFF(SECOND, m.offline_since, NOW()), m.offline_since "
            "FROM dc_rift_member m JOIN dc_rift r ON r.id=m.run_id "
            "WHERE m.player_guid={} AND m.quest_id={} AND r.state<>'closed' "
            "ORDER BY m.run_id DESC LIMIT 1", guid, questId);
        bool keep = false;
        Rift candidate;
        if (row)
        {
            std::uint64_t const runId = (*row)[0].Get<uint64>();
            std::string const state = (*row)[1].Get<std::string>();
            // NULL offline_since reads as 0, which is what an `enrolled` row
            // wants: it never left, so no grace has been spent.
            std::uint32_t const away = (*row)[2].Get<uint32>();
            bool haveLive = false;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                if (Rift const* run = live.Find(runId); run && run->state != "closed")
                {
                    candidate = *run;
                    haveLive = true;
                }
            }
            bool closing = false;
            if (haveLive)
            {
                std::lock_guard<std::mutex> lock(workMutex);
                closing = pendingCloses.count(candidate.id) != 0;
            }
            // Guardian death is the completion moment. A
            // member who was offline for it earns nothing and is NOT restored
            // by returning inside the grace - the run has already been won.
            bool const missedCompletion = haveLive && (candidate.state == "complete" || closing);
            if (haveLive && !missedCompletion && (state == "enrolled" || (state == "offline" && away <= grace)))
            {
                keep = true;
            }
            else if (missedCompletion)
            {
                CharacterDatabase.Execute(
                    "UPDATE dc_rift_member SET state='detached', offline_since=NULL, "
                    "departure_reason='missed_completion' WHERE run_id={} AND player_guid={}",
                    runId, guid);
                LeaveMembership(haveLive ? candidate.id : 0, player->GetGUID());
                StripRunQuest(player, questId);
                if (player->GetSession())
                    ChatHandler(player->GetSession()).SendSysMessage(
                        "Your party finished that rift while you were away.");
                continue;
            }
            else if (state == "offline")
                cutoff = (*row)[3].Get<std::string>();
        }
        if (keep)
        {
            restored = candidate;
            restoredAny = true;
            CharacterDatabase.Execute(
                "UPDATE dc_rift_member SET state='enrolled', offline_since=NULL, departure_reason='' "
                "WHERE run_id={} AND player_guid={}", restored.id, guid);
            // 7.5, unchanged for the offline member: they kept their enrollment
            // through the grace, so they come back to the party's hub objects exactly
            // as they left them - portal and rubble there, obelisk gone.
            JoinMembership(restored.id, player->GetGUID());
            SetQuestProgress(player, restored);
            if (player->GetSession())
                ChatHandler(player->GetSession()).SendSysMessage(
                    "Your Nephalem Rift is still open. Use the portal beside the obelisk.");
        }
        else
        {
            CharacterDatabase.Execute(
                "UPDATE dc_rift_member SET state='detached', offline_since=NULL, departure_reason='grace_expired' "
                "WHERE player_guid={} AND quest_id={} AND state<>'detached'", guid, questId);
            // The grace ran out. 0 means "whichever run they were in", because this
            // branch does not always have a live one to name.
            LeaveMembership(0, player->GetGUID());
            StripRunQuest(player, questId);
        }
    }

    // A run the party is on that this character is not enrolled in: 7.9.7 gives
    // an offline member the quest at login if the run still lives. After a
    // grace expiry that must be a DIFFERENT run - one opened since they went
    // offline - or this would undo the detach it just performed.
    Rift party;
    if (!restoredAny && PartyRun(player, party))
    {
        bool newer = cutoff.empty();
        if (!newer)
        {
            QueryResult later = CharacterDatabase.Query(
                "SELECT 1 FROM dc_rift WHERE id={} AND opened_at > '{}'", party.id, cutoff);
            newer = bool(later);
        }
        bool closing = false;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            closing = pendingCloses.count(party.id) != 0;
        }
        if (newer && party.mode != "gr" && party.state != "complete" && !closing)
            GiveRunQuest(party, player, "Your party has a Nephalem Rift open. Use the obelisk portal to enter.");
    }
    if (restoredAny)
        RescaleForHeadcount(restored.id);
}
// Closure. Every association goes, and every quest still in a log goes with it,
// whether that player is inside, in the hub or offline - 7.6 is explicit that
// removing a quest from map occupants only is not cleanup. An offline holder's
// row is marked here and their quest is stripped by the login sweep, which is
// the only moment their log can be touched.
void RemoveRunQuests(Rift const& rift)
{
    // The per-player half is enqueued (part B); the row update below is a
    // table write and stays here, so an offline member is detached immediately
    // and the login sweep finds the right answer.
    QueryResult rows = CharacterDatabase.Query(
        "SELECT player_guid FROM dc_rift_member WHERE run_id={} AND state<>'detached'", rift.id);
    if (rows)
        do
        {
            Enqueue(ObjectGuid((*rows)[0].Get<uint64>()),
                    PendingWork{QuestWork::Remove, rift, 0, 0});
        } while (rows->NextRow());
    CharacterDatabase.Execute(
        "UPDATE dc_rift_member SET state='detached', offline_since=NULL, departure_reason='closed' "
        "WHERE run_id={}", rift.id);
    // The whole run at once. RemoveEntrance clears the same set when it takes the
    // objects down; whichever of the two runs first, the other finds nothing to do.
    ClearMembership(rift.id);
}
// --- turn-in and the closing reward (7.9.7, step 3d) -----------------------
//
// "Any holder whose quest is complete may turn in at the Keeper. The first
// turn-in pays the closing reward and starts the 30-second countdown; later
// holders' quests are simply removed at closure. The reward goes to every
// player still holding the quest, wherever they are, once per run."
//
// The quest itself carries zero rewards; this is the module paying, with the
// run's own row as the receipt, exactly as the guardian payout does.
//
// Both bases are PLACEHOLDER 0 until they are set, so today this computes
// nothing and says so in the log. It never invents a value.
void PayClosingReward(Rift const& rift)
{
    double xpBase = 0.0, goldBase = 0.0;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        if (affixNumbers)
        {
            xpBase = affixNumbers->Get("_global|close_xp_base", 0.0);
            goldBase = affixNumbers->Get("_global|close_gold_base", 0.0);
        }
    }
    double xpBonus = 0.0, goldBonus = 0.0;
    if (QueryResult row = WorldDatabase.Query(
            "SELECT t.xp_bonus_pct, t.gold_bonus_pct FROM dc_tier_phase p "
            "JOIN dc_difficulty_tiers t ON t.tier=p.tier_name WHERE p.tier_id={}", rift.tier))
    {
        xpBonus = (*row)[0].Get<double>();
        goldBonus = (*row)[1].Get<double>();
    }
    std::uint64_t const xp = static_cast<std::uint64_t>(xpBase * (1.0 + xpBonus / 100.0));
    // The economy's unit is copper and one copper is one displayed gold,
    // so close_gold_base is already in the unit the
    // message prints. No conversion here, deliberately.
    std::uint64_t const gold = static_cast<std::uint64_t>(goldBase * (1.0 + goldBonus / 100.0));

    if (!xp && !gold)
    {
        LOG_INFO("server", "[DC rifts] rift {} closing reward paid nothing: close_xp_base and "
                           "close_gold_base are still PLACEHOLDER 0 (the designer's tunables, "
                           "dc_affix_tunables._global)", rift.id);
        return;
    }

    // Who is paid is the ENROLLED SET at this moment, never the quest log.
    // Player::RewardQuest removes the active quest before OnPlayerCompleteQuest,
    // and a repeatable quest then reads QUEST_STATUS_NONE, so the player who
    // just turned in would be the one member skipped.
    //
    // The payment itself is enqueued (part B): granting gold and Paragon XP and
    // sending the chat line all touch a Player who may be on another map. The
    // amounts are computed here, once, so every member is paid the figures the
    // run closed at rather than whatever the tier says when their tick comes.
    unsigned queued = 0;
    for (ObjectGuid guid : EnrolledGuids(rift.id))
    {
        Enqueue(guid, PendingWork{QuestWork::Reward, rift, xp, gold});
        ++queued;
    }
    LOG_INFO("server", "[DC rifts] rift {} closing reward queued: {} XP and {} gold for {} enrolled members "
                       "(tier {} bonuses +{}% XP, +{}% gold)",
             rift.id, xp, gold, queued, rift.tier, xpBonus, goldBonus);
}
// The idempotent turn-in coordinator 7.5 asks for. The FIRST turn-in pays and
// starts the countdown; every later one is a no-op, because closing_at is
// claimed once and a repeated request never moves it.
void HandleTurnIn(Player* player, std::uint32_t questId)
{
    Rift rift;
    if (!player || !EnrolledRun(player->GetGUID(), rift) || rift.questId != questId)
        return;
    // The Keeper does not offer this turn-in while a member has Urshi tries, so this is the backstop for a
    // turn-in that reached the server another way: no countdown starts.
    if (std::string held = UrshiBlocksClose(rift.id); !held.empty())
    {
        if (player->GetSession())
            ChatHandler(player->GetSession()).SendSysMessage(held);
        return;
    }
    bool first = false;
    {
        std::lock_guard<std::mutex> lock(workMutex);
        first = pendingCloses.find(rift.id) == pendingCloses.end();
        if (first)
            pendingCloses.emplace(rift.id, PendingClose{rift, getMSTime()});
    }
    if (!first)
    {
        // A later holder turning in: their quest is already gone from their log
        // by the time this runs, and the countdown is not restarted (7.6).
        if (player->GetSession())
            ChatHandler(player->GetSession()).SendSysMessage("The rift is already closing.");
        return;
    }
    // A Greater Rift's outcome is the Guardian's result, written when it died; the
    // turn-in only starts the countdown.
    CharacterDatabase.Execute(
        "UPDATE dc_rift SET closing_at=DATE_ADD(NOW(), INTERVAL {} SECOND){} WHERE id={}",
        RiftCloseMs() / 1000, rift.mode == "gr" ? "" : ", outcome='success'", rift.id);
    PayClosingReward(rift);
    Announce(rift, "The rift is closing.");
    if (player->GetSession())
        ChatHandler(player->GetSession()).SendSysMessage(
            "Your rift will close in 30 seconds. Anyone still inside will return to the hub.");
}
// Guardian death (7.4). Completes every still-enrolled member's quest, wherever
// they stand, and tops their counter up first so a member who was offline for
// the last few kills does not turn in a half-filled bar. The veto has already
// been lifted by the run's state, so CompleteQuest goes through this time.
void CompleteRunQuests(std::uint64_t runId)
{
    Rift rift;
    {
        std::lock_guard<std::mutex> lock(riftMutex);
        Rift const* run = live.Find(runId);
        if (!run)
            return;
        rift = *run;
    }
    // Enqueue-only (part B): a member standing in the hub is completed on their
    // own map thread, one tick later at most.
    for (ObjectGuid guid : EnrolledGuids(rift.id))
        Enqueue(guid, PendingWork{QuestWork::Complete, rift, 0, 0});
}
// Shares the run's quest with every member of the creator's party, online
// wherever they stand (7.9.7). An offline member gets it at login instead.
void ShareRunQuest(Rift const& rift, Player* creator)
{
    Group* group = creator ? creator->GetGroup() : nullptr;
    if (!group)
        return;
    for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
        if (Player* member = ref->GetSource())
            if (member != creator && member->IsInWorld())
                GiveRunQuest(rift, member,
                             "Your party opened a Nephalem Rift. Use the obelisk portal to enter.");
}
void JoinOrCreateRun(Player* player, std::uint32_t questId)
{
    if (enrolling)
        return;
    EnrollGuard guard;

    ChatHandler handler(player->GetSession());
    Rift rift;
    if (PartyRun(player, rift))
    {
        // A Greater Rift's roster closed at its start, so nobody accepts into it.
        if (rift.mode == "gr")
        {
            StripRunQuest(player, questId);
            handler.SendSysMessage("Your party's Greater Rift has started. Its roster is closed.");
            return;
        }
        // A reservation is per player, so two members can be holding dialogs on
        // different count variants at the same moment. Once the party has a run,
        // its variant is the only one that exists - accepting any other would
        // leave that player holding a quest the run never advances.
        if (rift.questId && questId != rift.questId)
        {
            StripRunQuest(player, questId);
            {
                std::lock_guard<std::mutex> lock(workMutex);
                reservations.erase(player->GetGUID());
            }
            GiveRunQuest(rift, player, nullptr);
            handler.SendSysMessage("Your party already has a rift open; you have been given its quest.");
            return;
        }
        // 7.9.1 item 3: join the run that exists. The dungeon, tier and progress
        // are the run's; nothing is rerolled and no second guardian is possible.
        EnrollMember(rift, player->GetGUID());
        SetQuestProgress(player, rift);
        {
            std::lock_guard<std::mutex> lock(workMutex);
            reservations.erase(player->GetGUID());
        }
        handler.SendSysMessage("Joined the Nephalem Rift. Use the obelisk portal to enter.");
        return;
    }

    Reservation reservation;
    bool held = false;
    {
        std::lock_guard<std::mutex> lock(workMutex);
        auto found = reservations.find(player->GetGUID());
        if (found != reservations.end())
        {
            if (getMSTimeDiff(found->second.made, getMSTime()) <= ReservationMs() &&
                found->second.questId == questId)
            {
                reservation = found->second;
                held = true;
            }
            reservations.erase(found);
        }
    }

    std::string error;
    Rift created;
    if (!OpenRun(player, held ? &reservation : nullptr, &created, error))
    {
        // The quest is already in the log at this point, so a failed run has to
        // take it back out rather than leave a rift quest with no rift. Through
        // StripRunQuest, which also clears the log SLOT - AbandonQuest and
        // RemoveActiveQuest between them do not, and left a ghost entry.
        StripRunQuest(player, questId);
        handler.SendSysMessage(error);
        return;
    }
    // 7.9.7: the run's quest goes to the whole party at this moment, silently.
    // After the creator is enrolled and the portal is up, so a member who reads
    // the notice and runs straight to the obelisk finds a portal already there.
    ShareRunQuest(created, player);
    handler.SendSysMessage("Nephalem Rift opened. Your party has the quest; use the portal beside the obelisk.");
}
// The other half of part B. Every item was queued by a run on some other
// thread; all of it happens here, on the player's own map update.
//
// A run may have closed between the enqueue and this tick, which is why each
// item carries its own copy of the Rift rather than looking one up: the work is
// what the run decided at the time, and a closure that has since happened must
// not silently change a payment or a completion that was already owed.
void DrainQuestWork(Player* player)
{
    std::vector<PendingWork> mine;
    {
        std::lock_guard<std::mutex> lock(questWorkMutex);
        auto found = questWork.find(player->GetGUID());
        if (found == questWork.end())
            return;
        mine.swap(found->second);
        questWork.erase(found);
    }
    for (PendingWork const& work : mine)
    {
        switch (work.kind)
        {
            case QuestWork::Progress:
                SetQuestProgress(player, work.rift);
                break;
            case QuestWork::Complete:
                // A Guardian that died after 0:00 does not beat the rift. The quest fails
                // here if the core's own timer has not got to it yet, and stays FAILED: no
                // completion, no turn-in, no Keeper countdown.
                if (work.rift.mode == "gr" && work.rift.outcome != "success")
                {
                    if (player->GetQuestStatus(work.rift.questId) == QUEST_STATUS_INCOMPLETE)
                        player->FailQuest(work.rift.questId);
                    break;
                }
                SetQuestProgress(player, work.rift);
                if (player->GetQuestStatus(work.rift.questId) == QUEST_STATUS_INCOMPLETE &&
                    player->CanCompleteQuest(work.rift.questId))
                {
                    // 7.4: the clock stops at the kill, so the trip back and the turn-in cannot
                    // fail a rift that was beaten.
                    if (work.rift.mode == "gr")
                    {
                        player->RemoveTimedQuest(work.rift.questId);
                        if (uint16 slot = player->FindQuestSlot(work.rift.questId); slot < MAX_QUEST_LOG_SIZE)
                            player->SetQuestSlotTimer(slot, 0);
                    }
                    player->CompleteQuest(work.rift.questId);
                }
                break;
            case QuestWork::Remove:
                StripRunQuest(player, work.rift.questId);
                if (player->GetSession())
                    ChatHandler(player->GetSession()).SendSysMessage("That rift has closed.");
                break;
            case QuestWork::Reward:
            {
                std::uint64_t granted = 0, paidGold = 0;
                if (work.gold)
                {
                    // The receipt is per run per player, so a replayed closure
                    // or a retried tick credits nothing twice.
                    std::string const receipt = "rift:" + std::to_string(work.rift.id) + ":closing:gold:" +
                                                std::to_string(player->GetGUID().GetCounter());
                    PlayerEconomy::Scope rewards(player);
                    if (!DC::AccountEconomy::CreditGold(player, work.gold, receipt))
                        PlayerEconomy::Fail();
                    if (rewards.Finish())
                        paidGold = work.gold;
                    else
                        LOG_ERROR("server", "[DC rifts] rift {} closing gold for {} did not commit",
                                  work.rift.id, player->GetName());
                }
                if (work.xp)
                {
                    std::string paragonError;
                    if (DC::Paragon::GrantXP(player, work.xp, paragonError))
                        granted = work.xp;
                    else
                        LOG_WARN("server", "[DC rifts] rift {} closing XP not granted to {}: {}",
                                 work.rift.id, player->GetName(), paragonError);
                }
                if (player->GetSession())
                    ChatHandler(player->GetSession()).PSendSysMessage(
                        "The rift is closing. Closing reward: {} Paragon XP and {} gold.", granted, paidGold);
                break;
            }
        }
    }
}

// Progress from a kill or an orb (see the header). Projected to every enrolled
// member, wherever they are: 7.6 says progress goes to all enrolled members with
// no distance or alive filter, so the hub and the graveyard both count.
void AddProgress(Player* source, std::uint64_t runId, unsigned units, unsigned kills)
{
    Rift rift;
    {
        std::lock_guard<std::mutex> lock(riftMutex);
        Rift* stored = live.Find(runId);
        if (!stored || stored->state != "open")
            return;
        stored->kills += kills;
        stored->progress = Gr::Filled(stored->progress, units, stored->requiredUnits);
        rift = *stored;
    }
    Persist(rift);
    ProjectProgress(rift);
    if (rift.progress >= rift.requiredUnits)
        SpawnGuardian(source, rift);
}

// A kill that counts for `killer` in their rift: the player kill hook below, and a charmed monster's kill (RiftCharmKills).
static void CreditRiftKill(Player* killer, Creature* killed)
{
    if (!killer || !killed)
        return;
    // An Illusionist duplicate is neither a pack member nor a real kill:
    // 13-elite-affixes §10 gives copies no rift progress and no loot. The
    // loot half of this is dc_loot's, which does not read the marker yet.
    if (killed->CustomData.Get<IllusionState>("DCRiftIllusion"))
        return;
    Rift rift;
    if (!Current(killer, rift))
        return;

    // The guardian's own death is the end of the run, not progress.
    if (rift.state == "guardian" && CompleteGuardianKill(killed, killer))
        return;
    if (rift.state != "open")
        return;

    // 7.3: the kill is 20 progress units, or in a Greater Rift the unit times the
    // monster's type multiple. Raw kills stay for the model and for
    // `.dc rift status`; the quest counter, the guardian trigger and the AIO bar
    // all read progress.
    AddProgress(killer, rift.id, KillUnits(killed, rift), 1);
}

class RiftPlayer final : public PlayerScript
{
public:
    RiftPlayer() : PlayerScript("dc_rift_player", {PLAYERHOOK_ON_CREATURE_KILL,
                                                   PLAYERHOOK_ON_LOGIN,
                                                   PLAYERHOOK_ON_BEFORE_LOGOUT,
                                                   PLAYERHOOK_ON_LOGOUT,
                                                   PLAYERHOOK_ON_MAP_CHANGED,
                                                   PLAYERHOOK_ON_PLAYER_QUEST_ACCEPT,
                                                   PLAYERHOOK_ON_QUEST_COMPUTE_EXP,
                                                   PLAYERHOOK_ON_BEFORE_QUEST_COMPLETE,
                                                   PLAYERHOOK_ON_QUEST_ABANDON,
                                                   PLAYERHOOK_ON_PLAYER_COMPLETE_QUEST,
                                                   PLAYERHOOK_ON_UPDATE,
                                                   PLAYERHOOK_NOT_AVOID_SATISFY}) { }

    // 7.9.7: accepting at the obelisk is what creates or joins the run. The
    // hook lands after the quest is in the log, which is why a failed creation
    // has to remove it again rather than refuse up front.
    void OnPlayerQuestAccept(Player* player, Quest const* quest) override
    {
        if (!player || !player->GetSession() || !quest || !IsRiftQuest(quest->GetQuestId()))
            return;
        JoinOrCreateRun(player, quest->GetQuestId());
    }

    // 7.5: zero rewards includes XP, and RewardXPDifficulty is a DBC index, so
    // an index of 0 in the template does not by itself mean zero XP. This is
    // the hook that runs before the payout, and it is the one that makes it 0.
    // The closing reward is the module's, paid at the Keeper, never the quest's.
    void OnPlayerQuestComputeXP(Player*, Quest const* quest, uint32& xpValue) override
    {
        if (quest && IsRiftQuest(quest->GetQuestId()))
            xpValue = 0;
    }

    // 7.4: full N/M is NOT completable. The quest stays INCOMPLETE
    // while the guardian lives, and only guardian death opens it. This is the
    // veto that holds it there - never infer guardian death from a quest
    // callback, only from the run's own recorded state.
    bool OnPlayerBeforeQuestComplete(Player* player, uint32 questId) override
    {
        if (!player || !IsRiftQuest(questId))
            return true;
        Rift rift;
        if (!EnrolledRun(player->GetGUID(), rift))
            return false;   // a rift quest with no live run never completes
        // A Greater Rift beaten only by a Guardian killed before 0:00. A failed run's
        // quest stays FAILED, so a full counter cannot complete it either.
        if (rift.mode == "gr" && rift.outcome != "success")
            return false;
        return rift.state == "complete";
    }

    // 7.9.7: "No player abandon." The quest cannot be given up from the log;
    // leaving the party is the only way out. The handler has already stripped
    // the quest by the time this runs, so the answer is to put it back with the
    // run's progress intact and say why.
    // 7.5: this is the end of RewardQuest, after its save. The Keeper's own
    // OnQuestReward would be a second callback for the same event, so the
    // coordinator lives here and only here - no duplicate reward or closure.
    void OnPlayerCompleteQuest(Player* player, Quest const* quest) override
    {
        if (!player || !quest || !IsRiftQuest(quest->GetQuestId()))
            return;
        HandleTurnIn(player, quest->GetQuestId());
    }

    void OnPlayerQuestAbandon(Player* player, uint32 questId) override
    {
        if (!player || !player->GetSession() || !IsRiftQuest(questId))
            return;
        Rift rift;
        if (!EnrolledRun(player->GetGUID(), rift) || rift.questId != questId)
            return;   // not theirs any more: let the abandon stand as cleanup
        // NOT re-added here. This hook runs before the handler clears the log
        // slot, so a full quest log would make the re-add fail and the abandon
        // succeed. Queued for this player's next update instead.
        {
            std::lock_guard<std::mutex> lock(reAddMutex);
            pendingReAdds.insert(player->GetGUID());
        }
        ChatHandler(player->GetSession()).SendSysMessage(
            "You cannot abandon a rift. Leave the party to give it up.");
    }

    // Affix debuffs rode the town portal into the hub and
    // kept ticking with their caster destroyed. Every generated shell has
    // AuraInterruptFlags = 0, so Player::TeleportTo's own
    // RemoveAurasWithInterruptFlags(AURA_INTERRUPT_FLAG_CHANGE_MAP) strips none
    // of them. The bug offers two fixes; this is the second, because the first
    // changes generated spell data, which needs approval (00b).
    //
    // The core calls this from Map::AddPlayerToMap, i.e. once the player is
    // already on the destination map, which is the only moment "caster-less" can
    // be decided: before the move the elite is still findable on the old map.
    // A new instance is a new Map object, so a rift entry counts as well as a
    // portal home.
    //
    // Self-cast auras are left alone - that is every class passive, buff, wing
    // and cosmetic - and so is any aura whose caster made the trip.
    void OnPlayerMapChanged(Player* player) override
    {
        if (!player)
            return;
        std::vector<uint32> orphaned;
        for (auto const& applied : player->GetAppliedAuras())
        {
            AuraApplication const* application = applied.second;
            Aura* aura = application ? application->GetBase() : nullptr;
            if (!aura || aura->GetCasterGUID() == player->GetGUID() || aura->GetCaster())
                continue;
            orphaned.push_back(applied.first);
        }
        for (uint32 spellId : orphaned)
            player->RemoveAurasDueToSpell(spellId);
        if (!orphaned.empty())
            LOG_DEBUG("server", "[DC rifts] Stripped {} caster-less aura(s) from {} on map change",
                      orphaned.size(), player->GetName());
        // The other half of the same problem: a Jailer root, a feared run or a
        // Knockback slow queued on the old map can no longer reach this player.
        ReleasePlayerControls(player);
    }

    // A `.dc elite` test pack is a summon on a continent map, which never
    // unloads, so it would outlive the GM who asked for it.
    // Everything queued for this player, run on this player's OWN update -
    // which is their own map's thread, which is the whole point of part B.
    void OnPlayerUpdate(Player* player, uint32) override
    {
        if (!player)
            return;
        DrainQuestWork(player);

        // The no-abandon re-add, the first moment after the abandon handler has
        // freed the log slot. Kept separate: it is not a cross-map write, it is
        // a deferral for a different reason.
        {
            std::lock_guard<std::mutex> lock(reAddMutex);
            if (!pendingReAdds.erase(player->GetGUID()))
                return;
        }
        Rift rift;
        if (EnrolledRun(player->GetGUID(), rift))
            GiveRunQuest(rift, player, nullptr);
    }

    // 7.5: the before-logout hook, so the ordinary save carries the stripped quest. The after-logout
    // hook runs behind WorldSession::LogoutPlayer's SaveToDB, so a strip there never reached
    // character_queststatus and the quest came back at the next login.
    void OnPlayerBeforeLogout(Player* player) override
    {
        HandleLogout(player);
    }

    void OnPlayerLogout(Player* player) override
    {
        ClearHarness(player);
    }

    bool OnPlayerNotAvoidSatisfy(Player* player, DungeonProgressionRequirements const*,
                                uint32 targetMap, bool) override
    {
        if (!player)
            return true;
        // Open binds each member before teleporting; the same binding also
        // covers the town portal's return trip. Only a live Diablocraft rift
        // replaces WoW's dungeon level/quest/item requirements (09 F1/F3).
        auto* bind = sInstanceSaveMgr->PlayerGetBoundInstance(
            player->GetGUID(), targetMap, player->GetDifficulty(false));
        if (!bind || !bind->save)
            return true;
        std::lock_guard<std::mutex> lock(riftMutex);
        Rift const* run = live.FindByInstance(bind->save->GetInstanceId(), targetMap);
        return !run || run->state == "closed";
    }

    // F3. The town portal is a Diablocraft spell, so every playable class knows
    // it; casting behavior and return locations are owned by dc_town_portal.cpp.
    void OnPlayerLogin(Player* player) override
    {
        if (PlayableClass(player) && !player->HasSpell(TOWN_PORTAL_SHELL)
            && sSpellMgr->GetSpellInfo(TOWN_PORTAL_SHELL))
            player->learnSpell(TOWN_PORTAL_SHELL);
        SweepOnLogin(player);
    }

    void OnPlayerCreatureKill(Player* killer, Creature* killed) override
    {
        CreditRiftKill(killer, killed);
    }
};

// Unit::Kill fires the player kill hook for a Player killer only, so a monster's kill while charmed would
// add nothing to the bar (the same gap as issue #88 for pets and Ancients, which this does not widen to). It is its
// charmer's rift kill. Loot, gold, Life per Kill and on-kill powers still read the player hook and do not see it.
class RiftCharmKills final : public UnitScript
{
public:
    RiftCharmKills() : UnitScript("dc_rift_charm_kills", true, {UNITHOOK_ON_UNIT_DEATH}) { }
    void OnUnitDeath(Unit* victim, Unit* killer) override
    {
        Creature* dead = victim ? victim->ToCreature() : nullptr;
        Creature* body = killer ? killer->ToCreature() : nullptr;
        Player* master = body ? DC::Combat::CharmEffect::MasterOf(body) : nullptr;
        if (dead && dead != body && IsCharmedMonster(body) && master)
            CreditRiftKill(master, dead);
    }
};
// 7.9.7: "Leaving the party is the only abandon: it removes the quest and rift
// access, and a leaver inside the instance is ported to the hub at once. Kick
// counts as leave." The owner leaving changes nothing for the rest - leadership
// moves as WoW moves it, and the stored owner is only cleanup bookkeeping.
class RiftGroup final : public GroupScript
{
public:
    RiftGroup() : GroupScript("dc_rift_group", {GROUPHOOK_ON_ADD_MEMBER, GROUPHOOK_ON_REMOVE_MEMBER}) { }

    // A member invited into a party that is already running gets the quest with
    // the run's current progress copied in (7.9.7, 7.9.1 item 3) - unless the
    // run is closing, which the obelisk refuses to start over.
    void OnAddMember(Group* group, ObjectGuid guid) override
    {
        Player* joined = ObjectAccessor::FindPlayer(guid);
        if (!group || !joined)
            return;
        Rift rift;
        bool found = false;
        for (GroupReference* ref = group->GetFirstMember(); ref && !found; ref = ref->next())
            if (Player* member = ref->GetSource())
                if (member != joined && EnrolledRun(member->GetGUID(), rift))
                    found = true;
        if (!found)
            return;
        if (rift.mode == "gr")
        {
            // Closed roster: a member invited after the start gets no quest and no way in.
            if (joined->GetSession())
                ChatHandler(joined->GetSession()).SendSysMessage(
                    "Your party's Greater Rift has started. Its roster is closed.");
            return;
        }
        GiveRunQuest(rift, joined, "Your party has a Nephalem Rift open. Use the obelisk portal to enter.");
        RescaleForHeadcount(rift.id);
    }

    void OnRemoveMember(Group*, ObjectGuid guid, RemoveMethod method, ObjectGuid, char const*) override
    {
        // Deliberately NOT gated on the player being online. Kicking an
        // offline member has to take their row too; otherwise the sweep
        // restores them into a party that removed them.
        Player* left = ObjectAccessor::FindPlayer(guid);
        Rift rift;
        if (!EnrolledRun(guid, rift))
            return;
        bool const kicked = method == GROUP_REMOVEMETHOD_KICK;
        DetachMember(rift, guid, left, kicked ? "kicked" : "left",
                     rift.mode == "gr" ? "You left the party, so you left its Greater Rift and cannot re-enter it."
                                       : "You left the party, so you left its Nephalem Rift.");
        // Ported out AT ONCE if they were inside, rather than left to finish the
        // fight: 7.9.7 is explicit, and the bind has just stopped meaning
        // anything for them.
        // On any floor of the run, and bound to one map per floor.
        std::vector<Floor> floors;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            floors = live.Floors(rift.id);
        }
        bool inside = false;
        for (Floor const& floor : floors)
            if (left && left->GetMap() && left->GetMap()->GetInstanceId() == floor.instanceId &&
                left->GetMap()->GetId() == floor.mapId)
                inside = true;
        if (inside)
        {
            WorldLocation hub;
            if (DC::World::HubLocation(hub))
                ForcedTeleport(left, [&](Player* moved) { moved->TeleportTo(hub); });
        }
        for (Floor const& floor : floors)
            sInstanceSaveMgr->PlayerUnbindInstance(guid, floor.mapId, DUNGEON_DIFFICULTY_NORMAL, true, left);
    }
};
class RiftKeeper final : public CreatureScript
{
public:
    RiftKeeper() : CreatureScript("dc_rift_keeper") { }
    bool OnGossipHello(Player* player, Creature* creature) override
    {
        if (!DC::World::IsInHub(player) || player->IsInCombat())
        {
            ChatHandler(player->GetSession()).SendSysMessage("Speak to the Rift Keeper in the hub out of combat.");
            return true;
        }
        // 7.2: handled creature gossip stops the default menu, so the quest
        // entries have to be prepared explicitly beside our own item or the
        // turn-in would be invisible. Only the quest this player actually
        // holds is offered - the other variants are an internal detail.
        // While a member still has Urshi tries the turn-in is not offered (it would start the countdown),
        // and the line says who.
        Rift rift;
        if (EnrolledRun(player->GetGUID(), rift) && rift.questId)
            if (Quest const* quest = sObjectMgr->GetQuestTemplate(rift.questId))
                if (player->GetQuestStatus(rift.questId) == QUEST_STATUS_COMPLETE)
                {
                    std::string const held = UrshiBlocksClose(rift.id);
                    if (held.empty())
                        player->PlayerTalkClass->GetQuestMenu().AddMenuItem(quest->GetQuestId(), 4);
                    else
                        ChatHandler(player->GetSession()).SendSysMessage(held);
                }
        AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Close my rift", GOSSIP_SENDER_MAIN, 1);
        SendGossipMenuFor(player, 1, creature->GetGUID());
        return true;
    }
    bool OnGossipSelect(Player* player, Creature* creature, uint32 sender, uint32 action) override
    {
        ClearGossipMenuFor(player);
        CloseGossipMenuFor(player);
        if (sender != GOSSIP_SENDER_MAIN || action != 1 || creature->GetEntry() != RIFT_KEEPER_ENTRY ||
            !player->IsWithinDistInMap(creature, INTERACTION_DISTANCE)) return true;
        std::string error;
        if (!Close(player, error)) ChatHandler(player->GetSession()).SendSysMessage(error);
        return true;
    }
};

void RegisterQuestScripts()
{
    new RiftKeeper();
    new RiftPlayer();
    new RiftCharmKills();
    new RiftGroup();
}
}

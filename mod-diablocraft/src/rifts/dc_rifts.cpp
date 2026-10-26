#include "dc_rifts.h"
#include "dc_ally.h"
#include "dc_gr_level.h"
#include "../monsters/dc_family_lineup.h"
#include "dc_gr_open.h"
#include "../monsters/dc_monster_ai.h"
#include "../monsters/affixes/dc_affixes.h"
#include "dc_rift_exit.h"
#include "dc_rift_quests.h"
#include "dc_rift_spawner.h"
#include "dc_rifts_internal.h"
#include "dc_rifts_shared.h"
#include "dc_shatter.h"
#include "dc_open_rift.h"
#include "dc_town_portal.h"

#include "../combat/dc_combat.h"
#include "../difficulty/dc_difficulty.h"
#include "../loot/dc_loot.h"
#include "../paragon/dc_paragon.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_world.h"
#include "../common/dc_tunables.h"
#include "../classes/dc_classes.h"

#include "Chat.h"
#include "CombatAI.h"
#include "Creature.h"
#include "GameObjectAI.h"
#include "PassiveAI.h"
#include "ScriptedCreature.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "ThreatManager.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "GameTime.h"
#include "Group.h"
#include "InstanceSaveMgr.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "GridNotifiers.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "World.h"
#include "WorldSession.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cctype>
#include <cmath>
#include <functional>
#include <list>
#include <memory>
#include <mutex>
#include <random>
#include <sstream>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Rifts
{
    // Enough that the killer is the guardian's first victim, and small enough
    // that a party member who then out-threats it takes over normally.

    // One dc_rift_guardian ability: the shell the module casts for the animation and
    // school, and how it is fought.

    std::mutex dataMutex;
    // The dc_affix_tunables snapshot. Read through Numbers(), which hands out the
    // shared_ptr rather than the object, so `.dc affix reload` can swap in a new one
    // while a pack is mid-tick.
    std::shared_ptr<AffixNumbers const> affixNumbers;
    std::vector<Dungeon> pool;
    double championScale = 1.0, rareScale = 1.0, minionScale = 1.0;
    std::vector<Guardian> guardians;
    // dc_elite_affix_count, as (hero_level_max, affixes_per_pack) in level order.
    // 03 §5 elite look, tunables in dc_loot_tuning (loot_tuning.csv). A
    // missing column leaves every scale at 1.0, which is the pre-change look.
    // A champion pack is 3 identical champions in total,
    // the promoted spawn included, so it summons championPackSize - 1 companions.
    // A tunable in dc_loot_tuning; the default matches the CSV so a table
    // without the column behaves the same as one with it.
    bool dataReady = false;
    // The entrance-portal looks, in entry order, loaded from dc_rift_portal beside
    // the dungeon pool and guarded by the same mutex. Also held as a set of entries,
    // because the obelisk script's question is "is this gameobject one of ours".
    std::vector<PortalLook> portalPool;
    std::set<std::uint32_t> portalEntries;

    // The live runs by run id, and the floor each of their instances is (dc_rift_floor), so a kill can find its rift
    // from the instance it is in without a DB round trip. Every lookup goes through it (rift floors Part F1).
    std::mutex riftMutex;
    LiveRuns<Rift> live;
    // Scoped to the synchronous CreateMap call, not a shared pending map-id slot.
    // The before-instance-script hook publishes the row before any AI can summon.
    thread_local Rift* opening = nullptr;

    // The one Nephalem quest and the one Greater quest (7.3, S3). Read
    // from quest_template at startup rather than compiled in, so the ids stay in
    // rift_quests.csv and a regenerated rifts_0011 cannot disagree with the binary.
    // Guarded by dataMutex with the rest of the loaded data.
    // EVERY rift template, Greater included. Cleanup, the no-abandon rule and the
    // XP zeroing must recognise a Phase B quest that reached a log somehow; only
    // the offering path is Nephalem-only. Guarded by dataMutex with the rest.

    std::mutex workMutex;

    void StripNativeAbilities(Creature* creature);
    // The requested Keeper countdown; progress remains live until expiry.
    std::unordered_map<std::uint64_t, PendingClose> pendingCloses; // by run id, workMutex
    std::vector<Rift> closingRifts;
    std::set<std::uint32_t> resetWhenEmpty;
    std::unordered_map<std::uint32_t, std::vector<ObjectGuid>> riftMembers;
    void ClosePortals(std::uint64_t runId);

    std::unordered_map<std::uint64_t, Entrance> entrances; // run id -> its portal, workMutex
    void RemoveEntrance(std::uint64_t runId);

    std::vector<Opening> openings; // workMutex

    // --- who the hub objects belong to (7.9.8, per-party) ----------------------
    //
    // player -> the id of the run they are enrolled in. This is the HOT
    // path: `CanBeSeen` is called from the visibility notifier, so it must never
    // touch SQL. dc_rift_member stays the durable store and this is its cache; see
    // the comment on RiftMembership for the six places that write both.
    //
    // A player can be enrolled in at most one run - OpenRun refuses a second - so a
    // plain map rather than a set per run is the whole truth.
    std::unordered_map<ObjectGuid, std::uint64_t> playerRun; // workMutex

    thread_local Claim claiming;
    // Defined with the rest of the quest plumbing, far below; the guardian kill
    // path needs it and runs first.
    // 7.9.7: "later holders' quests are simply removed at closure." Same reason for
    // the forward declaration - QueueClose runs long before the quest plumbing.

    // Every queue is keyed by instance id, and a destroyed map's queued work dies
    // with it. Without this the vectors grow for the life of the process and each
    // map update partitions the whole global list.
    // Floor work only: what belongs to the run (its Keeper countdown, its entrance) is
    // dropped when the run goes, not when one of its floors does.
    void EraseInstanceWork(std::uint32_t instanceId)
    {
        std::lock_guard<std::mutex> lock(workMutex);
        auto drop = [&](auto& queue)
        {
            queue.erase(std::remove_if(queue.begin(), queue.end(),
                                       [&](auto const& entry) { return entry.instanceId == instanceId; }),
                        queue.end());
        };
        drop(promotions);
        drop(bursts);
        drop(zones);
        drop(closingRifts);
        riftMembers.erase(instanceId);
        resetWhenEmpty.erase(instanceId);
    }

    // 7.9.8: the per-seer answer, and the only thing that decides who sees a hub
    // object. `owningRun` and `owner` are what the object's AI was built with.
    //
    // NO SQL HERE, ever: the core calls this from WorldObject::CanSeeOrDetect
    // (Object.cpp:1839 for a gameobject, :1826 for a creature), which runs out of the
    // visibility notifier for every nearby player. dc_rift_member is the durable
    // store and `playerRun` is its in-memory cache.
    bool CanSeeHubObject(GameObject const* go, std::uint64_t owningRun, ObjectGuid owner, Player const* seer)
    {
        if (!seer)
            return true;
        // A `.dc shatter` preview object: its caster and nobody else.
        if (owner)
            return seer->GetGUID() == owner;

        std::lock_guard<std::mutex> lock(workMutex);
        auto enrolled = playerRun.find(seer->GetGUID());
        std::uint64_t const seerRun = enrolled == playerRun.end() ? 0 : enrolled->second;
        // A run-owned object - the rubble, the portal, the trigger stalker: its own
        // party and nobody else.
        if (owningRun)
            return seerRun == owningRun;

        // Otherwise this is the SHARED hub obelisk, which is the other way round: it
        // stands for everyone and is hidden only from a party whose own run has
        // replaced it with rubble. That is what lets a second party
        // still take the quest while the first party's rift is open.
        if (!seerRun || !go || !go->GetSpawnId())
            return true;
        auto entrance = entrances.find(seerRun);
        return entrance == entrances.end() || entrance->second.obeliskSpawnId != go->GetSpawnId();
    }

    HubObjectClaim::HubObjectClaim(std::uint64_t runId)
    {
        claiming.run = runId;
        claiming.owner.Clear();
    }

    HubObjectClaim::HubObjectClaim(Player const* onlyFor)
    {
        claiming.run = 0;
        claiming.owner = onlyFor ? onlyFor->GetGUID() : ObjectGuid::Empty;
    }

    HubObjectClaim::HubObjectClaim(ObjectGuid onlyFor)
    {
        claiming.run = 0;
        claiming.owner = onlyFor;
    }

    HubObjectClaim::~HubObjectClaim()
    {
        claiming = Claim{};
    }

    // 7.9.8: the obelisk is hidden from the running party and left STANDING for
    // everyone else. It is a `gameobject` row, so it is never deleted, never
    // re-created and never despawned either: only who can see it
    // changes. `Entrance::obeliskSpawnId` is what CanSeeHubObject reads, and it is
    // already set by the time this runs, so all that is left is to tell the players
    // in range to re-evaluate.
    //
    // Why not the phase mask, which the research offered as the alternative: the
    // hub's obelisk copies are registered in dc_area_source / dc_area_spawn, and
    // DC::Areas' OnBeforeWorldObjectSetPhaseMask rewrites any requested phase for a
    // registered spawn back to the phase that owns it, so SetPhaseMask on the hub
    // obelisk is a silent no-op. Phasing could not express this anyway: the TierPhase
    // hook in dc_difficulty.cpp sets combined = false, which makes the mask a scalar
    // needing exact equality, so there is no per-party bit space at all.
    void RefreshObelisk(std::uint32_t mapId, ObjectGuid guid)
    {
        if (!guid)
            return;
        if (Map* map = sMapMgr->FindMap(mapId, 0))
            if (GameObject* obelisk = map->GetGameObject(guid))
                obelisk->UpdateObjectVisibility();
    }

    // Both halves of a membership change, in the order that matters: the cache first,
    // then the re-evaluation, and NEVER holding workMutex across the second, because
    // UpdateObjectVisibility calls straight back into CanSeeHubObject, which takes it.
    void RefreshHubObjects(std::uint64_t runId)
    {
        Entrance entrance;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            auto found = entrances.find(runId);
            if (found == entrances.end())
                return;
            entrance = found->second;
        }
        Map* map = sMapMgr->FindMap(entrance.hubMapId, 0);
        if (!map)
            return;
        for (ObjectGuid guid : {entrance.obelisk, entrance.object, entrance.rubble})
            if (guid)
                if (GameObject* object = map->GetGameObject(guid))
                    object->UpdateObjectVisibility();
    }

    // --- RiftMembership: the cache of dc_rift_member, and its only writers --------
    //
    // dc_rift_member is the durable store; `playerRun` is a cache of it that exists
    // only because CanBeSeen must not run SQL. They cannot drift, because every
    // statement in the module that writes a member row's `state` is in this list and
    // each one calls its neighbour here from the SAME function:
    //
    //   EnrollMember()              -> JoinMembership   the creator, a joiner, a re-add
    //   DetachMember()              -> LeaveMembership  leave, kick, any single detach
    //   HandleLogout() solo/last    -> ClearMembership  a whole-run detach
    //   HandleLogout() in a party   -> nothing, ON PURPOSE. `offline` is not a leave:
    //                                  7.5 keeps them enrolled through the grace and
    //                                  makes the login sweep decide, so they stay in
    //                                  the cache. They are not in the world, so it
    //                                  shows nobody anything, and by the time they are
    //                                  back the sweep has ruled one way or the other.
    //   SweepOnLogin() keep         -> JoinMembership   restored inside the grace
    //   SweepOnLogin() missed       -> LeaveMembership  the run finished without them
    //   SweepOnLogin() grace out    -> LeaveMembership
    //   RemoveRunQuests()           -> ClearMembership  closure, the whole run at once
    //   RiftWorld::OnStartup bulk   -> nothing needed: this cache is in memory, so a
    //                                  fresh process starts with it already empty
    //
    // `grep -n "dc_rift_member" mod-diablocraft/src | grep -iE "INSERT|UPDATE|DELETE"`
    // is the check that the list is still complete.
    void JoinMembership(std::uint64_t runId, ObjectGuid player)
    {
        if (!runId || !player)
            return;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            playerRun[player] = runId;
        }
        RefreshHubObjects(runId);
    }

    // `runId` is a GUARD, not the lookup: pass it when the caller knows which run
    // the detach is from, and 0 when it does not. The run that is actually refreshed
    // is always the one the cache had, so a caller with no run id still gets the
    // departing player's view corrected.
    void LeaveMembership(std::uint64_t runId, ObjectGuid player)
    {
        if (!player)
            return;
        std::uint64_t left = 0;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            auto found = playerRun.find(player);
            if (found == playerRun.end())
                return;
            // A player who has already joined a NEWER run must not be evicted from it
            // by a late detach from the old one.
            if (runId && found->second != runId)
                return;
            left = found->second;
            playerRun.erase(found);
        }
        RefreshHubObjects(left);
    }

    void ClearMembership(std::uint64_t runId)
    {
        if (!runId)
            return;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            for (auto it = playerRun.begin(); it != playerRun.end();)
                it = it->second == runId ? playerRun.erase(it) : std::next(it);
        }
        RefreshHubObjects(runId);
    }

    // The hub objects outlive their instance's map, so they are removed by their own
    // map, not by EraseInstanceWork. Safe to call for a run that never had one, and
    // safe to call twice.
    void RemoveEntrance(std::uint64_t runId)
    {
        Entrance entrance;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            auto found = entrances.find(runId);
            if (found == entrances.end())
                return;
            entrance = found->second;
            entrances.erase(found);
            // A run that closes inside its first second still has steps queued.
            openings.erase(std::remove_if(openings.begin(), openings.end(),
                                          [&](Opening const& opening) { return opening.runId == runId; }),
                           openings.end());
            // Nobody is in this run any more, so nothing of its is anybody's.
            for (auto it = playerRun.begin(); it != playerRun.end();)
                it = it->second == runId ? playerRun.erase(it) : std::next(it);
        }
        // The obelisk first, and outside the lock: erasing the entrance above is what
        // un-hides it - CanSeeHubObject can no longer find a run that owns this spawn
        // id - and this is the players in range being told to look again. It must not
        // be skipped by an early return for a portal that was never placed.
        RefreshObelisk(entrance.hubMapId, entrance.obelisk);

        WorldLocation hub;
        std::uint32_t const mapId = entrance.hubMapId                         ? entrance.hubMapId
                                    : DC::World::HubPoint("town_portal", hub) ? hub.GetMapId()
                                                                              : 0;
        if (!mapId)
            return;
        Map* map = sMapMgr->FindMap(mapId, 0);
        if (!map)
            return;
        for (ObjectGuid guid : {entrance.object, entrance.rubble})
            if (guid)
                if (GameObject* object = map->GetGameObject(guid))
                    object->Delete();
    }

    bool OwnedRift(Player const* player, Rift& result)
    {
        if (!player)
            return false;
        std::lock_guard<std::mutex> lock(riftMutex);
        bool owned = false;
        live.Each(
            [&](Rift const& rift)
            {
                if (!owned && rift.leaderGuid == player->GetGUID().GetRawValue() && rift.state != "closed")
                {
                    result = rift;
                    owned = true;
                }
            });
        return owned;
    }

    std::mt19937_64& Engine()
    {
        static thread_local std::mt19937_64 engine{std::random_device{}()};
        return engine;
    }

    double Roll()
    {
        return std::uniform_real_distribution<double>(0.0, 1.0)(Engine());
    }

    // Every playable D3 class opens rifts and knows the town portal. "Playable"
    // is a dc_class_map row (class_map.csv), the same one gate stats and hits
    // use, so no class is named here. A class with
    // no row is refused and named once in the log, never treated as a Barbarian.
    bool PlayableClass(Player const* player)
    {
        if (!player)
            return false;
        if (DC::Classes::Playable(player))
            return true;
        static std::mutex namedMutex;
        static std::set<unsigned> named;
        unsigned const wowClass = player->getClass();
        std::lock_guard<std::mutex> lock(namedMutex);
        if (named.insert(wowClass).second)
            LOG_WARN("server", "[DC rifts] WoW class {} has no dc_class_map row; rifts and the town portal "
                               "are refused for it", wowClass);
        return false;
    }

    // A dead player could be force-teleported. A corpse and its
    // ghost are on the map the player is leaving, so a forced move strands the
    // release point and, in hardcore, moves a body the player never chose to move.
    // mod-dungeon-master resurrects for the same reason, so every forced teleport in
    // this file goes through here rather than calling TeleportTo directly.
    //
    // Full Life and no resurrection sickness: the player did not choose to die here
    // and is not choosing to run back, so there is nothing to penalise. The corpse
    // bones are spawned so the world does not keep an orphaned corpse behind.
    void ForcedTeleport(Player* player, std::function<void(Player*)> const& move)
    {
        if (!player)
            return;
        if (!player->IsAlive())
        {
            player->ResurrectPlayer(1.0f);
            player->SpawnCorpseBones();
        }
        move(player);
    }

    void Announce(Rift const& rift, std::string const& text)
    {
        // Everyone standing in the rift hears it, on any floor, which is the whole
        // party by definition: the instances hold nobody else. A run that is not (or
        // no longer) in the book falls back to the one map the copy names.
        std::vector<Floor> floors;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            floors = live.Floors(rift.id);
        }
        if (floors.empty())
            floors.push_back(Floor{rift.id, rift.floor, rift.instanceId, rift.mapId, rift.dungeonId});
        for (Floor const& floor : floors)
        {
            Map* map = sMapMgr->FindMap(floor.mapId, floor.instanceId);
            if (!map)
                continue;
            map->DoForAllPlayers(
                [&](Player* player)
                {
                    if (player && player->GetSession())
                        ChatHandler(player->GetSession()).SendSysMessage(text);
                });
        }
    }

    void Persist(Rift const& rift)
    {
        CharacterDatabase.Execute("UPDATE dc_rift SET kills={}, progress={}, state='{}' WHERE id={}", rift.kills,
                                  rift.progress, rift.state, rift.id);
    }

    // --- enrollment (7.9.7, dc_rift_member) ------------------------------------
    //
    // The association is persisted because an in-memory quest id cannot tell two
    // runs apart that reuse the same template (7.6), and because the login sweep
    // has to answer "does this character still belong to a live run" for a player
    // who was offline when it ended.

    // A state change has to be on disk before anything reads it back. The AIO rift
    // bar is Lua and reads dc_rift directly, and it is pushed from the same kill
    // that changes the state, so an async write here is a race the bar loses: it
    // reports "Kill the guardian" off a row that is about to say complete. Kill
    // counting keeps the async path; only the three transitions are synchronous.
    void PersistNow(Rift const& rift)
    {
        CharacterDatabase.DirectExecute("UPDATE dc_rift SET kills={}, state='{}' WHERE id={}", rift.kills, rift.state,
                                        rift.id);
    }

    void QueueClose(Rift rift)
    {
        std::vector<Rift> floors;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            Rift* run = live.Find(rift.id);
            if (!run || run->state == "closed")
                return;
            run->state = "closed"; // Preserve kills/guardian progress earned during countdown.
            rift = *run;
            floors = live.Views(rift.id);
        }
        PersistNow(rift);
        RemoveRunQuests(rift);
        ClosePortals(rift.id);
        // Every floor closes on its own map's update, so each one is queued as the run seen from it.
        std::lock_guard<std::mutex> lock(workMutex);
        pendingCloses.erase(rift.id);
        closingRifts.insert(closingRifts.end(), floors.begin(), floors.end());
    }

    // The run the player's map is a floor of, seen from that floor, while it is not closed.
    bool Current(Player const* player, Rift& rift)
    {
        if (!player || !player->GetMap() || !player->GetMap()->IsDungeon())
            return false;
        std::lock_guard<std::mutex> lock(riftMutex);
        Rift seen;
        if (!live.View(player->GetMap()->GetInstanceId(), 0, seen) || seen.state == "closed")
            return false;
        rift = seen;
        return true;
    }

    // The arrival point of the floor the player stands on: that floor's dungeon entry from dc_rift_dungeon,
    // which is where its party was sent in the first place. False when the player is not in a live rift.
    bool EntryPosition(Player const* player, WorldLocation& entry)
    {
        Rift rift;
        if (!Current(player, rift))
            return false;
        std::lock_guard<std::mutex> lock(dataMutex);
        for (Dungeon const& dungeon : pool)
            if (dungeon.dungeonId == rift.dungeonId)
            {
                entry = WorldLocation(dungeon.mapId, dungeon.x, dungeon.y, dungeon.z, dungeon.o);
                return true;
            }
        return false;
    }

    bool ScalingContext(Map const* map, unsigned& tier, unsigned& players)
    {
        if (!map || !map->IsDungeon() || !map->GetInstanceId())
            return false;
        std::lock_guard<std::mutex> lock(riftMutex);
        Rift const* run = live.FindByInstance(map->GetInstanceId(), map->GetId());
        if (!run)
            return false;
        tier = run->tier;
        players = run->players;
        return true;
    }

    unsigned GreaterRiftLevel(Map const* map)
    {
        if (!map || !map->IsDungeon() || !map->GetInstanceId())
            return 0;
        std::lock_guard<std::mutex> lock(riftMutex);
        Rift const* run = live.FindByInstance(map->GetInstanceId(), map->GetId());
        if (!run || run->mode != "gr")
            return 0;
        return run->grRank;
    }

    bool IsLiveInstance(std::uint32_t mapId, std::uint32_t instanceId)
    {
        std::lock_guard<std::mutex> lock(riftMutex);
        Rift const* run = live.FindByInstance(instanceId, mapId);
        return run && run->state != "closed";
    }

    bool OutsiderInRift(Player const* player)
    {
        std::uint64_t run = 0;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            Rift const* here = live.FindByInstance(player->GetInstanceId(), player->GetMapId());
            if (!here || here->state == "closed")
                return false;
            run = here->id;
        }
        std::lock_guard<std::mutex> lock(workMutex);
        auto found = playerRun.find(player->GetGUID());
        return found == playerRun.end() || found->second != run;
    }

    bool InRift(Creature const* creature, unsigned& tier)
    {
        unsigned players = 0;
        return creature && ScalingContext(creature->GetMap(), tier, players);
    }

    bool IsPromotedElite(Creature const* creature)
    {
        if (!creature)
            return false;
        EliteState const* state = creature->CustomData.Get<EliteState>("DCRiftElite");
        // A pack member carries the pack's affixes but is still a normal kill for
        // loot, exactly as it was before members carried anything.
        return state != nullptr && !state->member;
    }

    bool IsElitePack(Creature const* creature)
    {
        return creature && creature->CustomData.Get<EliteState>("DCRiftElite") != nullptr;
    }

    std::vector<PortalLook> PortalPool()
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        return portalPool;
    }

    // One look out of the seventeen, uniformly, per rift. Returns
    // a zero entry when the pool did not load, and every caller treats that as "no
    // portal" rather than falling back to a hard-coded entry: a silent fallback is
    // how the retired 910014 would come back from the dead.
    PortalLook RollPortal()
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        if (portalPool.empty())
            return {};
        return portalPool[std::uniform_int_distribution<std::size_t>(0, portalPool.size() - 1)(Engine())];
    }

    bool IsEntrancePortal(std::uint32_t entry)
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        return portalEntries.count(entry) != 0;
    }

    bool IsExitPortal(std::uint32_t entry)
    {
        std::uint32_t const look = Exit::LookOf(entry);
        return look && IsEntrancePortal(look);
    }

    bool IsIllusion(Creature const* creature)
    {
        return creature && creature->CustomData.Get<IllusionState>("DCRiftIllusion") != nullptr;
    }

    // One transient hub gameobject in one phase: the rubble, and the portal. Both are
    // summoned rather than spawned, so neither is ever written to the `gameobject`
    // table and neither survives a restart. The template carries its own scale, which
    // is why rift_portals.csv's scale column is a data change and not a code change.
    GameObject* PlaceHubObject(Map* map, std::uint64_t runId, std::uint32_t entry, float x, float y, float z,
                               float o, std::uint32_t phase)
    {
        if (!map || !entry)
            return nullptr;
        // Claimed across the summon, not after it: SummonGameObject creates the object
        // AND adds it to the map, and the map add is when the create packet goes out.
        // An object claimed afterwards would be seen by everyone for one tick and then
        // yanked, which is a visible flicker for a party that should never have seen it.
        HubObjectClaim claim(runId);
        GameObject* object = map->SummonGameObject(entry, x, y, z, o, 0, 0, std::sin(o / 2), std::cos(o / 2), 0);
        if (!object)
            return nullptr;
        // The hub draws a tier per phase, so a hub object has to sit in the phase its
        // party can see, exactly as the town portal's hub half does. Unlike the
        // display id, a phase change after the map add is honoured by the client,
        // because phase is a server-side visibility test rather than something the
        // create packet bakes in.
        object->SetPhaseMask(phase, true);
        return object;
    }

} // namespace DC::Rifts

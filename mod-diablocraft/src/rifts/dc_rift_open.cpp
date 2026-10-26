// World of DiabloCraft - a rift's opening: the obelisk, the entrance, the floors, the close and the headcount.

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
    // t = 0 of 7.9.8: the dust. obelisk-shatter.md 5.2 - the client will not draw a
    // particle effect at bare coordinates, so an invisible stalker stands where the
    // obelisk stood and casts the spell on itself. Never cast by a player and never
    // at one; the stalker is made friendly first so no area effect in the spell has a
    // player to pick.
    void Detonate(Map* map, std::uint64_t runId, float x, float y, float z, float o, std::uint32_t phase)
    {
        if (!map)
            return;
        // Claimed the same way and for a stronger reason than the gameobjects: the
        // explosion is only private because the CASTER is. SMSG_SPELL_GO goes to the
        // players who already hold the caster, so the stalker has to be party-only
        // from its first create packet or the whole hub sees the dust.
        Creature* trigger = nullptr;
        {
            HubObjectClaim claim(runId);
            trigger = map->SummonCreature(OPEN_TRIGGER_ENTRY, Position(x, y, z, o), nullptr, OPEN_TRIGGER_MS);
        }
        if (!trigger)
        {
            LOG_ERROR("server",
                      "[DC rifts] the shatter trigger {} could not be summoned in the hub; "
                      "the obelisk still hides but there is no explosion",
                      OPEN_TRIGGER_ENTRY);
            return;
        }
        trigger->SetDisplayId(OPEN_TRIGGER_DISPLAY);
        trigger->SetObjectScale(0.01f);
        trigger->SetFaction(OPEN_TRIGGER_FACTION);
        trigger->SetImmuneToAll(true);
        trigger->SetPhaseMask(phase, true);
        trigger->CastSpell(trigger, OPEN_SPELL, true);
    }

    // 7.9.7: one portal per party, run-owned, beside the obelisk, party-only, for the
    // whole run lifetime. 7.9.8 moved it onto the obelisk's OWN position rather than
    // the creator's feet, because the portal now rises out of the rubble the obelisk
    // left. The accepter's position is only the fallback for a caller that is not
    // standing at an obelisk, which is the `.dc rift open` harness.
    void OpenEntrance(Rift const& rift, Player* player, Dungeon const& dungeon)
    {
        if (!player || !player->GetMap())
            return;
        Entrance entrance;
        entrance.instanceId = rift.instanceId;
        entrance.mapId = dungeon.mapId;
        entrance.x = dungeon.x;
        entrance.y = dungeon.y;
        entrance.z = dungeon.z;
        entrance.o = dungeon.o;
        entrance.phase = player->GetPhaseMask();
        entrance.hubMapId = player->GetMapId();

        PortalLook const look = RollPortal();
        if (!look.entry)
        {
            ChatHandler(player->GetSession())
                .SendSysMessage("The rift opened, but its portal pool is not loaded; see the startup log.");
            return;
        }
        entrance.portalEntry = look.entry;

        // FindNearestGameObject compares phases. The Sanctum has one obelisk in its one
        // shared phase and the accepter stands in that phase, so this finds it.
        GameObject* obelisk = player->FindNearestGameObject(OBELISK_ENTRY, OBELISK_SEARCH_YARDS);
        if (obelisk)
        {
            entrance.ox = obelisk->GetPositionX();
            entrance.oy = obelisk->GetPositionY();
            entrance.oz = obelisk->GetPositionZ();
            entrance.oo = obelisk->GetOrientation();
            entrance.obelisk = obelisk->GetGUID();
            entrance.obeliskSpawnId = obelisk->GetSpawnId();
        }
        else
        {
            // No obelisk in range: `.dc rift open` from anywhere, or a hub whose
            // obelisk is missing. Play the sequence two yards in front of the caller
            // instead of refusing the run, and leave nothing to un-hide.
            float const angle = player->GetOrientation();
            entrance.ox = player->GetPositionX() + 2.0f * std::cos(angle);
            entrance.oy = player->GetPositionY() + 2.0f * std::sin(angle);
            entrance.oz = player->GetPositionZ();
            entrance.oo = angle;
            LOG_INFO("server",
                     "[DC rifts] rift {} found no obelisk {} within {} yards of {}; the opening "
                     "sequence plays in front of them and no obelisk is hidden",
                     rift.id, OBELISK_ENTRY, OBELISK_SEARCH_YARDS, player->GetName());
        }

        Opening opening;
        opening.runId = rift.id;
        opening.hubMapId = entrance.hubMapId;
        opening.phase = entrance.phase;
        opening.portalEntry = look.entry;
        opening.x = entrance.ox;
        opening.y = entrance.oy;
        opening.z = entrance.oz;
        opening.o = entrance.oo;
        opening.notify = player->GetGUID();

        // The entrance row goes in BEFORE the obelisk is hidden, never the other way
        // round: that row is what CanSeeHubObject reads to answer "is this obelisk
        // hidden from this seer", so hiding first would be a refresh with nothing
        // behind it.
        {
            std::lock_guard<std::mutex> lock(workMutex);
            entrances[rift.id] = entrance;
            openings.push_back(opening);
        }

        // The creator is already enrolled by OpenRun, so the party is in `playerRun`
        // and both of the next two lines have someone to be private to.
        //
        // t = 0: the dust, and the obelisk leaving under it, in one step. The obelisk
        // is not despawned - it keeps standing for everyone who is not in this run -
        // so this is only the players in range being told to look at it again.
        Detonate(player->GetMap(), rift.id, entrance.ox, entrance.oy, entrance.oz, entrance.oo, entrance.phase);
        if (obelisk)
            obelisk->UpdateObjectVisibility();
    }

    // The +200 ms and +800 ms steps, drained on the hub map's own update so the
    // objects are built on the thread that owns them. Called for every non-instance
    // map; an opening only advances on the map it was queued for.
    void DrainOpenings(Map* map, std::uint32_t diff)
    {
        struct Step
        {
            std::uint64_t runId = 0;
            std::uint32_t entry = 0, phase = 1;
            float x = 0.0f, y = 0.0f, z = 0.0f, o = 0.0f;
            bool portal = false;
            ObjectGuid notify;
        };
        std::vector<Step> due;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            for (auto it = openings.begin(); it != openings.end();)
            {
                if (it->hubMapId != map->GetId())
                {
                    ++it;
                    continue;
                }
                it->elapsed += diff;
                if (!it->rubbleDone && it->elapsed >= OpenRubbleMs())
                {
                    it->rubbleDone = true;
                    due.push_back(
                        {it->runId, OPEN_RUBBLE, it->phase, it->x, it->y, it->z, it->o, false, it->notify});
                }
                if (!it->portalDone && it->elapsed >= OpenPortalMs())
                {
                    it->portalDone = true;
                    due.push_back({it->runId, it->portalEntry, it->phase, it->x, it->y, it->z + OPEN_PORTAL_Z,
                                   it->o, true, it->notify});
                }
                if (it->rubbleDone && it->portalDone)
                    it = openings.erase(it);
                else
                    ++it;
            }
        }

        for (Step const& step : due)
        {
            GameObject* object =
                PlaceHubObject(map, step.runId, step.entry, step.x, step.y, step.z, step.o, step.phase);
            {
                std::lock_guard<std::mutex> lock(workMutex);
                auto found = entrances.find(step.runId);
                // The run closed between the queue and this tick. Nothing owns the
                // object now, so it goes straight back out rather than standing in the
                // hub for the rest of the session.
                if (found == entrances.end())
                {
                    if (object)
                        object->Delete();
                    continue;
                }
                if (object)
                {
                    if (step.portal)
                        found->second.object = object->GetGUID();
                    else
                        found->second.rubble = object->GetGUID();
                }
            }
            if (object || !step.portal)
                continue;
            // The portal is the only step whose failure strands the party, so it is
            // the only one that speaks up. The run is real and already recorded.
            if (Player* accepter = ObjectAccessor::FindConnectedPlayer(step.notify))
                if (accepter->GetSession())
                    ChatHandler(accepter->GetSession())
                        .SendSysMessage("The rift opened, but its portal could not. Ask the Rift Keeper to "
                                        "close it and open another.");
        }
    }

    // There is no hidden-obelisk sweep any more, and there is nothing for one to do:
    // the obelisk is never despawned, so the only thing that can hide it is a live
    // entrance row naming its spawn id, and erasing that row IS the un-hide. A run
    // whose row is gone cannot leave the hub stranded, and a process that dies
    // mid-rift leaves no trace at all, because none of this is written down.

    // The run-creation primitive. `reserved` is the dungeon and variant already held
    // for this player at the obelisk; without one it rolls its own, which is what
    // the `.dc rift open` harness wants.
    // Defined below, beside the headcount code that is its other caller.
    unsigned PartyCap();

    // The member is bound to the floor's instance, and remembered for the closure's unbinding. False when the instance is
    // gone. A bind is what puts them in the SAME instance rather than a second copy of the dungeon.
    bool BindToFloor(Player* player, Floor const& floor)
    {
        auto* bind = sInstanceSaveMgr->PlayerGetBoundInstance(player->GetGUID(), floor.mapId, DUNGEON_DIFFICULTY_NORMAL);
        if (!bind || !bind->save || bind->save->GetInstanceId() != floor.instanceId)
        {
            InstanceSave* save = sInstanceSaveMgr->GetInstanceSave(floor.instanceId);
            if (!save)
                return false;
            sInstanceSaveMgr->PlayerBindToInstance(player->GetGUID(), save, false, player);
        }
        std::lock_guard<std::mutex> lock(workMutex);
        std::vector<ObjectGuid>& members = riftMembers[floor.instanceId];
        if (std::find(members.begin(), members.end(), player->GetGUID()) == members.end())
            members.push_back(player->GetGUID());
        return true;
    }

    bool ArrivalOf(std::uint32_t dungeonId, Dungeon& out)
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        for (Dungeon const& dungeon : pool)
            if (dungeon.dungeonId == dungeonId)
            {
                out = dungeon;
                return true;
            }
        return false;
    }

    bool OpenRun(Player* player, Reservation const* reserved, Rift* created, std::string& error,
                 GreaterStart const* greater)
    {
        if (!PlayableClass(player))
        {
            error = "Your class cannot open a rift yet.";
            return false;
        }
        Rift existing;
        if (Current(player, existing))
        {
            error = "You are already in a rift.";
            return false;
        }
        if (!DC::World::IsInHub(player) || player->IsInCombat())
        {
            error = "Open a rift from the hub while out of combat.";
            return false;
        }
        // 7.9.7 removed the leader-only rule: whoever FIRST takes the quest at the
        // obelisk creates the run, and party leadership is irrelevant. What is
        // still refused is a SECOND run for a party that already has one - the
        // others join through the existing one, they do not open another.
        if (PartyRun(player, existing))
        {
            error = "Your party already has a rift open. Take its quest at the obelisk and use the portal.";
            return false;
        }

        // Check before CreateMap publishes the new run and before changing binds.
        if (OwnedRift(player, existing))
        {
            error = "Speak to the Rift Keeper to close your current rift before opening another.";
            return false;
        }

        Dungeon dungeon;
        std::uint32_t questId = 0;
        if (reserved)
        {
            // 7.2: the variant was reserved before the quest was offered and is
            // never rerolled afterwards, or the player would accept one count and
            // play another.
            dungeon = reserved->dungeon;
            questId = reserved->questId;
        }
        else
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            if (!dataReady || pool.empty())
            {
                error = "The rift pool is not loaded; see the startup log.";
                return false;
            }
            dungeon = pool[std::uniform_int_distribution<std::size_t>(0, pool.size() - 1)(Engine())];
            // A Greater Rift's quest is the timed one; it has to exist, or the run would start with
            // nobody holding a quest to carry the clock.
            BarQuest const& bar = greater ? greaterQuest : nephalemQuest;
            if (bar.id)
                questId = bar.id;
            else if (greater)
            {
                error = "That rift has no Greater Rift quest; see the startup log.";
                return false;
            }
        }

        // Every rift is a fresh instance, so any save for this map is dropped first;
        // otherwise the player walks back into the last run of the same dungeon.
        //
        // 7.9.7 as corrected: the party is BOUND here and NOBODY is
        // moved. Everyone, the accepter included, walks through the obelisk portal,
        // which is what makes the bind matter - an unbound member would land in a
        // second instance of the same dungeon.
        std::vector<Player*> party;
        if (greater)
            party = greater->roster; // the ready check closed it; a late joiner is not on it
        else if (Group* group = player->GetGroup())
        {
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
                if (Player* member = itr->GetSource())
                    if (member->IsInWorld() && member->GetMap() == player->GetMap())
                        party.push_back(member);
        }
        else
            party.push_back(player);

        // Audit row 88: the cap is party_scaling.csv's row count, read through
        // PartyCap(), not a literal 4 repeated here.
        if (party.empty() || party.size() > PartyCap())
        {
            error = std::string(greater ? "Greater" : "Nephalem") + " Rifts support one to " +
                    std::to_string(PartyCap()) + " players.";
            return false;
        }

        for (Player* member : party)
            sInstanceSaveMgr->PlayerUnbindInstance(member->GetGUID(), dungeon.mapId, DUNGEON_DIFFICULTY_NORMAL, true,
                                                   member);

        unsigned const tier = DC::Difficulty::CurrentTier(player);
        Rift rift;
        rift.mapId = dungeon.mapId;
        rift.dungeonId = dungeon.dungeonId;
        rift.leaderGuid = player->GetGUID().GetRawValue();
        rift.tier = tier;
        rift.players = static_cast<unsigned>(party.size());
        {
            // S3: the bar is the quest's own count, the same for every dungeon.
            std::lock_guard<std::mutex> lock(dataMutex);
            rift.requiredUnits = (greater ? greaterQuest : nephalemQuest).units;
        }
        rift.questId = questId;
        rift.mode = greater ? "gr" : "nr";
        rift.grRank = greater ? greater->level : 0;

        Map* map = nullptr;
        {
            struct OpeningScope
            {
                explicit OpeningScope(Rift& value)
                {
                    opening = &value;
                }
                ~OpeningScope()
                {
                    opening = nullptr;
                }
            } scope(rift);
            map = sMapMgr->CreateMap(dungeon.mapId, player);
        }
        if (!map || !rift.id || map->GetInstanceId() != rift.instanceId)
        {
            error = "Could not create a fresh, recorded rift instance.";
            return false;
        }
        InstanceSave* save = sInstanceSaveMgr->GetInstanceSave(rift.instanceId);
        if (!save)
        {
            error = "Could not bind the rift instance.";
            return false;
        }
        // Bind before teleport acknowledgements; every party member uses this same
        // instance and its already-published scaling context from the first spawn.
        for (Player* member : party)
            sInstanceSaveMgr->PlayerBindToInstance(member->GetGUID(), save, false, member);
        {
            std::lock_guard<std::mutex> lock(workMutex);
            for (Player* member : party)
                riftMembers[rift.instanceId].push_back(member->GetGUID());
        }

        // The creator is enrolled here; the rest are enrolled as they accept.
        EnrollMember(rift, player->GetGUID());
        if (greater)
        {
            // 7.9.2 item 4: the quest goes to every member of the closed roster, the shared
            // deadline starts at quest begin (the quest's own TimeAllowed, the CSV's 15:00), and
            // only then does the whole roster go in together. No obelisk entrance: nobody is
            // admitted after the start, so there is nothing for a portal to serve.
            if (Quest const* quest = sObjectMgr->GetQuestTemplate(rift.questId))
                rift.deadline = GameTime::GetGameTime().count() + quest->GetTimeAllowed();
            CharacterDatabase.DirectExecute("UPDATE dc_rift SET deadline=FROM_UNIXTIME({}) WHERE id={}", rift.deadline,
                                            rift.id);
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                live.Store(rift);
            }
            for (Player* member : party)
                GiveRunQuest(rift, member, nullptr);
            for (Player* member : party)
                ForcedTeleport(member,
                               [&](Player* moved)
                               { moved->TeleportTo(dungeon.mapId, dungeon.x, dungeon.y, dungeon.z, dungeon.o); });
        }
        else
            OpenEntrance(rift, player, dungeon);

        // No teleport here, deliberately (superseding 7.9.7 rule
        // 1's "the only person to be teleported into the rift should be who started
        // it"). NOBODY is auto-teleported into a Nephalem Rift: the accepter stays
        // in the hub, watches the obelisk break apart and clicks the portal like
        // everyone else. Auto-teleport belongs only to Greater Rifts, where 7.9.2
        // moves the whole roster together after the unanimous ready check, and that
        // path is Phase B's rather than this function's.

        if (created)
            *created = rift;
        LOG_INFO("server.loading",
                 "[DC rifts] {} opened {} {} (rift {}, instance {}, map {}, tier {}, players {}, "
                 "bar {} hundredths of a point, quest {})",
                 player->GetName(), greater ? "Greater Rift " + std::to_string(greater->level) + " in" : "", dungeon.name,
                 rift.id, rift.instanceId, dungeon.mapId, tier, rift.players,
                 rift.requiredUnits, rift.questId);
        return true;
    }

    bool Open(Player* player, std::string& error)
    {
        return OpenRun(player, nullptr, nullptr, error);
    }

    // Rift floors Part F2 (4.3): the run's next floor, made for the member who used the exit below it. The steps are OpenRun's:
    // unbind the member from the dungeon's map so the core makes a fresh instance, create it inside the scope the hook reads
    // (which records a floor, not a new run), bind the member. The caller teleports. Followers bind on use (BindToFloor).
    bool OpenNextFloor(Player* player, Rift const& from, Dungeon const& dungeon, Floor& made, std::string& error)
    {
        sInstanceSaveMgr->PlayerUnbindInstance(player->GetGUID(), dungeon.mapId, DUNGEON_DIFFICULTY_NORMAL, true, player);
        Rift next;
        next.id = from.id;
        next.mapId = dungeon.mapId;
        next.dungeonId = dungeon.dungeonId;
        Map* map = nullptr;
        {
            // What the before-instance-script hook reads while CreateMap makes the map: a Rift that names its run (id set) is a
            // later floor of it, not a new run.
            struct FloorScope
            {
                explicit FloorScope(Rift& value)
                {
                    opening = &value;
                }
                ~FloorScope()
                {
                    opening = nullptr;
                }
            } scope(next);
            map = sMapMgr->CreateMap(dungeon.mapId, player);
        }
        if (!map || !next.floor || map->GetInstanceId() != next.instanceId)
        {
            error = "Could not create the next floor.";
            return false;
        }
        made = Floor{from.id, next.floor, next.instanceId, next.mapId, next.dungeonId};
        if (!BindToFloor(player, made))
        {
            error = "Could not bind the next floor.";
            return false;
        }
        LOG_INFO("server.loading", "[DC rifts] run {} opened floor {} ({}, instance {}, map {}) for {}", from.id, made.number,
                 dungeon.name, made.instanceId, made.mapId, player->GetName());
        return true;
    }

    bool Close(Player* player, std::string& error)
    {
        Rift rift;
        if (!DC::World::IsInHub(player) || player->IsInCombat())
        {
            error = "Use the town portal, then speak to the Rift Keeper in the hub out of combat.";
            return false;
        }
        if (!OwnedRift(player, rift))
        {
            error = "You do not own an open rift. Only its owner can close it.";
            return false;
        }
        // A member who still has Urshi tries holds the rift open.
        error = UrshiBlocksClose(rift.id);
        if (!error.empty())
            return false;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            if (!pendingCloses.emplace(rift.id, PendingClose{rift, getMSTime()}).second)
            {
                error = "Your rift is already counting down to closure. The timer has not restarted.";
                return false;
            }
        }
        ChatHandler(player->GetSession())
            .SendSysMessage("Your rift will close in 30 seconds. Anyone still inside will return to the hub.");
        return true;
    }

    // --- elite packs (09 §2 step 2) --------------------------------------------

    // The affix line the AIO nameplate overlay draws. dc_rift_elite is the only
    // channel the Lua side has into a promotion: the pack lives on the map, and the
    // module owns it in C++ (00 §5), so what the client is allowed to know is
    // written out here and pushed by lua/aio/dc_elite.lua.
    std::string Escape(std::string value)
    {
        CharacterDatabase.EscapeString(value);
        return value;
    }

    // Defined below with the rest of the affix helpers; Promote needs them first.

    // Remove every caster's portal pair when its source rift closes: one pair set per floor.
    void ClosePortals(std::uint64_t runId)
    {
        std::vector<Floor> floors;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            floors = live.Floors(runId);
        }
        for (Floor const& floor : floors)
            TownPortal::CloseInstance(floor.instanceId);
        // 7.9.1 item 5: the entrance stays up through the guardian and the closing
        // countdown, and goes at ACTUAL closure. This is that moment - QueueClose
        // and the run's last map destruction are the only callers.
        RemoveEntrance(runId);
    }

    // The party-only entrance portal. Everything it refuses, it refuses out loud:
    // a silent portal is indistinguishable from a broken one.
    void UseEntrance(Player* player, GameObject* go)
    {
        ChatHandler handler(player->GetSession());
        std::uint64_t runId = 0;
        {
            std::lock_guard<std::mutex> lock(workMutex);
            bool found = false;
            for (auto const& [id, value] : entrances)
                if (value.object == go->GetGUID())
                {
                    runId = id;
                    found = true;
                    break;
                }
            if (!found)
            {
                handler.SendSysMessage("That rift has closed.");
                return;
            }
        }
        // 6.8: the obelisk always leads to floor 1. A floor nobody stood on for Instance.UnloadDelay is gone, and then the
        // lowest floor still standing takes its place; the portal says so.
        std::vector<Floor> floors;
        bool closed = true;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            if (Rift const* run = live.Find(runId))
                closed = run->state == "closed";
            floors = live.Floors(runId);
        }
        std::vector<unsigned> standing;
        for (Floor const& floor : floors)
            standing.push_back(floor.number);
        unsigned const number = closed ? 0 : Exit::ObeliskFloor(standing);
        if (!number)
        {
            handler.SendSysMessage("That rift has closed.");
            return;
        }
        Floor target;
        for (Floor const& floor : floors)
            if (floor.number == number)
                target = floor;
        Dungeon arrival;
        if (!ArrivalOf(target.dungeonId, arrival))
        {
            handler.SendSysMessage("That rift has closed.");
            return;
        }
        // 7.9.7: party-only. Enrollment is the test, not proximity - a member who
        // took the quest and walked to town is still enrolled and may walk back.
        Rift rift;
        if (!EnrolledRun(player->GetGUID(), rift) || rift.id != runId)
        {
            handler.SendSysMessage("That portal belongs to another party. Take the rift quest at the obelisk.");
            return;
        }
        if (player->IsInCombat() || !player->IsAlive())
        {
            handler.SendSysMessage("Use the rift portal out of combat, and alive.");
            return;
        }
        if (!BindToFloor(player, target))
        {
            handler.SendSysMessage("That rift is no longer bindable. Ask the Rift Keeper to close it.");
            return;
        }
        if (number != 1)
            handler.PSendSysMessage("Floor 1 of this rift has closed behind its party; you arrive on floor {}.", number);
        ForcedTeleport(player, [&](Player* moved)
                       { moved->TeleportTo(arrival.mapId, arrival.x, arrival.y, arrival.z, arrival.o); });
    }

    // F3. Both halves of the town portal, and the obelisk. None of these carry a
    // ScriptName, so this catches every object and filters by entry rather than
    // editing 08-world's generator.
    // A later floor of a live run (rift floors Part F2): the floor is recorded and the book gets it before any AI can ask
    // for its scaling context. Called by the before-instance-script hook, inside OpenNextFloor's CreateMap.
    void RecordLaterFloor(Rift& rift)
    {
        std::lock_guard<std::mutex> lock(riftMutex);
        rift.floor = live.AddFloor(rift.id, rift.instanceId, rift.mapId, rift.dungeonId);
        if (rift.floor)
            CharacterDatabase.Execute(
                "INSERT INTO dc_rift_floor (run_id,floor,instance_id,map_id,dungeon_id) VALUES ({},{},{},{},{})", rift.id,
                rift.floor, rift.instanceId, rift.mapId, rift.dungeonId);
    }

    // 7.5: OnPlayerQuestAccept is a post-add notification, not a veto, and adding a
    // quest to another member re-enters it. One run coordinator, and a guard so a
    // nested add cannot create a second instance - or announce a second time, which
    // is what made "Joined the Nephalem Rift" appear twice on every internal add.

    // The no-abandon re-add cannot happen inline. OnPlayerQuestAbandon fires BEFORE
    // the handler clears the quest-log slot, so a player with a full log has no free
    // slot at that instant and the re-add silently fails - which is a way to abandon
    // a rift quest after all. The re-add is queued here and drained on that player's
    // own next update, by which time the slot is free.

    // The party cap comes from the data, not from a literal 4: party_scaling.csv
    // has one open_world row per supported headcount, so the row count IS the cap.
    unsigned PartyCap()
    {
        static unsigned cached = 0;
        if (cached)
            return cached;
        if (QueryResult row = WorldDatabase.Query("SELECT COUNT(*) FROM dc_party_scaling WHERE context='open_world'"))
            cached = static_cast<unsigned>((*row)[0].Get<uint64>());
        if (!cached)
        {
            LOG_ERROR("server", "[DC rifts] dc_party_scaling has no open_world rows; "
                                "rift headcount scaling is clamped to 1.");
            cached = 1;
        }
        return cached;
    }

    // --- headcount (7.9.7, step 3g) --------------------------------------------
    //
    // "Headcount changes rescale already-spawned monsters and the guardian (Life
    // per party_scaling.csv) in Nephalem Rifts. Greater Rifts keep their start
    // headcount." The scaling itself is 03's: dc_rift.party_size is what
    // ScalingContext hands to the difficulty module, so moving that number and
    // asking for a refresh is the whole of it here.
    void RescaleForHeadcount(std::uint64_t runId)
    {
        Rift rift;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            Rift const* run = live.Find(runId);
            if (!run || run->state == "closed")
                return;
            rift = *run;
        }
        if (rift.mode != "nr")
            return; // a Greater Rift keeps the headcount it started with
        QueryResult row = CharacterDatabase.Query(
            "SELECT COUNT(*) FROM dc_rift_member WHERE run_id={} AND state IN ('enrolled','offline')", rift.id);
        if (!row)
            return;
        // Never zero: party_scaling.csv has rows for one to four players, and a run
        // with nobody in it is about to close anyway.
        unsigned const headcount = std::clamp<unsigned>((*row)[0].Get<uint64>(), 1, PartyCap());
        if (headcount == rift.players)
            return;
        std::vector<Floor> floors;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            Rift* run = live.Find(runId);
            if (!run)
                return;
            run->players = headcount;
            rift = *run;
            floors = live.Floors(runId);
        }
        CharacterDatabase.Execute("UPDATE dc_rift SET party_size={} WHERE id={}", headcount, rift.id);
        // Every floor the run has open rescales: a member joining or leaving counts on all of them.
        for (Floor const& floor : floors)
            if (Map* map = sMapMgr->FindMap(floor.mapId, floor.instanceId))
                DC::Difficulty::RequestRefresh(map);
        LOG_INFO("server", "[DC rifts] rift {} rescaled to {} players", rift.id, headcount);
    }

    // --- departure and return (7.9.7, step 3f) ---------------------------------

    // A command tail arrives with the spaces and any quotes the player typed.
    std::string TrimArgument(std::string text)
    {
        while (!text.empty() && (text.back() == ' ' || text.back() == '"'))
            text.pop_back();
        while (!text.empty() && (text.front() == ' ' || text.front() == '"'))
            text.erase(text.begin());
        return text;
    }

} // namespace DC::Rifts

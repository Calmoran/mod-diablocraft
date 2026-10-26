/*
 * World of DiabloCraft - the open-world rift map, proof of concept (docs/research/open-world-rifts.md).
 *
 * Map 751 is Kalimdor's terrain as a private party instance (data/d3/world_open_rift_dbc.csv, generate_open_rift_map.py
 * and the links link_map_clone.py makes), so the core makes one copy per party with nothing in it: no creatures, no
 * rift. This file is the two things the proof of concept needs on top of the map:
 *
 *   `.dc openrift [<zone>|leave]` (GM only) walks the GM into a zone of a copy (the first zone of the sheet when no word
 *                                 is given), or back to where they stood;
 *   the boundary check            holds a player inside the copy's zone: the copy is the whole continent, so the zone is the
 *                                 wall (a bounty traveller's wall is the open zones of the asked zone's act: see Holds). A player who leaves it is put back at its entrance. Sealing
 *                                 individual exits with objects waits for exits that are verified (the research
 *                                 found 29 candidates, none confirmed), and this check seals every one of them.
 *                                 Where the terrain lets a player walk up a wall to the edge, a wall spot (a sphere
 *                                 from the sheet) does the same bounce before the player gets there.
 *
 * The zones are rift_open_zones.csv (dc_rift_open_zone, generate_rifts.py): Un'Goro and four more Kalimdor
 * zones on the one copy. A copy's zone is its rift floor's (the pool row of the same name), else the zone the player asked
 * `.dc openrift` for, else the sheet's first. Each zone's entrance is its own rows, rifts.csv <entry_tunable>_x/_y/_z/_o (Un'Goro's
 * is open_rift_entry_*, taken from a .gps), read when used, so it moves with `.dc tunables reload`; a
 * zone whose rows are blank is off.
 *
 * Several maps (bounty acts, docs/research/bounty-acts.md 7): each zone row carries its copy map
 * (`map_id`: 751 Kalimdor, 752 Eastern Kingdoms, 753 Outland), and a map is an open-zone map when a zone row names it
 * (IsOpenZoneMap). Everything that was "map 751" is the zone's map or the player's: the copies (the router keys them by
 * map and tier), the binds, the teleports, the hooks; a wall spot names its map too (open_rift_wall_NN_map), since the
 * continents' coordinates overlap. test_open_rift_script.py pins every zone's map to a clone sheet's Map row.
 *
 * Bounties: TravelToOpenZone (dc_rifts.h) is the players' way in, the bounty buttons and the zone
 * waypoints; it seals the player to the zone they went to, as the command does.
 *
 * The arrival check: the trip refuses a party copy that is a live rift, but the core picks the copy at the
 * worldport ack, so a rift opened during the loading screen still takes the traveller in, past the obelisk. On the first
 * update in a copy, after the login sweep has enrolled whoever 7.9.7 lets join, a player who is not in its live run goes to
 * the Sanctum with the trip's refusal text.
 *
 * The copy router (the rules are dc_copy_router.h): a copy that is not a rift is shared
 * by strangers (core patch 0022's IsInstanceShared), one copy a tier holding all the zones, each zone with its own cap
 * (rifts copy_cap_<zone>). A trip asks the router for the copy, binds the traveller (and their party's leader, whose bind
 * the core follows for every member) to it, then teleports; a new copy is made with sMapMgr->CreateMap the way a rift
 * is. The map's own enter and leave hooks keep the counts, so any way in (a town portal, a login) is counted. A player who
 * joins a party in another copy is moved to the party's copy on their next update. `.dc copies` (GM) lists them.
 *
 * Zone fog (the rules in dc_zone_fog.h): an arrival in a copy other than the player's last one clears
 * the explored bits of the open zones' areas, so every new copy's map starts dark; on the map an area lights its bit and
 * gives no exploration XP and no achievement credit.
 */

#include "dc_copy_router.h"
#include "dc_open_rift.h"
#include "dc_rifts_internal.h"
#include "dc_zone_fog.h"

#include "../common/dc_tunables.h"
#include "../common/dc_world.h"
#include "../difficulty/dc_difficulty.h"

#include "Chat.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Group.h"
#include "InstanceSaveMgr.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WorldSession.h"

#include <cstdio>
#include <map>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace DC::Rifts::OpenRift
{
    namespace
    {
        // One row of dc_rift_open_zone: the AreaTable zone a copy is sealed to (its subzones report it as their zone), the
        // command's word, the pool row's name, the rifts.csv prefix of its entrance, its bounty act (1 to 5, the board's
        // column) and its copy map. Loaded at startup, sheet order.
        struct OpenZone
        {
            std::string key, name, entryTunable;
            uint32 zoneId = 0;
            uint32 act = 0;
            uint32 mapId = 0;
        };
        std::vector<OpenZone> zones;

        // The entrance: where the command puts a GM and where the boundary sends a player back. A blank row is no entrance.
        struct Entry
        {
            float x = 0, y = 0, z = 0, o = 0;
            bool set = false;
        };
        Entry EntryPoint(OpenZone const& zone)
        {
            Entry entry;
            std::string const names[4] = {zone.entryTunable + "_x", zone.entryTunable + "_y", zone.entryTunable + "_z",
                                          zone.entryTunable + "_o"};
            entry.set = true;
            for (std::string const& name : names)
                entry.set = entry.set && DC::Tunables::Has("rifts", name);
            if (entry.set)
            {
                entry.x = static_cast<float>(DC::Tunables::Get("rifts", names[0]));
                entry.y = static_cast<float>(DC::Tunables::Get("rifts", names[1]));
                entry.z = static_cast<float>(DC::Tunables::Get("rifts", names[2]));
                entry.o = static_cast<float>(DC::Tunables::Get("rifts", names[3]));
            }
            return entry;
        }

        // The wall spots: rifts.csv open_rift_wall_NN_x/_y/_z/_r/_map, NN from 01 with no gap (the list ends at the first spot
        // with a blank row; a radius of 0 switches one off; a spot on another map is not this one's). Read where used, so
        // `.dc tunables set/reload` adds a spot with no restart.
        // ponytail: read every tick for a player on the copy (a few lookups in the tunables snapshot); a cache if the list grows large.
        bool InWallSpot(uint32 mapId, float px, float py, float pz)
        {
            for (unsigned n = 1; n < 100; ++n)
            {
                char names[5][32];
                char const* const axes[5] = {"x", "y", "z", "r", "map"};
                bool set = true;
                for (int i = 0; i < 5; ++i)
                {
                    std::snprintf(names[i], sizeof(names[i]), "open_rift_wall_%02u_%s", n, axes[i]);
                    set = set && DC::Tunables::Has("rifts", names[i]);
                }
                if (!set)
                    return false;
                if (static_cast<uint32>(DC::Tunables::Get("rifts", names[4])) != mapId)
                    continue;
                double const radius = DC::Tunables::Get("rifts", names[3]);
                double const dx = px - DC::Tunables::Get("rifts", names[0]);
                double const dy = py - DC::Tunables::Get("rifts", names[1]);
                double const dz = pz - DC::Tunables::Get("rifts", names[2]);
                if (radius > 0 && dx * dx + dy * dy + dz * dz <= radius * radius)
                    return true;
            }
            return false;
        }

        // Where each GM stood before going in, and the zone each player asked for (`.dc openrift`, or a bounty trip) (memory
        // only: a restart sends a player to their homebind, as for any instance).
        std::mutex mutex;
        std::unordered_map<uint64, WorldLocation> before;
        std::unordered_map<uint64, std::string> asked;
        std::unordered_set<uint64> arrived; // came onto the map, not yet checked (the arrival check)

        // The copy's zone for this player, among the zones of the map they stand on: a rift floor's is its dungeon's (the
        // pool row has the zone's name); a copy the command made is the zone the player asked for; else the map's first in
        // the sheet. Null only when no zone is on that map.
        OpenZone const* ZoneOf(Player* player)
        {
            uint32 const mapId = player->GetMapId();
            OpenZone const* first = nullptr;
            for (OpenZone const& zone : zones)
                if (zone.mapId == mapId)
                {
                    first = &zone;
                    break;
                }
            std::string name;
            Rift rift;
            bool inRift;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                inRift = live.View(player->GetInstanceId(), mapId, rift);
            }
            Dungeon dungeon;
            if (inRift && ArrivalOf(rift.dungeonId, dungeon))
                name = dungeon.name;
            std::string key;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = asked.find(player->GetGUID().GetRawValue());
                if (found != asked.end())
                    key = found->second;
            }
            for (OpenZone const& zone : zones)
                if (zone.mapId == mapId && (name.empty() ? zone.key == key : zone.name == name))
                    return &zone;
            return first;
        }

        // The zone edge: true when `newZone` is inside this player's wall. A rift floor
        // holds its one zone. A player whose zone asked for is known (a bounty trip, or the command) walks between the open
        // zones of that zone's act and is bounced leaving them (the act edge; docs/research/bounty-acts.md
        // 5); an unsurveyed zone is in no act. Anyone else in the copy keeps the one zone.
        bool Holds(Player* player, uint32 newZone)
        {
            OpenZone const* own = ZoneOf(player);
            if (!own)
                return true;
            bool inRift;
            {
                Rift rift;
                std::lock_guard<std::mutex> lock(riftMutex);
                inRift = live.View(player->GetInstanceId(), player->GetMapId(), rift);
            }
            bool travelled;
            {
                std::lock_guard<std::mutex> lock(mutex);
                travelled = asked.count(player->GetGUID().GetRawValue()) != 0;
            }
            if (inRift || !travelled)
                return newZone == own->zoneId;
            for (OpenZone const& zone : zones)
                if (zone.zoneId == newZone && zone.act == own->act)
                    return true;
            return false;
        }

        // The one bounce, for the zone edge and the wall spots: back to the zone's entrance, with the message once it worked.
        // A GM with GM mode on (.gm on) walks free; with .gm off a GM is bounced like any player.
        void Bounce(Player* player, OpenZone const& zone)
        {
            if (player->IsGameMaster())
                return;
            Entry const entry = EntryPoint(zone);
            if (!entry.set)
                return;
            if (player->TeleportTo(zone.mapId, entry.x, entry.y, entry.z, entry.o))
                ChatHandler(player->GetSession()).SendSysMessage("The rift's walls hold: back to the entrance.");
        }

        // The arrival check: true when the player was sent out. A GM with GM mode on stays, as at the walls.
        bool TurnAwayOutsider(Player* player)
        {
            WorldLocation hub;
            if (player->IsGameMaster() || !OutsiderInRift(player) || !DC::World::HubLocation(hub))
                return false;
            ChatHandler(player->GetSession()).SendSysMessage("Your party is in a rift; travel after it closes.");
            ForcedTeleport(player, [&](Player* moved) { moved->TeleportTo(hub); });
            return true;
        }

        // --- the copy router (R0) ---------------------------------------------------------------------------------------
        // Memory only: a restart loses it with the copies, and a player bound to an old copy is adopted when they come in.
        std::mutex routerMutex; // never held across a teleport or a map call
        CopyRouter::Router router;
        std::unordered_set<uint64> joined; // joined a party while in a copy; moved to the party's copy on their next update

        std::int64_t Now()
        {
            return static_cast<std::int64_t>(GameTime::GetGameTime().count());
        }

        // The rifts tunables, read when used (`.dc tunables reload` moves them with no restart).
        CopyRouter::Rules RouterRules()
        {
            CopyRouter::Rules rules;
            rules.cap = [](std::string const& zone)
            { return static_cast<unsigned>(DC::Tunables::Get("rifts", "copy_cap_" + zone)); };
            rules.linger = static_cast<std::int64_t>(DC::Tunables::Get("rifts", "copy_linger_seconds"));
            rules.seatTimeout = static_cast<std::int64_t>(DC::Tunables::Get("rifts", "copy_seat_timeout_seconds"));
            return rules;
        }

        // The party, leader first; a solo player has none.
        std::vector<uint64> PartyOf(Player* player)
        {
            std::vector<uint64> party;
            if (Group* group = player->GetGroup())
            {
                party.push_back(group->GetLeaderGUID().GetRawValue());
                for (Group::MemberSlot const& slot : group->GetMemberSlots())
                    if (slot.guid != group->GetLeaderGUID())
                        party.push_back(slot.guid.GetRawValue());
            }
            return party;
        }

        // `guid` follows `save` into its copy: the core sends a player to their own bind, or a party member to the
        // leader's (InstanceSaveMgr::PlayerGetDestinationInstanceId), so both are moved to it.
        void BindTo(ObjectGuid guid, InstanceSave* save)
        {
            Player* online = ObjectAccessor::FindConnectedPlayer(guid);
            ::Difficulty const difficulty = ::Difficulty(save->GetDifficulty());
            if (InstancePlayerBind* bind = sInstanceSaveMgr->PlayerGetBoundInstance(guid, save->GetMapId(), difficulty))
            {
                if (bind->save == save)
                    return;
                sInstanceSaveMgr->PlayerUnbindInstance(guid, save->GetMapId(), difficulty, true, online);
            }
            sInstanceSaveMgr->PlayerBindToInstance(guid, save, false, online);
        }

        // Route `player` to a copy of `zone`'s map for it, bind them (and their leader) to it and promise the seat: the
        // instance id, 0 with `error` set when there is none. `partyOnly`: only a copy chosen to keep the party together (a
        // join).
        uint32 SendTo(Player* player, OpenZone const& zone, std::string& error, bool partyOnly = false)
        {
            uint32 const mapId = zone.mapId;
            CopyRouter::Rules const rules = RouterRules();
            std::int64_t const now = Now();
            unsigned const tier = DC::Difficulty::CurrentTier(player);
            uint64 const me = player->GetGUID().GetRawValue();
            std::vector<uint64> const party = PartyOf(player);
            ObjectGuid const leader = party.empty() ? ObjectGuid::Empty : ObjectGuid(party.front());
            // While the party runs an open-zone rift the core's pick is the rift's instance (dc_rifts.cpp binds every
            // member to it): no route then, so a rift's binds are never moved.
            uint32 const current = sInstanceSaveMgr->PlayerGetDestinationInstanceId(player, mapId, player->GetDifficulty(false));
            if (current && IsLiveInstance(mapId, current))
            {
                error = "Your party is in a rift; travel after it closes.";
                return 0;
            }
            for (int attempt = 0; attempt < 3; ++attempt) // a copy whose save is gone is dropped and the route asked again
            {
                CopyRouter::Pick pick;
                {
                    std::lock_guard<std::mutex> lock(routerMutex);
                    pick = router.Route(rules, now, mapId, tier, zone.key, me, party);
                }
                if (partyOnly && !pick.party)
                    return 0;
                InstanceSave* save = nullptr;
                if (pick.open)
                {
                    // A fresh instance, as a rift is made: with no bind on the map the core creates a new one.
                    ::Difficulty const difficulty = player->GetDifficulty(false);
                    sInstanceSaveMgr->PlayerUnbindInstance(player->GetGUID(), mapId, difficulty, true, player);
                    if (!leader.IsEmpty() && leader != player->GetGUID())
                        sInstanceSaveMgr->PlayerUnbindInstance(leader, mapId, difficulty, true,
                                                               ObjectAccessor::FindConnectedPlayer(leader));
                    Map* map = sMapMgr->CreateMap(mapId, player);
                    save = map ? sInstanceSaveMgr->GetInstanceSave(map->GetInstanceId()) : nullptr;
                    std::lock_guard<std::mutex> lock(routerMutex);
                    if (!save || router.Find(save->GetInstanceId()))
                    {
                        error = "The way there would not open.";
                        LOG_ERROR("server", "[DC copies] no fresh copy of map {} for {} (tier {})", mapId, player->GetName(), tier);
                        return 0;
                    }
                    router.Opened(mapId, tier, pick.number, save->GetInstanceId());
                }
                else if (!(save = sInstanceSaveMgr->GetInstanceSave(pick.instanceId)))
                {
                    std::lock_guard<std::mutex> lock(routerMutex);
                    router.Drop(pick.instanceId);
                    continue;
                }
                BindTo(player->GetGUID(), save);
                if (!leader.IsEmpty() && leader != player->GetGUID())
                    BindTo(leader, save);
                if (!player->IsGameMaster())
                {
                    std::lock_guard<std::mutex> lock(routerMutex);
                    router.Promise(rules, now, save->GetInstanceId(), me, zone.key);
                }
                return save->GetInstanceId();
            }
            error = "The way there would not open.";
            return 0;
        }

        // A routed trip onto the zone's map: a far teleport when the copy differs from the one the player stands in (the
        // same map id would otherwise be a near teleport inside the old copy). A trip inside the copy counts at once.
        bool Arrive(Player* player, uint32 copy, OpenZone const& zone, float x, float y, float z, float o)
        {
            bool const sameCopy = player->GetMapId() == zone.mapId && player->GetInstanceId() == copy;
            if (!player->TeleportTo(zone.mapId, x, y, z, o, 0, nullptr, !sameCopy && player->GetMapId() == zone.mapId))
                return false;
            if (sameCopy)
            {
                std::lock_guard<std::mutex> lock(routerMutex);
                router.Enter(Now(), copy, zone.mapId, DC::Difficulty::CurrentTier(player), player->GetGUID().GetRawValue(),
                             zone.key, player->IsGameMaster());
            }
            return true;
        }

        // Rule 8: a player who joined a party in another copy goes to the party's copy, where they stand, now.
        void MoveToParty(Player* player)
        {
            if (!IsOpenZoneMap(player->GetMapId()) || IsLiveInstance(player->GetMapId(), player->GetInstanceId()))
                return;
            OpenZone const* zone = ZoneOf(player);
            std::string error;
            uint32 const copy = zone ? SendTo(player, *zone, error, true) : 0;
            if (!copy || copy == player->GetInstanceId())
                return;
            ChatHandler(player->GetSession()).SendSysMessage("Joining your party's copy of the zone.");
            Arrive(player, copy, *zone, player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(),
                   player->GetOrientation());
        }

        // Zone fog: the explored-zones words and bits of the open zones' areas (made once at startup from the zones and
        // AreaTable). The client's engine draws the fog of the walked path over the map, so the map under it is whole:
        // every arrival on a copy sets all of these bits, and the sub-area-by-sub-area reveal of the core is not used.
        std::map<uint32, uint32> fogMasks;

        void Light(Player* player)
        {
            for (auto const& [word, bits] : fogMasks)
                player->SetFlag(PLAYER_EXPLORED_ZONES_1 + word, bits);
        }

        class Boundary final : public PlayerScript
        {
        public:
            Boundary()
                : PlayerScript("dc_open_rift", {PLAYERHOOK_ON_UPDATE_ZONE, PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT,
                                                PLAYERHOOK_ON_MAP_CHANGED, PLAYERHOOK_CAN_AREA_EXPLORE_AND_OUTDOOR})
            {
            }

            void OnPlayerUpdateZone(Player* player, uint32 newZone, uint32 /*newArea*/) override
            {
                if (!IsOpenZoneMap(player->GetMapId()) || player->IsBeingTeleported())
                    return;
                if (OpenZone const* zone = ZoneOf(player); zone && !Holds(player, newZone))
                    Bounce(player, *zone);
            }

            // Map::AddPlayerToMap, at the worldport ack or the login: the copy is the core's pick from here on. Checked on the
            // first update, not here, so the move out is not started inside the core's arrival and the login sweep runs first.
            void OnPlayerMapChanged(Player* player) override
            {
                if (!IsOpenZoneMap(player->GetMapId()))
                    return;
                std::lock_guard<std::mutex> lock(mutex);
                arrived.insert(player->GetGUID().GetRawValue());
            }

            void OnPlayerUpdate(Player* player, uint32 /*p_time*/) override
            {
                if (!IsOpenZoneMap(player->GetMapId()) || player->IsBeingTeleported())
                    return;
                bool first;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    first = arrived.erase(player->GetGUID().GetRawValue()) != 0;
                }
                if (first && TurnAwayOutsider(player))
                    return;
                bool moveToParty;
                {
                    std::lock_guard<std::mutex> lock(routerMutex);
                    moveToParty = joined.erase(player->GetGUID().GetRawValue()) != 0;
                }
                if (moveToParty)
                    MoveToParty(player);
                if (InWallSpot(player->GetMapId(), player->GetPositionX(), player->GetPositionY(), player->GetPositionZ()))
                    if (OpenZone const* zone = ZoneOf(player))
                        Bounce(player, *zone);
            }

            // The zone stays (bounties W5): a player who logs back into the copy is sealed to the zone they went to.
            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> lock(mutex);
                before.erase(player->GetGUID().GetRawValue());
                arrived.erase(player->GetGUID().GetRawValue());
                std::lock_guard<std::mutex> routed(routerMutex);
                joined.erase(player->GetGUID().GetRawValue());
            }

            // The core's exploration is stopped on the map: no experience, no "Discovered" line, no achievement credit.
            bool OnPlayerCanAreaExploreAndOutdoor(Player* player) override
            {
                if (!IsOpenZoneMap(player->GetMapId()))
                    return true;
                return false;
            }
        };

        // The counts: every way onto a copy and off it, whatever moved the player. A rift's instance is not a copy.
        class CopyCounts final : public AllMapScript
        {
        public:
            CopyCounts()
                : AllMapScript("dc_open_rift_copies", {ALLMAPHOOK_ON_PLAYER_ENTER_ALL, ALLMAPHOOK_ON_PLAYER_LEAVE_ALL})
            {
            }

            void OnPlayerEnterAll(Map* map, Player* player) override
            {
                if (!IsOpenZoneMap(map->GetId()))
                    return;
                Light(player); // every copy, a rift floor's too
                if (IsLiveInstance(map->GetId(), map->GetInstanceId()))
                    return;
                OpenZone const* zone = ZoneOf(player);
                std::lock_guard<std::mutex> lock(routerMutex);
                router.Enter(Now(), map->GetInstanceId(), map->GetId(), DC::Difficulty::CurrentTier(player),
                             player->GetGUID().GetRawValue(), zone ? zone->key : std::string(), player->IsGameMaster());
            }

            void OnPlayerLeaveAll(Map* map, Player* player) override
            {
                if (!IsOpenZoneMap(map->GetId()))
                    return;
                std::lock_guard<std::mutex> lock(routerMutex);
                router.Leave(Now(), map->GetInstanceId(), player->GetGUID().GetRawValue());
            }
        };

        // Core patch 0022: a copy the router holds lets strangers in, up to every zone's cap plus a party's overflow; a
        // rift's instance, and any other dungeon, stays one party an instance.
        class SharedCopies final : public GlobalScript
        {
        public:
            SharedCopies()
                : GlobalScript("dc_open_rift_shared", {GLOBALHOOK_IS_INSTANCE_SHARED})
            {
            }

            bool IsInstanceShared(uint32 mapId, uint32 instanceId, uint32& maxPlayers) override
            {
                if (!IsOpenZoneMap(mapId))
                    return false;
                std::vector<std::string> keys; // the map's zones: a copy holds its own map's
                for (OpenZone const& zone : zones)
                    if (zone.mapId == mapId)
                        keys.push_back(zone.key);
                CopyRouter::Rules const rules = RouterRules();
                unsigned const party = PartyCap();
                std::lock_guard<std::mutex> lock(routerMutex);
                if (!router.Find(instanceId))
                    return false;
                maxPlayers = CopyRouter::Router::HardCap(keys, rules, party > 0 ? party - 1 : 0);
                return true;
            }
        };

        // Rule 8: joining a party marks the joiner; their next update in a copy moves them to the party's.
        class PartyJoin final : public GroupScript
        {
        public:
            PartyJoin()
                : GroupScript("dc_open_rift_party_join", {GROUPHOOK_ON_ADD_MEMBER})
            {
            }

            // Group::Create adds the leader with AddMember too (Group.cpp), and the party's copy is the leader's: only
            // a joiner moves.
            void OnAddMember(Group* group, ObjectGuid guid) override
            {
                if (group && group->IsLeader(guid))
                    return;
                Player* player = ObjectAccessor::FindConnectedPlayer(guid);
                if (!player || !IsOpenZoneMap(player->GetMapId()))
                    return; // not in a copy: their next trip goes to the party's copy anyway
                std::lock_guard<std::mutex> lock(routerMutex);
                joined.insert(guid.GetRawValue());
            }
        };

        class OpenRiftCommand final : public CommandScript
        {
        public:
            OpenRiftCommand()
                : CommandScript("dc_open_rift_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable children = {{"openrift", HandleOpenRift, SEC_GAMEMASTER, Console::No},
                                                    {"copies", HandleCopies, SEC_GAMEMASTER, Console::Yes}};
                static ChatCommandTable root = {{"dc", children}};
                return root;
            }

            // `.dc openrift <zone>` goes in (no word: the sheet's first zone); `leave` comes back. One copy per party: the first
            // of a party to go in makes it and the others who run the command join it.
            static bool HandleOpenRift(ChatHandler* handler, Optional<std::string> where)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                if (zones.empty())
                {
                    handler->SendSysMessage("No open zones loaded (dc_rift_open_zone is empty or missing; see the startup log).");
                    handler->SetSentErrorMessage(true);
                    return false;
                }
                std::string const word = where ? *where : zones.front().key;
                bool const inside = IsOpenZoneMap(player->GetMapId());
                if (word == "leave")
                    return Leave(handler, player, inside);
                OpenZone const* zone = nullptr;
                std::string words;
                for (OpenZone const& candidate : zones)
                {
                    if (candidate.key == word)
                        zone = &candidate;
                    words += (words.empty() ? "" : ", ") + candidate.key;
                }
                if (!zone)
                {
                    handler->PSendSysMessage("`.dc openrift <zone>` goes in ({}), `.dc openrift leave` comes back.", words);
                    handler->SetSentErrorMessage(true);
                    return false;
                }
                if (inside)
                {
                    handler->SendSysMessage("Already inside; `.dc openrift leave` comes back.");
                    handler->SetSentErrorMessage(true);
                    return false;
                }
                Entry const entry = EntryPoint(*zone);
                if (!entry.set)
                {
                    handler->PSendSysMessage("{} has no entrance yet (rifts {}_x, _y, _z and _o are blank).", zone->name,
                                             zone->entryTunable);
                    handler->SetSentErrorMessage(true);
                    return false;
                }
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    before[player->GetGUID().GetRawValue()] = player->GetWorldLocation();
                    asked[player->GetGUID().GetRawValue()] = zone->key;
                }
                std::string error;
                uint32 const copy = SendTo(player, *zone, error);
                if (!copy || !Arrive(player, copy, *zone, entry.x, entry.y, entry.z, entry.o))
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    before.erase(player->GetGUID().GetRawValue());
                    asked.erase(player->GetGUID().GetRawValue());
                    handler->SendSysMessage(error.empty() ? "The rift would not take you (see the message above, or the log)." : error);
                    handler->SetSentErrorMessage(true);
                    return false;
                }
                return true;
            }

            // `.dc copies`: every open copy with its map, tier, instance and each zone's count against its cap.
            static bool HandleCopies(ChatHandler* handler)
            {
                CopyRouter::Rules const rules = RouterRules();
                std::int64_t const now = Now();
                std::vector<CopyRouter::Copy> copies;
                {
                    std::lock_guard<std::mutex> lock(routerMutex);
                    router.Tidy(rules, now);
                    copies = router.Copies();
                }
                std::sort(copies.begin(), copies.end(), [](CopyRouter::Copy const& a, CopyRouter::Copy const& b)
                          { return a.map != b.map ? a.map < b.map : a.tier != b.tier ? a.tier < b.tier : a.number < b.number; });
                handler->PSendSysMessage("Open-zone copies: {} (linger {} s, seat timeout {} s).", copies.size(), rules.linger,
                                         rules.seatTimeout);
                for (CopyRouter::Copy const& copy : copies)
                {
                    std::string counts;
                    for (OpenZone const& zone : zones)
                    {
                        if (zone.mapId != copy.map)
                            continue;
                        unsigned promised = 0;
                        for (CopyRouter::Seat const& seat : copy.promised)
                            promised += seat.zone == zone.key;
                        unsigned const total = copy.InZone(zone.key, 0);
                        if (total)
                            counts += (counts.empty() ? "" : ", ") + zone.key + " " + std::to_string(total) + "/" +
                                      std::to_string(rules.cap(zone.key)) +
                                      (promised ? " (" + std::to_string(promised) + " on the way)" : "");
                    }
                    std::string const state = copy.emptySince >= 0
                        ? "empty " + std::to_string(now - copy.emptySince) + " s, closes at " + std::to_string(rules.linger) + " s"
                        : counts;
                    handler->PSendSysMessage("map {} #{} tier {} instance {}: {}", copy.map, copy.number, copy.tier, copy.instanceId,
                                             state);
                }
                return true;
            }

        private:
            static bool Leave(ChatHandler* handler, Player* player, bool inside)
            {
                if (!inside)
                {
                    handler->SendSysMessage("Not inside the rift map.");
                    handler->SetSentErrorMessage(true);
                    return false;
                }
                WorldLocation back(player->m_homebindMapId, player->m_homebindX, player->m_homebindY, player->m_homebindZ, 0.0f);
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto found = before.find(player->GetGUID().GetRawValue());
                    if (found != before.end())
                    {
                        back = found->second;
                        before.erase(found);
                    }
                    asked.erase(player->GetGUID().GetRawValue());
                }
                return player->TeleportTo(back);
            }
        };
        // The zones, once at startup (the sheet changes only with a migration).
        class ZoneLoader final : public WorldScript
        {
        public:
            ZoneLoader()
                : WorldScript("dc_open_rift_zones", {WORLDHOOK_ON_STARTUP})
            {
            }

            void OnStartup() override
            {
                QueryResult result = WorldDatabase.Query(
                    "SELECT `key`, `name`, `zone_id`, `entry_tunable`, `act`, `map_id` FROM `dc_rift_open_zone` ORDER BY `seq`");
                if (!result)
                {
                    LOG_ERROR("server.loading", "[DC open rift] dc_rift_open_zone has no zone: the copies are unsealed and "
                              "`.dc openrift` refuses");
                    return;
                }
                do
                {
                    Field* fields = result->Fetch();
                    zones.push_back({fields[0].Get<std::string>(), fields[1].Get<std::string>(), fields[3].Get<std::string>(),
                                     fields[2].Get<uint32>(), fields[4].Get<uint32>(), fields[5].Get<uint32>()});
                } while (result->NextRow());
                LOG_INFO("server.loading", "[DC open rift] {} open zones", zones.size());
                std::vector<ZoneFog::Area> areas;
                for (AreaTableEntry const* area : sAreaTableStore)
                    areas.push_back({area->ID, area->zone, area->exploreFlag});
                std::vector<uint32> ids;
                for (OpenZone const& zone : zones)
                    ids.push_back(zone.zoneId);
                fogMasks = ZoneFog::Masks(areas, ids, PLAYER_EXPLORED_ZONES_SIZE);
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new ZoneLoader();
        new Boundary();
        new CopyCounts();
        new SharedCopies();
        new PartyJoin();
        new OpenRiftCommand();
    }
} // namespace DC::Rifts::OpenRift

namespace DC::Rifts
{
    bool IsOpenZoneMap(std::uint32_t mapId)
    {
        for (OpenRift::OpenZone const& zone : OpenRift::zones)
            if (zone.mapId == mapId)
                return true;
        return false;
    }

    bool OpenZoneWaypoint(std::string const& zoneKey, float& x, float& y)
    {
        for (OpenRift::OpenZone const& zone : OpenRift::zones)
            if (zone.key == zoneKey)
            {
                OpenRift::Entry const entry = OpenRift::EntryPoint(zone);
                x = entry.x;
                y = entry.y;
                return entry.set;
            }
        return false;
    }

    std::string TravelToOpenZone(Player* player, std::string const& zoneKey, float const* spot)
    {
        OpenRift::OpenZone const* zone = nullptr;
        for (OpenRift::OpenZone const& candidate : OpenRift::zones)
            if (candidate.key == zoneKey)
                zone = &candidate;
        OpenRift::Entry const entry = zone ? OpenRift::EntryPoint(*zone) : OpenRift::Entry{};
        if (!entry.set) // a zone off the sheet, or with its entrance rows blank, has no copy built
            return "That zone has no way in yet.";
        // The copy is the core's pick (MapInstanced::CreateInstanceForPlayer). While the party runs an open-zone rift that
        // pick is the rift's own instance (dc_rifts.cpp rebinds every member), so the trip would land inside it, past the
        // obelisk: refused.
        std::uint32_t const copy =
            sInstanceSaveMgr->PlayerGetDestinationInstanceId(player, zone->mapId, player->GetDifficulty(false));
        if (copy && IsLiveInstance(zone->mapId, copy))
            return "Your party is in a rift; travel after it closes.";
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        std::string was;
        {
            std::lock_guard<std::mutex> lock(OpenRift::mutex);
            was = OpenRift::asked.count(guid) ? OpenRift::asked[guid] : "";
            OpenRift::asked[guid] = zone->key; // before the move: the zone edge reads it the moment the player lands
        }
        // The router picks the copy (bounties R0) and binds the traveller to it; the core then follows the bind.
        std::string error;
        std::uint32_t const routed = OpenRift::SendTo(player, *zone, error);
        bool const moved = routed && (spot ? OpenRift::Arrive(player, routed, *zone, spot[0], spot[1], spot[2], spot[3])
                                           : OpenRift::Arrive(player, routed, *zone, entry.x, entry.y, entry.z, entry.o));
        if (moved)
            return "";
        std::lock_guard<std::mutex> lock(OpenRift::mutex);
        if (was.empty())
            OpenRift::asked.erase(guid);
        else
            OpenRift::asked[guid] = was;
        return error.empty() ? "The way there would not open." : error;
    }
} // namespace DC::Rifts

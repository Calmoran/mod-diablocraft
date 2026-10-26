/*
 * World of DiabloCraft - the exit portal and the next floor (rift floors Part F2,
 * docs/proposals/rift-floors.md 4.3, 4.4).
 *
 *   .dc floor exit here | show | clear
 *
 * Every rift floor but the last stands an exit portal from the moment it opens. A member who clicks it goes down to the
 * floor after it, which is made the first time anybody uses the exit (OpenNextFloor, dc_rifts.cpp) and lives until the
 * run closes. The portal stands where a GM placed it for that dungeon (dc_rift_exit_spot, `here`), else at the survey's
 * far point (dc_rift_exit_point, monster spawning S0). generate_rift_survey.py --export writes those spots into the
 * committed sheet.
 *
 * Built on the stock systems: the portal is a gameobject summoned on the floor's map, as the town portal's halves are;
 * the click is the module's ordinary gameobject gossip hook (the obelisk's entrance portal does the same); the bind and
 * the teleport are the instance save manager's. Ours: the choice of floor and the spot, as dc_rift_exit.h writes them.
 *
 * Internal to the rifts folder.
 */

#include "dc_rift_exit.h"
#include "dc_rift_quests.h"
#include "dc_rift_way_back.h"
#include "dc_rifts_internal.h"

#include "../common/dc_tunables.h"
#include "../common/dc_world.h"

#include "AreaTriggerScript.h"
#include "Chat.h"
#include "Creature.h"
#include "DataMap.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "Log.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WorldSession.h"

#include <cmath>
#include <map>
#include <mutex>
#include <random>
#include <set>
#include <string>
#include <vector>

namespace DC::Rifts::Exit
{
    namespace
    {
        // The GM marker of `.dc floor exit show` lives this long and takes itself down. Constant: a lookup aid, not
        // gameplay.
        constexpr std::uint32_t MARKER_ENTRY = 1; // creature_template 1: stock "Waypoint (Only GM can see it)"
        constexpr std::uint32_t MARKER_MS = 60000;

        // What a floor's exit is, for `.dc rift status`: by instance, forgotten with the floor's map.
        struct Placed
        {
            std::uint32_t entry = 0; // 0: none stands
            std::string note;        // why none, or where it stands
            std::optional<Spot> at;  // where it stands: the way back from the floor below leads here (4.5)
        };
        std::mutex placedMutex;
        std::map<std::uint32_t, Placed> placed;

        // A floor's map is told once.
        struct ExitMark : public DataMap::Base
        {
            bool done = false;
        };

        unsigned FloorCap()
        {
            return static_cast<unsigned>(Tunables::Get("rifts", "rift_max_floors"));
        }

        std::optional<Spot> ReadSpot(char const* table, std::string const& dungeon)
        {
            QueryResult row = WorldDatabase.Query("SELECT `x`, `y`, `z`, `o` FROM `{}` WHERE `dungeon` = {}", table,
                                                  TouchUp::Quote(dungeon));
            if (!row)
                return std::nullopt;
            Field* f = row->Fetch();
            return Spot{f[0].Get<double>(), f[1].Get<double>(), f[2].Get<double>(), f[3].Get<double>()};
        }

        // A placed spot, else the survey's; `source` says which.
        std::optional<Spot> SpotFor(std::string const& dungeon, std::string& source)
        {
            std::optional<Spot> alex = ReadSpot("dc_rift_exit_spot", dungeon);
            std::optional<Spot> survey = alex ? std::nullopt : ReadSpot("dc_rift_exit_point", dungeon);
            source = alex ? "placed by the designer" : "the survey's far point";
            return ChooseSpot(alex, survey);
        }

        void Remember(std::uint32_t instanceId, std::uint32_t entry, std::string note,
                      std::optional<Spot> at = std::nullopt)
        {
            std::lock_guard<std::mutex> lock(placedMutex);
            placed[instanceId] = Placed{entry, std::move(note), at};
        }

        std::optional<Spot> PlacedAt(std::uint32_t instanceId)
        {
            std::lock_guard<std::mutex> lock(placedMutex);
            auto found = placed.find(instanceId);
            return found == placed.end() || !found->second.entry ? std::nullopt : found->second.at;
        }

        // A random look of the 17, as the obelisk's entrance rolls one (6.12), on the template named for the floor it leads to.
        std::uint32_t RollExitEntry(unsigned leadsTo)
        {
            std::vector<PortalLook> const looks = PortalPool();
            if (looks.empty())
                return 0;
            return ExitEntry(looks[std::uniform_int_distribution<std::size_t>(0, looks.size() - 1)(Engine())].entry, leadsTo);
        }

        bool Fail(ChatHandler* handler, std::string const& text)
        {
            handler->SendSysMessage(text);
            handler->SetSentErrorMessage(true);
            return false;
        }

        // The dungeon the GM means: the rift floor's own, or else the pool row on this map nearest its arrival point.
        bool DungeonHere(Player* player, Dungeon& out)
        {
            Map* map = player->GetMap();
            Rift view;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                if (live.View(map->GetInstanceId(), map->GetId(), view))
                    return ArrivalOf(view.dungeonId, out);
            }
            bool found = false;
            double best = 0;
            std::lock_guard<std::mutex> lock(dataMutex);
            for (Dungeon const& dungeon : pool)
            {
                if (dungeon.mapId != map->GetId())
                    continue;
                double const dx = dungeon.x - player->GetPositionX(), dy = dungeon.y - player->GetPositionY(),
                             dz = dungeon.z - player->GetPositionZ();
                double const distance = dx * dx + dy * dy + dz * dz;
                if (!found || distance < best)
                    found = true, best = distance, out = dungeon;
            }
            return found;
        }

        class FloorExitCommand final : public CommandScript
        {
        public:
            FloorExitCommand()
                : CommandScript("dc_floor_exit_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // Looking is for any GM; placing writes the world database, so it is an administrator's, as the
                // touch-up is.
                static ChatCommandTable exit = {
                    {"here", HandleHere, SEC_ADMINISTRATOR, Console::No},
                    {"show", HandleShow, SEC_GAMEMASTER, Console::No},
                    {"clear", HandleClear, SEC_ADMINISTRATOR, Console::No},
                };
                static ChatCommandTable floor = {{"exit", exit}};
                static ChatCommandTable dc = {{"floor", floor}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            static Player* Self(ChatHandler* handler)
            {
                return handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            }

            // `.dc floor exit here`: the exit of the dungeon he stands in is where he stands. The next floor to open
            // uses it; a floor already open keeps the portal it has.
            static bool HandleHere(ChatHandler* handler)
            {
                Player* player = Self(handler);
                Dungeon dungeon;
                if (!player || !DungeonHere(player, dungeon))
                    return Fail(handler, "Stand in a rift floor, or in a dungeon on the rift list.");
                Spot const at{player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(),
                              player->GetOrientation()};
                WorldDatabase.DirectExecute(PlaceSql(dungeon.name, at));
                handler->PSendSysMessage(
                    "The exit of {} is here now. The next floor to open uses it; a floor already open keeps "
                    "its portal. `.dc floor exit show` marks it.",
                    dungeon.name);
                return true;
            }

            // `.dc floor exit show`: marks where the exit of this dungeon stands, and says whose spot it is.
            static bool HandleShow(ChatHandler* handler)
            {
                Player* player = Self(handler);
                Dungeon dungeon;
                if (!player || !DungeonHere(player, dungeon))
                    return Fail(handler, "Stand in a rift floor, or in a dungeon on the rift list.");
                std::string source;
                std::optional<Spot> spot = SpotFor(dungeon.name, source);
                if (!spot)
                    return Fail(handler,
                                dungeon.name + " has no exit point: the survey has none and nobody placed one.");
                player->GetMap()->SummonCreature(MARKER_ENTRY, Position(spot->x, spot->y, spot->z, spot->o), nullptr,
                                                 MARKER_MS);
                handler->PSendSysMessage(
                    "The exit of {} ({}): {:.1f} {:.1f} {:.1f}, {} yards from you. Marked for a minute.", dungeon.name,
                    source, spot->x, spot->y, spot->z,
                    static_cast<int>(player->GetDistance(spot->x, spot->y, spot->z)));
                return true;
            }

            // `.dc floor exit clear`: his spot goes; the survey's far point is the exit again.
            static bool HandleClear(ChatHandler* handler)
            {
                Player* player = Self(handler);
                Dungeon dungeon;
                if (!player || !DungeonHere(player, dungeon))
                    return Fail(handler, "Stand in a rift floor, or in a dungeon on the rift list.");
                WorldDatabase.DirectExecute(ClearSql(dungeon.name));
                handler->PSendSysMessage("Your exit of {} is cleared: the survey's far point stands again.",
                                         dungeon.name);
                return true;
            }
        };

        // The dungeon's own way-out triggers (rifts_0022, one areatrigger_scripts row each) land here. In a live rift floor the
        // way back leads up to the exit portal of the floor above, or from floor 1 to the hub (4.5); anywhere
        // else the script declines and the stock teleport runs.
        class WayBackScript final : public AreaTriggerScript
        {
        public:
            WayBackScript()
                : AreaTriggerScript(WayBack::SCRIPT_NAME)
            {
            }

            bool OnTrigger(Player* player, AreaTrigger const*) override
            {
                Map* map = player->GetMap();
                Rift here;
                std::vector<Floor> floors;
                {
                    std::lock_guard<std::mutex> lock(riftMutex);
                    if (!map || !live.View(map->GetInstanceId(), map->GetId(), here))
                        return false;
                    floors = live.Floors(here.id);
                }
                Rift mine;
                bool const member = EnrolledRun(player->GetGUID(), mine) && mine.id == here.id;
                std::vector<unsigned> standing;
                for (Floor const& floor : floors)
                    standing.push_back(floor.number);
                WayBack::Choice const choice =
                    WayBack::Choose(here.floor, player->IsAlive(), member, here.mode == "gr", here.state, standing);
                ChatHandler handler(player->GetSession());
                switch (choice.way)
                {
                    case WayBack::Way::Dead:
                    case WayBack::Way::Shut:
                        handler.SendSysMessage(WayBack::Say(choice));
                        return true;
                    case WayBack::Way::Up:
                        return GoUp(player, handler, floors, choice);
                    default:
                        break;
                }
                WorldLocation hub;
                if (!DC::World::HubLocation(hub))
                    return false;
                handler.SendSysMessage(WayBack::Say(choice));
                ForcedTeleport(player, [&](Player* moved) { moved->TeleportTo(hub); });
                return true;
            }

        private:
            // The exit portal of the floor above; where none stands there (the dungeon had no exit point), its arrival point.
            static bool GoUp(Player* player, ChatHandler& handler, std::vector<Floor> const& floors,
                             WayBack::Choice choice)
            {
                Floor target;
                for (Floor const& floor : floors)
                    if (floor.number == choice.floor)
                        target = floor;
                Dungeon arrival;
                if (!ArrivalOf(target.dungeonId, arrival) || !BindToFloor(player, target))
                {
                    handler.SendSysMessage("That floor is no longer there. Ask the Rift Keeper to close the rift.");
                    return true;
                }
                Spot where{arrival.x, arrival.y, arrival.z, arrival.o};
                if (std::optional<Spot> exit = PlacedAt(target.instanceId))
                    where = *exit;
                handler.SendSysMessage(WayBack::Say(choice));
                ForcedTeleport(player,
                               [&](Player* moved)
                               { moved->TeleportTo(target.mapId, where.x, where.y, where.z, where.o); });
                return true;
            }
        };

        // A way-out trigger switched off in rifts (rift_way_none.csv; Pit of Saron's far exit sent players to the hub):
        // in a live rift floor stepping on it does nothing; anywhere else the stock teleport runs.
        class WayNoneScript final : public AreaTriggerScript
        {
        public:
            WayNoneScript()
                : AreaTriggerScript(WayBack::NONE_SCRIPT_NAME)
            {
            }

            bool OnTrigger(Player* player, AreaTrigger const*) override
            {
                Map* map = player->GetMap();
                Rift here;
                std::lock_guard<std::mutex> lock(riftMutex);
                return map && live.View(map->GetInstanceId(), map->GetId(), here);
            }
        };
    } // namespace

    // The dungeon a GM means by "here", for the commands that edit a dungeon's spots (`.dc pylon spot`).
    bool DungeonOf(Player* player, Dungeon& out)
    {
        return DungeonHere(player, out);
    }

    // Once per floor, on the floor's own map update, after the spawner has placed it (4.4: it stands from the moment
    // the floor opens). The last floor has none.
    void PlaceExit(Map* map)
    {
        if (!map || !map->IsDungeon())
            return;
        ExitMark* mark = map->CustomData.GetDefault<ExitMark>("DCRiftExit");
        if (mark->done)
            return;
        Rift view;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            if (!live.View(map->GetInstanceId(), map->GetId(), view))
                return; // not a live rift floor (yet): try again on the next update
        }
        mark->done = true;
        if (view.floor >= FloorCap())
        {
            Remember(map->GetInstanceId(), 0, "none: the last floor");
            return;
        }
        Dungeon dungeon;
        if (!ArrivalOf(view.dungeonId, dungeon))
        {
            Remember(map->GetInstanceId(), 0, "none: the dungeon is not in the pool");
            return;
        }
        std::string source;
        std::optional<Spot> spot = SpotFor(dungeon.name, source);
        if (!spot)
        {
            LOG_ERROR("server",
                      "[DC floors] {} has no exit point (dc_rift_exit_point, dc_rift_exit_spot); floor {} of run {} "
                      "has no exit",
                      dungeon.name, view.floor, view.id);
            Remember(map->GetInstanceId(), 0, "none: " + dungeon.name + " has no exit point");
            return;
        }
        // Named for the floor a click leads to: the one after this (a floor that unloaded while this one stands makes a click
        // open the next new number instead; the name then reads one floor early, see the sheet).
        std::uint32_t const entry = RollExitEntry(view.floor + 1);
        GameObject* portal = entry ? map->SummonGameObject(entry, spot->x, spot->y, spot->z, spot->o, 0, 0,
                                                           std::sin(spot->o / 2), std::cos(spot->o / 2), 0)
                                   : nullptr;
        if (!portal)
        {
            LOG_ERROR("server", "[DC floors] the exit portal {} of floor {} of run {} could not be summoned", entry,
                      view.floor, view.id);
            Remember(map->GetInstanceId(), 0, "none: the portal could not be summoned");
            return;
        }
        Remember(map->GetInstanceId(), entry,
                 "template " + std::to_string(entry) + " at " + std::to_string(spot->x) + " " +
                     std::to_string(spot->y) + " " + std::to_string(spot->z) + ", " + source,
                 spot);
    }

    // The click. A member of the run, alive, anywhere on the floor, in combat or not (6.3).
    void Use(Player* player, GameObject* go)
    {
        ChatHandler handler(player->GetSession());
        Map* map = go->GetMap();
        Rift here;
        std::vector<Floor> floors;
        std::set<std::uint32_t> used;
        unsigned highest = 0;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            if (!map || !live.View(map->GetInstanceId(), map->GetId(), here))
            {
                handler.SendSysMessage("That portal leads nowhere.");
                return;
            }
            floors = live.Floors(here.id);
            used = live.UsedMaps(here.id);
            highest = live.Highest(here.id);
        }
        if (here.state == "closed")
        {
            handler.SendSysMessage(Say(Refusal::Closed));
            return;
        }
        Rift mine;
        if (!EnrolledRun(player->GetGUID(), mine) || mine.id != here.id)
        {
            handler.SendSysMessage("That portal belongs to another party.");
            return;
        }
        if (!player->IsAlive())
        {
            handler.SendSysMessage("Use the exit portal alive.");
            return;
        }

        std::vector<unsigned> standing;
        for (Floor const& floor : floors)
            standing.push_back(floor.number);
        unsigned const next = NextStanding(standing, here.floor);
        Floor target;
        Dungeon arrival;
        if (next)
        {
            // The floor after this one stands: members who follow bind on use, as the obelisk's portal does.
            for (Floor const& floor : floors)
                if (floor.number == next)
                    target = floor;
            if (!ArrivalOf(target.dungeonId, arrival) || !BindToFloor(player, target))
            {
                handler.SendSysMessage("That floor is no longer bindable. Ask the Rift Keeper to close the rift.");
                return;
            }
        }
        else
        {
            // Nothing stands after this floor: the first use makes the next one (4.3).
            std::vector<Dungeon> candidates;
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                candidates = pool;
            }
            std::vector<std::uint32_t> maps;
            for (Dungeon const& dungeon : candidates)
                maps.push_back(dungeon.mapId);
            std::vector<std::size_t> const eligible = EligibleMaps(maps, used);
            Refusal const why = MayOpenNext(here.state, here.guardianInstance, highest, FloorCap(), eligible.size());
            if (why != Refusal::None)
            {
                handler.SendSysMessage(Say(why));
                return;
            }
            arrival =
                candidates[eligible[std::uniform_int_distribution<std::size_t>(0, eligible.size() - 1)(Engine())]];
            std::string error;
            if (!OpenNextFloor(player, here, arrival, target, error))
            {
                handler.SendSysMessage(error);
                return;
            }
        }
        handler.PSendSysMessage("Floor {}: {}.", target.number, arrival.name);
        ForcedTeleport(player, [&](Player* moved)
                       { moved->TeleportTo(arrival.mapId, arrival.x, arrival.y, arrival.z, arrival.o); });
    }

    std::string Describe(std::uint32_t instanceId, std::uint32_t)
    {
        std::lock_guard<std::mutex> lock(placedMutex);
        auto found = placed.find(instanceId);
        if (found == placed.end())
            return "exit portal: not placed yet";
        return "exit portal: " + found->second.note;
    }

    void Forget(std::uint32_t instanceId)
    {
        std::lock_guard<std::mutex> lock(placedMutex);
        placed.erase(instanceId);
    }

    void RegisterScripts()
    {
        new FloorExitCommand();
        new WayBackScript();
        new WayNoneScript();
    }
} // namespace DC::Rifts::Exit

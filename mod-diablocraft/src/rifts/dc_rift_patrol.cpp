/*
 * World of DiabloCraft - recording a patrol route in game (monster spawning S5,
 * docs/proposals/monster-spawning.md 3.6, 4.11).
 *
 *   .dc patrol record start | stop
 *
 * The only routes a patrol walks are the stock patrol paths already on the maps and these: a GM stands in a surveyed
 * dungeon (a rift floor, or the dungeon's own map), types `start`, walks the route, and types `stop`. The walk becomes
 * a stock waypoint_data path in the id range dc_rift_patrol.h reserves for them (the table the 516 stock paths are in,
 * which WaypointMgr loads and MotionMaster::MoveWaypoint walks) plus a dc_rift_route row (source 'alex') tying it to
 * the nearest anchor, and the spawner has it at once: the next floor to open may use it. generate_rift_patrols.py
 * --export brings the points into the committed sheet and generate_rift_survey.py --export brings the route row.
 *
 * Built on the stock systems: WaypointMgr::ReloadPath (what the stock `.wp reload` calls) makes the new path live; the
 * command is the module's ordinary CommandScript. Ours: the sampler, which a stock command does not have, and
 * dc_rift_patrol.h's rules.
 *
 * The point spacing is the `patrol_record_step_yards` row of rifts.csv, blank until it is set; `start` refuses while
 * it is blank. A second `start` throws the walk so far away and begins again. A walk left running when its GM logs out
 * is dropped by the next `start` of that GM; it records nothing by itself.
 */

#include "dc_rift_patrol.h"
#include "dc_rift_spawner.h"
#include "dc_rifts_internal.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "DatabaseEnv.h"
#include "Map.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WaypointMgr.h"
#include "WorldSession.h"

#include <atomic>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace DC::Rifts::Spawner
{
    namespace
    {
        using namespace Patrol;

        std::mutex recordingMutex;
        std::map<uint64, Recording> recordings; // by player guid
        std::atomic<unsigned> recording{
            0}; // how many walks are being recorded: the sampler asks this before taking the lock

        bool Fail(ChatHandler* handler, std::string const& text)
        {
            handler->SendSysMessage(text);
            handler->SetSentErrorMessage(true);
            return false;
        }

        std::vector<Spawn::Anchor> LoadAnchors(std::string const& dungeon)
        {
            std::vector<Spawn::Anchor> out;
            if (QueryResult rows = WorldDatabase.Query("SELECT `anchor`, `area`, `x`, `y`, `z`, `o` FROM "
                                                       "`dc_rift_anchor` WHERE `dungeon` = {} ORDER BY `anchor`",
                                                       Quote(dungeon)))
                do
                {
                    Field* f = rows->Fetch();
                    Spawn::Anchor anchor;
                    anchor.id = f[0].Get<uint32>(), anchor.area = f[1].Get<uint32>();
                    anchor.x = static_cast<float>(f[2].Get<double>()),
                    anchor.y = static_cast<float>(f[3].Get<double>()),
                    anchor.z = static_cast<float>(f[4].Get<double>()),
                    anchor.o = static_cast<float>(f[5].Get<double>());
                    out.push_back(anchor);
                } while (rows->NextRow());
            return out;
        }

        // The surveyed dungeon the GM stands in: the rift floor's own dungeon, or else the dungeon of this map (where
        // two share a map, the one with an anchor nearest him).
        bool Locate(Player* player, std::string& dungeon, std::string& why)
        {
            Map* map = player->GetMap();
            Rift view;
            bool inRift;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                inRift = live.View(map->GetInstanceId(), map->GetId(), view);
            }
            std::vector<std::string> candidates;
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                for (Rifts::Dungeon const& row : pool)
                    if (inRift ? row.dungeonId == view.dungeonId : row.mapId == map->GetId())
                        candidates.push_back(row.name);
            }
            Point const here{player->GetPositionX(), player->GetPositionY(), player->GetPositionZ()};
            double best = 0;
            for (std::string const& name : candidates)
            {
                std::vector<Spawn::Anchor> anchors = LoadAnchors(name);
                int const near = NearestAnchor(anchors, here);
                if (near < 0)
                    continue;
                double const distance = Distance({anchors[near].x, anchors[near].y, anchors[near].z}, here);
                if (dungeon.empty() || distance < best)
                    dungeon = name, best = distance;
            }
            if (dungeon.empty())
                why = "No surveyed dungeon here: stand in a rift floor, or in a dungeon on the rift list.";
            return !dungeon.empty();
        }

        class PatrolSampler final : public PlayerScript
        {
        public:
            PatrolSampler()
                : PlayerScript("dc_rift_patrol_sampler", {PLAYERHOOK_ON_UPDATE})
            {
            }
            void OnPlayerUpdate(Player* player, uint32) override
            {
                if (!recording.load())
                    return;
                std::lock_guard<std::mutex> lock(recordingMutex);
                auto found = recordings.find(player->GetGUID().GetRawValue());
                if (found != recordings.end())
                    found->second.Add(player->GetMapId(),
                                      {player->GetPositionX(), player->GetPositionY(), player->GetPositionZ()});
            }
        };

        class PatrolCommand final : public CommandScript
        {
        public:
            PatrolCommand()
                : CommandScript("dc_rift_patrol_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // A recording writes the world database, so it is an administrator's, as the touch-up of the survey is.
                static ChatCommandTable record = {
                    {"start", HandleStart, SEC_ADMINISTRATOR, Console::No},
                    {"stop", HandleStop, SEC_ADMINISTRATOR, Console::No},
                };
                static ChatCommandTable patrol = {{"record", record}};
                static ChatCommandTable dc = {{"patrol", patrol}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            static Player* Self(ChatHandler* handler)
            {
                return handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            }

            static bool HandleStart(ChatHandler* handler)
            {
                Player* player = Self(handler);
                std::string dungeon, why;
                if (!player || !Locate(player, dungeon, why))
                    return Fail(handler, why.empty() ? "Not in the world." : why);
                double const step = DC::Tunables::Has("rifts", "patrol_record_step_yards")
                                        ? DC::Tunables::Get("rifts", "patrol_record_step_yards")
                                        : 0.0;
                if (step <= 0)
                    return Fail(
                        handler,
                        "The sheet row rifts.patrol_record_step_yards is blank: set it (`.dc tunables set rifts "
                        "patrol_record_step_yards <yards>`) and start again.");
                {
                    std::lock_guard<std::mutex> lock(recordingMutex);
                    Recording walk(dungeon, step, player->GetMapId());
                    walk.Add(player->GetMapId(),
                             {player->GetPositionX(), player->GetPositionY(), player->GetPositionZ()});
                    if (recordings.erase(player->GetGUID().GetRawValue()) == 0)
                        ++recording;
                    recordings.emplace(player->GetGUID().GetRawValue(), std::move(walk));
                }
                handler->PSendSysMessage(
                    "Recording a patrol route in {}: walk it, then `.dc patrol record stop`. A point is kept every {} "
                    "yards.",
                    dungeon, step);
                return true;
            }

            static bool HandleStop(ChatHandler* handler)
            {
                Player* player = Self(handler);
                if (!player)
                    return Fail(handler, "Not in the world.");
                Recording walk("", 0, 0);
                {
                    std::lock_guard<std::mutex> lock(recordingMutex);
                    auto found = recordings.find(player->GetGUID().GetRawValue());
                    if (found == recordings.end())
                        return Fail(handler, "No route is being recorded: `.dc patrol record start` first.");
                    // The walk is on the map it started on; stopping anywhere else would save points that are not
                    // on the leader's map. The recording stays, so go back and stop.
                    if (!found->second.OnMap(player->GetMapId()))
                        return Fail(handler, "You left the map the route was recorded on: go back to it and `.dc "
                                             "patrol record stop`, or `start` again.");
                    walk = std::move(found->second);
                    recordings.erase(found);
                    --recording;
                }
                walk.Finish(player->GetMapId(),
                            {player->GetPositionX(), player->GetPositionY(), player->GetPositionZ()});
                if (!walk.Usable())
                    return Fail(handler, "That walk is one spot: nothing recorded. Start again and walk the route.");
                std::vector<Spawn::Anchor> anchors = LoadAnchors(walk.Dungeon());
                int const near = NearestAnchor(anchors, walk.Points().front());
                if (near < 0)
                    return Fail(handler, "The dungeon has no anchor to tie the route to; nothing recorded.");
                std::uint32_t highest = 0;
                if (QueryResult rows = WorldDatabase.Query(
                        "SELECT MAX(`id`) FROM `waypoint_data` WHERE `id` BETWEEN {} AND {}", RouteFirst, RouteLast))
                    if (!rows->Fetch()[0].IsNull())
                        highest = rows->Fetch()[0].Get<uint32>();
                if (QueryResult rows = WorldDatabase.Query(
                        "SELECT MAX(`path_id`) FROM `dc_rift_route` WHERE `path_id` BETWEEN {} AND {}", RouteFirst,
                        RouteLast))
                    if (!rows->Fetch()[0].IsNull())
                        highest = std::max<std::uint32_t>(highest, rows->Fetch()[0].Get<uint32>());
                std::uint32_t const path = NextPathId(highest);
                if (!path)
                    return Fail(handler, "The reserved range of route ids is full; nothing recorded.");

                WorldDatabaseTransaction transaction = WorldDatabase.BeginTransaction();
                for (std::string const& sql : Statements(walk.Dungeon(), path, anchors[near].id, walk.Points()))
                    transaction->Append(sql);
                if (!WorldDatabase.AsyncCommitTransaction(transaction).m_future.get())
                    return Fail(handler, "The world database refused the route; nothing recorded.");
                sWaypointMgr->ReloadPath(path);
                Point const& first = walk.Points().front();
                AddRoute(walk.Dungeon(), path, anchors[near].id, first.x, first.y, first.z);
                handler->PSendSysMessage(
                    "Recorded route {} in {}: {} points, {} yards, tied to anchor {}. The next floor to open may "
                    "give a patrol at that anchor this route; a floor already open keeps what stands on it.",
                    path, walk.Dungeon(), walk.Points().size(), Length(walk.Points()), anchors[near].id);
                return true;
            }
        };
    } // namespace

    void RegisterPatrol()
    {
        new PatrolSampler();
        new PatrolCommand();
    }
} // namespace DC::Rifts::Spawner

/*
 * World of DiabloCraft - the rift spawner (monster spawning S2). See dc_rift_spawner.h; the picks are dc_rift_spawn.h's.
 *
 * Built on the stock systems wherever they serve (monster-spawning.md section 6, "Built clean"). Monsters are placed with
 * Map::SummonCreature, each spot snapped to ground the anchor can reach (Map::CanReachPositionAndGetValidCoords, the test
 * WalkableSpawnPoint uses for the Guardian). The dungeon's own monsters are refused before they exist by core patch 0004's
 * CanWorldObjectSpawn hook, as dc_world_areas.cpp uses it. Elite packs are SpawnElitePack, unchanged. Doors are opened through the door's own state.
 *
 * Patrols (S5): the leader walks a stock waypoint_data path with MotionMaster::MoveWaypoint, the repeating walk the dungeon's own patrolling
 * monsters use (MotionMaster::MovePath is a one-shot spline), and the others follow it with MoveFollow.
 *
 * Fighting as one: stock assistance stays on, and the link copies CreatureGroup::MemberEngagingTarget (CreatureGroups.cpp:202-240),
 * because a summon cannot join a stock formation, which finds its members by spawn id.
 *
 * Ours: the picks (dc_rift_spawn.h; the stock pools cannot know the mode, the set or the floor, plan 3.8) and the link's registry.
 */

#include "dc_rift_spawner.h"

#include "../monsters/dc_family_ai.h"
#include "../monsters/affixes/dc_affixes.h"
#include "dc_rift_spawn.h"
#include "dc_rifts_internal.h"
#include "../common/dc_tunables.h"

#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "GameTime.h"
#include "Log.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "Timer.h"
#include "TypeContainerVisitor.h"
#include "WaypointMgr.h"
#include "WorldSession.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <unordered_map>
#include <unordered_set>

namespace DC::Rifts::Spawner
{
    namespace
    {
        using namespace Spawn;

        // --- the sheets, read from the world database (spawn_sheets_0001.sql, rift_survey_0001.sql)
        // -------------------------------------

        struct Loaded
        {
            Sheets sheets;
            std::map<std::string, Survey> dungeons;
            std::unordered_map<std::uint32_t, std::unordered_set<std::uint32_t>>
                refused; // map id -> creature spawn ids that become anchors
            unsigned routes = 0;
        };

        std::mutex loadedMutex;
        std::shared_ptr<Loaded const> loaded;

        std::shared_ptr<Loaded const> Sheet()
        {
            std::lock_guard<std::mutex> lock(loadedMutex);
            return loaded;
        }

        bool Build(Loaded& out, std::string& error)
        {
            auto query = [&](char const* sql, char const* table) -> QueryResult
            {
                QueryResult result = WorldDatabase.Query(sql);
                if (!result)
                    error = std::string(table) +
                            " is empty or missing; apply spawn_sheets_0001.sql and rift_survey_0001.sql";
                return result;
            };
            std::map<std::string, unsigned> monsterAt;
            unsigned sitOut = 0;
            QueryResult rows = query("SELECT monster, entry, family, role, solo, wander_yards FROM dc_monster_spawn "
                                     "WHERE entry IS NOT NULL ORDER BY monster",
                                     "dc_monster_spawn");
            if (!rows)
                return false;
            do
            {
                Field* f = rows->Fetch();
                Monster monster;
                monster.name = f[0].Get<std::string>();
                monster.entry = f[1].Get<std::uint32_t>();
                monster.family = f[2].Get<std::string>();
                monster.solo = f[4].Get<uint8>() != 0;
                monster.wanderYards = f[5].Get<double>();
                if (!RoleOf(f[3].Get<std::string>(), monster.role))
                {
                    error = "dc_monster_spawn: role '" + f[3].Get<std::string>() + "' of " + monster.name +
                            " is not melee, ranged, caster or big";
                    return false;
                }
                // A monster whose creature row does not exist yet sits out (3.2): sets switch on as families land.
                if (!sObjectMgr->GetCreatureTemplate(monster.entry))
                {
                    ++sitOut;
                    continue;
                }
                monsterAt[monster.name] = static_cast<unsigned>(out.sheets.monsters.size());
                out.sheets.monsters.push_back(monster);
            } while (rows->NextRow());

            rows = query("SELECT set_id, name, weight, nephalem, `greater` FROM dc_monster_set ORDER BY set_id",
                         "dc_monster_set");
            if (!rows)
                return false;
            std::map<std::uint32_t, unsigned> setAt;
            do
            {
                Field* f = rows->Fetch();
                MonsterSet set;
                set.id = f[0].Get<std::uint32_t>();
                set.name = f[1].Get<std::string>();
                set.weight = f[2].Get<double>();
                set.nephalem = f[3].Get<uint8>() != 0;
                set.greater = f[4].Get<uint8>() != 0;
                setAt[set.id] = static_cast<unsigned>(out.sheets.sets.size());
                out.sheets.sets.push_back(set);
            } while (rows->NextRow());

            rows = query("SELECT set_id, monster FROM dc_monster_set_member ORDER BY set_id, monster",
                         "dc_monster_set_member");
            if (!rows)
                return false;
            do
            {
                Field* f = rows->Fetch();
                auto set = setAt.find(f[0].Get<std::uint32_t>());
                auto monster = monsterAt.find(f[1].Get<std::string>());
                if (set != setAt.end() && monster != monsterAt.end())
                    out.sheets.sets[set->second].members.push_back(monster->second);
            } while (rows->NextRow());

            rows =
                query("SELECT set_id, family, weight, clusterable FROM dc_monster_set_family ORDER BY set_id, family",
                      "dc_monster_set_family");
            if (!rows)
                return false;
            do
            {
                Field* f = rows->Fetch();
                auto set = setAt.find(f[0].Get<std::uint32_t>());
                if (set == setAt.end())
                    continue;
                SetFamily family;
                family.family = f[1].Get<std::string>();
                family.weight = f[2].Get<double>();
                family.clusterable = f[3].Get<uint8>() != 0;
                // The generator said the family clusters from all its monsters; the ones that sit out may have been the
                // only melee or ranged.
                bool still = false;
                for (unsigned index : out.sheets.sets[set->second].members)
                {
                    Monster const& monster = out.sheets.monsters[index];
                    still = still || (monster.family == family.family && !monster.solo &&
                                      (monster.role == Melee || monster.role == Ranged));
                }
                family.clusterable = family.clusterable && still;
                out.sheets.sets[set->second].families.push_back(family);
            } while (rows->NextRow());

            rows = query("SELECT `size`, family, bodies_min, bodies_max, melee_min, melee_max, ranged_min, ranged_max, "
                         "caster_min, caster_max, "
                         "big_min, big_max FROM dc_cluster_recipe",
                         "dc_cluster_recipe");
            if (!rows)
                return false;
            do
            {
                Field* f = rows->Fetch();
                std::string const size = f[0].Get<std::string>();
                if (size != "small" && size != "medium" && size != "large" && size != "patrol")
                    continue;
                Recipe recipe;
                recipe.bodies = {f[2].Get<std::uint32_t>(), f[3].Get<std::uint32_t>()};
                for (unsigned role = 0; role < RoleCount; ++role)
                    recipe.role[role] = {f[4 + 2 * role].Get<std::uint32_t>(), f[5 + 2 * role].Get<std::uint32_t>()};
                out.sheets.recipes[{size == "small"    ? Small
                                    : size == "medium" ? Medium
                                    : size == "large"  ? Large
                                                       : Patrol,
                                    f[1].Get<std::string>()}] = recipe;
            } while (rows->NextRow());
            for (unsigned size = 0; size < SizeCount; ++size)
                if (!out.sheets.recipes.count({size, std::string()}))
                {
                    error = "dc_cluster_recipe has no all-family row for every cluster size";
                    return false;
                }

            rows = query("SELECT tag, anchors_min, anchors_max, small, medium, `large` FROM dc_area_default",
                         "dc_area_default");
            if (!rows)
                return false;
            unsigned tags = 0;
            do
            {
                Field* f = rows->Fetch();
                int const tag = TagIndex(f[0].Get<std::string>().empty() ? ' ' : f[0].Get<std::string>()[0]);
                if (tag < 0)
                    continue;
                AreaDefault& area = out.sheets.defaults[tag];
                area.anchors = {f[1].Get<std::uint32_t>(), f[2].Get<std::uint32_t>()};
                area.size[Small] = f[3].Get<uint8>() != 0;
                area.size[Medium] = f[4].Get<uint8>() != 0;
                area.size[Large] = f[5].Get<uint8>() != 0;
                ++tags;
            } while (rows->NextRow());
            if (tags != 3)
            {
                error = "dc_area_default needs the tags S, M and L";
                return false;
            }

            rows = query(
                "SELECT dungeon, area, tag, density_min, density_max, nospawn FROM dc_rift_area ORDER BY dungeon, area",
                "dc_rift_area");
            if (!rows)
                return false;
            do
            {
                Field* f = rows->Fetch();
                Survey& dungeon = out.dungeons[f[0].Get<std::string>()];
                dungeon.name = f[0].Get<std::string>();
                Area area;
                area.id = f[1].Get<std::uint32_t>();
                area.tag = f[2].Get<std::string>().empty() ? ' ' : f[2].Get<std::string>()[0];
                area.hasDensity = !f[3].IsNull() && !f[4].IsNull();
                if (area.hasDensity)
                    area.density = {f[3].Get<std::uint32_t>(), f[4].Get<std::uint32_t>()};
                area.nospawn = f[5].Get<uint8>() != 0;
                dungeon.areas.push_back(area);
            } while (rows->NextRow());

            rows = query("SELECT dungeon, anchor, area, x, y, z, o, entry_walk_yards FROM dc_rift_anchor ORDER BY "
                         "dungeon, anchor",
                         "dc_rift_anchor");
            if (!rows)
                return false;
            do
            {
                Field* f = rows->Fetch();
                auto dungeon = out.dungeons.find(f[0].Get<std::string>());
                if (dungeon == out.dungeons.end())
                    continue;
                Anchor anchor;
                anchor.id = f[1].Get<std::uint32_t>();
                anchor.area = f[2].Get<std::uint32_t>();
                anchor.x = static_cast<float>(f[3].Get<double>()), anchor.y = static_cast<float>(f[4].Get<double>()),
                anchor.z = static_cast<float>(f[5].Get<double>()), anchor.o = static_cast<float>(f[6].Get<double>());
                anchor.hasWalk = !f[7].IsNull();
                anchor.entryWalk = anchor.hasWalk ? f[7].Get<double>() : 0.0;
                dungeon->second.anchors.push_back(anchor);
            } while (rows->NextRow());

            // The routes a patrol can walk (S5): the stock paths the survey tied to anchors, and the recorded ones. A route whose path is
            // not in waypoint_data with two points is no route.
            rows = query("SELECT dungeon, path_id, anchor, start_x, start_y, start_z FROM dc_rift_route ORDER BY dungeon, path_id",
                         "dc_rift_route");
            if (!rows)
                return false;
            unsigned noPath = 0;
            do
            {
                Field* f = rows->Fetch();
                auto dungeon = out.dungeons.find(f[0].Get<std::string>());
                if (dungeon == out.dungeons.end())
                    continue;
                WaypointPath const* path = sWaypointMgr->GetPath(f[1].Get<std::uint32_t>());
                if (!path || path->Nodes.size() < 2)
                {
                    ++noPath;
                    continue;
                }
                Route route;
                route.path = f[1].Get<std::uint32_t>(), route.anchor = f[2].Get<std::uint32_t>();
                route.x = static_cast<float>(f[3].Get<double>()), route.y = static_cast<float>(f[4].Get<double>()),
                route.z = static_cast<float>(f[5].Get<double>());
                dungeon->second.routes.push_back(route);
                ++out.routes;
            } while (rows->NextRow());
            if (noPath)
                LOG_INFO("server", "[DC spawner] {} routes have no waypoint path of two points and are not walked", noPath);

            // The natives the spawner replaces. Read last, and only when everything above loaded: a floor with no
            // sheets must keep its natives.
            rows = query("SELECT map_id, spawn_guid FROM dc_rift_native_filter", "dc_rift_native_filter");
            if (!rows)
                return false;
            do
            {
                Field* f = rows->Fetch();
                out.refused[f[0].Get<std::uint32_t>()].insert(f[1].Get<std::uint32_t>());
            } while (rows->NextRow());

            unsigned usable = 0;
            for (MonsterSet const& set : out.sheets.sets)
                usable += Usable(out.sheets, set, false) || Usable(out.sheets, set, true);
            if (!usable)
            {
                error = "no monster set can put anything on the ground (every member sits out or every family is held "
                        "back)";
                return false;
            }
            if (sitOut)
                LOG_INFO("server", "[DC spawner] {} monsters have no creature row yet and sit out", sitOut);
            return true;
        }

        // --- the floor's knobs: rifts.csv rows (S1), read each time a floor opens so `.dc tunables reload` is enough
        // -----------------------------

        Knobs ReadKnobs()
        {
            auto number = [](char const* name, double fallback)
            { return DC::Tunables::Has("rifts", name) ? DC::Tunables::Get("rifts", name) : fallback; };
            Knobs knobs;
            knobs.elitePct = number("elite_chance_pct", 0);
            knobs.championPct = number("elite_champion_pct", 50);
            knobs.soloPct = number("solo_share_pct", 0);
            knobs.patrolPct = number("patrol_share_pct", 0);
            knobs.radiusSmallYards = number("cluster_radius_small_yards", 5);
            knobs.entryClearYards = number("entry_clear_yards", 0);
            knobs.minSpacingYards = number("cluster_min_spacing_yards", 0);
            knobs.eliteMin = static_cast<unsigned>(number("elite_packs_min", 0));
            knobs.eliteMax = static_cast<unsigned>(number("elite_packs_max", std::numeric_limits<unsigned>::max()));
            knobs.bodyCap = static_cast<unsigned>(number("floor_body_cap", 0));
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                knobs.championPack = championPackSize;
            }
            if (std::shared_ptr<AffixNumbers const> numbers = Numbers())
            {
                knobs.rareMinionsMax = numbers->rareMinionsMax;
                knobs.hordeMultiplier = numbers->hordeMultiplier;
            }
            return knobs;
        }

        // --- what a floor picked, for `.dc rift picks`, and the sets a run has had
        // --------------------------------------------------------

        struct FloorRecord
        {
            std::uint64_t runId = 0, seed = 0;
            unsigned floor = 0, setId = 0, planned = 0, summoned = 0, failed = 0, doors = 0, elapsedMs = 0;
            bool greater = false;
            std::string dungeon, setName;
            FloorPlan plan;
            std::vector<std::string> lines; // one per placement
        };

        struct RunMemo
        {
            std::uint64_t seed = 0;
            std::vector<unsigned> sets; // the set of each floor, in floor order; 0 where none was picked
        };

        std::mutex recordMutex;
        std::unordered_map<std::uint32_t, std::shared_ptr<FloorRecord const>> records; // by instance id
        std::unordered_map<std::uint64_t, RunMemo> runs;                               // by run id

        // --- the cluster link (3.9.3)
        // -----------------------------------------------------------------------------------------------------

        struct ClusterMember : public DataMap::Base
        {
            std::shared_ptr<std::vector<ObjectGuid>> group;
        };
        struct FloorMark : public DataMap::Base
        {
            bool done = false;
            bool doorsOpen = false; // OpenDoors ran: a door whose grid loads later opens as it comes (LateDoors)
        };

        void Link(std::vector<Creature*> const& members)
        {
            auto group = std::make_shared<std::vector<ObjectGuid>>();
            for (Creature* member : members)
                group->push_back(member->GetGUID());
            for (Creature* member : members)
                member->CustomData.GetDefault<ClusterMember>("DCRiftCluster")->group = group;
        }

        // Wander (3.7): stock random movement round the spot the monster stands on right now, so it is called once the
        // monster is placed and homed, never with the anchor. A summon starts idle, its wander distance 0
        // (Creature::InitEntry), so the distance and the default movement type are set before MoveRandom. Only until the
        // first fight: a rift monster's evade is Park() (dc_rift_ai.cpp), which stands it where it ended and does
        // not restart this. 0 yards stands still.
        void Wander(Creature* creature, double yards)
        {
            if (!creature || yards <= 0)
                return;
            creature->SetWanderDistance(static_cast<float>(yards));
            creature->SetDefaultMovementType(RANDOM_MOTION_TYPE);
            creature->GetMotionMaster()->MoveRandom(static_cast<float>(yards));
        }

        // The monster at its spot: summoned on the anchor, which is ground, then walked out to the spot as far as it
        // can reach (3.3 "Placing a cluster"). A spot with no path at all falls back to the anchor, so a member never
        // stands off the mesh.
        Creature* SummonAt(Map* map, std::uint32_t entry, Anchor const& anchor, Spot spot)
        {
            Creature* creature = map->SummonCreature(entry, Position(anchor.x, anchor.y, anchor.z, anchor.o));
            if (!creature)
                return nullptr;
            float const asked[3] = {anchor.x + spot.dx, anchor.y + spot.dy, anchor.z};
            float x = asked[0], y = asked[1], z = asked[2];
            bool const reached =
                map->CanReachPositionAndGetValidCoords(creature, anchor.x, anchor.y, anchor.z, x, y, z, true, true);
            if (!reached && x == asked[0] && y == asked[1] && z == asked[2])
                x = anchor.x, y = anchor.y, z = anchor.z; // nothing was found: the path never started
            if (x != anchor.x || y != anchor.y || z != anchor.z)
                creature->NearTeleportTo(x, y, z, anchor.o);
            creature->SetHomePosition(x, y, z, anchor.o);
            return creature;
        }

        // A patrol's walk (3.6): the leader on its route's stock path, repeating (MoveWaypoint, as the dungeon's own patrolling monsters
        // walk theirs), the rest following it from where they stand now (MoveFollow, at the distance and the side they stand at).
        // When the leader dies the followers stop following, as a stock formation's members do.
        void Walk(Creature* leader, std::vector<Creature*> const& members, std::uint32_t path)
        {
            leader->GetMotionMaster()->MoveWaypoint(path, true);
            for (Creature* member : members)
                if (member != leader)
                    member->GetMotionMaster()->MoveFollow(leader, leader->GetExactDist2d(member),
                                                          leader->GetRelativeAngle(member));
        }

        // A patrol's start: the route's first point, facing the second (the dungeon's anchor is only what the route was tied to).
        Anchor PatrolStart(Survey const& dungeon, Placement const& placement, Anchor const& anchor)
        {
            Anchor start = anchor;
            for (Route const& route : dungeon.routes)
                if (route.path == placement.route)
                {
                    start.x = route.x, start.y = route.y, start.z = route.z;
                    if (WaypointPath const* path = sWaypointMgr->GetPath(route.path); path && path->Nodes.size() > 1)
                        start.o = std::atan2(path->Nodes[1].Y - route.y, path->Nodes[1].X - route.x);
                }
            return start;
        }

        // An elite pack on the anchor (3.9.2): SpawnElitePack as today, then the pack is linked. A patrol's pack walks its route.
        Creature* SummonElite(Map* map, Sheets const& sheets, Placement const& placement, Anchor const& anchor,
                              unsigned tier)
        {
            Monster const& leader = sheets.monsters[placement.leader];
            CreatureTemplate const* info = sObjectMgr->GetCreatureTemplate(leader.entry);
            Creature* elite = SpawnElitePack(map, leader.entry, Position(anchor.x, anchor.y, anchor.z, anchor.o),
                                             placement.elite == Elite::Rare, tier, info ? info->maxlevel : 1, true, {},
                                             map->GetInstanceId(), nullptr);
            if (!elite)
                return nullptr;
            std::vector<Creature*> pack{elite};
            if (EliteState* state = elite->CustomData.Get<EliteState>("DCRiftElite"))
                for (ObjectGuid guid : state->pack)
                    if (Creature* member = map->GetCreature(guid))
                        pack.push_back(member);
            Link(pack);
            // A patrol's pack walks its route and never wanders (3.7); any other pack mills about its own spots.
            if (placement.kind == Kind::Patrol)
                Walk(elite, pack, placement.route);
            else
                for (Creature* member : pack)
                    Wander(member, leader.wanderYards);
            return elite;
        }

        struct CollectDoors
        {
            std::vector<GameObject*>& out;
            void Visit(std::unordered_map<ObjectGuid, GameObject*>& objects)
            {
                for (auto const& entry : objects)
                    if (entry.second->GetGoType() == GAMEOBJECT_TYPE_DOOR)
                        out.push_back(entry.second);
            }
            template<class T>
            void Visit(std::unordered_map<ObjectGuid, T*>&)
            {
            }
        };

        // 4.13: every door of the floor opens when the floor opens, set open and not deleted.
        unsigned OpenDoors(Map* map)
        {
            std::vector<GameObject*> doors;
            CollectDoors collect{doors};
            TypeContainerVisitor<CollectDoors, MapStoredObjectTypesContainer> visitor(collect);
            visitor.Visit(map->GetObjectsStore());
            for (GameObject* door : doors)
                door->SetGoState(GO_STATE_ACTIVE);
            return static_cast<unsigned>(doors.size());
        }

        char const* SizeWord(Placement const& placement)
        {
            return placement.kind == Kind::Solo      ? "solo"
                   : placement.kind == Kind::Patrol  ? "patrol"
                   : placement.size == Small         ? "small"
                   : placement.size == Medium        ? "medium"
                                                     : "large";
        }

        std::string Describe(Sheets const& sheets, Placement const& placement)
        {
            std::map<std::string, unsigned> counts;
            for (unsigned index : placement.monsters)
                ++counts[sheets.monsters[index].name];
            std::ostringstream text;
            text << "anchor " << placement.anchor << ": ";
            if (placement.elite != Elite::None)
                text << (placement.elite == Elite::Champion ? "champion" : "rare") << " pack of "
                     << sheets.monsters[placement.leader].name << " (replaces a "
                     << (placement.kind == Kind::Patrol ? "" : std::string(SizeWord(placement)) + " ") << placement.family
                     << (placement.kind == Kind::Patrol ? " patrol on route " + std::to_string(placement.route) : " cluster")
                     << ")";
            else
            {
                text << SizeWord(placement);
                if (placement.kind != Kind::Solo)
                    text << " " << placement.family
                         << (placement.kind == Kind::Patrol ? " on route " + std::to_string(placement.route) : " cluster");
                text << ": ";
                for (auto const& [name, count] : counts)
                    text << count << " " << name << "; ";
            }
            return text.str();
        }

        // A rift floor loads its grids as players reach them (core patch 0026), so OpenDoors finds only
        // the doors of grids loaded when the floor opens; any other door of the floor opens when its grid loads.
        class LateDoors final : public AllGameObjectScript
        {
        public:
            LateDoors()
                : AllGameObjectScript("dc_rift_late_doors")
            {
            }

            void OnGameObjectAddWorld(GameObject* go) override
            {
                if (go->GetGoType() != GAMEOBJECT_TYPE_DOOR)
                    return;
                if (FloorMark const* mark = go->GetMap()->CustomData.Get<FloorMark>("DCRiftSpawner"))
                    if (mark->doorsOpen)
                        go->SetGoState(GO_STATE_ACTIVE);
            }
        };

        // --- the native filter (4.8 (a), 3.9.1)
        // --------------------------------------------------------------------------------------------

        class NativeFilter final : public GlobalScript
        {
        public:
            NativeFilter()
                : GlobalScript("dc_rift_native_filter", {GLOBALHOOK_CAN_WORLD_OBJECT_SPAWN})
            {
            }

            // The dungeon's own monsters that the survey turned into anchors never exist; every other spawn is not this
            // script's to say.
            bool CanWorldObjectSpawn(WorldSpawnKind kind, uint32, uint32 spawnId, uint32 mapId, uint32,
                                     Position const&) override
            {
                if ((kind != WorldSpawnKind::Creature && kind != WorldSpawnKind::Vehicle) || !spawnId)
                    return true;
                std::shared_ptr<Loaded const> sheet = Sheet();
                if (!sheet)
                    return true;
                auto map = sheet->refused.find(mapId);
                return map == sheet->refused.end() || !map->second.count(spawnId);
            }
        };

        // Reads the spawn sheets and the dungeons' anchors; the message says what loaded or what is missing.
        bool Load(std::string& message)
        {
            auto fresh = std::make_shared<Loaded>();
            std::string error;
            if (!Build(*fresh, error))
            {
                message = error;
                return false;
            }
            std::ostringstream text;
            text << fresh->sheets.sets.size() << " monster sets, " << fresh->sheets.monsters.size() << " monsters, "
                 << fresh->dungeons.size() << " dungeons, " << fresh->routes << " patrol routes, " << fresh->refused.size()
                 << " maps with refused natives";
            message = text.str();
            std::lock_guard<std::mutex> lock(loadedMutex);
            loaded = fresh;
            return true;
        }

        class SpawnerWorld final : public WorldScript
        {
        public:
            SpawnerWorld()
                : WorldScript("dc_rift_spawner_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                std::string message;
                if (!Load(message))
                    LOG_ERROR("server", "[DC spawner] {}; rift floors keep their natives and place nothing", message);
            }
        };
    } // namespace

    void OpenFloor(Map* map, unsigned tier)
    {
        if (!map || !map->IsDungeon())
            return;
        FloorMark* mark = map->CustomData.GetDefault<FloorMark>("DCRiftSpawner");
        if (mark->done)
            return;
        Rift view;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            if (!live.View(map->GetInstanceId(), map->GetId(), view))
                return; // not a live rift floor (yet): try again on the next update
        }
        mark->done = true;

        std::shared_ptr<Loaded const> sheet = Sheet();
        if (!sheet)
        {
            LOG_ERROR("server", "[DC spawner] floor {} of run {} has no sheets loaded and stays empty", view.floor,
                      view.id);
            return;
        }
        std::string dungeonName;
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            for (Rifts::Dungeon const& dungeon : pool)
                if (dungeon.dungeonId == view.dungeonId)
                    dungeonName = dungeon.name;
        }
        auto dungeon = sheet->dungeons.find(dungeonName);
        if (dungeon == sheet->dungeons.end())
        {
            LOG_ERROR("server", "[DC spawner] dungeon '{}' (floor {} of run {}) is not in the survey and stays empty",
                      dungeonName, view.floor, view.id);
            return;
        }

        uint32 const started = getMSTime();
        auto record = std::make_shared<FloorRecord>();
        record->runId = view.id, record->floor = view.floor, record->dungeon = dungeonName,
        record->greater = view.mode == "gr";
        unsigned previous = 0;
        {
            std::lock_guard<std::mutex> lock(recordMutex);
            RunMemo& memo = runs[view.id];
            if (!memo.seed)
                memo.seed = Engine()() | 1;
            record->seed = memo.seed;
            if (view.floor > 1 && memo.sets.size() >= view.floor - 1)
                previous = memo.sets[view.floor - 2];
        }
        Rng rng(record->seed, view.floor);
        int const set = PickSet(sheet->sheets, record->greater, previous, rng);
        if (set < 0)
        {
            LOG_ERROR("server",
                      "[DC spawner] floor {} of run {}: no monster set is usable in a {} rift; the floor stays empty",
                      view.floor, view.id, record->greater ? "Greater" : "Nephalem");
            return;
        }
        MonsterSet const& chosen = sheet->sheets.sets[set];
        record->setId = chosen.id, record->setName = chosen.name;
        record->plan = PlanFloor(sheet->sheets, set, dungeon->second, ReadKnobs(), rng);
        {
            std::lock_guard<std::mutex> lock(recordMutex);
            RunMemo& memo = runs[view.id];
            memo.sets.resize(std::max<std::size_t>(memo.sets.size(), view.floor), 0);
            memo.sets[view.floor - 1] = chosen.id;
        }
        CharacterDatabase.Execute("UPDATE dc_rift_floor SET monster_set={} WHERE run_id={} AND floor={}", chosen.id,
                                  view.id, view.floor);

        record->doors = OpenDoors(map);
        mark->doorsOpen = true;
        for (Placement const& placement : record->plan.placements)
        {
            auto anchor = std::find_if(dungeon->second.anchors.begin(), dungeon->second.anchors.end(),
                                       [&](Anchor const& a) { return a.id == placement.anchor; });
            record->lines.push_back(Describe(sheet->sheets, placement));
            if (anchor == dungeon->second.anchors.end())
                continue;
            // A patrol stands where its route starts; anything else at its anchor.
            Anchor const where =
                placement.kind == Kind::Patrol ? PatrolStart(dungeon->second, placement, *anchor) : *anchor;
            if (placement.elite != Elite::None)
            {
                ++record->planned;
                (SummonElite(map, sheet->sheets, placement, where, tier) ? record->summoned : record->failed) += 1;
                continue;
            }
            std::vector<Creature*> members;
            Creature* leader = nullptr; // a patrol's: the first monster
            for (std::size_t i = 0; i < placement.monsters.size(); ++i)
            {
                Monster const& monster = sheet->sheets.monsters[placement.monsters[i]];
                ++record->planned;
                // A patrol's leader (the first) stands on the route's first point.
                if (Creature* creature = SummonAt(map, monster.entry, where,
                                                  placement.kind == Kind::Patrol && i == 0 ? Spot{} : placement.spots[i]))
                {
                    members.push_back(creature);
                    if (i == 0)
                        leader = creature;
                    if (placement.kind != Kind::Patrol) // a patrol member walks its route, it does not wander (3.7)
                        Wander(creature, monster.wanderYards);
                    ++record->summoned;
                }
                else
                    ++record->failed;
            }
            if (placement.kind != Kind::Solo)
                Link(members);
            if (placement.kind == Kind::Patrol && leader)
                Walk(leader, members, placement.route);
        }
        record->elapsedMs = getMSTimeDiff(started, getMSTime());
        LOG_INFO("server",
                 "[DC spawner] run {} floor {} ({}, {}): set {} '{}', {} clusters ({} patrols), {} solos, {} elite packs, {} bodies "
                 "planned, {} summoned, {} failed, "
                 "{} doors opened, {} ms, seed {}",
                 view.id, view.floor, dungeonName, record->greater ? "Greater" : "Nephalem", chosen.id, chosen.name,
                 record->plan.clusters, record->plan.patrols, record->plan.solos, record->plan.elitePacks, record->planned, record->summoned,
                 record->failed, record->doors, record->elapsedMs, record->seed);
        std::lock_guard<std::mutex> lock(recordMutex);
        records[map->GetInstanceId()] = record;
    }

    std::uint64_t RunSeed(std::uint64_t runId)
    {
        std::lock_guard<std::mutex> lock(recordMutex);
        auto found = runs.find(runId);
        return found == runs.end() ? 0 : found->second.seed;
    }

    void FloorGone(std::uint32_t instanceId, std::uint64_t runId, bool runEnds)
    {
        std::lock_guard<std::mutex> lock(recordMutex);
        records.erase(instanceId);
        if (runEnds)
            runs.erase(runId);
    }

    void MemberEngaged(Creature* member, Unit* target)
    {
        static thread_local bool linking = false;
        if (linking || !member || !target)
            return;
        ClusterMember* tag = member->CustomData.Get<ClusterMember>("DCRiftCluster");
        Map* map = member->GetMap();
        if (!tag || !tag->group || !map)
            return;
        linking = true;
        for (ObjectGuid guid : *tag->group)
        {
            Creature* other = guid == member->GetGUID() ? nullptr : map->GetCreature(guid);
            if (other && other->IsAlive() && !other->IsInCombat() && !other->IsCharmed() && other->AI())
                other->AI()->AttackStart(target);
        }
        linking = false;
    }

    bool Report(Map const* map, std::vector<std::string>& lines)
    {
        std::shared_ptr<FloorRecord const> record;
        {
            std::lock_guard<std::mutex> lock(recordMutex);
            auto found = map ? records.find(map->GetInstanceId()) : records.end();
            if (found == records.end())
                return false;
            record = found->second;
        }
        std::ostringstream head;
        head << "run " << record->runId << " floor " << record->floor << ", " << record->dungeon << ", "
             << (record->greater ? "Greater" : "Nephalem") << " Rift: set " << record->setId << " '" << record->setName
             << "', seed " << record->seed;
        lines.push_back(head.str());
        std::ostringstream sum;
        sum << record->plan.clusters << " clusters (" << record->plan.patrols << " patrols), " << record->plan.solos << " solos, " << record->plan.elitePacks
            << " elite packs; " << record->planned << " bodies planned, " << record->summoned << " summoned, "
            << record->failed << " failed; " << record->doors << " doors opened; the burst took " << record->elapsedMs
            << " ms";
        if (record->plan.cutByCap)
            sum << "; the body cap left " << record->plan.cutByCap << " anchors empty";
        lines.push_back(sum.str());
        unsigned const shown = std::min<std::size_t>(record->lines.size(), 40);
        for (unsigned i = 0; i < shown; ++i)
            lines.push_back(record->lines[i]);
        if (record->lines.size() > shown)
            lines.push_back("... and " + std::to_string(record->lines.size() - shown) + " more");
        return true;
    }

    void AddRoute(std::string const& dungeon, std::uint32_t path, unsigned anchor, float x, float y, float z)
    {
        std::lock_guard<std::mutex> lock(loadedMutex);
        if (!loaded)
            return;
        auto fresh = std::make_shared<Loaded>(*loaded);
        auto found = fresh->dungeons.find(dungeon);
        if (found == fresh->dungeons.end())
            return;
        Route route;
        route.path = path, route.anchor = anchor, route.x = x, route.y = y, route.z = z;
        found->second.routes.push_back(route);
        ++fresh->routes;
        loaded = fresh;
    }

    bool Reload(std::string& message)
    {
        return Load(message);
    }

    void RegisterScripts()
    {
        new NativeFilter();
        new LateDoors();
        new SpawnerWorld();
        RegisterPatrol();
        RegisterTouchUp();
    }
} // namespace DC::Rifts::Spawner

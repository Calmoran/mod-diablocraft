/*
 * World of DiabloCraft - where and when pylons and shrines stand in rifts (pylons and shrines Part P4,
 * docs/proposals/pylons.md 4.4, 4.5, 4.6, 6.5, 6.6, 6.11).
 *
 * A Nephalem floor rolls its spots when it opens and everything rolled stands at once; a Greater Rift floor's spot
 * rolls when the first player comes near, looked for every pylon_gr_check_ms. The objects are P3's (Combat::Pylons::
 * Spawn) and go when their floor's map closes. On arriving off the rift floors a player's pylon buffs end; arriving on
 * a Greater Rift floor ends their shrine buffs (6.11). The decisions are dc_rift_pylon.h's.
 *
 *   .dc pylon spot here | show [yards] | clear
 *
 * A spot belongs to a dungeon row: the survey gives one at the centre of each M and L area (rift_pylon_spots.csv, table
 * dc_rift_pylon_spot), and a GM adds, moves and removes them on dev standing in the dungeon (a rift floor, or the
 * dungeon's own map). `here` moves the spot of his that is within NEAR_YARDS of him, else adds one at his feet; `clear`
 * removes the nearest one within NEAR_YARDS; `show` marks the spots round him. The edits go into the dev world
 * database; the next floor to open reads the table, and generate_rift_survey.py --export writes them into the committed
 * sheet, as `.dc anchor` and `.dc floor exit` do.
 *
 * Built on the stock systems: the markers are what `.wp show` stands on a path, creature 1 "Waypoint (Only GM can see
 * it)"; the commands are the module's ordinary CommandScript tables, shaped as `.dc floor exit`. Ours: the edits, which
 * dc_rift_pylon.h builds as SQL.
 *
 * Internal to the rifts folder.
 */

#include "dc_rift_pylon.h"
#include "dc_rift_spawner.h"
#include "dc_rifts_internal.h"
#include "../combat/dc_pylons.h"
#include "../combat/dc_spell_shells.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "Map.h"
#include "Player.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "WorldSession.h"

#include <algorithm>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Rifts::Pylons
{
    namespace
    {
        // The GM markers of `show` live this long and take themselves down. Constant: a lookup aid, not gameplay.
        constexpr std::uint32_t MARKER_ENTRY = 1; // creature_template 1: stock "Waypoint (Only GM can see it)"
        constexpr std::uint32_t MARKER_MS = 60000;
        constexpr float SHOW_YARDS = 100.0f; // `show` with no number: the spots this near

        std::vector<Spot> LoadSpots(std::string const& dungeon)
        {
            std::vector<Spot> out;
            if (QueryResult rows = WorldDatabase.Query("SELECT `spot`, `area`, `x`, `y`, `z`, `o`, `entry_walk_yards`, "
                                                       "`source` FROM `dc_rift_pylon_spot` WHERE `dungeon` = {} "
                                                       "ORDER BY `spot`",
                                                       TouchUp::Quote(dungeon)))
                do
                {
                    Field* f = rows->Fetch();
                    Spot row;
                    row.id = f[0].Get<uint32>(), row.area = f[1].Get<uint32>(), row.x = f[2].Get<double>(),
                    row.y = f[3].Get<double>(), row.z = f[4].Get<double>(), row.o = f[5].Get<double>(),
                    row.walk = f[6].IsNull() ? -1 : f[6].Get<double>(), row.alex = f[7].Get<std::string>() == "alex";
                    out.push_back(row);
                } while (rows->NextRow());
            return out;
        }

        namespace Buffs = DC::Combat::Pylons;

        // The kinds a placement picks from, in the buff sheet's order (index i is Buffs::Kind i): even, Fortune at its
        // own weight (shrine_fortune_weight; blank: no Fortune Shrine, 6.5).
        std::vector<Kind> PlacementKinds()
        {
            std::vector<Kind> out;
            for (unsigned i = 0; i < Buffs::KindCount; ++i)
            {
                Buffs::Kind const kind = static_cast<Buffs::Kind>(i);
                double weight = 1;
                if (kind == Buffs::Kind::Fortune)
                    weight = DC::Tunables::Has("rifts", "shrine_fortune_weight")
                                 ? DC::Tunables::Get("rifts", "shrine_fortune_weight")
                                 : 0;
                out.push_back(Kind{Buffs::Names[i], Buffs::IsPylon(kind), weight});
            }
            return out;
        }

        // Every number is a row of rifts.csv; a blank one turns that rift kind's placement off (logged), never a
        // number of ours.
        bool Knobs(std::vector<char const*> const& names, std::vector<double>& out, char const* what)
        {
            out.clear();
            for (char const* name : names)
            {
                if (!DC::Tunables::Has("rifts", name))
                {
                    LOG_WARN("server", "[DC pylons] rifts.csv {} is blank: no {} pylons or shrines", name, what);
                    return false;
                }
                out.push_back(DC::Tunables::Get("rifts", name));
            }
            return true;
        }

        // One floor's pylons, in its map's own data (read and written on the map's update only).
        struct FloorPylons : DataMap::Base
        {
            bool opened = false, greater = false;
            std::uint64_t run = 0, seed = 0;
            unsigned floor = 0;
            std::vector<Spot> waiting; // a Greater Rift floor's spots not rolled yet
            std::vector<Spot> placed;  // what stands on the floor, for the spacing
            std::uint32_t sinceCheck = 0;
        };

        // What each Greater Rift run has had: its floors may update on different threads.
        std::mutex runMutex;
        std::unordered_map<std::uint64_t, RunHad> runsHad;

        void Stand(Map* map, FloorPylons& state, Spot const& spot, std::size_t kind)
        {
            if (Buffs::Spawn(map, static_cast<Buffs::Kind>(kind), Position(spot.x, spot.y, spot.z, spot.o)))
                state.placed.push_back(spot);
            else
                LOG_ERROR("server", "[DC pylons] run {} floor {}: the {} at spot {} would not stand", state.run,
                          state.floor, Buffs::Names[kind], spot.id);
        }

        // The floor opens: a Nephalem floor's plan stands at once; a Greater Rift floor's spots wait for a player.
        void Open(Map* map, FloorPylons& state, Rift const& view)
        {
            state.opened = true;
            state.run = view.id, state.floor = view.floor, state.greater = view.mode == "gr";
            state.seed = Spawner::RunSeed(view.id);
            std::string dungeonName;
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                for (Dungeon const& dungeon : pool)
                    if (dungeon.dungeonId == view.dungeonId)
                        dungeonName = dungeon.name;
            }
            if (!state.seed || dungeonName.empty())
                return; // the spawner left the floor empty (it logged why): nothing to place on either
            double const clear =
                DC::Tunables::Has("rifts", "entry_clear_yards") ? DC::Tunables::Get("rifts", "entry_clear_yards") : 0;
            // ponytail: one query per floor open on the map's thread; cache with the spawner's sheet if it shows in
            // the map update time.
            std::vector<Spot> const spots = Usable(LoadSpots(dungeonName), clear);
            if (state.greater)
            {
                state.waiting = spots;
                return;
            }
            std::vector<double> k;
            if (!Knobs({"pylon_nr_pylon_chance_pct", "pylon_nr_shrine_chance_pct", "pylon_nr_pylons_min",
                        "pylon_nr_pylons_max", "pylon_nr_shrines_min", "pylon_nr_shrines_max", "pylon_min_spacing_yd"},
                       k, "Nephalem"))
                return;
            NephalemKnobs const knobs{k[0], k[1], static_cast<unsigned>(k[2]), static_cast<unsigned>(k[3]),
                                      static_cast<unsigned>(k[4]), static_cast<unsigned>(k[5]), k[6]};
            Spawn::Rng rng = StreamOf(state.seed, state.floor);
            for (Placed const& placed : PlanNephalem(spots, PlacementKinds(), knobs, rng))
                Stand(map, state, spots[placed.spot], placed.kind);
        }

        // A Greater Rift floor: each spot a player has come near rolls once (6.5 (a), with the minimum spacing).
        void Approach(Map* map, FloorPylons& state)
        {
            std::vector<double> k;
            if (!Knobs({"pylon_gr_base_chance_pct", "pylon_gr_full_chance_progress_pct", "pylon_gr_check_yards",
                        "pylon_gr_max_per_run", "pylon_min_spacing_yd"},
                       k, "Greater Rift"))
            {
                state.waiting.clear();
                return;
            }
            GreaterKnobs const knobs{k[0], k[1], k[2], static_cast<unsigned>(k[3]), k[4]};
            Rift view;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                if (!live.View(map->GetInstanceId(), map->GetId(), view))
                    return;
            }
            double const share = view.requiredUnits ? 100.0 * view.progress / view.requiredUnits : 0;
            std::vector<Kind> const kinds = PlacementKinds();
            std::lock_guard<std::mutex> lock(runMutex);
            RunHad& had = runsHad[state.run];
            for (auto spot = state.waiting.begin(); spot != state.waiting.end();)
            {
                if (MayRoll(view.state, view.guardianInstance, had, knobs) != NoRoll::None)
                {
                    state.waiting.clear(); // the Guardian is up, or the run has had its four: no spot rolls again
                    return;
                }
                bool near = false;
                map->DoForAllPlayers([&](Player* player)
                                     { near = near || Within(*spot, player->GetPositionX(), player->GetPositionY(),
                                                             player->GetPositionZ(), knobs.checkYards); });
                if (!near)
                {
                    ++spot;
                    continue;
                }
                int const pick = ApproachGreater(state.seed, state.floor, *spot, share, knobs, kinds, state.placed, had);
                Spot const rolled = *spot;
                spot = state.waiting.erase(spot); // a spot rolls once, whatever it rolled
                if (pick >= 0)
                    Stand(map, state, rolled, static_cast<std::size_t>(pick));
            }
        }

        // 6.11: what a player's arrival on a map ends.
        class LeaveRules final : public PlayerScript
        {
        public:
            LeaveRules()
                : PlayerScript("dc_pylon_leave_rules", {PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerMapChanged(Player* player) override
            {
                if (!player)
                    return;
                Map* map = player->GetMap();
                Rift view;
                bool onFloor = false;
                if (map && map->IsDungeon())
                {
                    std::lock_guard<std::mutex> lock(riftMutex);
                    onFloor = live.View(map->GetInstanceId(), map->GetId(), view);
                }
                std::optional<Leaves> const when = Leaving(onFloor, onFloor && view.mode == "gr");
                if (!when)
                    return;
                for (unsigned i = 0; i < Buffs::KindCount; ++i)
                {
                    Buffs::Kind const kind = static_cast<Buffs::Kind>(i);
                    // EndsKnockOnly: Speed's knock-up is part P2's; until it lands there is
                    // nothing of Speed's to end, and its speed stays.
                    if (FateOf(Buffs::IsPylon(kind), kind == Buffs::Kind::Speed, *when) == Fate::Ends)
                        if (std::uint32_t const record = DC::Combat::Shells::PylonBuffFor(Buffs::Names[i]))
                            player->RemoveAurasDueToSpell(record);
                }
            }
        };

        bool Fail(ChatHandler* handler, std::string const& text)
        {
            handler->SendSysMessage(text);
            handler->SetSentErrorMessage(true);
            return false;
        }

        class PylonSpotCommand final : public CommandScript
        {
        public:
            PylonSpotCommand()
                : CommandScript("dc_pylon_spot_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // Looking is for any GM; an edit writes the world database, so it is an administrator's, as the
                // touch-up is.
                static ChatCommandTable spot = {
                    {"here", HandleHere, SEC_ADMINISTRATOR, Console::No},
                    {"show", HandleShow, SEC_GAMEMASTER, Console::No},
                    {"clear", HandleClear, SEC_ADMINISTRATOR, Console::No},
                };
                static ChatCommandTable pylon = {{"spot", spot}};
                static ChatCommandTable dc = {{"pylon", pylon}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            static Player* Self(ChatHandler* handler)
            {
                return handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            }

            // `.dc pylon spot here`: a spot of his within NEAR_YARDS moves to his feet; none near adds one there.
            static bool HandleHere(ChatHandler* handler)
            {
                Player* player = Self(handler);
                Dungeon dungeon;
                if (!player || !Exit::DungeonOf(player, dungeon))
                    return Fail(handler, "Stand in a rift floor, or in a dungeon on the rift list.");
                std::vector<Spot> const rows = LoadSpots(dungeon.name);
                Spot at;
                at.x = player->GetPositionX(), at.y = player->GetPositionY(), at.z = player->GetPositionZ(),
                at.o = player->GetOrientation();
                int const near = NearestSpot(rows, at.x, at.y, at.z);
                if (near >= 0)
                {
                    WorldDatabase.DirectExecute(MoveSql(dungeon.name, rows[near].id, at));
                    handler->PSendSysMessage("Spot {} of {} is here now. The next floor to open uses it.",
                                             rows[near].id, dungeon.name);
                    return true;
                }
                unsigned const id = NextSpotId(rows);
                WorldDatabase.DirectExecute(AddSql(dungeon.name, id, at));
                handler->PSendSysMessage("Spot {} of {} added here. The next floor to open uses it.", id, dungeon.name);
                return true;
            }

            // `.dc pylon spot show [yards]`: marks the spots that near (SHOW_YARDS), each with its number and whose it
            // is.
            static bool HandleShow(ChatHandler* handler, Optional<float> yards)
            {
                Player* player = Self(handler);
                Dungeon dungeon;
                if (!player || !Exit::DungeonOf(player, dungeon))
                    return Fail(handler, "Stand in a rift floor, or in a dungeon on the rift list.");
                std::vector<Spot> const rows = LoadSpots(dungeon.name);
                float const reach = yards ? *yards : SHOW_YARDS;
                unsigned shown = 0;
                for (Spot const& row : rows)
                {
                    if (!Within(row, player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(), reach))
                        continue;
                    ++shown;
                    player->GetMap()->SummonCreature(MARKER_ENTRY, Position(row.x, row.y, row.z, row.o), nullptr,
                                                     MARKER_MS);
                    handler->PSendSysMessage("spot {}, area {}, {}, {} yards", row.id, row.area,
                                             row.alex ? "the designer's" : "the survey's",
                                             static_cast<int>(player->GetDistance(row.x, row.y, row.z)));
                }
                handler->PSendSysMessage("{}: {} of {} spots within {} yards, marked for a minute.", dungeon.name,
                                         shown, rows.size(), static_cast<int>(reach));
                return true;
            }

            // `.dc pylon spot clear`: the spot within NEAR_YARDS of him goes.
            static bool HandleClear(ChatHandler* handler)
            {
                Player* player = Self(handler);
                Dungeon dungeon;
                if (!player || !Exit::DungeonOf(player, dungeon))
                    return Fail(handler, "Stand in a rift floor, or in a dungeon on the rift list.");
                std::vector<Spot> const rows = LoadSpots(dungeon.name);
                int const near =
                    NearestSpot(rows, player->GetPositionX(), player->GetPositionY(), player->GetPositionZ());
                if (near < 0)
                    return Fail(handler, "No spot of " + dungeon.name + " within " +
                                             std::to_string(static_cast<int>(NEAR_YARDS)) +
                                             " yards: `.dc pylon spot show` marks them.");
                WorldDatabase.DirectExecute(RemoveSql(dungeon.name, rows[near].id));
                handler->PSendSysMessage("Spot {} of {} is gone. The next floor to open will not use it.",
                                         rows[near].id, dungeon.name);
                return true;
            }
        };
    } // namespace

    void Update(Map* map, uint32 diff)
    {
        if (!map)
            return;
        FloorPylons* state = map->CustomData.GetDefault<FloorPylons>("DCRiftPylons");
        if (!state->opened)
        {
            Rift view;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                if (!live.View(map->GetInstanceId(), map->GetId(), view))
                    return;
            }
            Open(map, *state, view);
            return;
        }
        if (!state->greater || state->waiting.empty())
            return;
        state->sinceCheck += diff;
        double const every =
            DC::Tunables::Has("rifts", "pylon_gr_check_ms") ? DC::Tunables::Get("rifts", "pylon_gr_check_ms") : 0;
        if (every <= 0 || state->sinceCheck < every)
            return;
        state->sinceCheck = 0;
        Approach(map, *state);
    }

    void FloorGone(std::uint64_t runId, bool runEnds)
    {
        if (!runEnds)
            return;
        std::lock_guard<std::mutex> lock(runMutex);
        runsHad.erase(runId);
    }

    void RegisterScripts()
    {
        new PylonSpotCommand();
        new LeaveRules();
    }
} // namespace DC::Rifts::Pylons

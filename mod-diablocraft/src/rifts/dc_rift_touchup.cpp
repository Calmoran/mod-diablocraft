/*
 * World of DiabloCraft - touch-up of the survey in game (monster spawning S4,
 * docs/proposals/monster-spawning.md 3.5.3).
 *
 *   .dc anchor show [yards] | hide | add [area|new] | remove [id] | move [id]
 *   .dc area tag <S|M|L> [area] | density <min> <max> [area] | density default [area] | nospawn <on|off> [area]
 *
 * The generator gets some areas wrong (two rooms joined through a wall, a corridor tagged L); a GM fixes them on dev,
 * standing in the dungeon (a rift floor, or the dungeon's own map). The edits go into the dev world database's
 * dc_rift_anchor and dc_rift_area tables, are read by the spawner again at once (the next floor to open uses them; a
 * floor already open keeps what stands on it), and generate_rift_survey.py --export writes them into the committed
 * sheets. The sheet stays the source.
 *
 * Built on the stock systems: the markers are what `.wp show` stands on a path, creature 1 "Waypoint (Only GM can see
 * it)" (cs_wp.cpp VISUAL_WAYPOINT); the commands are the module's ordinary CommandScript tables. Ours: the edits, which
 * dc_rift_touchup.h builds as SQL.
 *
 * "The area he stands in" is the area of the anchor nearest to him: an area is a set of anchors, not a shape on the
 * ground. Every command that takes an area also takes its number, which `show` prints.
 */

#include "dc_rift_spawner.h"
#include "dc_rift_touchup.h"
#include "dc_rifts_internal.h"

#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Map.h"
#include "Player.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "WorldSession.h"

#include <algorithm>
#include <cctype>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <vector>

namespace DC::Rifts::Spawner
{
    namespace
    {
        using namespace TouchUp;

        constexpr uint32 MARKER_ENTRY = 1; // creature_template 1: stock "Waypoint (Only GM can see it)"

        // The markers each GM has up, to take them down on the next `show` or on `hide` (memory only: a map's end ends
        // them).
        std::mutex markerMutex;
        std::map<uint64, std::vector<ObjectGuid>> markers;

        struct Spot
        {
            std::string dungeon;
            float entryX = 0, entryY = 0, entryZ = 0; // where the party arrives
            std::vector<AnchorRow> anchors;
            std::vector<AreaRow> areas;
        };

        std::vector<AnchorRow> LoadAnchors(std::string const& dungeon)
        {
            std::vector<AnchorRow> out;
            if (QueryResult rows = WorldDatabase.Query(
                    "SELECT `anchor`, `area`, `x`, `y`, `z`, `o` FROM `dc_rift_anchor` WHERE `dungeon` = {} "
                    "ORDER BY `anchor`",
                    Quote(dungeon)))
                do
                {
                    Field* f = rows->Fetch();
                    AnchorRow row;
                    row.id = f[0].Get<uint32>(), row.area = f[1].Get<uint32>(), row.x = f[2].Get<double>(),
                    row.y = f[3].Get<double>(), row.z = f[4].Get<double>(), row.o = f[5].Get<double>();
                    out.push_back(row);
                } while (rows->NextRow());
            return out;
        }

        std::vector<AreaRow> LoadAreas(std::string const& dungeon)
        {
            std::vector<AreaRow> out;
            if (QueryResult rows = WorldDatabase.Query(
                    "SELECT `area`, `tag`, `natives`, `density_min`, `density_max`, `nospawn` FROM `dc_rift_area` "
                    "WHERE `dungeon` = {} ORDER BY `area`",
                    Quote(dungeon)))
                do
                {
                    Field* f = rows->Fetch();
                    AreaRow row;
                    row.id = f[0].Get<uint32>(),
                    row.tag = f[1].Get<std::string>().empty() ? ' ' : f[1].Get<std::string>()[0],
                    row.natives = f[2].Get<uint32>(), row.hasDensity = !f[3].IsNull() && !f[4].IsNull(),
                    row.densityMin = f[3].IsNull() ? 0 : f[3].Get<uint32>(),
                    row.densityMax = f[4].IsNull() ? 0 : f[4].Get<uint32>(), row.nospawn = f[5].Get<uint8>() != 0;
                    out.push_back(row);
                } while (rows->NextRow());
            return out;
        }

        bool Fail(ChatHandler* handler, std::string const& text)
        {
            handler->SendSysMessage(text);
            handler->SetSentErrorMessage(true);
            return false;
        }

        // The dungeon the GM stands in: the rift floor's own dungeon, or else the surveyed dungeon of this map (where
        // two share a map, the one whose anchor is nearest).
        bool Locate(Player* player, Spot& spot, std::string& why)
        {
            Map* map = player->GetMap();
            Rift view;
            bool inRift;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                inRift = live.View(map->GetInstanceId(), map->GetId(), view);
            }
            std::vector<Rifts::Dungeon> candidates;
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                for (Rifts::Dungeon const& dungeon : pool)
                    if (inRift ? dungeon.dungeonId == view.dungeonId : dungeon.mapId == map->GetId())
                        candidates.push_back(dungeon);
            }
            double best = 0;
            bool found = false;
            for (Rifts::Dungeon const& dungeon : candidates)
            {
                std::vector<AnchorRow> anchors = LoadAnchors(dungeon.name);
                int const near =
                    Nearest(anchors, player->GetPositionX(), player->GetPositionY(), player->GetPositionZ());
                if (near < 0)
                    continue;
                double const distance =
                    Distance(anchors[near], player->GetPositionX(), player->GetPositionY(), player->GetPositionZ());
                if (found && distance >= best)
                    continue;
                found = true, best = distance;
                spot.dungeon = dungeon.name, spot.entryX = dungeon.x, spot.entryY = dungeon.y, spot.entryZ = dungeon.z;
                spot.anchors = std::move(anchors);
            }
            if (!found)
            {
                why = "No surveyed dungeon here: stand in a rift floor, or in a dungeon on the rift list.";
                return false;
            }
            spot.areas = LoadAreas(spot.dungeon);
            return true;
        }

        // The straight-line distance from the entry point: never more than the walk, so an edited anchor is cleared at
        // the entry no later than the survey would have (the entry clearance, 3.5.1 step 8).
        double EntryYards(Spot const& spot, double x, double y, double z)
        {
            return std::sqrt((x - spot.entryX) * (x - spot.entryX) + (y - spot.entryY) * (y - spot.entryY) +
                             (z - spot.entryZ) * (z - spot.entryZ));
        }

        // Sends the statements as one transaction, then has the spawner read the tables again.
        bool Commit(ChatHandler* handler, std::vector<std::string> const& statements, std::string const& done)
        {
            WorldDatabaseTransaction transaction = WorldDatabase.BeginTransaction();
            for (std::string const& sql : statements)
                transaction->Append(sql);
            if (!WorldDatabase.AsyncCommitTransaction(transaction).m_future.get())
                return Fail(handler, "The world database refused the edit; nothing changed.");
            std::string message;
            if (!Reload(message))
                return Fail(handler, done + " Saved, but the spawner could not read the tables again (" + message +
                                         "); floors keep the sheets from before.");
            handler->SendSysMessage(done +
                                    " The next floor to open uses it; a floor already open keeps what stands on it.");
            return true;
        }

        bool Digits(std::string const& text)
        {
            return !text.empty() && text.size() < 10 &&
                   std::all_of(text.begin(), text.end(), [](unsigned char c) { return std::isdigit(c) != 0; });
        }

        // The area an area command means: the one named, or the nearest anchor's.
        bool AreaOf(ChatHandler* handler, Player* player, Spot const& spot, Optional<uint32> named, unsigned& area)
        {
            if (named)
                area = *named;
            else
            {
                int const near =
                    Nearest(spot.anchors, player->GetPositionX(), player->GetPositionY(), player->GetPositionZ());
                if (near < 0)
                    return Fail(handler, "This dungeon has no anchors to read an area from: name the area.");
                area = spot.anchors[near].area;
            }
            for (AreaRow const& row : spot.areas)
                if (row.id == area)
                    return true;
            return Fail(handler, "There is no area " + std::to_string(area) + " in " + spot.dungeon + ".");
        }

        void TakeDownMarkers(Player* player)
        {
            std::vector<ObjectGuid> mine;
            {
                std::lock_guard<std::mutex> lock(markerMutex);
                auto found = markers.find(player->GetGUID().GetRawValue());
                if (found == markers.end())
                    return;
                mine = std::move(found->second);
                markers.erase(found);
            }
            for (ObjectGuid guid : mine)
                if (Creature* marker = player->GetMap()->GetCreature(guid))
                    marker->DespawnOrUnsummon();
        }

        class TouchUpCommand final : public CommandScript
        {
        public:
            TouchUpCommand()
                : CommandScript("dc_rift_touchup_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // Looking is for any GM; an edit writes the world database, so it is an administrator's, as opening a
                // rift is.
                static ChatCommandTable anchor = {
                    {"show", HandleShow, SEC_GAMEMASTER, Console::No},
                    {"hide", HandleHide, SEC_GAMEMASTER, Console::No},
                    {"add", HandleAdd, SEC_ADMINISTRATOR, Console::No},
                    {"remove", HandleRemove, SEC_ADMINISTRATOR, Console::No},
                    {"move", HandleMove, SEC_ADMINISTRATOR, Console::No},
                };
                static ChatCommandTable area = {
                    {"tag", HandleTag, SEC_ADMINISTRATOR, Console::No},
                    {"density", HandleDensity, SEC_ADMINISTRATOR, Console::No},
                    {"nospawn", HandleNospawn, SEC_ADMINISTRATOR, Console::No},
                };
                static ChatCommandTable dc = {{"anchor", anchor}, {"area", area}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            static Player* Self(ChatHandler* handler)
            {
                return handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            }

            // `.dc anchor show` marks the anchors of the area he stands in; `.dc anchor show <yards>` marks every
            // anchor that near instead.
            static bool HandleShow(ChatHandler* handler, Optional<float> yards)
            {
                Player* player = Self(handler);
                Spot spot;
                std::string why;
                if (!player || !Locate(player, spot, why))
                    return Fail(handler, why.empty() ? "Not in the world." : why);
                float const x = player->GetPositionX(), y = player->GetPositionY(), z = player->GetPositionZ();
                std::vector<AnchorRow> shown;
                if (yards)
                    shown = Around(spot.anchors, x, y, z, *yards);
                else
                {
                    unsigned area = 0;
                    if (!AreaOf(handler, player, spot, {}, area))
                        return false;
                    for (AnchorRow const& row : Around(spot.anchors, x, y, z, 1e9))
                        if (row.area == area)
                            shown.push_back(row);
                }
                TakeDownMarkers(player);
                handler->SendSysMessage(spot.dungeon + ": " + std::to_string(shown.size()) + " of " +
                                        std::to_string(spot.anchors.size()) + " anchors marked");
                std::set<unsigned> seen;
                for (AnchorRow const& row : shown)
                    if (seen.insert(row.area).second)
                        for (AreaRow const& area : spot.areas)
                            if (area.id == row.area)
                                handler->SendSysMessage(DescribeArea(
                                    area, std::count_if(spot.anchors.begin(), spot.anchors.end(),
                                                        [&](AnchorRow const& a) { return a.area == area.id; })));
                std::vector<ObjectGuid> placed;
                for (AnchorRow const& row : shown)
                {
                    if (TempSummon* marker =
                            player->GetMap()->SummonCreature(MARKER_ENTRY, Position(row.x, row.y, row.z, row.o)))
                        placed.push_back(marker->GetGUID());
                    handler->SendSysMessage("anchor " + std::to_string(row.id) + ", area " + std::to_string(row.area) +
                                            ", " + std::to_string(static_cast<int>(Distance(row, x, y, z))) + " yards");
                }
                std::lock_guard<std::mutex> lock(markerMutex);
                markers[player->GetGUID().GetRawValue()] = std::move(placed);
                return true;
            }

            static bool HandleHide(ChatHandler* handler)
            {
                if (Player* player = Self(handler))
                    TakeDownMarkers(player);
                return true;
            }

            // `.dc anchor add` puts an anchor where he stands, in the area of the nearest one; `add <area>` in that
            // area, `add new` in a new area (tagged S, for `.dc area tag`).
            static bool HandleAdd(ChatHandler* handler, Optional<std::string> where)
            {
                Player* player = Self(handler);
                Spot spot;
                std::string why;
                if (!player || !Locate(player, spot, why))
                    return Fail(handler, why.empty() ? "Not in the world." : why);
                unsigned area = 0;
                bool const fresh = where && *where == "new";
                if (fresh)
                    area = NextAreaId(spot.areas);
                else if (where && !Digits(*where))
                    return Fail(handler, "`.dc anchor add [area number|new]`");
                else if (!AreaOf(handler, player, spot,
                                 where ? Optional<uint32>(std::stoul(*where)) : Optional<uint32>(), area))
                    return false;
                unsigned const id = NextAnchorId(spot.anchors);
                float const x = player->GetPositionX(), y = player->GetPositionY(), z = player->GetPositionZ();
                return Commit(handler,
                              AddAnchor(spot.dungeon, id, area, fresh, x, y, z, player->GetOrientation(),
                                        EntryYards(spot, x, y, z)),
                              "Anchor " + std::to_string(id) + " added to " + (fresh ? "new " : "") + "area " +
                                  std::to_string(area) + " of " + spot.dungeon + ".");
            }

            // The anchor an edit means: the one named, or the nearest.
            static AnchorRow const* AnchorOf(ChatHandler* handler, Player* player, Spot const& spot,
                                             Optional<uint32> named)
            {
                if (named)
                {
                    for (AnchorRow const& row : spot.anchors)
                        if (row.id == *named)
                            return &row;
                    Fail(handler, "There is no anchor " + std::to_string(*named) + " in " + spot.dungeon + ".");
                    return nullptr;
                }
                int const near =
                    Nearest(spot.anchors, player->GetPositionX(), player->GetPositionY(), player->GetPositionZ());
                if (near < 0)
                    Fail(handler, "This dungeon has no anchors.");
                return near < 0 ? nullptr : &spot.anchors[near];
            }

            static bool HandleRemove(ChatHandler* handler, Optional<uint32> id)
            {
                Player* player = Self(handler);
                Spot spot;
                std::string why;
                if (!player || !Locate(player, spot, why))
                    return Fail(handler, why.empty() ? "Not in the world." : why);
                AnchorRow const* row = AnchorOf(handler, player, spot, id);
                if (!row)
                    return false;
                if (spot.anchors.size() < 2)
                    return Fail(handler,
                                "That is the dungeon's last anchor; a stock patrol path needs one to be tied to.");
                return Commit(handler, RemoveAnchor(spot.dungeon, row->id, row->area),
                              "Anchor " + std::to_string(row->id) + " of area " + std::to_string(row->area) +
                                  " removed from " + spot.dungeon +
                                  " (its patrol paths now follow the nearest anchor left).");
            }

            // `.dc anchor move` puts the nearest anchor where he stands; `move <id>` that one (the number is on
            // `show`).
            static bool HandleMove(ChatHandler* handler, Optional<uint32> id)
            {
                Player* player = Self(handler);
                Spot spot;
                std::string why;
                if (!player || !Locate(player, spot, why))
                    return Fail(handler, why.empty() ? "Not in the world." : why);
                AnchorRow const* row = AnchorOf(handler, player, spot, id);
                if (!row)
                    return false;
                float const x = player->GetPositionX(), y = player->GetPositionY(), z = player->GetPositionZ();
                return Commit(handler,
                              MoveAnchor(spot.dungeon, row->id, row->area, x, y, z, player->GetOrientation(),
                                         EntryYards(spot, x, y, z)),
                              "Anchor " + std::to_string(row->id) + " of area " + std::to_string(row->area) +
                                  " moved here.");
            }

            static bool HandleTag(ChatHandler* handler, std::string word, Optional<uint32> named)
            {
                char const tag = ParseTag(word);
                if (!tag)
                    return Fail(handler, "`.dc area tag <S|M|L> [area]`");
                Player* player = Self(handler);
                Spot spot;
                std::string why;
                unsigned area = 0;
                if (!player || !Locate(player, spot, why))
                    return Fail(handler, why.empty() ? "Not in the world." : why);
                if (!AreaOf(handler, player, spot, named, area))
                    return false;
                return Commit(handler, SetTag(spot.dungeon, area, tag),
                              "Area " + std::to_string(area) + " of " + spot.dungeon + " is now " +
                                  std::string(1, tag) + ".");
            }

            // `.dc area density <min> <max> [area]` is the anchors the area fills; `.dc area density default [area]` is
            // the tag's default again.
            static bool HandleDensity(ChatHandler* handler, std::string first, Optional<std::string> second,
                                      Optional<std::string> third)
            {
                bool const clear = first == "default";
                bool const range = Digits(first) && second && Digits(*second);
                if (!clear && !range)
                    return Fail(handler, "`.dc area density <min> <max> [area]` or `.dc area density default [area]`");
                unsigned const low = range ? std::stoul(first) : 0, high = range ? std::stoul(*second) : 0;
                if (range && low > high)
                    return Fail(handler, "The least cannot be more than the most.");
                Optional<std::string> const& areaWord = clear ? second : third;
                if (areaWord && !Digits(*areaWord))
                    return Fail(handler, "The area is its number, which `.dc anchor show` prints.");
                Player* player = Self(handler);
                Spot spot;
                std::string why;
                unsigned area = 0;
                if (!player || !Locate(player, spot, why))
                    return Fail(handler, why.empty() ? "Not in the world." : why);
                if (!AreaOf(handler, player, spot,
                            areaWord ? Optional<uint32>(std::stoul(*areaWord)) : Optional<uint32>(), area))
                    return false;
                return Commit(handler, SetDensity(spot.dungeon, area, clear, low, high),
                              "Area " + std::to_string(area) + " of " + spot.dungeon + " fills " +
                                  (clear ? std::string("the tag's default number of anchors")
                                         : std::to_string(low) + " to " + std::to_string(high) + " anchors") +
                                  ".");
            }

            static bool HandleNospawn(ChatHandler* handler, std::string word, Optional<uint32> named)
            {
                if (word != "on" && word != "off")
                    return Fail(handler, "`.dc area nospawn <on|off> [area]`");
                Player* player = Self(handler);
                Spot spot;
                std::string why;
                unsigned area = 0;
                if (!player || !Locate(player, spot, why))
                    return Fail(handler, why.empty() ? "Not in the world." : why);
                if (!AreaOf(handler, player, spot, named, area))
                    return false;
                return Commit(handler, SetNospawn(spot.dungeon, area, word == "on"),
                              "Area " + std::to_string(area) + " of " + spot.dungeon + " holds " +
                                  (word == "on" ? "nothing" : "monsters again") + ".");
            }
        };
    } // namespace

    void RegisterTouchUp()
    {
        new TouchUpCommand();
    }
} // namespace DC::Rifts::Spawner

/*
 * World of DiabloCraft - bounties as quests.
 *
 * While a player stands in a bounty's zone (its open-zone copy), that zone's open bounty from the board they play
 * (their party's, else their own) is a quest in their log and tracker, and only that one: a Kill reads "<Unique> slain
 * 0/1", a Click "Shrines activated 0/n" with n the board's drawn count. The board stays the source of truth
 * (dc_bounties.cpp) and the quest mirrors it, on the rift quests' pattern (dc_rift_quests.cpp): the module puts the
 * quest in the log itself, writes its count absolute against the never-spawned credit creature, and takes it out with
 * the log slot. What the log needs is SyncQuests (dc_bounty_board.h); this file does it to the player.
 *
 * When: on a player's update on a bounty map, when the board epoch, the instance, the zone or the map moved since their
 * last look (a click or a kill moves the epoch, so every party member there ticks on their next update); on a map
 * change (leaving the copy takes the quest out); at login (every bounty quest out, then the look; and the logout rule,
 * ExpireBoardsOnLogin); after an abandon (the next look puts it back). A done bounty's quest is shown complete, then
 * taken out, and the zone's next open bounty (if any) comes in.
 *
 * Map marks: the quest's POI is the board's own, per player. The core answers CMSG_QUEST_POI_QUERY from the static
 * quest_poi table, the same for everyone (QueryHandler.cpp), so a query that names a bounty quest is answered here: the
 * bounty's open spots (a Kill's Unique, a Click's objectives still to click), one single-point POI each, on the zone's
 * world map area (dc_bounties_quest.poi_area); every other quest in the query as the core would.
 */

#include "dc_bounties.h"

#include "DatabaseEnv.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "Player.h"
#include "QuestDef.h"
#include "ScriptMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <algorithm>
#include <map>
#include <mutex>
#include <tuple>
#include <unordered_set>
#include <vector>

namespace DC::Bounties
{
    namespace
    {
        std::mutex questMutex; // the rows, the areas and the looks
        std::vector<QuestRow> rows;
        std::map<std::uint32_t, std::uint32_t> poiArea; // bounty -> WorldMapArea row
        using Look = std::tuple<std::uint64_t, std::uint32_t, std::uint32_t, std::uint32_t>;
        std::map<ObjectGuid, Look> looked;

        std::vector<QuestRow> Rows()
        {
            std::lock_guard<std::mutex> lock(questMutex);
            return rows;
        }

        QuestRow const* RowOfQuest(std::vector<QuestRow> const& all, std::uint32_t quest)
        {
            for (QuestRow const& r : all)
                if (r.quest == quest)
                    return &r;
            return nullptr;
        }

        // Every bounty quest in the log, by slot or by status (a slot can outlive its status, dc_rift_quests.cpp
        // ClearQuestSlots).
        std::vector<std::uint32_t> Held(Player* player, std::vector<QuestRow> const& all)
        {
            std::vector<std::uint32_t> out;
            auto note = [&](std::uint32_t quest)
            {
                if (quest && RowOfQuest(all, quest) && std::find(out.begin(), out.end(), quest) == out.end())
                    out.push_back(quest);
            };
            for (uint16 slot = 0; slot < MAX_QUEST_LOG_SIZE; ++slot)
                note(player->GetQuestSlotQuestId(slot));
            for (auto const& [quest, status] : player->getQuestStatusMap())
                note(quest);
            return out;
        }

        // Out of the log for good, slot and all (the rift quests' StripRunQuest).
        void Strip(Player* player, std::uint32_t quest)
        {
            if (player->GetQuestStatus(quest) != QUEST_STATUS_NONE)
            {
                player->AbandonQuest(quest);
                player->RemoveActiveQuest(quest, false);
            }
            for (uint16 slot = player->FindQuestSlot(quest); slot < MAX_QUEST_LOG_SIZE;
                 slot = player->FindQuestSlot(quest))
                player->SetQuestSlot(slot, 0);
        }

        // The count, absolute and never backwards, on the one objective (the rift quests' SetQuestProgress): the empty
        // guid keeps the core from crediting a creature entry; the last one completes the quest.
        void Write(Player* player, Quest const* quest, std::uint32_t count)
        {
            QuestStatusMap& statuses = player->getQuestStatusMap();
            auto found = statuses.find(quest->GetQuestId());
            if (found == statuses.end() || found->second.Status != QUEST_STATUS_INCOMPLETE)
                return;
            uint16 const current = found->second.CreatureOrGOCount[0];
            uint16 const target = static_cast<uint16>(std::min<std::uint32_t>(count, quest->RequiredNpcOrGoCount[0]));
            if (target <= current)
                return;
            found->second.CreatureOrGOCount[0] = target;
            player->GetQuestStatusSaveMap()[quest->GetQuestId()] = true;
            player->SendQuestUpdateAddCreatureOrGo(quest, ObjectGuid::Empty, 0, current, target - current);
            if (player->CanCompleteQuest(quest->GetQuestId()))
                player->CompleteQuest(quest->GetQuestId());
            else
                player->AdditionalSavingAddMask(ADDITIONAL_SAVING_QUEST_STATUS);
        }

        void Sync(Player* player, bool here)
        {
            std::vector<QuestRow> const all = Rows();
            if (all.empty())
                return;
            QuestSync const sync = QuestsFor(player, all, Held(player, all), here);
            for (std::uint32_t quest : sync.finish)
            {
                if (Quest const* q = sObjectMgr->GetQuestTemplate(quest))
                    Write(player, q, q->RequiredNpcOrGoCount[0]);
                Strip(player, quest);
            }
            for (std::uint32_t quest : sync.strip)
                Strip(player, quest);
            Quest const* shown = sync.quest ? sObjectMgr->GetQuestTemplate(sync.quest) : nullptr;
            if (sync.quest && !shown)
                LOG_ERROR("server", "[DC bounties] quest {} is not in quest_template; apply bounties_0005_quests.sql",
                          sync.quest);
            if (shown && sync.add)
            {
                if (!player->CanAddQuest(shown, false))
                    return; // a full log: the next look tries again
                player->AddQuestAndCheckCompletion(shown, nullptr);
            }
            if (shown)
                Write(player, shown, sync.count);
        }

        void LookAgain(Player* player)
        {
            std::lock_guard<std::mutex> lock(questMutex);
            looked.erase(player->GetGUID());
        }

        // One single-point POI a spot, the stock data's commonest shape (quest_poi: priority 0, flags 1, one point).
        void WritePoi(WorldPacket& data, std::uint32_t quest, std::uint32_t mapId, std::uint32_t area,
                      std::vector<std::pair<unsigned, Spot>> const& spots)
        {
            data << uint32(quest);
            data << uint32(spots.size());
            for (std::size_t i = 0; i < spots.size(); ++i)
            {
                data << uint32(i); // POI index
                data << int32(0);  // the objective: the quest has one
                data << uint32(mapId);
                data << uint32(area); // WorldMapArea row
                data << uint32(0);    // floor
                data << uint32(0);    // priority
                data << uint32(1);    // flags
                data << uint32(1);    // one point
                data << int32(spots[i].second.x);
                data << int32(spots[i].second.y);
            }
        }

        // The core's answer for a quest that is not a bounty's (QueryHandler.cpp HandleQuestPOIQuery).
        void WriteStockPoi(WorldPacket& data, Player* player, std::uint32_t quest)
        {
            uint16 const slot = player->FindQuestSlot(quest);
            QuestPOIVector const* poi = slot != MAX_QUEST_LOG_SIZE && player->GetQuestSlotQuestId(slot) == quest
                                            ? sObjectMgr->GetQuestPOIVector(quest)
                                            : nullptr;
            data << uint32(quest);
            data << uint32(poi ? poi->size() : 0);
            if (poi)
                for (QuestPOI const& p : *poi)
                {
                    data << uint32(p.Id) << int32(p.ObjectiveIndex) << uint32(p.MapId) << uint32(p.AreaId)
                         << uint32(p.FloorId) << uint32(p.Unk3) << uint32(p.Unk4) << uint32(p.points.size());
                    for (QuestPOIPoint const& point : p.points)
                        data << int32(point.x) << int32(point.y);
                }
        }

        class BountyQuestWorld final : public WorldScript
        {
        public:
            BountyQuestWorld()
                : WorldScript("dc_bounty_quests_world", {WORLDHOOK_ON_LOAD_CUSTOM_DATABASE_TABLE})
            {
            }
            void OnLoadCustomDatabaseTable() override
            {
                std::vector<QuestRow> loaded;
                std::map<std::uint32_t, std::uint32_t> areas;
                if (auto result =
                        WorldDatabase.Query("SELECT bounty_id,need,quest_id,poi_area,target FROM dc_bounties_quest"))
                    do
                    {
                        Field* f = result->Fetch();
                        loaded.push_back({f[0].Get<uint32>(), f[1].Get<uint8>(), f[2].Get<uint32>(), f[4].Get<uint32>()});
                        areas[f[0].Get<uint32>()] = f[3].Get<uint32>();
                    } while (result->NextRow());
                else
                    LOG_ERROR("server", "[DC bounties] dc_bounties_quest is missing or empty; bounties show no quest "
                                        "(apply bounties_0005_quests.sql)");
                std::lock_guard<std::mutex> lock(questMutex);
                rows = std::move(loaded);
                poiArea = std::move(areas);
                looked.clear();
                LOG_INFO("server.loading", "[DC bounties] {} bounty quests loaded", rows.size());
            }
        };

        class BountyQuestPlayer final : public PlayerScript
        {
        public:
            BountyQuestPlayer()
                : PlayerScript("dc_bounty_quests_player",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_MAP_CHANGED, PLAYERHOOK_ON_LOGIN,
                                PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_QUEST_ABANDON})
            {
            }
            void OnPlayerUpdate(Player* player, uint32 /*diff*/) override
            {
                if (!IsBountyMap(player->GetMapId()) || player->IsBeingTeleported() || !player->IsInWorld())
                    return;
                Look const now{Epoch(), player->GetInstanceId(), player->GetZoneId(), player->GetMapId()};
                {
                    std::lock_guard<std::mutex> lock(questMutex);
                    Look& last = looked[player->GetGUID()];
                    if (last == now)
                        return;
                    last = now;
                }
                Sync(player, true);
            }
            // Out of the copy: every bounty quest goes. Into one: the next update looks.
            void OnPlayerMapChanged(Player* player) override
            {
                LookAgain(player);
                if (!IsBountyMap(player->GetMapId()))
                    Sync(player, false);
            }
            // Nothing carries over a login: the board's logout rule, then a clean log; the look puts back what is due.
            void OnPlayerLogin(Player* player) override
            {
                ExpireBoardsOnLogin(player);
                Sync(player, false);
                LookAgain(player);
            }
            void OnPlayerLogout(Player* player) override
            {
                LookAgain(player);
            }
            // Not abandonable: the abandon runs before the handler clears the slot, so the quest comes back on the next
            // look, not here (dc_rift_quests.cpp's reason).
            void OnPlayerQuestAbandon(Player* player, uint32 quest) override
            {
                if (RowOfQuest(Rows(), quest))
                    LookAgain(player);
            }
        };

        class BountyQuestPoi final : public ServerScript
        {
        public:
            BountyQuestPoi()
                : ServerScript("dc_bounty_quests_poi", {SERVERHOOK_CAN_PACKET_RECEIVE})
            {
            }
            bool CanPacketReceive(WorldSession* session, WorldPacket const& packet) override
            {
                if (packet.GetOpcode() != CMSG_QUEST_POI_QUERY || !session || !session->GetPlayer())
                    return true;
                Player* player = session->GetPlayer();
                WorldPacket read(packet);
                read.rpos(0);
                if (read.size() < 4)
                    return true;
                uint32 count = 0;
                read >> count;
                if (count > MAX_QUEST_LOG_SIZE || read.size() < 4 + 4 * std::size_t(count))
                    return true; // the core's own refusal
                std::vector<std::uint32_t> quests;
                std::unordered_set<std::uint32_t> seen;
                for (uint32 i = 0; i < count; ++i)
                    if (std::uint32_t const quest = read.read<uint32>(); seen.insert(quest).second)
                        quests.push_back(quest);
                std::vector<QuestRow> const all = Rows();
                if (std::none_of(quests.begin(), quests.end(), [&](std::uint32_t q) { return RowOfQuest(all, q); }))
                    return true;
                std::map<std::uint32_t, std::uint32_t> areas;
                {
                    std::lock_guard<std::mutex> lock(questMutex);
                    areas = poiArea;
                }
                std::vector<Open> const open = OpenIn(player, player->GetMapId(), player->GetZoneId());
                WorldPacket data(SMSG_QUEST_POI_QUERY_RESPONSE, 4 + 8 * quests.size());
                data << uint32(quests.size());
                for (std::uint32_t quest : quests)
                {
                    QuestRow const* row = RowOfQuest(all, quest);
                    if (!row)
                    {
                        WriteStockPoi(data, player, quest);
                        continue;
                    }
                    std::vector<std::pair<unsigned, Spot>> spots;
                    if (player->FindQuestSlot(quest) != MAX_QUEST_LOG_SIZE)
                        for (Open const& o : open)
                            if (o.bounty == row->bounty)
                                spots = o.spots;
                    WritePoi(data, quest, player->GetMapId(), areas.count(row->bounty) ? areas[row->bounty] : 0, spots);
                }
                session->SendPacket(&data);
                return false;
            }
        };
    } // namespace

    void RegisterQuestScripts()
    {
        new BountyQuestWorld();
        new BountyQuestPlayer();
        new BountyQuestPoi();
    }
} // namespace DC::Bounties

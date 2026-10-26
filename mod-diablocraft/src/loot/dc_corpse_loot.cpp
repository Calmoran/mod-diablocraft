#include "dc_corpse_loot.h"
#include "dc_corpse_rules.h"
#include "dc_loot.h"
#include "../common/dc_tunables.h"
#include "../items/dc_quality_rule.h"
#include "../rifts/dc_rifts.h"

#include "Creature.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "UpdateFieldFlags.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include <algorithm>
#include <atomic>
#include <functional>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <tuple>
#include <vector>

// Personal corpse loot, M1 and M2 of the corpse-loot minimum
// (docs/proposals/corpse-loot-minimum.md). The stock loot of a D3 creature is
// empty (LootSuppression), so the corpse's window is ours: each player's drops
// are rows of dc_loot_buffer with kind 'corpse', and this file answers
// CMSG_LOOT, CMSG_AUTOSTORE_LOOT_ITEM, CMSG_LOOT_RELEASE and CMSG_LOOT_MONEY for
// such a corpse by building the stock SMSG_LOOT_RESPONSE by hand, per viewer.
//
// Literal audit: the only numbers are in dc_corpse_rules.h, each a recorded
// constant. The far-future expiry below is the same never-expires date
// dc_loot_delivery.cpp uses for held materials (a TIMESTAMP ends in 2038).
//
// The loot beam's server half (docs/contracts/loot-beam-tier.md): each player is
// sent the beam tier of their own rows on a corpse in its UNIT_FIELD_PADDING, per viewer, through the
// core's values-update patch hooks (the way mod-transmog sends each viewer their own item display). The
// field and its promotion to public come from manatactical/wxl-loot-beam's server/mod-loot-beam.
namespace DC::Loot
{
    namespace
    {
        constexpr char const* NeverExpires = "'2038-01-01 00:00:00'";

        struct Slot
        {
            std::uint64_t row = 0;
            ObjectGuid corpse;
            bool taken = false;
            std::uint32_t beam = Corpse::BeamNone; // the row's loot beam tier
        };
        struct Window
        {
            ObjectGuid corpse;
            std::vector<Slot> slots;
        };
        struct CorpseEntry
        {
            std::uint32_t rows = 0; // rows of every owner still on this corpse
            bool rift = false;      // a rift corpse dies with its rift
            std::uint32_t mapId = 0, instanceId = 0;
            std::set<ObjectGuid> owed; // players owed a roll on this corpse (OweCorpse)
            OwedPay pay;
            std::map<ObjectGuid, Corpse::BeamCounts> beams; // each owner's rows here, by beam tier
        };

        std::mutex mutex;
        std::map<Map*, std::map<ObjectGuid, CorpseEntry>> corpses;
        std::map<ObjectGuid, Window> windows; // by player guid
        std::atomic<bool> ready{false};

        bool Tracked(Map* map, ObjectGuid corpse)
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = corpses.find(map);
            return found != corpses.end() && found->second.count(corpse);
        }

        // The corpse is the stock window of the whole party: a placeholder copper
        // keeps Loot::isLooted() false, so UNIT_DYNFLAG_LOOTABLE survives both the
        // core's kill code and isAllowedToLoot. It is never sent (our packet says
        // gold 0) and never paid (CMSG_LOOT_MONEY is swallowed).
        void Prepare(Creature* corpse)
        {
            corpse->loot.gold = 1;
            // Personal in every group loot method: with a round-robin looter set, the
            // core's isAllowedToLoot lets only that one member (or, for group loot and
            // need-before-greed, an over-threshold item) through, and the corpse would
            // not sparkle or open for anyone else. Our rows carry no threshold and no
            // roll, so there is no looter to keep.
            corpse->loot.roundRobinPlayer.Clear();
            corpse->SetDynamicFlag(UNIT_DYNFLAG_LOOTABLE);
            corpse->ForceValuesUpdateAtIndex(UNIT_DYNAMIC_FLAGS);
        }

        // Unit::Kill has already run AllLootRemovedFromCorpse on this (empty) stock
        // loot and halved the corpse's life; a corpse that holds drops decays on
        // the normal timer, as in stock WoW.
        void RestoreDecay(Creature* corpse)
        {
            corpse->SetCorpseRemoveTime(corpse->GetCorpseDelay());
        }

        bool IsCorpse(Creature* creature)
        {
            return creature && creature->getDeathState() == DeathState::Corpse;
        }

        // Nothing is left on the corpse for anyone: no placeholder, no sparkle, no beam, and the
        // looted decay rate applies as it does when a stock corpse is emptied.
        void FinishCorpse(Creature* corpse)
        {
            corpse->loot.gold = 0;
            corpse->RemoveDynamicFlag(UNIT_DYNFLAG_LOOTABLE);
            corpse->ForceValuesUpdateAtIndex(UNIT_DYNAMIC_FLAGS);
            corpse->AllLootRemovedFromCorpse();
            corpse->SetUInt32Value(UNIT_FIELD_PADDING, 0);
        }

        // Somebody's beam tier on this corpse changed. The stored value is only whether anyone has one, so a
        // create packet carries the field; each viewer's own tier is written in at send time (CorpseBeam).
        // Forced, because one viewer's tier can change while the stored value does not. Called without the lock.
        void PublishBeam(Creature* corpse, bool any)
        {
            corpse->SetUInt32Value(UNIT_FIELD_PADDING, any ? 1 : 0);
            corpse->ForceValuesUpdateAtIndex(UNIT_FIELD_PADDING);
        }

        // Under the lock.
        bool AnyBeam(CorpseEntry const& entry)
        {
            for (auto const& owner : entry.beams)
                if (Corpse::BeamValue(owner.second) != Corpse::BeamNone)
                    return true;
            return false;
        }

        // The tier `viewer` is sent for `corpse`: their own highest, none for anyone else.
        std::uint32_t BeamFor(Map* map, ObjectGuid corpse, ObjectGuid viewer)
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = corpses.find(map);
            if (found == corpses.end())
                return Corpse::BeamNone;
            auto entry = found->second.find(corpse);
            if (entry == found->second.end())
                return Corpse::BeamNone;
            auto owner = entry->second.beams.find(viewer);
            return owner == entry->second.beams.end() ? Corpse::BeamNone : Corpse::BeamValue(owner->second);
        }

        void AddRow(Map* map, ObjectGuid corpseGuid, bool inRift, ObjectGuid owner, std::uint32_t beam)
        {
            bool first = false;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto& entry = corpses[map][corpseGuid];
                first = entry.rows == 0 && entry.owed.empty();
                ++entry.rows;
                entry.rift = inRift;
                entry.mapId = map->GetId();
                entry.instanceId = map->GetInstanceId();
                if (Corpse::Beams(beam))
                    Corpse::AddBeam(entry.beams[owner], beam);
            }
            if (Creature* corpse = map->GetCreature(corpseGuid))
            {
                Prepare(corpse);
                if (first)
                    RestoreDecay(corpse);
                if (Corpse::Beams(beam))
                    PublishBeam(corpse, true);
            }
        }

        // A row was taken. The last one of the corpse ends its window for everyone, unless a player is
        // still owed a roll on it. A beam row also lowers its owner's tier.
        void RowTaken(Creature* corpse, ObjectGuid owner, std::uint32_t beam)
        {
            bool empty = false;
            bool any = false;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = corpses.find(corpse->GetMap());
                if (found == corpses.end())
                    return;
                auto entry = found->second.find(corpse->GetGUID());
                if (entry == found->second.end())
                    return;
                std::uint32_t const left = entry->second.rows ? --entry->second.rows : 0;
                Corpse::TakeBeam(entry->second.beams[owner], beam);
                any = AnyBeam(entry->second);
                empty = Corpse::CorpseEmpty(left, static_cast<std::uint32_t>(entry->second.owed.size()));
                if (empty)
                {
                    found->second.erase(entry);
                    if (found->second.empty())
                        corpses.erase(found);
                }
            }
            if (empty)
                FinishCorpse(corpse);
            else if (Corpse::Beams(beam))
                PublishBeam(corpse, any);
        }

        // The player opens a corpse they are owed a roll on: pay it now, once. The pay runs outside the lock (it
        // writes rows, which take it). A pay that did not commit leaves them owed, so the next open tries again;
        // the receipt it was written with keeps a retry from paying twice. A corpse left with nothing is finished.
        void PayOwed(Player* player, Creature* corpse)
        {
            OwedPay pay;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = corpses.find(corpse->GetMap());
                if (found == corpses.end())
                    return;
                auto entry = found->second.find(corpse->GetGUID());
                if (entry == found->second.end() || !entry->second.owed.erase(player->GetGUID()))
                    return;
                pay = entry->second.pay;
            }
            bool const paid = pay && pay(player, corpse);
            bool empty = false;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = corpses.find(corpse->GetMap());
                if (found == corpses.end())
                    return;
                auto entry = found->second.find(corpse->GetGUID());
                if (entry == found->second.end())
                    return;
                if (!paid)
                    entry->second.owed.insert(player->GetGUID());
                else if (Corpse::CorpseEmpty(entry->second.rows, static_cast<std::uint32_t>(entry->second.owed.size())))
                {
                    found->second.erase(entry);
                    if (found->second.empty())
                        corpses.erase(found);
                    empty = true;
                }
            }
            if (empty)
                FinishCorpse(corpse);
        }

        // Rows die with the corpse (docs/proposals/corpse-loot-minimum.md M4): nothing goes
        // to the bags or the mail. `ids` empty deletes every corpse row of the map.
        void DeleteRows(std::uint32_t mapId, std::uint32_t instanceId, std::vector<ObjectGuid> const& ids)
        {
            if (ids.empty())
            {
                CharacterDatabase.DirectExecute(
                    "DELETE FROM dc_loot_buffer WHERE kind='corpse' AND map_id={} AND instance_id={}", mapId,
                    instanceId);
                return;
            }
            std::string list;
            for (ObjectGuid const& id : ids)
                list += (list.empty() ? "" : ",") + std::to_string(id.GetRawValue());
            CharacterDatabase.DirectExecute(
                "DELETE FROM dc_loot_buffer WHERE kind='corpse' AND map_id={} AND instance_id={} "
                "AND carrier_guid IN ({})",
                mapId, instanceId, list);
        }

        // The one function every release path ends in. The packet the client sees
        // is the stock SMSG_LOOT_RELEASE_RESPONSE.
        void ReleaseWindow(Player* player, bool notifyClient)
        {
            Window window;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = windows.find(player->GetGUID());
                if (found == windows.end())
                    return;
                window = std::move(found->second);
                windows.erase(found);
            }
            if (player->GetLootGUID() == window.corpse)
                player->SetLootGUID(ObjectGuid::Empty);
            if (notifyClient)
                player->SendLootRelease(window.corpse);
            player->RemoveUnitFlag(UNIT_FLAG_LOOTING);
        }

        // Area looting: the window lists the looter's own rows from every tracked corpse of
        // theirs on this map within loot/aoe_range_yards, best first, one page. The clicked
        // corpse only supplies the click; its rows are not special.
        void OpenWindow(Player* player, Creature* clicked)
        {
            ReleaseWindow(player, true); // another CMSG_LOOT while a window is open
            struct Row
            {
                std::uint64_t id;
                ObjectGuid corpse;
                std::uint32_t item;
                std::uint32_t count;
                std::uint32_t beam;
            };
            Map* map = player->GetMap();
            double const range = Corpse::ClampRange(DC::Tunables::Get("loot", "aoe_range_yards"));

            std::map<std::uint64_t, std::pair<ObjectGuid, float>> reachable; // carrier guid -> (guid, distance)
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = corpses.find(map);
                if (found != corpses.end())
                    for (auto const& entry : found->second)
                    {
                        Creature* corpse = map->GetCreature(entry.first);
                        if (!IsCorpse(corpse))
                            continue;
                        float const distance = player->GetDistance(corpse);
                        if (Corpse::InAoeRange(distance, range))
                            reachable[entry.first.GetRawValue()] = {entry.first, distance};
                    }
            }
            reachable[clicked->GetGUID().GetRawValue()] = {clicked->GetGUID(), player->GetDistance(clicked)};

            std::string list;
            for (auto const& entry : reachable)
                list += (list.empty() ? "" : ",") + std::to_string(entry.first);
            std::vector<Row> rows;
            std::vector<Corpse::Candidate> candidates;
            if (QueryResult result = CharacterDatabase.Query(
                    "SELECT id,carrier_guid,base_item,content_kind,drop_count,rarity,quality_tier FROM dc_loot_buffer "
                    "WHERE guid={} AND kind='corpse' AND map_id={} AND instance_id={} "
                    "AND phase_mask={} AND expires_at>NOW() AND carrier_guid IN ({}) ORDER BY id",
                    player->GetGUID().GetRawValue(), map->GetId(), map->GetInstanceId(), player->GetPhaseMask(),
                    list))
                do
                {
                    Field* f = result->Fetch();
                    std::uint32_t const item = WindowItem(f[2].Get<std::uint32_t>(), f[3].Get<std::string>());
                    if (!sObjectMgr->GetItemTemplate(item))
                    {
                        LOG_ERROR("server", "[DC corpse loot] row {} shows item {}, which has no template; skipped",
                                  f[0].Get<std::uint64_t>(), item);
                        continue;
                    }
                    auto const& where = reachable.at(f[1].Get<std::uint64_t>());
                    rows.push_back({f[0].Get<std::uint64_t>(), where.first, item, std::max(1u, f[4].Get<std::uint32_t>()),
                                    Corpse::BeamTier(f[5].Get<std::string>(), f[6].Get<std::string>())});
                    candidates.push_back({f[0].Get<std::uint64_t>(), Corpse::RarityRank(f[5].Get<std::string>()),
                                          where.second});
                } while (result->NextRow());

            std::vector<std::uint64_t> const shown = Corpse::Page(Corpse::Order(candidates));
            if (shown.empty())
            {
                player->SendLootError(clicked->GetGUID(), LOOT_ERROR_DIDNT_KILL);
                return;
            }

            Window window;
            window.corpse = clicked->GetGUID();
            WorldPacket data(SMSG_LOOT_RESPONSE, 9 + 6 + shown.size() * 22);
            data << clicked->GetGUID();
            data << std::uint8_t(LOOT_CORPSE);
            data << std::uint32_t(0); // gold: the placeholder is never shown
            data << std::uint8_t(shown.size());
            for (std::size_t slot = 0; slot < shown.size(); ++slot)
            {
                Row const& row = *std::find_if(rows.begin(), rows.end(),
                                               [&](Row const& candidate) { return candidate.id == shown[slot]; });
                ItemTemplate const* proto = sObjectMgr->GetItemTemplate(row.item);
                data << std::uint8_t(slot);
                data << std::uint32_t(row.item);
                data << std::uint32_t(row.count);
                data << std::uint32_t(proto->DisplayInfoID);
                data << std::uint32_t(0); // random suffix
                data << std::uint32_t(0); // random property
                data << std::uint8_t(LOOT_SLOT_TYPE_ALLOW_LOOT);
                window.slots.push_back({row.id, row.corpse, false, row.beam});
            }
            player->SendDirectMessage(&data);
            player->SetLootGUID(clicked->GetGUID());
            player->SetUnitFlag(UNIT_FLAG_LOOTING);
            std::lock_guard<std::mutex> lock(mutex);
            windows[player->GetGUID()] = std::move(window);
        }

        void Pickup(Player* player, std::uint8_t slotId)
        {
            Slot slot;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = windows.find(player->GetGUID());
                if (found == windows.end() || slotId >= found->second.slots.size() || found->second.slots[slotId].taken)
                {
                    player->SendEquipError(EQUIP_ERR_ALREADY_LOOTED, nullptr, nullptr);
                    return;
                }
                slot = found->second.slots[slotId];
            }
            Creature* corpse = player->GetMap() ? player->GetMap()->GetCreature(slot.corpse) : nullptr;
            if (!IsCorpse(corpse) || !player->IsAlive() ||
                !Corpse::InAoeRange(player->GetDistance(corpse),
                                    Corpse::ClampRange(DC::Tunables::Get("loot", "aoe_range_yards"))))
            {
                player->SendEquipError(EQUIP_ERR_ALREADY_LOOTED, nullptr, nullptr);
                return;
            }
            std::uint8_t storeError = Corpse::StoreOk;
            bool const claimed = ClaimCorpseRow(player, slot.row, corpse, storeError);
            switch (Corpse::PickupOutcome(claimed, storeError))
            {
                case Corpse::PickupError::StoreFailed:
                    // The core's own refusal - EQUIP_ERR_INVENTORY_FULL,
                    // EQUIP_ERR_ITEM_MAX_COUNT for a Unique one, and so on - so the
                    // player is told what actually happened instead of always
                    // "Inventory is full."
                    player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr);
                    return; // the row and the slot stay
                case Corpse::PickupError::AlreadyLooted:
                    player->SendEquipError(EQUIP_ERR_ALREADY_LOOTED, nullptr, nullptr);
                    break; // the row is gone: take the slot out of the window below
                case Corpse::PickupError::None:
                    break;
            }
            bool windowEmpty = true;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = windows.find(player->GetGUID());
                if (found != windows.end())
                {
                    found->second.slots[slotId].taken = true;
                    for (Slot const& other : found->second.slots)
                        windowEmpty = windowEmpty && other.taken;
                }
            }
            player->SendNotifyLootItemRemoved(slotId);
            if (claimed)
                RowTaken(corpse, player->GetGUID(), slot.beam);
            // The stock window closes itself on its last row; a module window shows
            // one page, so when the page is spent it is released and the next click
            // opens the next page.
            if (windowEmpty)
                ReleaseWindow(player, true);
        }

        class CorpsePackets final : public ServerScript
        {
        public:
            CorpsePackets()
                : ServerScript("dc_corpse_loot_packets", {SERVERHOOK_CAN_PACKET_RECEIVE})
            {
            }

            bool CanPacketReceive(WorldSession* session, WorldPacket const& packet) override
            {
                std::uint32_t const opcode = packet.GetOpcode();
                if (opcode != CMSG_LOOT && opcode != CMSG_LOOT_RELEASE && opcode != CMSG_AUTOSTORE_LOOT_ITEM &&
                    opcode != CMSG_LOOT_MONEY)
                    return true;
                Player* player = session ? session->GetPlayer() : nullptr;
                if (!player || !ready)
                    return true;
                WorldPacket copy(packet);
                bool const windowOpen = [&]
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    return windows.count(player->GetGUID()) > 0;
                }();

                if (opcode == CMSG_LOOT || opcode == CMSG_LOOT_RELEASE)
                {
                    ObjectGuid guid;
                    copy >> guid;
                    bool const tracked = player->GetMap() && Tracked(player->GetMap(), guid);
                    if (opcode == CMSG_LOOT)
                    {
                        if (!Corpse::Answers(Corpse::Packet::Open, tracked, windowOpen))
                            return true; // every other creature: the stock handler
                        Creature* corpse = player->GetMap()->GetCreature(guid);
                        // The stock handler's own checks (HandleLootOpcode, SendLoot), by hand.
                        if (!IsCorpse(corpse) || !player->IsAlive())
                        {
                            player->SendLootError(guid, LOOT_ERROR_DIDNT_KILL);
                            return false;
                        }
                        if (player->HasPlayerFlag(PLAYER_FLAGS_NO_PLAY_TIME))
                        {
                            player->SendLootError(guid, LOOT_ERROR_PLAY_TIME_EXCEEDED);
                            return false;
                        }
                        if (!corpse->IsWithinDistInMap(player, INTERACTION_DISTANCE))
                        {
                            player->SendLootError(guid, LOOT_ERROR_TOO_FAR);
                            return false;
                        }
                        if (player->IsNonMeleeSpellCast(false))
                            player->InterruptNonMeleeSpells(false);
                        PayOwed(player, corpse);
                        OpenWindow(player, corpse);
                        return false;
                    }
                    if (!Corpse::Answers(Corpse::Packet::Release, tracked, windowOpen))
                        return true;
                    // Swallowed: the stock release would run AllLootRemovedFromCorpse on the
                    // placeholder and strip the sparkle for everyone else.
                    ReleaseWindow(player, true);
                    return false;
                }
                if (opcode == CMSG_LOOT_MONEY)
                    return !Corpse::Answers(Corpse::Packet::Money, false, windowOpen);
                if (!Corpse::Answers(Corpse::Packet::Pickup, false, windowOpen))
                    return true;
                if (player->HasPlayerFlag(PLAYER_FLAGS_NO_PLAY_TIME))
                {
                    player->SendEquipError(EQUIP_ERR_ALREADY_LOOTED, nullptr, nullptr);
                    return false;
                }
                std::uint8_t slot = 0;
                copy >> slot;
                Pickup(player, slot);
                return false;
            }
        };

        // The owner leaves: what they had not taken goes with the corpse (as a ground drop did).
        // The corpses' counts follow, and a corpse left with nothing is finished by its map's next tick.
        void DropOwnerRows(Player* player)
        {
            std::uint64_t const owner = player->GetGUID().GetRawValue();
            std::vector<std::tuple<std::uint32_t, std::uint32_t, std::uint64_t, std::uint32_t>> held;
            if (QueryResult result = CharacterDatabase.Query(
                    "SELECT map_id,instance_id,carrier_guid,COUNT(*) FROM dc_loot_buffer "
                    "WHERE guid={} AND kind='corpse' GROUP BY map_id,instance_id,carrier_guid",
                    owner))
                do
                {
                    Field* f = result->Fetch();
                    held.emplace_back(f[0].Get<std::uint32_t>(), f[1].Get<std::uint32_t>(), f[2].Get<std::uint64_t>(),
                                      f[3].Get<std::uint32_t>());
                } while (result->NextRow());
            if (held.empty())
                return;
            CharacterDatabase.DirectExecute("DELETE FROM dc_loot_buffer WHERE guid={} AND kind='corpse'", owner);
            std::lock_guard<std::mutex> lock(mutex);
            for (auto const& [mapId, instanceId, corpse, count] : held)
                for (auto& [map, entries] : corpses)
                    for (auto& [guid, entry] : entries)
                        if (guid.GetRawValue() == corpse && entry.mapId == mapId && entry.instanceId == instanceId)
                        {
                            entry.rows = entry.rows > count ? entry.rows - count : 0;
                            // Their beam goes with them. The stored value is left to the corpse's next change or
                            // its finish: everyone else is sent their own tier whatever it says.
                            entry.beams.erase(player->GetGUID());
                        }
        }

        // The sweep: once a tick on the map's own thread, the same place the ground carriers
        // were swept. A corpse that has left the world, left the corpse state, or belongs to a
        // closed rift takes its rows with it; a corpse with nothing left is finished.
        class CorpseMaps final : public AllMapScript
        {
        public:
            CorpseMaps()
                : AllMapScript("dc_corpse_loot_maps", {ALLMAPHOOK_ON_MAP_UPDATE, ALLMAPHOOK_ON_DESTROY_MAP})
            {
            }
            void OnMapUpdate(Map* map, std::uint32_t) override
            {
                std::vector<ObjectGuid> dead, emptied;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto found = corpses.find(map);
                    if (found == corpses.end())
                        return;
                    for (auto it = found->second.begin(); it != found->second.end();)
                    {
                        Creature* corpse = map->GetCreature(it->first);
                        bool const live = !it->second.rift ||
                                          DC::Rifts::IsLiveInstance(it->second.mapId, it->second.instanceId);
                        if (Corpse::CorpseEmpty(it->second.rows, static_cast<std::uint32_t>(it->second.owed.size())))
                            emptied.push_back(it->first);
                        else if (!Corpse::KeepRows(corpse != nullptr, IsCorpse(corpse), it->second.rift, live))
                            dead.push_back(it->first);
                        else
                        {
                            ++it;
                            continue;
                        }
                        it = found->second.erase(it);
                    }
                    if (found->second.empty())
                        corpses.erase(found);
                }
                if (!dead.empty())
                    DeleteRows(map->GetId(), map->GetInstanceId(), dead);
                for (ObjectGuid const& guid : dead)
                    if (Creature* corpse = map->GetCreature(guid); IsCorpse(corpse))
                        FinishCorpse(corpse);
                for (ObjectGuid const& guid : emptied)
                    if (Creature* corpse = map->GetCreature(guid); IsCorpse(corpse))
                        FinishCorpse(corpse);
            }
            void OnDestroyMap(Map* map) override
            {
                bool had = false;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    had = corpses.erase(map) > 0;
                }
                if (had)
                    DeleteRows(map->GetId(), map->GetInstanceId(), {});
            }
        };

        class CorpsePlayers final : public PlayerScript
        {
        public:
            CorpsePlayers()
                : PlayerScript("dc_corpse_loot_players", {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED,
                                                          PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_PLAYER_JUST_DIED})
            {
            }
            void OnPlayerLogout(Player* player) override
            {
                ReleaseWindow(player, false);
                DropOwnerRows(player);
            }
            void OnPlayerMapChanged(Player* player) override
            {
                ReleaseWindow(player, true);
            }
            void OnPlayerJustDied(Player* player) override
            {
                ReleaseWindow(player, true);
            }
            void OnPlayerUpdate(Player* player, std::uint32_t) override
            {
                ObjectGuid corpseGuid;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto found = windows.find(player->GetGUID());
                    if (found == windows.end())
                        return;
                    corpseGuid = found->second.corpse;
                }
                Creature* corpse = player->GetMap() ? player->GetMap()->GetCreature(corpseGuid) : nullptr;
                if (!Corpse::KeepWindow(IsCorpse(corpse), corpse ? player->GetDistance(corpse) : 0.0f,
                                        INTERACTION_DISTANCE))
                    ReleaseWindow(player, true);
            }
        };

        // Each viewer's own beam tier, written into the corpse's UNIT_FIELD_PADDING as the update is sent to them
        // (docs/contracts/loot-beam-tier.md). The core builds a unit's values once and patches them per viewer; this
        // asks it to note where the field sits and fills it in, the way mod-transmog does for item displays.
        class CorpseBeam final : public UnitScript
        {
        public:
            CorpseBeam()
                : UnitScript("dc_corpse_loot_beam", true,
                             {UNITHOOK_SHOULD_TRACK_VALUES_UPDATE_POS_BY_INDEX, UNITHOOK_ON_PATCH_VALUES_UPDATE})
            {
            }
            bool ShouldTrackValuesUpdatePosByIndex(Unit const* unit, uint8 /*updateType*/, uint16 index) override
            {
                return index == UNIT_FIELD_PADDING && unit->IsCreature();
            }
            void OnPatchValuesUpdate(Unit const* unit, ByteBuffer& buf, BuildValuesCachePosPointers& posPointers,
                                     Player* target) override
            {
                auto found = posPointers.other.find(UNIT_FIELD_PADDING);
                if (found == posPointers.other.end() || !unit->IsCreature() || !target)
                    return;
                buf.put(found->second, BeamFor(unit->GetMap(), unit->GetGUID(), target->GetGUID()));
            }
        };

        class CorpseWorld final : public WorldScript
        {
        public:
            CorpseWorld()
                : WorldScript("dc_corpse_loot_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                // loot_0009 drops the one-row-per-carrier key; with it still in place a
                // second owner's row on a corpse would fail, so corpse delivery stays off
                // and kills keep delivering directly.
                QueryResult unique = CharacterDatabase.Query(
                    "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() "
                    "AND table_name='dc_loot_buffer' AND index_name='dc_ground_carrier' AND non_unique=0");
                if (!unique || (*unique)[0].Get<std::uint64_t>() != 0)
                {
                    LOG_ERROR("server", "[DC corpse loot] Disabled: apply CHARACTERS loot_0009_corpse_rows.sql.");
                    return;
                }
                // Corpses do not survive a restart, and neither do their rows.
                CharacterDatabase.DirectExecute("DELETE FROM dc_loot_buffer WHERE kind='corpse'");
                // The loot beam's field: the core ships it never-sent (UF_FLAG_NONE); public, it rides every
                // unit update, and only a corpse holding a beam row ever stores anything in it.
                UnitUpdateFieldFlags[UNIT_FIELD_PADDING] = UF_FLAG_PUBLIC;
                ready = true;
                LOG_INFO("server.loading", "[DC corpse loot] Ready: drops are personal rows on the corpse.");
            }
        };
    } // namespace

    bool CorpseCanHold(Creature const* corpse)
    {
        return corpse &&
               Corpse::CanHoldRows(ready, !corpse->IsAlive(), corpse->hasLootRecipient(), corpse->GetLootMode());
    }

    bool CorpseHoldsRows(Creature const* corpse)
    {
        if (!corpse || !corpse->GetMap())
            return false;
        std::lock_guard<std::mutex> lock(mutex);
        auto found = corpses.find(corpse->GetMap());
        return found != corpses.end() && found->second.count(corpse->GetGUID());
    }

    bool OweCorpse(Creature* corpse, std::vector<ObjectGuid> const& owed, OwedPay pay)
    {
        if (!corpse || owed.empty() || !pay || !CorpseCanHold(corpse) || !corpse->GetMap())
            return false;
        Map* map = corpse->GetMap();
        bool first = false;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto& entry = corpses[map][corpse->GetGUID()];
            first = entry.rows == 0 && entry.owed.empty();
            entry.owed.insert(owed.begin(), owed.end());
            entry.pay = std::move(pay);
            entry.rift = DC::Rifts::IsLiveInstance(map->GetId(), map->GetInstanceId());
            entry.mapId = map->GetId();
            entry.instanceId = map->GetInstanceId();
        }
        Prepare(corpse);
        if (first)
            RestoreDecay(corpse);
        return true;
    }

    void KeepCorpseLootable(Creature* corpse)
    {
        Prepare(corpse);
    }

    bool DropCorpseLoot(Player* owner, Creature* corpse, std::uint32_t entry, unsigned itemLevel,
                        std::string const& rarity, char const* source, unsigned tier, char const* contentKind,
                        unsigned count, std::string const& rollClass, std::string const& quality)
    {
        if (!owner || !corpse || !CorpseCanHold(corpse) || !corpse->GetMap())
            return false;
        Map* map = corpse->GetMap();
        ObjectGuid const corpseGuid = corpse->GetGUID();
        Position const position = corpse->GetPosition();
        bool const inRift = DC::Rifts::IsLiveInstance(map->GetId(), map->GetInstanceId());
        std::string safeRarity = rarity, safeSource = source, safeKind = contentKind, safeClass = rollClass;
        CharacterDatabase.EscapeString(safeRarity);
        CharacterDatabase.EscapeString(safeSource);
        CharacterDatabase.EscapeString(safeKind);
        CharacterDatabase.EscapeString(safeClass);
        auto transaction = PlayerEconomy::BeginTransaction();
        transaction->Append(
            "INSERT INTO dc_loot_buffer (guid,base_item,item_level,rarity,drop_source,tier,kind,content_kind,"
            "carrier_guid,map_id,instance_id,phase_mask,drop_x,drop_y,drop_z,drop_o,in_rift,drop_count,"
            "expires_at,roll_class,quality_tier) VALUES ({},{},{},'{}','{}',{},'corpse','{}',{},{},{},{},{},{},{},{},{},{},{},'{}','{}')",
            owner->GetGUID().GetRawValue(), entry, itemLevel, safeRarity, safeSource, tier, safeKind,
            corpseGuid.GetRawValue(), map->GetId(), map->GetInstanceId(), owner->GetPhaseMask(),
            position.GetPositionX(), position.GetPositionY(), position.GetPositionZ(), position.GetOrientation(),
            inRift ? 1 : 0, count, NeverExpires, safeClass, DC::Quality::Clean(quality));
        ObjectGuid const ownerGuid = owner->GetGUID();
        std::uint32_t const beam = Corpse::BeamTier(rarity, DC::Quality::Clean(quality));
        auto publish = [map, corpseGuid, inRift, ownerGuid, beam]() { AddRow(map, corpseGuid, inRift, ownerGuid, beam); };
        if (PlayerEconomy::Current())
        {
            PlayerEconomy::AfterCommit(publish);
            return true;
        }
        if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
            return false;
        publish();
        return true;
    }

    void RegisterCorpseLootScripts()
    {
        new CorpsePackets();
        new CorpsePlayers();
        new CorpseMaps();
        new CorpseWorld();
        new CorpseBeam();
    }
} // namespace DC::Loot

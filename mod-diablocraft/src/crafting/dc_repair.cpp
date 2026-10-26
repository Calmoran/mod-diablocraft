// Constant (2): DurabilityQuality DBC lookup stride; Core DBC key mapping, not price multiplier.
// Crafting: the artisans' repair (the quote, the selection, the repair itself and the repair packet).
#include "dc_crafting_internal.h"
#include "../common/dc_economy.h"
#include "PlayerEconomy.h"
#include "Chat.h"
#include "Creature.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "Opcodes.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "World.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include <algorithm>
#include <cmath>
#include <vector>

namespace DC::Crafting
{
    using namespace Detail;
    namespace
    {
        uint64 RepairQuote(Player* player, Creature* npc, Item* item, double tuning)
        {
            auto* proto = item->GetTemplate();
            uint32 max = item->GetUInt32Value(ITEM_FIELD_MAXDURABILITY),
                   current = item->GetUInt32Value(ITEM_FIELD_DURABILITY);
            if (!max || current >= max)
                return 0;
            auto* costs = sDurabilityCostsStore.LookupEntry(proto->ItemLevel);
            auto* quality = sDurabilityQualityStore.LookupEntry((proto->Quality + 1) * 2);
            Need(costs && quality, "Repair price data is missing.");
            double base =
                std::floor(double(max - current) *
                           costs->multiplier[ItemSubClassToDurabilityMultiplierId(proto->Class, proto->SubClass)] *
                           quality->quality_mod);
            double value =
                std::floor(base * player->GetReputationPriceDiscount(npc) * sWorld->getRate(RATE_REPAIRCOST) * tuning);
            Need(std::isfinite(value) && value >= 0 && value < double(UINT64_MAX), "Invalid repair price.");
            return std::max<uint64>(TunableCount("repair_minimum_gold"), uint64(value));
        }
    } // namespace
    namespace Detail
    {
        std::vector<Item*> RepairSelection(Player* player, uint32 scope, uint32 guid)
        {
            Need(scope <= 2 && ((scope == 0 && guid > 0) || (scope != 0 && guid == 0)), "Choose an item, equipped gear or all items.");
            if (scope == 0)
                return {Owned(player, guid)};
            auto items = Inventory(player);
            if (scope == 1)
                items.erase(std::remove_if(items.begin(), items.end(), [](Item* item) { return !item->IsEquipped(); }), items.end());
            return items;
        }
        uint64 RepairTotal(Player* player, Creature* npc, std::vector<Item*> const& items)
        {
            auto row = WorldDatabase.Query("SELECT repair_multiplier FROM dc_loot_tuning WHERE source='normal'");
            Need(bool(row), "Repair prices are unavailable.");
            double tuning = (*row)[0].Get<double>();
            Need(std::isfinite(tuning) && tuning >= 0, "Invalid repair multiplier.");
            uint64 cost = 0;
            for (auto* item : items)
            {
                uint64 quote = RepairQuote(player, npc, item, tuning);
                Need(quote <= UINT64_MAX - cost, "The repair total exceeds supported currency capacity.");
                cost += quote;
            }
            return cost;
        }
        void Repair(Player* player, Creature* npc, Item* only, bool equippedOnly)
        {
            Artisan(player, npc->GetEntry());
            auto items = only ? std::vector<Item*>{only} : RepairSelection(player, equippedOnly ? 1 : 2, 0);
            uint64 cost = RepairTotal(player, npc, items);
            Need(Economy::CanAfford(player, cost) && Economy::Charge(player, cost),
                 "Not enough account gold to repair.");
            for (auto* item : items)
                player->DurabilityRepair(item->GetPos(), false, 1, false);
            Save(player, PlayerEconomy::BeginTransaction());
            ChatHandler(player->GetSession())
                .PSendSysMessage("Repaired for {} gold.", cost);
            LOG_INFO("server", "[DC crafting] {} repaired for {} gold", player->GetName(), cost);
        }
    } // namespace Detail
    namespace
    {
        class RepairPackets final : public ServerScript
        {
        public:
            RepairPackets()
                : ServerScript("dc_artisan_repair", {SERVERHOOK_CAN_PACKET_RECEIVE})
            {
            }
            bool CanPacketReceive(WorldSession* session, WorldPacket const& packet) override
            {
                if (packet.GetOpcode() != CMSG_REPAIR_ITEM || !session || !session->GetPlayer())
                    return true;
                if (packet.size() != 17)
                    return false;
                WorldPacket copy(packet);
                ObjectGuid npcGuid, itemGuid;
                uint8 guild;
                copy >> npcGuid >> itemGuid >> guild;
                auto* player = session->GetPlayer();
                // The Jeweler does not repair: refused here by name, whatever flags it
                // carries, rather than left to the stock handler.
                if (auto* target = player->GetMap()->GetCreature(npcGuid); target && target->GetEntry() == Jeweler)
                {
                    ChatHandler(session).SendSysMessage("The Jeweler does not repair.");
                    return false;
                }
                auto* npc = player->GetNPCIfCanInteractWith(npcGuid, UNIT_NPC_FLAG_REPAIR);
                if (!npc || (npc->GetEntry() != Blacksmith && npc->GetEntry() != Mystic))
                    return true;
                try
                {
                    Need(!guild, "Use your account gold for artisan repairs.");
                    auto* item = itemGuid ? Owned(player, itemGuid.GetCounter()) : nullptr;
                    Repair(player, npc, item);
                }
                catch (std::exception const& error)
                {
                    if (auto* op = PlayerEconomy::Current(); op && (op->Dirty() || op->transaction->GetSize()))
                        PlayerEconomy::Fail();
                    ChatHandler(session).SendSysMessage(error.what());
                }
                return false;
            }
        };
    } // namespace
    namespace Detail
    {
        void RegisterRepairScripts()
        {
            new RepairPackets();
        }
    } // namespace Detail
} // namespace DC::Crafting

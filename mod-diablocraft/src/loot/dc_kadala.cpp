// Kadala's purchase (docs/proposals/kadala.md 3.2).
//
// The stock buy packet reaches Player::BuyItemFromVendorSlot, whose first line is the module hook below. For one of
// Kadala's Mystery entries the hook takes the purchase over (item = 0, the core's own "custom vendor process"), so the
// stock bag-count price check, which cannot see account shards, and the stock store step, which would hand over the
// Mystery item itself, never run. Every other vendor stays stock.
//
// Core patch 0007 already wraps every buy packet in one account operation. Inside it: check what the stock path would
// have (dc_kadala_rule.h), roll the item (PickGamble), stage it, debit the Blood Shards from the ledger, commit the two
// together, then publish the item and send the stock confirmation. A refusal before the stage changes nothing.
#include "dc_kadala_rule.h"
#include "dc_loot.h"

#include "../common/dc_account_economy.h"
#include "../common/dc_blood_shards.h"
#include "../common/dc_tunables.h"
#include "../items/dc_items.h"

#include "Creature.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <map>
#include <mutex>
#include <optional>
#include <string>

namespace DC::Loot
{
    namespace
    {
        std::mutex entriesMutex;
        std::map<std::uint32_t, Kadala::SlotFilter> entries; // Mystery item entry -> what it sells

        std::optional<Kadala::SlotFilter> FilterOf(std::uint32_t item)
        {
            std::lock_guard<std::mutex> lock(entriesMutex);
            auto found = entries.find(item);
            if (found == entries.end())
                return std::nullopt;
            return found->second;
        }

        // Keeps the account operation honest once something has been staged: unless the commit went through, the
        // operation fails and the session reloads its last committed state, as IdentifyOne does.
        struct Staged
        {
            Player* player;
            bool committed = false;
            ~Staged()
            {
                if (committed)
                    return;
                PlayerEconomy::Fail();
                player->GetSession()->AbortEconomy();
            }
        };

        void Buy(Player* player, ObjectGuid vendorGuid, std::uint32_t vendorSlot, std::uint32_t entry, unsigned count,
                 Kadala::SlotFilter const& filter)
        {
            Creature* creature = player->GetNPCIfCanInteractWith(vendorGuid, UNIT_NPC_FLAG_VENDOR);
            ItemTemplate const* proto = sObjectMgr->GetItemTemplate(entry);
            VendorItem const* listed = nullptr;
            if (creature)
                if (VendorItemData const* items =
                        player->GetSession()->GetCurrentVendor()
                            ? sObjectMgr->GetNpcVendorItemList(player->GetSession()->GetCurrentVendor())
                            : creature->GetVendorItems();
                    items && vendorSlot < items->GetItemCount())
                    if (VendorItem const* row = items->GetItem(vendorSlot); row && row->item == entry)
                        listed = row;

            Kadala::Facts facts;
            facts.alive = player->IsAlive();
            facts.count = count;
            facts.inReach = creature != nullptr;
            facts.onList = listed != nullptr;
            // The stock rule (Player.cpp:10956): a bind-on-pickup entry is closed to the classes its mask leaves out.
            facts.classAllowed = proto && ((proto->AllowableClass & player->getClassMask()) ||
                                           proto->Bonding != BIND_WHEN_PICKED_UP || player->IsGameMaster());

            // The price is the server's own copy of the entry's ExtendedCost row, never anything the client sent.
            if (listed && listed->ExtendedCost && DC::AccountEconomy::Enabled())
                if (ItemExtendedCostEntry const* row = sItemExtendedCostStore.LookupEntry(listed->ExtendedCost))
                {
                    Kadala::CostRow cost;
                    for (unsigned i = 0; i < cost.item.size(); ++i)
                    {
                        cost.item[i] = row->reqitem[i];
                        cost.count[i] = row->reqitemcount[i];
                    }
                    cost.honor = row->reqhonorpoints;
                    cost.arena = row->reqarenapoints;
                    cost.arenaRating = row->reqpersonalarenarating;
                    facts.priced = Kadala::ShardPrice(cost, BloodShards::Entry, facts.price);
                }
            facts.held = DC::AccountEconomy::MaterialBalance(player, BloodShards::Entry);

            unsigned const level = player->GetLevel();
            std::string const rollClass = DC::Items::ClassKeyOf(player->getClass());
            std::uint32_t const base =
                rollClass.empty()
                    ? 0
                    : PickGamble(filter, level, rollClass, DC::Tunables::Get("loot", "kadala_legendary_pct"));
            facts.rolled = base != 0;
            ItemPosCountVec cell;
            InventoryResult const room =
                base ? player->CanStoreNewItem(NULL_BAG, NULL_SLOT, cell, base, 1) : EQUIP_ERR_OK;
            facts.bagFree = room == EQUIP_ERR_OK;

            switch (Kadala::Judge(facts))
            {
                case Kadala::Verdict::Buy:
                    break;
                case Kadala::Verdict::Dead:
                    return;
                case Kadala::Verdict::TooFar:
                    player->SendBuyError(BUY_ERR_DISTANCE_TOO_FAR, nullptr, entry, 0);
                    return;
                case Kadala::Verdict::TooFewShards:
                    player->SendEquipError(EQUIP_ERR_VENDOR_MISSING_TURNINS, nullptr, nullptr);
                    return;
                case Kadala::Verdict::BagsFull:
                    player->SendEquipError(room, nullptr, nullptr, base);
                    return;
                case Kadala::Verdict::NoPrice:
                    LOG_ERROR(
                        "server",
                        "[DC kadala] entry {} on {}'s list has no Blood Shard price (ExtendedCost {}, economy {})",
                        entry, player->GetName(), listed ? listed->ExtendedCost : 0, DC::AccountEconomy::Enabled());
                    [[fallthrough]];
                default:
                    player->SendBuyError(BUY_ERR_CANT_FIND_ITEM, creature, entry, 0);
                    return;
            }

            PlayerEconomy::Scope operation(player);
            auto transaction = PlayerEconomy::BeginTransaction();
            // No class named here: the roll class is the buyer's (kadala.md 4.7), and an identified item needs no
            // shell.
            // A gamble is not a monster drop: Ancient and Primal need the level only, on any difficulty (D3).
            auto staged = DC::Items::StageRoll(player, base, level, "", transaction, rollClass,
                                               DC::Items::RollQuality(player, base, level, 0, true));
            if (!staged || !staged->GetItem())
            {
                // Nothing was stored, so nothing needs undoing.
                player->SendBuyError(BUY_ERR_CANT_FIND_ITEM, creature, entry, 0);
                return;
            }
            Staged guard{player};
            if (!DC::AccountEconomy::DebitMaterial(player, BloodShards::Entry, facts.price))
                return;
            player->SaveInventoryAndGoldToDB(transaction);
            if (!DC::AccountEconomy::Commit(player, transaction))
                return;
            guard.committed = true;

            Item* item = staged->Publish();
            if (!item)
                return;
            // The stock confirmation (Player.cpp:10903): the vendor window's own line, then the item-received line.
            WorldPacket data(SMSG_BUY_ITEM, 8 + 4 + 4 + 4);
            data << creature->GetGUID();
            data << std::uint32_t(vendorSlot + 1); // numbered from 1 at the client
            data << std::int32_t(-1);              // unlimited stock
            data << std::uint32_t(1);
            player->SendDirectMessage(&data);
            player->SendNewItem(item, 1, true, false, false);
            LOG_INFO("server", "[DC kadala] {} bought Mystery {} for {} Blood Shards: base {} level {} class {}",
                     player->GetName(), entry, facts.price, base, level, rollClass);
        }

        class KadalaWorld final : public WorldScript
        {
        public:
            KadalaWorld()
                : WorldScript("dc_kadala_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                QueryResult result = WorldDatabase.Query("SELECT item_entry, slot, base_types FROM dc_kadala_entry");
                if (!result)
                {
                    LOG_ERROR(
                        "server",
                        "dc_kadala_entry is missing or empty (apply kadala_0002_entries.sql): Kadala cannot sell");
                    return;
                }
                std::map<std::uint32_t, Kadala::SlotFilter> loaded;
                do
                {
                    Field* fields = result->Fetch();
                    loaded[fields[0].Get<std::uint32_t>()] = {fields[1].Get<std::string>(),
                                                              Kadala::SplitTypes(fields[2].Get<std::string>())};
                } while (result->NextRow());
                std::lock_guard<std::mutex> lock(entriesMutex);
                entries = std::move(loaded);
                LOG_INFO("server.loading", "[DC kadala] {} Mystery entries", entries.size());
            }
        };

        class KadalaPlayer final : public PlayerScript
        {
        public:
            KadalaPlayer()
                : PlayerScript("dc_kadala_player", {PLAYERHOOK_ON_BEFORE_BUY_ITEM_FROM_VENDOR})
            {
            }
            void OnPlayerBeforeBuyItemFromVendor(Player* player, ObjectGuid vendorGuid, uint32 vendorSlot, uint32& item,
                                                 uint8 count, uint8, uint8) override
            {
                auto filter = FilterOf(item);
                if (!player || !filter)
                    return;
                std::uint32_t const entry = item;
                item = 0; // the stock path stops here, on success and on refusal alike
                Buy(player, vendorGuid, vendorSlot, entry, count, *filter);
            }
        };
    } // namespace

    void RegisterKadalaScripts()
    {
        new KadalaWorld();
        new KadalaPlayer();
    }
} // namespace DC::Loot

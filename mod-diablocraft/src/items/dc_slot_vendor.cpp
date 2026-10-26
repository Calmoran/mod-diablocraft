// The legendary slot vendors' purchase (docs/proposals/kadala.md 6.5).
//
// Thirteen stock vendors, one per slot, list every legendary and set item of the slot by name, free
// (generate_slot_vendors.py, dc_slot_vendor). The stock buy packet reaches Player::BuyItemFromVendorSlot, whose first
// line is the module hook below. For one of these vendors the hook takes every purchase over (item = 0, the core's own
// "custom vendor process"), on success and on refusal alike, so the stock store step, which would hand over the bare
// template with no affixes, never runs. Other vendors stay stock. It reuses the way the Kadala hook buys (one account
// operation, the roller's StageRoll, one commit, the stock confirmation) and shares nothing else with her.
//
// Inside the account operation core patch 0007 already opens for every buy packet: check what the stock path would have
// (dc_slot_vendor_rule.h), stage the entry's own base through StageRoll (identified, no shell), commit, publish,
// confirm. A refusal before the stage changes nothing. Per kadala.md 6.7.3 a bought item sells and salvages
// like any drop.
#include "dc_items.h"
#include "dc_slot_vendor_rule.h"

#include "ConditionMgr.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include "../common/dc_account_economy.h"

#include <map>
#include <mutex>
#include <string>

namespace DC::Items
{
    namespace
    {
        // What the roll class of a listed item depends on, read from dc_base_item and dc_set_class like the drops do.
        struct Listed
        {
            std::string designated, setClass;
        };
        std::mutex listsMutex;
        std::map<std::uint32_t, std::map<std::uint32_t, Listed>> lists; // slot vendor entry -> item entry -> roll facts

        bool IsSlotVendor(std::uint32_t vendor)
        {
            std::lock_guard<std::mutex> lock(listsMutex);
            return lists.count(vendor) != 0;
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

        void Buy(Player* player, Creature* vendor, std::uint32_t vendorSlot, std::uint32_t entry, unsigned count)
        {
            Creature* creature = player->GetNPCIfCanInteractWith(vendor->GetGUID(), UNIT_NPC_FLAG_VENDOR);
            VendorItem const* listed = nullptr;
            if (creature)
                if (VendorItemData const* items =
                        player->GetSession()->GetCurrentVendor()
                            ? sObjectMgr->GetNpcVendorItemList(player->GetSession()->GetCurrentVendor())
                            : creature->GetVendorItems();
                    items && vendorSlot < items->GetItemCount())
                    if (VendorItem const* row = items->GetItem(vendorSlot); row && row->item == entry)
                        listed = row;

            Listed roll;
            {
                std::lock_guard<std::mutex> lock(listsMutex);
                auto const& forVendor = lists[vendor->GetEntry()];
                if (auto found = forVendor.find(entry); listed && found != forVendor.end())
                    roll = found->second;
                else
                    listed = nullptr;
            }

            SlotVendor::Facts facts;
            facts.alive = player->IsAlive();
            facts.count = count;
            facts.inReach = creature != nullptr;
            facts.onList = listed != nullptr;
            // The stock level condition of the entry (Player.cpp:10975), which the stock path would have checked.
            facts.conditionMet =
                creature &&
                sConditionMgr->IsObjectMeetToConditions(
                    player, creature, sConditionMgr->GetConditionsForNpcVendorEvent(creature->GetEntry(), entry));

            std::string const rollClass =
                SlotVendor::RollClassFor(roll.designated, roll.setClass, ClassKeyOf(player->getClass()));
            facts.rollClassKnown = !rollClass.empty();
            ItemPosCountVec cell;
            InventoryResult const room =
                facts.onList ? player->CanStoreNewItem(NULL_BAG, NULL_SLOT, cell, entry, 1) : EQUIP_ERR_OK;
            facts.bagFree = room == EQUIP_ERR_OK;

            switch (SlotVendor::Judge(facts))
            {
                case SlotVendor::Verdict::Buy:
                    break;
                case SlotVendor::Verdict::Dead:
                    return;
                case SlotVendor::Verdict::TooFar:
                    player->SendBuyError(BUY_ERR_DISTANCE_TOO_FAR, nullptr, entry, 0);
                    return;
                case SlotVendor::Verdict::BagsFull:
                    player->SendEquipError(room, nullptr, nullptr, entry);
                    return;
                default:
                    player->SendBuyError(BUY_ERR_CANT_FIND_ITEM, creature, entry, 0);
                    return;
            }

            PlayerEconomy::Scope operation(player);
            auto transaction = PlayerEconomy::BeginTransaction();
            // The item level is the buyer's (6.5 step 3); the base is the entry itself and arrives identified.
            // A purchase is not a monster drop: Ancient and Primal need the level only.
            auto staged = StageRoll(player, entry, player->GetLevel(), "", transaction, rollClass,
                                    RollQuality(player, entry, player->GetLevel(), 0, true));
            if (!staged || !staged->GetItem())
            {
                // Nothing was stored, so nothing needs undoing.
                player->SendBuyError(BUY_ERR_CANT_FIND_ITEM, creature, entry, 0);
                return;
            }
            Staged guard{player};
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
            LOG_INFO("server", "[DC slot vendor] {} took item {} from vendor {}: level {} class {}", player->GetName(),
                     entry, creature->GetEntry(), player->GetLevel(), rollClass);
        }

        class SlotVendorWorld final : public WorldScript
        {
        public:
            SlotVendorWorld()
                : WorldScript("dc_slot_vendor_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                QueryResult result = WorldDatabase.Query(
                    "SELECT v.entry, n.item, b.designated_class, COALESCE(sc.class_key, '') "
                    "FROM dc_slot_vendor v JOIN npc_vendor n ON n.entry = v.entry "
                    "JOIN dc_base_item b ON b.entry = n.item LEFT JOIN dc_set_class sc ON sc.set_name = b.set_name");
                if (!result)
                {
                    LOG_ERROR("server", "dc_slot_vendor is missing or empty (apply slot_vendors_0001.sql): the slot "
                                        "vendors cannot sell");
                    return;
                }
                std::map<std::uint32_t, std::map<std::uint32_t, Listed>> loaded;
                std::size_t entries = 0;
                do
                {
                    Field* fields = result->Fetch();
                    loaded[fields[0].Get<std::uint32_t>()][fields[1].Get<std::uint32_t>()] = {
                        fields[2].Get<std::string>(), fields[3].Get<std::string>()};
                    ++entries;
                } while (result->NextRow());
                std::lock_guard<std::mutex> lock(listsMutex);
                lists = std::move(loaded);
                LOG_INFO("server.loading", "[DC slot vendor] {} vendors, {} entries", lists.size(), entries);
            }
        };

        class SlotVendorPlayer final : public PlayerScript
        {
        public:
            SlotVendorPlayer()
                : PlayerScript("dc_slot_vendor_player", {PLAYERHOOK_ON_BEFORE_BUY_ITEM_FROM_VENDOR})
            {
            }
            void OnPlayerBeforeBuyItemFromVendor(Player* player, ObjectGuid vendorGuid, uint32 vendorSlot, uint32& item,
                                                 uint8 count, uint8, uint8) override
            {
                if (!player || !item)
                    return;
                Creature* vendor = ObjectAccessor::GetCreature(*player, vendorGuid);
                if (!vendor || !IsSlotVendor(vendor->GetEntry()))
                    return;
                std::uint32_t const entry = item;
                item = 0; // the stock path stops here, on success and on refusal alike
                Buy(player, vendor, vendorSlot, entry, count);
            }
        };
    } // namespace

    void RegisterSlotVendorScripts()
    {
        new SlotVendorWorld();
        new SlotVendorPlayer();
    }
} // namespace DC::Items

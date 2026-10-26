/*
 * World of DiabloCraft - account stash (11-hardcore §4).
 *
 * Storage rules:
 *   A3  the container is keyed by account and mode only, never by character
 *   A5  character deletion and restart never touch the stash; deleting the
 *       ACCOUNT deletes it and its parked items (AccountSweep)
 *   A6  the principal is the session's account plus the permanent mode row;
 *       an unchosen mode is refused, never mapped to normal
 *   A7  before every operation: approved Stash object, map/phase/range, chosen
 *       mode, alive, no hardcore death pending or recorded
 *   A14 one tab at launch, four more at dc_stash_tuning.price_gold; an unset
 *       price refuses the purchase; no gold is ever stored in the stash
 *   A15 real item rows, real binding checks: our account-bound gear only for
 *       its own account, and stock soulbinding is not relaxed
 *
 * A deposit is the guild bank's own move (Guild.cpp:473): the item leaves the
 * bag, its character_inventory row goes, and the item_instance row is parked
 * with owner and container cleared. The item guid never changes, so every
 * dc_item_instance / dc_item_affix / gem row survives untouched.
 */

#include "dc_stash.h"

#include "../common/dc_tunables.h"
#include "dc_items.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_economy.h"
#include "../hardcore/dc_hardcore.h"
#include "Bag.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "ObjectDefines.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "WorldSession.h"
#include <algorithm>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (25600): upper bound on a packed bag/slot index; Matches the 8-bit bag/slot packing used two lines below it, but nothing states that.

namespace DC::Stash
{
    // The three tunable numbers, read
    // from dc_tunables rather than compiled in (tunables phase 2 §A, audit rows
    // 30, 31 and 33). `.dc tunables set economy stash_max_tabs 6` and the next
    // stash window sees six.
    std::uint8_t MaxTabs()
    {
        return static_cast<std::uint8_t>(DC::Tunables::Get("economy", "stash_max_tabs"));
    }

    std::uint8_t LaunchTabs()
    {
        return static_cast<std::uint8_t>(DC::Tunables::Get("economy", "stash_launch_tabs"));
    }

    float ActionRange()
    {
        return static_cast<float>(DC::Tunables::Get("ui", "stash_action_range_yards"));
    }

    namespace
    {
        using Acore::ChatCommands::ChatCommandTable;

        // OpenRange claims to be the core's own interaction range. Keep that a fact
        // rather than a comment: if the core ever retunes INTERACTION_DISTANCE, the
        // stash stops compiling instead of quietly opening at a different distance.
        static_assert(OpenRange == INTERACTION_DISTANCE,
                      "DC::Stash::OpenRange must stay the core's INTERACTION_DISTANCE");

        void Need(bool ok, char const* message)
        {
            if (!ok)
                throw std::runtime_error(message);
        }

        // Same refusal, for the two messages that have to name MaxTabs() now that
        // it is a tunable: "all five tabs" reads as a lie the moment the tunable says six.
        void Need(bool ok, std::string const& message)
        {
            if (!ok)
                throw std::runtime_error(message);
        }

        // ---------------------------------------------------------------- principal

        // A3/A6. Account plus mode, and nothing else. Mode is the permanent row, so a
        // normal and a hardcore character on one account never see the same container.
        struct Key
        {
            std::uint32_t account = 0;
            bool hardcore = false;

            bool operator<(Key const& other) const
            {
                return account != other.account ? account < other.account : hardcore < other.hardcore;
            }
            char const* Mode() const
            {
                return hardcore ? "hardcore" : "normal";
            }
        };

        // Everything A7 checks about the PLAYER, with the Stash object left out.
        // Authorize adds that object below; a bag-to-bag move (Rebag) writes no stash
        // row and so has no business requiring it, but it is still an inventory write
        // and every condition here is what makes one safe at all.
        Key Actor(Player* player, char const* dead, char const* combat, char const* unchosen)
        {
            Need(player && player->GetSession(), "No session.");
            Need(player->IsAlive(), dead);
            Need(!player->IsInCombat(), combat);
            Hardcore::Mode const mode = Hardcore::ModeOf(player);
            Need(mode != Hardcore::Mode::Unchosen, unchosen);
            // A7/A8. IsLocked is the recorded death; DeathPending is the one the core
            // has not written yet, so a queued packet cannot withdraw between the kill
            // and the logout.
            Need(!Hardcore::IsLocked(player->GetGUID().GetCounter()), "This Hardcore character has fallen.");
            Need(!Hardcore::DeathPending(player), "This Hardcore character has fallen.");
            return {player->GetSession()->GetAccountId(), mode == Hardcore::Mode::Hardcore};
        }

        Key Authorize(Player* player)
        {
            Key const key = Actor(player, "You cannot use the Stash while dead.", "Use the Stash out of combat.",
                                  "This character has no mode yet. Log out and back in, then try again.");
            // Entry, map, phase and range in one call: FindNearestCreature filters on
            // IsWithinDistInMap, which is IsInMap && InSamePhase && distance. Every
            // caller of Authorize is an action on an already-open window, so this is
            // ActionRange, a yard wider than the OpenRange the window opened at.
            Need(player->FindNearestCreature(StashEntry, ActionRange()) != nullptr, "Stand at the hub Stash.");
            return key;
        }

        // ---------------------------------------------------------------- container

        struct Container
        {
            std::uint8_t tabs = LaunchTabs();
            std::uint64_t revision = 0;
            std::map<std::uint16_t, Item*> items; // tab * SlotsPerTab + slot -> parked item
            bool loaded = false;
        };

        std::mutex registry;
        std::map<Key, Container> containers;
        std::map<Key, std::shared_ptr<std::mutex>> operations;

        // A11. One operation at a time per account and mode. One WoW account holds one
        // session, so this is belt and braces - but the rule is the rule, and a second
        // map thread must never interleave two halves of a move.
        std::shared_ptr<std::mutex> OperationLock(Key const& key)
        {
            std::lock_guard<std::mutex> guard(registry);
            auto& lock = operations[key];
            if (!lock)
                lock = std::make_shared<std::mutex>();
            return lock;
        }

        void LoadItems(Key const& key, Container& container)
        {
            // Field order 0..10 is exactly what Item::LoadFromDB reads; 11..14 are ours.
            auto rows = CharacterDatabase.Query(
                "SELECT ii.creatorGuid,ii.giftCreatorGuid,ii.count,ii.duration,ii.charges,ii.flags,ii.enchantments,"
                "ii.randomPropertyId,ii.durability,ii.playedTime,ii.text,s.tab_id,s.slot_id,s.item_guid,ii.itemEntry "
                "FROM dc_account_stash_item s JOIN item_instance ii ON ii.guid=s.item_guid "
                "WHERE s.account_id={} AND s.mode='{}' ORDER BY s.tab_id,s.slot_id",
                key.account, key.Mode());
            if (!rows)
                return;
            do
            {
                Field* fields = rows->Fetch();
                std::uint8_t const tab = fields[11].Get<uint8>();
                std::uint8_t const slot = fields[12].Get<uint8>();
                std::uint32_t const itemGuid = fields[13].Get<uint32>();
                std::uint32_t const entry = fields[14].Get<uint32>();
                if (tab >= MaxTabs() || slot >= SlotsPerTab)
                {
                    LOG_ERROR("server", "[DC stash] account {} mode {} holds item {} at tab {} slot {}; skipped.",
                              key.account, key.Mode(), itemGuid, tab, slot);
                    continue;
                }
                ItemTemplate const* proto = sObjectMgr->GetItemTemplate(entry);
                if (!proto)
                {
                    LOG_ERROR("server", "[DC stash] unknown item template {} for stash item {}; skipped.", entry,
                              itemGuid);
                    continue;
                }
                Item* item = NewItemOrBag(proto);
                if (!item->LoadFromDB(itemGuid, ObjectGuid::Empty, fields, entry))
                {
                    // The item_instance row is gone. Drop the dangling link, never the
                    // row: A5 keeps the container, and there is nothing left to keep.
                    LOG_ERROR("server", "[DC stash] item {} has no item_instance row; link removed.", itemGuid);
                    CharacterDatabase.Execute("DELETE FROM dc_account_stash_item WHERE item_guid={}", itemGuid);
                    delete item;
                    continue;
                }
                item->AddToWorld();
                container.items[std::uint16_t(tab * SlotsPerTab + slot)] = item;
            } while (rows->NextRow());
        }

        // Reads the container, creating the account row on first use. Never called
        // without the operation lock held.
        Container& Get(Key const& key)
        {
            Container* container = nullptr;
            {
                std::lock_guard<std::mutex> guard(registry);
                container = &containers[key];
            }
            if (container->loaded)
                return *container;
            CharacterDatabase.DirectExecute(
                "INSERT IGNORE INTO dc_account_stash(account_id,mode,tabs_granted,revision) "
                "VALUES({},'{}',{},0)",
                key.account, key.Mode(), LaunchTabs());
            if (auto row =
                    CharacterDatabase.Query("SELECT tabs_granted,revision FROM dc_account_stash WHERE account_id={} "
                                            "AND mode='{}'",
                                            key.account, key.Mode()))
            {
                container->tabs = std::min<std::uint8_t>((*row)[0].Get<uint8>(), MaxTabs());
                container->revision = (*row)[1].Get<uint64>();
            }
            if (!container->tabs)
                container->tabs = LaunchTabs();
            LoadItems(key, *container);
            container->loaded = true;
            return *container;
        }

        // Drops the cached copy. The caller must already hold the operation lock.
        void Purge(Key const& key)
        {
            std::lock_guard<std::mutex> guard(registry);
            auto found = containers.find(key);
            if (found == containers.end())
                return;
            for (auto const& entry : found->second.items)
            {
                if (entry.second->IsInWorld())
                    entry.second->RemoveFromWorld();
                delete entry.second;
            }
            containers.erase(found);
        }

        void Release(Key const& key)
        {
            std::lock_guard<std::mutex> operation(*OperationLock(key));
            Purge(key);
        }

        // --------------------------------------------------------------- addressing

        // The addon never computes a position. It sends back the index the snapshot
        // gave it, and both sides encode the same way:
        //   stash index = tab * 70 + slot
        //   bag index   = container * 100 + slot, with container 255 for the backpack
        //   -1          = "the first free slot on this side", which is the right-click
        constexpr std::int32_t AutoPlace = -1;

        std::uint16_t StashSlot(Container const& container, std::int32_t index)
        {
            Need(index >= 0 && index < std::int32_t(container.tabs) * SlotsPerTab, "That stash slot is not unlocked.");
            return std::uint16_t(index);
        }

        void DecodeBag(std::int32_t index, std::uint8_t& bag, std::uint8_t& slot)
        {
            Need(index >= 0 && index < 25600, "That is not a bag slot.");
            bag = std::uint8_t(index / 100);
            slot = std::uint8_t(index % 100);
            if (bag == INVENTORY_SLOT_BAG_0)
            {
                // Equipped gear and the bag buttons themselves are not stashable from
                // here; the stash grid only ever offers the 16 backpack slots.
                Need(slot >= INVENTORY_SLOT_ITEM_START && slot < INVENTORY_SLOT_ITEM_END, "That is not a bag slot.");
                return;
            }
            Need(bag >= INVENTORY_SLOT_BAG_START && bag < INVENTORY_SLOT_BAG_END, "That is not a bag slot.");
        }

        // ------------------------------------------------------------- item legality

        // A15. Real binding checks. Our account-bound gear travels inside its own
        // account and nowhere else; everything stock soulbound stays where it is.
        void CheckDepositable(Item* item, Key const& key, bool worn = false)
        {
            Need(item != nullptr, "There is no item in that slot.");
            Need(!item->IsNotEmptyBag(), "Empty that bag before stashing it.");
            Need(!item->IsInTrade(), "That item is in a trade.");
            Need(!item->IsWrapped(), "A wrapped gift cannot go in the Stash.");
            Need(item->GetUInt32Value(ITEM_FIELD_DURATION) == 0, "Items with a timer cannot go in the Stash.");
            std::uint32_t const entry = item->GetEntry();
            Need(entry != Economy::GoldBarEntry, "Gold Bars are retired; they cannot be stashed.");
            Need(!AccountEconomy::IsMaterial(entry), "Materials are account totals, not stash items.");
            auto rolled = Items::Get(item->GetGUID().GetCounter());
            if (rolled && rolled->boundAccount)
                Need(rolled->boundAccount == key.account, "That item is bound to another account.");
            // A template bound to the account (the stock flag; the Horadric Caches, bounties_0004) binds
            // in bags but travels inside its account, and this stash is the account's: D3's account-bound items go in
            // the shared stash.
            else if (!item->IsBoundAccountWide())
                Need(item->CanBeTraded(), worn ? "That item bound to you when you put it on, so it cannot go in the Stash."
                                               : "Soulbound items cannot go in the Stash.");
        }

        // ---------------------------------------------------------------- the moves

        // A slot write is a DELETE and an INSERT, and they are separate calls on
        // purpose. dc_account_stash_item carries UNIQUE KEY
        // dc_account_stash_item_guid (stash_0001_account_stash.sql:44), so an item
        // is linked in one slot of one container and nowhere else. Writing a slot
        // as its own delete-then-insert meant a move inside the stash INSERTed the
        // source guid at the destination while the source's own row was still
        // there, and the unique key refused it - which is why every stash-to-stash
        // move failed. Callers now clear EVERY slot they touch
        // before they fill any of them.
        void ClearSlot(CharacterDatabaseTransaction const& transaction, Key const& key, std::uint16_t position)
        {
            transaction->Append("DELETE FROM dc_account_stash_item WHERE account_id={} "
                                "AND mode='{}' AND tab_id={} AND "
                                "slot_id={}",
                                key.account, key.Mode(), std::uint8_t(position / SlotsPerTab),
                                std::uint8_t(position % SlotsPerTab));
        }

        void FillSlot(CharacterDatabaseTransaction const& transaction, Key const& key, std::uint16_t position,
                      Item* item)
        {
            transaction->Append("INSERT INTO "
                                "dc_account_stash_item(account_id,mode,tab_id,slot_id,item_guid) "
                                "VALUES({},'{}',{},{},{})",
                                key.account, key.Mode(), std::uint8_t(position / SlotsPerTab),
                                std::uint8_t(position % SlotsPerTab), item->GetGUID().GetCounter());
        }

        // Guild.cpp:473 with our own link table. The item keeps its guid, so nothing
        // that hangs off that guid has to move.
        void Park(CharacterDatabaseTransaction const& transaction, Item* item)
        {
            item->SetGuidValue(ITEM_FIELD_CONTAINED, ObjectGuid::Empty);
            item->SetGuidValue(ITEM_FIELD_OWNER, ObjectGuid::Empty);
            item->FSetState(ITEM_NEW);
            item->SaveToDB(transaction);
        }

        // ------------------------------------------------------------- the bag side

        // Player::MoveItemFromInventory (PlayerStorage.cpp:3056) with its last
        // statement left out; AnnounceTaken below is that statement.
        //
        // The statement is sScriptMgr->OnPlayerAfterMoveItemFromInventory, and the
        // only listener on this server is dc_loot.cpp:598, which answers it by
        // delivering a buffered drop into the cell that has just been freed. In a
        // stash swap that cell is the one the incoming stash item was measured
        // against, and Player::_StoreItem (PlayerStorage.cpp:2750) adds counts to
        // whatever it finds at the position without comparing entries: one item
        // ends up with count 2 and the other is destroyed.
        //
        // Re-picking the cell afterwards cannot be made safe. The buffer only holds
        // a drop while the bags are FULL, and full bags mean the cell the swap just
        // freed is the only free cell there is - so there is nowhere to re-pick to,
        // and the item that has already left the bag has no way back. Deferring the
        // hook is the other fix the bug entry offers, and this is the half of it
        // that lives in this file; dc_loot.cpp belongs to another lane. Nothing is
        // lost: the buffer still delivers, one moment later, into bags that have
        // stopped moving.
        //
        // This mirrors a core function, so it is pinned to it by name and line. If
        // an AzerothCore update changes that function, this changes with it.
        void TakeFromBags(Player* player, std::uint8_t bag, std::uint8_t slot, Item* item)
        {
            player->ItemRemovedQuestCheck(item->GetEntry(), item->GetCount());
            player->RemoveItem(bag, slot, true);
            player->UpdateTitansGrip();
            item->SetNotRefundable(player, false);
            item->RemoveFromUpdateQueueOf(player);
            if (item->IsInWorld())
            {
                item->RemoveFromWorld();
                item->DestroyForPlayer(player);
            }
        }

        void AnnounceTaken(Player* player, Item* item, std::uint8_t bag, std::uint8_t slot)
        {
            sScriptMgr->OnPlayerAfterMoveItemFromInventory(player, item, bag, slot, true);
        }

        // True when every cell a store would write to is empty, so _StoreItem takes
        // its "nothing here" branch and cannot add counts to another item.
        // CanStoreItem answers for the bags as they were when it ran; this is the
        // assertion that they have not moved since.
        bool CellsAreFree(Player* player, ItemPosCountVec const& destination)
        {
            for (auto const& cell : destination)
                if (player->GetItemByPos(cell.pos))
                    return false;
            return true;
        }

        // Player::StoreItem clones the item once per cell when a destination spans
        // more than one (PlayerStorage.cpp:2682), and a clone has its own guid and
        // none of the rolled rows that hang off the original, so a store into more
        // than one cell is refused rather than attempted. One cell always is.
        bool StoreOne(Player* player, ItemPosCountVec const& destination, Item* item)
        {
            if (destination.size() != 1)
                return false;
            if (item->IsInWorld())
                item->RemoveFromWorld();
            player->MoveItemToInventory(destination, item, true);
            return true;
        }

        std::uint16_t FirstFreeStashSlot(Container const& container)
        {
            for (std::uint16_t position = 0; position < std::uint16_t(container.tabs) * SlotsPerTab; ++position)
                if (!container.items.count(position))
                    return position;
            throw std::runtime_error("The Stash is full.");
        }

        // A11: the addon is only told after the write is durable, so the snapshot it
        // reads back can never be older than the move it just asked for.
        //
        // It has to be AsyncCommitTransaction().m_future.get(), not
        // DirectCommitTransaction. The core prepares the statements this
        // transaction carries - CHAR_DEL_CHAR_INVENTORY_BY_ITEM from
        // Item::DeleteFromInventoryDB, CHAR_REP_ITEM_INSTANCE from Item::SaveToDB,
        // and the inventory/money statements from SaveInventoryAndGoldToDB - as
        // CONNECTION_ASYNC only. Direct commit runs them on the synchronous
        // connection, which never prepared them, and MySQLConnection::Execute
        // asserts on a null m_mStmt and takes the worldserver down. The future
        // gives us the same durability on the connection that owns them.
        //
        // It answers rather than throws. A throw from here left the move half
        // applied: the rollback put the stash row back while the item was already
        // live in the bags, and the next inventory save wrote it to a second place.
        // Every caller now undoes its own half and then calls
        // Fail.
        bool Commit(Key const& key, Container& container, CharacterDatabaseTransaction& transaction)
        {
            ++container.revision;
            transaction->Append("UPDATE dc_account_stash SET revision={} WHERE "
                                "account_id={} AND mode='{}'",
                                container.revision, key.account, key.Mode());
            return CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get();
        }

        // Called when a move changed nothing in the player's memory (Rearrange).
        // The cached container goes anyway, so the next open reads the committed
        // truth rather than our idea of it. The Container reference the caller
        // holds is dead after this, which is why it never returns.
        [[noreturn]] void Fail(Key const& key)
        {
            LOG_ERROR("server", "[DC stash] commit failed for account {} mode {}; the move was not saved.", key.account,
                      key.Mode());
            Purge(key);
            throw std::runtime_error("The Stash could not save that move. Nothing was moved.");
        }

        constexpr char const* ReloadMessage =
            "The Stash could not save that move. You are being disconnected to reload your bags; nothing was lost.";

        // A move that has already changed the player's bags is not undone by hand.
        // It follows dc_inventory.cpp's MutationGuard: when it does not reach a
        // durable commit, the player's session is aborted and kicked, the logout
        // skips the save (WorldSession.cpp:691), and the next login reads what the
        // database holds. The database is the only copy of the truth, because every
        // move is ONE transaction.
        //
        // The stash cache goes too, and `held` is an item the move took out of the
        // bags and had not yet linked into the container: nothing else owns it.
        // Anything the container or the bags already own is freed by their owners
        // (a stackable that merged on withdraw was freed by the inventory save, so
        // this never touches it).
        struct BagMove
        {
            Player* player;
            Key key;
            bool saved = false;
            Item* held = nullptr;

            BagMove(Player* actor, Key const& principal)
                : player(actor)
                , key(principal)
            {
            }
            BagMove(BagMove const&) = delete;
            BagMove& operator=(BagMove const&) = delete;
            ~BagMove()
            {
                if (saved)
                    return;
                LOG_ERROR("server", "[DC stash] move for account {} mode {} did not commit; session aborted, bags reload.",
                          key.account, key.Mode());
                if (held)
                    delete held;
                Purge(key);
                PlayerEconomy::Fail();
                player->GetSession()->AbortEconomy();
            }
        };

        // A WORN item's index: bag 255 and an equipment slot, 25500 + 0..18 and
        // nothing else. DecodeBag keeps refusing bag 255 below the backpack, so
        // the bag-slot buttons (19-22), the bank, the keyring, the buyback and the
        // currency slots stay refused; only this whitelist reaches DepositWorn.
        bool IsWornIndex(std::int32_t index)
        {
            return index >= std::int32_t(INVENTORY_SLOT_BAG_0) * 100 &&
                   index < std::int32_t(INVENTORY_SLOT_BAG_0) * 100 + std::int32_t(EQUIPMENT_SLOT_END);
        }

        void Deposit(Player* player, Key const& key, Container& container, std::int32_t fromIndex, std::int32_t toIndex);

        // Unequip and deposit as ONE operation, or refuse whole.
        // Every check - the item's legality, a free stash
        // slot, a bag cell to take it through - happens BEFORE anything moves, because
        // an equipment slot cannot be restored the way a bag cell is (a bag move
        // cannot re-equip). The item is then taken off with SwapItem, as Unequip does,
        // not RemoveItem: SwapItem is what fires OnPlayerUnequip, which dc_items.cpp
        // (gear and weapon-gem bonuses) and dc_stats.cpp listen to, so the character's
        // stats drop exactly as on any unequip. The deposit from that cell is the
        // ordinary Deposit; if it still fails after all the checks (a commit failure),
        // the item is put back on with SwapItem so it stays worn, and the refusal is
        // said. A worn item never swaps with a stash item: the target slot must be
        // empty.
        void DepositWorn(Player* player, Key const& key, Container& container, std::int32_t fromIndex,
                         std::int32_t toIndex)
        {
            std::uint8_t const worn = std::uint8_t(fromIndex - std::int32_t(INVENTORY_SLOT_BAG_0) * 100);
            Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, worn);
            Need(item != nullptr, "Nothing is worn in that slot.");
            CheckDepositable(item, key, true);
            std::uint16_t const position =
                toIndex == AutoPlace ? FirstFreeStashSlot(container) : StashSlot(container, toIndex);
            Need(!container.items.count(position), "Put a worn item in an empty Stash slot.");
            ItemPosCountVec cell;
            Need(player->CanStoreItem(NULL_BAG, NULL_SLOT, cell, item, false) == EQUIP_ERR_OK && cell.size() == 1,
                 "Your bags are full. Make room, then stash it.");
            std::uint16_t const from = std::uint16_t(INVENTORY_SLOT_BAG_0 << 8) | worn;
            std::uint16_t const to = cell[0].pos;
            player->SwapItem(from, to);
            Need(player->GetItemByPos(std::uint8_t(to >> 8), std::uint8_t(to & 255)) == item,
                 "That item could not be taken off. Nothing was moved.");
            try
            {
                Deposit(player, key, container, std::int32_t(to >> 8) * 100 + std::int32_t(to & 255), position);
            }
            catch (...)
            {
                // A move that failed after it changed the bags has aborted the session
                // and freed the item (BagMove); there is nothing to put back, and the
                // next login reads the database.
                if (!player->GetSession()->EconomyAborted())
                    player->SwapItem(to, from);
                throw;
            }
        }

        void Deposit(Player* player, Key const& key, Container& container, std::int32_t fromIndex, std::int32_t toIndex)
        {
            if (IsWornIndex(fromIndex))
            {
                DepositWorn(player, key, container, fromIndex, toIndex);
                return;
            }
            std::uint8_t bag = 0, slot = 0;
            DecodeBag(fromIndex, bag, slot);
            Item* source = player->GetItemByPos(bag, slot);
            CheckDepositable(source, key);

            std::uint16_t const position =
                toIndex == AutoPlace ? FirstFreeStashSlot(container) : StashSlot(container, toIndex);
            auto occupant = container.items.find(position);
            Item* swapped = occupant == container.items.end() ? nullptr : occupant->second;

            ItemPosCountVec destination;
            if (swapped)
            {
                // The source slot is about to be emptied, so the swap target is checked
                // against that exact slot with the stock swap flag.
                InventoryResult const result = player->CanStoreItem(bag, slot, destination, swapped, true);
                Need(result == EQUIP_ERR_OK && destination.size() == 1,
                     "That stash item does not fit in that bag slot.");
            }

            // Everything above refuses cleanly; from here a failure aborts the session.
            CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
            BagMove move(player, key);
            TakeFromBags(player, bag, slot, source);
            move.held = source;
            if (swapped)
            {
                // Measured again against the cell as it is now. With the loot hook
                // deferred nothing has run since it was freed, so this only confirms
                // the first answer - and it is here because a merge is silent.
                destination.clear();
                Need(player->CanStoreItem(bag, slot, destination, swapped, false) == EQUIP_ERR_OK &&
                         CellsAreFree(player, destination) && StoreOne(player, destination, swapped),
                     ReloadMessage);
                container.items.erase(position);
            }
            source->DeleteFromInventoryDB(transaction);
            Park(transaction, source);
            ClearSlot(transaction, key, position);
            FillSlot(transaction, key, position, source);
            container.items[position] = source;
            move.held = nullptr;
            player->SaveInventoryAndGoldToDB(transaction);
            Need(Commit(key, container, transaction), ReloadMessage);
            move.saved = true;
            AnnounceTaken(player, source, bag, slot);
        }

        void Withdraw(Player* player, Key const& key, Container& container, std::int32_t fromIndex,
                      std::int32_t toIndex)
        {
            std::uint16_t const position = StashSlot(container, fromIndex);
            auto found = container.items.find(position);
            Need(found != container.items.end(), "That stash slot is empty.");
            Item* source = found->second;

            ItemPosCountVec destination;
            Item* swapped = nullptr;
            std::uint8_t bag = 0, slot = 0;
            if (toIndex == AutoPlace)
            {
                Need(player->CanStoreItem(NULL_BAG, NULL_SLOT, destination, source, false) == EQUIP_ERR_OK,
                     "Your bags are full.");
                // The quick-move is the only path that says "anywhere", and the core
                // answers it by filling partial stacks first. More than one cell means
                // it would clone, which loses the rolled rows; one stack at a time.
                Need(destination.size() == 1, "Make room for that stack in one bag slot.");
            }
            else
            {
                DecodeBag(toIndex, bag, slot);
                swapped = player->GetItemByPos(bag, slot);
                if (swapped)
                    CheckDepositable(swapped, key);
                Need(player->CanStoreItem(bag, slot, destination, source, swapped != nullptr) == EQUIP_ERR_OK &&
                         destination.size() == 1,
                     "That item does not fit in that bag slot.");
            }

            // Everything above refuses cleanly; from here a failure aborts the session.
            CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
            BagMove move(player, key);
            if (swapped)
            {
                TakeFromBags(player, bag, slot, swapped);
                move.held = swapped;
                // Same re-measure as the deposit, for the same reason.
                destination.clear();
                Need(player->CanStoreItem(bag, slot, destination, source, false) == EQUIP_ERR_OK &&
                         CellsAreFree(player, destination),
                     ReloadMessage);
            }
            Need(StoreOne(player, destination, source), ReloadMessage);
            container.items.erase(position);
            ClearSlot(transaction, key, position);
            if (swapped)
            {
                swapped->DeleteFromInventoryDB(transaction);
                Park(transaction, swapped);
                FillSlot(transaction, key, position, swapped);
                container.items[position] = swapped;
                move.held = nullptr;
            }
            player->SaveInventoryAndGoldToDB(transaction);
            Need(Commit(key, container, transaction), ReloadMessage);
            move.saved = true;
            if (swapped)
                AnnounceTaken(player, swapped, bag, slot);
        }

        void Rearrange(Key const& key, Container& container, std::int32_t fromIndex, std::int32_t toIndex)
        {
            std::uint16_t const from = StashSlot(container, fromIndex);
            auto found = container.items.find(from);
            Need(found != container.items.end(), "That stash slot is empty.");
            Item* source = found->second;
            std::uint16_t const to =
                toIndex == AutoPlace ? FirstFreeStashSlot(container) : StashSlot(container, toIndex);
            Need(to != from, "That item is already there.");
            auto occupant = container.items.find(to);
            Item* swapped = occupant == container.items.end() ? nullptr : occupant->second;

            CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
            // Both rows go before either is written. The source guid is still live at
            // `from` while the INSERT at `to` runs, and the unique key on item_guid
            // refuses it otherwise - a swap collides on both guids.
            ClearSlot(transaction, key, from);
            ClearSlot(transaction, key, to);
            FillSlot(transaction, key, to, source);
            container.items[to] = source;
            if (swapped)
            {
                FillSlot(transaction, key, from, swapped);
                container.items[from] = swapped;
            }
            else
                container.items.erase(from);
            // Nothing left the container, so dropping the cache is the whole undo:
            // the next open reads the rows the rollback kept.
            if (!Commit(key, container, transaction))
                Fail(key);
        }

        // ------------------------------------------------------------- bag to bag

        // Dragging has to work in every direction, the inventory screen included:
        // the bag frame is OUR screen, so a refusal would leave nowhere to rearrange bags.
        //
        // A bag-to-bag move is not a stash operation. Nothing is parked, no
        // dc_account_stash_item row is written and the container cache is not
        // touched, so this takes neither the Key nor the operation lock and never
        // reaches the stash tables. It is the core's own inventory swap.
        void Rebag(Player* player, std::int32_t fromIndex, std::int32_t toIndex)
        {
            std::uint8_t fromBag = 0, fromSlot = 0, toBag = 0, toSlot = 0;
            DecodeBag(fromIndex, fromBag, fromSlot);
            // AutoPlace is the right-click quick-move between the two containers, and
            // it has no meaning with one container on both sides.
            Need(toIndex != AutoPlace, "Choose the bag slot to move it to.");
            DecodeBag(toIndex, toBag, toSlot);
            Need(fromIndex != toIndex, "That item is already there.");
            Item* source = player->GetItemByPos(fromBag, fromSlot);
            Need(source != nullptr, "There is no item in that slot.");
            Need(!source->IsInTrade(), "That item is in a trade.");

            // Player::SwapItem (PlayerStorage.cpp:3612) owns every rule from here: it
            // moves into an empty cell, swaps two occupied ones, merges two stacks of
            // the same entry, refuses a non-empty bag over another bag, and answers a
            // refusal with its own SendEquipError. None of that is reimplemented, and
            // no rolled row moves because no item guid changes.
            player->SwapItem(std::uint16_t(std::uint16_t(fromBag) << 8 | fromSlot),
                             std::uint16_t(std::uint16_t(toBag) << 8 | toSlot));

            // A11: the addon is told only after the write is durable, so the snapshot
            // it reads back can never be older than the move it asked for. Async for
            // the reason Commit gives above - the core prepared these statements on
            // that connection and no other.
            CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
            player->SaveInventoryAndGoldToDB(transaction);
            Need(CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get(),
                 "That bag move could not be saved.");
        }

        void Move(Player* player, std::string const& fromKind, std::int32_t fromIndex, std::string const& toKind,
                  std::int32_t toIndex)
        {
            // An aborted session is on its way out and its bags are not saved
            // (WorldSession.cpp:691); a move now would unlink an item the save skips.
            Need(player && player->GetSession() && !player->GetSession()->EconomyAborted(),
                 "Reconnect to use the Stash.");
            bool const fromStash = fromKind == "stash";
            bool const toStash = toKind == "stash";
            Need(fromStash || fromKind == "bag", "Move from bag or stash.");
            Need(toStash || toKind == "bag", "Move to bag or stash.");
            if (!fromStash && !toStash)
            {
                // No stash row, no container, no lock, and no Stash object: standing at
                // the Stash is not a condition of rearranging your own bags.
                Actor(player, "You cannot move items while dead.", "Move items out of combat.",
                      "This character has no mode yet. Log out and back in, then try again.");
                Rebag(player, fromIndex, toIndex);
                return;
            }
            Key const key = Authorize(player);
            std::lock_guard<std::mutex> operation(*OperationLock(key));
            Container& container = Get(key);
            if (!fromStash)
                Deposit(player, key, container, fromIndex, toIndex);
            else if (!toStash)
                Withdraw(player, key, container, fromIndex, toIndex);
            else
                Rearrange(key, container, fromIndex, toIndex);
        }

        // ------------------------------------------------------------- tab purchase

        // A14. A tunable. An unset price is not a free tab and not a default one:
        // it refuses the purchase and says so.
        void BuyTab(Player* player)
        {
            Key const key = Authorize(player);
            std::lock_guard<std::mutex> operation(*OperationLock(key));
            Container& container = Get(key);
            Need(container.tabs < MaxTabs(),
                 "All " + std::to_string(MaxTabs()) + " stash tabs are already yours.");
            std::uint8_t const next = std::uint8_t(container.tabs + 1);
            auto row = WorldDatabase.Query(
                "SELECT price_gold FROM dc_stash_tuning WHERE next_tab={} AND price_gold IS NOT NULL", next);
            Need(row.get() != nullptr, "The price of that stash tab is not set yet.");
            std::uint64_t const gold = (*row)[0].Get<uint64>();
            std::uint64_t const cost = Economy::GoldCost(gold);

            PlayerEconomy::Scope accountOperation(player);
            try
            {
                Need(Economy::CanAfford(player, cost) && Economy::Charge(player, cost), "Not enough account gold.");
                CharacterDatabaseTransaction transaction = PlayerEconomy::BeginTransaction();
                transaction->Append(
                    "UPDATE dc_account_stash SET tabs_granted={},revision=revision+1 WHERE account_id={} AND "
                    "mode='{}'",
                    next, key.account, key.Mode());
                transaction->Append("INSERT IGNORE INTO dc_account_stash_tab(account_id,mode,tab_id,name,icon,text) "
                                    "VALUES({},'{}',{},'','','')",
                                    key.account, key.Mode(), next - 1);
                player->SaveInventoryAndGoldToDB(transaction);
                Need(AccountEconomy::Commit(player, transaction),
                     "The purchase could not be committed; nothing was charged.");
                container.tabs = next;
                ++container.revision;
                ChatHandler(player->GetSession()).PSendSysMessage("Stash tab {} bought for {}g.", next, gold);
                LOG_INFO("server", "[DC stash] account {} mode {} bought tab {} for {} copper", key.account, key.Mode(),
                         next, cost);
            }
            catch (std::exception const&)
            {
                if (auto* current = PlayerEconomy::Current();
                    current && (current->Dirty() || current->transaction->GetSize()))
                    PlayerEconomy::Fail();
                throw;
            }
        }

        // ------------------------------------------------------- account deletion

        // A5: deleting the ACCOUNT deletes its stash
        // and the items parked in it, in both modes; deleting a character never does.
        // The hook is the core's own, AccountMgr::DeleteAccount (AccountMgr.cpp:117),
        // so nothing in the core changes. It runs before the core removes the
        // account's characters and kicks the sessions, so the cached containers go
        // first and the rows follow in ONE transaction.
        //
        // Only item_instance rows with no owner are deleted: a parked item is one
        // whose owner and container were cleared (Park), and a link that points at a
        // row a character owns is a fault to leave alone, never a row to delete.
        // The rolled rows go only with a row that is deleted (the same owner_guid=0 join),
        // so a linked item a character owns keeps them. They are the same tables
        // Items::Erase clears (dc_items_store.cpp).
        void AccountSweep(std::uint32_t account)
        {
            for (bool hardcore : {false, true})
                Release(Key{account, hardcore});
            CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
            for (char const* table : {"dc_item_affix", "dc_item_instance", "dc_enchant_offer", "dc_item_unidentified",
                                      "dc_legendary_gem_rank"})
                transaction->Append("DELETE d FROM {} d JOIN dc_account_stash_item s ON s.item_guid=d.item_guid "
                                    "JOIN item_instance i ON i.guid=s.item_guid "
                                    "WHERE s.account_id={} AND i.owner_guid=0",
                                    table, account);
            transaction->Append("DELETE i FROM item_instance i JOIN dc_account_stash_item s ON s.item_guid=i.guid "
                                "WHERE s.account_id={} AND i.owner_guid=0",
                                account);
            for (char const* table : {"dc_account_stash_item", "dc_account_stash_tab", "dc_account_stash"})
                transaction->Append("DELETE FROM {} WHERE account_id={}", table, account);
            if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
                LOG_ERROR("server", "[DC stash] account {} deleted but its stash rows could not be removed.", account);
        }

        class StashAccount final : public AccountScript
        {
        public:
            StashAccount()
                : AccountScript("dc_stash_account", {ACCOUNTHOOK_ON_BEFORE_ACCOUNT_DELETE})
            {
            }

            void OnBeforeAccountDelete(std::uint32_t accountId) override
            {
                AccountSweep(accountId);
            }
        };

        // -------------------------------------------------------------- diagnostics

        void Show(ChatHandler* handler, Player* player)
        {
            Key const key = Authorize(player);
            std::lock_guard<std::mutex> operation(*OperationLock(key));
            Container& container = Get(key);
            handler->PSendSysMessage("Stash account={} mode={} tabs={}/{} used={}/{} revision={}", key.account,
                                     key.Mode(), container.tabs, MaxTabs(), container.items.size(),
                                     container.tabs * SlotsPerTab, container.revision);
        }

        class Commands final : public CommandScript
        {
        public:
            Commands()
                : CommandScript("dc_stash_commands")
            {
            }

            ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // Show and tabs are staff commands; move and buytab are what the addon's AIO
                // bridge runs through Player:RunCommand, the same way the artisans do.
                static ChatCommandTable stash = {{"", HandleShow, SEC_GAMEMASTER, Console::No},
                                                 {"tabs", HandleTabs, SEC_ADMINISTRATOR, Console::No},
                                                 {"move", HandleMove, SEC_PLAYER, Console::No},
                                                 {"buytab", HandleBuyTab, SEC_PLAYER, Console::No}};
                static ChatCommandTable dc = {{"stash", stash}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            static bool HandleShow(ChatHandler* handler)
            {
                try
                {
                    Show(handler, handler->GetSession()->GetPlayer());
                    return true;
                }
                catch (std::exception const& error)
                {
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }

            // Test only: grants tabs without a payment so a tester can see tabs 2-5 before a
            // price exists. Never reachable by a player.
            static bool HandleTabs(ChatHandler* handler, uint32 tabs)
            {
                auto* player = handler->GetSession()->GetPlayer();
                try
                {
                    Need(tabs >= LaunchTabs() && tabs <= MaxTabs(),
                         "Choose " + std::to_string(LaunchTabs()) + " to "
                             + std::to_string(MaxTabs()) + " tabs.");
                    Key const key = Authorize(player);
                    std::lock_guard<std::mutex> operation(*OperationLock(key));
                    Container& container = Get(key);
                    CharacterDatabase.DirectExecute(
                        "UPDATE dc_account_stash SET tabs_granted={},revision=revision+1 WHERE "
                        "account_id={} AND mode='{}'",
                        tabs, key.account, key.Mode());
                    for (std::uint8_t tab = 0; tab < tabs; ++tab)
                        CharacterDatabase.DirectExecute(
                            "INSERT IGNORE INTO dc_account_stash_tab(account_id,mode,tab_id,name,"
                            "icon,text) VALUES({},'{}',{},'','','')",
                            key.account, key.Mode(), tab);
                    container.tabs = std::uint8_t(tabs);
                    ++container.revision;
                    handler->PSendSysMessage("Stash tabs set to {} for account {} ({}).", tabs, key.account,
                                             key.Mode());
                    return true;
                }
                catch (std::exception const& error)
                {
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }

            static bool HandleMove(ChatHandler* handler, std::string fromKind, int32 fromIndex, std::string toKind,
                                   int32 toIndex)
            {
                auto* player = handler->GetSession()->GetPlayer();
                try
                {
                    Move(player, fromKind, fromIndex, toKind, toIndex);
                    return true;
                }
                catch (std::exception const& error)
                {
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }

            static bool HandleBuyTab(ChatHandler* handler)
            {
                try
                {
                    BuyTab(handler->GetSession()->GetPlayer());
                    return true;
                }
                catch (std::exception const& error)
                {
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }
        };

        // A5. The container outlives every character on the account. This drops the
        // cached copy when nobody is left to look at it; it deletes no rows. Only
        // StashAccount above ever deletes them, and only for a deleted account.
        class StashPlayer final : public PlayerScript
        {
        public:
            StashPlayer()
                : PlayerScript("dc_stash_player", {PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerLogout(Player* player) override
            {
                ReleaseFor(player);
            }
        };
    } // namespace

    void ReleaseFor(Player const* player)
    {
        if (!player || !player->GetSession())
            return;
        Hardcore::Mode const mode = Hardcore::ModeOf(player);
        if (mode == Hardcore::Mode::Unchosen)
            return;
        Release(Key{player->GetSession()->GetAccountId(), mode == Hardcore::Mode::Hardcore});
    }

    // The deposit's own steps (Park, ClearSlot, FillSlot, Commit) on an item nobody held before: it is created parked, so no
    // bag cell is touched and nothing needs undoing but the item itself. Under the operation lock and through the cached
    // container, so an open window or a later move sees the slot taken; a failed commit drops the cache, as Fail does.
    bool DeliverNew(Player* player, std::uint32_t entry, std::function<std::string(std::uint32_t itemGuid)> const& also)
    {
        if (!player || !player->GetSession() || !sObjectMgr->GetItemTemplate(entry)) // CreateItem aborts on an unknown entry
            return false;
        Hardcore::Mode const mode = Hardcore::ModeOf(player);
        if (mode == Hardcore::Mode::Unchosen || Hardcore::IsLocked(player->GetGUID().GetCounter()) ||
            Hardcore::DeathPending(player))
            return false;
        Key const key{player->GetSession()->GetAccountId(), mode == Hardcore::Mode::Hardcore};
        std::lock_guard<std::mutex> operation(*OperationLock(key));
        Container& container = Get(key);
        std::uint16_t position = 0;
        try
        {
            position = FirstFreeStashSlot(container);
        }
        catch (std::runtime_error const&)
        {
            return false;
        }
        Item* item = Item::CreateItem(entry, 1, player);
        if (!item)
            return false;
        CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
        Park(transaction, item);
        ClearSlot(transaction, key, position);
        FillSlot(transaction, key, position, item);
        if (std::string const statement = also ? also(item->GetGUID().GetCounter()) : ""; !statement.empty())
            transaction->Append(statement.c_str());
        if (!Commit(key, container, transaction))
        {
            LOG_ERROR("server", "[DC stash] delivery of item {} to account {} mode {} did not commit; nothing was stored.",
                      entry, key.account, key.Mode());
            delete item;
            Purge(key);
            return false;
        }
        item->AddToWorld();
        container.items[position] = item;
        LOG_INFO("server", "[DC stash] delivered item {} (guid {}) to {}'s stash, account {} mode {} tab {} slot {}", entry,
                 item->GetGUID().GetCounter(), player->GetName(), key.account, key.Mode(), position / SlotsPerTab,
                 position % SlotsPerTab);
        return true;
    }

    void RegisterScripts()
    {
        new Commands();
        new StashPlayer();
        new StashAccount();
    }
} // namespace DC::Stash

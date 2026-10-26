// The set caches' open (docs/proposals/kadala.md 6.6).
//
// One cache item per set (generate_set_caches.py, dc_set_cache). Buying one is the stock purchase of a free item with
// nothing to roll, so no hook is involved. A right-click sends CMSG_OPEN_ITEM; the core checks the player is alive and
// the item has the has-loot flag, then asks OnPlayerBeforeOpenItem. For a cache the hook answers every open, refusals
// included, and returns false: the stock path would open an empty loot window (a cache has no item_loot_template rows)
// and destroy the cache when it closed (LootHandler.cpp:455). Every other item is left to the stock path.
//
// The open runs like IdentifyOne, for every piece at once, in its own account operation (patch 0007 does not wrap
// CMSG_OPEN_ITEM): the cache destroyed first, which frees its slot; every piece staged through StageRoll in the same
// transaction, each rolled as a named purchase for the opener (the slot vendors' rule, dc_slot_vendor_rule.h); one
// commit; then every piece published. A refusal changes nothing and gives the client its loot release, which unlocks
// the cache (the core's own comment, SpellHandler.cpp:227). Per kadala.md 6.7.3 the pieces sell and salvage
// like any drop, and the cache itself has no sell price.
#include "dc_items.h"
#include "dc_set_cache_rule.h"
#include "dc_slot_vendor_rule.h"

#include "Bag.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "WorldSession.h"
#include "../common/dc_account_economy.h"

#include <algorithm>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace DC::Items
{
    // The free slots every piece can go into: the backpack, and each bag the core lets every piece
    // into (ItemCanGoIntoBag, CanStoreNewItem's own rule). GetFreeInventorySpace also counts a special-purpose bag
    // (herb, enchanting, soul...), which takes no armour: a player whose only room was there passed the count, the
    // store then failed after the cache was destroyed, and the rollback kicked them instead of saying so.
    unsigned FreeSlotsFor(Player* player, std::vector<ItemTemplate const*> const& pieces)
    {
        unsigned free = 0;
        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            if (!player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                ++free;
        for (uint8 slot = INVENTORY_SLOT_BAG_START; slot < INVENTORY_SLOT_BAG_END; ++slot)
            if (Bag* bag = player->GetBagByPos(slot))
                if (std::all_of(pieces.begin(), pieces.end(),
                                [&](ItemTemplate const* piece) { return ItemCanGoIntoBag(piece, bag->GetTemplate()); }))
                    free += bag->GetFreeSlots();
        return free;
    }

    namespace
    {
        // What the roll class of a piece depends on, read from dc_base_item and dc_set_class like the drops do.
        struct Piece
        {
            std::uint32_t entry;
            std::string designated, setClass;
        };
        struct Cache
        {
            std::string setName;
            std::vector<Piece> pieces;
        };
        std::mutex cachesMutex;
        std::map<std::uint32_t, Cache> caches; // cache item entry -> its set's pieces

        bool Find(std::uint32_t entry, Cache& out)
        {
            std::lock_guard<std::mutex> lock(cachesMutex);
            auto found = caches.find(entry);
            if (found == caches.end())
                return false;
            out = found->second;
            return true;
        }

        // Keeps the account operation honest once something has been destroyed or staged: unless the commit went
        // through, the operation fails and the session reloads its last committed state, as IdentifyOne does.
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

        void Open(Player* player, Item* item, Cache const& cache)
        {
            // The client locked the cache when it sent the open; only a loot response for its guid unlocks it, so every
            // refusal ends with one. The guid is kept because the item is gone once it is destroyed.
            ObjectGuid const guid = item->GetGUID();
            ChatHandler handler(player->GetSession());
            auto refuse = [&](std::string const& line)
            {
                handler.SendSysMessage(line.c_str());
                player->SendLootRelease(guid);
            };

            std::string const buyerClass = ClassKeyOf(player->getClass());
            std::vector<std::string> rollClasses;
            bool known = true;
            for (Piece const& piece : cache.pieces)
            {
                rollClasses.push_back(SlotVendor::RollClassFor(piece.designated, piece.setClass, buyerClass));
                known = known && !rollClasses.back().empty();
            }

            SetCache::Facts facts;
            facts.alive = player->IsAlive();
            facts.inCombat = player->IsInCombat();
            facts.inTrade = item->IsInTrade();
            facts.rollClassesKnown = known;
            facts.pieces = static_cast<unsigned>(cache.pieces.size());
            std::vector<ItemTemplate const*> templates;
            for (Piece const& piece : cache.pieces)
                templates.push_back(sObjectMgr->GetItemTemplate(piece.entry));
            facts.freeSlots = FreeSlotsFor(player, templates);
            SetCache::Verdict const verdict = SetCache::Judge(facts);
            if (verdict != SetCache::Verdict::Open)
            {
                refuse(SetCache::Refusal(verdict, cache.setName, facts.pieces, facts.freeSlots));
                return;
            }

            PlayerEconomy::Scope operation(player);
            auto transaction = PlayerEconomy::BeginTransaction();
            Staged guard{player};
            // The cache's slot is freed first, inside this transaction, so the last piece has somewhere to go.
            std::uint32_t const cacheEntry = item->GetEntry();
            DestroyWithRows(player, item, transaction);
            item = nullptr;

            // The item level is the opener's (the slot vendors' rule); each base is the piece itself, identified.
            std::vector<std::unique_ptr<StagedRoll>> staged;
            for (std::size_t i = 0; i < cache.pieces.size(); ++i)
            {
                auto roll =
                    StageRoll(player, cache.pieces[i].entry, player->GetLevel(), "", transaction, rollClasses[i]);
                if (!roll || !roll->GetItem())
                {
                    // The guard discards every unsaved bag change, the cache included.
                    refuse(cache.setName + " could not be opened. Nothing was changed.");
                    return;
                }
                staged.push_back(std::move(roll));
            }
            player->SaveInventoryAndGoldToDB(transaction);
            if (!DC::AccountEconomy::Commit(player, transaction))
            {
                refuse(cache.setName + " could not be opened. Nothing was changed.");
                return;
            }
            guard.committed = true;

            for (auto& roll : staged)
                if (Item* published = roll->Publish())
                    player->SendNewItem(published, 1, true, false, false);
            std::string classes; // the roll class of each piece, in the set's order
            for (std::string const& rollClass : rollClasses)
                classes += (classes.empty() ? "" : ",") + rollClass;
            LOG_INFO("server", "[DC set cache] {} opened cache {} ({}): {} pieces at level {}, rolled for {}",
                     player->GetName(), cacheEntry, cache.setName, cache.pieces.size(), player->GetLevel(), classes);
        }

        class SetCacheWorld final : public WorldScript
        {
        public:
            SetCacheWorld()
                : WorldScript("dc_set_cache_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                QueryResult result = WorldDatabase.Query(
                    "SELECT c.entry, c.set_name, p.item_entry, b.designated_class, COALESCE(sc.class_key, '') "
                    "FROM dc_set_cache c JOIN dc_set_cache_piece p ON p.cache_entry = c.entry "
                    "JOIN dc_base_item b ON b.entry = p.item_entry LEFT JOIN dc_set_class sc ON sc.set_name = "
                    "b.set_name "
                    "ORDER BY c.entry, p.item_entry");
                if (!result)
                {
                    LOG_ERROR("server", "dc_set_cache is missing or empty (apply set_caches_0001.sql): the set caches "
                                        "cannot open");
                    return;
                }
                std::map<std::uint32_t, Cache> loaded;
                std::size_t pieces = 0;
                do
                {
                    Field* fields = result->Fetch();
                    Cache& cache = loaded[fields[0].Get<std::uint32_t>()];
                    cache.setName = fields[1].Get<std::string>();
                    cache.pieces.push_back(
                        {fields[2].Get<std::uint32_t>(), fields[3].Get<std::string>(), fields[4].Get<std::string>()});
                    ++pieces;
                } while (result->NextRow());
                std::lock_guard<std::mutex> lock(cachesMutex);
                caches = std::move(loaded);
                LOG_INFO("server.loading", "[DC set cache] {} caches, {} pieces", caches.size(), pieces);
            }
        };

        class SetCachePlayer final : public PlayerScript
        {
        public:
            SetCachePlayer()
                : PlayerScript("dc_set_cache_player", {PLAYERHOOK_ON_BEFORE_OPEN_ITEM})
            {
            }
            bool OnPlayerBeforeOpenItem(Player* player, Item* item) override
            {
                Cache cache;
                if (!player || !item || !Find(item->GetEntry(), cache))
                    return true; // not a cache: the stock open
                Open(player, item, cache);
                return false; // a cache is never left to the stock path
            }
        };
    } // namespace

    void RegisterSetCacheScripts()
    {
        new SetCacheWorld();
        new SetCachePlayer();
    }
} // namespace DC::Items

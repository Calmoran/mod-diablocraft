/*
 * World of DiabloCraft - the Horadric Cache (docs/research/bounties.md 5.5).
 *
 * When a column completes, every online member of the board's owner is owed that column's cache at their tier of the
 * moment (OweCache, from dc_bounties.cpp). The debt is paid on the member's own update, which is their own map's thread
 * (another member's bags are not this thread's to touch; the rift quests' DrainQuestWork does the same), or at their
 * logout if that comes first. Paying is the one new delivery: the bags, else the account stash
 * (DC::Stash::DeliverNew), else lost with a chat line. The cache's column and tier go in dc_bounties_cache_item in the
 * same transaction that stores it.
 *
 * Opening is the set cache's shape (dc_set_cache.cpp): OnPlayerBeforeOpenItem answers every open of a cache and returns
 * false; a refusal changes nothing and gives the client its loot release. An open destroys the cache and its row,
 * stages the rare and legendary rolls, stores the gems, credits the gold, Blood Shards, the act reagent and Death's
 * Breath to the account ledger under receipts named for the cache's guid, and commits it all as one account operation.
 * The amounts are dc_bounty_cache_rule.h's, from the rifts tunables bounty_cache_*.
 *
 * `.dc bounty cache <column>` (GM) delivers one at the GM's tier, through the same path.
 */

#include "dc_bounties.h"
#include "dc_bounty_cache_rule.h"

#include "../common/dc_account_economy.h"
#include "../common/dc_blood_shards.h"
#include "../common/dc_economy.h"
#include "../common/dc_tunables.h"
#include "../difficulty/dc_difficulty.h"
#include "../items/dc_items.h"
#include "../items/dc_stash.h"
#include "../loot/dc_loot.h"

#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "WorldSession.h"

#include <atomic>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Bounties
{
    namespace
    {
        constexpr char const* TUNABLES = "rifts";

        struct CacheRow
        {
            unsigned column = 0;
            std::uint32_t entry = 0, reagent = 0;
            std::string name, reagentName;
            std::vector<std::uint32_t> pool; // the column's act legendaries; empty rolls none
        };

        std::mutex cacheMutex;                                     // the two maps below, written once at startup
        std::map<std::uint32_t, CacheRow> caches;                  // cache item entry -> its row
        std::map<unsigned, std::vector<std::uint32_t>> gemsByRank; // dc_gem_item.rank -> the gem entries of that grade

        bool ByEntry(std::uint32_t entry, CacheRow& out)
        {
            std::lock_guard<std::mutex> lock(cacheMutex);
            auto found = caches.find(entry);
            if (found == caches.end())
                return false;
            out = found->second;
            return true;
        }
        bool ByColumn(unsigned column, CacheRow& out)
        {
            std::lock_guard<std::mutex> lock(cacheMutex);
            for (auto const& [entry, row] : caches)
                if (row.column == column)
                {
                    out = row;
                    return true;
                }
            return false;
        }

        // What each online member is owed, kept until their own update pays it.
        // ponytail: memory only; a crash between the completion and the member's next update (one tick) loses the debt.
        // A dc_ table of debts, paid at login, if that window ever matters.
        struct Owed
        {
            unsigned column = 0, tier = 0;
        };
        std::mutex owedMutex;
        std::unordered_map<ObjectGuid, std::vector<Owed>> owed;
        std::atomic<unsigned> owedCount{0}; // the update's cheap "anything owed at all?"

        std::vector<Owed> TakeOwed(Player* player)
        {
            if (!owedCount.load())
                return {};
            std::lock_guard<std::mutex> lock(owedMutex);
            auto found = owed.find(player->GetGUID());
            if (found == owed.end())
                return {};
            std::vector<Owed> out = std::move(found->second);
            owed.erase(found);
            owedCount -= static_cast<unsigned>(out.size());
            return out;
        }

        // Unless the commit went through, the account operation fails and the session reloads its last committed state:
        // dc_set_cache.cpp's guard.
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

        // The one new delivery: bags, else the stash, else lost with a line. True when the cache was stored somewhere.
        // `bags` false (at logout): the stash only, no line, and false leaves the cache to the caller. The logout's save
        // flag is fixed before its hook runs (WorldSession::LogoutPlayer), so a bag commit that failed there would still
        // save the cache into the bags without its dc_bounties_cache_item row; a failed stash commit stores nothing.
        bool Deliver(Player* player, CacheRow const& cache, unsigned tier, bool bags = true)
        {
            // The cache's column and tier, in the transaction that stores it.
            auto record = [&](std::uint32_t itemGuid)
            {
                return Acore::StringFormat("INSERT INTO dc_bounties_cache_item (item_guid,col,tier) VALUES ({},{},{})",
                                           itemGuid, cache.column, tier);
            };
            ChatHandler chat(player->GetSession());
            ItemPosCountVec cell;
            if (bags && player->CanStoreNewItem(NULL_BAG, NULL_SLOT, cell, cache.entry, 1) == EQUIP_ERR_OK)
            {
                PlayerEconomy::Scope operation(player);
                auto transaction = PlayerEconomy::BeginTransaction();
                Staged guard{player};
                Item* item = player->StoreNewItem(cell, cache.entry, true);
                if (!item)
                    return false;
                transaction->Append(record(item->GetGUID().GetCounter()).c_str());
                player->SaveInventoryAndGoldToDB(transaction);
                if (!DC::AccountEconomy::Commit(player, transaction))
                    return false;
                guard.committed = true;
                player->SendNewItem(item, 1, true, false, false);
                LOG_INFO("server", "[DC bounty cache] {} received {} (column {}, tier {}) in their bags",
                         player->GetName(), cache.name, cache.column, tier);
                return true;
            }
            if (DC::Stash::DeliverNew(player, cache.entry, record))
            {
                if (bags)
                    chat.SendSysMessage(Cache::StashLine(cache.name));
                LOG_INFO("server", "[DC bounty cache] {} received {} (column {}, tier {}) in their stash",
                         player->GetName(), cache.name, cache.column, tier);
                return true;
            }
            if (!bags)
                return false;
            chat.SendSysMessage(Cache::LostLine(cache.name));
            LOG_INFO("server", "[DC bounty cache] {} lost {} (column {}, tier {}): bags and stash full",
                     player->GetName(), cache.name, cache.column, tier);
            return false;
        }

        // `atLogout`: the stash only (Deliver's `bags`); a cache the stash cannot take stays owed and is paid on the next
        // login's first update (memory only, as every debt is).
        void PayOwed(Player* player, bool atLogout = false)
        {
            for (Owed const& debt : TakeOwed(player))
            {
                CacheRow cache;
                if (!ByColumn(debt.column, cache))
                    LOG_ERROR("server", "[DC bounty cache] column {} has no cache (dc_bounties_cache): {} gets none",
                              debt.column, player->GetName());
                else if (!Deliver(player, cache, debt.tier, !atLogout) && atLogout)
                {
                    std::lock_guard<std::mutex> lock(owedMutex);
                    owed[player->GetGUID()].push_back(debt);
                    ++owedCount;
                }
            }
        }

        double Row(std::string const& name)
        {
            return DC::Tunables::Get(TUNABLES, name);
        }

        Cache::Top ReadTop()
        {
            Cache::Top top;
            top.gold = Row("bounty_cache_gold");
            top.shards = Row("bounty_cache_blood_shards");
            top.reagent = Row("bounty_cache_reagent");
            top.deathsBreath = Row("bounty_cache_deaths_breath");
            top.gemsMin = Row("bounty_cache_gems_min");
            top.gemsMax = Row("bounty_cache_gems_max");
            top.raresMin = Row("bounty_cache_rares_min");
            top.raresMax = Row("bounty_cache_rares_max");
            top.legendaries = Row("bounty_cache_legendaries");
            return top;
        }

        std::uint32_t Roll(std::uint32_t lo, std::uint32_t hi)
        {
            return urand(lo, hi);
        }

        // The ledger part of an open, each under its own receipt (a repeat of one is a no-op). False refuses the open.
        bool CreditLedger(Player* player, CacheRow const& cache, Cache::Amounts const& a, std::string const& receipt,
                          std::uint64_t& shardsLost)
        {
            if (a.gold && !DC::AccountEconomy::CreditGold(player, DC::Economy::GoldCost(a.gold), receipt + ":gold"))
                return false;
            if (a.shards && !DC::AccountEconomy::CreditMaterial(player, DC::BloodShards::Entry, a.shards,
                                                                receipt + ":shards", &shardsLost))
                return false;
            if (a.reagent &&
                !DC::AccountEconomy::CreditMaterial(player, cache.reagent, a.reagent, receipt + ":reagent"))
                return false;
            if (a.deathsBreath && !DC::AccountEconomy::CreditMaterial(player, Cache::DeathsBreathEntry, a.deathsBreath,
                                                                      receipt + ":deathsbreath"))
                return false;
            return true;
        }

        void Open(Player* player, Item* item, CacheRow const& cache)
        {
            // The client locked the cache when it sent the open; only a loot response for its guid unlocks it.
            ObjectGuid const guid = item->GetGUID();
            ChatHandler handler(player->GetSession());
            auto refuse = [&](std::string const& line)
            {
                handler.SendSysMessage(line.c_str());
                player->SendLootRelease(guid);
            };

            unsigned tier = 0;
            if (QueryResult row = CharacterDatabase.Query("SELECT tier FROM dc_bounties_cache_item WHERE item_guid={}",
                                                          guid.GetCounter()))
                tier = (*row)[0].Get<uint8>();
            std::string const scaleRow = Cache::TierRow("bounty_cache_scale_pct", tier);
            std::string const gemRow = Cache::TierRow("bounty_cache_gem_rank", tier);
            bool const rows =
                !scaleRow.empty() && DC::Tunables::Has(TUNABLES, scaleRow) && DC::Tunables::Has(TUNABLES, gemRow);
            Cache::Amounts const amounts = Cache::Scale(ReadTop(), rows ? Row(scaleRow) : 0);
            Cache::Counts const counts = Cache::Roll(amounts, cache.pool.empty(), Roll);

            // The bases, before anything changes: Rare generics for the opener's class and level (Kadala's rule), the
            // legendaries from the act's pool, the gems of the tier's grade in a random colour.
            unsigned const level = player->GetLevel();
            std::string const rollClass = DC::Items::ClassKeyOf(player->getClass());
            std::vector<std::uint32_t> rares, legendaries, gems;
            for (unsigned i = 0; i < counts.rares && !rollClass.empty(); ++i)
                if (std::uint32_t const base = DC::Loot::PickBaseItem(DC::Loot::Rarity::Rare, level, rollClass))
                    rares.push_back(base);
            for (unsigned i = 0; i < counts.legendaries; ++i)
                legendaries.push_back(cache.pool[urand(0, static_cast<std::uint32_t>(cache.pool.size() - 1))]);
            {
                std::lock_guard<std::mutex> lock(cacheMutex);
                auto grade = gemsByRank.find(rows ? static_cast<unsigned>(Row(gemRow)) : 0);
                for (unsigned i = 0; i < counts.gems && grade != gemsByRank.end() && !grade->second.empty(); ++i)
                    gems.push_back(grade->second[urand(0, static_cast<std::uint32_t>(grade->second.size() - 1))]);
            }
            if (rares.size() < counts.rares || gems.size() < counts.gems)
                LOG_ERROR("server",
                          "[DC bounty cache] {} opening {}: {} of {} rares and {} of {} gems found a base "
                          "(class '{}', level {}, gem grade row {})",
                          player->GetName(), cache.name, rares.size(), counts.rares, gems.size(), counts.gems,
                          rollClass, level, gemRow);

            Cache::Facts facts;
            facts.alive = player->IsAlive();
            facts.inCombat = player->IsInCombat();
            facts.inTrade = item->IsInTrade();
            facts.ledger = DC::AccountEconomy::Enabled();
            facts.earned = tier != 0;
            facts.rows = rows;
            facts.items = static_cast<unsigned>(rares.size() + legendaries.size() + gems.size());
            // Room the items can go into: a special-purpose bag counts only if it takes them all.
            // ponytail: a gem bag is not counted beside rares even though it would take the gems; exact per-family room
            // if a refusal there ever matters (a refusal, never a kick).
            std::vector<ItemTemplate const*> templates;
            for (auto const* list : {&rares, &legendaries, &gems})
                for (std::uint32_t entry : *list)
                    templates.push_back(sObjectMgr->GetItemTemplate(entry));
            facts.freeSlots = DC::Items::FreeSlotsFor(player, templates);
            Cache::Verdict const verdict = Cache::Judge(facts);
            if (verdict != Cache::Verdict::Open)
            {
                if (verdict == Cache::Verdict::NoRecord || verdict == Cache::Verdict::NoRows ||
                    verdict == Cache::Verdict::NoLedger)
                    LOG_ERROR("server", "[DC bounty cache] {} could not open {} (guid {}): tier {}, rows {}, ledger {}",
                              player->GetName(), cache.name, guid.GetCounter(), tier, rows, facts.ledger);
                refuse(Cache::Refusal(verdict, cache.name, facts.items, facts.freeSlots));
                return;
            }

            PlayerEconomy::Scope operation(player);
            auto transaction = PlayerEconomy::BeginTransaction();
            Staged guard{player};
            std::string const failed = cache.name + " could not be opened. Nothing was changed.";
            // The cache's slot is freed first, inside this transaction, so the last item has somewhere to go.
            DC::Items::DestroyWithRows(player, item, transaction);
            item = nullptr;
            transaction->Append("DELETE FROM dc_bounties_cache_item WHERE item_guid={}", guid.GetCounter());

            std::vector<std::unique_ptr<DC::Items::StagedRoll>> staged;
            auto stage = [&](std::uint32_t base, char const* rarity)
            {
                auto roll = DC::Items::StageRoll(player, base, level, rarity, transaction, rollClass);
                if (!roll || !roll->GetItem())
                    return false;
                staged.push_back(std::move(roll));
                return true;
            };
            for (std::uint32_t base : rares)
                if (!stage(base, "rare"))
                    return refuse(failed); // the guard discards every unsaved bag change, the cache included
            for (std::uint32_t base : legendaries)
                if (!stage(base, ""))
                    return refuse(failed);
            std::vector<Item*> stored;
            for (std::uint32_t gem : gems)
            {
                ItemPosCountVec cell;
                Item* stone = player->CanStoreNewItem(NULL_BAG, NULL_SLOT, cell, gem, 1) == EQUIP_ERR_OK
                                  ? player->StoreNewItem(cell, gem, true)
                                  : nullptr;
                if (!stone)
                    return refuse(failed);
                stored.push_back(stone);
            }
            std::uint64_t shardsLost = 0;
            if (!CreditLedger(player, cache, amounts, "bountycache:" + std::to_string(guid.GetCounter()), shardsLost))
                return refuse(failed);
            player->SaveInventoryAndGoldToDB(transaction);
            if (!DC::AccountEconomy::Commit(player, transaction))
                return refuse(failed);
            guard.committed = true;

            for (auto& roll : staged)
                if (Item* published = roll->Publish())
                    player->SendNewItem(published, 1, true, false, false);
            for (Item* stone : stored)
                player->SendNewItem(stone, 1, true, false, false);
            std::string line = cache.name + ": " + std::to_string(amounts.gold) + " gold, " +
                               std::to_string(amounts.shards) + " Blood Shards";
            if (shardsLost)
                line += " (" + std::to_string(shardsLost) + " over your cap were lost)";
            line += ", " + std::to_string(amounts.reagent) + " " + cache.reagentName + ", " +
                    std::to_string(amounts.deathsBreath) + " Death's Breath.";
            handler.SendSysMessage(line);
            LOG_INFO("server",
                     "[DC bounty cache] {} opened {} (guid {}, column {}, tier {}): {} gold, {} shards ({} lost), "
                     "{} reagent, {} Death's Breath, {} rares, {} legendaries, {} gems",
                     player->GetName(), cache.name, guid.GetCounter(), cache.column, tier, amounts.gold, amounts.shards,
                     shardsLost, amounts.reagent, amounts.deathsBreath, rares.size(), legendaries.size(), gems.size());
        }

        class CacheWorld final : public WorldScript
        {
        public:
            CacheWorld()
                : WorldScript("dc_bounty_cache_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                std::map<std::uint32_t, CacheRow> loaded;
                if (QueryResult result = WorldDatabase.Query(
                        "SELECT c.col, c.entry, c.reagent_entry, t.name, COALESCE(r.name, '') FROM dc_bounties_cache c "
                        "JOIN item_template t ON t.entry = c.entry LEFT JOIN item_template r ON r.entry = "
                        "c.reagent_entry"))
                    do
                    {
                        Field* f = result->Fetch();
                        CacheRow& row = loaded[f[1].Get<uint32>()];
                        row.column = f[0].Get<uint8>();
                        row.entry = f[1].Get<uint32>();
                        row.reagent = f[2].Get<uint32>();
                        row.name = f[3].Get<std::string>();
                        row.reagentName = f[4].Get<std::string>();
                    } while (result->NextRow());
                if (loaded.empty())
                {
                    LOG_ERROR("server",
                              "dc_bounties_cache is missing or empty (apply bounties_0003_caches.sql): no column "
                              "delivers a cache");
                    return;
                }
                if (QueryResult result = WorldDatabase.Query("SELECT col, item_entry FROM dc_bounties_cache_legendary "
                                                             "ORDER BY col, item_entry"))
                    do
                    {
                        Field* f = result->Fetch();
                        for (auto& [entry, row] : loaded)
                            if (row.column == f[0].Get<uint8>())
                                row.pool.push_back(f[1].Get<uint32>());
                    } while (result->NextRow());
                std::map<unsigned, std::vector<std::uint32_t>> grades;
                if (QueryResult result = WorldDatabase.Query("SELECT `rank`, entry FROM dc_gem_item ORDER BY entry"))
                    do
                    {
                        Field* f = result->Fetch();
                        grades[f[0].Get<int32>()].push_back(f[1].Get<uint32>());
                    } while (result->NextRow());
                std::lock_guard<std::mutex> lock(cacheMutex);
                caches = std::move(loaded);
                gemsByRank = std::move(grades);
                LOG_INFO("server.loading", "[DC bounty cache] {} caches, {} gem grades", caches.size(),
                         gemsByRank.size());
            }
        };

        class CachePlayer final : public PlayerScript
        {
        public:
            CachePlayer()
                : PlayerScript("dc_bounty_cache_player",
                               {PLAYERHOOK_ON_BEFORE_OPEN_ITEM, PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_BEFORE_LOGOUT})
            {
            }
            bool OnPlayerBeforeOpenItem(Player* player, Item* item) override
            {
                CacheRow cache;
                if (!player || !item || !ByEntry(item->GetEntry(), cache))
                    return true; // not a bounty cache: the other hooks and the stock open
                Open(player, item, cache);
                return false;
            }
            void OnPlayerUpdate(Player* player, uint32 /*diff*/) override
            {
                if (owedCount.load() && !player->IsBeingTeleported())
                    PayOwed(player);
            }
            // A member who logs out before their next update is paid here, into the stash only.
            void OnPlayerBeforeLogout(Player* player) override
            {
                PayOwed(player, true);
            }
        };

        class CacheCommand final : public CommandScript
        {
        public:
            CacheCommand()
                : CommandScript("dc_bounty_cache_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable bounty = {{"cache", HandleCache, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable dc = {{"bounty", bounty}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
            // `.dc bounty cache <column>`: one cache of that column at the GM's tier, delivered as a column's are.
            static bool HandleCache(ChatHandler* handler, uint8 column)
            {
                Player* player = handler->GetSession()->GetPlayer();
                CacheRow cache;
                if (!ByColumn(column, cache))
                {
                    handler->PSendSysMessage("Column {} has no cache (dc_bounties_cache).", column);
                    return true;
                }
                unsigned const tier = DC::Difficulty::CurrentTier(player);
                handler->PSendSysMessage("{} at tier {}: {}", cache.name, tier,
                                         Deliver(player, cache, tier) ? "delivered." : "not delivered.");
                return true;
            }
        };
    } // namespace

    void OweCache(Player* member, unsigned column)
    {
        unsigned const tier = DC::Difficulty::CurrentTier(member);
        std::lock_guard<std::mutex> lock(owedMutex);
        owed[member->GetGUID()].push_back({column, tier});
        ++owedCount;
    }

    void RegisterCacheScripts()
    {
        new CacheWorld();
        new CachePlayer();
        new CacheCommand();
    }
} // namespace DC::Bounties

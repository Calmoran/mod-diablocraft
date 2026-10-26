// Constant (96): Receipt identifier maximum length; Storage bound.
// Constant (32): Receipt printable-ASCII lower bound; Input encoding bound.
// Constant (126): Receipt printable-ASCII upper bound; Input encoding bound.
#include "dc_account_economy.h"
#include "dc_blood_shards.h"
#include "dc_tunables.h"
#include "../hardcore/dc_hardcore.h"
#include "../items/dc_mail_rule.h"
#include "Chat.h"
#include "Config.h"
#include "DBCStores.h"
#include "Log.h"
#include "Opcodes.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "World.h"
#include "WorldSession.h"
#include "WorldPacket.h"
#include <boost/uuid/random_generator.hpp>
#include <boost/uuid/uuid_io.hpp>
#include <algorithm>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <tuple>
#include <vector>

namespace DC::AccountEconomy
{
    namespace
    {
        using Key = std::tuple<uint32, bool, uint32>; // account, hardcore, asset (0=copper)
        struct State
        {
            uint64 amount = 0, revision = 0;
        };
        struct PendingBalance
        {
            State before;
            uint64 amount = 0;
            bool dirty = false;
        };
        struct Kind
        {
            bool material = false;
            uint64 copper = 0;
        };
        std::recursive_mutex mutex;
        std::map<Key, State> cache;
        std::set<std::pair<uint32, bool>> faultAccounts;
        std::set<uint32> quarantinedCharacters;
        std::map<uint32, Kind> kinds;
        bool enabled = false;
        std::map<uint64, uint64> sentRevisions;
        char const* Mode(bool hardcore)
        {
            return hardcore ? "hardcore" : "normal";
        }
        std::string Escape(std::string value)
        {
            CharacterDatabase.EscapeString(value);
            return value;
        }
        std::string NewId()
        {
            return boost::uuids::to_string(boost::uuids::random_generator()());
        }
        uint64 Count(std::string const& sql)
        {
            auto row = CharacterDatabase.Query(sql);
            if (!row)
                throw std::runtime_error("Account migration preflight query failed");
            return (*row)[0].Get<uint64>();
        }
        bool Principal(uint32 guid, uint32& account, bool& hardcore)
        {
            auto row = CharacterDatabase.Query(
                "SELECT c.account,m.mode FROM characters c JOIN dc_character_mode m ON m.guid=c.guid WHERE c.guid={} "
                "UNION ALL SELECT e.account_id,e.mode FROM dc_account_economy_migration e WHERE "
                "e.source_kind='character' AND e.source_guid={} AND NOT EXISTS(SELECT 1 FROM characters WHERE guid={}) "
                "LIMIT 1",
                guid, guid, guid);
            if (!row)
                return false;
            account = (*row)[0].Get<uint32>();
            auto mode = (*row)[1].Get<std::string>();
            if (mode != "normal" && mode != "hardcore")
                return false;
            hardcore = mode == "hardcore";
            return true;
        }
        bool Actor(Player const* player, uint32& account, bool& hardcore)
        {
            if (!player || player->GetSession()->EconomyAborted() ||
                !Principal(player->GetGUID().GetCounter(), account, hardcore) ||
                account != player->GetSession()->GetAccountId())
                return false;
            return !hardcore || (player->IsAlive() && !Hardcore::IsLocked(player->GetGUID().GetCounter()));
        }
        State Load(Key const& key)
        {
            auto found = cache.find(key);
            if (found != cache.end())
                return found->second;
            auto [account, hardcore, entry] = key;
            // The outer SELECT always returns one row, including a genuinely absent
            // ledger. A failed query must never be interpreted as a zero balance.
            auto row = entry
                           ? CharacterDatabase.Query(
                                 "SELECT COALESCE((SELECT amount FROM dc_account_currency WHERE account_id={} AND "
                                 "mode='{}' AND item_entry={}),0),COALESCE((SELECT revision FROM dc_account_currency "
                                 "WHERE account_id={} AND mode='{}' AND item_entry={}),0)",
                                 account, Mode(hardcore), entry, account, Mode(hardcore), entry)
                           : CharacterDatabase.Query("SELECT COALESCE((SELECT balance_copper FROM dc_account_gold "
                                                     "WHERE account_id={} AND mode='{}'),0),COALESCE((SELECT revision "
                                                     "FROM dc_account_gold WHERE account_id={} AND mode='{}'),0)",
                                                     account, Mode(hardcore), account, Mode(hardcore));
            if (!row)
                throw std::runtime_error("Account ledger read failed");
            State state{(*row)[0].Get<uint64>(), (*row)[1].Get<uint64>()};
            cache[key] = state;
            return state;
        }
        // The Blood Shard cap of one account and mode (kadala.md 4.2). The best solo Greater Rift level
        // is the account's, kept in dc_account_gr_solo even after its character is deleted.
        uint64 ShardCap(uint32 account, bool hardcore)
        {
            auto row = CharacterDatabase.Query("SELECT COALESCE((SELECT beaten_solo FROM dc_account_gr_solo WHERE "
                                               "account_id={} AND mode='{}'),0)",
                                               account, Mode(hardcore));
            if (!row)
                throw std::runtime_error("Blood Shard cap read failed");
            auto const tunable = [](char const* name) { return uint64(std::max(0.0, Tunables::Get("loot", name))); };
            return BloodShards::Cap(tunable("blood_shard_cap_base"), tunable("blood_shard_cap_per_gr_level"),
                                    (*row)[0].Get<uint64>());
        }
        class Operation final : public PlayerEconomy::Context
        {
        public:
            std::map<std::string, std::string> receipts;
            Operation()
                : lock_(mutex)
            {
            }
            ~Operation() override
            {
                // A commit exception can have an uncertain transport outcome. Never
                // leave pre-commit cache entries authoritative for the next operation.
                for (auto const& [key, row] : changes_)
                    if (row.dirty)
                        cache.erase(key);
            }
            PendingBalance& Row(Key const& key)
            {
                auto found = changes_.find(key);
                if (found != changes_.end())
                    return found->second;
                State state = Load(key);
                return changes_.emplace(key, PendingBalance{state, state.amount, false}).first->second;
            }
            bool Adjust(Key const& key, uint64 amount, bool debit, bool absolute = false)
            {
                auto& row = Row(key);
                if (row.before.revision == UINT64_MAX ||
                    (!absolute && (debit ? amount > row.amount : amount > UINT64_MAX - row.amount)))
                    return false;
                row.amount = absolute ? amount : debit ? row.amount - amount : row.amount + amount;
                row.dirty = true;
                // One account revision changes for material-only operations too.
                auto& gold = Row({std::get<0>(key), std::get<1>(key), 0});
                if (gold.before.revision == UINT64_MAX)
                    return false;
                gold.dirty = true;
                return true;
            }
            bool Read(Player const* player, uint64& value) override
            {
                uint32 account;
                bool hardcore;
                if (!Actor(player, account, hardcore))
                    return false;
                value = Row({account, hardcore, 0}).amount;
                return true;
            }
            bool Change(Player* player, uint64 amount, bool debit, bool absolute) override
            {
                uint32 account;
                bool hardcore;
                if (!Actor(player, account, hardcore) || !Adjust({account, hardcore, 0}, amount, debit, absolute))
                    return false;
                player->SetMoneyMirror(uint32(std::min<uint64>(Row({account, hardcore, 0}).amount, UINT32_MAX)));
                return true;
            }
            bool CreditOffline(uint32 guid, uint64 amount) override
            {
                uint32 account;
                bool hardcore;
                return Principal(guid, account, hardcore) && !Hardcore::IsLocked(guid) &&
                       Adjust({account, hardcore, 0}, amount, false);
            }
            bool Transfer(Player* from, Player* to, int64 fromDelta, int64 toDelta) override
            {
                uint32 a, b;
                bool ha, hb;
                if (!Actor(from, a, ha) || !Actor(to, b, hb) || ha != hb)
                    return false;
                auto apply = [this](Key const& key, int64 delta)
                { return Adjust(key, delta < 0 ? uint64(-(delta + 1)) + 1 : uint64(delta), delta < 0); };
                if (a == b)
                {
                    // Reduce opposite signs before applying: a shared-principal trade
                    // cannot underflow merely because its net-zero debit leg runs first.
                    if ((fromDelta < 0) != (toDelta < 0))
                    {
                        int64 net = fromDelta + toDelta; // Opposite signs cannot overflow.
                        if (!apply({a, ha, 0}, net))
                            return false;
                    }
                    else if (!apply({a, ha, 0}, fromDelta) || !apply({a, ha, 0}, toDelta))
                        return false;
                }
                else if (!apply({a, ha, 0}, fromDelta) || !apply({b, hb, 0}, toDelta))
                    return false;
                from->SetMoneyMirror(uint32(std::min<uint64>(Row({a, ha, 0}).amount, UINT32_MAX)));
                to->SetMoneyMirror(uint32(std::min<uint64>(Row({b, hb, 0}).amount, UINT32_MAX)));
                return true;
            }
            bool Dirty() const override
            {
                return std::any_of(changes_.begin(), changes_.end(),
                                   [](auto const& pair) { return pair.second.dirty; });
            }
            bool Commit() override
            {
                std::string id = NewId();
                uint32 sequence = 0;
                for (auto const& [key, row] : changes_)
                {
                    if (!row.dirty)
                        continue;
                    auto [account, hardcore, entry] = key;
                    if (entry)
                    {
                        transaction->Append(
                            "INSERT IGNORE INTO dc_account_currency(account_id,mode,item_entry) VALUES({},'{}',{})",
                            account, Mode(hardcore), entry);
                        transaction->Append("UPDATE dc_account_currency SET amount={},revision=revision+1 WHERE "
                                            "account_id={} AND mode='{}' AND item_entry={} AND revision={}",
                                            row.amount, account, Mode(hardcore), entry, row.before.revision);
                    }
                    else
                    {
                        transaction->Append("INSERT IGNORE INTO dc_account_gold(account_id,mode) VALUES({},'{}')",
                                            account, Mode(hardcore));
                        transaction->Append("UPDATE dc_account_gold SET balance_copper={},revision=revision+1 WHERE "
                                            "account_id={} AND mode='{}' AND revision={}",
                                            row.amount, account, Mode(hardcore), row.before.revision);
                    }
                    // A stale revision must fail the whole SQL transaction, not silently
                    // commit inventory with a zero-row UPDATE. MySQL 8 enforces CHECK.
                    transaction->Append("INSERT INTO dc_account_economy_check VALUES('{}',{},IF(ROW_COUNT()=1,1,0))",
                                        id, sequence++);
                    if (!entry && faultAccounts.erase({account, hardcore}))
                        transaction->Append("INSERT INTO dc_account_economy_check VALUES('{}',{},0)", id, sequence++);
                }
                transaction->Append("INSERT INTO dc_account_economy_operation(operation_id,description) "
                                    "VALUES('{}','account operation')",
                                    id);
                bool ok = CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get();
                for (auto const& [key, row] : changes_)
                {
                    if (!row.dirty)
                        continue;
                    if (ok)
                        cache[key] = {row.amount, row.before.revision + 1};
                    else
                        cache.erase(key);
                }
                changes_.clear();
                receipts.clear();
                return ok;
            }

        private:
            std::unique_lock<std::recursive_mutex> lock_;
            std::map<Key, PendingBalance> changes_;
        };
        class Provider final : public PlayerEconomy::Provider
        {
        public:
            std::unique_ptr<PlayerEconomy::Context> Begin() override
            {
                return std::make_unique<Operation>();
            }
            bool ReadOffline(uint32 guid, uint64& value) override
            {
                std::lock_guard<std::recursive_mutex> lock(mutex);
                uint32 account;
                bool hardcore;
                if (!Principal(guid, account, hardcore))
                    return false;
                value = Load({account, hardcore, 0}).amount;
                return true;
            }
            bool AllowTransfer(uint32 from, uint32 to) override
            {
                std::lock_guard<std::recursive_mutex> lock(mutex);
                uint32 a, b;
                bool ha, hb;
                if (!Principal(to, b, hb))
                    return false;
                return from == 0 || (Principal(from, a, ha) && ha == hb);
            }
        } provider;
        Operation* Current()
        {
            return dynamic_cast<Operation*>(PlayerEconomy::Current());
        }
        bool MaterialChange(Player* player, uint32 entry, uint64 amount, bool debit, std::string const& receipt,
                            uint64* lost = nullptr)
        {
            if (lost)
                *lost = 0;
            if (!enabled || (entry && !IsMaterial(entry)))
                return false;
            PlayerEconomy::Scope scope(player);
            try
            {
                auto* operation = Current();
                uint32 account;
                bool hardcore;
                if (!operation || !Actor(player, account, hardcore))
                    return false;
                PlayerEconomy::Enlist(player);
                if (!receipt.empty())
                {
                    if (receipt.size() > 96 ||
                        std::any_of(receipt.begin(), receipt.end(), [](unsigned char c) { return c < 32 || c > 126; }))
                        return false;
                    std::string payload = std::to_string(account) + ":" + Mode(hardcore) + ":" + std::to_string(entry) +
                                          ":" + std::to_string(amount) + ":" + (debit ? "debit" : "credit");
                    auto pending = operation->receipts.find(receipt);
                    if (pending != operation->receipts.end())
                        return pending->second == payload;
                    auto prior = CharacterDatabase.Query("SELECT COALESCE((SELECT description FROM "
                                                         "dc_account_economy_operation WHERE operation_id='{}'),'')",
                                                         Escape(receipt));
                    if (!prior)
                    {
                        PlayerEconomy::Fail();
                        return false;
                    }
                    auto description = (*prior)[0].Get<std::string>();
                    if (!description.empty())
                        return description == payload;
                    operation->transaction->Append(
                        "INSERT INTO dc_account_economy_operation(operation_id,description) VALUES('{}','{}')",
                        Escape(receipt), Escape(payload));
                    operation->receipts.emplace(receipt, payload);
                }
                uint64 grant = amount;
                if (!debit && entry == BloodShards::Entry)
                {
                    auto const fit = BloodShards::Fit(operation->Row({account, hardcore, entry}).amount, amount,
                                                      ShardCap(account, hardcore));
                    grant = fit.granted;
                    if (lost)
                        *lost = fit.lost;
                }
                bool ok = !operation->failed &&
                          (entry                         ? !grant || operation->Adjust({account, hardcore, entry}, grant, debit)
                           : amount <= uint64(INT64_MAX) ? player->ModifyMoney(debit ? -int64(amount) : int64(amount))
                                                         : PlayerEconomy::Change(player, amount, debit));
                if (!ok)
                    PlayerEconomy::Fail();
                return scope.Finish() && ok;
            }
            catch (std::exception const&)
            {
                PlayerEconomy::Fail();
                return false;
            }
        }
        bool Migrate();
        bool HasMigratedSources()
        {
            return Count("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND "
                         "table_name='dc_account_economy_migration'") &&
                   Count("SELECT COUNT(*) FROM dc_account_economy_migration");
        }
        uint64 RetiredKnownMask()
        {
            uint64 mask = 0;
            for (auto const& [entry, kind] : kinds)
                if (auto const* currency = sCurrencyTypesStore.LookupEntry(entry);
                    currency && currency->BitIndex > 0 && currency->BitIndex <= 64)
                    mask |= uint64(1) << (currency->BitIndex - 1);
            return mask;
        }
        void Push(Player* player)
        {
            Snapshot snapshot;
            if (!ReadSnapshot(player, snapshot))
                return;
            std::string message = "DCECON\t" + std::to_string(snapshot.account) + ";" + snapshot.mode + ";" +
                                  snapshot.revision + ";" + snapshot.gold;
            for (auto const& [entry, amount] : snapshot.materials)
                message += ";" + std::to_string(entry) + "=" + amount;
            WorldPacket packet;
            ChatHandler::BuildChatPacket(packet, CHAT_MSG_WHISPER, LANG_ADDON, player, player, message);
            player->GetSession()->SendPacket(&packet);
            sentRevisions[player->GetGUID().GetRawValue()] = std::stoull(snapshot.revision);
        }
    } // namespace
    bool Enabled()
    {
        return enabled;
    }
    bool Eligible(Player const* player)
    {
        std::lock_guard<std::recursive_mutex> lock(mutex);
        uint32 account;
        bool hardcore;
        return enabled && Actor(player, account, hardcore);
    }
    bool IsMaterial(uint32 entry)
    {
        auto found = kinds.find(entry);
        return found != kinds.end() && found->second.material;
    }
    uint64 MaterialBalance(Player const* player, uint32 entry)
    {
        if (!enabled || !IsMaterial(entry))
            return 0;
        PlayerEconomy::Scope scope;
        uint32 account;
        bool hardcore;
        try
        {
            return Actor(player, account, hardcore) ? Current()->Row({account, hardcore, entry}).amount : 0;
        }
        catch (std::exception const&)
        {
            PlayerEconomy::Fail();
            return 0;
        }
    }
    bool CreditMaterial(Player* p, uint32 e, uint64 n, std::string const& receipt, uint64* lost)
    {
        return IsMaterial(e) && MaterialChange(p, e, n, false, receipt, lost);
    }
    bool CreditGold(Player* p, uint64 n, std::string const& receipt)
    {
        return MaterialChange(p, 0, n, false, receipt);
    }
    bool DebitMaterial(Player* p, uint32 e, uint64 n)
    {
        return IsMaterial(e) && MaterialChange(p, e, n, true, "");
    }
    bool ReadSnapshot(Player const* player, Snapshot& snapshot)
    {
        if (!enabled)
            return false;
        PlayerEconomy::Scope scope;
        try
        {
            uint32 account;
            bool hardcore;
            if (!Actor(player, account, hardcore))
                return false;
            auto& gold = Current()->Row({account, hardcore, 0});
            snapshot = {account, Mode(hardcore), std::to_string(gold.amount), std::to_string(gold.before.revision), {}};
            for (auto const& [entry, kind] : kinds)
                if (kind.material)
                    snapshot.materials[entry] = std::to_string(Current()->Row({account, hardcore, entry}).amount);
            return true;
        }
        catch (std::exception const&)
        {
            PlayerEconomy::Fail();
            return false;
        }
    }
    bool TopUp(Player* player, uint64 goldCopper, uint64 materialCount, Snapshot& before, Snapshot& after)
    {
        if (!enabled || !player)
            return false;
        PlayerEconomy::Scope scope(player);
        try
        {
            auto* operation = Current();
            uint32 account;
            bool hardcore;
            if (!operation || !Actor(player, account, hardcore) || !ReadSnapshot(player, before))
                return false;
            auto const gold = std::stoull(before.gold);
            if (gold < goldCopper && !PlayerEconomy::Change(player, goldCopper, false, true))
            {
                PlayerEconomy::Fail();
                return false;
            }
            for (auto const& [entry, value] : before.materials)
            {
                auto const held = std::stoull(value);
                // The coffer raises every material, Blood Shards only up to the account's cap.
                auto const target =
                    entry == BloodShards::Entry ? std::min(materialCount, ShardCap(account, hardcore)) : materialCount;
                if (held < target && !operation->Adjust({account, hardcore, entry}, target - held, false))
                {
                    PlayerEconomy::Fail();
                    return false;
                }
            }
            if (!ReadSnapshot(player, after))
            {
                PlayerEconomy::Fail();
                return false;
            }
            return scope.Finish();
        }
        catch (std::exception const&)
        {
            PlayerEconomy::Fail();
            return false;
        }
    }
    bool Commit(Player* player, CharacterDatabaseTransaction const& transaction)
    {
        if (!enabled)
            return CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get();
        PlayerEconomy::Enlist(player);
        if (!Current() || Current()->transaction != transaction)
        {
            PlayerEconomy::Fail();
            return false;
        }
        return PlayerEconomy::Flush();
    }
    namespace
    {
        struct LegacyCharacter
        {
            uint32 account = 0;
            std::string mode;
            uint64 money = 0;
            bool seeded = false;
        };
        struct Contribution
        {
            std::string kind, mode, location;
            uint64 guid = 0, original = 0, pool = 0;
            uint32 character = 0, account = 0, entry = 0, mail = 0;
            bool recorded = false;
        };
        void Quarantine(uint32 guid, std::string const& reason)
        {
            quarantinedCharacters.insert(guid);
            LOG_ERROR("server.loading",
                      "[DC accounts] Character guid={} quarantined: {}; repair migration provenance before login", guid,
                      reason);
        }
        void QuarantineItem(uint64 item, std::set<uint32> const& principals, std::string const& reason,
                            std::set<uint64>& unownedItems)
        {
            if (principals.empty())
            {
                unownedItems.insert(item);
                return;
            }
            for (uint32 guid : principals)
                Quarantine(guid, "item source " + std::to_string(item) + ": " + reason);
        }
        void AppendContribution(Operation& operation, Contribution const& source)
        {
            if (source.recorded)
                return;
            if (source.mode != "pending" &&
                !operation.Adjust({source.account, source.mode == "hardcore", source.entry}, source.pool, false))
                throw std::runtime_error("Legacy holdings exceed uint64 capacity");
            operation.transaction->Append(
                "INSERT INTO "
                "dc_account_economy_migration(source_kind,source_guid,character_guid,account_id,mode,item_entry,"
                "original_amount,pool_amount,location) VALUES('{}',{},{},{},'{}',{},{},{},'{}')",
                source.kind, source.guid, source.character, source.account, source.mode, source.entry, source.original,
                source.pool, Escape(source.location));
        }
        bool ClaimPending(Operation& operation, uint32 guid, uint32 account, std::string const& mode)
        {
            if (mode == "pending")
                return true;
            auto rows = CharacterDatabase.Query(
                "SELECT source_kind,source_guid,item_entry,pool_amount FROM dc_account_economy_migration WHERE "
                "character_guid={} AND account_id={} AND mode='pending' ORDER BY source_kind,source_guid",
                guid, account);
            uint64 expected =
                Count("SELECT COUNT(*) FROM dc_account_economy_migration WHERE character_guid=" + std::to_string(guid) +
                      " AND account_id=" + std::to_string(account) + " AND mode='pending'");
            if ((rows ? rows->GetRowCount() : 0) != expected)
                throw std::runtime_error("Pending migration read was incomplete");
            if (!rows)
                return true;
            struct PendingSource
            {
                std::string kind;
                uint64 guid = 0, pool = 0;
                uint32 entry = 0;
            };
            std::vector<PendingSource> sources;
            std::map<uint32, uint64> totals;
            do
            {
                auto* f = rows->Fetch();
                uint32 entry = f[2].Get<uint32>();
                uint64 pool = f[3].Get<uint64>();
                if (pool > UINT64_MAX - totals[entry])
                    return false;
                totals[entry] += pool;
                sources.push_back({f[0].Get<std::string>(), f[1].Get<uint64>(), pool, entry});
            } while (rows->NextRow());
            for (auto const& [entry, total] : totals)
            {
                auto const& row = operation.Row({account, mode == "hardcore", entry});
                auto const& gold = operation.Row({account, mode == "hardcore", 0});
                if (row.before.revision == UINT64_MAX || gold.before.revision == UINT64_MAX ||
                    total > UINT64_MAX - row.amount)
                    return false;
            }
            std::string id = NewId();
            uint32 sequence = 0;
            for (auto const& source : sources)
            {
                // The complete per-character total was checked before the first
                // mutation, so a data-capacity failure cannot leave a partial claim.
                if (!operation.Adjust({account, mode == "hardcore", source.entry}, source.pool, false))
                    throw std::runtime_error("Pending claim changed after capacity preflight");
                operation.transaction->Append(
                    "UPDATE dc_account_economy_migration SET mode='{}' WHERE source_kind='{}' AND source_guid={} AND "
                    "mode='pending' AND account_id={}",
                    mode, source.kind, source.guid, account);
                operation.transaction->Append(
                    "INSERT INTO dc_account_economy_check VALUES('{}',{},IF(ROW_COUNT()=1,1,0))", id, sequence++);
            }
            return true;
        }
        bool Migrate()
        {
            auto online = CharacterDatabase.Query("SELECT COUNT(*) FROM characters WHERE online<>0");
            if (!online || (*online)[0].Get<uint64>() != 0)
                throw std::runtime_error("Account migration requires all characters offline");
            Operation operation;
            quarantinedCharacters.clear();
            std::map<uint32, LegacyCharacter> characters;
            std::vector<Contribution> contributions;
            std::set<uint64> unownedItems;
            uint64 expectedCharacters = Count("SELECT COUNT(*) FROM characters");
            auto rows = CharacterDatabase.Query(
                "SELECT c.guid,c.account,c.money,COALESCE(m.mode,'pending'),e.source_guid,e.account_id,e.mode FROM "
                "characters c LEFT JOIN dc_character_mode m ON m.guid=c.guid LEFT JOIN dc_account_economy_migration e "
                "ON e.source_kind='character' AND e.source_guid=c.guid ORDER BY c.guid");
            if ((rows ? rows->GetRowCount() : 0) != expectedCharacters)
                throw std::runtime_error("Character migration read was incomplete");
            if (rows)
                do
                {
                    auto* f = rows->Fetch();
                    uint32 guid = f[0].Get<uint32>();
                    LegacyCharacter character{f[1].Get<uint32>(), f[3].Get<std::string>(), f[2].Get<uint64>(),
                                              f[4].Get<uint64>() != 0};
                    if (!character.account)
                        Quarantine(guid, "legacy character has no account owner");
                    if (character.mode != "pending" && character.mode != "normal" && character.mode != "hardcore")
                        Quarantine(guid, "legacy character mode is invalid");
                    if (character.seeded &&
                        (f[5].Get<uint32>() != character.account ||
                         (f[6].Get<std::string>() != "pending" && f[6].Get<std::string>() != character.mode)))
                        Quarantine(guid, "character seed principal disagrees with live character");
                    characters.emplace(guid, character);
                    if (!character.seeded && !quarantinedCharacters.count(guid))
                        contributions.push_back({"character", character.mode, "characters.money", guid, character.money,
                                                 character.money, guid, character.account, 0, 0, false});
                } while (rows->NextRow());
            // Pending item contributions can remain after their item was consumed.
            // Check them separately so a stale row cannot be claimed by a reused GUID.
            auto pending = CharacterDatabase.Query(
                "SELECT e.character_guid,e.source_guid FROM dc_account_economy_migration e JOIN characters c "
                "ON c.guid=e.character_guid WHERE e.source_kind='item' AND e.mode='pending' AND "
                "e.account_id<>c.account");
            uint64 expectedPending = Count(
                "SELECT COUNT(*) FROM dc_account_economy_migration e JOIN characters c ON c.guid=e.character_guid "
                "WHERE e.source_kind='item' AND e.mode='pending' AND e.account_id<>c.account");
            if ((pending ? pending->GetRowCount() : 0) != expectedPending)
                throw std::runtime_error("Pending item provenance read was incomplete");
            if (pending)
                do
                {
                    auto* f = pending->Fetch();
                    Quarantine(f[0].Get<uint32>(), "pending item source " + std::to_string(f[1].Get<uint64>()) +
                                                       " belongs to another account");
                } while (pending->NextRow());
            std::string entries;
            for (auto const& [entry, kind] : kinds)
            {
                if (!entries.empty())
                    entries += ",";
                entries += std::to_string(entry);
            }
            if (entries.empty())
                throw std::runtime_error("Legacy currency manifest is missing");
            uint64 expectedItems = Count("SELECT COUNT(*) FROM item_instance WHERE itemEntry IN (" + entries + ")");
            rows = CharacterDatabase.Query(
                "SELECT "
                "i.guid,i.itemEntry,i.owner_guid,i.count,e.source_guid,e.character_guid,e.account_id,e.original_amount,"
                "e.item_entry,e.pool_amount,e.mode FROM item_instance i LEFT JOIN dc_account_economy_migration e ON "
                "e.source_kind='item' AND e.source_guid=i.guid WHERE i.itemEntry IN ({}) ORDER BY i.guid",
                entries);
            if ((rows ? rows->GetRowCount() : 0) != expectedItems)
                throw std::runtime_error("Item migration read was incomplete");
            if (rows)
                do
                {
                    auto* f = rows->Fetch();
                    uint64 item = f[0].Get<uint64>(), count = f[3].Get<uint64>();
                    uint32 entry = f[1].Get<uint32>(), owner = f[2].Get<uint32>();
                    auto inventory =
                        CharacterDatabase.Query("SELECT guid,bag,slot FROM character_inventory WHERE item={}", item);
                    auto mail = CharacterDatabase.Query("SELECT m.id,m.receiver,m.sender FROM mail_items mi JOIN mail "
                                                        "m ON m.id=mi.mail_id WHERE mi.item_guid={}",
                                                        item);
                    uint64 inventoryCount =
                        Count("SELECT COUNT(*) FROM character_inventory WHERE item=" + std::to_string(item));
                    uint64 mailCount = Count("SELECT COUNT(*) FROM mail_items mi JOIN mail m ON m.id=mi.mail_id "
                                             "WHERE mi.item_guid=" +
                                             std::to_string(item));
                    if ((inventory ? inventory->GetRowCount() : 0) != inventoryCount ||
                        (mail ? mail->GetRowCount() : 0) != mailCount)
                        throw std::runtime_error("Legacy item location read was incomplete");
                    std::set<uint32> principals;
                    auto addPrincipal = [&](uint32 guid)
                    {
                        if (characters.count(guid))
                            principals.insert(guid);
                    };
                    addPrincipal(owner);
                    if (f[4].Get<uint64>() != 0 && f[10].Get<std::string>() == "pending")
                        addPrincipal(f[5].Get<uint32>());
                    uint32 inventoryGuid = 0, bag = 0, slot = 0, mailId = 0, receiver = 0, sender = 0;
                    if (inventory)
                        do
                        {
                            auto* link = inventory->Fetch();
                            if (!inventoryGuid)
                            {
                                inventoryGuid = link[0].Get<uint32>();
                                bag = link[1].Get<uint32>();
                                slot = link[2].Get<uint32>();
                            }
                            addPrincipal(link[0].Get<uint32>());
                        } while (inventory->NextRow());
                    if (mail)
                        do
                        {
                            auto* link = mail->Fetch();
                            if (!mailId)
                            {
                                mailId = link[0].Get<uint32>();
                                receiver = link[1].Get<uint32>();
                                sender = link[2].Get<uint32>();
                            }
                            addPrincipal(link[1].Get<uint32>());
                            addPrincipal(link[2].Get<uint32>());
                        } while (mail->NextRow());
                    if (!count || bool(inventoryCount) == bool(mailCount))
                    {
                        QuarantineItem(item, principals,
                                       !count ? "zero-count legacy currency item" : "ambiguous or orphaned location",
                                       unownedItems);
                        continue;
                    }
                    Contribution source;
                    source.kind = "item";
                    source.guid = item;
                    source.original = count;
                    source.recorded = f[4].Get<uint64>() != 0;
                    if (inventoryCount)
                    {
                        source.character = inventoryGuid;
                        source.location = "inventory:" + std::to_string(bag) + ":" + std::to_string(slot);
                        if (owner != source.character || inventoryCount != 1)
                        {
                            QuarantineItem(item, principals, "inventory ownership or link mismatch", unownedItems);
                            continue;
                        }
                    }
                    else
                    {
                        source.mail = mailId;
                        source.character = receiver;
                        auto receiverCharacter = characters.find(source.character), from = characters.find(sender);
                        if (receiverCharacter == characters.end() ||
                            (sender && (from == characters.end() || receiverCharacter->second.mode == "pending" ||
                                        from->second.mode != receiverCharacter->second.mode)))
                        {
                            QuarantineItem(item, principals, "mail principals are unresolved or cross-mode",
                                           unownedItems);
                            continue;
                        }
                        if ((owner != source.character && owner != sender) || mailCount != 1)
                        {
                            QuarantineItem(item, principals, "mail ownership or link mismatch", unownedItems);
                            continue;
                        }
                        source.location = "mail:" + std::to_string(source.mail) + ":sender:" + std::to_string(sender);
                    }
                    auto character = characters.find(source.character);
                    if (character == characters.end())
                    {
                        QuarantineItem(item, principals, "legacy currency owner is missing", unownedItems);
                        continue;
                    }
                    if (quarantinedCharacters.count(source.character))
                        continue;
                    source.account = character->second.account;
                    source.mode = character->second.mode;
                    auto kind = kinds.at(entry);
                    source.entry = kind.material ? entry : 0;
                    if (!kind.material && count > UINT64_MAX / kind.copper)
                    {
                        Quarantine(source.character,
                                   "item source " + std::to_string(item) + " Gold Bar conversion overflows");
                        continue;
                    }
                    source.pool = kind.material ? count : count * kind.copper;
                    if (source.recorded)
                    {
                        std::string recordedMode = f[10].Get<std::string>();
                        bool valueMismatch = f[7].Get<uint64>() != count || f[8].Get<uint32>() != source.entry ||
                                             f[9].Get<uint64>() != source.pool;
                        // Settled rows are historical account audit records. Their
                        // character GUID/account/mode need not describe this live item.
                        bool pendingPrincipalMismatch =
                            recordedMode == "pending" &&
                            (f[5].Get<uint32>() != source.character || f[6].Get<uint32>() != source.account);
                        if (valueMismatch || pendingPrincipalMismatch)
                        {
                            QuarantineItem(item, principals,
                                           "source value or pending principal disagrees with provenance", unownedItems);
                            continue;
                        }
                    }
                    if (Count("SELECT COUNT(*) FROM dc_item_instance WHERE item_guid=" + std::to_string(item)))
                    {
                        Quarantine(source.character,
                                   "item source " + std::to_string(item) + " has rolled item metadata");
                        continue;
                    }
                    contributions.push_back(source);
                } while (rows->NextRow());
            if (!unownedItems.empty())
            {
                std::string guids;
                for (uint64 item : unownedItems)
                {
                    if (!guids.empty())
                        guids += ",";
                    guids += std::to_string(item);
                }
                LOG_ERROR("server.loading",
                          "[DC accounts] Unowned legacy items left untouched and unpaid: count={} item_guids={}; "
                          "repair source rows",
                          unownedItems.size(), guids);
            }
            contributions.erase(std::remove_if(contributions.begin(), contributions.end(),
                                               [](Contribution const& source)
                                               { return quarantinedCharacters.count(source.character) != 0; }),
                                contributions.end());
            // All credits for one account/mode/asset must fit together. If they
            // do not, quarantine every contributor to that total before adding
            // anything to the shared operation; iteration order cannot decide
            // which character receives the remaining capacity.
            std::map<Key, uint64> proposed;
            std::map<Key, std::set<uint32>> contributors;
            std::set<Key> overflowing;
            auto plan = [&](uint32 guid, Key const& key, uint64 amount)
            {
                contributors[key].insert(guid);
                if (!overflowing.count(key))
                {
                    if (amount > UINT64_MAX - proposed[key])
                        overflowing.insert(key);
                    else
                        proposed[key] += amount;
                }
            };
            for (auto const& source : contributions)
                if (!source.recorded && source.mode != "pending")
                    plan(source.character, {source.account, source.mode == "hardcore", source.entry}, source.pool);
            auto pendingCredits = CharacterDatabase.Query(
                "SELECT character_guid,account_id,item_entry,pool_amount FROM dc_account_economy_migration "
                "WHERE mode='pending' ORDER BY character_guid,source_kind,source_guid");
            uint64 expectedCredits = Count("SELECT COUNT(*) FROM dc_account_economy_migration WHERE mode='pending'");
            if ((pendingCredits ? pendingCredits->GetRowCount() : 0) != expectedCredits)
                throw std::runtime_error("Pending credit preflight read was incomplete");
            if (pendingCredits)
                do
                {
                    auto* f = pendingCredits->Fetch();
                    uint32 guid = f[0].Get<uint32>();
                    auto character = characters.find(guid);
                    if (character == characters.end() || quarantinedCharacters.count(guid) ||
                        character->second.mode == "pending" || f[1].Get<uint32>() != character->second.account)
                        continue;
                    plan(guid, {character->second.account, character->second.mode == "hardcore", f[2].Get<uint32>()},
                         f[3].Get<uint64>());
                } while (pendingCredits->NextRow());
            for (auto const& [key, amount] : proposed)
            {
                auto const& row = operation.Row(key);
                auto const& gold = operation.Row({std::get<0>(key), std::get<1>(key), 0});
                if (row.before.revision == UINT64_MAX || gold.before.revision == UINT64_MAX ||
                    amount > UINT64_MAX - row.amount)
                    overflowing.insert(key);
            }
            for (auto const& key : overflowing)
                for (uint32 guid : contributors.at(key))
                    Quarantine(guid, "account pool capacity or revision exhausted: account=" +
                                         std::to_string(std::get<0>(key)) + " mode=" + Mode(std::get<1>(key)) +
                                         " asset=" + std::to_string(std::get<2>(key)));
            contributions.erase(std::remove_if(contributions.begin(), contributions.end(),
                                               [](Contribution const& source)
                                               { return quarantinedCharacters.count(source.character) != 0; }),
                                contributions.end());
            // Preflight above did not write anything. Contributions, removal, provenance
            // and mirrors below share one durable commit, including dead hardcore owners.
            std::string sourceCheck = NewId();
            uint32 sourceSequence = 0;
            for (auto const& source : contributions)
            {
                // Validate the original source again inside the write transaction.
                // INSERT ... SELECT takes source locks until commit; a changed source
                // refuses the entire migration instead of crediting the preflight copy.
                if (source.kind == "character")
                    operation.transaction->Append(
                        "INSERT INTO dc_account_economy_check SELECT '{}',{},IF(COUNT(*)=1,1,0) FROM characters WHERE "
                        "guid={} AND account={} AND money={}",
                        sourceCheck, sourceSequence++, source.guid, source.account, source.original);
                else
                    operation.transaction->Append(
                        "INSERT INTO dc_account_economy_check SELECT '{}',{},IF(COUNT(*)=1,1,0) FROM item_instance "
                        "WHERE guid={} AND count={}",
                        sourceCheck, sourceSequence++, source.guid, source.original);
                AppendContribution(operation, source);
                if (source.kind == "item")
                {
                    operation.transaction->Append("DELETE FROM character_inventory WHERE item={}", source.guid);
                    operation.transaction->Append("DELETE FROM mail_items WHERE item_guid={}", source.guid);
                    operation.transaction->Append("DELETE FROM item_instance WHERE guid={}", source.guid);
                    if (source.mail)
                        operation.transaction->Append(
                            "UPDATE mail SET has_items=EXISTS(SELECT 1 FROM mail_items WHERE mail_id={}) WHERE id={}",
                            source.mail, source.mail);
                }
            }
            for (auto const& [guid, character] : characters)
            {
                if (quarantinedCharacters.count(guid))
                    continue;
                if (!ClaimPending(operation, guid, character.account, character.mode))
                {
                    Quarantine(guid, "pending contribution exceeds account capacity");
                    continue;
                }
                uint64 balance = character.mode == "pending"
                                     ? 0
                                     : operation.Row({character.account, character.mode == "hardcore", 0}).amount;
                operation.transaction->Append(
                    "UPDATE characters SET money={},knownCurrencies=knownCurrencies & {} WHERE guid={}",
                    std::min<uint64>(balance, UINT32_MAX), ~RetiredKnownMask(), guid);
            }
            return operation.Commit();
        }
        class AccountWorld final : public WorldScript
        {
        public:
            AccountWorld()
                : WorldScript("dc_account_economy", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                auto rows = WorldDatabase.Query(
                    "SELECT item_entry,kind,copper_per_item FROM dc_account_economy_kind ORDER BY item_entry");
                if (rows)
                    do
                    {
                        auto* f = rows->Fetch();
                        kinds[f[0].Get<uint32>()] = {f[1].Get<std::string>() == "material", f[2].Get<uint64>()};
                    } while (rows->NextRow());
                try
                {
                    if (!sConfigMgr->GetOption<bool>("Diablocraft.AccountEconomy.Enable", false))
                    {
                        if (HasMigratedSources())
                            throw std::runtime_error("Cannot disable account authority after migration; restore the "
                                                     "complete pre-cutover database for a rollback");
                        LOG_INFO(
                            "server.loading",
                            "[DC accounts] Cutover disabled; requires the complete gold/material caller integration.");
                        return;
                    }
                    if (!rows || kinds.size() != rows->GetRowCount() || !Migrate())
                        throw std::runtime_error("Account migration failed");
                    enabled = true;
                    PlayerEconomy::Install(&provider);
                    LOG_INFO("server.loading", "[DC accounts] Account-mode economy enabled; migration committed.");
                }
                catch (std::exception const& error)
                {
                    LOG_ERROR("server.loading", "[DC accounts] Startup refused: {}", error.what());
                    World::StopNow(ERROR_EXIT_CODE);
                }
            }
        };
        class AccountPlayer final : public PlayerScript
        {
        public:
            AccountPlayer()
                : PlayerScript("dc_account_economy_player", {PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_UPDATE,
                                                             PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_DELETE_FROM_DB})
            {
            }
            void OnPlayerLogin(Player* player) override
            {
                if (enabled && !ResolvePending(player))
                    player->GetSession()->AbortEconomy();
                if (enabled)
                {
                    std::lock_guard<std::recursive_mutex> lock(mutex);
                    player->SetUInt64Value(PLAYER_FIELD_KNOWN_CURRENCIES,
                                           player->GetUInt64Value(PLAYER_FIELD_KNOWN_CURRENCIES) & ~RetiredKnownMask());
                    Push(player);
                }
            }
            void OnPlayerUpdate(Player* player, uint32) override
            {
                if (!enabled || player->GetSession()->EconomyAborted())
                    return;
                auto mode = Hardcore::ModeOf(player);
                std::lock_guard<std::recursive_mutex> lock(mutex);
                if (mode == Hardcore::Mode::Unchosen ||
                    (mode == Hardcore::Mode::Hardcore && Hardcore::IsLocked(player->GetGUID().GetCounter())))
                {
                    if (sentRevisions.erase(player->GetGUID().GetRawValue()))
                    {
                        WorldPacket packet;
                        ChatHandler::BuildChatPacket(packet, CHAT_MSG_WHISPER, LANG_ADDON, player, player,
                                                     "DCECON\tclear");
                        player->GetSession()->SendPacket(&packet);
                    }
                    return;
                }
                auto found = cache.find({player->GetSession()->GetAccountId(), mode == Hardcore::Mode::Hardcore, 0});
                if (found != cache.end())
                {
                    uint32 mirror = uint32(std::min<uint64>(found->second.amount, UINT32_MAX));
                    if (player->GetMoney() != mirror)
                        player->SetMoneyMirror(mirror);
                    auto sent = sentRevisions.find(player->GetGUID().GetRawValue());
                    if (sent == sentRevisions.end() || sent->second != found->second.revision)
                        Push(player);
                }
            }
            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::recursive_mutex> lock(mutex);
                sentRevisions.erase(player->GetGUID().GetRawValue());
            }
            void OnPlayerDeleteFromDB(CharacterDatabaseTransaction transaction, uint32 guid) override
            {
                transaction->Append(
                    "DELETE FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid={}", guid);
                transaction->Append("DELETE FROM dc_account_economy_migration WHERE source_kind='item' AND "
                                    "character_guid={} AND mode='pending'",
                                    guid);
                std::lock_guard<std::recursive_mutex> lock(mutex);
                quarantinedCharacters.erase(guid);
            }
        };
        class AccountCommands final : public CommandScript
        {
        public:
            AccountCommands()
                : CommandScript("dc_account_snapshot")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable account = {{"snapshot", HandleSnapshot, SEC_PLAYER, Console::No},
                                                   {"failnext", HandleFailNext, SEC_ADMINISTRATOR, Console::No}};
                static ChatCommandTable dc = {{"account", account}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
            static bool HandleSnapshot(ChatHandler* handler)
            {
                auto* player = handler->GetSession()->GetPlayer();
                if (!Eligible(player))
                    return false;
                std::lock_guard<std::recursive_mutex> lock(mutex);
                Push(player);
                return true;
            }
            static bool HandleFailNext(ChatHandler* handler)
            {
                if (!sConfigMgr->GetOption<bool>("Diablocraft.AccountEconomy.TestFaults", false))
                    return false;
                uint32 account;
                bool hardcore;
                auto* player = handler->GetSession()->GetPlayer();
                std::lock_guard<std::recursive_mutex> lock(mutex);
                if (!enabled || !Actor(player, account, hardcore))
                    return false;
                faultAccounts.insert({account, hardcore});
                handler->SendSysMessage(
                    "Next account-mode write will fail its SQL transaction; reconnect to verify rollback.");
                return true;
            }
        };
        class AccountPackets final : public ServerScript
        {
        public:
            AccountPackets()
                : ServerScript("dc_account_no_bank_money", {SERVERHOOK_CAN_PACKET_RECEIVE})
            {
            }
            bool CanPacketReceive(WorldSession*, WorldPacket const& packet) override
            {
                if (!enabled)
                    return true;
                switch (packet.GetOpcode())
                {
                    // H2: no guild-wide item/money route between account modes. This
                    // refusal does not implement or open the blocked 0006 stash.
                    case CMSG_GUILD_BANKER_ACTIVATE:
                    case CMSG_GUILD_BANK_QUERY_TAB:
                    case CMSG_GUILD_BANK_SWAP_ITEMS:
                    case CMSG_GUILD_BANK_BUY_TAB:
                    case CMSG_GUILD_BANK_UPDATE_TAB:
                    case CMSG_GUILD_BANK_DEPOSIT_MONEY:
                    case CMSG_GUILD_BANK_WITHDRAW_MONEY:
                        return false;
                    // g400: items are account bound, so mail carries letters and gold
                    // only; the auction house is closed whole (a mailbox and an
                    // auctioneer both exist in the stock world).
                    case CMSG_SEND_MAIL:
                        return !DC::Mail::SendMailCarriesItem(packet);
                    case MSG_AUCTION_HELLO:
                    case CMSG_AUCTION_SELL_ITEM:
                    case CMSG_AUCTION_REMOVE_ITEM:
                    case CMSG_AUCTION_LIST_ITEMS:
                    case CMSG_AUCTION_LIST_OWNER_ITEMS:
                    case CMSG_AUCTION_PLACE_BID:
                    case CMSG_AUCTION_LIST_BIDDER_ITEMS:
                    case CMSG_AUCTION_LIST_PENDING_SALES:
                        return false;
                    default:
                        return true;
                }
            }
        };
    } // namespace
    static bool ResolveStart(Player* player, bool creation)
    {
        if (!enabled)
            return true;
        // The creation Player has a session but is deliberately not its logged-in
        // player. Resolve only the durable principal/ledger here; do not enlist it
        // in the online economy scope or weaken the core's session-owner guard.
        if (!player || (creation && (player->IsInWorld() || player->GetSession()->GetPlayer() ||
                                    !player->HasAtLoginFlag(AT_LOGIN_FIRST))))
            return false;
        PlayerEconomy::Scope scope(creation ? nullptr : player);
        auto* operation = Current();
        try
        {
            uint32 guid = player->GetGUID().GetCounter(), account = player->GetSession()->GetAccountId();
            if (quarantinedCharacters.count(guid))
                throw std::runtime_error("guid=" + std::to_string(guid) +
                                         " has quarantined migration provenance; repair row and restart");
            auto mode = Hardcore::ModeOf(player);
            std::string name = mode == Hardcore::Mode::Unchosen ? "pending" : Mode(mode == Hardcore::Mode::Hardcore);
            auto marker = CharacterDatabase.Query(
                "SELECT COALESCE((SELECT account_id FROM dc_account_economy_migration WHERE source_kind='character' "
                "AND source_guid={}),0),COALESCE((SELECT mode FROM dc_account_economy_migration WHERE "
                "source_kind='character' AND source_guid={}),'missing')",
                guid, guid);
            if (!marker)
                throw std::runtime_error("Character contribution lookup failed");
            auto recordedMode = (*marker)[1].Get<std::string>();
            if (recordedMode != "missing" &&
                ((*marker)[0].Get<uint32>() != account || (recordedMode != "pending" && recordedMode != name)))
                throw std::runtime_error("guid=" + std::to_string(guid) +
                                         " character seed principal changed; repair migration provenance");
            auto pendingMismatch = CharacterDatabase.Query(
                "SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='item' AND character_guid={} "
                "AND mode='pending' AND account_id<>{}",
                guid, account);
            if (!pendingMismatch)
                throw std::runtime_error("Pending item provenance lookup failed");
            if ((*pendingMismatch)[0].Get<uint64>() != 0)
                throw std::runtime_error("guid=" + std::to_string(guid) +
                                         " pending item principal changed; repair migration provenance");
            if (recordedMode == "missing")
            {
                auto original =
                    CharacterDatabase.Query("SELECT money FROM characters WHERE guid={} AND account={}", guid, account);
                if (!original)
                {
                    PlayerEconomy::Fail();
                    return false;
                }
                uint64 copper = (*original)[0].Get<uint64>();
                try
                {
                    AppendContribution(*operation, {"character", name, "new character seed", guid, copper, copper, guid,
                                                    account, 0, 0, false});
                }
                catch (std::exception const&)
                {
                    PlayerEconomy::Fail();
                    return false;
                }
            }
            if (!ClaimPending(*operation, guid, account, name))
            {
                PlayerEconomy::Fail();
                return false;
            }
            uint64 balance = name == "pending" ? 0 : operation->Row({account, name == "hardcore", 0}).amount;
            player->SetMoneyMirror(uint32(std::min<uint64>(balance, UINT32_MAX)));
            if (!creation && name != "pending" && !PlayerEconomy::FinalizeLoad(player))
            {
                PlayerEconomy::Fail();
                return false;
            }
            return PlayerEconomy::Flush();
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "[DC accounts] Login/choice refused: {}", error.what());
            PlayerEconomy::Fail();
            return false;
        }
    }
    bool ResolvePending(Player* player) { return ResolveStart(player, false); }
    bool ResolveCreation(Player* player) { return ResolveStart(player, true); }
    void RegisterScripts()
    {
        new AccountWorld();
        new AccountPlayer();
        new AccountCommands();
        new AccountPackets();
    }
} // namespace DC::AccountEconomy

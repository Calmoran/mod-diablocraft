#include "dc_economy.h"
#include "dc_account_economy.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "Item.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "WorldSession.h"
#include <limits>
namespace DC::Economy
{
    std::uint64_t CopperPerBar()
    {
        // CSV -> dc_account_economy_kind is the sole denomination authority.
        static auto const value = []() -> std::uint64_t
        {
            auto row = WorldDatabase.Query("SELECT copper_per_item FROM dc_account_economy_kind WHERE item_entry={} AND kind='retired_gold'", GoldBarEntry);
            if (!row) throw std::runtime_error("Missing retired Gold Bar denomination");
            auto denomination = (*row)[0].Get<uint64>();
            if (!denomination || denomination > std::numeric_limits<std::uint32_t>::max())
                throw std::runtime_error("Retired denomination exceeds native copper storage");
            return denomination;
        }();
        return value;
    }
    std::uint64_t Balance(Player const* player)
    {
        if(!player) return 0;
        return AccountEconomy::Enabled() ? player->GetAccountMoney() :
            uint64(player->GetMoney())+uint64(player->GetItemCount(GoldBarEntry,false))*CopperPerBar();
    }
    bool CanAfford(Player const* player, std::uint64_t copper)
    {
        return player && (!AccountEconomy::Enabled() || AccountEconomy::Eligible(player)) && Balance(player) >= copper;
    }
    bool Charge(Player* player, std::uint64_t copper)
    {
        if(!player) return false;
        if(!AccountEconomy::Enabled())
        {
            auto plan=Plan(player->GetMoney(),player->GetItemCount(GoldBarEntry,false),copper);
            if(!plan.ok || !player->SetMoney(plan.copper)) return false;
            if(plan.bars) player->DestroyItemCount(GoldBarEntry,plan.bars,true);
            return true;
        }
        if (!AccountEconomy::Eligible(player))
            return false;
        return copper <= uint64(INT64_MAX) ? player->ModifyMoney(-int64(copper))
                                           : PlayerEconomy::Change(player, copper, true);
    }
    bool Credit(Player* player, std::uint64_t copper)
    {
        if (!player)
            return false;
        if (AccountEconomy::Enabled())
        {
            if (!AccountEconomy::Eligible(player))
                return false;
            return copper <= uint64(INT64_MAX) ? player->ModifyMoney(int64(copper))
                                               : PlayerEconomy::Change(player, copper, false);
        }
        // Staged deployment before cutover retains native copper, never makes bars.
        return copper <= uint64(INT64_MAX) && player->ModifyMoney(int64(copper));
    }
    void KnowCurrency(Player* player, std::uint32_t entry)
    {
        if(!player || AccountEconomy::Enabled()) return;
        if(auto* currency=sCurrencyTypesStore.LookupEntry(entry);currency && currency->BitIndex>0 && currency->BitIndex<=64)
            player->SetFlag64(PLAYER_FIELD_KNOWN_CURRENCIES,1ULL<<(currency->BitIndex-1));
    }
    namespace
    {
        class GoldCommand final : public CommandScript
        {
        public:
            GoldCommand()
                : CommandScript("dc_gold_commands")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable gold = {{"balance", BalanceCommand, SEC_GAMEMASTER, Console::Yes},
                                                {"set", SetCommand, SEC_ADMINISTRATOR, Console::Yes},
                                                {"credit", CreditCommand, SEC_ADMINISTRATOR, Console::Yes},
                                                {"charge", ChargeCommand, SEC_ADMINISTRATOR, Console::Yes}};
                static ChatCommandTable dc = {{"gold", gold}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
            static Player* Find(ChatHandler* handler, std::string const& name)
            {
                auto* player = ObjectAccessor::FindPlayerByName(name);
                if (!player)
                    handler->SendSysMessage("That character must be online.");
                return player;
            }
            static void Report(ChatHandler* handler, Player* player)
            {
                // Gold is the only unit shown. The mirror is the
                // uint32 native field, saturated, and is diagnostics only.
                handler->PSendSysMessage("{}: account={} balance={} gold, mirror={}", player->GetName(),
                                         player->GetSession()->GetAccountId(), Balance(player), player->GetMoney());
            }
            static bool SaveAndReport(ChatHandler* handler, Player* player)
            {
                auto transaction = PlayerEconomy::BeginTransaction();
                player->SaveInventoryAndGoldToDB(transaction);
                if (!AccountEconomy::Commit(player, transaction))
                {
                    handler->SendSysMessage("Account payment failed; reconnect to reload the committed balance.");
                    return false;
                }
                Report(handler, player);
                return true;
            }
            static bool BalanceCommand(ChatHandler* handler, std::string name)
            {
                auto* player = Find(handler, name);
                if (!player)
                    return false;
                Report(handler, player);
                return true;
            }
            // All three take the one unit: gold, which is copper.
            static bool SetCommand(ChatHandler* handler, std::string name, uint64 gold)
            {
                auto* player = Find(handler, name);
                if (!player)
                    return false;
                if (!player->SetMoney(gold))
                    return false;
                return SaveAndReport(handler, player);
            }
            static bool CreditCommand(ChatHandler* handler, std::string name, uint64 gold)
            {
                auto* player = Find(handler, name);
                if (!player)
                    return false;
                if (gold > UINT64_MAX / CopperPerGold || !Credit(player, GoldCost(gold)))
                {
                    handler->SendSysMessage("Credit refused; balance unchanged.");
                    return false;
                }
                return SaveAndReport(handler, player);
            }
            static bool ChargeCommand(ChatHandler* handler, std::string name, uint64 gold)
            {
                auto* player = Find(handler, name);
                if (!player)
                    return false;
                if (gold > UINT64_MAX / CopperPerGold || !Charge(player, GoldCost(gold)))
                {
                    handler->SendSysMessage("Debit refused; balance unchanged.");
                    return false;
                }
                return SaveAndReport(handler, player);
            }
        };
    } // namespace
    void RegisterScripts()
    {
        AccountEconomy::RegisterScripts();
        new GoldCommand();
    }
} // namespace DC::Economy

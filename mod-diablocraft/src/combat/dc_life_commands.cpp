#include "dc_life_commands.h"
#include "dc_exact_damage.h"
#include "Chat.h"
#include "Creature.h"
#include "Player.h"
#include "ScriptMgr.h"
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat
{
    namespace
    {
        // `.dc dmgmult`: the GM's own dev multiplier, by player guid. Held here and nowhere else, so
        // it is not saved and the logout hook is all it takes for it to be gone.
        std::mutex devMutex;
        std::unordered_map<std::uint64_t, double> devMult;

        class DevMultLogout final : public PlayerScript
        {
        public:
            DevMultLogout()
                : PlayerScript("dc_dev_mult_logout", {PLAYERHOOK_ON_LOGOUT})
            {
            }
            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> lock(devMutex);
                devMult.erase(player->GetGUID().GetRawValue());
            }
        };

        class LifeCommands final : public CommandScript
        {
        public:
            LifeCommands()
                : CommandScript("dc_life_commands")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable children = {{"biglife", HandleMaxLife, SEC_ADMINISTRATOR, Console::No},
                                                      {"dmgmult", HandleDmgMult, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable root = {{"dc", children}};
                return root;
            }
            // `.dc dmgmult [x]` multiplies the GM's own final hits (skills, Rend ticks, Ancients), for dev testing of hits past 2^32; 1 turns it off,
            // no argument prints. Gone at logout.
            static bool HandleDmgMult(ChatHandler* handler, Optional<double> mult)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                if (mult)
                {
                    if (!(*mult > 0) || !std::isfinite(*mult))
                    {
                        handler->SendSysMessage("A number above 0; 1 turns it off.");
                        handler->SetSentErrorMessage(true);
                        return false;
                    }
                    std::lock_guard<std::mutex> lock(devMutex);
                    if (*mult == 1)
                        devMult.erase(player->GetGUID().GetRawValue());
                    else
                        devMult[player->GetGUID().GetRawValue()] = *mult;
                }
                handler->PSendSysMessage("Damage multiplier x{} (dev test, not saved, gone at logout).", DevMultiplier(player));
                return true;
            }
            // `.dc biglife <Life>` gives the selected creature that real max Life at full Life; no argument prints. A respawn restores the template Life.
            static bool HandleMaxLife(ChatHandler* handler, Optional<uint64> life)
            {
                Creature* creature = handler->getSelectedCreature();
                if (!creature)
                {
                    handler->SendSysMessage("Select a creature.");
                    handler->SetSentErrorMessage(true);
                    return false;
                }
                if (life)
                {
                    if (!*life)
                    {
                        handler->SendSysMessage("A Life above 0.");
                        handler->SetSentErrorMessage(true);
                        return false;
                    }
                    creature->SetBaseHealth(*life);
                    creature->UpdateMaxHealth();
                    creature->ResetPlayerDamageReq();
                    creature->SetFullHealth();
                }
                handler->PSendSysMessage("Life {} / {}.", creature->GetHealth(), creature->GetMaxHealth());
                return true;
            }
        };
    } // namespace

    double DevMultiplier(Unit const* dealer)
    {
        Player* player = dealer ? const_cast<Unit*>(dealer)->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
        if (!player)
            return 1;
        std::lock_guard<std::mutex> lock(devMutex);
        auto found = devMult.find(player->GetGUID().GetRawValue());
        return found == devMult.end() ? 1 : found->second;
    }

    double DevBoost(Unit const* dealer, double amount)
    {
        return Boosted(amount, DevMultiplier(dealer));
    }

    void RegisterLifeCommands()
    {
        new LifeCommands();
        new DevMultLogout();
    }
} // namespace DC::Combat

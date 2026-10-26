// Combat: the .dc combat diagnostics command.
#include "dc_combat_internal.h"

namespace DC::Combat
{
    namespace
    {
        class CombatCommand final : public CommandScript
        {
        public:
            CombatCommand()
                : CommandScript("dc_combat_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable combat = {
                    {"hit", HandleHit, SEC_GAMEMASTER, Console::No},
                    {"aps", HandleAps, SEC_GAMEMASTER, Console::No},
                    {"cooldowns", HandleCooldowns, SEC_GAMEMASTER, Console::No},
                    {"fury", HandleFury, SEC_GAMEMASTER, Console::No},
                };
                static ChatCommandTable root = {{"dc", combat}};
                return root;
            }

            static bool HandleCooldowns(ChatHandler* handler)
            {
                auto player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player) return false;
                // The record's own numbers, so the readout says what the core
                // reads: RecoveryTime, the category the rune family shares,
                // and what the player's modifiers make of them.
                for (auto const& slot : Classes::Bar(player))
                    if (auto shell = Shells::FindAbility(slot.spellId))
                    {
                        SpellInfo const* info = sSpellMgr->GetSpellInfo(slot.spellId);
                        handler->PSendSysMessage(
                            "{} ({}): record {} ms, category {} at {} ms, reduced to {} ms, "
                            "remaining {} ms, APS {}, swing {} ms",
                            !*shell->rune ? std::string(shell->skill)
                                          : std::string(shell->skill) + " - " + shell->rune,
                            slot.spellId, info ? info->RecoveryTime : 0,
                            info ? info->GetCategory() : 0, info ? info->CategoryRecoveryTime : 0,
                            SkillCooldownMilliseconds(player, slot.spellId),
                            player->GetSpellCooldownDelay(slot.spellId),
                            AttacksPerSecond(player, slot.spellId),
                            SwingEligible(slot.spellId) ? SwingRecoveryMilliseconds(player, slot.spellId) : 0);
                    }
                return true;
            }

            // .dc hit <skill name> - resolve one hit against the selected target and
            // print every bucket of damage_formula.csv.
            static bool HandleHit(ChatHandler* handler, Acore::ChatCommands::Tail skillName)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                std::string wanted(skillName);
                std::uint32_t spellId = 0;
                std::string baseSkill;
                {
                    std::lock_guard<std::mutex> lock(dataMutex);
                    for (auto const& [id, shell] : shells)
                    {
                        std::string full = shell.rune.empty() ? shell.skill : shell.skill + " - " + shell.rune;
                        if (full == wanted || shell.skill == wanted)
                        {
                            spellId = id;
                            baseSkill = shell.skill;
                            if (full == wanted)
                                break;
                        }
                    }
                }
                if (!spellId)
                {
                    handler->SendSysMessage("Unknown skill. Use the exact name, e.g. .dc hit Whirlwind");
                    return false;
                }
                Hit hit;
                hit.spent = ItemPowers::ResourceSpend(player, baseSkill, CurrentFury(player)); // Blade of the Warlord: the preview takes nothing, it shows what a cast now is worth
                if (!ComputeHit(player, handler->getSelectedUnit(), spellId, hit))
                {
                    handler->SendSysMessage("No stat sheet, or shell data is not loaded.");
                    return false;
                }
                handler->SendSysMessage(hit.Describe());
                if (double const mult = DevMultiplier(player); mult != 1)
                    handler->PSendSysMessage("Dev multiplier x{} (.dc dmgmult): the hit lands as {:.0f}.", mult,
                                             DevBoost(player, hit.total));
                LOG_INFO("server.loading", "[DC combat] {}", hit.Describe());
                return true;
            }

            static bool HandleFury(ChatHandler* handler)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                handler->PSendSysMessage("Fury: {} / {} (native Rage: {} / {})", CurrentFury(player),
                                         Resources::Max(player, Resources::Fury),
                                         Resources::Units(player, Resources::Fury),
                                         Resources::MaxUnits(player, Resources::Fury));
                return true;
            }

            // .dc aps - the sheet's APS beside the three inputs it is made of, so the
            // cached number can still be checked by hand now that combat reads it
            // rather than recomputing its own.
            static bool HandleAps(ChatHandler* handler)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
                if (!sheet)
                {
                    handler->SendSysMessage("No stat sheet.");
                    return false;
                }
                Item* main = player->GetWeaponForAttack(BASE_ATTACK, true);
                Item* off = player->GetWeaponForAttack(OFF_ATTACK, true);
                double delay = main && main->GetTemplate()->Delay ? main->GetTemplate()->Delay
                                                                  : player->GetAttackTime(BASE_ATTACK);
                if (delay <= 0)
                    delay = 2000;
                double const aps = AttacksPerSecond(player);
                std::ostringstream out;
                out.imbue(std::locale::classic());
                out << std::fixed << std::setprecision(3) << "weapon " << delay << " ms = " << 1000.0 / delay
                    << " base APS"
                    << ", weapon IAS " << sheet->weaponIAS << "%, sheet IAS " << (*sheet)[Stat::AttackSpeed] << "%"
                    << (off ? " (dual wield)" : "") << " -> APS " << aps << " (primary recovery and animation-time scale)";
                // C7: an off-hand primary cast recovers at the off-hand's own speed.
                if (off && sheet->offhandAttacksPerSecond > 0)
                    out << ", off-hand APS " << HandAttacksPerSecond(player, 0, true) << " (off-hand primary recovery)";
                handler->SendSysMessage(out.str());
                LOG_INFO("server.loading", "[DC combat] {}", out.str());
                return true;
            }
        };
    } // namespace

    void RegisterCommandScripts()
    {
        new CombatCommand();
    }
} // namespace DC::Combat

/*
 * The Witch Doctor's passives that change how long a skill's effect or cooldown lasts. Tribal Rites shortens the
 * cooldown the core installed on six skills when one is cast; Creeping Death lengthens the debuffs of Haunt, Locust
 * Swarm and Piranhas, answered for the skills that ask.
 */

#include "dc_witch_doctor_skill_passives.h"
#include "dc_witch_doctor_passive_common.h"
#include "dc_witch_doctor_passive_rules.h"
#include "../../combat/dc_combat.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"

#include <array>

namespace DC::Combat::WitchDoctor::Passive::Skills
{
    namespace
    {
        // The skills Tribal Rites names (witch_doctor_passives.csv's tooltip).
        constexpr std::array<std::string_view, 6> TribalSkills = {
            "Hex", "Gargantuan", "Fetish Army", "Summon Zombie Dogs", "Big Bad Voodoo", "Mass Confusion"};

        // The cast of a Witch Doctor skill, after the core has taken the cost and installed the cooldown.
        class CastHook final : public PlayerScript
        {
        public:
            CastHook()
                : PlayerScript("dc_witch_doctor_skill_passives", {PLAYERHOOK_ON_SPELL_CAST})
            {
            }

            void OnPlayerSpellCast(Player* player, Spell* spell, bool) override
            {
                SpellInfo const* info = spell ? spell->GetSpellInfo() : nullptr;
                auto const* row = info ? Shells::FindAbility(info->Id) : nullptr;
                if (!row || spell->IsTriggered() || !Rules::Listed(TribalSkills, row->skill) ||
                    !On(player, "Tribal Rites"))
                    return;
                // "Reduce the cooldowns of the following skills by {cooldown_reduction_pct}": the cooldown the core
                // installed is shortened by the share.
                if (std::uint32_t const left = player->GetSpellCooldownDelay(info->Id))
                    if (std::uint32_t const cut =
                            Rules::CooldownCut(left, Num("Tribal Rites", "cooldown_reduction_pct")))
                        Combat::SendSkillCooldown(player, info->Id, left - cut);
            }
        };
    } // namespace

    double Lasting(Player* player, double baseSeconds)
    {
        return Rules::Lasting(On(player, "Creeping Death"), baseSeconds, Tune("creeping_death_seconds"));
    }

    void Register()
    {
        new CastHook();
    }
} // namespace DC::Combat::WitchDoctor::Passive::Skills

/*
 * The Witch Doctor's passives that change what a hit or a cast deals or costs: Pierce the Veil and Confidence Ritual. Each
 * is a multiplier of its own on a hit of a Witch Doctor skill, and the Mana Pierce the Veil adds to a cast is paid after
 * the core has charged the record's cost, so it cannot refuse a cast the Witch Doctor could not pay in full: it takes
 * what Mana is left.
 */

#include "dc_witch_doctor_damage_passives.h"
#include "dc_witch_doctor_passive_common.h"
#include "dc_witch_doctor_passive_rules.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

namespace DC::Combat::WitchDoctor::Passive::Damage
{
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!Shells::FindAbility(spellId))
            return;
        // "All of your damage is increased by {damage_bonus_pct}": every hit of a Witch Doctor skill.
        if (On(player, "Pierce the Veil"))
            AddFactor(out, "Pierce the Veil", Num("Pierce the Veil", "damage_bonus_pct"));
        // "You deal {damage_bonus_pct} additional damage to enemies within {radius_yards} yards": counted from the Witch
        // Doctor to the enemy, with the file's combat reach.
        if (target && On(player, "Confidence Ritual") &&
            Rules::Near(player->GetExactDist(target), Num("Confidence Ritual", "radius_yards"),
                        Tune("confidence_ritual_reach_yards")))
            AddFactor(out, "Confidence Ritual", Num("Confidence Ritual", "damage_bonus_pct"));
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        // "but your Mana costs are increased by {cost_increase_pct}": a skill that costs Mana pays that share more.
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info || !Shells::FindAbility(spellId) || info->PowerType != POWER_MANA || !On(player, "Pierce the Veil"))
            return;
        double const extra = Rules::ExtraCost(double(info->ManaCost), Num("Pierce the Veil", "cost_increase_pct"));
        if (extra > 0)
            Resources::SpendUnits(player, Resources::Mana,
                                  int32(std::lround(Resources::ToUnits(Resources::Mana, extra))));
    }
} // namespace DC::Combat::WitchDoctor::Passive::Damage

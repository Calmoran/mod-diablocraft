/*
 * World of DiabloCraft - the Demon Hunter's dispatch (dc_demon_hunter.h) and the Hatred its primaries generate.
 */

#include "dc_demon_hunter.h"
#include "dc_demon_hunter_bolas.h"
#include "dc_demon_hunter_caltrops.h"
#include "dc_demon_hunter_chakram.h"
#include "dc_demon_hunter_companion.h"
#include "dc_demon_hunter_cluster_arrow.h"
#include "dc_demon_hunter_elemental_arrow.h"
#include "dc_demon_hunter_entangling_shot.h"
#include "dc_demon_hunter_evasive_fire.h"
#include "dc_demon_hunter_fan_of_knives.h"
#include "dc_demon_hunter_grenade.h"
#include "dc_demon_hunter_hatred.h"
#include "dc_demon_hunter_passives.h"
#include "dc_demon_hunter_ranged_weapon.h"
#include "dc_demon_hunter_rain_of_vengeance.h"
#include "dc_demon_hunter_rapid_fire.h"
#include "dc_demon_hunter_sentry.h"
#include "dc_demon_hunter_shadow_power.h"
#include "dc_demon_hunter_smoke_screen.h"
#include "dc_demon_hunter_spike_trap.h"
#include "dc_demon_hunter_strafe.h"
#include "dc_demon_hunter_hungering_arrow.h"
#include "dc_demon_hunter_impale.h"
#include "dc_demon_hunter_multishot.h"
#include "dc_demon_hunter_vault.h"
#include "dc_demon_hunter_vengeance.h"
#include "dc_demon_hunter_preparation.h"
#include "dc_demon_hunter_marked_for_death.h"
#include "../dc_classes.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"

namespace DC::Combat::DemonHunter
{
    void Connected(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return;
        // "Generate: N Hatred": a skill states the number unqualified in demon_hunter_skill_values.csv and its runes
        // inherit it (the five primaries; a rune that raises it states its own). An item power that raises a skill's
        // resource generation multiplies the pay.
        auto const generated = Numbers::Get(spellId, "generated_resource");
        auto const* row = Shells::FindAbility(spellId);
        if (generated && row)
            Generate(player, Classes::ClassIdOf(player), spellId,
                     Passive::Generated(player, spellId, *generated) * ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") * ItemPowers::GenerationFactor(player));
        Vengeance::Attack(player, spellId);
        Passive::Attack(player, spellId);
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (auto arrow = HungeringArrow::BasePct(spellId))
            return arrow;
        if (auto shot = EntanglingShot::BasePct(spellId))
            return shot;
        if (auto bola = Bolas::BasePct(spellId))
            return bola;
        if (auto fire = EvasiveFire::BasePct(spellId))
            return fire;
        if (auto nade = Grenade::BasePct(spellId))
            return nade;
        if (auto knife = Impale::BasePct(spellId))
            return knife;
        if (auto disc = RapidFire::BasePct(spellId))
            return disc;
        if (auto ring = Chakram::BasePct(spellId))
            return ring;
        if (auto arrow = ElementalArrow::BasePct(spellId))
            return arrow;
        if (auto dash = Vault::BasePct(spellId))
            return dash;
        if (auto form = Vengeance::BasePct(spellId))
            return form;
        if (auto mark = MarkedForDeath::BasePct(spellId))
            return mark;
        if (auto laid = SpikeTrap::BasePct(spellId))
            return laid;
        if (auto turret = Sentry::BasePct(spellId))
            return turret;
        if (auto volley = Strafe::BasePct(spellId))
            return volley;
        if (auto salvo = Multishot::BasePct(spellId))
            return salvo;
        if (auto burst = ClusterArrow::BasePct(spellId))
            return burst;
        if (auto rain = RainOfVengeance::BasePct(spellId))
            return rain;
        if (auto pet = Companion::BasePct(spellId))
            return pet;
        return Caltrops::BasePct(spellId);
    }

    double CritBonus(Player* player, Unit* target, std::uint32_t spellId)
    {
        return Vault::CritBonus(spellId) + Multishot::CritBonus(target) + Passive::CritBonus(player, target);
    }

    void Fatal(Player* player, std::uint32_t& damage)
    {
        Passive::Fatal(player, damage);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        HungeringArrow::Landed(player, target, spellId, critical);
        EntanglingShot::Landed(player, target, spellId);
        Bolas::Landed(player, target, spellId);
        Grenade::Landed(player, target, spellId);
        Impale::Landed(player, target, spellId, critical);
        Chakram::Landed(player, target, spellId);
        ElementalArrow::Landed(player, target, spellId, critical);
        Passive::Landed(player, target, spellId, critical);
        MarkedForDeath::Landed(player, target, spellId);
        FanOfKnives::Landed(player, target, spellId);
        Strafe::Landed(player, target, spellId, critical);
        Multishot::Landed(player, target, spellId);
        ClusterArrow::Landed(player, target, spellId);
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        EvasiveFire::Casting(player, spellId);
        Passive::Cast(player, spellId);
        SpikeTrap::Casting(player, spellId);
    }

    bool Impact(Player* player, Unit* target, Unit* aimed, std::vector<ObjectGuid> const& cone, std::uint32_t spellId)
    {
        return EvasiveFire::Impact(player, target, aimed, cone, spellId) ||
               Impale::Impact(player, target, aimed, spellId) || EntanglingShot::Impact(player, target, aimed, spellId);
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        Grenade::Ground(player, spellId, center);
        Passive::Ground(player, spellId, center);
        Caltrops::Ground(player, spellId, center);
        SpikeTrap::Ground(player, spellId, center);
        Vault::Ground(player, spellId, center);
        ClusterArrow::Ground(player, spellId, center);
        RainOfVengeance::Ground(player, spellId, center);
    }

    void Aim(Player* player, std::uint32_t spellId, Position& center)
    {
        Grenade::Aim(player, spellId, center);
    }

    SpellCastResult CanCast(Player* player, std::uint32_t spellId)
    {
        // 'Requires Bow': a ranged weapon wielded, or the weapon the stock error names.
        if (!RangedWeapon::Permitted(player, spellId))
            return SPELL_FAILED_EQUIPPED_ITEM_CLASS_MAINHAND;
        // A channel whose start the module pays: the Hatred must be there.
        return RapidFire::Affordable(player, spellId) ? SPELL_CAST_OK : SPELL_FAILED_NO_POWER;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        RapidFire::Cast(player, spellId, targets);
        Chakram::Cast(player, spellId, targets);
        ElementalArrow::Cast(player, spellId, targets);
        Strafe::Cast(player, spellId, targets);
        Multishot::Cast(player, spellId, targets);
        SmokeScreen::Cast(player, spellId, targets);
        ShadowPower::Cast(player, spellId, targets);
        Vengeance::Cast(player, spellId);
        Preparation::Cast(player, spellId, targets);
        MarkedForDeath::Cast(player, spellId, targets);
        FanOfKnives::Cast(player, spellId, targets);
        Sentry::Cast(player, spellId);
        Companion::Cast(player, spellId, targets);
    }

    void BarWritten(Player* player, std::vector<Classes::Slot> const& bar)
    {
        Preparation::BarWritten(player, bar);
    }

    void RegisterScripts()
    {
        RapidFire::RegisterScripts();
        Chakram::RegisterScripts();
        ElementalArrow::RegisterScripts();
        Caltrops::RegisterScripts();
        Preparation::RegisterScripts();
        Vault::RegisterScripts();
        Vengeance::RegisterScripts();
        Passive::RegisterScripts();
        MarkedForDeath::RegisterScripts();
        Companion::RegisterScripts();
        Strafe::RegisterScripts();
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, Factors& out)
    {
        Vengeance::Multipliers(player, out);
        Passive::Multipliers(player, target, spellId, out);
        Grenade::Multipliers(player, target, spellId, out);
    }
} // namespace DC::Combat::DemonHunter

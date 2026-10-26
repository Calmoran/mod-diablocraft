#include "dc_wizard_slow_time.h"
#include "dc_wizard_buffs.h"
#include "../../combat/dc_item_powers.h"
#include "SpellAuraEffects.h"
#include "SpellScript.h"
#include <string_view>

namespace DC::Combat::Wizard::SlowTime
{
    using namespace Shared;

    namespace
    {
        // Crown of the Primus: "Slow Time gains the effect of every rune except Point of No Return and permanently follows
        // you". The follow records (generate_spells.py, kind slow_follow) are Slow Time's bubble worn by the Wizard: one per Slow Time record,
        // infinite, the bubble's size, the same two enemy effects and Stretch Time's ally effect on the party.
        bool IsFollow(Shells::Helper const& helper)
        {
            return std::string_view(helper.identity).ends_with(" - follow");
        }
    } // namespace

    bool Following(Unit const* unit)
    {
        for (auto const& helper : Shells::Helpers)
            if (IsFollow(helper) && unit->HasAura(helper.id))
                return true;
        return false;
    }

    void RemoveFollow(Player* player)
    {
        for (auto const& helper : Shells::Helpers)
            if (IsFollow(helper))
                player->RemoveAurasDueToSpell(helper.id);
    }

    // Whether `unit` stands in the follow aura of a Wizard to whom an item gives Slow Time's `rune` (the table's `rune` rows, ItemPowers::GrantsRune).
    bool GivenFollow(Unit const* unit, char const* rune)
    {
        if (unit)
            for (auto const& helper : Shells::Helpers)
                if (IsFollow(helper))
                    if (Aura const* aura = unit->GetAura(helper.id))
                        if (Unit* caster = aura->GetCaster();
                            caster && ItemPowers::GrantsRune(caster->ToPlayer(), "Slow Time", rune))
                            return true;
        return false;
    }

    namespace
    {
        // The record of one of Slow Time's runes, 0 if there is none.
        uint32 SlowTimeRune(std::string_view rune)
        {
            for (Row const& row : Shells::Abilities)
                if (IsSkill(row.id, "Slow Time") && rune == row.rune)
                    return row.id;
            return 0;
        }

        // Slow Time's bubbles and Archon form's Slow Time. The records hold
        // no amounts (the owner skill's sheet does), so the amounts are read
        // here: slow_pct:enemy for movement (Time Shell's own slow_pct in
        // its place), attack_speed_pct for the enemies' attacks, and Stretch
        // Time's own attack_speed_pct for the allies in the third slot.
        class dc_wizard_slow final : public AuraScript
        {
            PrepareAuraScript(dc_wizard_slow);

            uint32 Owner() const
            {
                uint32 const id = GetId();
                for (auto const& helper : Shells::Helpers)
                    if (helper.id == id && helper.owner)
                        return helper.owner;
                return id;
            }

            void Amount(AuraEffect const* effect, int32& amount, bool& canBeRecalculated)
            {
                canBeRecalculated = false;
                uint32 const owner = Owner();
                bool const stretch = IsRune(owner, "Stretch Time");
                switch (effect->GetAuraType())
                {
                    case SPELL_AURA_MOD_DECREASE_SPEED:
                    {
                        // Crown of the Primus gives Time Shell's stronger slow whichever rune is chosen.
                        uint32 slow = owner;
                        Unit* caster = GetCaster();
                        if (uint32 shell = SlowTimeRune("Time Shell");
                            shell && caster && ItemPowers::GrantsRune(caster->ToPlayer(), "Slow Time", "Time Shell"))
                            slow = shell;
                        amount = -int32(std::lround(Numbers::Own(slow, "slow_pct").value_or(Num(slow, "slow_pct", "enemy"))));
                        return;
                    }
                    case SPELL_AURA_MELEE_SLOW:
                        if (effect->GetEffIndex() == EFFECT_2)
                            // Allies: their attack speed is the D3 sheet's,
                            // which Wizard's Refresh raises; the WoW swing
                            // timer is left alone.
                            amount = 0;
                        else
                            amount =
                                -int32(std::lround(stretch ? Numbers::Inherited(owner, "attack_speed_pct").value_or(0)
                                                           : Num(owner, "attack_speed_pct")));
                        return;
                    default:
                        amount = 0;
                        return;
                }
            }

            // Point of No Return: "Enemies that enter or leave the Slow Time
            // area are stunned".
            void Entered(AuraEffect const*, AuraEffectHandleModes)
            {
                StunFor(false);
            }

            void Left(AuraEffect const*, AuraEffectHandleModes)
            {
                AuraApplication const* application = GetTargetApplication();
                StunFor(application && application->GetRemoveMode() == AURA_REMOVE_BY_EXPIRE);
            }

            void StunFor(bool expired)
            {
                uint32 const owner = Owner();
                Player* player = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
                Unit* target = GetUnitOwner();
                if (expired || !player || !target || target == player || !IsRune(owner, "Point of No Return") ||
                    !player->IsValidAttackTarget(target))
                    return;
                Stun(player, target, Num(owner, "stun_duration_seconds"));
            }

            void Ally(AuraEffect const*, AuraEffectHandleModes)
            {
                if (Player* player = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr)
                    Buffs::Refresh(player);
            }

            void Register() override
            {
                DoEffectCalcAmount += AuraEffectCalcAmountFn(dc_wizard_slow::Amount, EFFECT_ALL, SPELL_AURA_ANY);
                AfterEffectApply +=
                    AuraEffectApplyFn(dc_wizard_slow::Entered, EFFECT_0, SPELL_AURA_ANY, AURA_EFFECT_HANDLE_REAL);
                AfterEffectRemove +=
                    AuraEffectRemoveFn(dc_wizard_slow::Left, EFFECT_0, SPELL_AURA_ANY, AURA_EFFECT_HANDLE_REAL);
                // Only Stretch Time's bubble has a third aura effect (its allies);
                // on the others the core reports a mismatch for each hook (#64).
                if (HasAuraEffect(m_scriptSpellId, SPELL_AURA_ANY, EFFECT_2))
                {
                    AfterEffectApply +=
                        AuraEffectApplyFn(dc_wizard_slow::Ally, EFFECT_2, SPELL_AURA_ANY, AURA_EFFECT_HANDLE_REAL);
                    AfterEffectRemove +=
                        AuraEffectRemoveFn(dc_wizard_slow::Ally, EFFECT_2, SPELL_AURA_ANY, AURA_EFFECT_HANDLE_REAL);
                }
            }
        };
    } // namespace

    void Cast(Player* player, uint32 id, Position const& center)
    {
        // Crown of the Primus: the bubble follows the Wizard (an infinite aura on the Wizard, a recast replaces it)
        // and Time Shell's cooldown is the skill's whichever rune is chosen; every other cast drops the bubble
        // at the target.
        bool const follows = ItemPowers::SkillSetTo(player, "Slow Time", "follow_caster", 0) > 0;
        if (follows)
            RemoveFollow(player);
        for (auto const& helper : Shells::Helpers)
            if (helper.owner == id && IsFollow(helper) == follows)
            {
                if (follows)
                    player->CastSpell(player, helper.id, true);
                else
                    player->CastSpell(center.GetPositionX(), center.GetPositionY(), center.GetPositionZ(),
                                      helper.id, true);
            }
        if (uint32 shell = SlowTimeRune("Time Shell"); shell && !IsRune(id, "Time Shell") &&
                                                       ItemPowers::GrantsRune(player, "Slow Time", "Time Shell"))
            if (uint32 const ms = uint32(Numbers::Own(shell, "cooldown_seconds").value_or(0) * 1000))
                SendSkillCooldown(player, id, ReducedCooldownMilliseconds(player, id, ms));
    }

    void RegisterScripts()
    {
        RegisterSpellScript(dc_wizard_slow);
    }
} // namespace DC::Combat::Wizard::SlowTime

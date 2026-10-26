/*
 * The Crusader's dispatch: the seams the combat engine calls (dc_crusader.h), the Wrath its primaries generate, and the
 * hand-over to the file of each skill that needs code.
 */

#include "dc_crusader_common.h"
#include "dc_crusader_akarats_champion.h"
#include "dc_crusader_blessed_hammer.h"
#include "dc_crusader_bombardment.h"
#include "dc_crusader_blessed_shield.h"
#include "dc_crusader_condemn.h"
#include "dc_crusader_consecration.h"
#include "dc_crusader_block_share.h"
#include "dc_crusader_falling_sword.h"
#include "dc_crusader_fist_of_the_heavens.h"
#include "dc_crusader_heavens_fury.h"
#include "dc_crusader_iron_skin.h"
#include "dc_crusader_judgment.h"
#include "dc_crusader_justice.h"
#include "dc_crusader_laws.h"
#include "dc_crusader_laws_of_hope.h"
#include "dc_crusader_laws_of_justice.h"
#include "dc_crusader_laws_of_valor.h"
#include "dc_crusader_passives.h"
#include "dc_crusader_provoke.h"
#include "dc_crusader_phalanx.h"
#include "dc_crusader_punish.h"
#include "dc_crusader_shield_bash.h"
#include "dc_crusader_shield_glare.h"
#include "dc_crusader_slash.h"
#include "dc_crusader_steed_charge.h"
#include "dc_crusader_sweep_attack.h"
#include "dc_crusader_smite.h"
#include "../../combat/dc_item_powers.h"

#include "SpellAuraEffects.h"
#include "SpellMgr.h"

#include <algorithm>
#include <array>
#include <cmath>

namespace DC::Combat::Crusader
{
    namespace
    {
        // Stock "Ice Blast": one instant MOD_STUN effect, mechanic STUN - the hold the rift elites freeze a player with.
        constexpr std::uint32_t StunHold = 15878;
        // Stock "Dizzy" (9992): one MOD_CONFUSE effect, no other: the blind of an enemy (it wanders and does not attack).
        constexpr std::uint32_t BlindHold = 9992;
        // Stock "Fear" (5782): one MOD_FEAR effect, no other: an enemy Feared runs from the Crusader.
        constexpr std::uint32_t FearHold = 5782;
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, Snare mechanic; its amount is set to the slow.
        constexpr std::uint32_t SlowHold = 50259;
        // Stock "Earthgrab": one MOD_ROOT effect, mechanic Root - the Immobilize.
        constexpr std::uint32_t RootHold = 64695;
        // Stock "Challenging Shout" (1161, Provoke's donor): one MOD_TAUNT effect, no other: an enemy taunted attacks the Crusader.
        constexpr std::uint32_t TauntHold = 1161;
        // Stock "Slow" (10371): one MOD_MELEE_HASTE effect on an enemy; its amount is set to the attack speed it takes off.
        constexpr std::uint32_t WearyHold = 10371;

        // A stock control aura of `seconds` on `target`; control immunity answers nothing, and a second one restarts it.
        // True when the aura took hold.
        bool Hold(Player* player, Unit* target, std::uint32_t aura, double seconds, int amount = 0)
        {
            if (!player || !target || seconds <= 0 || !target->IsAlive())
                return false;
            target->RemoveAurasDueToSpell(aura, player->GetGUID());
            Aura* hold = player->AddAura(aura, target);
            if (!hold)
                return false;
            if (amount)
                if (AuraEffect* effect = hold->GetEffect(EFFECT_0))
                    effect->ChangeAmount(amount);
            hold->SetMaxDuration(int32(seconds * 1000));
            hold->SetDuration(int32(seconds * 1000));
            return true;
        }

        // The skills whose tooltip says "Requires Shield" (crusader_skills.csv; test_crusader_shield_bash reads the sheet).
        constexpr std::array<std::string_view, 4> NeedShield = {"Punish", "Shield Bash", "Blessed Shield", "Shield Glare"};

        bool RequiresShield(std::string_view skill)
        {
            return std::find(NeedShield.begin(), NeedShield.end(), skill) != NeedShield.end();
        }

        // The skills whose tooltip says "Requires Weapon" (crusader_skills.csv; test_crusader_sweep_attack reads the sheet).
        constexpr std::array<std::string_view, 1> NeedWeapon = {"Sweep Attack"};

        bool RequiresWeapon(std::string_view skill)
        {
            return std::find(NeedWeapon.begin(), NeedWeapon.end(), skill) != NeedWeapon.end();
        }

        bool ShieldWorn(Player* player)
        {
            Item const* offHand = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_OFFHAND);
            return offHand && offHand->GetTemplate()->InventoryType == INVTYPE_SHIELD;
        }

        constexpr Resources::Resource const& Wrath = *Resources::Find("Crusader", "wrath");

        // "Generate: N Wrath per attack": a skill states the number unqualified in crusader_skill_values.csv and its runes
        // inherit it; Provoke's qualified rows (its own code, through PayWrath) and the passives' bonuses are their own.
        void Generate(Player* player, std::uint32_t spellId)
        {
            if (auto const points = Numbers::Get(spellId, "generated_resource"))
                PayWrath(player, spellId, *points);
        }
    } // namespace

    // Wrath a skill generates: paid through the core's own energize, as every module-paid class power is. A power that
    // raises a skill's resource generation multiplies the pay.
    void PayWrath(Player* player, std::uint32_t spellId, double points)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!row || points <= 0 || Classes::ClassIdOf(player) != Wrath.classId || !Resources::Displayed(player, Wrath))
            return;
        Resources::Energize(player, Wrath, spellId,
                            points * ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") * ItemPowers::GenerationFactor(player));
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (auto punish = Punish::BasePct(spellId))
            return punish;
        if (auto smite = Smite::BasePct(spellId))
            return smite;
        if (auto bash = ShieldBash::BasePct(spellId))
            return bash;
        if (auto sweep = SweepAttack::BasePct(spellId))
            return sweep;
        if (auto hammer = BlessedHammer::BasePct(spellId))
            return hammer;
        if (auto shield = BlessedShield::BasePct(spellId))
            return shield;
        if (auto fist = FistOfTheHeavens::BasePct(spellId))
            return fist;
        if (auto glare = ShieldGlare::BasePct(spellId))
            return glare;
        if (auto skin = IronSkin::BasePct(spellId))
            return skin;
        if (auto ground = Consecration::BasePct(spellId))
            return ground;
        if (auto judgment = Judgment::BasePct(spellId))
            return judgment;
        if (auto provoke = Provoke::BasePct(spellId))
            return provoke;
        if (auto steed = SteedCharge::BasePct(spellId))
            return steed;
        if (auto condemn = Condemn::BasePct(spellId))
            return condemn;
        if (auto phalanx = Phalanx::BasePct(spellId))
            return phalanx;
        if (auto valor = LawsOfValor::BasePct(spellId))
            return valor;
        if (auto justice = LawsOfJustice::BasePct(spellId))
            return justice;
        if (auto hope = LawsOfHope::BasePct(spellId))
            return hope;
        if (auto sword = FallingSword::BasePct(spellId))
            return sword;
        if (auto champion = AkaratsChampion::BasePct(spellId))
            return champion;
        if (auto fury = HeavensFury::BasePct(spellId))
            return fury;
        if (auto bombardment = Bombardment::BasePct(spellId))
            return bombardment;
        return Justice::BasePct(spellId);
    }

    void Stun(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, StunHold, seconds);
    }

    void Root(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, RootHold, seconds);
    }

    void Blind(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, BlindHold, seconds);
    }

    void Unblind(Player* player, Unit* target)
    {
        if (player && target)
            target->RemoveAurasDueToSpell(BlindHold, player->GetGUID());
    }

    bool Fear(Player* player, Unit* target, double seconds)
    {
        return Hold(player, target, FearHold, seconds);
    }

    bool Taunt(Player* player, Unit* target, double seconds)
    {
        return Hold(player, target, TauntHold, seconds);
    }

    void Weary(Player* player, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
            Hold(player, target, WearyHold, seconds, -static_cast<int>(std::lround(pct)));
    }

    void Heal(Player* caster, Unit* target, std::uint32_t spellId, double amount)
    {
        if (!caster || !target || !target->IsAlive() || amount <= 0)
            return;
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
        {
            HealInfo heal(caster, target, uint32(std::min(amount, double(UINT32_MAX))), info, SPELL_SCHOOL_MASK_HOLY);
            caster->HealBySpell(heal);
        }
    }

    void GainWrath(Player* player, std::uint32_t spellId, double points)
    {
        if (player && points > 0 && Classes::ClassIdOf(player) == Wrath.classId && Resources::Displayed(player, Wrath))
            Resources::Energize(player, Wrath, spellId, points);
    }

    void Slow(Player* player, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
            Hold(player, target, SlowHold, seconds, -static_cast<int>(std::lround(pct)));
    }

    SpellCastResult CanCast(Player* player, std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (player && row && RequiresShield(row->skill) && !ShieldWorn(player))
            return SPELL_FAILED_EQUIPPED_ITEM_CLASS_OFFHAND;
        if (player && row && RequiresWeapon(row->skill) && !SweepAttack::WeaponWorn(player))
            return SPELL_FAILED_EQUIPPED_ITEM_CLASS_MAINHAND;
        return SPELL_CAST_OK;
    }

    void Connected(Player* player, std::uint32_t spellId, unsigned enemies)
    {
        if (!player)
            return;
        Generate(player, spellId);
        Punish::Connected(player, spellId);
        Slash::Connected(player, spellId, enemies);
        Passive::Connected(player, spellId);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        Slash::Cast(player, spellId, targets);
        Smite::Cast(player, spellId, targets);
        ShieldBash::Cast(player, spellId, targets);
        SweepAttack::Cast(player, spellId, targets);
        BlessedHammer::Cast(player, spellId, targets);
        ShieldGlare::Cast(player, spellId, targets);
        IronSkin::Cast(player, spellId);
        Consecration::Cast(player, spellId);
        Provoke::Cast(player, spellId, targets);
        SteedCharge::Cast(player, spellId);
        Condemn::Cast(player, spellId);
        Phalanx::Cast(player, spellId, targets);
        LawsOfValor::Cast(player, spellId, targets);
        LawsOfJustice::Cast(player, spellId, targets);
        LawsOfHope::Cast(player, spellId, targets);
        FallingSword::Cast(player, spellId, targets);
        AkaratsChampion::Cast(player, spellId);
    }

    double DodgeFactor(Unit const* unit)
    {
        return Passive::DodgeFactor(unit);
    }

    double AttackSpeed(Player* player, std::uint32_t spellId, double base)
    {
        return Passive::AttackSpeed(player, spellId, base);
    }

    void Approach(Player* player, std::uint32_t spellId, Unit* target)
    {
        ShieldBash::Approach(player, spellId, target);
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        BlockShare::Multipliers(player, spellId, out);
        Passive::Multipliers(player, spellId, out);
        AkaratsChampion::Multipliers(player, out);
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        FistOfTheHeavens::Ground(player, spellId, center);
        Judgment::Ground(player, spellId, center);
        Phalanx::Ground(player, spellId, center);
        FallingSword::Ground(player, spellId, center);
        HeavensFury::Ground(player, spellId, center);
        Bombardment::Ground(player, spellId, center);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        Justice::Landed(player, target, spellId);
        BlessedShield::Landed(player, target, spellId);
        Provoke::Landed(player, target, spellId);
        Passive::Landed(player, spellId);
        AkaratsChampion::Landed(player, target, spellId);
    }

    double CritBonus(Player* player, Unit* target, std::uint32_t spellId)
    {
        return Punish::CritBonus(player, spellId) + Slash::CritBonus(player, spellId) +
               Judgment::CritBonus(player, target) + Bombardment::CritBonus(spellId);
    }

    void Blocked(Unit* victim, Unit* attacker)
    {
        if (Player* player = victim ? victim->ToPlayer() : nullptr)
        {
            Punish::Blocked(player, attacker);
            Passive::Blocked(player);
        }
    }

    void Fatal(Player* player, std::uint32_t& damage)
    {
        AkaratsChampion::Fatal(player, damage);
    }

    void RegisterScripts()
    {
        Phalanx::RegisterScripts();
        LawsOfValor::Register();
        LawsOfJustice::Register();
        LawsOfHope::Register();
        Passive::Register();
        Laws::RegisterScripts();
    }

    double Redirect(Unit* victim, double damage)
    {
        return LawsOfJustice::Redirect(victim, damage);
    }

    void Taken(Unit* victim, Unit* attacker, double damage)
    {
        if (Player* player = victim ? victim->ToPlayer() : nullptr)
        {
            IronSkin::Taken(player);
            Condemn::Taken(player, damage);
            LawsOfJustice::Taken(player, attacker);
        }
    }
} // namespace DC::Combat::Crusader

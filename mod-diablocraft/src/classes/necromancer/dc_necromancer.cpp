/*
 * World of DiabloCraft - the Necromancer's class code: the dispatch to the file of each mechanic (dc_necromancer.h),
 * and the Essence its primaries generate.
 */

#include "dc_necromancer.h"
#include "dc_necromancer_army_of_the_dead.h"
#include "dc_necromancer_blood_rush.h"
#include "dc_necromancer_bone_armor.h"
#include "dc_necromancer_bone_spear.h"
#include "dc_necromancer_bone_spikes.h"
#include "dc_necromancer_bone_spirit.h"
#include "dc_necromancer_command_golem.h"
#include "dc_necromancer_command_skeletons.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_corpse_explosion.h"
#include "dc_necromancer_corpse_lance.h"
#include "dc_necromancer_corpses.h"
#include "dc_necromancer_death_nova.h"
#include "dc_necromancer_decrepify.h"
#include "dc_necromancer_devour.h"
#include "dc_necromancer_revive.h"
#include "dc_necromancer_frailty.h"
#include "dc_necromancer_grim_scythe.h"
#include "dc_necromancer_land_of_the_dead.h"
#include "dc_necromancer_leech.h"
#include "dc_necromancer_passives.h"
#include "dc_necromancer_grim_scythe_math.h"
#include "dc_necromancer_siphon_blood.h"
#include "dc_necromancer_simulacrum.h"
#include "dc_necromancer_skeletal_mage.h"

#include <algorithm>
#include <array>

namespace DC::Combat::Necromancer
{
    namespace
    {
        // The skills whose tooltip says "Generate: N Essence per enemy hit" (necromancer_skills.csv; the test reads the
        // sheet).
        constexpr std::array<std::string_view, 1> PaysPerEnemy = {"Grim Scythe"};

        // "Generate: N Essence": a skill states the number unqualified in necromancer_skill_values.csv and its runes
        // inherit it; a skill that says "per enemy hit" pays it for each enemy its cast hit.
        void Generate(Player* player, std::uint32_t spellId, unsigned enemies)
        {
            auto const points = BoneSpikes::GeneratedEssence(spellId) ? BoneSpikes::GeneratedEssence(spellId)
                                                                       : Numbers::Get(spellId, "generated_resource");
            // A channel pays on each of its own strikes, not for the cast.
            if (!points || SiphonBlood::PaysByStrike(spellId))
                return;
            auto const* row = Shells::FindAbility(spellId);
            bool const perEnemy = row && std::find(PaysPerEnemy.begin(), PaysPerEnemy.end(), row->skill) != PaysPerEnemy.end();
            PayEssence(player, spellId, perEnemy ? GrimScythe::EssenceOfHits(*points, enemies) : *points);
        }
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (auto spikes = BoneSpikes::BasePct(spellId))
            return spikes;
        if (auto blood = SiphonBlood::BasePct(spellId))
            return blood;
        if (auto mage = SkeletalMage::BasePct(spellId))
            return mage;
        if (auto nova = DeathNova::BasePct(spellId))
            return nova;
        if (auto skeletons = CommandSkeletons::BasePct(spellId))
            return skeletons;
        if (auto golem = CommandGolem::BasePct(spellId))
            return golem;
        if (auto army = ArmyOfTheDead::BasePct(spellId))
            return army;
        if (auto land = LandOfTheDead::BasePct(spellId))
            return land;
        if (auto curse = Decrepify::BasePct(spellId))
            return curse;
        if (auto leech = Leech::BasePct(spellId))
            return leech;
        if (auto frailty = Frailty::BasePct(spellId))
            return frailty;
        if (auto spirit = BoneSpirit::BasePct(spellId))
            return spirit;
        if (auto explosion = CorpseExplosion::BasePct(spellId))
            return explosion;
        return CorpseLance::BasePct(spellId);
    }

    void Connected(Player* player, std::uint32_t spellId, unsigned enemies)
    {
        if (player)
            Generate(player, spellId, enemies);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        BoneSpikes::Cast(player, spellId, targets);
        GrimScythe::Cast(player, spellId, targets);
        SiphonBlood::Cast(player, spellId, targets);
        SkeletalMage::Cast(player, spellId, targets);
        CommandSkeletons::Cast(player, spellId, targets);
        LandOfTheDead::Cast(player, spellId, targets);
        BoneArmor::Cast(player, spellId, targets);
        BoneSpirit::Cast(player, spellId, targets);
        BloodRush::Cast(player, spellId, targets);
        Simulacrum::Cast(player, spellId, targets);
        DeathNova::Cast(player, spellId, targets);
        Devour::Cast(player, spellId);
    }

    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Position const* aim, Unit* target)
    {
        if (SpellCastResult const refused = CorpseExplosion::CanCast(player, spellId, aim); refused != SPELL_CAST_OK)
            return refused;
        if (SpellCastResult const refused = CorpseLance::CanCast(player, spellId, target); refused != SPELL_CAST_OK)
            return refused;
        if (SpellCastResult const refused = Devour::CanCast(player, spellId); refused != SPELL_CAST_OK)
            return refused;
        if (SpellCastResult const refused = CommandGolem::CanCast(player, spellId, aim); refused != SPELL_CAST_OK)
            return refused;
        return CorpseRevive::CanCast(player, spellId, aim);
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        // A skill a copy repeats is a triggered cast: it costs nothing and opens nothing (no Secondary is a skill Rathma's Shield names).
        if (Simulacrum::Repeating())
            return;
        Passive::Casting(player, spellId);
        BoneSpear::Casting(player, spellId);
        CorpseLance::Casting(player, spellId);
        SkeletalMage::Casting(player, spellId);
        DeathNova::Casting(player, spellId);
        ArmyOfTheDead::Casting(player, spellId);
        BoneArmor::Casting(player, spellId);
        BoneSpirit::Casting(player, spellId);
        BloodRush::Casting(player, spellId);
        Simulacrum::Casting(player, spellId);
        Frailty::Casting(player, spellId);
    }

    bool Impact(Player* player, Unit* target, std::uint32_t spellId, unsigned index)
    {
        return BoneSpear::Impact(player, target, spellId, index) || CorpseLance::Impact(player, target, spellId, index);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        BoneSpear::Landed(player, target, spellId);
        CorpseLance::Landed(player, target, spellId);
        Decrepify::Landed(player, target, spellId);
        Leech::Landed(player, target, spellId);
        Passive::Landed(player, target, spellId);
    }

    double AttackSpeed(Player* player, std::uint32_t spellId, double base)
    {
        return Passive::AttackSpeed(player, spellId, base);
    }

    double Reduce(Unit* victim, double damage)
    {
        return Simulacrum::Reduce(victim, Passive::Reduce(victim, BoneArmor::Reduce(victim, CorpseRevive::Reduce(victim, damage))));
    }

    double CritBonus(Player* player, Unit* target)
    {
        return CorpseLance::CritBonus(player, target) + CommandGolem::CritBonus(player, target);
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        BoneSpear::Multipliers(player, spellId, out);
        BoneSpirit::Multipliers(player, spellId, out);
        Passive::Multipliers(player, target, spellId, out);
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        BoneSpikes::Ground(player, spellId, center);
        CommandGolem::Ground(player, spellId, center);
        Decrepify::Ground(player, spellId, center);
        Leech::Ground(player, spellId, center);
        Frailty::Ground(player, spellId, center);
        Simulacrum::Ground(player, spellId, center);
        BloodRush::Ground(player, spellId, center);
        ArmyOfTheDead::Ground(player, spellId, center);
        CorpseExplosion::Ground(player, spellId, center);
        CorpseRevive::Ground(player, spellId, center);
    }

    void RegisterScripts()
    {
        KillCorpses::RegisterScripts();
        SiphonBlood::RegisterScripts();
        Devour::RegisterScripts();
        LandOfTheDead::RegisterScripts();
        Decrepify::RegisterScripts();
        Leech::RegisterScripts();
        Frailty::RegisterScripts();
        BoneSpirit::RegisterScripts();
        Passive::Register();
        Simulacrum::RegisterScripts();
    }
} // namespace DC::Combat::Necromancer

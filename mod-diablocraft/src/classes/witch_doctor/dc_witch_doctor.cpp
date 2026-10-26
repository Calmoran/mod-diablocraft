/*
 * World of DiabloCraft - the Witch Doctor's dispatch (dc_witch_doctor.h) and the Mana its on-hit runes return.
 */

#include "dc_witch_doctor.h"
#include "dc_witch_doctor_acid_cloud.h"
#include "dc_witch_doctor_big_bad_voodoo.h"
#include "dc_witch_doctor_damage_passives.h"
#include "dc_witch_doctor_corpse_spiders.h"
#include "dc_witch_doctor_fetish_army.h"
#include "dc_witch_doctor_firebats.h"
#include "dc_witch_doctor_firebomb.h"
#include "dc_witch_doctor_hex.h"
#include "dc_witch_doctor_horrify.h"
#include "dc_witch_doctor_gargantuan.h"
#include "dc_witch_doctor_grasp_of_the_dead.h"
#include "dc_witch_doctor_haunt.h"
#include "dc_witch_doctor_locust_swarm.h"
#include "dc_witch_doctor_mass_confusion.h"
#include "dc_witch_doctor_mana.h"
#include "dc_witch_doctor_passives.h"
#include "dc_witch_doctor_mana_passives.h"
#include "dc_witch_doctor_pet_passives.h"
#include "dc_witch_doctor_piranhas.h"
#include "dc_witch_doctor_plague_of_toads.h"
#include "dc_witch_doctor_poison_dart.h"
#include "dc_witch_doctor_spirit_walk.h"
#include "dc_witch_doctor_skill_passives.h"
#include "dc_witch_doctor_spirit_barrage.h"
#include "dc_witch_doctor_survival_passives.h"
#include "dc_witch_doctor_wall_of_death.h"
#include "dc_witch_doctor_sacrifice.h"
#include "dc_witch_doctor_soul_harvest.h"
#include "dc_witch_doctor_zombie_charger.h"
#include "dc_witch_doctor_zombie_dogs.h"
#include "../dc_classes.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"

#include <algorithm>
#include <array>
#include <string_view>

namespace DC::Combat::WitchDoctor
{
    namespace
    {
        // The skills whose rune tooltip says "Gain N Mana every time it hits" (witch_doctor_runes.csv; the test reads
        // the sheet). The other gain_resource rows are paid by what they count (a horrified enemy, a sacrificed dog),
        // not by a hit.
        constexpr std::array<std::string_view, 4> PaysPerHit = {"Poison Dart", "Corpse Spiders", "Plague of Toads",
                                                                "Spirit Barrage"};
    } // namespace

    void Connected(Player* player, std::uint32_t spellId, unsigned enemies)
    {
        // Spirit Barrage pays for each of its own bolts as they land, not for the cast.
        if (!player || SpiritBarrage::Is(spellId))
            return;
        auto const perHit = Numbers::Get(spellId, "gain_resource");
        auto const* row = Shells::FindAbility(spellId);
        if (perHit && row && std::find(PaysPerHit.begin(), PaysPerHit.end(), row->skill) != PaysPerHit.end())
            Gain(player, Classes::ClassIdOf(player), spellId, *perHit * ItemPowers::GenerationFactor(player), enemies);
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (auto charge = ZombieCharger::BasePct(spellId))
            return charge;
        if (auto bolts = SpiritBarrage::BasePct(spellId))
            return bolts;
        if (auto cloud = AcidCloud::BasePct(spellId))
            return cloud;
        if (auto wall = WallOfDeath::BasePct(spellId))
            return wall;
        if (auto pool = Piranhas::BasePct(spellId))
            return pool;
        if (auto dart = PoisonDart::BasePct(spellId))
            return dart;
        if (auto jar = CorpseSpiders::BasePct(spellId))
            return jar;
        if (auto toads = PlagueOfToads::BasePct(spellId))
            return toads;
        if (auto fire = Firebomb::BasePct(spellId))
            return fire;
        if (auto grasp = GraspOfTheDead::BasePct(spellId))
            return grasp;
        if (auto bats = Firebats::BasePct(spellId))
            return bats;
        if (auto spirit = Haunt::BasePct(spellId))
            return spirit;
        if (auto swarm = LocustSwarm::BasePct(spellId))
            return swarm;
        if (auto soul = SoulHarvest::BasePct(spellId))
            return soul;
        if (auto mass = MassConfusion::BasePct(spellId))
            return mass;
        return Sacrifice::BasePct(spellId);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        PoisonDart::Landed(player, target, spellId);
        Passive::Landed(player, target, spellId);
        ZombieCharger::Landed(player, target, spellId);
        Passive::ManaOverTime::Landed(player, target, spellId);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        PoisonDart::Cast(player, spellId, targets);
        ZombieCharger::Cast(player, spellId, targets);
        SpiritBarrage::Cast(player, spellId, targets);
        Passive::Damage::Cast(player, spellId);
        Passive::ManaOverTime::Cast(player, spellId);
        ZombieDogs::Cast(player, spellId, targets);
        FetishArmy::Cast(player, spellId, targets);
        PlagueOfToads::Cast(player, spellId, targets);
        Firebomb::Cast(player, spellId, targets);
        Horrify::Cast(player, spellId);
        Firebats::Cast(player, spellId, targets);
        Haunt::Cast(player, spellId, targets);
        LocustSwarm::Cast(player, spellId, targets);
        SoulHarvest::Cast(player, spellId, targets);
        MassConfusion::Cast(player, spellId, targets);
        SpiritWalk::Cast(player, spellId);
    }

    double AttackSpeed(Player* /*player*/, std::uint32_t spellId, double base)
    {
        return PlagueOfToads::AttackSpeed(spellId, base);
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        CorpseSpiders::Ground(player, spellId, center);
        AcidCloud::Ground(player, spellId, center);
        WallOfDeath::Ground(player, spellId, center);
        Piranhas::Ground(player, spellId, center);
        GargantuanRunes::Ground(player, spellId, center);
        BigBadVoodoo::Ground(player, spellId, center);
        GraspOfTheDead::Ground(player, spellId, center);
        Sacrifice::Ground(player, spellId, center);
        Hex::Cast(player, spellId, center);
    }

    bool Toggle(Player* player, std::uint32_t spellId)
    {
        return Hex::Press(player, spellId);
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        Passive::Damage::Multipliers(player, target, spellId, out);
        BigBadVoodoo::Multipliers(player, out);
        Sacrifice::Multipliers(player, out);
    }

    double Reduce(Unit* victim, double damage)
    {
        return Passive::Survival::Reduce(victim, ZombieDogs::Reduce(victim, BigBadVoodoo::Reduce(victim, Passive::Reduce(victim, damage))));
    }

    void RegisterScripts()
    {
        Firebats::RegisterScripts();
        SpiritBarrage::RegisterScripts();
        Passive::Survival::Register();
        MassConfusion::RegisterScripts();
        BigBadVoodoo::RegisterScripts();
        FetishArmy::RegisterScripts();
        GraspOfTheDead::RegisterScripts();
        Passive::Pets::Register();
        Passive::Skills::Register();
        Hex::Register();
        SpiritWalk::Register();
        Passive::Register();
    }
} // namespace DC::Combat::WitchDoctor

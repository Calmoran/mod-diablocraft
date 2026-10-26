/*
 * The Wizard's mechanics, dispatched to the file of each skill or family (see dc_wizard.h and README.md in this folder).
 *
 * The stock carriers (generate_spells.py wizard_mechanics): the control helpers are MOD_STUN / MOD_DECREASE_SPEED / MOD_TAUNT records,
 * the shields SCHOOL_ABSORB, Slow Time's bubbles and Meteor's molten grounds persistent area auras, Teleport a LEAP, the Hydra a
 * totem SUMMON, the armors' reductions MOD_MELEE_DAMAGE_TAKEN_PCT and SPELLMOD_COST, Evocation a SPELLMOD_COOLDOWN. The mechanic files
 * decide when they go on, on whom, and with what amount: every amount is a sheet number read through Numbers, or a dc_ability_tuning
 * placeholder that fails closed at zero.
 */

#include "dc_wizard_internal.h"
#include "dc_wizard_arcane_orb.h"
#include "dc_wizard_armors.h"
#include "dc_wizard_auras.h"
#include "dc_wizard_black_hole.h"
#include "dc_wizard_energy_twister.h"
#include "dc_wizard_explosive_blast.h"
#include "dc_wizard_familiar.h"
#include "dc_wizard_frost_nova.h"
#include "dc_wizard_hydra.h"
#include "dc_wizard_magic_missile.h"
#include "dc_wizard_magic_weapon.h"
#include "dc_wizard_meteor.h"
#include "dc_wizard_mirror_image.h"
#include "dc_wizard_next_spell_bonus.h"
#include "dc_wizard_passives.h"
#include "dc_wizard_slow_time.h"
#include "dc_wizard_spectral_blade.h"
#include "dc_wizard_teleport.h"
#include "dc_wizard_upkeep.h"
#include <algorithm>
#include <mutex>
#include <string_view>

namespace DC::Combat::Wizard
{
    using namespace Shared;

    // --- the cast ---------------------------------------------------------------

    void Begin(Player* player, std::uint32_t spellId, Unit* explicitTarget)
    {
        if (!player)
            return;
        Passive::Prodigy(player, spellId);
        SpectralBlade::Begin(player, spellId);
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        Teleport::Begin(player, state, spellId);
        Passive::ArcaneDynamo(player, state, spellId);
        EnergyTwister::Begin(player, state, spellId, explicitTarget);
        if (IsRune(spellId, "Flame Ward"))
            state.flameWard = Now();
        Passive::IllusionistBegin(player, state, spellId);
        Familiar::Begin(player, state, spellId, explicitTarget);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Position const& center,
              Unit* /*explicitTarget*/)
    {
        if (!player)
            return;
        uint32 const id = spellId;
        if (EnergyTwister::Wanders(id))
            EnergyTwister::Start(player, id, center);
        else if (IsSkill(id, "Energy Twister"))
            EnergyTwister::Stay(player, id, center);
        if (IsSkill(id, "Frost Nova"))
            FrostNova::Cast(player, id, targets);
        if (IsSkill(id, "Slow Time"))
            SlowTime::Cast(player, id, center);
        if (IsSkill(id, "Teleport"))
            Teleport::Cast(player, id);
        if (Teleport::Travels(id))
            Teleport::FaceTravel(player, id);
        if (IsSkill(id, "Teleport") && IsRune(id, "Reversal"))
            Teleport::ReversalCast(player, id);
        // Frozen Solid: "Enemies caught in the Blizzard are Frozen for
        // {freeze_duration_seconds} seconds" - once, as it lands, over
        // Blizzard's own area (wizard.js:759 getTargets(12); :745 range 12),
        // not on every tick.
        if (IsRune(id, "Frozen Solid"))
            for (Unit* target : Combat::Enemies(player, id, center, Num(id, "radius_yards")))
                Freeze(player, target, Num(id, "freeze_duration_seconds"));
        if (IsSkill(id, "Mirror Image"))
            MirrorImage::SummonImages(player, id);
        if (IsRune(id, "Scorch"))
            ArcaneOrb::Cast(player, center);
        if (IsSkill(id, "Black Hole"))
            BlackHole::Cast(player, id, targets, center);
        MagicWeapon::Cast(player, targets);
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        if (state.empowered == id && !IsSkill(id, "Ray of Frost") && !IsSkill(id, "Arcane Torrent") &&
            !IsSkill(id, "Disintegrate"))
            state.empowered = 0;
        NextSpellBonus::Cast(state, id, targets);
        EnergyTwister::Cast(state, id);
    }

    bool Delayed(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player)
            return false;
        uint32 const id = spellId;
        bool dynamo = false;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = StateOf(player);
            dynamo = state.empowered == id;
            if (dynamo)
                state.empowered = 0;
        }
        if (IsSkill(id, "Meteor"))
            return Meteor::Delayed(player, id, center, dynamo);
        if (IsSkill(id, "Explosive Blast"))
            return ExplosiveBlast::Delayed(player, id, dynamo);
        return false;
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId, Hit const& hit, bool periodic)
    {
        if (!player || !target || !target->IsAlive())
            return;
        uint32 const id = spellId;
        uint64 const now = Now();
        std::string_view const element = ElementOf(hit.school);
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            Marks& marks = StateOf(player).marks[target->GetGUID().GetRawValue()];
            if (uint32 p = PassiveId("Conflagration"); p && element == "fire" && Has(player, "Conflagration"))
                marks.conflagration = now + uint64(Num(p, "duration_seconds") * 1000);
            if (uint32 p = PassiveId("Elemental Exposure"); p && !element.empty() && Has(player, "Elemental Exposure"))
                marks.exposure[hit.school] = now + uint64(Num(p, "duration_seconds") * 1000);
            // Snow Blast (Cold), Intensify (Arcane), Gale Force (Fire):
            // "Enemies hit take {damage_taken_pct} increased damage from X".
            unsigned school = 0;
            if (IsRune(id, "Snow Blast"))
                school = SPELL_SCHOOL_MASK_FROST;
            else if (IsRune(id, "Intensify"))
                school = SPELL_SCHOOL_MASK_ARCANE;
            else if (IsRune(id, "Gale Force"))
                school = SPELL_SCHOOL_MASK_FIRE;
            if (school)
                marks.schoolTaken[school] = {now + uint64(Num(id, "duration_seconds") * 1000),
                                             Num(id, "damage_taken_pct")};
        }
        if (element == "fire" && !IsRune(id, "Conflagrate"))
            MagicMissile::RefreshBurn(player, target);
        if (uint32 p = PassiveId("Temporal Flux"); p && element == "arcane" && Has(player, "Temporal Flux"))
            Slow(player, target, Num(p, "slow_pct"), Num(p, "slow_duration_seconds"));
        if (IsRune(id, "Debilitating Force"))
            Weaken(target, id, Num(id, "enemy_damage_pct"), Num(id, "duration_seconds"));
        // The chances on hit, each scaled by this hit's proc coefficient
        // (d3planner's onhit_proc, damage.js:145, fires only when it is
        // non-zero). A DoT tick is a hit here: it carries its cast's proc.
        if (double const proc = ProcOf(id); proc > 0)
        {
            ObjectGuid const guid = target->GetGUID();
            // Paralysis: "Lightning damage has a {proc_chance_pct} chance to
            // Stun the target for {stun_duration_seconds} seconds": 15% x proc
            // for 90 frames on a lightning hit (wizard.js:1242-1244,
            // cast.js:568-572).
            if (uint32 p = PassiveId("Paralysis");
                p && element == "lightning" && Has(player, "Paralysis") && Roll() < Num(p, "proc_chance_pct") * proc)
                Stun(player, target, Num(p, "stun_duration_seconds"));
            Armors::ShockingAspect(player, guid, hit, proc);
            MagicWeapon::Ignite(player, guid, proc);
        }
        if (periodic)
            return;
        if (IsRune(id, "Flame Blades"))
            SpectralBlade::FlameBlade(player, id);

        // The skill's own control on a hit.
        bool const handled = IsSkill(id, "Frost Nova") || IsRune(id, "Ice Reflect") || IsRune(id, "Comet") ||
                             IsRune(id, "Arcane Mines") || IsSkill(id, "Archon") || IsRune(id, "Frozen Solid") ||
                             IsRune(id, "Ice Blades");
        if (IsRune(id, "Ice Blades"))
            SpectralBlade::IceBlades(player, target, id);
        if (!handled && Numbers::Has(id, "freeze_duration_seconds"))
        {
            bool fire = !Numbers::Has(id, "proc_chance_pct") || Roll() < Num(id, "proc_chance_pct");
            // Glacial Spike: "Enemies cannot be Frozen by Glacial Spike more
            // than once every {internal_cooldown_seconds} seconds".
            if (fire && IsRune(id, "Glacial Spike"))
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                Marks& marks = StateOf(player).marks[target->GetGUID().GetRawValue()];
                fire = marks.glacialSpike <= now;
                if (fire)
                    marks.glacialSpike = now + uint64(Num(id, "internal_cooldown_seconds") * 1000);
            }
            if (fire)
                Freeze(player, target, Num(id, "freeze_duration_seconds"));
        }
        if (!handled && !IsRune(id, "Point of No Return") && !IsRune(id, "Mocking Demise") &&
            Numbers::Has(id, "stun_duration_seconds"))
            Stun(player, target, Num(id, "stun_duration_seconds"));
        if (!handled && Numbers::Has(id, "slow_pct") && Numbers::Has(id, "slow_duration_seconds"))
            Slow(player, target, Num(id, "slow_pct"), Num(id, "slow_duration_seconds"));
        // Archon - Slow Time: "your Arcane Blast and Arcane Strike abilities
        // Freeze enemies for {freeze_duration_seconds} second".
        if (char const* name = ArchonAbilityName(id))
            if (uint32 form = BuffOf(player, "Archon");
                form && IsRune(form, "Slow Time") &&
                (std::string_view(name) == "Arcane Strike" || std::string_view(name) == "Arcane Blast"))
                Freeze(player, target, Num(form, "freeze_duration_seconds"));
    }

    std::uint32_t GroundSource(std::uint32_t spellId)
    {
        for (auto const& helper : Shells::Helpers)
            if (helper.id == spellId && helper.owner)
                return helper.owner;
        return spellId;
    }

    // --- the defence ----------------------------------------------------------

    double IncomingFactor(Unit* attacker)
    {
        if (!attacker)
            return 1.0;
        double factor = 1.0;
        if (uint32 exhaustion = Shells::HelperFor("Slow Time - Exhaustion - bubble");
            (exhaustion && attacker->HasAura(exhaustion)) || SlowTime::GivenFollow(attacker, "Exhaustion"))
            for (Row const& row : Shells::Abilities)
                if (IsSkill(row.id, "Slow Time") && IsRune(row.id, "Exhaustion"))
                    factor *= 1 - Num(row.id, "enemy_damage_pct") / 100;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto found = weakened.find(attacker->GetGUID().GetRawValue());
        if (found == weakened.end())
            return factor;
        uint64 const now = Now();
        for (auto const& [source, debuff] : found->second)
            if (debuff.until > now)
                factor *= 1 - debuff.value / 100;
        return std::max(0.0, factor);
    }

    void Incoming(Player* victim, Unit* attacker, std::uint32_t& damage, Attack kind)
    {
        if (!victim || victim->getClass() != CLASS_MAGE || !damage)
            return;
        double const maxLife = victim->GetMaxHealth();
        uint64 const now = Now();
        Armors::ForceArmor(victim, maxLife, damage);
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = StateOf(victim);
            if (Familiar::Guardian(victim, state, now, damage))
                return;
            if (Passive::UnstableAnomaly(victim, state, now, damage))
                return;
            state.lastDamaged = now;
            Passive::Illusionist(victim, state, now, maxLife, damage);
        }
        if (attacker)
            Armors::ArmorsHit(victim, attacker, kind);
    }

    void RegisterScripts()
    {
        Auras::RegisterScripts();
        SlowTime::RegisterScripts();
        MirrorImage::RegisterScripts();
        Familiar::RegisterScripts();
        Hydra::RegisterScripts();
        Upkeep::RegisterScripts();
    }
} // namespace DC::Combat::Wizard

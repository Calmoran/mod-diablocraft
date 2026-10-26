#include "dc_wizard_internal.h"
#include "dc_wizard_familiar.h"
#include "dc_wizard_slow_time.h"
#include "dc_wizard_spectral_blade.h"
#include "SpellMgr.h"
#include <algorithm>

namespace DC::Combat::Wizard
{
    using namespace Shared;

    double DamageBonus(Player* player, Unit* /*target*/, std::uint32_t spellId)
    {
        if (!player)
            return 0;
        double bonus = 0;
        if (uint32 id = BuffOf(player, "Magic Weapon"))
            bonus += Num(id, "damage_bonus_pct");
        if (uint32 id = BuffOf(player, "Familiar"); id && IsRune(id, "Sparkflint") && Familiar::FamiliarOf(player))
            bonus += Num(id, "damage_bonus_pct");
        if (uint32 id = PassiveId("Glass Cannon"); id && Has(player, "Glass Cannon"))
            bonus += Num(id, "damage_bonus_pct");
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        if (uint32 id = PassiveId("Unwavering Will");
            id && Has(player, "Unwavering Will") && state.still >= Num(id, "duration_seconds") * 1000)
            bonus += Num(id, "damage_bonus_pct");
        uint64 const now = Now();
        for (Expiring const& stack : state.spellsteal)
            if (stack.until > now)
                bonus += stack.value;
        return bonus;
    }

    double TargetBonus(Player* player, Unit* target, unsigned school)
    {
        if (!player || !target)
            return 0;
        double bonus = 0;
        // Blizzard - Lightning Storm: "Enemies affected by Blizzard take
        // {damage_taken_pct} increased damage from Lightning" - the ground
        // is the rune's own record.
        if (school == SPELL_SCHOOL_MASK_NATURE)
            for (Row const& row : Shells::Abilities)
                if (IsSkill(row.id, "Blizzard") && IsRune(row.id, "Lightning Storm") && target->HasAura(row.id))
                    bonus += Num(row.id, "damage_taken_pct");
        if (uint32 warp = Shells::HelperFor("Slow Time - Time Warp - bubble");
            (warp && target->HasAura(warp)) || SlowTime::GivenFollow(target, "Time Warp"))
            for (Row const& row : Shells::Abilities)
                if (IsSkill(row.id, "Slow Time") && IsRune(row.id, "Time Warp"))
                    bonus += Num(row.id, "damage_taken_pct");
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        auto found = state.marks.find(target->GetGUID().GetRawValue());
        if (found == state.marks.end())
            return bonus;
        Marks const& marks = found->second;
        uint64 const now = Now();
        // Bone Chill: "Enemies take more damage while frozen or chilled by
        // Frost Nova".
        if (marks.boneChill > now && Frozen(player, target))
            for (Row const& row : Shells::Abilities)
                if (IsSkill(row.id, "Frost Nova") && IsRune(row.id, "Bone Chill"))
                    bonus += Num(row.id, "damage_taken_pct");
        if (auto taken = marks.schoolTaken.find(school); taken != marks.schoolTaken.end() && taken->second.until > now)
            bonus += taken->second.value;
        if (uint32 id = PassiveId("Cold Blooded");
            id && Has(player, "Cold Blooded") && (Frozen(player, target) || Chilled(player, target)))
            bonus += Num(id, "damage_taken_pct");
        return bonus;
    }

    double ElementalBonus(Player* player, unsigned school)
    {
        if (!player)
            return 0;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        double bonus = 0;
        uint64 const now = Now();
        if (school == SPELL_SCHOOL_MASK_FROST)
            for (Expiring const& stack : state.absoluteZero)
                if (stack.until > now)
                    bonus += stack.value;
        if (school == SPELL_SCHOOL_MASK_FIRE)
            SpectralBlade::FlameBladesBonus(player, bonus);
        return bonus;
    }

    double Standalone(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player)
            return 1.0;
        double factor = 1.0;
        // Archon: dmgmul 30 in the form's buff, dmgmul 6 a kill in its own
        // stacking buff (wizard.js:1010, :1024) - two multipliers.
        if (uint32 form = BuffOf(player, "Archon"))
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            factor *= 1 + Num(form, "damage_bonus_pct", "form") / 100;
            factor *= 1 + Num(form, "damage_bonus_pct", "kill") * StateOf(player).archonStacks / 100;
        }
        if (target)
        {
            double const distance = player->GetDistance(target);
            if (uint32 id = PassiveId("Power Hungry");
                id && Has(player, "Power Hungry") && distance > Num(id, "radius_yards"))
                factor *= 1 + Num(id, "damage_bonus_pct") / 100;
            if (uint32 id = PassiveId("Audacity"); id && Has(player, "Audacity") && distance <= Num(id, "radius_yards"))
                factor *= 1 + Num(id, "damage_bonus_pct") / 100;
        }
        if (uint32 id = PassiveId("Arcane Dynamo"); id && Has(player, "Arcane Dynamo"))
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State const& state = StateOf(player);
            if (state.empowered == spellId || state.empoweredNow == spellId)
                factor *= 1 + Num(id, "damage_bonus_pct") / 100;
        }
        return factor;
    }

    double CritBonus(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target)
            return 0;
        double bonus = 0;
        // Ice Blades: "Frozen enemies have a {crit_taken_pct} increased
        // chance to be critically hit by Spectral Blade" (wizard.js:105).
        if (IsRune(spellId, "Ice Blades") && Frozen(player, target))
            bonus += Num(spellId, "crit_taken_pct");
        uint32 const id = PassiveId("Conflagration");
        if (!id || !Has(player, "Conflagration"))
            return bonus;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        auto found = state.marks.find(target->GetGUID().GetRawValue());
        return bonus +
               (found != state.marks.end() && found->second.conflagration > Now() ? Num(id, "crit_taken_pct") : 0);
    }

    bool ChilledBy(Player* player, Unit* target)
    {
        return player && target && Chilled(player, target);
    }
} // namespace DC::Combat::Wizard

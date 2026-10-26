#pragma once
/*
 * The readers of the class-resource and monster-type affix stats on the sheet (Stat::ResourceOnCrit .. DamageVsHuman):
 * the arithmetic of what each stat does, with no core include, so tests/stat_readers compiles this exact code. The game
 * paths that call it: Combat::CriticalResource (apoc), Stats::FurySpent (lifefury), the resource pulse (spiritregen,
 * manaregen) and Combat::ComputeHit's step 6 (damage to a creature type).
 */
#include "../common/dc_common.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>

namespace DC::Stats::Readers
{
    // Life for Fury spent: d3planner's lifefury, "Gain N Life per Fury Spent" (data_stats.js:99), N flat Life for each
    // Fury point the cast took.
    inline double LifeForFurySpent(StatSheet const& sheet, double furySpent)
    {
        return furySpent > 0 ? furySpent * sheet[Stat::LifePerFury] : 0.0;
    }

    // Whole points of Arcane Power one critical hit pays, with the remainder carried to the next. D3 pays apoc scaled
    // by the proc coefficient of the skill that crit (d3planner simulator/wizard.js:1314-1322: targets x proc x chc x
    // apoc); a hit whose spell states no coefficient pays nothing, as every proc here (dc_proc_math.h).
    inline std::uint32_t CritResource(StatSheet const& sheet, std::optional<double> procCoefficient, double& carry)
    {
        double const perCrit = sheet[Stat::ResourceOnCrit];
        if (perCrit <= 0 || !procCoefficient || *procCoefficient <= 0)
            return 0;
        carry += perCrit * *procCoefficient;
        double const whole = std::floor(carry);
        carry -= whole;
        return static_cast<std::uint32_t>(whole);
    }

    // The creature kinds D3 gives a damage-to-type stat. Beast, Demon and Undead are the creature template's type; Human
    // is a roster monster D3 types as Human (data/d3/gr_monster_progress.csv), since 3.3.5's Humanoid also holds orcs,
    // trolls and murlocs.
    enum class MonsterKind
    {
        Other,
        Beast,
        Demon,
        Undead,
        Human
    };

    // Percent damage dealt to a creature of this kind.
    inline double DamageVsKind(StatSheet const& sheet, MonsterKind kind)
    {
        switch (kind)
        {
            case MonsterKind::Beast:
                return sheet[Stat::DamageVsBeast];
            case MonsterKind::Demon:
                return sheet[Stat::DamageVsDemon];
            case MonsterKind::Undead:
                return sheet[Stat::DamageVsUndead];
            case MonsterKind::Human:
                return sheet[Stat::DamageVsHuman];
            default:
                return 0.0;
        }
    }

    // The step 6 multiplier for the kind: 1 + the sheet's percent (damage_formula.csv step 6: Multiplier_Type).
    inline double MonsterTypeFactor(StatSheet const& sheet, MonsterKind kind)
    {
        return 1.0 + DamageVsKind(sheet, kind) / 100.0;
    }

    // The sheet stat that adds points a second to the class resource with this registry key (class_resources.csv
    // resource_key), none for a resource no affix regenerates.
    inline std::optional<Stat> RegenStatOf(std::string_view resourceKey)
    {
        if (resourceKey == "spirit")
            return Stat::SpiritRegen;
        if (resourceKey == "mana")
            return Stat::ManaRegen;
        return std::nullopt;
    }

    // Points a second the sheet adds to the resource with this key, on top of the class's own regeneration.
    inline double RegenPerSecond(StatSheet const& sheet, std::string_view resourceKey)
    {
        auto const stat = RegenStatOf(resourceKey);
        return stat ? sheet[*stat] : 0.0;
    }
} // namespace DC::Stats::Readers

#pragma once
// The rules of Grim Scythe's runes that need no core type, header-only so tests/necromancer_grim_scythe compiles this
// exact code: which rune is which, the Essence an enemy hit pays, Blood Scythe's heal for the enemies hit, Execution's
// decapitation and the point Dual Scythes draws an enemy to. The production half is dc_necromancer_grim_scythe.cpp.
#include <algorithm>
#include <string_view>

namespace DC::Combat::Necromancer::GrimScythe
{
    enum class Rune
    {
        None,
        BloodScythe,
        Execution,
        FrostScythe,
        DualScythes,
        CursedScythe
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Blood Scythe")
            return Rune::BloodScythe;
        if (name == "Execution")
            return Rune::Execution;
        if (name == "Frost Scythe")
            return Rune::FrostScythe;
        if (name == "Dual Scythes")
            return Rune::DualScythes;
        if (name == "Cursed Scythe")
            return Rune::CursedScythe;
        return Rune::None;
    }

    // "Generate: {generated_resource} Essence per enemy hit": the Essence of a cast that hit `enemies` enemies.
    inline double EssenceOfHits(double perEnemy, unsigned enemies)
    {
        return perEnemy > 0 ? perEnemy * enemies : 0.0;
    }

    // "Heal for {heal_pct} of your health per enemy hit": the Life of a cast that hit `enemies` enemies.
    inline double HealOfHits(double maxLife, double healPct, unsigned enemies)
    {
        return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 * enemies : 0.0;
    }

    // "Enemies below {life_threshold_pct} health have a {proc_chance_pct} chance to be decapitated": an enemy with
    // `lifePct` percent of its Life left is, for a roll of `roll` (0 to 100).
    inline bool Decapitated(double lifePct, double thresholdPct, double roll, double chancePct)
    {
        return thresholdPct > 0 && chancePct > 0 && lifePct < thresholdPct && roll < chancePct;
    }

    // "push enemies together": where an enemy at (ex, ey) is drawn to, the point on the line the Necromancer faces
    // ((fx, fy) a unit direction) level with it. The distance along the line, never behind the Necromancer.
    inline double LevelWith(double px, double py, double fx, double fy, double ex, double ey)
    {
        return std::max(0.0, (ex - px) * fx + (ey - py) * fy);
    }
} // namespace DC::Combat::Necromancer::GrimScythe

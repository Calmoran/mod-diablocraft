#pragma once
// The rules of Skeletal Mage's runes that need no core type, header-only so tests/necromancer_skeletal_mage compiles
// this exact code: which rune is which, what Singularity's Essence is worth and how much it takes, the mage's time with
// Life Support, and the range an Archer shoots from. The production half is dc_necromancer_skeletal_mage.cpp, and the
// mage itself is dc_necromancer_pets.cpp on the shared minions.
#include <algorithm>
#include <string_view>

namespace DC::Combat::Necromancer::SkeletalMage
{
    enum class Rune
    {
        None,
        GiftOfDeath,
        Singularity,
        LifeSupport,
        Contamination,
        SkeletonArcher
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Gift of Death")
            return Rune::GiftOfDeath;
        if (name == "Singularity")
            return Rune::Singularity;
        if (name == "Life Support")
            return Rune::LifeSupport;
        if (name == "Contamination")
            return Rune::Contamination;
        if (name == "Skeleton Archer")
            return Rune::SkeletonArcher;
        return Rune::None;
    }

    // "The minion's damage is increased by {damage_bonus_pct} for every point of Essence consumed": the bonus of a mage
    // raised with `points` of Essence.
    inline double SingularityBonusPct(double perPoint, double points)
    {
        return perPoint > 0 && points > 0 ? perPoint * points : 0.0;
    }

    // "Consumes all Essence": what the module takes besides the cost the core takes, of a pool of `points` and a cost
    // of `cost`. The cost itself is the core's.
    inline double EssenceBeyondCost(double points, double cost)
    {
        return std::max(0.0, points - std::max(0.0, cost));
    }

    // "Dist between Player and Target % (0 - 1)": the point a `share` of the way from `from` to `to`, the share held to the
    // way itself.
    inline double Along(double from, double to, double share)
    {
        return from + (to - from) * std::clamp(share, 0.0, 1.0);
    }

    // "last an additional {duration_seconds} seconds": the mage's time, the skill's seconds and Life Support's more.
    inline double LifeSeconds(double baseSeconds, double extraSeconds, bool lifeSupport)
    {
        return std::max(0.0, baseSeconds) + (lifeSupport ? std::max(0.0, extraSeconds) : 0.0);
    }
} // namespace DC::Combat::Necromancer::SkeletalMage

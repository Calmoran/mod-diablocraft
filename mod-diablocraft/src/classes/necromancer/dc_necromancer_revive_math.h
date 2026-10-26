#pragma once
// The rules of Revive's runes that need no core type, header-only so tests/necromancer_revive compiles this exact code:
// which rune is which, the look a corpse gives, Personal Army's reduction, Horrific Return's fear and how many corpses
// a cast revives. The production half is dc_necromancer_revive.cpp; the corpses are the shared combat/dc_corpses_math.h
// and the minions dc_necromancer_pets.cpp on the shared combat/dc_minions.
#include <algorithm>
#include <cstddef>
#include <string_view>

namespace DC::Combat::Necromancer::CorpseRevive
{
    enum class Rune
    {
        None,
        Purgatory,
        Oblation,
        PersonalArmy,
        Recklessness,
        HorrificReturn
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Purgatory")
            return Rune::Purgatory;
        if (name == "Oblation")
            return Rune::Oblation;
        if (name == "Personal Army")
            return Rune::PersonalArmy;
        if (name == "Recklessness")
            return Rune::Recklessness;
        if (name == "Horrific Return")
            return Rune::HorrificReturn;
        return Rune::None;
    }

    // "Damage taken is reduced by {damage_reduction_pct} for each revived minion active": the share of a hit that still
    // lands with `active` minions standing, never below nothing.
    inline double TakenFactor(double reductionPerMinionPct, unsigned active)
    {
        if (reductionPerMinionPct <= 0)
            return 1.0;
        return std::max(0.0, 1.0 - reductionPerMinionPct * active / 100.0);
    }

    // "reviving up to {target_count} corpses": how many of `lying` corpses a cast revives. At the most a cast may.
    inline std::size_t Revived(std::size_t lying, double targetCount)
    {
        return targetCount > 0 ? std::min(lying, std::size_t(targetCount)) : 0;
    }

    // Whether a corpse-less cast may begin: at least one corpse lies within reach.
    inline bool CanRevive(std::size_t lyingNearThePoint)
    {
        return lyingNearThePoint > 0;
    }

    // "Health Cost Per Target": the share of maximum Life a cast that revived `corpses` corpses costs, `perCorpsePct` each.
    inline double LifeCostPct(double perCorpsePct, std::size_t corpses)
    {
        return perCorpsePct > 0 ? perCorpsePct * double(corpses) : 0.0;
    }

    // The runes whose minions are stronger: Oblation and Recklessness state a damage bonus.
    inline bool RaisesDamage(Rune rune)
    {
        return rune == Rune::Oblation || rune == Rune::Recklessness;
    }
} // namespace DC::Combat::Necromancer::CorpseRevive

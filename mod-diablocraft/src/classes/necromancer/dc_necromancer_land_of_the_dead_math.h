#pragma once
// The rules of Land of the Dead's runes that need no core type, header-only so tests/necromancer_land_of_the_dead compiles this
// exact code: which rune is which, which kill extends Shallow Graves and by how much, how much of a plague tick fits under
// Plaguelands' maximum, and what a kill heals. The production half is dc_necromancer_land_of_the_dead.cpp.
#include <algorithm>
#include <string_view>

namespace DC::Combat::Necromancer::LandOfTheDead
{
    enum class Rune
    {
        None,
        Invigoration,
        FrozenLands,
        Plaguelands,
        LandOfPlenty,
        ShallowGraves
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Invigoration")
            return Rune::Invigoration;
        if (name == "Frozen Lands")
            return Rune::FrozenLands;
        if (name == "Plaguelands")
            return Rune::Plaguelands;
        if (name == "Land of Plenty")
            return Rune::LandOfPlenty;
        if (name == "Shallow Graves")
            return Rune::ShallowGraves;
        return Rune::None;
    }

    // Shallow Graves: "Every {trigger_count} enemies killed extends the duration": whether the `kills`th kill of the land is one that
    // does. No trigger count, no extension.
    inline bool ExtendsOn(unsigned kills, unsigned triggerCount)
    {
        return triggerCount > 0 && kills > 0 && kills % triggerCount == 0;
    }

    // The extension a kill gives, in the same unit as its arguments: a step, held to what is left of the most the land may be
    // extended in all.
    inline double ExtensionFor(double extendedSoFar, double step, double most)
    {
        return std::max(0.0, std::min(step, most - extendedSoFar));
    }

    // Plaguelands: of a tick of `tickPct` weapon damage, what fits under the `maxPct` an enemy may take in all, having taken
    // `dealtPct`.
    inline double PlagueTick(double dealtPct, double tickPct, double maxPct)
    {
        return std::max(0.0, std::min(tickPct, maxPct - dealtPct));
    }

    // Land of Plenty: "healed for {heal_pct} of your maximum life whenever you kill an enemy": the Life of one kill.
    inline double KillHeal(double maxLife, double healPct)
    {
        return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 : 0.0;
    }
} // namespace DC::Combat::Necromancer::LandOfTheDead

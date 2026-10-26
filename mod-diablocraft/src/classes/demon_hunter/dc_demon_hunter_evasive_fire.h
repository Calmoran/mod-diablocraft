#pragma once
// Evasive Fire's rules that need no core type, header-only so tests/demon_hunter_evasive_fire compiles this exact code:
// which rune is which and whether the backflip happens (which enemies the bolts reach is dc_demon_hunter_seek.h). The
// production half is dc_demon_hunter_evasive_fire.cpp.
#include "dc_demon_hunter_seek.h"

#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class ObjectGuid;
class Player;
class Unit;

namespace DC::Combat::DemonHunter::EvasiveFire
{
    enum class Rune
    {
        None,
        Hardened,     // armor instead of the backflip
        CoveringFire, // stronger side bolts and Fire
        PartingGift,  // a bomb left where the backflip began
        Surge,        // a longer backflip and Lightning
        Focus         // more Hatred (paid by the class's Connected) instead of the backflip, and Cold
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Hardened")
            return Rune::Hardened;
        if (name == "Covering Fire")
            return Rune::CoveringFire;
        if (name == "Parting Gift")
            return Rune::PartingGift;
        if (name == "Surge")
            return Rune::Surge;
        if (name == "Focus")
            return Rune::Focus;
        return Rune::None;
    }

    // "Instead of backflipping" (Hardened, Focus): the runes that give something else for the trigger.
    inline bool Backflips(Rune rune)
    {
        return rune != Rune::Hardened && rune != Rune::Focus;
    }

    // Whether any enemy, by its distance from the Demon Hunter and its bearing from them (radians), stands in front of
    // them (their facing, radians) within `radius` yards and a cone of `coneDegrees`.
    inline bool EnemyInFront(std::vector<double> const& distances, std::vector<double> const& bearings, double facing,
                             double radius, double coneDegrees)
    {
        for (std::size_t i = 0; i < distances.size() && i < bearings.size(); ++i)
            if (distances[i] <= radius && InCone(facing, bearings[i], coneDegrees))
                return true;
        return false;
    }

    // The production half (dc_demon_hunter_evasive_fire.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The bolt at the enemy aimed at, which every rune inherits (Covering Fire's 200% is the side bolts').
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast began: the backflip, or what Hardened gives instead, and Parting Gift's bomb.
    void Casting(Player* player, std::uint32_t spellId);
    // A bolt reached `target` among the enemies of the `cone` the cast was aimed into at `aimed`: true when the side
    // bolts' own hit was dealt here (or none is due) and the engine's hit is not to follow.
    bool Impact(Player* player, Unit* target, Unit* aimed, std::vector<ObjectGuid> const& cone, std::uint32_t spellId);
} // namespace DC::Combat::DemonHunter::EvasiveFire

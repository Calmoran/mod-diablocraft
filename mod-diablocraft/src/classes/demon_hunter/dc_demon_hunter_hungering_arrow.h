#pragma once
// Hungering Arrow's rules that need no core type, header-only so tests/demon_hunter_hungering_arrow compiles this exact
// code: which rune is which, the arrow's damage after each pierce and how far it travels (which enemies it seeks next
// is dc_demon_hunter_seek.h). The production half is dc_demon_hunter_hungering_arrow.cpp.
#include "dc_demon_hunter_seek.h"

#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::HungeringArrow
{
    enum class Rune
    {
        None,
        SerratedArrow,   // more Hatred (paid by the class's Connected) and Fire
        ShatterShot,     // the first pierce splits the arrow
        DevouringArrow,  // each consecutive pierce hits harder
        PuncturingArrow, // a larger chance to pierce
        SprayOfTeeth     // a critical hit bursts
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Serrated Arrow")
            return Rune::SerratedArrow;
        if (name == "Shatter Shot")
            return Rune::ShatterShot;
        if (name == "Devouring Arrow")
            return Rune::DevouringArrow;
        if (name == "Puncturing Arrow")
            return Rune::PuncturingArrow;
        if (name == "Spray of Teeth")
            return Rune::SprayOfTeeth;
        return Rune::None;
    }

    // "Each consecutive pierce increases the damage of the arrow by {damage_bonus_pct}": the weapon damage percent of
    // the arrow that has pierced `pierces` enemies (0 for the first enemy it hits). No bonus stated, the arrow's own.
    inline double PiercedDamagePct(double basePct, double bonusPct, unsigned pierces)
    {
        return basePct * (1.0 + bonusPct * pierces / 100.0);
    }

    // The arrow flies no farther from where it was shot than `travel` yards: an enemy beyond is not reached. No
    // distance stated, no limit.
    inline bool Reachable(double distanceFromCaster, double travel)
    {
        return travel <= 0 || distanceFromCaster <= travel;
    }

    // The production half (dc_demon_hunter_hungering_arrow.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The arrow's own hit, which every rune inherits (Spray of Teeth's 60% is the burst's, not the arrow's).
    std::optional<double> BasePct(std::uint32_t spellId);
    // A hit of the arrow landed on `target` (`critical` when it was a critical hit): the pierce or the split, and Spray
    // of Teeth's burst.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);
} // namespace DC::Combat::DemonHunter::HungeringArrow

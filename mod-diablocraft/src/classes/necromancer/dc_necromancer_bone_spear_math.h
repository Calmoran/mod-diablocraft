#pragma once
// The rules of Bone Spear's runes that need no core type, header-only so tests/necromancer_bone_spear compiles this exact
// code: which rune is which, Blighted Marrow's bonus for the enemies already passed through, Teeth's shorter reach, and
// which impact of a spear is the first. The production half is dc_necromancer_bone_spear.cpp.
#include <string_view>

namespace DC::Combat::Necromancer::BoneSpear
{
    enum class Rune
    {
        None,
        Crystallization,
        Shatter,
        BlightedMarrow,
        BloodSpear,
        Teeth
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Crystallization")
            return Rune::Crystallization;
        if (name == "Shatter")
            return Rune::Shatter;
        if (name == "Blighted Marrow")
            return Rune::BlightedMarrow;
        if (name == "Blood Spear")
            return Rune::BloodSpear;
        if (name == "Teeth")
            return Rune::Teeth;
        return Rune::None;
    }

    // "Damage is increased by {damage_bonus_pct} for each enemy Bone Spear passes through": the bonus of the hit after
    // `passed` enemies.
    inline double PierceBonusPct(double bonusPct, unsigned passed)
    {
        return bonusPct > 0 ? bonusPct * passed : 0.0;
    }

    // Teeth reach `reach` yards; an enemy farther than that is not struck. No reach stated, no limit.
    inline bool WithinReach(double distance, double reach)
    {
        return reach <= 0 || distance <= reach;
    }

    // "Instead of piercing now detonates on the first enemy hit": the first impact detonates, the others do nothing.
    inline bool Detonates(unsigned impactIndex)
    {
        return impactIndex == 0;
    }
} // namespace DC::Combat::Necromancer::BoneSpear

#pragma once
// The rules of Bone Armor's runes that need no core type, header-only so tests/necromancer_bone_armor compiles this exact code: which rune
// is which, what the enemies hit give, and what the armor lets through. The production half is dc_necromancer_bone_armor.cpp.
#include <algorithm>
#include <string_view>

namespace DC::Combat::Necromancer::BoneArmor
{
    enum class Rune
    {
        None,
        VengefulArmaments,
        LimitedImmunity,
        Dislocation,
        ThyFleshSustained,
        HarvestOfAnguish
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Vengeful Armaments")
            return Rune::VengefulArmaments;
        if (name == "Limited Immunity")
            return Rune::LimitedImmunity;
        if (name == "Dislocation")
            return Rune::Dislocation;
        if (name == "Thy Flesh Sustained")
            return Rune::ThyFleshSustained;
        if (name == "Harvest of Anguish")
            return Rune::HarvestOfAnguish;
        return Rune::None;
    }

    // "{per} for every enemy hit, up to a maximum of {most} enemies": what `hit` enemies give.
    inline double PerEnemy(unsigned hit, double perEnemy, unsigned most)
    {
        return std::min(hit, most) * std::max(0.0, perEnemy);
    }

    // The share of a hit the armor lets through when it takes `reductionPct` percent off, never below nothing.
    inline double TakenFactor(double reductionPct)
    {
        return std::max(0.0, 1.0 - std::max(0.0, reductionPct) / 100.0);
    }

    // Limited Immunity absorbs every hit; the others cut by the enemies' share.
    inline bool AbsorbsAll(Rune rune)
    {
        return rune == Rune::LimitedImmunity;
    }
} // namespace DC::Combat::Necromancer::BoneArmor

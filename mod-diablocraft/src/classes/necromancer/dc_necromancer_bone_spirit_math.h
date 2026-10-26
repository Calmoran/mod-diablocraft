#pragma once
// The rules of Bone Spirit's runes that need no core type, header-only so tests/necromancer_bone_spirit compiles this exact code: which
// rune is which, which enemies the spirit passes through on its way to the target, and what that is worth. The production half is
// dc_necromancer_bone_spirit.cpp.
#include <algorithm>
#include <cmath>
#include <string_view>

namespace DC::Combat::Necromancer::BoneSpirit
{
    enum class Rune
    {
        None,
        Possession,
        PanicAttack,
        Poltergeist,
        UnfinishedBusiness,
        AstralProjection
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Possession")
            return Rune::Possession;
        if (name == "Panic Attack")
            return Rune::PanicAttack;
        if (name == "Poltergeist")
            return Rune::Poltergeist;
        if (name == "Unfinished Business")
            return Rune::UnfinishedBusiness;
        if (name == "Astral Projection")
            return Rune::AstralProjection;
        return Rune::None;
    }

    // Unfinished Business explodes on top of the spirit's own hit: the skill keeps its number for the target.
    inline bool KeepsTheSkillsHit(Rune rune)
    {
        return rune == Rune::UnfinishedBusiness;
    }

    // Whether an enemy at (ex, ey) lies on the way of the spirit from (px, py) to its target at (tx, ty): between the two, not past the target,
    // within half of `width` of the line. The target itself is not passed through.
    inline bool PassedThrough(double px, double py, double tx, double ty, double ex, double ey, double width)
    {
        double const dx = tx - px, dy = ty - py;
        double const length = std::sqrt(dx * dx + dy * dy);
        if (length < 1e-9)
            return false;
        double const along = ((ex - px) * dx + (ey - py) * dy) / length;
        double const aside = std::fabs((ex - px) * dy - (ey - py) * dx) / length;
        return along >= 0 && along < length && aside <= width / 2.0;
    }

    // Astral Projection: "damage is increased by {damage_bonus_pct} for each enemy that Bone Spirit passes through".
    inline double PassBonusPct(unsigned passed, double perEnemyPct)
    {
        return passed * std::max(0.0, perEnemyPct);
    }
} // namespace DC::Combat::Necromancer::BoneSpirit

#pragma once
// The rules of Command Skeletons' runes that need no core type, header-only so tests/necromancer_command_skeletons
// compiles this exact code: which rune is which, which record a skeleton's blow is dealt as, and what a blow heals. The production half is dc_necromancer_command_skeletons.cpp (the cast) and
// dc_necromancer_pets.cpp (the skeleton).
#include <algorithm>
#include <string_view>

namespace DC::Combat::Necromancer::CommandSkeletons
{
    enum class Rune
    {
        None,
        Enforcer,
        DarkMending,
        FreezingGrasp,
        KillCommand,
        Frenzy
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Enforcer")
            return Rune::Enforcer;
        if (name == "Dark Mending")
            return Rune::DarkMending;
        if (name == "Freezing Grasp")
            return Rune::FreezingGrasp;
        if (name == "Kill Command")
            return Rune::KillCommand;
        if (name == "Frenzy")
            return Rune::Frenzy;
        return Rune::None;
    }

    // Kill Command's {damage_pct} is the explosion's, so the skeletons' own blows come from the skill's record and not the
    // rune's; every other rune's record carries the skeleton's number (Freezing Grasp's turns the school to Cold).
    inline bool BlowsUseSkillRecord(Rune rune)
    {
        return rune == Rune::KillCommand;
    }

    // Dark Mending: "heal you for {heal_pct} of your total health per hit while being commanded": the Life one blow gives,
    // none for a blow at a target that was not commanded.
    inline double HealPerBlow(bool commanded, double maxLife, double healPct)
    {
        return commanded && maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 : 0.0;
    }
} // namespace DC::Combat::Necromancer::CommandSkeletons

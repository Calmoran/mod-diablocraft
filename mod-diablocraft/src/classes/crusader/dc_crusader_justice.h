#pragma once
// Justice's rules that need no core type, header-only so tests/crusader_justice compiles this exact code: which rune is
// which, which number is the hammer's hit, and the Life Holy Bolt heals. The production half is
// dc_crusader_justice.cpp.
#include "dc_crusader_nearest.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::Justice
{
    enum class Rune
    {
        None,
        SwordOfJustice,  // movement speed for each enemy the sword hits
        Crack,           // the hammer cracks into smaller hammers
        HammerOfPursuit, // a heavier hit
        Burst,           // an explosion of lightning around the enemy hit
        HolyBolt         // heals you and your allies when it hits
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Sword of Justice")
            return Rune::SwordOfJustice;
        if (rune == "Crack")
            return Rune::Crack;
        if (rune == "Hammer of Pursuit")
            return Rune::HammerOfPursuit;
        if (rune == "Burst")
            return Rune::Burst;
        if (rune == "Holy Bolt")
            return Rune::HolyBolt;
        return Rune::None;
    }

    // The weapon-damage percentage of the hammer's own hit. Hammer of Pursuit "deals" its own 335%; every other rune's
    // damage_pct (Crack's smaller hammers, Burst's explosion) is not the hit, which stays the skill's.
    inline double HitPct(Rune rune, double skillPct, double runePct)
    {
        return rune == Rune::HammerOfPursuit ? runePct : skillPct;
    }

    // "heals you and your allies for {heal_min_life} - {heal_max_life} Life": a roll between the two.
    inline double HealAmount(double minLife, double maxLife, double roll)
    {
        return minLife + std::clamp(roll, 0.0, 1.0) * (maxLife - minLife);
    }

    // The production half (dc_crusader_justice.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    std::optional<double> BasePct(std::uint32_t spellId);
    // The hammer landed on `target`: what the rune does about it.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::Crusader::Justice

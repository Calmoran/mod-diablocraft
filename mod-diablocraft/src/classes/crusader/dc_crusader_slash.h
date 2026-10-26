#pragma once
// Slash's rules that need no core type, header-only so tests/crusader_slash compiles this exact code: which rune is
// which, the critical chance Crush adds to its own skill, and the front arc Carve strikes in. The production half is
// dc_crusader_slash.cpp.
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::Slash
{
    enum class Rune
    {
        None,
        Zeal,      // attack speed for every enemy hit
        Electrify, // a chance to stun each enemy hit
        Crush,     // critical hit chance for the skill's own hits
        Carve,     // a larger area in front
        Guard      // armor for every enemy hit
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Zeal")
            return Rune::Zeal;
        if (rune == "Electrify")
            return Rune::Electrify;
        if (rune == "Crush")
            return Rune::Crush;
        if (rune == "Carve")
            return Rune::Carve;
        if (rune == "Guard")
            return Rune::Guard;
        return Rune::None;
    }

    // "Slash gains {crit_chance_pct} increased Critical Hit Chance": the rune's number for the skill's hits and no other
    // rune's.
    inline double CrushCrit(Rune rune, double pct)
    {
        return rune == Rune::Crush ? pct : 0.0;
    }

    // The front arc, in the radians the core's HasInArc takes, from degrees.
    inline double ArcRadians(double degrees)
    {
        return degrees * 3.14159265358979323846 / 180.0;
    }

    // An enemy Carve strikes beyond the core's cone: inside the larger reach and not struck already. The reach never
    // shrinks the skill's own.
    inline bool Carved(double distance, double reach, double baseReach, bool alreadyStruck)
    {
        return !alreadyStruck && reach > baseReach && distance <= reach;
    }

    // The production half (dc_crusader_slash.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The attack connected on `enemies` enemies: Zeal and Guard stack for each.
    void Connected(Player* player, std::uint32_t spellId, unsigned enemies);
    // The swing resolved on `targets`: Electrify's stuns and Carve's extra enemies.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    double CritBonus(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::Crusader::Slash

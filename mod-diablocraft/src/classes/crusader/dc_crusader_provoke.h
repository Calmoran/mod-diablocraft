#pragma once
// Provoke's rules that need no core type, header-only so tests/crusader_provoke compiles this exact code: which rune is
// which, whether a rune taunts or frightens, the Wrath the cast pays, and when Charged Up's rider is owed. The production
// half is dc_crusader_provoke.cpp.
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::Provoke
{
    enum class Rune
    {
        None,
        Cleanse,        // Life on Hit for each enemy taunted
        FleeFool,       // the enemies flee in Fear instead of being taunted
        TooScaredToRun, // the taunted are slowed and attack slower
        ChargedUp,      // damage you deal also strikes as Lightning for a while
        HitMe           // Block Chance for a while
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Cleanse")
            return Rune::Cleanse;
        if (rune == "Flee Fool")
            return Rune::FleeFool;
        if (rune == "Too Scared to Run")
            return Rune::TooScaredToRun;
        if (rune == "Charged Up")
            return Rune::ChargedUp;
        if (rune == "Hit Me")
            return Rune::HitMe;
        return Rune::None;
    }

    // Flee Fool: "Provoke no longer taunts, but instead causes enemies to flee in Fear": the one rune that frightens, and
    // the only one that does not taunt.
    inline bool Frightens(Rune rune)
    {
        return rune == Rune::FleeFool;
    }

    // "Generate: {base} Wrath ... an additional {per_enemy} Wrath for every enemy taunted": the base always, and the
    // extra for each enemy the cast took hold of.
    inline double WrathFor(double base, double perEnemy, unsigned enemies)
    {
        return (base > 0 ? base : 0.0) + (perEnemy > 0 ? perEnemy * enemies : 0.0);
    }

    // Cleanse: "For each enemy successfully taunted, you gain {heal_per_hit_life} additional Life on Hit": a stack of
    // the heal for each enemy.
    inline unsigned CleanseStacks(Rune rune, unsigned enemies)
    {
        return rune == Rune::Cleanse ? enemies : 0u;
    }

    // Charged Up's time is over from its end moment on.
    inline bool Charged(std::uint64_t now, std::uint64_t until)
    {
        return now < until;
    }

    // Charged Up: "any damage you deal will also deal {damage_pct} weapon damage as Lightning": the rider's percentage
    // for a hit of the Crusader's while the time lasts, nothing for another rune, and nothing for the rider's own hit.
    inline double RiderPct(Rune rune, bool charged, bool ownHit, double pct)
    {
        return rune == Rune::ChargedUp && charged && !ownHit && pct > 0 ? pct : 0.0;
    }

    // The production half (dc_crusader_provoke.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // Provoke deals no damage of its own: 0 for the skill and every rune, so Charged Up's 50% is not read as the cast's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets`, the enemies around the Crusader: the taunt (or the fear), the Wrath, and what the
    // rune adds.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // A hit of `spellId` landed on `target`: Charged Up's Lightning on top of it.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::Crusader::Provoke

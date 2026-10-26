#pragma once
// Judgment's rules that need no core type, header-only so tests/crusader_judgment compiles this exact code: which rune
// is which, how much Penitence heals each second, how long an enemy stays judged, and what Resolved adds to a hit on
// it. The production half is dc_crusader_judgment.cpp.
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Crusader::Judgment
{
    enum class Rune
    {
        None,
        Penitence,    // the Crusader heals for each enemy judged
        MassVerdict,  // the enemies are drawn to the centre
        Deliberation, // the Immobilize lasts longer
        Resolved,     // hits on judged enemies crit more often
        Debilitate    // the enemies deal less damage
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Penitence")
            return Rune::Penitence;
        if (rune == "Mass Verdict")
            return Rune::MassVerdict;
        if (rune == "Deliberation")
            return Rune::Deliberation;
        if (rune == "Resolved")
            return Rune::Resolved;
        if (rune == "Debilitate")
            return Rune::Debilitate;
        return Rune::None;
    }

    // Penitence: "For every enemy upon whom you pass judgment, you heal for {heal_per_second_life} Life per second":
    // each enemy adds its own heal.
    inline double HealPerTick(double perEnemy, unsigned enemies)
    {
        return perEnemy > 0 ? perEnemy * enemies : 0.0;
    }

    // An enemy stays judged for as long as it is Immobilized: until the end time, not at it.
    inline bool Judged(std::uint64_t now, std::uint64_t until)
    {
        return now < until;
    }

    // Resolved: "Damage dealt to judged enemies has an {crit_chance_pct} increased chance to be a Critical Hit." Only
    // the rune's, only on a judged enemy.
    inline double CritFor(Rune rune, bool judged, double pct)
    {
        return rune == Rune::Resolved && judged ? pct : 0.0;
    }

    // The production half (dc_crusader_judgment.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // Judgment deals no damage: 0 for the skill and every rune.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A cast of the skill landed at `center` (the point it was aimed at): the judged enemies and what the rune does.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // Resolved's critical hit chance, in percent, on `target` for the Crusader's hit.
    double CritBonus(Player* player, Unit* target);
} // namespace DC::Combat::Crusader::Judgment

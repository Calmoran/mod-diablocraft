#pragma once
// Bombardment's rules that need no core type, header-only so tests/crusader_bombardment compiles this exact code: which
// rune is which, how many impacts fall and what each deals, how long the next one waits, what Barrels of Spikes adds,
// what Annihilate adds to the chance to critically hit, and where a mine is scattered. The production half is
// dc_crusader_bombardment.cpp.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Crusader::Bombardment
{
    enum class Rune
    {
        None,
        BarrelsOfSpikes,      // barrels that add a share of Thorns
        Annihilate,           // every impact is a sure critical hit
        MineField,            // each impact scatters mines
        ImpactfulBombardment, // one much larger ball
        Targeted              // every impact falls on the first target
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Barrels of Spikes")
            return Rune::BarrelsOfSpikes;
        if (rune == "Annihilate")
            return Rune::Annihilate;
        if (rune == "Mine Field")
            return Rune::MineField;
        if (rune == "Impactful Bombardment")
            return Rune::ImpactfulBombardment;
        if (rune == "Targeted")
            return Rune::Targeted;
        return Rune::None;
    }

    // "A single, much larger ball of explosive pitch is hurled": one impact for Impactful Bombardment, the skill's
    // count for every other.
    inline unsigned Impacts(Rune rune, unsigned skillCount)
    {
        return rune == Rune::ImpactfulBombardment ? 1u : skillCount;
    }

    // The weapon damage of one impact: the total over the impacts. Impactful Bombardment states a total of its own.
    inline double PctEach(Rune rune, double skillTotalPct, double runeTotalPct, unsigned impacts)
    {
        double const total = rune == Rune::ImpactfulBombardment ? runeTotalPct : skillTotalPct;
        return impacts && total > 0 ? total / impacts : 0.0;
    }

    // The area an impact strikes: Impactful Bombardment's own radius, the skill's for every other.
    inline double ImpactRadius(Rune rune, double skillRadius, double runeRadius)
    {
        return rune == Rune::ImpactfulBombardment ? runeRadius : skillRadius;
    }

    // The least time before the next impact falls: the power file's wait with what Barrels of Spikes and Mine Field
    // add.
    inline double MinWait(Rune rune, double baseWait, double barrelsAdded, double minesAdded)
    {
        return baseWait + (rune == Rune::BarrelsOfSpikes ? barrelsAdded : 0.0) +
               (rune == Rune::MineField ? minesAdded : 0.0);
    }

    // The wait before the next impact: the least, and a part of the extra by a roll in [0, 1].
    inline double Wait(double minWait, double extra, double roll)
    {
        return minWait + std::max(0.0, extra) * std::clamp(roll, 0.0, 1.0);
    }

    // Barrels of Spikes: "Damage of each barrel is increased by {thorns_share_pct} of your Thorns", for that rune only.
    inline double BarrelBonus(Rune rune, double thorns, double sharePct)
    {
        return rune == Rune::BarrelsOfSpikes && thorns > 0 && sharePct > 0 ? thorns * sharePct / 100.0 : 0.0;
    }

    // Annihilate: "Each impact has a {crit_chance_pct} Critical Hit Chance", for that rune only.
    inline double CritBonusPct(Rune rune, double pct)
    {
        return rune == Rune::Annihilate && pct > 0 ? pct : 0.0;
    }

    // The enemy of `count` that a roll in [0, 1) picks. Nothing when there are none.
    inline std::optional<std::size_t> Pick(std::size_t count, double roll)
    {
        if (!count)
            return std::nullopt;
        return std::min(count - 1, static_cast<std::size_t>(std::max(0.0, roll) * count));
    }

    // Mine Field: how far from the impact a mine lies, between the nearest and the farthest by a roll in [0, 1].
    inline double MineDistance(double nearest, double farthest, double roll)
    {
        return nearest + std::max(0.0, farthest - nearest) * std::clamp(roll, 0.0, 1.0);
    }

    // Mine Field: "explode when enemies walk near them": an enemy within the mine's radius sets it off.
    inline bool MineGoesOff(double nearestEnemy, double radius)
    {
        return radius > 0 && nearestEnemy <= radius;
    }

    // The production half (dc_crusader_bombardment.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The cast deals no hit of its own: the impacts fall after it. 0 for the skill and every rune.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The critical hit chance, in percent, an impact of `spellId` has on top of the sheet's.
    double CritBonus(std::uint32_t spellId);
    // The cast was aimed at `center`: the impacts begin to fall.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::Crusader::Bombardment

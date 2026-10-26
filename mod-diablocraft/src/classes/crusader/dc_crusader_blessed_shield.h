#pragma once
// Blessed Shield's rules that need no core type, header-only so tests/crusader_blessed_shield compiles this exact code:
// which rune is which, where the ricochet goes next, how the first enemy's stun chance falls with each enemy after it,
// and which enemies stand on the line a piercing shield flies along. The production half is
// dc_crusader_blessed_shield.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <utility>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::BlessedShield
{
    enum class Rune
    {
        None,
        StaggeringShield, // a chance to stun, smaller for each enemy after the first
        Combust,          // a chance to explode on each enemy hit
        DivineAegis,      // Armor and Life regeneration for each enemy hit
        ShatteringThrow,  // fragments bounce between the enemies around
        PiercingShield    // no ricochet: it pierces and may knock enemies aside
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Staggering Shield")
            return Rune::StaggeringShield;
        if (rune == "Combust")
            return Rune::Combust;
        if (rune == "Divine Aegis")
            return Rune::DivineAegis;
        if (rune == "Shattering Throw")
            return Rune::ShatteringThrow;
        if (rune == "Piercing Shield")
            return Rune::PiercingShield;
        return Rune::None;
    }

    // "The shield will ricochet to {target_count} nearby enemies": from the enemy hit last, the nearest enemy not hit
    // yet inside the bounce radius; -1 when none is. `distances` are from the enemy hit last and `hit` marks the ones
    // already struck.
    inline int NextBounce(std::vector<double> const& distances, std::vector<bool> const& hit, double radius)
    {
        int best = -1;
        for (std::size_t i = 0; i < distances.size() && i < hit.size(); ++i)
            if (!hit[i] && distances[i] <= radius && (best < 0 || distances[i] < distances[std::size_t(best)]))
                best = int(i);
        return best;
    }

    // Staggering Shield: "{proc_chance_pct:base} chance to Stun the first enemy hit ... Each enemy hit after the first
    // has a {proc_chance_pct:reduction} reduced chance": the chance, in percent, of the enemy hit `place` places after
    // the first (0 for the first), never below nothing.
    inline double StunChance(double base, double reduction, unsigned place)
    {
        return std::max(0.0, base - reduction * place);
    }

    // Piercing Shield: an enemy `along` yards down the line the shield flies and `across` yards off it is pierced when
    // it is within the length and half the width. No width, no pierce beyond the enemy aimed at.
    inline bool OnLine(double along, double across, double length, double width)
    {
        return width > 0 && along >= 0 && along <= length && std::fabs(across) <= width / 2;
    }

    // The production half (dc_crusader_blessed_shield.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The shield's own hit: 430%, which every rune inherits (Combust's 310% and Shattering Throw's 170% are the
    // explosion's and the fragments').
    std::optional<double> BasePct(std::uint32_t spellId);
    // The shield's own weapon damage and Block Chance share, for the hit's multiplier.
    std::optional<std::pair<double, double>> Main(std::uint32_t spellId);
    // The shield landed on `target`: the ricochet, and what the rune does about every enemy it hit.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::Crusader::BlessedShield

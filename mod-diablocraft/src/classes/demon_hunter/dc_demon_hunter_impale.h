#pragma once
// Impale's rules that need no core type, header-only so tests/demon_hunter_impale compiles this exact code: which rune
// is which and the damage of each bounce of Ricochet (which enemies the knife pierces or bounces to is
// dc_demon_hunter_seek.h). The production half is dc_demon_hunter_impale.cpp.
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::Impale
{
    enum class Rune
    {
        None,
        Overpenetration, // the knife pierces every enemy in the line, Cold
        Impact,          // knockback and a stun
        ChemicalBurn,    // a burn on the enemy hit, Fire
        Ricochet,        // the knife bounces to more enemies, Lightning
        GrievousWounds   // a critical hit deals more
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Overpenetration")
            return Rune::Overpenetration;
        if (name == "Impact")
            return Rune::Impact;
        if (name == "Chemical Burn")
            return Rune::ChemicalBurn;
        if (name == "Ricochet")
            return Rune::Ricochet;
        if (name == "Grievous Wounds")
            return Rune::GrievousWounds;
        return Rune::None;
    }

    // The weapon damage percent of the knife after `bounces` bounces, each leaving `factor` of the hit before (a factor
    // of 1 is a bounce that loses nothing).
    inline double BouncePct(double basePct, double factor, unsigned bounces)
    {
        return basePct * std::pow(factor, double(bounces));
    }

    // The production half (dc_demon_hunter_impale.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The knife's own hit, which every rune inherits (Chemical Burn's 500% is the burn's).
    std::optional<double> BasePct(std::uint32_t spellId);
    // A knife reached `target`, `aimed` being the enemy it was thrown at (Combat's Impact, before the hit): true for Ricochet's
    // knife at an enemy the core chained it to, which the bounces below deal with themselves.
    bool Impact(Player* player, Unit* target, Unit* aimed, std::uint32_t spellId);
    // The knife landed on `target` (`critical` when it was a critical hit): the pierce, the bounces, the knockback and
    // stun, the burn, the extra damage of a critical hit.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);
} // namespace DC::Combat::DemonHunter::Impale

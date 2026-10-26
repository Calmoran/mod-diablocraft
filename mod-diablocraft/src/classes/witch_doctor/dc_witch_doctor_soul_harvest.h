#pragma once
// Soul Harvest's rules that need no core type, header-only so tests/witch_doctor_soul_harvest compiles this exact code:
// which rune is which, the stacks a cast adds, the Life Siphon returns and the hit Vengeful Spirit deals. The
// production half is dc_witch_doctor_soul_harvest.cpp.
#include "dc_witch_doctor_buffs.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::SoulHarvest
{
    enum class Rune
    {
        None,
        Siphon,          // Life for each harvested enemy, Physical
        SoulToWaste,     // movement speed for each, Fire
        Languish,        // armor for each and the enemies slowed, Cold
        SwallowYourSoul, // Mana and a larger Mana pool for each, Poison
        VengefulSpirit   // the harvested enemies take a hit, Physical
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Siphon")
            return Rune::Siphon;
        if (name == "Soul to Waste")
            return Rune::SoulToWaste;
        if (name == "Languish")
            return Rune::Languish;
        if (name == "Swallow Your Soul")
            return Rune::SwallowYourSoul;
        if (name == "Vengeful Spirit")
            return Rune::VengefulSpirit;
        return Rune::None;
    }

    // "Gain {primary_stat_pct} Intelligence for {duration_seconds} seconds for each affected enemy. This effect stacks
    // up to {max_stacks_count} times": the stacks one cast adds, one for each enemy harvested; the buff's own cap holds
    // the rest.
    inline unsigned StacksAdded(unsigned enemies, unsigned most)
    {
        return std::min(enemies, std::max(1u, most));
    }

    // Siphon: "(0.06) * Table(Healing, Effective_Level)": the Life one harvested enemy returns at a level whose Healing
    // table row is `table`.
    inline double SiphonHeal(double share, double table, unsigned enemies)
    {
        return share > 0 && table > 0 ? share * table * enemies : 0.0;
    }

    // The hit the engine deals each enemy harvested: Vengeful Spirit's `runePct`, nothing for the others.
    inline double HitPct(Rune rune, double runePct)
    {
        return rune == Rune::VengefulSpirit ? runePct : 0.0;
    }

    // The production half (dc_witch_doctor_soul_harvest.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The engine's hit on each enemy in the area: Vengeful Spirit's, none for the others.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets` (the enemies within the radius): the stacks and the rune's part.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::WitchDoctor::SoulHarvest

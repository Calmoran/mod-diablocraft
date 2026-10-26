#pragma once
// Corpse Spiders' rules that need no core type, header-only so tests/witch_doctor_corpse_spiders compiles this exact
// code: which rune is which, what each bite is worth, when each bite and each pulse of the queen lands, the chance of a
// slow. The production half is dc_witch_doctor_corpse_spiders.cpp.
#include "dc_witch_doctor_pick.h"
#include "../../combat/dc_periodic_strike.h"

#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::WitchDoctor::CorpseSpiders
{
    enum class Rune
    {
        None,
        BlazingSpiders, // Mana for each bite, Fire
        SpiderQueen,    // a queen that pulses in place of the spiders, Poison
        LeapingSpiders, // spiders that reach farther, Poison
        Widowmakers,    // more damage, Physical
        MedusaSpiders   // a slow with every bite, Cold
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Blazing Spiders")
            return Rune::BlazingSpiders;
        if (name == "Spider Queen")
            return Rune::SpiderQueen;
        if (name == "Leaping Spiders")
            return Rune::LeapingSpiders;
        if (name == "Widowmakers")
            return Rune::Widowmakers;
        if (name == "Medusa Spiders")
            return Rune::MedusaSpiders;
        return Rune::None;
    }

    // "{spawn_count} spiders that attack nearby enemies for a total of {damage_pct} weapon damage": what one bite
    // carries when each of the `spiders` bites `bites` times. No spiders or no bites, none.
    inline double BiteShare(double totalPct, unsigned spiders, unsigned bites)
    {
        return spiders && bites ? totalPct / (double(spiders) * double(bites)) : 0.0;
    }

    // The milliseconds after the jar lands the `index`th of `bites` bites of a spider that lives `lifetimeSeconds`
    // lands, spread evenly inside its life.
    inline std::uint32_t BiteMs(unsigned index, unsigned bites, double lifetimeSeconds)
    {
        return bites ? std::uint32_t((lifetimeSeconds > 0 ? lifetimeSeconds : 0.0) * 1000.0 * double(index + 1) /
                                         double(bites + 1) +
                                     0.5)
                     : 0u;
    }

    // The queen: the milliseconds after the jar lands the `index`th of her pulses lands, the first one interval after.
    inline std::uint32_t PulseMs(unsigned index, double intervalSeconds)
    {
        return std::uint32_t((intervalSeconds > 0 ? intervalSeconds : 0.0) * 1000.0 * (index + 1) + 0.5);
    }

    // "have a {proc_chance_pct} chance to Slow": whether a roll of 0 to 100 slows.
    inline bool Slows(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // The production half (dc_witch_doctor_corpse_spiders.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The jar's own hit, the file's impact scalar: the spiders' and the queen's damage is theirs.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The jar landed at `center`: the spiders are on their way, or the queen.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::WitchDoctor::CorpseSpiders

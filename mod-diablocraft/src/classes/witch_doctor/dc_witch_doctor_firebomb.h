#pragma once
// Firebomb's rules that need no core type, header-only so tests/witch_doctor_firebomb compiles this exact code: which
// rune is which, which enemy the skull bounces to, what a bounce of Flash Fire is worth, how many Pyrogeists stand and
// when they spew. The production half is dc_witch_doctor_firebomb.cpp.
#include "../../combat/dc_periodic_strike.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::Firebomb
{
    enum class Rune
    {
        None,
        GhostBomb,    // a larger blast of Cold besides the explosion
        RollTheBones, // the skull bounces and explodes again
        FirePit,      // a pool of fire where it exploded
        Pyrogeist,    // a column of flame that spews fire at the closest enemy
        FlashFire     // no explosion: it bounces from enemy to enemy
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Ghost Bomb")
            return Rune::GhostBomb;
        if (name == "Roll the Bones")
            return Rune::RollTheBones;
        if (name == "Fire Pit")
            return Rune::FirePit;
        if (name == "Pyrogeist")
            return Rune::Pyrogeist;
        if (name == "Flash Fire")
            return Rune::FlashFire;
        return Rune::None;
    }

    // "can bounce": the place in `distances` of the nearest enemy not yet `hit` and within `reach` yards, or none (the
    // size of `distances`).
    inline std::size_t NextBounce(std::vector<double> const& distances, std::vector<bool> const& hit, double reach)
    {
        std::size_t best = distances.size();
        for (std::size_t place = 0; place < distances.size(); ++place)
            if (!hit[place] && distances[place] <= reach &&
                (best == distances.size() || distances[place] < distances[best]))
                best = place;
        return best;
    }

    // "Damage is reduced by {damage_dealt_reduction_pct} per bounce": the weapon damage of the `bounce`th bounce (the
    // first is 1) of a hit of `basePct`, each bounce taking the reduction off the whole of the base once more, never
    // below none.
    inline double FlashPct(double basePct, unsigned bounce, double reductionPct)
    {
        double const left = 1.0 - (reductionPct > 0 ? reductionPct : 0.0) / 100.0 * double(bounce);
        return basePct * (left > 0 ? left : 0.0);
    }

    // The milliseconds after the cast the `index`th bounce of Flash Fire lands, the first one delay after.
    inline std::uint32_t BounceMs(unsigned index, double delaySeconds)
    {
        return std::uint32_t((delaySeconds > 0 ? delaySeconds : 0.0) * 1000.0 * (index + 1) + 0.5);
    }

    // "You may have up to {max_count} Pyrogeists active at a time": how many of the standing ones give way when another
    // is made.
    inline std::size_t Retired(std::size_t standing, std::size_t most)
    {
        return most > 0 && standing >= most ? standing - most + 1 : 0;
    }

    // The milliseconds after it stands the `index`th spew of a Pyrogeist lands, the first one tick after.
    inline std::uint32_t SpewMs(unsigned index, double tickSeconds)
    {
        return std::uint32_t((tickSeconds > 0 ? tickSeconds : 0.0) * 1000.0 * (index + 1) + 0.5);
    }

    // The production half (dc_witch_doctor_firebomb.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The explosion at the enemy aimed at: the skill's own number for every rune (the rune numbers are the extra
    // blasts').
    std::optional<double> BasePct(std::uint32_t spellId);
    // The skull landed on `targets.front()`: the blast round it, the rune's part.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::WitchDoctor::Firebomb

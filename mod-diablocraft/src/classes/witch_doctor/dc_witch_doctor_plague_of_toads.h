#pragma once
// Plague of Toads' rules that need no core type, header-only so tests/witch_doctor_plague_of_toads compiles this exact
// code: which rune is which, which enemy the toads reach, how fast Rain of Toads casts, when its rain ticks, the chance
// of a confusion, whether the selected enemy still centres the rain. The production half is
// dc_witch_doctor_plague_of_toads.cpp.
#include "dc_witch_doctor_pick.h"
#include "../../combat/dc_periodic_strike.h"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::PlagueOfToads
{
    enum class Rune
    {
        None,
        ExplosiveToads, // fire bullfrogs, Fire
        RainOfToads,    // toads rain on the enemy's place, Poison, and the cast is faster
        PiercingToads,  // toads that go through every enemy on the line, Physical
        ToadAffinity,   // Mana for each hit, Cold
        AddlingToads    // a chance to confuse, Poison
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Explosive Toads")
            return Rune::ExplosiveToads;
        if (name == "Rain of Toads")
            return Rune::RainOfToads;
        if (name == "Piercing Toads")
            return Rune::PiercingToads;
        if (name == "Toad Affinity")
            return Rune::ToadAffinity;
        if (name == "Addling Toads")
            return Rune::AddlingToads;
        return Rune::None;
    }

    // "enemies they come in contact with": the place in `distances` of the nearest enemy, the first on a tie. None,
    // none.
    inline std::size_t NearestOf(std::vector<double> const& distances)
    {
        std::size_t nearest = 0;
        for (std::size_t place = 1; place < distances.size(); ++place)
            if (distances[place] < distances[nearest])
                nearest = place;
        return nearest;
    }

    // Rain of Toads falls on the enemy the Witch Doctor selected only while that enemy is within the line's `reach` and
    // in the Witch Doctor's line of sight; else it falls on the nearest enemy the toads would have reached.
    inline bool SelectedHolds(double distance, double reach, bool inSight)
    {
        return distance <= reach && inSight;
    }

    // "Attack Speed Mult = 1.0 + 0.4": what Rain of Toads' attack speed is multiplied by, `bonus` (0.4) more than 1;
    // every other rune's is 1.
    inline double SpeedFactor(Rune rune, double bonus)
    {
        return rune == Rune::RainOfToads ? 1.0 + (bonus > 0 ? bonus : 0.0) : 1.0;
    }

    // The milliseconds after the cast the `index`th tick of the rain lands, the first one tick after.
    inline std::uint32_t RainMs(unsigned index, double tickSeconds)
    {
        return std::uint32_t((tickSeconds > 0 ? tickSeconds : 0.0) * 1000.0 * (index + 1) + 0.5);
    }

    // "have a {proc_chance_pct} chance to Confuse": whether a roll of 0 to 100 confuses.
    inline bool Confuses(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // The production half (dc_witch_doctor_plague_of_toads.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The engine's hit along the line: Piercing Toads' (every enemy on it); the other runes' toads reach the nearest
    // enemy, struck in Cast.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets` (the enemies along the line): the nearest is struck, or the rain begins.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // `base` attacks a second of the skill's cast, made faster for Rain of Toads.
    double AttackSpeed(std::uint32_t spellId, double base);
} // namespace DC::Combat::WitchDoctor::PlagueOfToads

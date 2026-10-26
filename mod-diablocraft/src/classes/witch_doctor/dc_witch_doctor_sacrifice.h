#pragma once
// Sacrifice's rules that need no core type, header-only so tests/witch_doctor_sacrifice compiles this exact code: which
// rune is which, how many Zombie Dogs a cast banishes, what Pride pays, the chance a banished dog comes back, and how
// long Provoke the Pack's damage lasts. The production half is dc_witch_doctor_sacrifice.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
struct Position;

namespace DC::Combat::WitchDoctor::Sacrifice
{
    enum class Rune
    {
        None,
        ProvokeThePack, // more damage done for a while after the cast
        ForTheMaster,   // every Zombie Dog is banished, each exploding for the rune's damage
        BlackBlood,     // the explosion stuns the enemies
        Pride,          // Mana for each dog banished
        NextOfKin       // a banished dog may come back as a new one
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Provoke the Pack")
            return Rune::ProvokeThePack;
        if (name == "For the Master")
            return Rune::ForTheMaster;
        if (name == "Black Blood")
            return Rune::BlackBlood;
        if (name == "Pride")
            return Rune::Pride;
        if (name == "Next of Kin")
            return Rune::NextOfKin;
        return Rune::None;
    }

    // "Banish one of your active Zombie Dogs" and, for For the Master, "all of your Zombie Dogs": the dogs a cast
    // banishes of `standing`.
    inline unsigned Sacrificed(Rune rune, unsigned standing)
    {
        return rune == Rune::ForTheMaster ? standing : std::min(standing, 1u);
    }

    // "Gain {gain_resource} Mana for each Zombie Dog you sacrifice."
    inline double PrideMana(double perDog, unsigned dogs)
    {
        return perDog > 0 ? perDog * dogs : 0.0;
    }

    // "Each Zombie Dog you sacrifice has a {proc_chance_pct} chance to resurrect": whether a roll of 0 up to 100 brings
    // a dog back.
    inline bool Resurrects(double roll, double chancePct)
    {
        return chancePct > 0 && roll < chancePct;
    }

    // "Gain {damage_bonus_pct} increased damage done for {duration_seconds} seconds after using Sacrifice": the moment
    // the bonus ends.
    inline std::uint64_t BonusUntil(std::uint64_t nowMs, double seconds)
    {
        return seconds > 0 ? nowMs + static_cast<std::uint64_t>(seconds * 1000.0 + 0.5) : nowMs;
    }

    inline bool BonusOn(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // The production half (dc_witch_doctor_sacrifice.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // No hit of the cast itself: the dogs' explosions are the damage, and only when a dog stands.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast aimed at the ground point `center` resolved: the dogs are banished and explode there.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // Provoke the Pack's damage done, a multiplier of its own on every hit while it lasts.
    void Multipliers(Player* player, DC::Combat::Factors& out);
} // namespace DC::Combat::WitchDoctor::Sacrifice

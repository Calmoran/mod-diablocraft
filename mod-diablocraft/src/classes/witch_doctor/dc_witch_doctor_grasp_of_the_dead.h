#pragma once
// Grasp of the Dead's rules that need no core type, header-only so tests/witch_doctor_grasp_of_the_dead compiles this
// exact code: which rune is which, how long a pulse's slow holds, when each pulse and each corpse lands, how long the
// hands' area catches a death and whether a death rises as a Zombie Dog. The production half is
// dc_witch_doctor_grasp_of_the_dead.cpp.
#include "dc_witch_doctor_pick.h"
#include "../../combat/dc_periodic_strike.h"

#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
struct Position;

namespace DC::Combat::WitchDoctor::GraspOfTheDead
{
    enum class Rune
    {
        None,
        GropingEels,      // more damage (the sheet's number)
        RainOfCorpses,    // corpses fall on nearby enemies besides, Physical
        UnbreakableGrasp, // no Mana cost (the record's), a stronger slow, Cold
        DesperateGrasp,   // a shorter cooldown (the record's), Poison
        DeathIsLife       // a chance of a Zombie Dog for an enemy that dies in it, Poison
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Groping Eels")
            return Rune::GropingEels;
        if (name == "Rain of Corpses")
            return Rune::RainOfCorpses;
        if (name == "Unbreakable Grasp")
            return Rune::UnbreakableGrasp;
        if (name == "Desperate Grasp")
            return Rune::DesperateGrasp;
        if (name == "Death Is Life")
            return Rune::DeathIsLife;
        return Rune::None;
    }

    // "slowing enemy movement": the seconds a pulse's slow holds, the pulse's own interval and the extra the file adds,
    // so the slow does not lapse between two pulses.
    inline double SlowSeconds(double pulseSeconds, double extraSeconds)
    {
        return (pulseSeconds > 0 ? pulseSeconds : 0.0) + (extraSeconds > 0 ? extraSeconds : 0.0);
    }

    // The milliseconds after the hands rise the `index`th pulse (or corpse) lands, the first one interval after.
    inline std::uint32_t PulseMs(unsigned index, double intervalSeconds)
    {
        return std::uint32_t((intervalSeconds > 0 ? intervalSeconds : 0.0) * 1000.0 * (index + 1) + 0.5);
    }

    // "Enemies who die while in the area": how long, in milliseconds, the hands' area catches a death after they rise, the
    // skill's seconds and the slow's extra, so an enemy the last pulse kills still counts.
    inline std::uint64_t AreaMs(double seconds, double extraSeconds)
    {
        return std::uint64_t(SlowSeconds(seconds, extraSeconds) * 1000.0 + 0.5);
    }

    // Whether an enemy that died `distance` yards from the hands' middle, `nowMs` on the game clock, died in the area
    // that holds until `untilMs`.
    inline bool InArea(std::uint64_t nowMs, std::uint64_t untilMs, double distance, double radius)
    {
        return nowMs < untilMs && distance <= radius;
    }

    // Death Is Life: "a {proc_chance_pct} chance to summon a Zombie Dog": a roll of 0 to 100 against the chance.
    inline bool Rises(double roll, double chancePct)
    {
        return chancePct > 0 && roll < chancePct;
    }

    // The production half (dc_witch_doctor_grasp_of_the_dead.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The cast hits nothing of its own: the hands' pulses are the damage.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The hands rose at `center`: the pulses, and Rain of Corpses' corpses, are on their way.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // The health globe Death Is Life's file also names (SF_21 'Zombie Dog / Health Globe Spawn Chance'): the health
    // globes (on hold) fill this in; nothing calls it yet.
    void SpawnGlobe(Player* player, Position const& at);
    // Death Is Life's death script; at startup.
    void RegisterScripts();
} // namespace DC::Combat::WitchDoctor::GraspOfTheDead

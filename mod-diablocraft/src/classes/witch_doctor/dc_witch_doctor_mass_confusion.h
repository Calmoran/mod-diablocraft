#pragma once
// Mass Confusion's rules that need no core type, header-only so tests/witch_doctor_mass_confusion compiles this exact
// code: which rune is which, which enemies the confusion takes, how many of the others Mass Hysteria stuns, and how far
// and which way the giant spirit walks each tick, how long an enemy counts as confused and whether its death leaves a
// Zombie Dog. The production half is dc_witch_doctor_mass_confusion.cpp.
#include "dc_witch_doctor_clock.h"
#include "dc_witch_doctor_pick.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::MassConfusion
{
    enum class Rune
    {
        None,
        Paranoia,          // the enemies in the area deal less damage
        MassHysteria,      // enemies the confusion missed are stunned
        MassHallucination, // a giant spirit rampages through the enemies
        UnstableRealm,     // a shorter cooldown (the record's)
        Devolution         // an enemy killed while confused may leave a Zombie Dog
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Paranoia")
            return Rune::Paranoia;
        if (name == "Mass Hysteria")
            return Rune::MassHysteria;
        if (name == "Mass Hallucination")
            return Rune::MassHallucination;
        if (name == "Unstable Realm")
            return Rune::UnstableRealm;
        if (name == "Devolution")
            return Rune::Devolution;
        return Rune::None;
    }

    // "Monsters Affected Proportion": whether an enemy in the area is taken by the confusion, given a roll of 0 up to 1
    // and the proportion.
    inline bool Affected(double roll, double proportion)
    {
        return proportion > 0 && roll < proportion;
    }

    // "Up to {target_count} enemies who are not Confused become Stunned": how many of `unaffected` enemies are stunned.
    inline unsigned ToStun(unsigned unaffected, unsigned most)
    {
        return std::min(unaffected, most);
    }

    // The yards a power-file speed (yards per frame at 60 frames a second) covers in a tick of `tickSeconds`.
    inline double StepYards(double speedPerFrame, double tickSeconds)
    {
        return speedPerFrame > 0 && tickSeconds > 0 ? speedPerFrame * 60.0 * tickSeconds : 0.0;
    }

    // The milliseconds an enemy the confusion took counts as confused: the confusion's seconds, none for no seconds.
    inline std::uint64_t HeldMs(double seconds)
    {
        return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;
    }

    // "Enemies killed while Confused": whether a death `nowMs` on the game clock came before the confusion, which holds
    // until `untilMs`, ended.
    inline bool Confused(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // Devolution: "a {proc_chance_pct} chance to spawn a Zombie Dog": a roll of 0 to 100 against the chance.
    inline bool Rises(double roll, double chancePct)
    {
        return chancePct > 0 && roll < chancePct;
    }

    struct Spot
    {
        double x = 0;
        double y = 0;
    };

    // The spirit's new spot: `step` yards from `from` towards `to`, or `to` itself when it is nearer than that.
    inline Spot Advance(Spot from, Spot to, double step)
    {
        double const dx = to.x - from.x, dy = to.y - from.y, distance = std::sqrt(dx * dx + dy * dy);
        if (step <= 0)
            return from;
        if (distance <= step)
            return to;
        return {from.x + dx / distance * step, from.y + dy / distance * step};
    }

    // The production half (dc_witch_doctor_mass_confusion.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // No hit of the cast itself.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets` (the enemies within the radius): the confusion, and each rune's part.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // Devolution's death script; at startup.
    void RegisterScripts();
} // namespace DC::Combat::WitchDoctor::MassConfusion

#pragma once
// The rules of the Gargantuan's runes that need no core type, header-only so tests/witch_doctor_gargantuan compiles
// this exact code: when Restless Giant enrages and when it may again, what one pulse of Big Stinker's cloud deals, how
// Wrathful Protector's attack speed shortens a swing and what lifts an enemy into the air. The production half is
// dc_witch_doctor_gargantuan.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>

namespace DC::Combat::WitchDoctor::GargantuanRunes
{
    // Restless Giant: "When the Gargantuan encounters an elite enemy or is near {nearby_enemy_count} enemies, it
    // enrages".
    inline bool Enraged(unsigned nearby, unsigned most, bool elite)
    {
        return elite || (most > 0 && nearby >= most);
    }

    // "This effect cannot occur more than once every {internal_cooldown_seconds} seconds": the last time it did (none
    // before), now and the cooldown, in milliseconds.
    inline bool OffCooldown(std::optional<std::uint64_t> lastMs, std::uint64_t nowMs, std::uint64_t cooldownMs)
    {
        return !lastMs || nowMs >= *lastMs + cooldownMs;
    }

    // Big Stinker: "a poison cloud that deals {damage_pct} weapon damage as Poison per second": the weapon damage one
    // pulse deals when a pulse comes every `tickSeconds`.
    inline double PulsePct(double perSecondPct, double tickSeconds)
    {
        return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;
    }

    // Wrathful Protector: the milliseconds between two swings when its attack speed is `factor` times the normal; no
    // factor, the normal.
    inline double Quickened(double swingMs, double factor)
    {
        return swingMs > 0 && factor > 0 ? swingMs / factor : swingMs;
    }

    // The speeds that lift an enemy `heightYards` into the air on the core's knockback (a parabola: height = vz^2 / 2g,
    // Movement::gravity). The core refuses a horizontal speed of 0.1 or less, so a lift straight up (the power file's
    // magnitude 0) moves just over it. No height, no lift.
    struct Lift
    {
        double xy = 0, z = 0;
    };

    constexpr double MinimumSpeedXY = 0.1;

    inline Lift LiftSpeeds(double heightYards, double gravity = 19.29110527038574)
    {
        if (heightYards <= 0 || gravity <= 0)
            return {};
        return {MinimumSpeedXY * 1.1, std::sqrt(2 * gravity * heightYards)};
    }
} // namespace DC::Combat::WitchDoctor::GargantuanRunes

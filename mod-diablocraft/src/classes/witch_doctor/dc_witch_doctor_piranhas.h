#pragma once
// Piranhas' rules that need no core type, header-only so tests/witch_doctor_piranhas compiles this exact code: which
// rune is which, what a pool tick deals, how far the pool reaches, when Wave of Mutilation reaches an enemy, which
// enemies the wave passes over and which the tornado sucks in. The production half is dc_witch_doctor_piranhas.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;
struct Position;

namespace DC::Combat::WitchDoctor::Piranhas
{
    enum class Rune
    {
        None,
        Bogadile,         // a giant bogadile bites and stuns, Physical
        ZombiePiranhas,   // the piranhas leap out at enemies farther away, Poison
        Piranhado,        // the pool is a short tornado that sucks enemies in, Poison
        WaveOfMutilation, // a wave in place of the pool, Poison
        FrozenPiranhas    // Cold, and the enemies in the pool are chilled
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Bogadile")
            return Rune::Bogadile;
        if (name == "Zombie Piranhas")
            return Rune::ZombiePiranhas;
        if (name == "Piranhado")
            return Rune::Piranhado;
        if (name == "Wave of Mutilation")
            return Rune::WaveOfMutilation;
        if (name == "Frozen Piranhas")
            return Rune::FrozenPiranhas;
        return Rune::None;
    }

    // The Bogadile names Physical for its bite alone: the pool stays the skill's Poison.
    inline bool PoolTakesRuneElement(Rune rune)
    {
        return rune != Rune::Bogadile;
    }

    // "{damage_pct} weapon damage over {dot_duration_seconds} seconds": the percent of one tick of `tickSeconds`,
    // whatever the seconds the pool stands (the Piranhado's tornado stands half as long and deals half as much).
    inline double TickPct(double totalPct, double totalSeconds, double tickSeconds)
    {
        return totalSeconds > 0 ? totalPct / totalSeconds * tickSeconds : 0.0;
    }

    // The yards from the middle the pool's damage reaches: the pool's, Zombie Piranhas' leap farther.
    inline double PoolReach(Rune rune, double pool, double leap)
    {
        return rune == Rune::ZombiePiranhas ? leap : pool;
    }

    // Where a point `dx`, `dy` yards from the Witch Doctor (east and north) lies against the wave's aim `heading`
    // (radians): yards along it and across it.
    inline double Ahead(double dx, double dy, double heading)
    {
        return dx * std::cos(heading) + dy * std::sin(heading);
    }

    inline double Across(double dx, double dy, double heading)
    {
        return -dx * std::sin(heading) + dy * std::cos(heading);
    }

    // Whether the wave passes over a point: ahead of the Witch Doctor, no farther than the wave's last distance, and
    // within half its width to a side.
    inline bool WaveCovers(double ahead, double across, double distance, double width)
    {
        return ahead >= 0 && ahead <= distance && std::fabs(across) <= width / 2;
    }

    // The milliseconds after the cast the wave reaches a point `ahead` yards from the Witch Doctor: it starts `offset +
    // length` yards out (the wave and its length) and runs at `yardsPerSecond`; what lies within that reach is hit at
    // once.
    inline std::uint32_t WaveReachesMs(double ahead, double offset, double length, double yardsPerSecond)
    {
        double const lead = offset + length;
        return yardsPerSecond > 0 && ahead > lead ? std::uint32_t((ahead - lead) / yardsPerSecond * 1000.0 + 0.5) : 0u;
    }

    // Piranhado: "Nearby enemies are periodically sucked into the tornado": the enemies within the vacuum radius.
    inline bool Sucked(double distance, double vacuumRadius)
    {
        return distance <= vacuumRadius;
    }

    // The production half (dc_witch_doctor_piranhas.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The cast's own hit: none; the pool and the wave strike for themselves.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast went off at `center`: the pool, or the wave.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::WitchDoctor::Piranhas

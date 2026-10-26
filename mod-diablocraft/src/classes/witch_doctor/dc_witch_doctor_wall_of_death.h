#pragma once
// Wall of Death's rules that need no core type, header-only so tests/witch_doctor_wall_of_death compiles this exact
// code: which rune is which, which enemies stand in the wall, which are in front of it and how far they are shoved,
// what a tick deals and when Fire Wall burns an enemy again. The production half is dc_witch_doctor_wall_of_death.cpp.
#include "../../combat/dc_periodic_strike.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::WitchDoctor::WallOfDeath
{
    enum class Rune
    {
        None,
        SurroundedByDeath,    // a circle of zombies that attacks what is in it, Physical
        RingOfPoison,         // a ring that poisons what is in it, Poison
        CommuningWithSpirits, // a circle that hurts, chills and weakens, Cold
        WallOfZombies,        // a wider wall that shoves the enemies before it behind it, Physical
        FireWall              // a wall of flame that burns what walks through it, Fire
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Surrounded by Death")
            return Rune::SurroundedByDeath;
        if (name == "Ring of Poison")
            return Rune::RingOfPoison;
        if (name == "Communing with Spirits")
            return Rune::CommuningWithSpirits;
        if (name == "Wall of Zombies")
            return Rune::WallOfZombies;
        if (name == "Fire Wall")
            return Rune::FireWall;
        return Rune::None;
    }

    // The wall stands across the aim, `width` yards wide, with `capsule` yards of reach round it. The yards from the
    // wall's middle to the farthest point an enemy can stand in it.
    inline double WallReach(double width, double capsule)
    {
        return width / 2 + capsule;
    }

    // Where a point `dx`, `dy` yards from the wall's middle (east and north) lies against a wall across `heading`
    // (radians): yards along the aim (negative before the wall's middle) and across it.
    inline double Along(double dx, double dy, double heading)
    {
        return dx * std::cos(heading) + dy * std::sin(heading);
    }

    inline double Across(double dx, double dy, double heading)
    {
        return -dx * std::sin(heading) + dy * std::cos(heading);
    }

    // Whether a point stands in the wall: within `capsule` yards of its line, the line `width` yards long across the
    // aim.
    inline bool InWall(double dx, double dy, double heading, double width, double capsule)
    {
        double const along = Along(dx, dy, heading), across = std::fabs(Across(dx, dy, heading));
        return std::hypot(along, std::max(0.0, across - width / 2)) <= capsule;
    }

    // Wall of Zombies: "All enemies in front of you are knocked back behind the wall": an enemy `along` yards from the
    // wall's middle toward the Witch Doctor (positive when before it) and `across` yards to a side is in front when it
    // is before the wall and no farther to a side than the wall's end.
    inline bool InFront(double alongEnemy, double acrossEnemy, double width)
    {
        return alongEnemy < 0 && std::fabs(acrossEnemy) <= width / 2;
    }

    // The yards that shove an enemy at `alongEnemy` (negative: before the wall's middle) to just past the wall's far
    // edge.
    inline double KnockYards(double alongEnemy, double capsule)
    {
        return capsule - alongEnemy;
    }

    // "{damage_pct} weapon damage ... over {seconds} seconds" in ticks of `tickSeconds`: the percent of one tick.
    inline double TickPct(double totalPct, double seconds, double tickSeconds)
    {
        return PeriodicStrike::TickPct(totalPct, PeriodicStrike::Ticks(seconds, tickSeconds));
    }

    // Fire Wall burns "enemies who walk through": an enemy burns again once its last burn is over (`lastMs`, none for
    // an enemy not yet burnt; `nowMs`; the burn lasts `burnMs`).
    inline bool BurnsAgain(std::optional<std::uint64_t> lastMs, std::uint64_t nowMs, std::uint64_t burnMs)
    {
        return !lastMs || nowMs >= *lastMs + burnMs;
    }

    // The production half (dc_witch_doctor_wall_of_death.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The cast's own hit: none; the wall and the circles strike for themselves.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast went off at `center`: the wall, circle or ring.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::WitchDoctor::WallOfDeath

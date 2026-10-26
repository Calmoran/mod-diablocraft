#pragma once
// Cluster Arrow's rules that need no core type, header-only so tests/demon_hunter_cluster_arrow compiles this exact
// code: which rune is which, where a grenade lands round the impact, where Cluster Bombs drops each bomb along its line
// and when, what a rocket heals, the chance of a stun. The production half is dc_demon_hunter_cluster_arrow.cpp.
#include "dc_demon_hunter_pick.h"

#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::DemonHunter::ClusterArrow
{
    enum class Rune
    {
        None,
        LoadedForBear, // a bigger explosion at the impact (the record's), Fire
        ShootingStars, // rockets in place of the grenades, Physical
        ClusterBombs,  // bombs dropped along a line in place of the impact, Fire
        Maelstrom,     // rockets in place of the grenades that heal, Cold
        DazzlingArrow  // the grenades may stun, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Loaded for Bear")
            return Rune::LoadedForBear;
        if (name == "Shooting Stars")
            return Rune::ShootingStars;
        if (name == "Cluster Bombs")
            return Rune::ClusterBombs;
        if (name == "Maelstrom")
            return Rune::Maelstrom;
        if (name == "Dazzling Arrow")
            return Rune::DazzlingArrow;
        return Rune::None;
    }

    // A point on the ground.
    struct Spot
    {
        double x = 0;
        double y = 0;
    };

    // "Baby Offset Min/Delta": where a grenade lands round the impact at (x, y): the heading a roll of 0 up to 1 gives
    // (a full turn) and a distance from the minimum up to the minimum plus the delta, by a second roll.
    inline Spot GrenadeLanding(double x, double y, double headingRoll, double distanceRoll, double minYards,
                               double deltaYards)
    {
        double const heading = headingRoll * 2.0 * 3.14159265358979323846;
        double const yards = minYards + deltaYards * distanceRoll;
        return {x + std::cos(heading) * yards, y + std::sin(heading) * yards};
    }

    // Cluster Bombs: where the `index`th of `count` bombs lands on the line of `heading` from (x, y), spread evenly
    // over `distance` yards, and to the side by a roll of 0 up to 1 within `spread` yards either way ("Range Left/Right
    // Max").
    inline Spot BombLanding(double x, double y, double heading, unsigned index, unsigned count, double distance,
                            double sideRoll, double spread)
    {
        double const along = count ? distance * double(index + 1) / double(count) : 0.0;
        double const side = (sideRoll * 2.0 - 1.0) * spread;
        return {x + std::cos(heading) * along - std::sin(heading) * side,
                y + std::sin(heading) * along + std::cos(heading) * side};
    }

    // "BabyBomb Spawn Rate": the milliseconds after the cast the `index`th bomb is dropped.
    inline std::uint32_t BombDelayMs(unsigned index, double intervalSeconds)
    {
        return std::uint32_t((intervalSeconds > 0 ? intervalSeconds : 0.0) * 1000.0 * index + 0.5);
    }

    // "You gain {heal_pct} Life per enemy hit": the Life of a maximum.
    inline double Healed(double maxLife, double pct)
    {
        return (maxLife > 0 ? maxLife : 0.0) * (pct > 0 ? pct : 0.0) / 100.0;
    }

    // "have a {proc_chance_pct} chance to be stunned": whether a roll of 0 to 100 stuns.
    inline bool Stuns(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // The production half (dc_demon_hunter_cluster_arrow.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The explosion at the impact: the skill's own number for every rune but Loaded for Bear (the rune's own) and
    // Cluster Bombs (none).
    std::optional<double> BasePct(std::uint32_t spellId);
    // The arrow exploded at `center`: the grenades, the rockets or the bombs.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // A hit of the cast landed on `target`: Dazzling Arrow's stun for a grenade's.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::DemonHunter::ClusterArrow

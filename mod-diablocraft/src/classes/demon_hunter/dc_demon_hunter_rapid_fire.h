#pragma once
// Rapid Fire's rules that need no core type, header-only so tests/demon_hunter_rapid_fire compiles this exact code:
// which rune is which, the seconds between shots and what a shot is worth and costs, and the clock that tells how many
// shots are due. The production half is dc_demon_hunter_rapid_fire.cpp.
#include "dc_demon_hunter_clock.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::RapidFire
{
    enum class Rune
    {
        None,
        Bombardment,   // grenades that explode around the enemy, Fire
        HighVelocity,  // arrows that may pierce, Lightning
        FireSupport,   // homing rockets besides the shots
        WitheringFire, // a cheaper start, Fire
        FrostShots     // the enemies hit are chilled, Cold
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Bombardment")
            return Rune::Bombardment;
        if (name == "High Velocity")
            return Rune::HighVelocity;
        if (name == "Fire Support")
            return Rune::FireSupport;
        if (name == "Withering Fire")
            return Rune::WitheringFire;
        if (name == "Frost Shots")
            return Rune::FrostShots;
        return Rune::None;
    }

    // The seconds between two shots: a second of attack speed holds `shotsPerAttack` shots. No speed or no shots, none.
    inline double ShotSeconds(double shotsPerAttack, double attacksPerSecond)
    {
        return shotsPerAttack > 0 && attacksPerSecond > 0 ? 1.0 / (attacksPerSecond * shotsPerAttack) : 0.0;
    }

    // "Rapidly fire for {damage_pct} weapon damage": the number is for a second of attack speed, so a shot carries its
    // share.
    inline double ShotPct(double damagePct, double shotsPerAttack)
    {
        return shotsPerAttack > 0 ? damagePct / shotsPerAttack : 0.0;
    }

    // "an additional {cost_resource:channel} Hatred while channeling": the same share of the channel's cost, for each
    // shot.
    inline double ShotCost(double channelCost, double shotsPerAttack)
    {
        return shotsPerAttack > 0 ? channelCost / shotsPerAttack : 0.0;
    }

    // "launch {projectile_count} homing rockets every second": the seconds between two rockets.
    inline double RocketSeconds(double rocketsPerSecond)
    {
        return rocketsPerSecond > 0 ? 1.0 / rocketsPerSecond : 0.0;
    }

    // The production half (dc_demon_hunter_rapid_fire.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // No hit of the cast itself: the channel's shots are the damage.
    std::optional<double> BasePct(std::uint32_t spellId);
    // Whether the Hatred the start costs is there.
    bool Affordable(Player* player, std::uint32_t spellId);
    // The channel began on `targets` (Combat::ResolveCast): the start is paid and the first shot fires.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::RapidFire

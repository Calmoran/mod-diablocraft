#pragma once
// Falling Sword's rules that need no core type, header-only so tests/crusader_falling_sword compiles this exact code:
// which rune is which, how long the cooldown waits for what the rune leaves behind, what Rapid Descent takes off it,
// and how a rate a second is paid in ticks. The production half is dc_crusader_falling_sword.cpp.
#include "dc_crusader_dot.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Crusader::FallingSword
{
    enum class Rune
    {
        None,
        Superheated,   // the ground burns
        PartTheClouds, // a storm strikes random enemies and stuns them
        RiseBrothers,  // avatars fight beside the Crusader
        RapidDescent,  // the cooldown is cut for each enemy hit
        Flurry         // swords strike and incapacitate the enemies around
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Superheated")
            return Rune::Superheated;
        if (rune == "Part the Clouds")
            return Rune::PartTheClouds;
        if (rune == "Rise Brothers")
            return Rune::RiseBrothers;
        if (rune == "Rapid Descent")
            return Rune::RapidDescent;
        if (rune == "Flurry")
            return Rune::Flurry;
        return Rune::None;
    }

    // "This ability does not start its cooldown until after its effects expire": the four runes that leave something
    // behind wait for it (the ground, the storm, the avatars, the flurry); the skill and Rapid Descent leave nothing,
    // so their cooldown starts at the landing.
    inline double WaitSeconds(Rune rune, double durationSeconds)
    {
        bool const leaves = rune == Rune::Superheated || rune == Rune::PartTheClouds || rune == Rune::RiseBrothers ||
                            rune == Rune::Flurry;
        return leaves && durationSeconds > 0 ? durationSeconds : 0.0;
    }

    // Rapid Descent: "Reduce the cooldown by {cooldown_reduction_seconds} second for each enemy hit ... The cooldown
    // cannot be reduced below {min_cooldown_seconds} seconds." A cooldown already below the floor is not raised to it.
    inline double CooldownSeconds(Rune rune, double wholeSeconds, unsigned enemiesHit, double perEnemySeconds,
                                  double floorSeconds)
    {
        if (rune != Rune::RapidDescent || perEnemySeconds <= 0)
            return wholeSeconds;
        return std::max(std::min(wholeSeconds, floorSeconds), wholeSeconds - enemiesHit * perEnemySeconds);
    }

    // A rate of weapon damage a second ("{damage_pct} weapon damage as Fire per second") over `seconds` is paid in the
    // ticks that fit, whole: each tick is the total over the ticks. Nothing for a rate, a time or a tick of 0.
    inline double PctPerTick(double ratePerSecond, double seconds, double tickSeconds)
    {
        unsigned const ticks = Dot::Ticks(seconds, tickSeconds);
        return ratePerSecond > 0 ? Dot::TickPct(ratePerSecond * seconds, ticks) : 0.0;
    }

    // Part the Clouds: the enemy of `count` that a roll in [0, 1) picks. Nothing when there are none.
    inline std::optional<std::size_t> Pick(std::size_t count, double roll)
    {
        if (!count)
            return std::nullopt;
        return std::min(count - 1, static_cast<std::size_t>(std::max(0.0, roll) * count));
    }

    // The production half (dc_crusader_falling_sword.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The landing's own hit: the skill's percentage for the skill and every rune (a rune's other numbers are its
    // effect's).
    std::optional<double> BasePct(std::uint32_t spellId);
    // The landing struck `targets`: the cooldown starts again once the rune's effects are over, and Rapid Descent cuts
    // it.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The landing was at `center`: what the rune leaves there.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::Crusader::FallingSword

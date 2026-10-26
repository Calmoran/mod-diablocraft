#pragma once
// Firebats' rules that need no core type, header-only so tests/witch_doctor_firebats compiles this exact code: which
// rune is which, the seconds between ticks and what a tick costs and deals, which enemies are in the cone, how Plague
// Bats' stacks and Cloud of Bats' bonus grow. The production half is dc_witch_doctor_firebats.cpp.
#include "dc_witch_doctor_clock.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::Firebats
{
    enum class Rune
    {
        None,
        DireBats,    // one larger bat a tick
        HungryBats,  // bats that each seek an enemy
        PlagueBats,  // diseased bats whose damage grows
        VampireBats, // a start cost and no channelling cost, Physical
        CloudOfBats  // a swirl round the Witch Doctor whose damage grows
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Dire Bats")
            return Rune::DireBats;
        if (name == "Hungry Bats")
            return Rune::HungryBats;
        if (name == "Plague Bats")
            return Rune::PlagueBats;
        if (name == "Vampire Bats")
            return Rune::VampireBats;
        if (name == "Cloud of Bats")
            return Rune::CloudOfBats;
        return Rune::None;
    }

    // "Tick Rate Multiplier": the seconds between two ticks when a second of attack speed holds `ticksPerAttack` of
    // them. No speed or no ticks, none.
    inline double TickSeconds(double ticksPerAttack, double attacksPerSecond)
    {
        return ticksPerAttack > 0 && attacksPerSecond > 0 ? 1.0 / (attacksPerSecond * ticksPerAttack) : 0.0;
    }

    // "Cost: {cost_resource} Mana" and "{damage_pct} weapon damage": the share of a second of attack speed's cost or
    // damage that one tick carries.
    inline double TickShare(double perAttack, double ticksPerAttack)
    {
        return ticksPerAttack > 0 ? perAttack / ticksPerAttack : 0.0;
    }

    // "burn enemies in front of you": whether an enemy `offsetRadians` off the way the Witch Doctor faces (either side)
    // is within a cone of `coneDegrees` across.
    inline bool InCone(double offsetRadians, double coneDegrees)
    {
        return coneDegrees > 0 && std::fabs(offsetRadians) <= coneDegrees * 3.14159265358979323846 / 360.0 + 1e-12;
    }

    // Plague Bats: "Damage is slow at first, but can increase over time": the stacks an enemy hit by a tick carries,
    // one more than it had when its last tick was `sinceMs` ago and the stacks last `lastsMs`, none having lasted, and
    // at most `most`.
    inline unsigned PlagueStacks(unsigned stacks, double sinceMs, double lastsMs, unsigned most)
    {
        unsigned const held = sinceMs <= lastsMs ? stacks : 0u;
        return std::min(held + 1u, most > 0 ? most : 1u);
    }

    // The share of the rune's most that a tick deals to an enemy with `stacks` of `most`.
    inline double PlaguePct(double mostPct, unsigned stacks, unsigned most)
    {
        return most ? mostPct * double(std::min(stacks, most)) / double(most) : 0.0;
    }

    // Cloud of Bats: "The damage of the bats increases every second, up to a maximum after 3 seconds": what the damage
    // is multiplied by after `channelSeconds` of channel, each whole second adding `perStack`, up to `most` of them.
    inline double CloudFactor(double channelSeconds, double perStack, unsigned most)
    {
        double const stacks = std::min(std::floor(channelSeconds > 0 ? channelSeconds : 0.0), double(most));
        return 1.0 + perStack * stacks;
    }

    // The production half (dc_witch_doctor_firebats.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // No hit of the cast itself: the channel's ticks are the damage.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The channel began: Vampire Bats' start is paid and the first tick falls.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    void RegisterScripts();
} // namespace DC::Combat::WitchDoctor::Firebats

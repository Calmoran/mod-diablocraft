#pragma once
// Locust Swarm's rules that need no core type, header-only so tests/witch_doctor_locust_swarm compiles this exact code:
// which rune is which, when a swarm jumps and to how many enemies, what the damage over time is for each rune, when an
// enemy's death leaves a cloud and when each of the cloud's pulses falls. The production half is
// dc_witch_doctor_locust_swarm.cpp.
#include "dc_witch_doctor_clock.h"
#include "dc_witch_doctor_pick.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::LocustSwarm
{
    enum class Rune
    {
        None,
        SearingLocusts, // a larger damage over time, Fire
        Pestilence,     // may jump to two enemies instead of one, Poison
        CloudOfInsects, // the swarmed deal less damage, Physical
        DevouringSwarm, // Mana while the first enemy is swarmed, Cold
        DiseasedSwarm   // an enemy killed while swarmed leaves a cloud, Poison
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Searing Locusts")
            return Rune::SearingLocusts;
        if (name == "Pestilence")
            return Rune::Pestilence;
        if (name == "Cloud of Insects")
            return Rune::CloudOfInsects;
        if (name == "Devouring Swarm")
            return Rune::DevouringSwarm;
        if (name == "Diseased Swarm")
            return Rune::DiseasedSwarm;
        return Rune::None;
    }

    // "Swarm Jump Time Min" and "Swarm Jump Time Delta": the seconds before a swarm jumps, the least plus a roll of 0
    // to 1 of the delta.
    inline double JumpDelay(double minSeconds, double deltaSeconds, double roll)
    {
        return std::max(0.0, minSeconds) + std::max(0.0, deltaSeconds) * std::clamp(roll, 0.0, 1.0);
    }

    // "Locust Swarm has a {proc_chance_pct} chance to jump to two additional enemies instead of one": the enemies a
    // jump reaches, given a roll of 0 to 100.
    inline unsigned Jumps(Rune rune, double chancePct, double roll)
    {
        return rune == Rune::Pestilence && roll < chancePct ? 2u : 1u;
    }

    // The damage over time's total: the rune's own for Searing Locusts, the skill's for the others (Diseased Swarm
    // states its cloud's damage as its own).
    inline double SwarmTotal(Rune rune, double skillPct, double runePct)
    {
        return rune == Rune::SearingLocusts ? runePct : skillPct;
    }

    // "Enemies killed while affected by Locust Swarm leave behind a cloud": whether an enemy found dead with
    // `leftSeconds` of swarm left left one.
    inline bool LeavesCloud(Rune rune, bool dead, double leftSeconds)
    {
        return rune == Rune::DiseasedSwarm && dead && leftSeconds > 0;
    }

    // The cloud's pulses: the milliseconds after it forms the `index`th falls, the first a pulse after.
    inline std::uint32_t CloudPulseMs(unsigned index, double tickSeconds)
    {
        return std::uint32_t((tickSeconds > 0 ? tickSeconds : 0.0) * 1000.0 * (index + 1) + 0.5);
    }

    // The production half (dc_witch_doctor_locust_swarm.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // No hit of the cast itself: the swarm's ticks are the damage.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets`: the swarm settles on the enemy aimed at and starts to jump.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::WitchDoctor::LocustSwarm

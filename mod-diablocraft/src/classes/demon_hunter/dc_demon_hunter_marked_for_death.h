#pragma once
// Marked for Death's rules that need no core type, header-only so tests/demon_hunter_marked_for_death compiles this
// exact code: which rune is which, how a mark runs out, what each enemy takes of Grim Reaper's share, which enemies
// Contagion spreads to, what Death Toll heals. The production half is dc_demon_hunter_marked_for_death.cpp.
#include "dc_demon_hunter_clock.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <numeric>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::MarkedForDeath
{
    enum class Rune
    {
        None,
        GrimReaper,    // a share of the damage the marked enemy takes goes to the enemies round it
        Contagion,     // the mark spreads when the enemy dies
        ValleyOfDeath, // an area marked in place of an enemy
        MortalEnemy,   // Hatred for the attacks the Demon Hunter makes at the marked enemy
        DeathToll      // attackers heal when they damage the marked enemy
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Grim Reaper")
            return Rune::GrimReaper;
        if (name == "Contagion")
            return Rune::Contagion;
        if (name == "Valley of Death")
            return Rune::ValleyOfDeath;
        if (name == "Mortal Enemy")
            return Rune::MortalEnemy;
        if (name == "Death Toll")
            return Rune::DeathToll;
        return Rune::None;
    }

    // The game time (ms) a mark made at `nowMs` that lasts `seconds` is over at; none for no seconds.
    inline std::uint64_t EndsAt(std::uint64_t nowMs, double seconds)
    {
        return nowMs + std::uint64_t(seconds > 0 ? seconds * 1000.0 : 0.0);
    }

    // Whether a mark that ends at `endsMs` is still on at `nowMs`.
    inline bool On(std::uint64_t endsMs, std::uint64_t nowMs)
    {
        return nowMs < endsMs;
    }

    // "{damage_share_pct} of damage dealt to the marked enemy is also divided evenly among all enemies within
    // {radius_yards} yards": what each of `others` takes of a hit of `damage`. Nobody to share with, or nothing to
    // share, nothing.
    inline double SharePerEnemy(double damage, double sharePct, std::size_t others)
    {
        return others && damage > 0 && sharePct > 0 ? damage * sharePct / 100.0 / double(others) : 0.0;
    }

    // "the mark spreads to the closest {target_count} enemies": the places in `distances` of the `count` nearest,
    // nearest first, a tie keeping its order.
    inline std::vector<std::size_t> Nearest(std::vector<double> const& distances, std::size_t count)
    {
        std::vector<std::size_t> order(distances.size());
        std::iota(order.begin(), order.end(), std::size_t(0));
        std::stable_sort(order.begin(), order.end(),
                         [&](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        order.resize(std::min(order.size(), count));
        return order;
    }

    // "Mark an area on the ground of {radius_yards} yard radius": whether a point `distance` from its middle is in it.
    inline bool InArea(double distance, double radius)
    {
        return radius > 0 && distance <= radius;
    }

    // "Attackers heal for up to {heal_pct} of their maximum Life": what one attack heals.
    inline double LifeBack(double maxLife, double pct)
    {
        return std::max(0.0, maxLife) * std::max(0.0, pct) / 100.0;
    }

    // The production half (dc_demon_hunter_marked_for_death.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The cast hits nothing of its own (the file gives it 0.0001 of weapon damage).
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets`: the mark is put on the enemy, or the area on the ground.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // `player` landed a direct hit of `spellId` on `target`: Mortal Enemy's Hatred, Death Toll's heal, each scaled by that
    // spell's proc coefficient.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::MarkedForDeath

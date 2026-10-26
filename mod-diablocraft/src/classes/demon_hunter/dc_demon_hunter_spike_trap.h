#pragma once
// Spike Trap's rules that need no core type, header-only so tests/demon_hunter_spike_trap compiles this exact code:
// which rune is which, how long a trap takes to arm, how far its blast reaches, where Scatter lays its traps, when each
// trap of a chain reaction goes off and which enemies Lightning Rod's chain takes. The production half is
// dc_demon_hunter_spike_trap.cpp.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <utility>
#include <vector>

class Player;
struct Position;

namespace DC::Combat::DemonHunter::SpikeTrap
{
    enum class Rune
    {
        None,
        ImpalingSpines, // enemies near are immobilized when it is laid, Physical
        EchoingBlast,   // the blast slows, Cold
        CustomTrigger,  // a Hatred generator detonates it too, a wider blast, Fire
        Scatter,        // two traps at once, Fire
        LightningRod    // the blast is lightning that chains, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Impaling Spines")
            return Rune::ImpalingSpines;
        if (name == "Echoing Blast")
            return Rune::EchoingBlast;
        if (name == "Custom Trigger")
            return Rune::CustomTrigger;
        if (name == "Scatter")
            return Rune::Scatter;
        if (name == "Lightning Rod")
            return Rune::LightningRod;
        return Rune::None;
    }

    // The seconds a trap takes to arm: the skill's, Impaling Spines' longer by the file's modifier, Custom Trigger's
    // own.
    inline double ArmSeconds(Rune rune, double base, double impalingExtra, double customTrigger)
    {
        return rune == Rune::ImpalingSpines ? base + impalingExtra : rune == Rune::CustomTrigger ? customTrigger : base;
    }

    // The yards a trap's blast reaches: the skill's radius, wider for Custom Trigger and for Lightning Rod.
    inline double BlastRadius(Rune rune, double base, double customBonus, double rodBonus)
    {
        return rune == Rune::CustomTrigger ? base + customBonus : rune == Rune::LightningRod ? base + rodBonus : base;
    }

    // Scatter lays `count` traps side by side across the aim, `spacing` yards apart, centred on the point: the sideways
    // yards of each. One trap lies on the point.
    inline std::vector<double> Layout(unsigned count, double spacing)
    {
        std::vector<double> sideways;
        for (unsigned trap = 0; trap < count; ++trap)
            sideways.push_back((double(trap) - (double(count) - 1.0) / 2.0) * spacing);
        return sideways;
    }

    // "the trap and all other traps will explode in a chain reaction": the milliseconds after the detonation the
    // `order`th trap (0 first) goes off.
    inline std::uint32_t ExplosionDelayMs(unsigned order, double gapSeconds)
    {
        return gapSeconds > 0 ? std::uint32_t(order * gapSeconds * 1000.0 + 0.5) : 0u;
    }

    // Whether a cast detonates the traps: another Hatred spender does (never Spike Trap itself), and Custom Trigger's
    // Hatred generators too.
    inline bool Detonates(bool spikeTrap, bool spender, bool generator, Rune rune)
    {
        return !spikeTrap && (spender || (generator && rune == Rune::CustomTrigger));
    }

    // Lightning Rod: "lightning chain hits up to {target_count} enemies within {radius_yards:chain} yards": of the
    // enemies in the trap's blast (`distances` from the trap), the nearest `most` within `chain` yards, nearest first.
    inline std::vector<std::size_t> Chain(std::vector<double> const& distances, double chain, unsigned most)
    {
        std::vector<std::size_t> near;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] <= chain)
                near.push_back(i);
        std::stable_sort(near.begin(), near.end(),
                         [&distances](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        if (near.size() > most)
            near.resize(most);
        return near;
    }

    // "{damage_pct} weapon damage as Lightning over {hit_count} hits": the percent of one hit.
    inline double HitPct(double total, unsigned hits)
    {
        return hits ? total / hits : 0.0;
    }

    // The production half (dc_demon_hunter_spike_trap.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The cast lays traps, it hits nothing itself.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A cast began: another Hatred spender detonates the traps.
    void Casting(Player* player, std::uint32_t spellId);
    // The cast of a Spike Trap went off at `center`: the trap, or Scatter's two, is laid.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::DemonHunter::SpikeTrap

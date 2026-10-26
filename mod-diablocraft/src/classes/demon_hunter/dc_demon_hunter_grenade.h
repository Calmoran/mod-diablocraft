#pragma once
// Grenade's rules that need no core type, header-only so tests/demon_hunter_grenade compiles this exact code: which
// rune is which, how the three grenades of Grenade Cache fan out and what each pulse of Cluster Grenades deals. The
// production half is dc_demon_hunter_grenade.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
struct Position;
class Unit;

namespace DC::Combat::DemonHunter::Grenade
{
    enum class Rune
    {
        None,
        ColdGrenade,     // a cloud that chills and hurts over time, Cold
        ClusterGrenades, // pulses over a larger radius, Fire
        GrenadeCache,    // more grenades in a fan
        Tinkerer,        // more Hatred (paid by the class's Connected)
        StunGrenade      // a chance to stun, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Cold Grenade")
            return Rune::ColdGrenade;
        if (name == "Cluster Grenades")
            return Rune::ClusterGrenades;
        if (name == "Grenade Cache")
            return Rune::GrenadeCache;
        if (name == "Tinkerer")
            return Rune::Tinkerer;
        if (name == "Stun Grenade")
            return Rune::StunGrenade;
        return Rune::None;
    }

    // "Throw out {projectile_count} grenades": the angles in degrees, from the line to the point aimed at, of the
    // grenades besides the one thrown at it, spread `spreadDegrees` apart and balanced on either side of the line.
    // Three grenades are one on each side; a count of one or none throws no more.
    inline std::vector<double> FanOffsets(std::size_t count, double spreadDegrees)
    {
        std::vector<double> offsets;
        for (std::size_t i = 0; i < count; ++i)
        {
            double const place = double(i) - double(count - 1) / 2.0;
            if (place != 0.0)
                offsets.push_back(place * spreadDegrees);
        }
        return offsets;
    }

    // "{damage_pct} weapon damage as Fire over a {radius_yards} yard radius": the weapon damage percent of one of
    // `pulses` pulses that share the rune's total. No pulses, the total at once.
    inline double PulsePct(double totalPct, unsigned pulses)
    {
        return pulses ? totalPct / pulses : totalPct;
    }

    // The seconds after the throw that the pulse of place `index` (0 for the first, at once) goes off.
    inline double PulseAfter(unsigned index, double gapSeconds)
    {
        return gapSeconds * index;
    }

    // "Min Throw Distance": a grenade aimed nearer than `minimum` yards lands that far away, along the line of the aim.
    inline double ThrownYards(double aimedYards, double minimum)
    {
        return aimedYards < minimum ? minimum : aimedYards;
    }

    // "Damage falls off": the percent of its damage a hit keeps `distance` yards from the middle of a blast of `radius` yards: all of it at the
    // middle, falling in a straight line to `edgePct` percent at the edge and beyond it. No radius, all of it.
    inline double KeptPct(double distance, double radius, double edgePct)
    {
        if (radius <= 0 || distance <= 0)
            return 100.0;
        double const share = distance >= radius ? 1.0 : distance / radius;
        return 100.0 - (100.0 - edgePct) * share;
    }

    // The production half (dc_demon_hunter_grenade.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The grenade's own hit at the point aimed at, which every rune but Cluster Grenades inherits (Cluster Grenades'
    // hit is its first pulse).
    std::optional<double> BasePct(std::uint32_t spellId);
    // The grenade's hit landed on `target`: Stun Grenade's chance.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The point aimed at, moved out along the aim to the minimum throw distance (6 yards, 8 for Cluster Grenades).
    void Aim(Player* player, std::uint32_t spellId, Position& center);
    // The grenade exploded at `center`: the cloud, the pulses, the rest of the fan.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // A hit of `spellId` on `target` is being computed: a grenade's blast hurts less toward its edge.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, Factors& out);
} // namespace DC::Combat::DemonHunter::Grenade

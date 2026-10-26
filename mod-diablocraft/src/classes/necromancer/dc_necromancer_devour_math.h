#pragma once
// The rules of Devour's runes that need no core type, header-only so tests/necromancer_devour compiles this exact code:
// which rune is which, the Essence of the corpses and minions consumed, Cannibalize's heal, the aura's radius and the
// sums Voracious and Satiated stack. The production half is dc_necromancer_devour.cpp; the corpses are the shared
// combat/dc_corpses_math.h.
#include <algorithm>
#include <cstddef>
#include <string_view>

namespace DC::Combat::Necromancer::Devour
{
    enum class Rune
    {
        None,
        Cannibalize,
        Ruthless,
        Voracious,
        DevouringAura,
        Satiated
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Cannibalize")
            return Rune::Cannibalize;
        if (name == "Ruthless")
            return Rune::Ruthless;
        if (name == "Voracious")
            return Rune::Voracious;
        if (name == "Devouring Aura")
            return Rune::DevouringAura;
        if (name == "Satiated")
            return Rune::Satiated;
        return Rune::None;
    }

    // "to restore {gain_resource} Essence per corpse": the Essence of `count` consumed.
    inline double EssenceOf(double perOne, std::size_t count)
    {
        return perOne > 0 ? perOne * double(count) : 0.0;
    }

    // "Each corpse consumed also restores {heal_pct} health": the Life of `corpses` consumed.
    inline double HealOf(double maxLife, double healPct, std::size_t corpses)
    {
        return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 * double(corpses) : 0.0;
    }

    // "The range of this effect is increased by {radius_share_pct} of your gold pickup radius": the aura's radius, the
    // increase held to `maxIncreaseYards` (the power's Max Radius Increase; none stated, no limit).
    inline double AuraRadius(double baseYards, double sharePct, double pickupYards, double maxIncreaseYards)
    {
        double increase = sharePct > 0 && pickupYards > 0 ? pickupYards * sharePct / 100.0 : 0.0;
        if (maxIncreaseYards > 0)
            increase = std::min(increase, maxIncreaseYards);
        return std::max(0.0, baseYards) + increase;
    }

    // "Additionally consumes your minions": the cast needs a corpse, or for Ruthless a minion.
    inline bool CanDevour(Rune rune, std::size_t corpses, unsigned minions)
    {
        return corpses > 0 || (rune == Rune::Ruthless && minions > 0);
    }

    // "Becomes an aura": a cast of the aura rune turns the aura on or off; the others are the cast itself.
    inline bool TogglesAnAura(Rune rune)
    {
        return rune == Rune::DevouringAura;
    }

    // The aura is felt every `pulseSeconds` while on; the pulses a clock of `ms` more adds to what it had.
    inline unsigned PulsesDue(double& clockMs, double diffMs, double pulseSeconds)
    {
        clockMs += diffMs;
        if (pulseSeconds <= 0)
        {
            clockMs = 0;
            return 0;
        }
        unsigned due = 0;
        while (clockMs >= pulseSeconds * 1000.0)
        {
            clockMs -= pulseSeconds * 1000.0;
            ++due;
        }
        return due;
    }
} // namespace DC::Combat::Necromancer::Devour

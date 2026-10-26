#pragma once
// The rules of Siphon Blood's channel that need no core type, header-only so tests/necromancer_siphon_blood compiles
// this exact code: which rune is which, how often it strikes and what a strike is worth, Power Shift's stacks, the
// Essence a strike pays and the clock that tells how many strikes and heals are due. The production half is
// dc_necromancer_siphon_blood.cpp.
#include <algorithm>
#include <string_view>

namespace DC::Combat::Necromancer::SiphonBlood
{
    enum class Rune
    {
        None,
        Suppress,
        PurityOfEssence,
        DrainLife,
        PowerShift,
        BloodSucker
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Suppress")
            return Rune::Suppress;
        if (name == "Purity of Essence")
            return Rune::PurityOfEssence;
        if (name == "Drain Life")
            return Rune::DrainLife;
        if (name == "Power Shift")
            return Rune::PowerShift;
        if (name == "Blood Sucker")
            return Rune::BloodSucker;
        return Rune::None;
    }

    // "Damage Interval Base" seconds before attack speed: the seconds between two strikes. No speed, no strikes.
    inline double TickSeconds(double baseSeconds, double attacksPerSecond)
    {
        return baseSeconds > 0 && attacksPerSecond > 0 ? baseSeconds / attacksPerSecond : 0.0;
    }

    // The skill's weapon damage is a number for a second of channel: one strike carries the share of the seconds
    // between strikes.
    inline double TickPct(double damagePct, double tickSeconds)
    {
        return damagePct * std::max(0.0, tickSeconds);
    }

    // "Damage is increased by {damage_bonus_pct} each time damage is dealt. Max {max_stacks_count} stacks": the strike
    // after `stacks` strikes.
    inline double PowerShiftPct(double pct, double bonusPct, unsigned stacks)
    {
        return pct * (1.0 + std::max(0.0, bonusPct) / 100.0 * stacks);
    }

    inline unsigned NextStacks(unsigned stacks, unsigned maxStacks)
    {
        return std::min(stacks + 1, maxStacks);
    }

    // "Essence gained is increased to {gain_resource} while you are at full health": the Essence of one strike.
    inline double EssenceOfTick(double gained, double gainedAtFullHealth, bool fullHealth)
    {
        return fullHealth && gainedAtFullHealth > 0 ? gainedAtFullHealth : gained;
    }

    // A clock that has run `clock` ms and is given `diff` more: how many whole `interval`s are due, the rest left in
    // `clock`. No interval, none due; never more than `cap` at once.
    inline unsigned Due(double& clock, double diff, double interval, unsigned cap = 20)
    {
        clock += diff;
        if (interval <= 0)
        {
            clock = 0;
            return 0;
        }
        unsigned due = 0;
        while (clock >= interval && due < cap)
        {
            clock -= interval;
            ++due;
        }
        if (clock >= interval)
            clock = 0;
        return due;
    }
} // namespace DC::Combat::Necromancer::SiphonBlood

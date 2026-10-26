#pragma once
// Preparation's rules that need no core type, header-only so tests/demon_hunter_preparation compiles this exact code:
// which rune is which, what each rune restores at the cast, what a tick of Focused Mind gives, when Backup Plan keeps
// the cooldown away. The production half is dc_demon_hunter_preparation.cpp.
#include "dc_demon_hunter_clock.h"
#include "dc_demon_hunter_dot.h"

#include <algorithm>
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Classes
{
    struct Slot;
}

namespace DC::Combat::DemonHunter::Preparation
{
    enum class Rune
    {
        None,
        Punishment,   // Hatred as well, a shorter cooldown (the record holds the cooldown)
        Invigoration, // the Discipline maximum is higher while it is on the bar
        FocusedMind,  // the Discipline comes over time
        BattleScars,  // Life
        BackupPlan    // a chance the cooldown is not kept
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Punishment")
            return Rune::Punishment;
        if (name == "Invigoration")
            return Rune::Invigoration;
        if (name == "Focused Mind")
            return Rune::FocusedMind;
        if (name == "Battle Scars")
            return Rune::BattleScars;
        if (name == "Backup Plan")
            return Rune::BackupPlan;
        return Rune::None;
    }

    // What a cast restores: Discipline now, Hatred now, Discipline over time.
    struct Restore
    {
        double disciplineNow = 0;
        double hatredNow = 0;
        double disciplineOver = 0;
    };

    // `base` is the skill's Discipline ("Instantly restore {gain_resource} Discipline"), `own` the rune's own
    // `gain_resource`: Punishment's Hatred ("Restore {gain_resource} Hatred", the Discipline too), Focused Mind's
    // Discipline over time ("instead of restoring it immediately").
    inline Restore RestoreOf(Rune rune, double base, double own)
    {
        switch (rune)
        {
            case Rune::Punishment:
                return {base, own, 0};
            case Rune::FocusedMind:
                return {0, 0, own};
            default:
                return {base, 0, 0};
        }
    }

    // "Gain {gain_resource} Discipline over {dot_duration_seconds} seconds": what one tick of `tickSeconds` gives.
    inline double RegenTick(double total, double seconds, double tickSeconds)
    {
        return Dot::TickPct(total, Dot::Ticks(seconds, tickSeconds));
    }

    // "Gain {heal_pct} Life when using Preparation": the Life of a maximum.
    inline double HealOf(double maxLife, double pct)
    {
        return std::max(0.0, maxLife) * std::max(0.0, pct) / 100.0;
    }

    // "There is a {proc_chance_pct} chance that Preparation's cooldown will not be triggered": whether a roll of 0 to
    // 100 keeps it away.
    inline bool CooldownSkipped(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // The production half (dc_demon_hunter_preparation.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The cast resolved: the restoring, the Life, the cooldown that may not be kept.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The saved bar was written: Invigoration's higher maximum is on while that rune stands in a slot.
    void BarWritten(Player* player, std::vector<DC::Classes::Slot> const& bar);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::Preparation

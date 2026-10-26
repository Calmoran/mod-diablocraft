// Rend: the bleed (its aura script and the provider of its damage), the mark of Mutilate and the heal of Blood Lust.
#pragma once
#include "dc_barbarian_internal.h"
#include <optional>

namespace DC::Combat::Abilities::Rend
{
    using Shared::Row;
    using Shared::State;

    // Adds the damage bonus an enemy under Mutilate's mark takes.
    void OnTargetBonus(Unit* u, double& bonus);
    // A hit of the skill landed on `target`: Mutilate's mark.
    void OnHit(Player* p, Unit* target, Row const* r, Row const* b);
    // A tick of the bleed: Blood Lust heals.
    void OnTick(Player* p, uint32 id);
    // Rend's bleed on `unit` by the shell `skill` (spell `spellId`). A power can let it stack: a new application beside a running bleed
    // of the same rune is another bleed of that aura, until the cap, and replaces the oldest at it. Otherwise it replaces the running
    // bleed. `keepRunning` (a bleed applied by another skill's hit) applies only while the enemy carries fewer bleeds of the player's
    // than the cap. False for any shell that is not Rend's.
    bool Apply(Player* player, Unit* unit, std::uint32_t spellId, std::string const& skill, bool keepRunning = false);
    // A hit of the shell `skill` being resolved: Rend's hit applies the bleed and does not deal damage itself.
    std::optional<bool> OnResolve(Player* player, Unit* target, std::uint32_t spellId, std::string const& skill);
    // The bleed's aura script and the provider of its damage.
    void RegisterScripts();
    // Whether `skill` is Rend, whose ticks carry average crit.
    bool DamageOverTime(std::string const& skill);
} // namespace DC::Combat::Abilities::Rend

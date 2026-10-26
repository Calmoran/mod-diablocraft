// Teleport: the leap's landing and its facing, Reversal's return window, Wormhole's grace window, Safe Passage and Calamity.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::Teleport
{
    // The cast has begun, before the leap: Reversal's recast flag and where the Wizard stood. Called with the module lock held.
    void Begin(Player* player, Shared::State& state, uint32 spellId);
    // The cast has resolved, after the leap moved the Wizard: the arrival effects of the runes and Wormhole's window.
    void Cast(Player* player, uint32 id);
    // A Teleport cast or the Archon form's Teleport ability.
    bool Travels(uint32 id);
    // Turns the landing to face the way the Wizard travelled.
    void FaceTravel(Player* player, uint32 id);
    // The cast of the Reversal rune: the first opens the window, the recast inside it returns the Wizard.
    void ReversalCast(Player* player, uint32 id);
    // The window is over without a return: puts on what is left of the cooldown. Safe to call with no window open.
    void ReversalEnd(Player* player);
} // namespace DC::Combat::Wizard::Teleport

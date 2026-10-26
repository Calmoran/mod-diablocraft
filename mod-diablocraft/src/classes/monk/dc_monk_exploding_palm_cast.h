#pragma once
// Exploding Palm: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_exploding_palm.h.
#include "dc_monk.h"

namespace DC::Combat::Monk::ExplodingPalm
{
    // Whether `spellId` is Exploding Palm or one of its runes.
    bool Is(std::uint32_t spellId);
    // The weapon damage of the cast itself: none (the palm only marks; the bleed and the explosion are the damage).
    std::optional<double> BasePct(std::uint32_t spellId);
    // After the cast: the palm on the enemy struck (and Shocking Grasp's arc), its bleed, The Flesh is Weak's debuff.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // N-APPLYAURA (Gungdo Gear): the palm of `spellId` put on `enemy` as the cast's would (its mark, its bleed, The Flesh
    // is Weak's debuff), without a cast and for no cost. False for a spell that is not Exploding Palm's or an enemy that is not alive.
    bool Apply(Player* player, Unit* enemy, std::uint32_t spellId);
    // Registers the death script that sets the explosions off.
    void RegisterScripts();
} // namespace DC::Combat::Monk::ExplodingPalm

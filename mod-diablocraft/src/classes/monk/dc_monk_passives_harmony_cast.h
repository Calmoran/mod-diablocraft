#pragma once
// Six Monk passives (Harmony, Combination Strike, Near Death Experience, Unity,
// Momentum, Mythic Rhythm): what dc_monk.cpp, dc_monk_effects.cpp and dc_combat.cpp call. The pure rules are in
// dc_monk_passives_harmony.h.
#include "dc_monk.h"

namespace DC::Combat::Monk::PassivesHarmony
{
    // The separate multipliers these passives put on a hit of `spellId` by `player` (Monk::Multipliers, step 8 of the hit):
    // Combination Strike, Mythic Rhythm, Momentum, and Unity's two sides. Nothing for a player with none of them.
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
    // A Monk skill was cast (Monk::Cast, before its own dispatch): Combination Strike remembers the generator used,
    // Mythic Rhythm's primed bonus is spent by a spender.
    void Cast(Player* player, std::uint32_t spellId);
    // An attack of `spellId` hit at least one enemy (Monk::Connected): a Spirit Generator's hit counts for Mythic
    // Rhythm.
    void Connected(Player* player, std::uint32_t spellId);
    // The scripts of Momentum's distance, Harmony's resistances and Near Death Experience's fatal-damage rule.
    void RegisterScripts();
} // namespace DC::Combat::Monk::PassivesHarmony

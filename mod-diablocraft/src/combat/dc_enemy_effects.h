#pragma once
// The timed effects on an enemy that any class's skill may put: "enemies take N% more damage for S seconds", "enemies deal N% less for
// S seconds". The module keeps them as numbers with an end time (no aura, no icon) and the damage path reads them; a class
// includes this and calls these, and one class's folder defines them.
#include <cstdint>

class Unit;

namespace DC::Combat::EnemyEffects
{
    // `key` names the effect (the rune's spell id): casting a key again refreshes it, and with `maxStacks` above 1 each cast adds a
    // stack. Seconds of 0 or less put nothing.
    // "enemies take pct additional damage from all attacks".
    void Taken(Unit* enemy, std::uint32_t key, double pct, double seconds, unsigned maxStacks = 1);
    // "enemies deal pct less damage".
    void Weaken(Unit* enemy, std::uint32_t key, double pct, double seconds, unsigned maxStacks = 1);
    // Ends what `key` put on the enemy (both kinds), before its time: another curse took its place.
    void Remove(Unit* enemy, std::uint32_t key);
} // namespace DC::Combat::EnemyEffects

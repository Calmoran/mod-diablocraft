#pragma once
// Siphon Blood and its five runes: the channel that strikes the targeted enemy every few tenths of a second, pays
// Essence for each strike and heals the Necromancer every second. The rules that need no core type are
// dc_necromancer_siphon_blood_math.h.
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Necromancer::SiphonBlood
{
    // The engine's hit of the channel's cast is none: the channel strikes for itself. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // Whether the skill pays its Essence on each strike rather than once for the cast.
    bool PaysByStrike(std::uint32_t spellId);
    // The channel began on `targets`: the first strike lands at once.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The channel's strikes and heals (Combat::RegisterScripts).
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::SiphonBlood

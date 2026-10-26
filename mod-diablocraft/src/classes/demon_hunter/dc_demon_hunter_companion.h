#pragma once
// Companion and its five runes on the shared minions piece (combat/dc_minions.h): the permanent pet of the form on the
// bar, what each form does while it stands, and what the press does. The creatures are demon_hunter_summons.csv. The
// rules that need no core type are dc_demon_hunter_companion_math.h.
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::Companion
{
    // Whether `spellId` is the skill or one of its runes.
    bool Is(std::uint32_t spellId);
    // The pet is the damage; the cast itself hits nothing.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The press of the skill or a rune resolved: what the active of the form does.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The kind of the pet and the keeper that holds it; at startup.
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::Companion

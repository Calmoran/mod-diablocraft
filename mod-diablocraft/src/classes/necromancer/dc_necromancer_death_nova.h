#pragma once
// Death Nova and its five runes: Tendril Nova's heal, Bone Nova's smaller nova, Blood Nova's cost in Life, Blight's
// patch and Unstable Compound's growing radius. The nova itself is the engine's (a spell record and the sheet's
// numbers, hitting everyone within the radius); this file holds what the record cannot say. The rules that need no core
// type are dc_necromancer_death_nova_math.h.
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Necromancer::DeathNova
{
    // The runes that strike for themselves have no hit of the engine's. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A Necromancer cast began: Blood Nova takes its Life, and any cast but Death Nova ends Unstable Compound's growth.
    void Casting(Player* player, std::uint32_t spellId);
    // The nova resolved on `targets`: the rune's part.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Necromancer::DeathNova

#pragma once
// Bone Spikes and its five runes: the stun, the line, the pillars, the frost and the bleed. The skill's hit on the area is
// the engine's (a spell record and the sheet's numbers); this file holds what the record cannot say. The rules that need
// no core type are dc_necromancer_bone_spikes_math.h.
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::BoneSpikes
{
    // The weapon damage of the engine's hit: none for the runes that deal their own (Path of Bones, Bone Pillars), the
    // skill's number for Blood Spikes (its own number is the bleed's). nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The Essence a cast generates when it is not the sheet's number (Path of Bones). nullopt for every other spell.
    std::optional<double> GeneratedEssence(std::uint32_t spellId);
    // The cast hit `targets`: Sudden Impact's stun, Frost Spikes' slow, Blood Spikes' bleed.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The cast was aimed at `center`: Path of Bones' line and Bone Pillars' strikes.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::Necromancer::BoneSpikes

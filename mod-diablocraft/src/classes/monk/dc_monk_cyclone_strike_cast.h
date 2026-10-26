#pragma once
// Cyclone Strike: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_cyclone_strike.h.
#include <cstdint>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Monk::CycloneStrike
{
    // Whether `spellId` is Cyclone Strike or one of its runes.
    bool Is(std::uint32_t spellId);
    // Before the hits (Combat::ResolveCast): pull up to the sheet's enemies in, freeze them (Wall of Wind), and replace
    // `targets` with the enemies the blast then reaches.
    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*>& targets);
    // After the hits: Soothing Breeze heals the Monk and the allies around.
    void Cast(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::Monk::CycloneStrike

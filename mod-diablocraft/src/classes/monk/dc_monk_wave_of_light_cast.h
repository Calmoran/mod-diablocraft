#pragma once
// Wave of Light: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_wave_of_light.h.
#include <cstdint>

class Player;
struct Position;

namespace DC::Combat::Monk::WaveOfLight
{
    // Whether `spellId` is Wave of Light or one of its runes.
    bool Is(std::uint32_t spellId);
    // The cast resolved with its ground point `aimed` (Combat::ResolveCast): the bell, the pillar, the rune's extras.
    void Cast(Player* player, std::uint32_t spellId, Position const& aimed);
} // namespace DC::Combat::Monk::WaveOfLight

#pragma once
// Serenity: what dc_monk.cpp dispatches to. The pure rules are in dc_monk_serenity.h.
#include <cstdint>

class Player;

namespace DC::Combat::Monk::Serenity
{
    // Whether `spellId` is Serenity or one of its runes.
    bool Is(std::uint32_t spellId);
    // The cast has resolved (the core has installed the cooldown): the shield, the rune's extras, the delayed cooldown.
    void Cast(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::Monk::Serenity

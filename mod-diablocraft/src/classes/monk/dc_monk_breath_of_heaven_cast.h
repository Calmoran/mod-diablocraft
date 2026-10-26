#pragma once
// Breath of Heaven: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_breath_of_heaven.h.
#include <cstdint>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Monk::Breath
{
    // Whether `spellId` is Breath of Heaven or one of its runes.
    bool Is(std::uint32_t spellId);
    // The cast resolved: `targets` are the Monk and the allies within its radius.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // An attack of the Monk's connected (Monk::Connected, once per attack): Infused with Light's extra Spirit.
    void Attack(Player* player, bool generates);
} // namespace DC::Combat::Monk::Breath

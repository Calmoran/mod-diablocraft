#pragma once
// Deadly Reach: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_deadly_reach.h.
#include "dc_monk.h"

namespace DC::Combat::Monk::DeadlyReach
{
    // Whether `spellId` is Deadly Reach or one of its runes.
    bool Is(std::uint32_t spellId);
    // The weapon damage of the punch itself; nullopt for any other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The punch before it hits: the combo stage, and on the third hit the enemies between the cast's own 12 yards and
    // the 25 the third hit reaches.
    Punch Begin(Player* player, std::uint32_t spellId, Unit* primary);
    // After the hits: the third hit's extras, the knock-up, Foresight, Strike from Beyond's discount, Scattered Blows.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Punch const& punch);
    // A Monk skill that costs Spirit has been cast: Strike from Beyond's pending discount is paid back as Spirit.
    void Spent(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::Monk::DeadlyReach

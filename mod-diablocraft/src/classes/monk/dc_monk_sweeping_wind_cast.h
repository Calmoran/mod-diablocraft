#pragma once
// Sweeping Wind: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_sweeping_wind.h.
#include <cstdint>
#include <optional>

class Player;
class Unit;

namespace DC::Combat::Monk::Wind
{
    // Whether `spellId` is Sweeping Wind or one of its runes.
    bool Is(std::uint32_t spellId);
    // The cast itself deals nothing (the vortex does): 0 for Sweeping Wind's spells, nullopt for any other.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast: the vortex starts, with one stack, and ticks until its time runs out.
    void Cast(Player* player, std::uint32_t spellId);
    // A hit of the Monk's landed (Monk::Landed): "refreshed each time you strike an enemy with a melee attack".
    void Landed(Player* player);
    // The enemy a hit of the Monk's landed on (Monk::Landed): the last enemy hit, which the 4-piece's decoy is put beside.
    void Struck(Player* player, Unit* target);
    // Whether the Monk's vortex is up now, and how many stacks it holds (0 with none): read by the item powers (a `skills_active`
    // row on Sweeping Wind, a per-stack damage row).
    bool Active(Player const* player);
    unsigned Stacks(Player const* player);
    // An attack of the Monk's connected (Monk::Connected, once per attack): a Spirit Generator's adds a stack, up to the
    // maximum, and at the maximum Cyclone spawns its tornado.
    void Attack(Player* player, bool generates);
} // namespace DC::Combat::Monk::Wind

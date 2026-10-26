#pragma once
// Frailty and its five runes: the curse that kills the enemies it holds when their Life falls under a share. Early Grave kills at a
// higher share and costs Life, Harvest Essence pays Essence for each cursed death, Volatile Death makes the dead explode, Scent of Blood
// makes the minions hit the cursed harder and Aura of Frailty curses everything around the Necromancer. The rules that need no core type
// are dc_necromancer_frailty_math.h.
#include <cstdint>
#include <optional>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::Frailty
{
    // A curse deals nothing of its own. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast began: Early Grave takes its Life.
    void Casting(Player* player, std::uint32_t spellId);
    // The cast was aimed at `center`.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // Scent of Blood: the percent more damage a minion of the Necromancer's deals to `enemy`; 0 for an enemy not so cursed.
    double MinionBonus(Player* player, Unit* enemy);
    // The kill hook of the runes that answer the death of a cursed enemy; at startup.
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::Frailty

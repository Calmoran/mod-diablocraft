#pragma once
// Grim Scythe and its five runes: Blood Scythe's heal, Execution's decapitation, Frost Scythe's attack speed, Dual
// Scythes' push and Cursed Scythe's curse. The skill's hit on the cone is the engine's (a spell record and the sheet's
// numbers) and the Essence it pays for each enemy is the dispatch's; this file holds what the record cannot say. The
// rules that need no core type are dc_necromancer_grim_scythe_math.h.
#include <cstdint>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Necromancer::GrimScythe
{
    // The cast hit `targets`: what each rune does to them or for the Necromancer.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Necromancer::GrimScythe

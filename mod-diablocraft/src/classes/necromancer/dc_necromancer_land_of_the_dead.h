#pragma once
// Land of the Dead and its five runes: for its duration every corpse skill is used at will (the shared corpses meet a request
// with corpses made on the spot). Invigoration makes the Necromancer's skills cost nothing, Frozen Lands freezes the enemies
// around it now and then, Plaguelands plagues them, Land of Plenty heals for each kill and Shallow Graves extends the land for
// every few kills. The rules that need no core type are dc_necromancer_land_of_the_dead_math.h.
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Necromancer::LandOfTheDead
{
    // The cast has no hit of its own. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved: the land opens.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The kill hook of Land of Plenty and Shallow Graves; at startup.
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::LandOfTheDead

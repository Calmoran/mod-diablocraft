#pragma once
// The Necromancer's minions on the shared piece (combat/dc_minions.h): the kinds it defines from its sheets, the
// keepers of the two skills that hold a standing minion (Command Skeletons, Command Golem), and the calls the skills
// that raise one make. The creatures are necromancer_summons.csv. The corpse a Revive raises from is the corpses' piece
// (not here): Revive takes the look of the corpse it is given.
#include <cstdint>

class Creature;
class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::Pets
{
    // Skeletal Mage: raises a mage of the record cast (0: the rune on the bar) at `at`, its damage `bonusPct` percent
    // higher (Singularity). It lasts the skill's seconds; at most the cap stand.
    Creature* RaiseMage(Player* owner, Position const& at, std::uint32_t record = 0, double bonusPct = 0);
    // Revive: raises a minion of the rune on the bar at `at` wearing the look `display` of the corpse it came from.
    Creature* Revive(Player* owner, Position const& at, std::uint32_t display, std::uint32_t record = 0,
                     std::uint32_t corpseEntry = 0);
    // Simulacrum: raises the copy of the Necromancer, or (`bone`) the Simulacrum of Bone that Blood and Bone adds, on the other side.
    Creature* Simulacrum(Player* owner, bool bone = false);
    // Command Skeletons' active: the skeletons strike `target` with the rune on the bar's bonus for `ms`.
    void CommandSkeletons(Player* owner, Unit* target, std::uint32_t ms);
    // The kinds and the keepers; at startup.
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::Pets

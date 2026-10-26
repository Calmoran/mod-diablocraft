#pragma once
// The Witch Doctor's passives that need code: Jungle Fortitude, Circle of Life, Spiritual Attunement, Gruesome Feast,
// Blood Ritual and Bad Medicine. The rules that need no core type are dc_witch_doctor_passives_math.h; the numbers are
// witch_doctor_passive_values.csv (skill = the passive's name), read through each passive's record.
#include <cstdint>

class Player;
class Unit;
struct Position;

namespace DC::Combat::WitchDoctor::Passive
{
    // A hit of `spellId` landed on `target`: Bad Medicine weakens the enemy a Poison hit struck.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The damage `victim` takes after the passives (Jungle Fortitude's share for the Witch Doctor).
    double Reduce(Unit* victim, double damage);
    // The Witch Doctor was healed by a health globe (Gruesome Feast's Mana and Intelligence). The health globes do not
    // exist yet, so nothing calls it: the globes call it when they land.
    void GlobePicked(Player* player);
    // Circle of Life's Zombie Dog comes up at `where` for `player`. The pets are a piece of their own and the call does
    // nothing until that lands; the roll and the range are built and tested.
    void DogEmerges(Player* player, Position const& where);
    // The update script (the pool, the regeneration), the death and damage hooks and the cast hook; at startup.
    void Register();
} // namespace DC::Combat::WitchDoctor::Passive

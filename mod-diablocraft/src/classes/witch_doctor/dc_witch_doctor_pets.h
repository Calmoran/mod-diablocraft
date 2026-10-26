#pragma once
// The Witch Doctor's pets on the shared minions piece (combat/dc_minions.h): the Zombie Dogs and the Gargantuan
// (permanent), the Fetishes of the Army (a timed burst) and the Fetish Sycophants (the passive's summons). The
// creatures are witch_doctor_summons.csv; the rules that need no core type are dc_witch_doctor_pets_math.h. The skills
// that raise them call these; a skill's runes are its own bead's.
#include "Position.h"

#include <cstdint>
#include <functional>
#include <optional>
#include <string>

class Creature;
class Player;
class Unit;

namespace DC::Combat::WitchDoctor::Pets
{
    // The creature of every Fetish of the Army (witch_doctor_summons.csv): the daggers, the casters and the hunters.
    inline constexpr std::uint32_t FetishEntry = 900172;

    // Summon Zombie Dogs: raises the dogs the Witch Doctor is short of beside them, up to the skill's count and one
    // more for each passive that allows one. How many it raised.
    unsigned SummonDogs(Player* owner);
    // The Gargantuan: sends the one that stands away and raises a new one at `at`.
    Creature* RaiseGargantuan(Player* owner, Position const& at);
    // Where a Fetish of the Army comes to stand, and what happens when it has: `where` is told the ring point the Fetish was
    // to appear on and answers the point it appears on (none: the ring point); `landed` is told that point after it came.
    struct Arrival
    {
        std::function<Position(Player*, Position const&)> where;
        std::function<void(Player*, Position const&)> landed;
    };
    // Fetish Army: raises the skill's Fetishes (and `extra` more) on the ring round the Witch Doctor, one every spawn
    // interval, for the skill's seconds. How many it will raise.
    unsigned RaiseFetishes(Player* owner, unsigned extra = 0, Arrival arrival = {});
    // `count` Fetishes of the kind `key` (the Army's casters and hunters) on the same ring, the first `firstIndex` spawn intervals
    // after the cast. How many it will raise.
    unsigned RaiseOnRing(Player* owner, std::string const& key, unsigned count, unsigned firstIndex = 0);
    // One Zombie Dog raised at `at` when the Witch Doctor has room for one more (Boogie Man's, Circle of Life's: no dog is sent away
    // to make room); nullptr otherwise.
    Creature* RaiseDogAt(Player* owner, Position const& at);
    // Whether a Zombie Dog stands for the Witch Doctor (Sacrifice needs one).
    bool HasDog(Player* owner);
    // Sacrifice: banishes the oldest Zombie Dog and answers where it stood; nothing when none stands.
    std::optional<Position> SacrificeDog(Player* owner);
    // A hit of `spellId` landed on `target`: Fetish Sycophants' chance to summon a Fetish, scaled by the spell's proc
    // coefficient.
    void Landed(Player* owner, Unit* target, std::uint32_t spellId);
    // The kinds; at startup.
    void RegisterScripts();
} // namespace DC::Combat::WitchDoctor::Pets

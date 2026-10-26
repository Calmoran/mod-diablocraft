#pragma once
// The follower skills: the skills the hired follower casts and the passives it gives its player (contract docs/contracts/followers.md).
// The companion's AI asks Tick; the combat hooks ask Fatal; the loader asks RegisterScripts; the Follower window asks PickOf and PickSkill. Other folders include only this header.
#include <cstdint>
#include <string>

class Creature;
class Player;
class Unit;

namespace DC::Classes::Follower
{
void RegisterScripts();
// One look at the skills of the player's follower, from the companion's AI: `target` is the enemy it fights now (null when it
// follows), `diffMs` the time since its last update. Nothing unless the companion is out and alive.
void Tick(Player* player, Creature* companion, Unit* target, std::uint32_t diffMs);
// The player landed a critical hit (Combat's critical-hit call): Hysteria.
void Critical(Player* player);
// Percent more critical hit chance against `target` for the player's hits: 100 inside the Scoundrel's cloud, else 0.
double CritBonus(Player* player, Unit* target);
// The multiplier on a blow of the player's, melee or not (Combat's damage taken): the Enchantress' Powered Shield takes a share off ranged ones.
double TakenFactor(Player* player, bool melee);
// A blow of `damage` on the player: the follower's cheat-death skill saves it (the damage becomes 0), and a shield it raised holds off
// the blows after it.
void Fatal(Player* player, std::uint32_t& damage);
// The skill_id picked in a tier (1 to 4) of a follower (1 to 3) for this player; empty when none. The Follower window reads it.
std::string PickOf(Player const* player, unsigned follower, unsigned tier);
// Picks a skill by its skill_id for a follower's tier, with the checks of `.dc follower skill` (hub, out of combat, the tier open,
// a skill of that tier). Empty when the pick was made; else the refusal's words.
std::string PickSkill(Player* player, unsigned follower, unsigned tier, std::string const& skill);
} // namespace DC::Classes::Follower

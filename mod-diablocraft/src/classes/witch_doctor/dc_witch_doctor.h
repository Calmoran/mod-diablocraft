/*
 * World of DiabloCraft - the Witch Doctor's class code. The combat engine asks the class through these entry points,
 * each answered in the file of the mechanic it belongs to. Everything shared reads the class from dc_class_map and the
 * sheets; the Witch Doctor's name stays in this folder.
 */

#ifndef DC_WITCH_DOCTOR_H
#define DC_WITCH_DOCTOR_H

#include "../../combat/dc_damage_buckets.h"

#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::WitchDoctor
{
    // A cast or channel tick of `spellId` hit `enemies` enemies (Combat::Connected, once per attack): a skill whose
    // rune returns Mana per hit pays it for each enemy hit.
    void Connected(Player* player, std::uint32_t spellId, unsigned enemies);

    // The weapon-damage percentage a Witch Doctor skill's own hit deals, for the loader that gives every shell its hit (dc_combat.cpp).
    // nullopt for a spell the skills do not claim: the loader's own rule applies.
    std::optional<double> BasePct(std::uint32_t spellId);

    // A hit of `spellId` landed on `target` (Combat's ResolveHit and Strike): what a skill, rune or passive adds to the enemy struck.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);

    // A cast of `spellId` resolved its hits on `targets` (Combat::ResolveCast, after them and before Connected).
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);

    // The attacks a second of `spellId` before the other classes' and the items' factors, made faster for a skill that casts faster (Rain of Toads).
    double AttackSpeed(Player* player, std::uint32_t spellId, double base);

    // A cast of `spellId` aimed at the ground point `center` resolved (Combat::ResolveCast, after the hits): what a skill does at the
    // point it was aimed at (Corpse Spiders' jar, Hex's Fetish Shaman).
    void Ground(Player* player, std::uint32_t spellId, Position const& center);

    // A press of `spellId` before the core checks the cast (Combat's OnSpellCheckCast): true when the class took the press and the cast
    // is to be refused (the second press of the Angry Chicken is its explosion).
    bool Toggle(Player* player, std::uint32_t spellId);

    // The multipliers of a hit of `spellId` on `target` (Combat's ComputeHit, beside the other classes'): the passives' own and the
    // separate "increased damage done" categories of the skills (Sacrifice's Provoke the Pack).
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);

    // The damage `victim` takes after the Witch Doctor's passives (Combat's Mitigate, beside the Necromancer's Reduce).
    double Reduce(Unit* victim, double damage);

    // The Witch Doctor's scripts (Combat::RegisterScripts): the channel loops, the passives' update, death, damage and cast hooks, the
    // Fetish Shaman's kind and Unstable Form's death hook.
    void RegisterScripts();
} // namespace DC::Combat::WitchDoctor

#endif

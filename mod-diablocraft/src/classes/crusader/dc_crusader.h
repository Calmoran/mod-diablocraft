/*
 * World of DiabloCraft - the Crusader's class code. The combat engine asks the class through these seams
 * (Combat::ResolveCast, Mitigate, ComputeHit and the spell check); each is answered here, in the file of the skill it
 * belongs to. Everything shared reads the class from dc_class_map and the sheets; the Crusader's name stays in this
 * folder.
 */

#ifndef DC_CRUSADER_H
#define DC_CRUSADER_H

#include "../../combat/dc_damage_buckets.h"
#include "SharedDefines.h"

#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Crusader
{
    // The weapon-damage percentage a Crusader skill's own hit deals, for the loader that gives every shell its hit
    // (dc_combat.cpp). A rune states numbers of its own that are not the hit's (Retaliate's 140% is the answer to a
    // block), so the skills say here which number is the hit. nullopt for a spell that is not one of its hit-skills: the
    // loader's own rule applies.
    std::optional<double> BasePct(std::uint32_t spellId);

    // Whether a press of a Crusader skill may cast (Combat's OnSpellCheckCast, before the cost and the cooldown): the
    // result to refuse it with, SPELL_CAST_OK for every spell that needs nothing.
    SpellCastResult CanCast(Player* player, std::uint32_t spellId);

    // A cast or channel tick of `spellId` hit `enemies` enemies, at least one (Combat::Connected, once per attack, never
    // per enemy): a Crusader's primary pays the Wrath its sheet row generates, and the skills' own effects follow.
    void Connected(Player* player, std::uint32_t spellId, unsigned enemies);

    // A cast of `spellId` resolved its hits on `targets` (Combat::ResolveCast, after them and before Connected): what a
    // skill or rune does to or around the enemies it struck.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);

    // Before the hits of a cast of `spellId` at `target` (Combat::ResolveCast): what a skill does first, such as a charge.
    void Approach(Player* player, std::uint32_t spellId, Unit* target);

    // The multipliers of its own a hit of `spellId` takes (ComputeHit, beside every class's other multipliers).
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);

    // A cast of `spellId` landed on the ground at `center` (Combat::ResolveCast, beside the other classes' ground hook): what a skill does
    // at the place it was aimed.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);

    // A hit of `spellId` landed on `target` (Combat::ResolveHit and Strike, where every class's hook sits): what a skill does where it
    // lands, for the skills whose hit is a projectile and so never reaches Cast.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);

    // The critical hit chance, in percent, a hit of `spellId` on `target` gets on top of the sheet's (ComputeHit).
    double CritBonus(Player* player, Unit* target, std::uint32_t spellId);

    // `victim` blocked a hit of `attacker` (Combat::Mitigate, the one place a hit is blocked). Does nothing unless the
    // victim is a Crusader whose skills answer a block.
    void Blocked(Unit* victim, Unit* attacker);

    // `victim` took a hit of `attacker` that dealt damage (a melee or spell hit, not a periodic tick; the damage path's other class hook of the same name is beside it). Does nothing
    // unless the victim is a Crusader whose skill answers being hit while it lasts. `damage` is what the hit dealt, after the
    // victim's defences (Condemn's Reciprocate counts it).
    void Taken(Unit* victim, Unit* attacker, double damage);

    // The multiplier on a dodge chance a Crusader would have had (Combat's outcome hook and spell hook): 0 for one that can no
    // longer dodge, 1 for everyone else.
    double DodgeFactor(Unit const* unit);

    // A skill's attacks per second `base` with the Crusader's passives' share added (Combat::AttacksPerSecond and
    // HandAttacksPerSecond, beside the other classes' share); `base` itself for anyone else.
    double AttackSpeed(Player* player, std::uint32_t spellId, double base);
    // The damage `victim` is about to take, after its own mitigation (Combat::Mitigate, after the absorbs): what a
    // Crusader's Law sends elsewhere is taken off, and the rest returned.
    double Redirect(Unit* victim, double damage);

    // A blow of `damage` is about to land on `player` (the damage hook, before the damage is dealt): a transformation
    // that answers a fatal blow turns it into nothing. Does nothing unless `player` is a Crusader whose rune does.
    void Fatal(Player* player, std::uint32_t& damage);

    // The Crusader's scripts (Combat::RegisterScripts): the avatars Phalanx summons, the Laws' aura and kill hook.
    void RegisterScripts();
} // namespace DC::Combat::Crusader

#endif // DC_CRUSADER_H

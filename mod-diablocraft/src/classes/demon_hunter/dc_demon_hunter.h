/*
 * World of DiabloCraft - the Demon Hunter's class code. The combat engine asks the class through these entry points,
 * each answered in the file of the mechanic it belongs to. Everything shared reads the class from dc_class_map and the
 * sheets; the Demon Hunter's name stays in this folder.
 */

#ifndef DC_DEMON_HUNTER_H
#define DC_DEMON_HUNTER_H

#include "../dc_classes.h"
#include "../../combat/dc_damage_buckets.h"
#include "ObjectGuid.h"
#include "SharedDefines.h"

#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::DemonHunter
{
    // A cast or channel tick of `spellId` hit at least one enemy (Combat::Connected, once per attack, never per enemy):
    // a primary pays the Hatred its sheet row generates.
    void Connected(Player* player, std::uint32_t spellId);

    // The weapon-damage percentage a Demon Hunter skill's own hit deals, for the loader that gives every shell its hit
    // (dc_combat.cpp). nullopt for a spell the skills do not claim: the loader's own rule applies.
    std::optional<double> BasePct(std::uint32_t spellId);

    // A hit of `spellId` landed on `target`, `critical` when it was a critical hit (Combat's ResolveHit and Strike): what a
    // skill or rune adds to the enemy struck.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);

    // The critical hit chance, in percent, that a Demon Hunter skill or passive adds to `player`'s hit of `spellId` on `target` (Combat's ComputeHit): 0 for a
    // hit that gets none.
    double CritBonus(Player* player, Unit* target, std::uint32_t spellId);

    // Whether a press of a Demon Hunter skill may cast (Combat's OnSpellCheckCast, before the cost and the cooldown): the result
    // to refuse it with, SPELL_CAST_OK for every spell that needs nothing.
    SpellCastResult CanCast(Player* player, std::uint32_t spellId);

    // A cast of `spellId` resolved its hits on `targets` (Combat::ResolveCast, after them and before Connected): for a channel,
    // the one call at its start.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);

    // A hit by `player` is being computed: the named multipliers of its own that the class adds (Combat's ComputeHit, beside the
    // other classes'): Vengeance's increased damage, the passives' and a grenade's falloff.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, Factors& out);

    // A blow of `damage` is about to be dealt to `player` (Combat's OnDamage, beside the Crusader's): a class save sets `damage` to 0 (Awareness).
    void Fatal(Player* player, std::uint32_t& damage);

    // The saved skill bar was written (Classes::WriteActionBar): what a rune does while it stands in a slot.
    void BarWritten(Player* player, std::vector<Classes::Slot> const& bar);

    // The Demon Hunter's scripts (Combat::RegisterScripts): the channel loops.
    void RegisterScripts();

    // A cast of `spellId` began (Combat's OnCast, before the cost is taken): what a skill does as it begins.
    void Casting(Player* player, std::uint32_t spellId);

    // A cast of `spellId` aimed at the ground point `center` began (Combat's OnCast): the point the cast resolves at, moved if
    // the skill throws no nearer than a minimum.
    void Aim(Player* player, std::uint32_t spellId, Position& center);

    // A cast of `spellId` aimed at the ground point `center` exploded (Combat::ResolveCast, after the hits): what a skill
    // does around the point besides the engine's hit.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);

    // A bolt of `spellId` reached `target`, one of the enemies of the `cone` the cast was aimed into at `aimed` (Combat's
    // Impact, before the hit): true when the class dealt with the impact and the engine's own hit is not to follow.
    bool Impact(Player* player, Unit* target, Unit* aimed, std::vector<ObjectGuid> const& cone, std::uint32_t spellId);
} // namespace DC::Combat::DemonHunter

#endif

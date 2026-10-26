/*
 * World of DiabloCraft - the Necromancer's class code. The combat engine and the shared mechanics ask the class through
 * these entry points, each answered in the file of the mechanic it belongs to. Everything shared reads the class from
 * dc_class_map and the sheets; the Necromancer's name stays in this folder.
 */

#ifndef DC_NECROMANCER_H
#define DC_NECROMANCER_H

#include "../../combat/dc_damage_buckets.h"
#include "SharedDefines.h"

#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer
{
    // The weapon-damage percentage a Necromancer skill's own hit deals, for the loader that gives every shell its hit
    // (dc_combat.cpp). nullopt for a spell the skills do not claim: the loader's own rule applies.
    std::optional<double> BasePct(std::uint32_t spellId);

    // A cast or channel tick of `spellId` hit `enemies` enemies, at least one (Combat::Connected, once per attack,
    // never per enemy): a primary pays the Essence its sheet row generates.
    void Connected(Player* player, std::uint32_t spellId, unsigned enemies);

    // A cast of `spellId` resolved its hits on `targets` (Combat::ResolveCast, after them and before Connected): what a
    // skill or rune does to or around the enemies it struck.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);

    // Whether a press of a Necromancer skill may cast, `aim` being the ground point aimed at and `target` the unit (null for none) (Combat's
    // OnSpellCheckCast, before the cost and the cooldown): the result to refuse it with, SPELL_CAST_OK for every spell
    // that needs nothing.
    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Position const* aim, Unit* target);

    // A cast of `spellId` began (Combat's OnCast, before the cost is taken): what a skill takes besides its resource.
    void Casting(Player* player, std::uint32_t spellId);

    // A projectile of `spellId` reached `target`, the `index`th enemy it met (Combat's Impact, before the hit): true when
    // the class dealt with the impact and the engine's own hit is not to follow.
    bool Impact(Player* player, Unit* target, std::uint32_t spellId, unsigned index);

    // The chance, in percent, that a hit on `target` by the Necromancer crits, besides the sheet's (Combat::ComputeHit).
    double CritBonus(Player* player, Unit* target);

    // The damage `victim` takes from a hit once the engine has mitigated it, as the class changes it (Combat::Mitigate).
    double Reduce(Unit* victim, double damage);

    // A hit of `spellId` landed on `target` (Combat's ResolveHit and Strike): what a rune adds to the enemy struck.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);

    // The hit of `spellId` on `target` (null when none) being computed (Combat::ComputeHit): the class's multipliers of its own.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);

    // A cast of `spellId` aimed at the ground point `center` (Combat::ResolveCast, after the hits).
    void Ground(Player* player, std::uint32_t spellId, Position const& center);

    // The attacks per second `base` of `spellId` with the Necromancer's passives in (Combat::AttacksPerSecond).
    double AttackSpeed(Player* player, std::uint32_t spellId, double base);

    // The Necromancer's scripts (Combat::RegisterScripts): the kill hook that leaves corpses.
    void RegisterScripts();
} // namespace DC::Combat::Necromancer

#endif // DC_NECROMANCER_H

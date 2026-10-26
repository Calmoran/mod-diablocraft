/*
 * World of DiabloCraft - legendary gem powers.
 *
 * The gems that count for a character (one per kind, the highest rank: Unique Equipped) are cached per
 * player and rebuilt whenever an item carrying a legendary gem is equipped, unequipped, socketed or
 * swapped (Items::Apply calls Refresh). The powers read the cache; the numbers come from
 * DC::LegendaryGem (docs/contracts/legendary-gems.md). The pure sums are in dc_gem_power_math.h.
 * Group D adds the rank-25 bonuses. Enforcer acts on the player's pets, which
 * dc_legendary_gem_pet (data/legendary_gem_pets.csv) names: PetFactor and PetIncoming. Legacy of Dreams
 * reads ItemPowers' worn legendaries and set counter: Multipliers and IncomingFactor.
 */

#pragma once

#include "dc_damage_buckets.h"
#include "../items/dc_legendary_gem_item.h"

#include <cstdint>
#include <vector>

class Item;
class Player;
class Unit;

namespace DC::Items
{
    struct Instance;
}

namespace DC::Combat::GemPowers
{
    // Called by Items::Apply with the item that changed and whether it is now worn.
    void Refresh(Player*, Item* changed, bool equipping, DC::Items::Instance const& instance);

    // The cached gems that count, sorted by gem_id (what the later groups read).
    std::vector<DC::LegendaryGemItem::Socketed> Active(Player*);

    // The damage-taken factor of the always-on reductions for one incoming hit (Legacy of Dreams' included).
    double IncomingFactor(Player*, unsigned schoolMask, bool melee);

    // damage_formula.csv step 8, named for `.dc hit`: Legacy of Dreams' multiplier for the legendary items that count now.
    void Multipliers(Player*, DC::Combat::Factors& out);

    // damage_formula.csv step 8: the gem multiplier on one skill's hit.
    double SkillFactor(Player*, std::uint32_t spellId);

    // damage_formula.csv step 8 on a hit that is a pet's: Enforcer's multiplier when `skill` (the base skill's name, as the
    // skill sheets spell it) is on the pet list, 1 otherwise. A hit that is the player's own gets 1 because its skill
    // is not a pet's.
    double PetFactor(Player*, char const* skill);
    // Whether `skill` is on the pet list (dc_legendary_gem_pet): the skills whose rolled "+N% <skill> damage" affix
    // is a separate multiplier in D3 (maxroll Pets Skill Damage; d3planner skilldata.js:213) and not in the pool.
    bool IsPetSkill(char const* skill);

    // A monster hit on `victim` (the swing, the spell and the periodic tick hooks): Enforcer's rank-25 "your pets take 90%
    // less damage" when the victim is a creature of a pet skill that the list says enemies can target and its owner
    // wears the gem.
    void PetIncoming(Unit* victim, std::uint32_t& damage);

    // A hit of the player's landed (Passives::Hit, every non-periodic hit): Gogok's and Invigorating's stacks, and
    // Bane of the Stricken's stack on the target; then the gems that act on a hit (group C): Mirinae's smite,
    // Wreath of Lightning, Efficacious Toxin's poison, Zei's stun and Boyarsky's taunt (rank 25) and Iceblink's
    // Chill. `spellId` is the spell that landed it (0 when unknown: it then rolls no chance, the proc rule of
    // dc_proc_math.h) and `school` its school mask (0 reads the spell record's).
    void Hit(Player*, Unit* target, std::uint32_t spellId = 0, unsigned school = 0);

    // A critical hit landed (Abilities::CriticalHit): Pain Enhancer's bleed.
    void Critical(Player*, Unit* target, std::uint32_t spellId);

    // One incoming hit, after every mitigation but the shields (the monster-hit hooks and DealMonsterHit, beside
    // Wizard::Incoming): Moratorium puts its share off, `damage` is what is dealt now. `attacker` is whose hit
    // it was; the later payment is dealt in its name.
    void Incoming(Player*, Unit* attacker, std::uint32_t& damage);

    // True while Moratorium's payment is being dealt: a damage hook that reacts to being hit (Thorns, Revenge)
    // reads it, because the payment is the same hit's debt and not a new hit.
    bool PayingStagger();

    // Iceblink: the additional slow, in percent, a Chill of this player's carries (0 when it is not worn).
    double ChillBonus(Player const*);

    // A channeled skill's tick took resource (PayChannelTick): Taeguk's stack.
    void ChannelSpent(Player*);

    // damage_formula.csv step 8 on one target: Bane of the Powerful, of the Trapped, of the Stricken and Zei's.
    double TargetFactor(Player*, Unit* target);

    // damage_formula.csv step 4, in percent: Taeguk.
    double DamageBonus(Player*);

    // damage_formula.csv step 4, in percent, on one target: the monster damage-taken debuffs (group D: Gem of
    // Efficacious Toxin's "takes 10% increased damage from all sources", the poisoner's number whoever hits).
    double TargetBonus(Unit* target);

    // Critical Hit Chance on this target, percent (group D: Iceblink's chilled enemy).
    double CritBonus(Player*, Unit* target);

    // Gogok of Swiftness's Dodge, in percent (Abilities::DodgeChance adds it).
    double Dodge(Player const*);

    void RegisterScripts();
} // namespace DC::Combat::GemPowers

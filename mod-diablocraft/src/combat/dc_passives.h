#pragma once
#include <cstdint>
#include <string>
#include "dc_damage_buckets.h"
class Player;
class Unit;
namespace DC::Combat::Passives
{
    // Has, Invalidate, RefreshModifiers, Hit and Taken are dc_passives.cpp's, for every class; the other calls are
    // answered by the passives of the class that has them (classes/barbarian/dc_barbarian_passives.cpp).
    void RegisterScripts();
    void Fatal(Player*, std::uint32_t&);
    void Globe(Player*);
    void Invalidate(Player*);
    // The gear and paragon reductions a player pays with: the
    // SPELLMOD_COST and SPELLMOD_COOLDOWN auras are rebuilt from the sheet and
    // the character sheet's Resource Cost Reduction and Cooldown Reduction are
    // re-measured from the auras themselves. Call it wherever a contribution
    // that feeds either can have changed - item equip, unequip and socket,
    // paragon, and the passive refresh.
    void RefreshModifiers(Player*);
    bool Has(Player*, char const*);
    double DamageBonus(Player*);
    // Ruthless and No Escape: D3 multipliers of their own (maxroll Barbarian Separate Multipliers), not additive.
    void Multipliers(Player*, Unit* target, std::string const& skill, DC::Combat::Factors& out);
    double GenerationFactor(Player*);
    double FuryHealFactor(Player*);
    double IncomingFactor(Player*, unsigned);
    void Spent(Player*, double);
    void Begin(Player*,std::uint32_t);
void Cast(Player*, std::uint32_t);
    // `spellId` and `school` are the spell that landed the hit and its school (0 each when unknown), for the gems.
    void Hit(Player*, Unit*, std::uint32_t spellId = 0, unsigned school = 0);
    void Taken(Player*, unsigned, bool, double damage);
} // namespace DC::Combat::Passives

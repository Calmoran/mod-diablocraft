#pragma once
#include <cstdint>
#include <vector>
class Player;
class Unit;
namespace DC::Combat::Primaries
{
double DamageBonus(Player* player);
double CritBonus(Unit* target);
double TargetBonus(Unit* target);
double AttackSpeed(Player* player, std::uint32_t spellId, double base);
// Frenzy's buff without a swing (Echoing Fury): at least `stacks` stacks, at most the skill's maximum, a fresh timer; it speeds Frenzy as
// the swings' stacks do.
void GrantFrenzy(Player* player, unsigned stacks);
void RegisterScripts();
// A shell of the primaries that is not on the bar: what a primary launches (a shockwave, an axe, a blast, an explosion).
struct SecondaryShell
{
    std::uint32_t spellId;
    char const* skill;
    char const* rune;
    char const* element;
    double damagePct;
};
std::vector<SecondaryShell> SecondaryShells();
}

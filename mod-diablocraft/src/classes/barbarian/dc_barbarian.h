#pragma once
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
#include "../../combat/dc_damage_buckets.h"
class Player;
class Unit;
class Position;
namespace DC::Combat::Abilities
{
    void RegisterScripts();
    void InvalidateBar(Player* player);
    double DamageBonus(Player* player);
    // Wrath of the Berserker - Insanity: a D3 multiplier of its own (maxroll Barbarian Separate Multipliers).
    void Multipliers(Player* player, DC::Combat::Factors& out);
    double TargetBonus(Unit* target);
    double IncomingFactor(Unit* attacker);
    double DodgeChance(Player const* player);
    void ReflectMelee(Player* player, Unit* attacker, std::uint32_t& damage);
    bool Ready(Player* player, std::uint32_t spellId);
    // The skills that run on a charge count (Furious Charge, Revenge, Avalanche - Tectonic Rift):
    // the charge is their limiter, so the one-swing recovery does not apply (dc_combat.cpp SwingEligible).
    bool UsesCharges(std::uint32_t spellId);
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets,
              Position const* center = nullptr, double extraDamage = 0);
    void Spent(Player* player, double fury);
    void CriticalHit(Player* player, Unit* target, std::uint32_t spellId, double damage);
    void HitEffects(Player* player, Unit* target, std::uint32_t spellId);
    void LaunchEffects(Player* player, std::uint32_t spellId);
    void RendTick(Player* player, std::uint32_t spellId);
    void Taken(Player* player, Unit* attacker, std::uint32_t damage);
    // Whether `skill` is active for the item powers' `skills_active` condition: its buff is on the player, or (Call of the Ancients) its
    // Ancients are alive.
    bool SkillActive(Player const* player, std::string const& skill);
    bool WhirlwindActive(Player* player);
    void StartWhirlwind(Player* player, std::uint32_t spellId);
    void StopWhirlwind(Player* player);
    // Cooldowns, for the item powers: take `milliseconds` off the running cooldown of every rune of `skill`; or off the running cooldown of
    // one skill picked at random among the player's skills whose record states a cooldown (a primary's swing and a charge are not one).
    // CutRunningCooldown answers whether a skill was on cooldown to cut.
    void ReduceSkillCooldown(Player* player, char const* skill, double milliseconds);
    bool CutRunningCooldown(Player* player, double milliseconds);
    // The `apply_skill` effect (Ambo's Pride): applies `skill`'s bleed (Rend) to `target`, in the rune the bar holds or, with none on the bar, the
    // skill's own, and does what a Rend hit does to its target besides (Mutilate's mark).
    void ApplySkillBleed(Player* player, Unit* target, char const* skill);
    // A hit of the shell `skill`/`rune` (spell `spellId`) on `target` being resolved that the class settles itself: the answer to give
    // (whether it connected), or nothing when the ordinary hit applies.
    std::optional<bool> Resolve(Player* player, Unit* target, std::uint32_t spellId, std::string const& skill, std::string const& rune);
    // The bleed of the shell `skill` (spell `spellId`) applied to `target` without a cast; `keepRunning` leaves a bleed already running.
    // False for a shell that is not a bleed.
    bool Bleed(Player* player, Unit* target, std::uint32_t spellId, std::string const& skill, bool keepRunning);
    // Whether the shell of skill `skill` is a channel the module pays for tick by tick (it has no cost on its record).
    bool PaysByTick(std::string const& skill);
    // Whether the rune `rune` of `skill` keeps the sheet's damage in place of the rune row's.
    bool KeepsSheetDamage(std::string const& skill, std::string const& rune);
    // A press of `spellId` while its channel runs: the channel stops and the press is refused. True when it stopped one.
    bool Toggle(Player* player, std::uint32_t spellId);
    // Whether the shell of skill `skill` deals its damage as ticks of average crit.
    bool DamageOverTime(std::string const& skill);
    // Whether a cast of skill `skill` deals no hit of its own at the launch.
    bool LaunchesNoHit(std::string const& skill);
    // Whether the rune spends every point of the pool when it is cast (the core takes the base cost, the module the rest).
    bool SpendsEveryPoint(std::string const& skill, std::string const& rune);
    // A cast of the shell `skill`/`rune` begins (`id` its spell), the pool holding `fury` and the core about to take `cost` of it:
    // the runes that turn the pool into damage set `damagePct` or `extraDamage`.
    void Begin(std::string const& skill, std::string const& rune, std::uint32_t id, double fury, double cost, double& damagePct,
               double& extraDamage);
    // Whether the rune deals its damage once, around the first enemy the skill reaches.
    bool BurstsAtFirstImpact(std::string const& skill, std::string const& rune);
    // The critical chance, in percent, the skill `skill` gets from the `fury` in the pool.
    double CritBonus(std::string const& skill, double fury);
    // The skills the passives No Escape (the throws and the long hits), Earthen Might (the Rage ground skills) and Inspiring Presence
    // (the shouts) name.
    bool NoEscapeSkill(std::string const& skill);
    bool EarthenMightSkill(std::string const& skill);
    bool ShoutSkill(std::string const& skill);
} // namespace DC::Combat::Abilities

/*
 * World of DiabloCraft - the Wizard's mechanics.
 *
 * Every Wizard skill's D3 effect beyond its hit: the freezes, stuns and slows,
 * the shields and armors, the summons, Slow Time, Teleport, Explosive Blast,
 * Meteor's fall, Black Hole's pull, Archon form and its five abilities, and
 * the passives. Each rides the stock thing that already does it - a control
 * aura, SCHOOL_ABSORB, a persistent area aura, LEAP, SUMMON, a spell
 * modifier - on the records generate_spells.py writes; what is left here is
 * the part no record field can say: when, where, on whom, and how much.
 *
 * Each function below is defined in the file of the skill or family it belongs to; README.md in this folder lists them.
 *
 * Every number comes from DC::Combat::Numbers (the Wizard's sheets and
 * wizard_archon_values.csv, each row sourced) or from dc_ability_tuning for
 * the placeholders that have not been filled.
 */

#ifndef DC_WIZARD_H
#define DC_WIZARD_H

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "../../combat/dc_damage_buckets.h"

class Player;
class Unit;
struct Position;

namespace DC::Combat
{
    struct Hit;
}

namespace DC::Combat::Wizard
{
    // The shell name the combat loader gives Archon form's abilities: the
    // ability is the shell's rune, so "Archon form - Slow Time" never
    // collides with the Slow Time skill or the Archon rune of the same name.
    inline constexpr char const* ARCHON_FORM = "Archon form";

    enum class Attack
    {
        Melee,
        Ranged,
        Spell,
        Periodic
    };

    void RegisterScripts();

    // --- the cast --------------------------------------------------------
    // A shell's cast has begun (Spell OnCast): Prodigy's Arcane Power and
    // Arcane Dynamo's stacks, Storm Chaser's release on a Signature spell.
    void Begin(Player* player, std::uint32_t spellId, Unit* explicitTarget);
    // A Wizard shell's cast has resolved: `targets` are the units its area
    // or aim resolved to, `center` its point. Everything the skill does
    // besides its own hit happens here.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Position const& center,
              Unit* explicitTarget);
    // A cast whose damage lands later. True when the module has taken the
    // cast over: Meteor's impact and molten ground land after the sheet's
    // delay_seconds (Meteor Shower's seven at their scattered points), and
    // Explosive Blast goes off after its duration_seconds, Chain Reaction's
    // explosions one attack apart.
    bool Delayed(Player* player, std::uint32_t spellId, Position const& center);
    // True for a cast whose damage lands in separate pieces later (Meteor Shower's seven meteors), which the cast's own impact must not
    // deal as one.
    bool LandsApart(std::string const& skill, std::string const& rune);
    // One hit of a Wizard spell that dealt damage. `periodic` for a
    // damage-over-time tick, which applies no control.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, Hit const& hit, bool periodic);
    // A hit whose whole effect is an affliction (Magic Missile - Conflagrate:
    // the missile deals nothing itself, wizard.js:57 coeff 0, and burns):
    // puts it on and returns true, so the shell's own hit is not dealt.
    bool Afflict(Player* player, Unit* target, std::uint32_t spellId);
    // A channel tick that places something instead of hitting: Arcane
    // Torrent - Arcane Mines lays a mine at the torrent's point.
    void ChannelTick(Player* player, std::uint32_t spellId, Position const& center);
    // True for a channel whose tick carries its share of the channel's own time rather than of the caster's attack speed (Arcane Torrent).
    bool ChannelsByDuration(std::string const& skill);
    // Archon form: its abilities only while transformed; the Wizard's own
    // skills not while they are replaced.
    bool CanCast(Player* player, std::uint32_t spellId);
    // Electrocute's jumps: the enemies the bolt jumps to after `first`, in order, each the nearest
    // enemy within wizard.electrocute_jump_radius_yards of the one before it (dc_wizard_chain.h). Empty for every other
    // skill, for Lightning Blast and Arc Lightning, and with the tunable blank. dc_combat.cpp makes them the cast's chain
    // targets, so the arcs the client draws are the enemies hit, and hits each.
    std::vector<Unit*> Jumps(Player* player, std::uint32_t spellId, Unit* first);
    // Whether the spell is one whose bolt jumps (Electrocute's), so the engine registers the chain on its target.
    bool Chains(std::uint32_t spellId);
    // A Meteor molten-ground helper deals its Meteor record's numbers;
    // every other spell is its own source.
    std::uint32_t GroundSource(std::uint32_t spellId);

    // --- the formula (damage_formula.csv) --------------------------------
    // Step 3: Improved Archon's "increase the damage of all Archon abilities
    // by 50%", which d3planner applies to the ability's coefficient
    // (simulator/wizard.js:1052, :1071, :1093).
    double SkillFactor(Player* player, std::uint32_t spellId);
    // Step 4, percent: the caster's additive damage (Magic Weapon, Glass
    // Cannon, Unwavering Will, Sparkflint, Spellsteal).
    double DamageBonus(Player* player, Unit* target, std::uint32_t spellId);
    // Step 4, percent: what the victim takes more of (Bone Chill, Time Warp,
    // Snow Blast, Intensify, Gale Force, Cold Blooded).
    double TargetBonus(Player* player, Unit* target, unsigned school);
    // Step 8, separate multipliers (maxroll Wizard Separate Multipliers): Wave of Force - Arcane Attunement and Arcane
    // Orb - Spark, the next Arcane / Lightning spell; Elemental Exposure's stacks on the victim, "their sum being a
    // separate damage multiplier" (maxroll wins over d3planner's dmgtaken, damage-buckets.md section 4).
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
    double TargetFactor(Player* player, Unit* target);
    // The same factor, added to `out` under its passive's name when it is not 1, for `.dc hit`.
    double TargetFactor(Player* player, Unit* target, DC::Combat::Factors& out);
    // Step 5, percent: Absolute Zero's Cold damage.
    double ElementalBonus(Player* player, unsigned school);
    // Step 8, a factor: Archon form and its kill stacks, Power Hungry,
    // Audacity, Arcane Dynamo.
    double Standalone(Player* player, Unit* target, std::uint32_t spellId);
    // Critical Hit Chance on this victim, percent: Conflagration, and Ice
    // Blades against a frozen enemy.
    double CritBonus(Player* player, Unit* target, std::uint32_t spellId);
    // True when a Chill of this player's is on the enemy (Iceblink's rank-25 power reads it).
    bool ChilledBy(Player* player, Unit* target);
    // Archon's element runes.
    std::optional<std::string> Element(Player* player, std::uint32_t spellId);

    // --- the defence -----------------------------------------------------
    // A factor on what this attacker deals: Slow Time - Exhaustion, Wave of
    // Force - Debilitating Force, Black Hole - Spellsteal.
    double IncomingFactor(Unit* attacker);
    // A hit about to land on a Wizard, after the D3 mitigation and before
    // the core's absorbs: Force Armor's cap, the Familiar's Ancient
    // Guardian, Unstable Anomaly, and everything that answers being hit.
    void Incoming(Player* victim, Unit* attacker, std::uint32_t& damage, Attack kind);

    // --- the summons -----------------------------------------------------
    // Archmage's Vicalyke: the Mirror Image `dead`, killed by an enemy, is replaced by one more Image where it stood, with the cast's Life
    // and the dead one's remaining time, counted among the player's Images like the others (so the next cast and ClearSummons clear it).
    // False, and nothing summoned, when `dead` is not one of the player's own Images or no time is left.
    bool MultiplyImage(Player* player, Unit* dead);

    // Tal Rasha's Elements 2-piece: whether Meteor is on the player's bar, and a triggered cast of Meteor's `rune` ("" is the skill's own) at `target`.
    bool MeteorOnBar(Player* player);
    void CastMeteor(Player* player, Unit* target, std::string const& rune);
} // namespace DC::Combat::Wizard

#endif // DC_WIZARD_H

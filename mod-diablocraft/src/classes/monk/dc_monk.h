/*
 * World of DiabloCraft - the Monk's class code. The Monk is the third
 * class and the first with no stock body to remove, so this file starts small:
 * each skill adds its own hook here, as the Wizard's mechanics did in
 * src/classes/wizard/. Everything shared reads the class from dc_class_map and
 * the sheets; the Monk's name stays in this folder.
 */

#ifndef DC_MONK_H
#define DC_MONK_H

#include "../../combat/dc_damage_buckets.h"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Monk
{
    // The Monk's scripts (Combat::RegisterScripts, beside the Wizard's): Exploding Palm's death script, Mystic Ally's creature AI and player upkeep, the Mantras' always-on hook, Epiphany's, the passives' tick.
    void RegisterScripts();
    // The percent of its melee swings a blinded elite attacker misses now (Blinding Flash); 0 for any other unit.
    double MissChance(Unit const* attacker);

    // A cast or channel tick of `spellId` hit at least one enemy (Combat::Connected,
    // once per attack, never per enemy): a Monk's primary pays the Spirit its sheet
    // row generates. Does nothing for any other class or for a skill with no
    // generated_resource row.
    void Connected(Player* player, std::uint32_t spellId);

    // Band of Rue Chambers: "Your Spirit Generators generate [40-50]% more Spirit." The multiplier 1 + N/100 of the
    // worn `resource_generation_pct` rows for the skill `spellId` belongs to (a rune's spell is its skill's), 1 when none. Every payment of
    // Spirit by a primary multiplies by it: Connected's per-attack pay and Crippling Wave - Rising Tide's per-enemy pay.
    double SpiritFactor(Player* player, std::uint32_t spellId);

    // The weapon-damage percentage a Monk skill's own punch deals, for the loader that gives every shell its hit
    // (dc_combat.cpp). A rune states numbers of its own that are not the punch's (Bounding Light's 240% is the arcs',
    // Static Charge's 40% the proc's), so the Monk's skills say here which number is the punch. nullopt for a spell
    // that is not one of its hit-skills: the loader's own rule applies.
    std::optional<double> BasePct(std::uint32_t spellId);

    // One punch of Fists of Thunder, decided before it hits (Combat::ResolveCast): the combo advances here, so the cast
    // knows which stage it is. `pct` is the weapon damage the primary enemy takes in place of the shell's own, when the
    // stage changes it (the third hit's 400% shared by the enemies in front); `others` are the enemies in front who
    // share it. Empty for a spell that is not a Monk hit-skill.
    struct Punch
    {
        unsigned stage = 0;
        std::optional<double> pct;
        std::vector<Unit*> others;
    };
    Punch Begin(Player* player, std::uint32_t spellId, Unit* primary);

    // Whether a press of a Monk skill may cast (Combat's OnSpellCheckCast, before the cost and the cooldown): Seven-Sided
    // Strike needs an enemy. True for every other spell.
    bool CanCast(Player* player, std::uint32_t spellId);

    // A Monk skill whose hits come after the cast, one at a time (Seven-Sided Strike's strikes),
    // takes the resolved cast here (Combat::ResolveCast, before Begin): true, and the cast path deals nothing itself.
    // `targets` are the units its aim resolved to, `aimed` the unit it was cast at (may be null).
    bool Delayed(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Unit* aimed);
    // Epiphany: a cast at a selected enemy beyond the skill's own reach dashes to it before its hits are
    // found (Combat::ResolveCast). True when the Monk moved, so the cone is searched, and melee reach measured, from there.
    bool Approach(Player* player, std::uint32_t spellId, Unit* selected);

    // The enemies a Monk skill's own cast strikes beyond the core's `targets` (Lashing Tail Kick's half circle and column), read by
    // Combat::ResolveCast before the hits so they count in the cast's places and enemy count (N-NHIT, Scarbringer); empty for every
    // other skill. Monk::Cast strikes them.
    std::vector<Unit*> Beside(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);

    // A Monk shell's cast has resolved (Combat::ResolveCast, after the Wizard's): `targets` are the units its aim
    // resolved to and `punch` what Begin decided. Everything the skill does besides its own hit on the primary happens
    // here.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Punch const& punch);

    // What the item powers read of the Monk's own state: the stacks Sweeping Wind's vortex holds now (0 with none), and whether `skill` is active
    // for a `skills_active` row (Sweeping Wind while its vortex is up; false for any other skill).
    unsigned WindStacks(Player const* player);
    bool SkillActive(Player const* player, std::string const& skill);

    // Every shell cast as it begins (the OnCast hook in dc_combat.cpp, beside Wizard::Begin): Epiphany's on-cast runes.
    void Casting(Player* player, std::uint32_t spellId);

    // One hit of a Monk's spell landed on `target` (Combat::DealHit's callers, beside the Wizard's): Static Charge's
    // chance and Epiphany - Ascendance's stun.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // Rabid Strike's copy (Epiphany::Dash): `spellId` once more on `target`, paid by nobody and cast by nobody (no
    // dash, so no copy of the copy): Exploding Palm's palm, any other skill's own hit.
    void Mimic(Player* player, std::uint32_t spellId, Unit* target);

    // A press of `spellId` while a Monk channel of it runs (Combat::OnSpellCheckCast, beside Whirlwind's): the channel stops
    // and the press is refused, so it costs nothing. True when it stopped one.
    bool Toggle(Player* player, std::uint32_t spellId);
    // The `apply_skill` effect for a Monk skill (Combat::ApplySkillBleed, beside Rend's): Exploding Palm's palm on `target`, as the cast's would,
    // without a cast (Gungdo Gear). False for a spell that is not a Monk skill it can apply.
    bool Apply(Player* player, Unit* target, std::uint32_t spellId);
    // A cast of a ground-aimed Monk skill has resolved (Combat::ResolveCast, after Cast): `aimed` is the ground point it was
    // cast at (the caster's own position for a skill with no ground point). Wave of Light strikes everything from here.
    void Ground(Player* player, std::uint32_t spellId, Position const& aimed);
    // Timed effects (src/classes/monk/dc_monk_effects.h): what a rune says "for N seconds". `key` is
    // the rune's spell id; casting a key again refreshes it, and with maxStacks above 1 each cast adds a stack. Seconds
    // of 0 or less put nothing. Module state, no aura: nothing is shown on the buff bar.
    namespace Effects
    {
        // "increases the damage of all your attacks by pct": read by DamageBonus below.
        void Dealt(Player* player, std::uint32_t key, double pct, double seconds, unsigned maxStacks = 1);
        // "enemies take pct additional damage from all attacks": read by TargetBonus below.
        void Taken(Unit* enemy, std::uint32_t key, double pct, double seconds, unsigned maxStacks = 1);
        // "enemies deal pct less damage": read by IncomingFactor below.
        void Weaken(Unit* enemy, std::uint32_t key, double pct, double seconds, unsigned maxStacks = 1);
        // The stacks of a Dealt effect now (0 when it has run out).
        unsigned DealtStacks(Player* player, std::uint32_t key);
    } // namespace Effects

    // Before the hits of a cast (Combat::ResolveCast, before Begin): a Monk skill that picks its own enemies from the
    // cone the cast resolved (Way of the Hundred Fists: stage 1 one enemy, stage 3 an area; Cyclone Strike pulls enemies in
    // and then hits the ones around the Monk) reorders or replaces `targets`, the primary enemy first. `aimed` is the unit
    // the caster has targeted, if any.
    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*>& targets, Unit* aimed);

    // A critical hit of the player's, by any spell (Combat::ResolveHit and Strike, beside Abilities::CriticalHit): Blazing
    // Fists' speed buff, while that rune is the one slotted.
    void Critical(Player* player, std::uint32_t spellId);

    // Way of the Hundred Fists (dc_monk_hundred_fists.cpp). Each does nothing for a spell that is not
    // one of its records; Monk::BasePct, Begin, Cast, Landed and Critical call them first.
    namespace HundredFists
    {
        bool Is(std::uint32_t spellId);
        std::optional<double> BasePct(std::uint32_t spellId);
        void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*>& targets, Unit* aimed);
        unsigned Hits(std::uint32_t spellId, unsigned stage);
        Punch Begin(Player* player, std::uint32_t spellId, Unit* primary);
        void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Punch const& punch);
        void Landed(Player* player, Unit* target, std::uint32_t spellId);
        void Critical(Player* player, std::uint32_t spellId);
    } // namespace HundredFists
    // Dashing Strike (dc_monk_dashing_strike.cpp). Each does nothing for a spell that is not one of
    // its records; Monk::BasePct and Cast call them first.
    namespace DashingStrike
    {
        bool Is(std::uint32_t spellId);
        std::optional<double> BasePct(std::uint32_t spellId);
        // Spends the dash's charge, then the rune: Barrage's damage over time on the last enemy dashed through, the
        // speed buffs of Way of the Falling Star and Radiance, Blinding Speed's dodge.
        void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
        // Blinding Speed's dodge chance in percent while it runs; 0 for anyone else.
        double Dodge(Unit const* unit);
    } // namespace DashingStrike
    // Mystic Ally (dc_monk_mystic_ally.cpp): the ally that fights beside the Monk while the skill is on
    // the bar (its creature AI and the player upkeep are registered by RegisterScripts below), its rune's Passive and the
    // record's Active. Each does nothing for a spell that is not one of its records.
    namespace MysticAlly
    {
        bool Is(std::uint32_t spellId);
        std::optional<double> BasePct(std::uint32_t spellId);
        void Cast(Player* player, std::uint32_t spellId);
        // Water Ally's slow on the Monk's own hits.
        void Landed(Player* player, Unit* target, std::uint32_t spellId);
        // Fire Ally's damage bonus while the ally lives, read by Monk::DamageBonus.
        double DamageBonus(Player* player);
        void RegisterScripts();
    } // namespace MysticAlly

    // The passives of dc_monk_passives.cpp: Resolve and Seize the Initiative on the Monk's hits,
    // Chant of Resonance's mantra payback on a cast; the rest is a player tick, registered by Monk::RegisterScripts.
    namespace Passive
    {
        void Landed(Player* player, Unit* target, std::uint32_t spellId);
        void Cast(Player* player, std::uint32_t spellId);
        void RegisterScripts();
    } // namespace Passive

    // The class hooks of the damage path, beside the Wizard's (dc_combat.cpp): the additive percent the Monk's Dealt
    // effects add to a hit, the additive percent the victim's Taken effects add to every hit on it (whoever hits), and
    // the factor its Weaken effects put on what it deals.
    double DamageBonus(Player* player, Unit* target, std::uint32_t spellId);
    double TargetBonus(Player* player, Unit* target);
    double IncomingFactor(Unit* attacker);

    // A hit a player took (Combat::ModifyMeleeDamage, ModifySpellDamageTaken and DealMonsterHit, beside Passives::Taken): the
    // Mantra of Retribution of every Monk in the victim's group hits the attacker back.
    void Taken(Unit* victim, Unit* attacker);

    // The Monk's dodge chance in percent from its skills (Dashing Strike - Blinding Speed), beside
    // Abilities::DodgeChance; 0 for anyone else.
    double Dodge(Unit const* unit);
    // A Monk's ground circle on the damage path (Combat::Mitigate): the factor on what a player
    // standing in an ally's circle takes, among the percentage layers, and what of a hit gets through a shield the
    // circle's cast gave, after them. 1.0 and the damage as it is for anyone else.
    double TakenFactor(Unit* victim);
    double Absorb(Unit* victim, double damage);

    // The Monk's passives (dc_monk_passives_guardians_path.cpp). RegisterPassiveScripts: called by
    // Monk::RegisterScripts. AttackSpeed: a hand's attacks per second `base` for the skill `spellId`, with Alacrity's share of
    // the speed added for a Spirit Generator (Combat::HandAttacksPerSecond and AttacksPerSecond).
    void RegisterPassiveScripts();
    // The Monk's passives' damage multipliers (Combat::ComputeHit, right after Wizard::Multipliers;
    // D3's passives are separate multipliers, each a named factor of the hit). Called for every player (Unity's
    // ally side reaches non-Monks); `target` is the victim (Relentless Assault).
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
    double AttackSpeed(Player* player, std::uint32_t spellId, double base);
} // namespace DC::Combat::Monk

#endif // DC_MONK_H

/*
 * World of DiabloCraft - combat (02-combat §2-§4).
 *
 * The hit itself is damage_formula.csv steps 1-11 against the cached stat
 * sheet. Public surface of the combat folder.
 */

#ifndef DC_COMBAT_H
#define DC_COMBAT_H

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "dc_damage_buckets.h"
#include "../classes/dc_classes.h"

class Player;
class Unit;
struct Position;

namespace DC::Combat
{
    // One resolved hit, kept whole so ".dc hit" and the debug log can show every
    // bucket of damage_formula.csv rather than just the total.
    struct Hit
    {
        double weapon = 0;      // step 1, the sampled roll of the swinging hand
        double mainstat = 1;    // step 2
        double skill = 0;       // step 3
        double additive = 1;    // step 4
        double targetBonus = 0; // victim debuff already included in additive
        double elemental = 1;   // step 5
        double elite = 1;       // step 6 (Elite Damage and Damage to the creature's type)
        double legendary = 1;   // step 7, empty until legendary powers exist
        double standalone = 1;  // step 8, the product of every separate multiplier (factors below among them)
        Factors factors;        // step 8's named multipliers of the damage buckets (Ruthless, Spark, pet affix...)
        double targetFactor = 1; // the victim's multiplying debuff (Elemental Exposure), already in standalone
        double crit = 1;        // step 9
        double total = 0;       // step 10
        double areaDamage = 0;  // step 11, 0 when the 20% proc did not fire
        bool critical = false;
        bool offHand = false;
        double spent = 0;       // points of the skill's resource the cast took before this hit (Blade of the Warlord), set by the caller
        unsigned school = 1;
        std::string skillName;
        std::string Describe() const;
    };

    // Arcane Power on Critical Hit (the sheet's Stat::ResourceOnCrit): called for each critical hit a player lands, from
    // Abilities::CriticalHit; pays only the class whose resource is Arcane Power.
    void CriticalResource(Player* player, std::uint32_t spellId);

    // Runs the whole formula for one cast of a shell. Returns false when the caster
    // has no stat sheet or the spell is not one of ours.
    // `skillPct`, when given, is the step 3 percentage in place of the shell's
    // own: a Wizard channel tick carries its share of a ramping number, a
    // ground tick its share of a damage-over-time total. `periodic` makes the
    // hit a damage-over-time tick: average crit, never a roll (02 C11).
    // `petSkill`, when given, is the name of the summoning skill whose creature deals this hit under a spell of another
    // skill (the Ancients' bonus abilities): Enforcer then reads that skill, not the spell's own, as the pet's.
    bool ComputeHit(Player* player, Unit* target, std::uint32_t spellId, Hit& hit,
                    std::optional<double> skillPct = std::nullopt, bool periodic = false,
                    char const* petSkill = nullptr);

    // 02 §3. Weapon base speed x (1 + weapon IAS) x (1 + sheet IAS incl. the
    // dual-wield 15%), capped at 5.0. The sheet holds it - DC::Stats::RefreshWeapon
    // supplies the weapon inputs - and this reads that one cached value for the
    // animation-time scale and the character sheet.
    double AttacksPerSecond(Player* player, std::uint32_t spellId = 0);

    // One cast of a shell, resolved into `hit`: the shell has to be slotted, be
    // this character's, and have a target it can reach. `error` says why a
    // refused cast was refused. It takes no resources - the core
    // charges the record's cost and the module only keeps the books.
    bool CastShell(Player* player, Unit* target, std::uint32_t spellId, Hit& hit, std::string& error);

    // Hands a resolved hit to the core as a SpellNonMeleeDamage so the client draws
    // its own floating number and combat-log line, with our crit flag (C5) and the
    // shell's school. Creature armor and resistance are bypassed (C8). `fixed` deals hit.total as it is, without the
    // victim's debuffs (a Greater Rift Conduit strike, pylons.md 6.10: "unaffected by player damage, buffs and debuffs").
    void DealHit(Player* player, Unit* target, std::uint32_t spellId, Hit const& hit, bool fixed = false);

    // Exact resolved hit before crit; never re-roll damage for Reflects Damage.
    // Producers bracket delivery; the affix damage hook consumes it once. A Rend
    // tick cannot bracket the core's own delivery, so RendPeriodicProvider's
    // OnDamage drops its receipt when the absorb ate the tick whole.
    struct PreCritHit
    {
        double damage = 0;
        unsigned school = 0;
    };
    void RecordPreCritHit(Player*, Unit*, double damage, unsigned school);
    std::optional<PreCritHit> ConsumePreCritHit(Player*, Unit*);
    void ClearPreCritHit(Player*);

    // The total of `hit` with the victim's debuffs read now: for a periodic snapshot and a retargeted splash.
    double VictimAdjustedTotal(Player*, Unit*, Hit const&);

    // 01-stats §3's damage-taken factor for one incoming school, read off the
    // victim's cached sheet: (1 - Armor DR) x (1 - Resist DR) x (1 - Class DR) x
    // specific. This is the only copy of the player's mitigation maths - every
    // monster-sourced hit, ability or plain swing, multiplies by this and by
    // nothing else. Empty for anyone without a D3 sheet, which is what tells a
    // caller that this victim's defence is still the core's to compute.
    // `melee` is a melee hit: Mutilation Guard reduces it (legendary gems).
    std::optional<double> DamageTakenFactor(Unit* victim, unsigned schoolMask, bool melee = false);

    // The whole of the player's own mitigation for one incoming hit, in
    // mitigation.csv's order: the damage-taken factor above, then Shield Block -
    // a Block Chance roll that removes a FLAT Block Amount, rolled inside the
    // shield's range, after every percentage layer (docs/research/block.md). This
    // is the only place a hit is blocked, so a hit is blocked once wherever it
    // came from: the melee, spell and periodic hooks and DealMonsterHit all come
    // here. Empty for anyone without a D3 sheet, exactly like DamageTakenFactor.
    // `attacker` is who hit: an elite one is reduced by the sheet's Elite
    // Damage Reduction (Stat::EliteReduction).
    std::optional<double> Mitigate(Unit* victim, unsigned schoolMask, double damage, bool* blocked = nullptr,
                                   bool melee = false, Unit* attacker = nullptr);

    // 02 §5, the monster half of the fight. Deals one monster-sourced hit: the
    // caller's base damage times the victim's damage-taken factor for the spell's
    // school (01-stats §3). The tier's monster_damage_multiplier is already in the
    // creature's own numbers by the time a rift elite swings (03 §4 scaling), so it
    // is not applied a second time here.
    //
    // There is no dodge check: dodge is not implemented, and every caller so far is
    // a ground effect, which mitigation.csv says cannot be dodged anyway.
    void DealMonsterHit(Unit* attacker, Player* victim, std::uint32_t spellId, double baseDamage,
                        unsigned schoolOverride = 0);

    // Per-skill recovery. The record owns it and the core installs it from
    // RecoveryTime, with the rune family sharing it through Category;
    // this reads the same fields in the same order, for the GM readout.
    // A primary's is one swing of the hand asked for: `offhand` reads the
    // off-hand's own speed (HandAttacksPerSecond), otherwise the main hand's.
    std::uint32_t SkillCooldownMilliseconds(Player* player, std::uint32_t spellId, bool offhand = false);
    // The one cooldown the module still installs: a primary's swing recovery,
    // which is 1/APS and has no record field that could hold it.
    // `offhand` is the hand this cast swung with.
    void StartSkillCooldown(Player* player, std::uint32_t spellId, bool offhand = false);
    // What the player's own SPELLMOD_COOLDOWN auras make of a duration, asked
    // of the core through the same Player::ApplySpellMod call it makes on
    // RecoveryTime. For the numbers the module still schedules itself - the
    // charge recharges - so they are reduced by exactly what a cooldown is.
    std::uint32_t ReducedCooldownMilliseconds(Player* player, std::uint32_t spellId, std::uint32_t milliseconds);
    // The percentage of those auras, measured on a probe record of the
    // player's own class, for the sheet.
    double CooldownReductionPercent(Player* player, std::uint32_t probeSpell);
    // What the player's own SPELLMOD_DURATION auras make of a duration the
    // module applies itself, asked of the core through the same
    // Player::ApplySpellMod call Aura::CalcMaxDuration makes on a record's own.
    double ModifiedDurationSeconds(Player* player, std::uint32_t spellId, double seconds);
    void SendSkillCooldown(Player*, std::uint32_t, std::uint32_t milliseconds);
    // C1: a skill with no stated cooldown on its record
    // gets its own recovery of one swing; the charge skills keep their charges only.
    bool SwingEligible(std::uint32_t spellId);
    // A form ability: a shell of its own with no catalogue row, its own skill.
    bool IsStandaloneAbility(std::uint32_t spellId);
    // 1 / attacks per second of the hand asked for, in milliseconds; CDR does not touch it.
    std::uint32_t SwingRecoveryMilliseconds(Player* player, std::uint32_t spellId, bool offhand = false);
    void StartSwingRecovery(Player* player, std::uint32_t spellId, bool offhand = false);
    // What a finished cast owes: nothing for a triggered one or a channel (its swing
    // starts when it ends), otherwise StartSwingRecovery.
    void AbilityCast(Player* player, std::uint32_t spellId, bool triggered, bool channel);
    bool PayWhirlwindTick(Player* player, std::uint32_t spellId, bool offhand = false);
    // What the player's own SPELLMOD_COST auras do to this spell's cost, asked
    // of the core itself (Player::ApplySpellMod over a probe cost): 1.0 with no
    // reduction, 0 when a cost is free. The module never adds the modifiers up
    // itself, so this stays right whatever the core's stacking does.
    double CostReductionFactor(Player* player, std::uint32_t spellId);
    // Whether the player has a weapon in each hand, which is what makes the
    // Whirlwind channel alternate them.
    bool DualWielding(Player* player);
    // The attacks per second of one hand: the offhand's own speed when
    // `offhand` is asked for and there is one, otherwise the main hand's.
    // D3 keeps a speed per hand (stats_full.js:673-675) and swings them
    // alternately (simulator/cast.js:391-397).
    double HandAttacksPerSecond(Player* player, std::uint32_t spellId, bool offhand);
    // D3's channel cadence for Whirlwind: the
    // simulator's floor(channeling / attack speed) frames of 60 for the hand
    // that is about to swing, so 40 frames at one attack a second and 28 at
    // 1.4. Read fresh, so attack speed moves the next tick. The cost a tick
    // charges keeps the unrounded 40/60 scaling; it is not this number.
    double WhirlwindTickSeconds(Player* player, std::uint32_t spellId, bool offhand = false);
    // The sheet's damage line: the additive bonuses of the caster, then the separate multipliers that hold without a
    // target (Insanity). Ruthless and No Escape need a victim and read 0 and 1 here, as they always did.
    double DamageBonus(Player* player);
    double DamageFactor(Player* player);

    // The pieces of the hit path a class's own
    // mechanics reuse, so a Frost Nova, a Hydra bolt or an explosion lands
    // exactly the way a shell's own hit does.
    //
    // Every living enemy the caster may hit within `radius` of `center`, in
    // line of sight - the same list a shell's area resolves to.
    std::vector<Unit*> Enemies(Player* player, std::uint32_t spellId, Position const& center, double radius);
    // N-LESSER (Ranslor's Folly): whether `unit` is a lesser enemy, a monster that is neither an elite (IsElite: a native elite, or a champion or rare
    // pack's monster) nor a boss (a world or dungeon boss, a Rift Guardian). A pull or a lure that spares the strong asks this.
    bool IsLesser(Unit const* unit);
    // G1: one swing's weapon range of a hand before the sheet's flat damage (template, gem, rolled elemental range).
    // Bul-Kathos's Wedding Band's cap reads it (ItemPowers).
    std::pair<double, double> WeaponRange(Player* player, bool offHand);
    // One hit of `spellId` on one enemy: the formula (at `pct` percent of
    // weapon damage in place of the shell's own, when given), the core's
    // damage log, the passives' on-hit, the class's on-hit and the critical
    // hooks. `periodic` makes it a damage-over-time tick: average crit and no
    // on-hit control. True when it dealt damage.
    bool Strike(Player* player, Unit* target, std::uint32_t spellId, std::optional<double> pct = std::nullopt,
                bool periodic = false);
    // Whether `skill` is active for the player now, for a `skills_active` row: the Barbarian's buffs and Ancients, a class's vortex.
    bool SkillIsActive(Player const* player, std::string const& skill);
    // The proc coefficient the hit landing on this thread rolls (item powers, gems): its spell's, or while a PetBlow stands the
    // coefficient of the pet's own melee attack.
    std::optional<double> ProcCoefficient(std::uint32_t spellId);
    // A pet's blows, dealt as its owner's Strike of the pet's skill record, roll `coefficient` (nullopt: the pet's attack states none)
    // while this stands. Not nested.
    class PetBlow
    {
    public:
        explicit PetBlow(std::optional<double> coefficient);
        ~PetBlow();
        PetBlow(PetBlow const&) = delete;
        PetBlow& operator=(PetBlow const&) = delete;
    };

    // Strike on every enemy of Enemies(); the units hit.
    std::vector<Unit*> StrikeArea(Player* player, std::uint32_t spellId, Position const& center, double radius,
                                  std::optional<double> pct = std::nullopt, bool periodic = false);
    // A cast or a channel tick of `spellId` hit at least one enemy: called once for it, never per enemy or splash target. Life per
    // Hit (Stats::SkillHit) and the item powers' per-attack events (ItemPowers::Attack: "when you hit with a resource-spending
    // attack") read it. `enemies` is how many enemies it hit, where the caller counts them (the cast path and StrikeArea; 0 elsewhere):
    // the item powers' `enemies_hit_at_most` reads it (The Gavel of Judgment).
    void Connected(Player* player, std::uint32_t spellId, unsigned enemies = 0);
    // The saved skill bar was written (Classes::WriteActionBar): what a rune does while it stands in a slot.
    void BarWritten(Player* player, std::vector<Classes::Slot> const& bar);
    // The targeting sheet's radius for a shell (dc_spell_targeting), 0 when
    // it has none.
    double TargetRadius(std::uint32_t spellId);
    // The targeting sheet's range for a shell, the reach of its line or aim, 0 when it has none.
    double TargetRange(std::uint32_t spellId);
    // Arcane Power a Wizard gains, through the core's own energize.
    void GainResource(Player* player, std::uint32_t spellId, double points);

    // Applies the damage-over-time aura of the skill `spellId` (Rend and its runes; Exploding Palm's palm through its class's own Apply)
    // to `target` as another skill's hit would, without a cast: the snapshot is taken now. False when it did not apply because the enemy already carries all the bleeds of the skill that the player's
    // powers let it stack (docs/contracts/legendary-powers.md, `apply_skill`).
    bool ApplySkillBleed(Player* player, Unit* target, std::uint32_t spellId);
    // N-CAST (Dark Mage's Shade): casts the player's own `skill` by code, at `target` (the player when null): the spell on the
    // bar for that skill, so the rune the player chose, as the core's triggered cast (TRIGGERED_FULL_MASK: no resource cost, no cooldown, no global
    // cooldown; not a pressed cast, so it fires no cast event). False when the skill is not on the bar or the core refuses the cast.
    bool CastSkill(Player* player, std::string const& skill, Unit* target = nullptr);
    // Rabid Strike: the multiplier every hit computed on this thread takes (ComputeHit's legendary term), 1 but while a copy
    // is dealt (Epiphany's dash sets it around the copy and puts it back). A damage over time the copy starts takes it into its tick when it starts.
    double& CopyFactor();
    void RegisterScripts();
} // namespace DC::Combat

#endif // DC_COMBAT_H

/*
 * World of DiabloCraft - the item power table and the set counter.
 * The rows are dc_legendary_power (data/legendary_powers.csv): an item's or a set bonus's powers.
 * The worn pieces of each set are counted per player and rebuilt whenever a set piece is equipped, unequipped or
 * swapped (Items::Apply calls Refresh, beside GemPowers::Refresh). The rules are in dc_item_power_math.h.
 * Contract: docs/contracts/legendary-powers.md.
 */

#pragma once

#include "dc_item_power_math.h"

#include <cstdint>
#include <string>
#include <vector>

class Item;
class Player;
class Unit;

namespace DC
{
    struct StatSheet;
}

namespace DC::Items
{
    struct Instance;
}

namespace DC::Combat::ItemPowers
{
    // Called by Items::Apply with the item that changed and whether it is now worn (a broken item is not worn); rebuilds the set
    // counts and the item's entry of WornRolls.
    void Refresh(Player*, Item* changed, bool equipping, DC::Items::Instance const& instance);

    // The worn pieces of `set` (a name as base_items.csv spells it): distinct pieces, broken ones left out.
    unsigned SetCount(Player const*, std::string const& set);

    // Whether the `pieces`-piece bonus of `set` is on: the count reaches it and the table has its power.
    bool BonusActive(Player const*, std::string const& set, unsigned pieces);

    // N-SETSTAT: the set `stat` rows that are on for the player, each with its contribution index
    // (ItemPower::SetStats). The reader is Items::RefreshCubedStats, which puts them on the sheet through the affix map.
    std::vector<std::pair<unsigned, ItemPower::Row>> SetStats(Player const*);

    // What Legacy of Dreams counts (docs/contracts/legendary-gems.md): the worn, unbroken Legendary and Set items, how many of them
    // are Ancient or Primal, and whether any set bonus is worn (any set at its first bonus's pieces, built or not).
    struct Legendaries
    {
        unsigned items = 0, ancients = 0;
        bool setBonusOn = false;
    };
    Legendaries WornLegendaries(Player const*);

    // The (skill, stat) modifiers of the powers that are on for the player (docs/contracts/legendary-powers.md). A `_pct` stat as
    // the multiplier of its sources (1 when none), a `set to` stat as the skill's own `base` or a source's higher number.
    double SkillFactor(Player const*, std::string const& skill, std::string const& stat);

    // N-NHIT (Bracers of Destruction): the place of the hit being computed on this thread among the enemies its cast hits,
    // nearest first (1 the first), 0 outside a cast's targets. Combat's ResolveCast sets it around each target's hit and puts it back; a
    // `first_hits` row reads it (ItemPower::Holds).
    unsigned& HitPlace();

    // N-NHIT (Skular's Salvation): the enemies the cast of the hit being computed on this thread hits in all, 0 outside a cast's targets.
    // Combat's ResolveCast and the Boulder Toss burst set it around their hits and put it back; a `cast_enemies_at_most` row reads it
    // (ItemPower::Holds).
    unsigned& CastEnemies();

    // The multiplier the `damage_by_missing_resource_pct` rows that are on give a hit of `skill` (Dishonored Legacy): 1 + N/100 x
    // the percent of the player's primary resource missing now /100, read by ComputeHit into the hit's legendary term (a multiplier of its own).
    // 1.0 when none.
    double MissingResourceFactor(Player const*, std::string const& skill);
    // N-DERIVED (Standoff): the product of ItemPower::DerivedFactor over every `damage_per_<stat>_pct` stat, each read with
    // its sheet stat from `sheet` (the hit's own). Read by ComputeHit into the hit's legendary term.
    double DerivedFactor(Player const*, std::string const& skill, DC::StatSheet const& sheet);
    // N-COUNTREAD (a set's per-stack bonus): the product of ItemPower::PerStackFactor over the `stat` rows of the worn items for
    // `skill`, with the live count `stacks` a class reports (a vortex's stacks). Read by ComputeHit into the hit's legendary term.
    double PerStackFactor(Player const*, std::string const& skill, std::string const& stat, double stacks);
    // N-NEXT (Saffron Wrap): the enemies the skill's last cast left for the cast in progress (kept by EnemyStackPress and EnemyStackConnect), the stacks a
    // `damage_per_enemy_hit_pct` row reads through PerStackFactor; 0 when none or when no worn row counts them.
    double EnemyStacks(Player const*, std::string const& skill);
    // Blade of the Warlord: the points of its resource a hit of `skill` takes from a player who `have`s that many (up to the
    // `resource_spent_cap` row, 0 with no worn, rolled item), and the multiplier the hit gets for `spent` points taken: 1 + N/100 x spent/cap, read by
    // ComputeHit into the hit's legendary term (a multiplier of its own). 1.0 when none. The one taker is the primary provider (dc_primaries.cpp).
    double ResourceSpend(Player const*, std::string const& skill, double have);
    double SpentFactor(Player const*, std::string const& skill, double spent);
    // N-DUR (Pride of Cassius): `base` seconds of `skill`'s duration plus the worn items' `duration_add_seconds`; `base` itself for no player or none.
    // The reader of that stat: Ignore Pain's cast (dc_abilities.cpp) marks with it.
    double DurationSeconds(Player const*, std::string const& skill, double base);
    // N-HYDRA (Serpent's Sparker): how many of `skill`'s summons the player may have up at once, `base` plus the worn items'
    // `extra_active_count` (ItemPower::ActiveCount). The reader: the Hydra's summon (dc_wizard_hydra.cpp), before the core's totem slot.
    double ActiveCount(Player const*, std::string const& skill, double base);
    double SkillSetTo(Player const*, std::string const& skill, std::string const& stat, double base);
    // N-CD (Gesture of Orpheus): the multiplier on `skill`'s cooldown, ItemPower::CooldownFactor of the powers that are on
    // (1 when none). Read by Combat::SkillCooldownMilliseconds and by Cast's cut of the cooldown the core installed. It takes no Seen (the stat
    // takes no condition, so there is nothing for it to read), only the item powers' lock.
    double CooldownFactor(Player const*, std::string const& skill);
    // The same for a stat that only shortens (`dot_payout_seconds`): the skill's own `base`, or a source's lower number.
    double SkillLowest(Player const*, std::string const& skill, std::string const& stat, double base);

    // A passive's number with the worn items' raise (kind `passive`: Primordial Soul): the passive's own `base`, or a source's higher number.
    // The caller asks only for a player who has the passive.
    double PassiveSetTo(Player const*, std::string const& passive, std::string const& token, double base);

    // Whether a rune of `skill` is given to the player without choosing it (kind `rune`: the Wastes 6-piece's Dust Devils, Mortick's
    // Brace's every rune of Wrath of the Berserker). The rune on the bar is the caller's own.
    bool GrantsRune(Player const*, std::string const& skill, std::string const& rune);

    // The player's damage-taken multiplier from the powers that are on (1 when none): the rows of `damage_taken_pct`, each its own
    // factor 1 + N/100 (-50 is half damage; a stacking row's N is per stack, summed), whose condition holds now. Mitigate multiplies
    // it in beside the sheet's factor (and the `damage_reduction_pct` powers, each 1 - N/100). DealtFactor is the same for `damage_dealt_pct`, read by the hit (ComputeHit).
    double IncomingFactor(Player const*);
    double DealtFactor(Player const*);
    // N-MOVE (Hexing Pants of Mr. Yan): the percent the powers that are on add to (or, below 0, take from) the additive pool of a hit, damage_formula.csv step 4,
    // read by ComputeHit beside the other additive terms; 0 when none. And the multiplier of the primary resource a class pays itself from the same rows,
    // 1 when none: every class multiplies the generation it pays by it, where it pays it (the same place as its own generation bonuses).
    double DamageBonus(Player const*);
    double GenerationFactor(Player const*);
    // Fleshrake: the multiplier of one skill's hits from the `skill_damage_pct` buff rows naming it, 1 + stacks x N/100 at the stacks of
    // their owner's record (a multiplier of its own beside SkillFactor's); 1 with none. Read by the hit (ComputeHit).
    double StackedSkillFactor(Player const*, std::string const& skill);
    // Homing Pads: the multiplier of the damage a player takes while casting Town Portal, 1 - N/100 of the `town_portal_bubble_pct` rows worn;
    // 1.0 with none, so a value below 1.0 also means the cast is not interrupted by damage. The one reader: the PortalDamage hook (rifts/dc_town_portal.cpp).
    double TownPortalFactor(Player const*);
    // The critical hit chance, in percentage points, that the `crit_chance_pct` rows that are on add to a hit on `target` (Envious Blade: 100 while the
    // target is at full Life): the sum of the active sources, read by ComputeHit into the crit chance before it is clamped. 0 when none, or with no target.
    double CritBonus(Player const*, Unit const* target);
    // N-PYLONDUR (Gloves of Worship): the seconds a shrine effect lasts, the shrine's own `base` or the highest `shrine_seconds` row that is on
    // when that is more (ItemPower::PlayerSetTo); `base` for no player or none. The one reader: Pylons::Give, for a shrine and never a pylon.
    double ShrineSeconds(Player const*, double base);
    // The multiplier of the owner's pets' attacks per second (`pet_attack_speed_pct`, Tasker and Theo; 1 when none): read by each pet's own swing.
    double PetSpeedFactor(Player const*);

    // What the powers that are on do to every stun the player applies (Dovu Energy Trap): the product of the `stun_duration_pct`
    // rows, each 1 + N/100 with the worn item's rolled N; 1 when none. Read by the StunDurations hook (a stun record's own duration) and by each
    // site that sets a stun's seconds itself after AddAura (Ground Stomp and Thunderstrike's Control, the Wizard's Stun, Zei's stun, a class's own stuns).
    double StunFactor(Player const*);

    // What the powers that are on do to a shield's absorb amount (Ashnagarr's Blood Bracer): the product of the `shield_potency_pct`
    // rows, each 1 + N/100 with the worn item's rolled N; 1 when none. The one reader of that stat: every place a player's own shield sets its
    // absorb amount (Molten Wildebeest's PutShield, the Wizard's Shield helper, Diamond Skin's aura amount and Force Armor's cap on what a hit is cut by) multiplies by it.
    double ShieldFactor(Player const*);

    // What the powers that are on do to the Death's Breath a loot roll grants (Sage's Journey 3-piece): the product of the
    // `deaths_breath_pct` rows, each 1 + N/100 (100 doubles); 1 when none. The one reader: the loot roll's Death's Breath grant (Loot::Roll).
    double DeathsBreathFactor(Player const*);
    // The keystone factor of the powers that are on (Cain's Destiny 3-piece): 1 + N/100 of the `extra_keystone_pct` rows, 1 with none.
    // The one reader is DC::Loot::ExtraKeystones, which rolls it once for each Greater Rift Keystone a Guardian pays.
    double KeystoneFactor(Player const*);

    // What the `element` rows that are on add to a hit of `element` (the shell's, "fire"): the sum of their `damage_pct`, read by ComputeHit into
    // the hit's elemental bonus (Magefist, the additive:elemental bucket). 0 when none.
    double ElementBonus(Player const*, std::string const& element);

    // N-PREVENT (Countess Julia's Cameo): a hit of `schoolMask` the player is about to take, `damage` after its defences. The `damage_prevented_pct`
    // rows that are on for the hit's element take their share off it, and the `heal_of_prevented_pct` rows heal the player a share of what was
    // prevented. Nothing for a school with no element, a hit of 0, or a player with no such row.
    void Prevent(Player*, unsigned schoolMask, std::uint32_t& damage);

    // The multiplier the `damage_per_distance_pct` rows that are on give a hit of `element` on `target` (Starfire): 1 + N x whole
    // steps of the yards from the player to the target, up to the row's cap, read by ComputeHit into the hit's legendary term (a multiplier of its
    // own). 1.0 when none, or with no target.
    double DistanceFactor(Player const*, Unit const*, std::string const& element);
    // N-TCTRL (Fjord Cutter): the multiplier the `damage_increase_pct` rows of `skill` with a `target_` condition give a hit on
    // `target` (ItemPower::TargetFactor), read by ComputeHit into the hit's legendary term. 1.0 when none, or with no target.
    double TargetFactor(Player const*, Unit const* target, std::string const& skill);
    // N-TCTRL (Krysbin's Sentence): the multiplier the `damage_vs_impaired_pct` rows give a hit on `target` (ItemPower::ImpairedFactor): N% against a slowed enemy,
    // triple N% against one under any other control-impairing effect, read by ComputeHit into the hit's legendary term. 1.0 when none, or with no target.
    double ImpairedFactor(Player const*, Unit const* target);

    // The events the rows fire on (docs/contracts/legendary-powers.md "Events"): a player's own cast of a skill (CombatCastCheck::OnSpellCast), a
    // hit of a skill on one enemy (`hit`, Passives::Hit), a cast or channel tick that hit at least one enemy (`hit_spender`, `hit_generator`,
    // Combat::Connected), a being hit (Passives::Taken); a kill is the table's own PlayerScript. Cast also takes the seconds that
    // `cooldown_reduction_seconds` powers that are on off the cooldown the skill just started.
    void Cast(Player*, std::uint32_t spellId);
    // Storm Armor electrocuted `target` (the armor's tick, or Shocking Aspect's shock on a critical hit): fires the `storm_armor_shock` rows with the
    // yards to it, so an item that asks for a distance (Halo of Karini, "more than 15 yards away") sees it. Called by the Wizard's
    // Storm Armor code after the shock's strike.
    void StormArmorShock(Player*, Unit*);
    // A skill's on-death explosion reached `enemy` (Exploding Palm's, dc_monk_exploding_palm.cpp Explode, before the blast's damage): fires the
    // `explosion` rows that name `skill` with the enemy as their target (Gungdo Gear's `apply_skill`).
    void Exploded(Player*, Unit* enemy, std::string const& skill);
    void Hit(Player*, Unit* target, std::uint32_t spellId);
    // Tal Rasha's Elements: a hit of the school mask `school` on `target` (called beside Hit by Passives::Hit): fires `hit_element` with
    // the element's name when the school is one of Arcane, Frost (cold), Fire and Nature (lightning).
    void HitElement(Player*, Unit* target, unsigned school);
    void Attack(Player*, std::uint32_t spellId, unsigned enemies = 0);
    void Taken(Player*);
    // N-SCHOOLEV (Krede's Flame): a hit of the school mask `school` that takes `damage` Life from the player (called beside Taken by Passives::Taken, after the
    // defence, before the hit is dealt): fires `taken_element` with the school's element where a skill fires with its name.
    void TakenElement(Player*, unsigned school, double damage);
    // N-BLOCK (Blood Brother): the chance, in percentage points, the `block_chance_pct` rows that are on add to the player's Block Chance (the sum of
    // the active sources, 0 when none); read by Mitigate beside the sheet's, and held to the same total cap (ItemBlock::Chance).
    double BlockBonus(Player const*);
    // The multiplier the `blocked_damage_cut_pct` rows give a blocked hit: 1 - N/100 per source (1 with none). Read by Mitigate for a hit that was blocked.
    double BlockedFactor(Player const*);
    // A hit on the player was blocked (Mitigate, once per blocked hit, `attacker` the unit that struck, null when none): fires the `block` rows
    // with the attacker as their target. Blood Brother's arms the next attack.
    void Blocked(Player*, Unit* attacker);
    // The multiplier a hit of `skill` the player deals takes from an armed `next_attack_pct` (the aura on the player) or from the cast that
    // spent it (ItemBlock::NextAttackFactor); 1 with none. ComputeHit reads it for a hit that is no tick and no pet's.
    double NextAttackFactor(Player const*, std::string const& skill);

    // A hit of `damage` is about to be dealt to the player (UNITHOOK_ON_DAMAGE): the `life_below` event of Dark Mage's Shade
    // when it takes Life from the item's level or above to under it. Nothing for a hit that kills.
    void Damaged(Player*, std::uint32_t damage);
    // N-FATAL (Ancestors' Grace): the same hook, for a hit that would take all the Life the player has left (ItemPower::IsFatal). Fires the `fatal`
    // rows; when one saved the player (`revive_full`) the damage is set to 0, so the hit deals nothing.
    void Fatal(Player*, std::uint32_t& damage);
    // The player landed a cast of `spellId` that moved them (Leap: the landing's resolve, dc_combat.cpp OnEffectMovementFinalized): the `land`
    // event, named by the skill, of Might of the Earth's 4-piece.
    void Landed(Player*, std::uint32_t spellId);

    // N-SPENT (Immortal King's Call 4-piece): the player spent `fury` points of Fury now (Abilities::Spent, every cast the core charged and a
    // Primary's extra take). Fires the `resource_spent` rows, once per whole step of their `cond_arg` points, and carries the part of a step not yet paid.
    // N-CDNAMED: the `cooldown_cut_named_seconds` effect they fire cuts the running cooldown of every skill the row names, all its runes.
    void Spent(Player*, double fury);

    // A Mirror Image of the player's was killed by an enemy (`image_death`, Archmage's Vicalyke; the Image's own AI reports it, never a despawn):
    // fires the rows of that event with the dead Image as the target.
    void ImageDied(Player*, Unit* image);

    // The player took damage now (Mitigate): a `quiet_stacks` power loses its stacks and builds none for its reset seconds.
    void Hurt(Player const*);

    // A channel of `skill` began or ended (Whirlwind's Start/StopWhirlwind, the Wizard's StartChannel/StopChannel): what the conditions
    // over channelled skills read. Ending a channel that is not running is ignored (StopWhirlwind also runs on death, a map change and a logout).
    void ChannelStarted(Player const*, std::string const& skill);
    void ChannelEnded(Player const*, std::string const& skill);

    // The item-owned powers worn (docs/contracts/legendary-powers.md "Per-item rolls"): one number of `skill`'s `stat` per worn, unbroken
    // item that has the row, the item's own stored roll for a row with a range and the table's number for a fixed row. Empty when no
    // such item is worn: no value, no power. The caller combines several as its stat says (SkillFactor multiplies, SkillSetTo takes the highest).
    std::vector<double> WornRolls(Player const*, std::string const& skill, std::string const& stat);

    // The stat rows `d3Id` rolls as its own presets, with the roll range the table gives (the roller reads them).
    std::vector<ItemPower::Row> ItemStats(std::string const& d3Id);

    // What the stacking slows on the player leave of the attacks per second (Stone Gauntlets): the product of
    // ItemPower::StackedSpeedFactor over each `movement_speed_pct` power buff on it, by its stacks; 1 with none. Read where the attacks per
    // second are (Combat::AttacksPerSecond, HandAttacksPerSecond), so control immunity, which takes the slow off, takes this off too.
    double AttackSpeedFactor(Player*);

    // The factor a hit of `skill` gets from the marks the player's powers put on `target` (`mark_enemy`, Bindings of the Lesser Gods): the
    // mark is a debuff record on the enemy cast by this player, holding the rolled percent; `split` is a hit of the skill's split allies
    // (Fire Ally's bombs), which read `mark_split_factor` times the percent. 1 with no mark of this player's on the target.
    double MarkFactor(Player const*, Unit const* target, std::string const& skill, bool split);

    // The hidden cost auras put where the worn items and the timed cuts (CostCut) have them now: called when a timed cut starts or ends.
    void RefreshCostAuras(Player*);

    // Whether the player's abilities cost nothing now (N-COST, Kekegi's Unbreakable Spirit: a fired `cost_free_seconds`
    // row's window). The costs the core charges are already free through the gear cost aura; a cost the module charges itself reads this.
    bool CostFree(Player const*);

    // Every ability of the player costs nothing for `seconds` from now (the window N-COST opens; a class's own window, Land of the
    // Dead's Invigoration): a later call moves the end to the later of the two.
    void FreeAbilities(Player*, double seconds);

    // Whether the base item `entry` has an item-owned power row of any kind but `stat` (the login sweep reads such items).
    bool HasItemPower(std::uint32_t entry);

    // Every item-owned row of `d3Id` (the roller rolls the ones with a range once: ItemPower::RollPowers). A legacy twin (same name and rarity as one
    // pool row) owns its pool item's rows, with `owner` set to its own d3_id.
    std::vector<ItemPower::Row> ItemRows(std::string const& d3Id);

    // ---- Kanai's Cube: the second source of a power (docs/contracts/legendary-powers.md "The Cube source") ----
    // The Archive calls these; nothing here has a window, a command or a table of its own. A power is its pool item's d3_id.

    // The power id an item's d3_id stands for: a legacy twin's pool id, any other id as it is.
    std::string PowerIdOf(std::string const& d3Id);

    // Whether the table has an item-owned row for the power (a stat-only power too): the Archive refuses an item whose power is not built.
    bool Built(std::string const& powerId);

    // The class rule of the Cube's `choose` verb, read when a power is chosen: the pool item's usable_by and designated_class against the player's
    // class key (RollClass::Eligible, the function dc_crafting.cpp ChooseCubePower calls). False for an id that is no pool item.
    bool ClassMayChoose(Player const*, std::string const& powerId);

    // Choose `powerId` in one of the Cube's slots (dc_cube_slot_item, cube_slots.csv; a legacy id is taken as its pool id). False, and nothing changed, for a slot that is
    // not one, a power that is not built or one the player's class may not choose. The immunities, the cost auras and the stacking buffs are redone.
    bool CubeSet(Player*, unsigned slot, std::string const& powerId);
    void CubeClear(Player*, unsigned slot);

    // The powers chosen, in slot order; and every power in play: the worn ones first, then the cubed ones that are not worn, each id once.
    std::vector<std::string> Cubed(Player const*);
    std::vector<ItemPower::Active> ActivePowers(Player const*);

    void RegisterScripts();
} // namespace DC::Combat::ItemPowers

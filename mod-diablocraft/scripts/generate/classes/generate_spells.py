#!/usr/bin/env python3
"""Generate Barbarian spell shells as spell_dbc rows (02-combat §10, C12).

Primaries carry real effects; other skills retain their existing implementations.

A shell is built by cloning the 936-byte Spell.dbc record of the WoW spell that
barbarian_visuals.csv maps the skill to, then overriding only the fields we own:
id, name, school, cooldown, GCD, range, radius and effects. Cloning inherits
the animation/icon/visual set; gameplay restrictions are cleared explicitly.

The rows go into the world table `spell_dbc`, which AzerothCore layers over the
client's Spell.dbc at startup (DBCStores.cpp: LOAD_DBC(sSpellStore, "Spell.dbc",
"spell_dbc") -> storage.LoadFromDB). The server therefore knows these spells
with no client patch; the client needs its own Spell.dbc rows before it can draw
their name, icon and animation, which is client-patch/'s job.

Run from the repo root:

    python mod-diablocraft/scripts/generate/classes/generate_spells.py

This script never touches generate_sql.py or the dc_ tables it produces.
"""

import csv
import re
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import primary_spells
import generate_class_resources
import spell_id_reservations as reservations
from class_names import sheet_stem
from text_guard import UNFILLED_TOKEN_WOW, refuse_unfilled
from pathlib import Path

from applied_migrations import write_migration

# Literal audit (docs/research/literal-audit-claude.md): the numbers below are
# constants, not tunables - recorded here, nothing else changes.
# Constant (audit 108, 81000, 42650, 81, 14, 81202, 81203, 81204, 81138, 81310): shell id bases, donor spells, the SpellCastTimes row for 3 s; Identifiers; the manifest asserts they never renumber.
# Constant (audit 109, 29, 30, 46, 71, 86, 92, 110, 133, 136, 205, 206, 225, 6, 104, 20, 936, 5000): Spell.dbc field indices, implicit-target enums, DBC header size and record length; One row for the whole group: client file format, not game values.
# Constant (audit 110, 62373, 122, 52960, 3815, 10059, 11988, 1535, 6544, 28131, 52305, 845, 1449, 46968, 57755, 2983, 23881, 1464, 139, 2061, 2054, 439): donor spell ids and icon ids the shells clone; Identifiers and looks; the designer's to change, one constant each.
# Constant (audit 111, 87, 149, 42, 6, 3, 226, 1000, 33, 197, 12, 11, 7, 13, 5, 94): effect, aura, mechanic and implicit-target enum values written into the shells; One row for the group; engine enums.
# Constant (audit 112, 16): tooltip numbers a row may carry; Capacity check that fails loudly.
# Constant (audit 113, 25): shell rows per INSERT statement; SQL batching.

MODULE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE_ROOT.parent
DBC = REPO_ROOT / "azerothcore-wotlk/build/server/data/dbc"
CORE_SQL = REPO_ROOT / "azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql"
DATA = MODULE_ROOT / "data/d3"
# Phase 2 (Architect, 2026-09-19): this sheet is the designer's numbers, not D3's
# published reference data, so it moved to data/tunables/ and out of
# data/d3/. Its runtime home is unchanged - it is still this generator's
# table, not dc_tunables. data/tunables/README.md says so under "Files with
# their own table".
TUNABLES = MODULE_ROOT / "data/tunables"
GENERATED = MODULE_ROOT / "data/generated"
# The gem shells' engineering map: it has no D3 source, so it sits beside legendary_gem_items.csv, not in data/d3.
GEM_SPELLS = MODULE_ROOT / "data/legendary_gem_spells.csv"
# The buffs the player wears for a gem's effects (buff icons build 1, diablocraft-xumo): their own sheet, because a gem
# can have a shell above and one or two buffs here (Gogok has none above and two here, one per rank band).
GEM_BUFFS_SHEET = MODULE_ROOT / "data/legendary_gem_buffs.csv"
# The buffs the player wears for a class's effects (buff icons build 2, diablocraft-b3zj), and the text of the class
# buffs that had none: one row each, the amounts named from the class sheets so none is written twice.
CLASS_BUFFS_SHEET = MODULE_ROOT / "data/class_buffs.csv"
# The buffs a pylon or shrine gives (pylons and shrines P1, diablocraft-plgq2): one row per kind, the numbers named from
# the `pylon_`/`shrine_` rows of data/tunables/combat.csv so none is written twice.
PYLON_BUFFS_SHEET = MODULE_ROOT / "data/pylon_buffs.csv"
POWER_BUFFS_SHEET = MODULE_ROOT / "data/legendary_power_buffs.csv"
LEGENDARY_POWERS_SHEET = MODULE_ROOT / "data/legendary_powers.csv"
PYLON_TUNABLES_SHEET = TUNABLES / "combat.csv"
UPDATES = MODULE_ROOT / "data/sql/db-world/updates"
CLIENT_DBC = REPO_ROOT / "client-patch/dbc/Spell.dbc"
# The client resolves $<name> from this file and nowhere else; the server
# ignores it and reads the same numbers from dc_spell_values.
CLIENT_VARIABLES_DBC = REPO_ROOT / "client-patch/dbc/SpellDescriptionVariables.dbc"
# Step 6: the cooldown categories the rune families share have to exist as
# SpellCategory.dbc rows or the core reads them back as no category at all.
CLIENT_CATEGORY_DBC = REPO_ROOT / "client-patch/dbc/SpellCategory.dbc"
# The stock SpellRadius.dbc holds 58 rows (2 to 500 yards, ids 1-65) and has no row for every yardage D3 states (24 yards,
# Acid Cloud - Acid Rain's area, sits between 23 and 25). data/spell_radius_rows.csv lists the rows the module adds: the writer
# gives the server the `spellradius_dbc` rows in the spell migration and the client a SpellRadius.dbc of the stock rows plus ours.
RADIUS_ROWS_SHEET = MODULE_ROOT / "data/spell_radius_rows.csv"
CLIENT_RADIUS_DBC = REPO_ROOT / "client-patch/dbc/SpellRadius.dbc"
FIRST_MODULE_RADIUS_ID = 1000

# Field layout of Spell.dbc, verified by aligning the 234 column names of
# azerothcore's spell_dbc table against SpellEntryfmt in
# src/server/shared/DataStores/DBCfmt.h (every 'f' lands on a float column and
# the string run starts exactly on Name_Lang_enUS).
FMT = ("niiiiiiiiiiiixixiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiifxiiiiiiiiiiiiiiiiiiiiiiiiiiii"
       "fffiiiiiiiiiiiiiiiiiiiiifffiiiiiiiiiiiiiiifffiiiiiiiiiiiiiissssssssssssssss"
       "xssssssssssssssssxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxiiiiiiiiiiixfffxxxiiiii"
       "xxfffxx")
F_ID = 0
F_ATTRIBUTES = 4
F_RECOVERY_TIME = 29
F_CATEGORY_RECOVERY = 30
F_RANGE_INDEX = 46
F_EFFECT_1 = 71
F_EFFECT_RADIUS_1 = 92
# 86, not 110. 110 is EffectMiscValue_1: every shell generated before this fix
# wrote its implicit target into that column and left ImplicitTargetA_1 as the
# cloned spell's own, which is how Threatening Shout inherited a target that
# could miss (docs/handoff-claude-desktop.md, deferred item 5).
F_IMPLICIT_TARGET_A_1 = 86
F_EFFECT_MISC_VALUE_1 = 110
F_SPELL_ICON = 133
F_NAME_ENUS = 136
# Step 8 (Architect ruling, 2026-09-20): the rune name goes in the record's
# rank, which the client draws in the top right of the tooltip and
# GetSpellInfo() returns as its second value. 153 is NameSubtext_Lang_enUS,
# the spell_dbc name for Spell.dbc's Rank: 136 + 16 locale strings + the
# mask beside them. The mask itself is left at the base spell's, exactly as
# the name's already is - Name_Lang_Mask is even on every base we clone, so
# its enUS bit is clear and names still render, which is the proof the
# client does not gate the string on it.
F_RANK_ENUS = 153
F_START_RECOVERY_CATEGORY = 205
F_START_RECOVERY_TIME = 206
F_SCHOOL_MASK = 225

# 01-stats S9. D3 element -> WoW spell school mask.
SCHOOL = {"physical": 1, "holy": 2, "fire": 4, "lightning": 8, "cold": 16,
          "poison": 32, "arcane": 64}
SPELL_EFFECT_DUMMY = 3
SPELL_ATTR0_PASSIVE = 0x40
SPELL_ATTR0_IS_ABILITY = 0x10
# Client-only hiding is forbidden on selectable shells (ruling 2026-09-13).
# The sole hidden Primary record is its unlearned Frostbite lockout marker.
SPELL_ATTR0_DO_NOT_DISPLAY = 0x80
# Cannot be dodged, parried or blocked: monsters have no mitigation (02 C8).
SPELL_ATTR0_NO_ACTIVE_DEFENSE = 0x00200000
# SharedDefines.h:499 "Spell cannot miss, or be dodged/parried/blocked", and in
# Unit::MeleeSpellHitResult/MagicSpellHitResult it also skips resist and deflect.
# D3 has no miss, dodge or parry on either side (decisions.md 2026-09-08), so
# every shell carries it - the player's and the ones the module casts for a
# monster alike. Attr0's NO_ACTIVE_DEFENSE above only covers dodge/parry/block.
SPELL_ATTR3_ALWAYS_HIT = 0x00040000
# SharedDefines.h:488 "Stack separately for each caster". A passive aura is a
# multi-slot aura (SpellInfo::IsMultiSlotAura), so while the elite slow was
# passive, two elites each kept their own copy of it without asking for
# anything. A visible debuff is not passive, and Aura::CanStackWith then runs
# past IsMultiSlotAura to "same spell with same caster should not stack" and
# returns false - which makes the arriving slow remove the other elite's
# (Unit::_ApplyAura's RemoveOwnedAuras of everything the new aura cannot stack
# with). This attribute is the core's own answer to exactly that question: it
# returns true from CanStackWith's !sameCaster branch, so the per-caster
# lifetimes survive the record becoming visible. It is not a stacking rule we
# invented; it is the stock one, named.
SPELL_ATTR3_DOT_STACKING_RULE = 0x00000080
# 13-elite-affixes S10 chain beams. A non-PASSIVE dummy aura is sent to the
# client (Aura::CanBeSentToClient); DO_NOT_DISPLAY keeps it out of the aura bar
# and the combat log while its SpellVisual's StateKit still draws the chain.
# ALLOW_AURA_WHILE_DEAD mirrors the wings; NO_AURA_CANCEL stops a right-click
# wiping a tether the player does not own.
SPELL_ATTR0_ALLOW_WHILE_MOUNTED = 0x01000000
SPELL_ATTR0_NO_AURA_CANCEL = 0x80000000
SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD = 0x00100000
CAST_TIME_INSTANT = 1          # SpellCastTimes.dbc id 1 is 0 ms

# Cloning a WoW spell brings its whole rulebook with it, and most of that rulebook
# is wrong for a D3 skill. Rather than clear bits one at a time, every shell gets
# an explicit baseline: instant, no level gate, no weapon requirement, no reagents,
# no resource cost, no spell family. Left alone from the base: the icon, the two
# visual ids, projectile Speed and the effect radius, which is the whole point of
# cloning. Values are set by column name so a field never lands in the wrong slot.
FORCED_ZERO = (
    # "Category" was here until step 6: a clone must not keep the donor's
    # cooldown category, and emit() now writes our own or leaves it at zero.
    "SpellLevel", "BaseLevel", "MaxLevel", "MaxTargetLevel",
    "PowerType", "ManaCost", "ManaCostPct", "ManaCostPerLevel",
    "ManaPerSecond", "ManaPerSecondPerLevel",
    "RequiresSpellFocus", "FacingCasterFlags",
    # 04 K3: stances are removed. Clear both halves of required/excluded masks.
    "ShapeshiftMask", "unk_320_2", "ShapeshiftExclude", "unk_320_3",
    "Totem_1", "Totem_2", "RequiredTotemCategoryID_1", "RequiredTotemCategoryID_2",
    "EquippedItemSubclass", "EquippedItemInvTypes",
    "ChannelInterruptFlags", "AuraInterruptFlags", "InterruptFlags",
    "SpellClassSet", "SpellClassMask_1", "SpellClassMask_2", "SpellClassMask_3",
    "CumulativeAura", "RequiredAuraVision",
    "CasterAuraState", "TargetAuraState", "ExcludeCasterAuraState", "ExcludeTargetAuraState",
    "CasterAuraSpell", "TargetAuraSpell", "ExcludeCasterAuraSpell", "ExcludeTargetAuraSpell",
)
# The same clear for the fields that come in numbered slots: the three effects' numbers (EffectDieSides, EffectRealPointsPerLevel,
# EffectBasePoints and the aura period: the old "EffectBaseDice" is no field of the 3.3.5 record and "EffectAmplitude" is EffectAuraPeriod)
# and the eight reagents with their counts.
FORCED_ZERO_EFFECTS = tuple(f"{prefix}{slot}" for slot in range(1, 4)
                            for prefix in ("EffectBasePoints_", "EffectDieSides_", "EffectRealPointsPerLevel_", "EffectAuraPeriod_"))
FORCED_ZERO_REAGENTS = tuple(f"{prefix}{slot}" for slot in range(1, 9) for prefix in ("Reagent_", "ReagentCount_"))


def check_forced_zero(columns, names=None):
    """Refuse a FORCED_ZERO name that is no spell_dbc column. A name that matches nothing used to be skipped without a word, which left the
    donor's value on every record (TotemCategory_1 for RequiredTotemCategoryID_1 kept the stock totem tools on 37 class records)."""
    wanted = FORCED_ZERO + FORCED_ZERO_EFFECTS + FORCED_ZERO_REAGENTS if names is None else names
    unknown = [name for name in wanted if name not in columns]
    if unknown:
        raise SystemExit("FORCED_ZERO names no spell_dbc column: " + ", ".join(unknown) +
                         " (the column names are those of the core's spell_dbc table; a name that is no column clears nothing)")


# Spell rewrite step 1 (docs/research/wow-spell-mapping.md section 1): where a
# named number lives in the record. "base" takes an effect slot; the record-level
# kinds take their own field; "exact" has no field that can hold it exactly and
# is printed and read from the exact-value table instead. Cooldown is still
# deliberately absent from the writable kinds: the module owns it until step 6.
# Cost became a kind in step 5 (see MODULE_PAID_SKILLS for the one exception).
TOKEN_KIND = {}
for _token in ("damage_pct", "damage_bonus_pct", "enemy_damage_pct", "damage_taken_pct",
               "damage_reduction_pct", "damage_share_pct", "max_damage_pct", "slow_pct",
               "chill_pct", "crit_chance_pct", "crit_damage_pct", "crit_taken_pct",
               "attack_speed_pct", "movement_speed_pct", "armor_pct", "armor_points",
               "resistance_pct", "resistance_points", "thorns_pct", "thorns_share_pct",
               "primary_stat_pct", "dodge_pct", "block_pct", "max_life_pct", "heal_pct",
               "heal_life", "heal_per_hit_life", "heal_per_second_life", "absorb_life",
               "absorb_pct", "life_regen_pct", "max_pool_resource", "max_pool_pct",
               "generated_resource", "gain_resource", "gain_pct", "regen_per_second_resource",
               "regen_pct", "cost_reduction_pct", "knockback_yards", "life_threshold_pct",
               "life_floor_pct", "max_bonus_pct", "cooldown_reduction_pct",
               "cooldown_reduction_seconds", "cc_duration_reduction_pct", "duration_bonus_pct",
               "pet_life_pct", "radius_share_pct", "resistance_share_pct",
               "resource_cost_share_pct",
               # diablocraft-wizard-records, step 1: the Wizard's new plain
               # numbers. cast_count and absorb_hit_count have no field and
               # stay in the exact-value home.
               "absorb_capacity_life_pct", "cost_reduction_resource", "damage_threshold_pct",
               "damage_cap_pct", "max_absorb_pct"):
    TOKEN_KIND[_token] = "base"
for _token in ("duration_seconds", "duration_minutes", "dot_duration_seconds",
               "slow_duration_seconds", "chill_duration_seconds", "stun_duration_seconds",
               "freeze_duration_seconds", "blind_duration_seconds", "fear_duration_seconds",
               "immobilize_duration_seconds", "charm_duration_seconds",
               "absorb_duration_seconds", "bonus_duration_seconds"):
    TOKEN_KIND[_token] = "duration"
# Step 5: the cost is a record field now (ManaCost, in Rage units, with
# PowerType). Cooldown is still the module's until step 6.
TOKEN_KIND["cost_resource"] = "cost"
TOKEN_KIND["radius_yards"] = "radius"
TOKEN_KIND["interval_seconds"] = "period"
# A chain count: how many enemies the ability REACHES. The +1/-1 lives in the
# chain FIELD branch below, because it is a property of EffectChainTargets -
# the core's own count includes the primary victim - and not of this name.
TOKEN_KIND["target_count"] = "chain"
# How many enemies are already near you, which gates or scales an effect
# (Brawler's "as long as there are 3 enemies within 12 yards"). It reaches
# nobody, so it is an ordinary base-points number with no conversion of its
# own (Architect, 2026-09-20).
TOKEN_KIND["nearby_enemy_count"] = "base"
TOKEN_KIND["proc_chance_pct"] = "proc_chance"
TOKEN_KIND["max_stacks_count"] = "stacks"
TOKEN_KIND["charge_count"] = "charges"
# Step 6: the cooldown and the charge recharge are record fields now. Both are
# written by emit() from the skill sheet, so these two kinds check the field
# against the values sheet rather than writing it a second time.
TOKEN_KIND["cooldown_seconds"] = "cooldown"
TOKEN_KIND["charge_recharge_seconds"] = "recharge"
TOKEN_KIND["max_count"] = "max_targets"

# Step 8 (Architect ruling, decisions.md 8d89601): Inspiring Presence's
# SPELLMOD_DURATION reaches every record of a shout, because a spell modifier's
# mask is a skill bit and a rune shares its skill's. Three of those records'
# duration is not the shout's own but a side effect inside it - Hardened
# Wrath's armour window, Demoralize's taunt, Terrify's fear - and the ruling is
# that those three stay what they are. DurationIndex is the field the modifier
# moves, so a number that must not move cannot live there: these go to the
# exact-value home instead, where the sentence renders $<name> from
# SpellDescriptionVariables and the module reads the same literal out of
# dc_spell_values. The record's DurationIndex is then free for the shout's own
# duration, which the rune inherits from its skill and which does double.
#
# This is the record's OWN row only. The inherited row of the same token is the
# skill's shout duration and keeps its field.
SIDE_EFFECT_DURATIONS = {
    ("War Cry", "Hardened Wrath", "duration_seconds"),
    ("Threatening Shout", "Demoralize", "duration_seconds"),
    ("Threatening Shout", "Terrify", "fear_duration_seconds"),
    # Wizard B3: Ice Blades' freeze and chill (d3planner wizard.js:108, :110)
    # are side effects on the target; Spectral Blade's record keeps its own
    # duration.
    ("Spectral Blade", "Ice Blades", "freeze_duration_seconds"),
    ("Spectral Blade", "Ice Blades", "chill_duration_seconds"),
}

# The same shape for a cooldown (diablocraft-wizard-records): a rune row that
# names a cooldown which is NOT the rune's own recovery. Teleport - Reversal's
# "set the remaining cooldown to 1 second" is what a second cast does to
# Teleport's timer, and Archon - Teleport's "cast Teleport with a 2 second
# cooldown" is the cooldown of Archon form's Teleport, not of Archon. Neither
# may become the record's RecoveryTime, which would make the rune a 1-second
# (or 2-second) skill; both are exact values the sentence renders as $<name>,
# and the record keeps its skill's cooldown. Every other rune cooldown row IS
# the rune's own recovery and goes into RecoveryTime.
CONDITIONAL_COOLDOWNS = {
    ("Teleport", "Reversal", "cooldown_seconds"),
    ("Archon", "Teleport", "cooldown_seconds"),
}

# An unused SpellClassSet: no stock record in the shipped client Spell.dbc uses
# 20 (only 0, 1, 3-13, 15 and 17 occur), so a modifier keyed to it can only ever
# reach our shells. One mask bit per skill; a rune shares its skill's bit.
BARBARIAN_FAMILY = 20
# SpellDescriptionVariables.dbc rows we own. Stock ids are three digits.
FIRST_VARIABLE_ID = 81000
# The reserved block for token-storage helper records (mapping report section 2).
HELPER_ID_FIRST, HELPER_ID_LAST = 82400, 82499


# --- the reserved blocks, one set per class ---------------------------------
# diablocraft-wizard-records (Architect, 2026-09-22): the generator runs once
# per class_map.csv row that has sheets, and each class owns four things no
# other class may use - a spell family, a block for its skill, rune and passive
# records, a block for its helper records and a block of cooldown categories.
# A future class takes the next free set and adds its row here; every block is
# checked against the others and against the stock DBCs when the generator runs.
#
# The Barbarian's records are not one block: its skills, runes and passives are
# 81000-81156 and the companions it grew later sit at fixed offsets above them
# (the potion and identify shells at 81202-81204, the ability auras from 81310,
# the control auras from 81710, the proc from 81910, the passive effects at
# 82300-82304). Those stay where they are; only its three reserved blocks are
# named here. 83000-83001 are the chain beams, 84000 up the wings - separate writers - so every class's records sit below
# 84000, inside the one DELETE range this writer owns.
#
# The Wizard's family: 21 is, like 20, a SpellClassSet no stock Spell.dbc record
# carries (checked in main() against the shipped file, as 20 was).
class ClassBlocks:
    def __init__(self, stem, family, records, helpers, categories):
        self.stem = stem
        self.family = family
        self.records = records          # (first, last) for skills, runes, passives
        self.helpers = helpers          # (first, last) helper records
        self.categories = categories    # (first, last) cooldown categories


CLASS_BLOCKS = {
    "barbarian": ClassBlocks("barbarian", BARBARIAN_FAMILY, (81000, 81156),
                             (HELPER_ID_FIRST, HELPER_ID_LAST), (8100, 8199)),
    "wizard": ClassBlocks("wizard", 21, (83100, 83299), (83300, 83399), (8200, 8299)),
    "monk": ClassBlocks("monk", 22, (83650, 83849), (83850, 83949), (8300, 8399)),
    # The first class above the shared span: no stock Spell.dbc record and no other writer holds 85100-85399
    # (the wings are 84000-84006, the retired trade-skill pilot 85000-85003, world_0013).
    "necromancer": ClassBlocks("necromancer", 23, (85100, 85299), (85300, 85399), (8400, 8499)),
    # Live before its skill sheets: until they are in data/d3 only the class's own resource records are written
    # (its Energy rate). Family 24 is the next no stock record carries; the class rows keep the stock Paladin's
    # SpellClassSet until the records carry it (docs/contracts/crusader-class.md).
    "crusader": ClassBlocks("crusader", 24, (85400, 85599), (85600, 85699), (8500, 8599)),
    # Live before its skill sheets, as the Crusader's: until they are in data/d3 only the resource records are written
    # (its Energy rate and the regeneration mask for its two module-paid powers). Family 25 is the next no stock record
    # carries; the class row keeps the stock Hunter's SpellClassSet until the records carry it (docs/contracts/demon-hunter-class.md).
    "demon_hunter": ClassBlocks("demon_hunter", 25, (85700, 85899), (85900, 85999), (8600, 8699)),
    # Family 26 is the next no stock record carries; the client row takes it with the records (docs/contracts/witch-doctor-class.md).
    "witch_doctor": ClassBlocks("witch_doctor", 26, (86000, 86199), (86200, 86299), (8700, 8799)),
    # Family 27 is the next no stock record carries; the client row takes it with the records (docs/contracts/shaman-class.md).
    "shaman": ClassBlocks("shaman", 27, (86300, 86499), (86500, 86599), (8800, 8899)),
}

# Ids held for a class whose records are not written yet, beside the blocks above, so its records need no second
# change here: stem -> (records, helpers, categories). None is held now.
RESERVED_BLOCKS = {}

# The span every class below the wings shares: the Barbarian's companions, the chain beams, the gems, pylons, power
# buffs and bounties and the Wizard's and Monk's blocks. Ids above it belong to other writers (the wings,
# generate_wings.py) except the class blocks named above, so the spell SQL deletes this span up to the highest id it
# writes and then each class block above it, never one span across the wings.
SHARED_SPAN_LAST = 83999


def owned_spans(written):
    """The (first, last) id ranges the spell SQL replaces, for the ids it writes: the shared span from FIRST_SPELL_ID
    to the highest id written in it, then each class block above it (records and helpers) whole, so a record a sheet
    drops is deleted too. An id written above the shared span outside every class block is refused."""
    spans = [(FIRST_SPELL_ID, max(identifier for identifier in written if identifier <= SHARED_SPAN_LAST))]
    for block in CLASS_BLOCKS.values():
        for first, last in (block.records, block.helpers):
            if first > SHARED_SPAN_LAST:
                spans.append((first, last))
            elif last > SHARED_SPAN_LAST:
                raise SystemExit("%s: block %d-%d straddles the shared span's end %d"
                                 % (block.stem, first, last, SHARED_SPAN_LAST))
    stray = sorted(identifier for identifier in written
                   if not any(first <= identifier <= last for first, last in spans))
    if stray:
        raise SystemExit("spell ids %s are above %d and in no class block" % (stray[:5], SHARED_SPAN_LAST))
    return spans


def module_spell(identifier):
    """True for an id this writer owns: the shared span, a class block above it, or a reserved block."""
    if FIRST_SPELL_ID <= identifier <= SHARED_SPAN_LAST:
        return True
    ranges = [r for block in CLASS_BLOCKS.values() for r in (block.records, block.helpers)]
    ranges += [r for blocks in RESERVED_BLOCKS.values() for r in blocks[:2]]
    return any(first <= identifier <= last for first, last in ranges)


def check_blocks():
    """No two class or reserved blocks share an id or a cooldown category."""
    named = [(stem, kind, r) for stem, block in CLASS_BLOCKS.items()
             for kind, r in (("records", block.records), ("helpers", block.helpers),
                             ("categories", block.categories))]
    named += [(stem, kind, r) for stem, blocks in RESERVED_BLOCKS.items()
              for kind, r in zip(("records", "helpers", "categories"), blocks)]
    for index, (stem, kind, (first, last)) in enumerate(named):
        for other_stem, other_kind, (other_first, other_last) in named[index + 1:]:
            if (kind == "categories") == (other_kind == "categories") and first <= other_last and other_first <= last:
                raise SystemExit("%s %s %d-%d overlaps %s %s %d-%d" % (stem, kind, first, last,
                                                                       other_stem, other_kind, other_first, other_last))


# Legendary gems, part 10b-3 (diablocraft-y75r): the shells a gem's power casts, one block for every class (a gem
# is not a class's own skill), ids listed in data/legendary_gem_spells.csv and kept inside this block.
GEM_ID_FIRST, GEM_ID_LAST = 83400, 83499
# Pylons and shrines (diablocraft-plgq2): the buff a pylon or shrine gives, one record per kind, from data/pylon_buffs.csv.
# 83500-83510 are the eleven kinds; the rest of the block is for what parts P2 (Speed's knock-up) adds.
PYLON_ID_FIRST, PYLON_ID_LAST = 83500, 83549
# Legendary powers (diablocraft-pl8fc): the buff a legendary power or set bonus shows while it is on, from
# data/legendary_power_buffs.csv; every class, like the gems.
POWER_BUFF_ID_FIRST, POWER_BUFF_ID_LAST = 83550, 83599
# Bounties W2 (diablocraft-e719a): the bounties' block, every class's; its first record is the Click objective's channel, one shell
# the module casts on the player. Its length is maxroll's (bounties: "Clicking on an objective will start a 4 second channel"), the number the rifts
# tunable bounty_click_channel_ms gives the server; test_bounty_click_shell.py holds the two together once the row is on the sheet.
BOUNTY_ID_FIRST, BOUNTY_ID_LAST = 83600, 83649
BOUNTY_CLICK_SPELL = BOUNTY_ID_FIRST
BOUNTY_CLICK_CAST_MS = 4000
# Bounties (diablocraft-dm9vg.10, ruling 2026-10-12): the travel cast from the open world, Town Portal's length by default; the
# rifts tunable bounty_travel_cast_ms gives the server its length, test_bounty_travel_shell.py holds the two together.
BOUNTY_TRAVEL_SPELL = BOUNTY_ID_FIRST + 1
BOUNTY_TRAVEL_CAST_MS = 1500
# P2 (diablocraft-eok78, pylons.md 6.9, 6.10): Conduit's strike, Speed's knock-up aura and the stock knockback it casts.
PYLON_CONDUIT_STRIKE, PYLON_SPEED_KNOCKUP, PYLON_SPEED_THROW = 83511, 83512, 83513
SPELL_ATTR1_NO_AURA_ICON = 0x10000000   # SharedDefines.h: "Hide in aura bar (client only)"
SPELL_EFFECT_KNOCK_BACK = 98
RANGE_ANYWHERE = 13                     # stock SpellRange.dbc 50000 yd: the module picks the monsters in reach
GEM_PAY_PERIOD_TUNABLE = "gem_moratorium_pay_period_ms"
# heal (10b-4): a name-only record, like hit; absorb (10b-4): the shield the player wears.
GEM_EFFECTS = ("hit", "heal", "stagger", "dot", "pulse", "stun", "taunt", "slow", "absorb")
# The effects that are a buff on the player; every other aura is a debuff on the enemy.
GEM_BUFFS = ("pulse", "absorb")


def block_for_helper(identifier):
    """The class whose helper block holds this id, or None."""
    for block in CLASS_BLOCKS.values():
        if block.helpers[0] <= identifier <= block.helpers[1]:
            return block
    return None


def block_for_category(identifier):
    """The class whose cooldown-category block holds this id, or None."""
    for block in CLASS_BLOCKS.values():
        if block.categories[0] <= identifier <= block.categories[1]:
            return block
    return None
# Effects that read the record's own duration and stack count: on these a
# tooltip number would be live aura behaviour, so the writer leaves them be.
AURA_EFFECTS = (6, 27, 35, 65, 119, 128, 143)

# --- step 5: the cost, and who pays it ------------------------------------
# decisions.md 2026-09-20 (design ruling): the cost moves into the spell record and the
# core pays it. The reductions the records below write are SPELLMOD_COST
# auras, and core-patches/0014 - approved the same day - is what makes the
# core multiply them instead of adding them up. A record's cost is in its
# PowerType slot's units: which slot a class's resource lives in and how many
# of its units one point is are the class resource registry's
# (diablocraft-resource-registry; generate_class_resources.py, the sheets
# data/d3/ and data/tunables/class_resources.csv). Every class power is one
# slot unit a point (storage_scale 1): a 25 Fury skill is ManaCost 25 on Rage,
# which the stock client prints as a tenth and the rebuilt client by the row's
# units per point (class_power_tokens.h UnitsPerPointFor). Arcane Power is
# Energy at one a point (Q1=1A, decisions.md 2026-09-23; Mana before,
# 2026-09-22 Q4): Ray of Frost's 16 is ManaCost 16.
RESOURCES = generate_class_resources.registry()
# The conversion name the value map records for a (slot, scale) pair.
CONVERSION_NAMES = {("Rage", 10): "rage_tenths", ("Rage", 1): "rage_points", ("Mana", 1): "mana_points",
                    ("Energy", 1): "energy_points", ("Runic Power", 1): "runic_power_points",
                    ("Focus", 1): "focus_points"}


def power_of(d3_class):
    """(the record's PowerType, units per D3 resource point, the conversion the
    value map names) for a class's primary resource, from the registry."""
    for entry in RESOURCES:
        if entry["d3_class"] == d3_class and entry["role"] == "primary":
            name = CONVERSION_NAMES.get((entry["power"], entry["scale"]),
                                        "%s_x%d" % (entry["power"].lower().replace(" ", "_"), entry["scale"]))
            return entry["power_id"], entry["scale"], name
    raise SystemExit("class_resources.csv: %s has no primary resource" % d3_class)


def primary_regeneration(d3_class):
    """What the hidden regeneration aura adds for a class's primary resource,
    per second, or None when the slot's own gain already is the D3 rate
    (Arcane Power on Energy's native 10/s) or the resource does not refill."""
    for entry in RESOURCES:
        if entry["d3_class"] == d3_class and entry["role"] == "primary":
            return entry["aura_regen"] or None
    return None


def primary_energy_rate(d3_class):
    """The percent the Energy-rate passive adds to the native gain for a
    class's primary resource, or None when the class has none (its resource
    is not on Energy, or Energy's own 10/s already is the D3 rate)."""
    for entry in RESOURCES:
        if entry["d3_class"] == d3_class and entry["role"] == "primary":
            return entry["energy_rate_pct"]
    return None


def energy_rate_effects(power_id, percent):
    """The ENERGY_RATE record's three effect slots as {column prefix: [slot 1,
    slot 2, slot 3]}: slot 1 is the percent aura on the power, the other two
    are empty."""
    return {"Effect_": [SPELL_EFFECT_APPLY_AURA, 0, 0],
            "EffectAura_": [SPELL_AURA_MOD_POWER_REGEN_PERCENT, 0, 0],
            "EffectMiscValue_": [power_id, 0, 0],
            "EffectMiscValueB_": [0, 0, 0],
            # Exact: no die side, the amount is the number.
            "EffectBasePoints_": [percent, 0, 0],
            "EffectDieSides_": [0, 0, 0],
            "ImplicitTargetA_": [TARGET_UNIT_CASTER, 0, 0],
            "ImplicitTargetB_": [0, 0, 0],
            "EffectRadiusIndex_": [0, 0, 0],
            "EffectSpellClassMaskA_": [0, 0, 0]}


def class_lookup_cases(manifest, kind, suffix, class_ids):
    """The C++ `if (classId == N) return SPELL;` lines for the manifest's records
    of one kind, whose names are '<D3 class><suffix>', in spell id order."""
    return "".join(
        "    if (classId == %d)\n        return %d;\n"
        % (class_ids[r["name"].rsplit(suffix, 1)[0]], int(r["spell_id"]))
        for r in sorted(manifest, key=lambda r: int(r["spell_id"]))
        if r["kind"] == kind)


# The Barbarian's primaries are Fury generators with no cost; primary_spells.py
# writes their PowerType from here.
POWER_FURY = power_of("Barbarian")[0]
# The one skill the same ruling leaves the module paying: Whirlwind charges per
# channel tick, its D3 cost (7 / attack_speed + 3) is speed-dependent and
# ManaPerSecond is static, so no record field can hold it. Its shells carry no
# ManaCost and its Fury number stays an exact value the module reads back.
MODULE_PAID_SKILLS = ("Whirlwind",)
# The Wizard's three channelled spells are the same shape: D3 drains their
# Arcane Power per second of channel (d3planner simulator/cast.js scales the
# cost by channeling/60 per tick), which ManaCost - one charge per cast -
# cannot say. The per-second drain is part B's; until then the number sits in
# the exact-value home and the record carries no ManaCost (brief step 4).
CHANNEL_DRAIN_SKILLS = ("Ray of Frost", "Arcane Torrent", "Disintegrate",
                        # The Necromancer's Siphon Blood and the Demon Hunter's Rapid Fire (decisions of the PM on
                        # diablocraft-vawmy.13): the same shape, a real channel the module drains and deals the strikes of.
                        "Siphon Blood", "Rapid Fire",
                        # Strafe (diablocraft-vawmy.28): the same shape, and the Demon Hunter moves while it lasts.
                        "Strafe",
                        # The Witch Doctor's Firebats (diablocraft-vxrcu.13): the same shape, a real channel the module drains in Mana.
                        "Firebats")
# A channel the player keeps up while walking: its record takes none of the donor's interrupt flags (the donor, Volley, stops on movement).
CHANNEL_WHILE_MOVING_SKILLS = ("Strafe",)
# A channel D3 ends the moment the player walks (Rapid Fire; the donor spell's record has no interrupt flags of its
# own, so the flag is written here). The core ends a channel on a step through ChannelInterruptFlags
# (AURA_INTERRUPT_FLAG_MOVE, SpellDefines.h), and the module's loop ends with the core's channel. Only movement:
# turning to aim, being hit and casting through stay out, so a standing Demon Hunter keeps channelling.
CHANNEL_ENDS_ON_MOVE_SKILLS = ("Rapid Fire",)
AURA_INTERRUPT_FLAG_MOVE = 0x00000008
# The Wizard's ground damage over time (diablocraft-wizard-resource item 5,
# PM review 2026-09-22: stock first). Blizzard and Meteor's molten ground are
# the stock ground-DoT shape - a persistent area aura on a dynamic object
# (Spell::EffectPersistentAA) whose periodic effect ticks every unit inside
# (AuraEffect::Update -> PeriodicTick). The aura is PERIODIC_DUMMY with the
# sheet's interval_seconds as its period and dot_duration_seconds as its life,
# and the module's AuraScript deals each tick through the sheet (Rend's shape).
GROUND_DOT_SKILLS = ("Blizzard", "Black Hole")
# diablocraft-wizard-mechanics: Energy Twister - Wicked Wind "no longer
# travels but spins in place" - the same stationary ground, one rune only (the
# base twister and its other runes move and are the module's:
# EnergyTwister::Start in dc_wizard_energy_twister.cpp).
GROUND_DOT_RUNES = ("Energy Twister - Wicked Wind",)
# Meteor's molten ground starts where and when the meteor LANDS, 1.25 s after
# the cast (delay_seconds, ruling 2026-09-22), and Meteor Shower drops seven.
# A stock persistent area aura starts at cast and no 3.3.5 field holds a fixed
# delay (Spell::CalculateDelayMomentForDst is distance / Speed), so each
# Meteor record's ground moves to a helper record of the same shape, which
# the module casts at each landing point once the delay has run.
METEOR_GROUND_SKILL = "Meteor"
METEOR_GROUND = "%s - molten ground"
# Meteor - Meteor Shower is seven spread meteors of 277% each, every one with
# its own 70% molten ground over 2 s (d3planner simulator/wizard.js:681-682,
# :701 and :718-721 at the pin 898918b); the sheet carries only the 277% and
# the rune inherits the base's single impact and molten rows, so it keeps no
# ground and deals nothing until the multi-meteor mechanic exists.
GROUND_DOT_BLOCKED = ()
WIZARD_GROUND_SCRIPT = "dc_wizard_ground"
# Values a sheet row states for the module to read and no sentence prints
# (Architect, 2026-09-20): Whirlwind's channel terms, which D3 uses to build a
# per-tick cost the tooltip never shows. They are exact values like any other
# number no field can hold, they carry their own source, and they are the one
# kind of values row with no placeholder - so they are listed, not inferred.
# One row, not a token: Meteor - Molten Impact's sourced 18 yards, which its
# sentence says as "Greatly increases the size" and never prints (PM review,
# 2026-09-22). Listing the token would let any unprinted radius through.
MODULE_READ_ROWS = {("Meteor", "Molten Impact", "radius_yards"),
                    # diablocraft-wizard-mechanics: sourced numbers the
                    # sentences say in words ("nearby", "immediately") or not
                    # at all; each row carries its simulator line.
                    ("Diamond Skin", "Diamond Shards", "radius_yards"),
                    ("Teleport", "Calamity", "radius_yards"),
                    ("Hydra", "", "radius_yards"),
                    ("Hydra", "Arcane Hydra", "radius_yards"),
                    ("Hydra", "Blazing Hydra", "radius_yards"),
                    ("Hydra", "", "projectile_count"),
                    ("Meteor", "Meteor Shower", "radius_yards"),
                    ("Meteor", "Meteor Shower", "damage_pct"),
                    ("Meteor", "Meteor Shower", "dot_duration_seconds"),
                    ("Ice Armor", "Frozen Storm", "radius_yards"),
                    ("Ice Armor", "Ice Reflect", "radius_yards"),
                    ("Ice Armor", "Ice Reflect", "freeze_duration_seconds"),
                    ("Frost Nova", "Frozen Mist", "chill_duration_seconds"),
                    ("Explosive Blast", "Short Fuse", "duration_seconds"),
                    # diablocraft-wizard-b3: Scorch's wall (its half-width
                    # and reach), Arcane Mines' explosion and mine cap, and
                    # Frost Hydra's cone, each from the pinned simulator line
                    # its row cites. No sentence prints them.
                    ("Arcane Orb", "Scorch", "radius_yards"),
                    ("Arcane Orb", "Scorch", "range_yards"),
                    ("Arcane Torrent", "Arcane Mines", "radius_yards"),
                    ("Arcane Torrent", "Arcane Mines", "max_count"),
                    ("Hydra", "Frost Hydra", "radius_yards"),
                    ("Hydra", "Frost Hydra", "cone_width_degrees"),
                    # Item 2: "Chilled enemies have a 5% chance to be Frozen"
                    # never says for how long; the simulator's 60 frames.
                    ("Spectral Blade", "Ice Blades", "freeze_duration_seconds"),
                    ("Spectral Blade", "Ice Blades", "chill_duration_seconds")}
MODULE_READ_TOKENS = ("channel_cost_speed_term_resource", "channel_cost_flat_resource",
                      # diablocraft-proc-coefficients-wiring: each Barbarian and
                      # Wizard skill's and rune's D3 proc coefficient. The
                      # module rolls it (dc_proc_math.h) on the hit that
                      # landed a crit; no sentence prints it.
                      "proc_coefficient",
                      "channel_tick_frames_count", "channel_frames_per_second_count",
                      # Step 8: Inspiring Presence's sentence says its shouts
                      # last "doubled", in a word, and never prints a number.
                      # The sheet row records what the word is worth so the
                      # modifier record can carry it, and no sentence asks for
                      # it.
                      "duration_bonus_pct",
                      # diablocraft-wizard-resource item 5: a Wizard ground
                      # damage-over-time's tick period (Blizzard, Meteor's
                      # molten ground), from the pinned simulator; the
                      # sentence says "over 6 seconds" and never the cadence.
                      "interval_seconds",
                      # diablocraft-wizard-mechanics, ruling 2026-09-22: the three
                      # timing names, each a sourced module-read row because no
                      # stock field holds it - a fixed landing delay (Speed is
                      # distance / speed), a summon's attack frames before
                      # attack speed, and a moving area's travel speed.
                      "delay_seconds", "attack_frames_count",
                      "travel_speed_yards_per_second",
                      # diablocraft-wizard-b3 item 2 (ruling 2026-09-23): a
                      # skill's proc coefficient, the pinned simulator's
                      # proctable (and the per-damage proc: overrides), which
                      # scales Paralysis, Shocking Aspect and Ignite. No record
                      # field holds it and no sentence prints it.
                      "proc_coefficient",
                      # The Demon Hunter's 'Requires Bow' skills (decisions.md
                      # 2026-10-21): the tooltip line is a word, so the sheet row
                      # carries a 1 for the module to read; no sentence prints it.
                      "requires_ranged_weapon")
# The Wizard's ten-minute buffs (diablocraft-wizard-mechanics). The record's
# DurationIndex is the buff's own duration_minutes - the record IS the buff
# the core applies - so no side effect's seconds (a chill, a stack, a burn)
# may take it, own or inherited.
WIZARD_BUFF_SKILLS = ("Ice Armor", "Storm Armor", "Magic Weapon", "Familiar", "Energy Armor")
# "Only one Armor may be active at a time": stock exclusivity, a spell_group of every Armor shell with the EXCLUSIVE
# stack rule (diablocraft-aura-fixes, aura review row 9), not a removal loop in the module. The id is the module's own.
WIZARD_ARMORS = ("Ice Armor", "Storm Armor", "Energy Armor")
WIZARD_ARMOR_GROUP = 90001
SPELL_GROUP_STACK_RULE_EXCLUSIVE = 1
# The reductions, as the stock cost-modifier auras the same ruling asks for.
# Two are passives with a sheet percentage; the third is the one hidden aura
# the module keeps in step with the stat sheet's item and paragon RCR.
SPELL_EFFECT_APPLY_AURA = 6
SPELL_AURA_ADD_PCT_MODIFIER = 108
SPELLMOD_COST = 14
COST_MODIFIER_PASSIVES = ("Relentless", "Sword and Board")
GEAR_COST_MODIFIER = "Resource cost reduction - gear and paragon"

# Step 6 (decisions.md, 2026-09-20): the cooldown moves into the record too,
# and Player::AddSpellAndCategoryCooldowns installs it. RecoveryTime is the
# skill's own; Category and CategoryRecoveryTime are how a base skill and its
# five runes share one timer, which is what that pair is for and what replaces
# the module's own "set it on every ability row" loop. The reductions are
# SPELLMOD_COOLDOWN auras, and core-patches/0014 makes the flat ones land
# before the percentage as D3 does.
SPELL_AURA_ADD_FLAT_MODIFIER = 107
# diablocraft-wizard-mechanics: the stock ids the Wizard's carriers use.
SPELL_EFFECT_SUMMON = 28
SPELL_EFFECT_LEAP = 29
SPELL_EFFECT_PERSISTENT_AREA_AURA = 27
SPELL_EFFECT_APPLY_AREA_AURA_ENEMY = 129
SPELL_EFFECT_APPLY_AREA_AURA_PARTY = 35
SPELL_AURA_DUMMY = 4
SPELL_AURA_MOD_TAUNT = 11
SPELL_AURA_MOD_STUN = 12
SPELL_AURA_SCHOOL_ABSORB = 69
SPELL_AURA_MOD_MELEE_DAMAGE_TAKEN_PCT = 126
SPELL_AURA_MELEE_SLOW = 193
SPELL_AURA_PERIODIC_DUMMY = 226
SPELL_SCHOOL_MASK_ALL = 127
MECHANIC_SNARE = 11
MECHANIC_STUN = 12
MECHANIC_FREEZE = 13
TARGET_DEST_CASTER = 18
TARGET_DEST_DYNOBJ_ALLY = 29
TARGET_DEST_DEST = 87
# SpellCastTargetFlags in the core's SpellInfo.h: the client shows the ground
# cursor for a spell whose Targets mask has it (GitHub #45).
TARGET_FLAG_DEST_LOCATION = 0x40
SPELLMOD_COOLDOWN = 11
# One category per skill that has a shared timer, in a reserved block of its
# own. The stock SpellCategory.dbc holds 262 rows, ids 1-1253, so this block
# collides with nothing; the record suite re-reads both DBCs and checks.
#
# A category only exists as far as the core is concerned if SpellCategory.dbc
# has a row for it: SpellInfo's constructor does
# `CategoryEntry = Category ? sSpellCategoryStore.LookupEntry(Category) : nullptr`
# (SpellInfo.cpp:789 at the pin) and GetCategory() returns CategoryEntry->Id or
# 0 (SpellInfo.cpp:882), so an id with no row reads back as no category at all
# and Player::AddSpellAndCategoryCooldowns never takes its sibling branch. The
# writer therefore emits client-patch/dbc/SpellCategory.dbc as well, with every
# stock row preserved (Architect, 2026-09-20).
COOLDOWN_CATEGORY_FIRST, COOLDOWN_CATEGORY_LAST = 8100, 8199
if CLASS_BLOCKS["barbarian"].categories != (COOLDOWN_CATEGORY_FIRST, COOLDOWN_CATEGORY_LAST):
    raise SystemExit("the Barbarian's category block disagrees with CLASS_BLOCKS")
# Flags 0: the stock values are 1, 2 and 4, and 2 is
# SPELL_CATEGORY_FLAG_COOLDOWN_STARTS_ON_EVENT, which SpellInfo.cpp:1246 reads.
# Ours start when the spell is cast, which is flags 0.
COOLDOWN_CATEGORY_FLAGS = 0
# SPELL_ATTR0_CU_FORCE_SEND_CATEGORY_COOLDOWNS (SpellInfo.h:205), set through
# the stock spell_custom_attr table: the core tells the client about every
# record in the category, not only the one that was cast.
FORCE_SEND_CATEGORY_COOLDOWNS = 0x10000000
COOLDOWN_MODIFIER_PASSIVES = ("Boon of Bul-Kathos",)
# Step 8 (brief step 8): "The duration of your shouts is doubled" is what the
# core calls a SPELLMOD_DURATION modifier. The passive's own sentence names
# the shouts - "Your shouts are: | Battle Rage | Threatening Shout | War Cry"
# - so the mask is read from the sheet rather than written down a second time
# in this generator or in the module.
SPELLMOD_DURATION = 1
# Epiphany's reach (diablocraft-a1noc): "enabling your melee attacks to instantly dash to your target", but the client
# refuses a skill aimed past its record's range. D3's Epiphany adds range to the Monk's skills while it is up; D3's data
# gives no number, so the reach is the designer's (card q-1014-09, 2026-10-14): +15 yards on every Monk skill. One hidden
# SPELLMOD_RANGE aura over the Monk family's every skill bit, lasting Epiphany's own duration_seconds, which the module
# puts on the Monk when Epiphany starts and takes off when it ends (dc_monk_epiphany.cpp, Shells::HelperFor).
SPELLMOD_RANGE = 5
EPIPHANY_REACH = "Epiphany - reach"
# A record the module strikes with, in the Demon Hunter's helper block: Grenadier's giant grenade drops where the Demon Hunter
# falls and hits as Fire (the passive's own record is Physical and no hit rides it). Its id is kept by spell_helper_ids.csv.
GRENADIER_BLAST = "Grenadier - giant grenade"
EPIPHANY_REACH_YARDS = 15
DURATION_MODIFIER_PASSIVES = ("Inspiring Presence",)
SHOUT_LIST = re.compile(r"your shouts are\s*:\s*(.*)", re.I)
GEAR_COOLDOWN_MODIFIER = "Cooldown reduction - gear and paragon"
# GitHub #44: the rune whose buff the player wears, and that buff's identity
# in the helper map. The identity is the name the buff bar shows.
PUNISH_RUNE = "Bash - Punish"
PUNISH_BUFF = "Punish"
FLAME_BLADES_BUFF = "Flame Blades"   # the aura Spectral Blade - Flame Blades puts on the Wizard


# Issue #61: a SPELLMOD reaches only its own record's family, so one gear
# cost and one gear cooldown aura per class, each in that class's family. The
# Barbarian's keep the identities their ids were persisted under; every other
# class's name the class_map.csv class they belong to.
def gear_identity(base, d3_class):
    return base if d3_class == "Barbarian" else "%s - %s" % (base, d3_class)


# Cindercoat (diablocraft-5cqu3): a cost reduction that reaches only the skills of one element. Word three of a skill record's
# SpellClassMask is its element's school bit (SCHOOL), so a hidden SPELLMOD_COST aura per class and element that names that bit in
# word three reaches exactly the records of the element; no other modifier or donor mask of the classes' families uses word three.
# One aura per class for each element a `cost_reduction_pct` row of data/legendary_powers.csv names; the module sets its amount.
def element_cost_elements():
    with LEGENDARY_POWERS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        return sorted({r["skill"] for r in csv.DictReader(stream) if r["kind"] == "element" and r["stat"] == "cost_reduction_pct"})


def element_cost_identity(element, d3_class):
    return "%s skills cost reduction - %s" % (element.capitalize(), d3_class)


# N-COST (Fury of the Vanished Peak): a cost reduction on one skill. A hidden SPELLMOD_COST aura per skill a `skill` row of
# `cost_reduction_pct` in data/legendary_powers.csv names, in the skill's class family, its mask the skill's own bit in word one, so it reaches
# that skill's records (every rune) and nothing else; the module sets its amount.
# Skills whose class code cuts the cost for a time through the shared CostCut piece (combat/dc_cost_cut.h): Vault's Tumble makes the next Vault cost half
# before the cast; the Necromancer's Commander of the Risen Dead (Command Skeletons) and Eternal Torment (the three curses) stand as long as the passive is
# slotted; the Demon Hunter's Perfectionist cuts every Discipline skill (Caltrops, Smoke Screen, Shadow Power, Vault, Marked for Death) as long as it is slotted.
# The Shaman's Lava Surge makes the next Lava Burst free: the whole cost cut stands until that Lava Burst is cast; the Shaman's Elemental Focus
# cuts the next Secondary cast (Chain Lightning, Lava Burst, Earthquake, Elemental Blast) after a critical hit.
# Each has the hidden cost aura a worn item's `cost_reduction_pct` gives, and the two multiply.
CLASS_COST_CUT_SKILLS = ("Vault", "Command Skeletons", "Decrepify", "Leech", "Frailty", "Caltrops", "Smoke Screen", "Shadow Power", "Marked for Death",
                        "Lava Burst", "Chain Lightning", "Earthquake (Shaman)", "Elemental Blast")


def skill_cost_skills():
    with LEGENDARY_POWERS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        return sorted({name for r in csv.DictReader(stream) if r["kind"] == "skill" and r["stat"] == "cost_reduction_pct"
                       for name in r["skill"].split(";")} | set(CLASS_COST_CUT_SKILLS))


def skill_cost_identity(skill):
    return "%s cost reduction" % skill


# N-COST (Aether Walker): a cost put on one skill that has none. A hidden flat SPELLMOD_COST aura per skill a `skill` row of `cost_add_resource` in
# data/legendary_powers.csv names, built as the cost reduction above is (the skill's class family, its bit in word one); the module sets its amount, the
# points in the class resource's units, and the core charges it beside the record's own cost and refuses a cast the player cannot pay.
def skill_cost_add_skills():
    with LEGENDARY_POWERS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        return sorted({name for r in csv.DictReader(stream) if r["kind"] == "skill" and r["stat"] == "cost_add_resource"
                       for name in r["skill"].split(";")})


def skill_cost_add_identity(skill):
    return "%s cost addition" % skill

# Issue #54 (2026-09-21): the stat sheet's Movement Speed had no publisher at
# all - it was accumulated, capped and displayed, and nothing turned it into
# speed. It is published as ONE aggregate aura because the core takes the
# LARGEST SPELL_AURA_MOD_INCREASE_SPEED rather than the sum
# (Unit::UpdateSpeed), so a per-source aura would silently drop every source
# but the biggest. The amount is the sheet's whole total - the capped gear and
# paragon share plus the uncapped skill bonuses - and the module fills it in
# from the sheet, exactly as it fills in the gear cost and cooldown reductions.
#
# The elite-affix slows get the stock negative aura beside it, so the core
# combines the two itself instead of the module overwriting a rate with
# SetSpeed and having to put it back afterwards.
SPELL_AURA_MOD_INCREASE_SPEED = 31
SPELL_AURA_MOD_DECREASE_SPEED = 33
MOVEMENT_MODIFIER = "Movement speed - gear, paragon and skills"
# diablocraft-wizard-resource item 2: a resource that refills by itself (the
# Wizard's Arcane Power, 10 per second in and out of combat) gets one hidden
# aura that does it through the core's own mana regeneration. The rate is the
# class resource registry's regen_per_second (class_resources.csv). Two effects:
#
#   1. SPELL_AURA_MOD_POWER_REGEN, the stock "per 5 seconds" regeneration.
#      Player::UpdateManaRegen (StatSystem.cpp:958) divides it by 5 and puts it
#      in BOTH the normal and the "interrupted" rate (:971, :973), so the
#      five-second rule after a cast does not slow it.
#   2. SPELL_AURA_MOD_POWER_REGEN_PERCENT at -100. The only other term in that
#      function is WoW's Spirit regeneration (:953-955), which that aura
#      multiplies; D3 has no Spirit, so the term goes to zero and the rate is
#      exactly the sheet's.
#
# Not a tuning number: -100 is "none of WoW's Spirit term", and 5 is the core's
# own per-5-seconds unit.
SPELL_AURA_MOD_POWER_REGEN = 85
SPELL_AURA_MOD_POWER_REGEN_PERCENT = 110
POWER_REGEN_SECONDS = 5
NO_SPIRIT_REGEN_PCT = -100
RESOURCE_REGENERATION = "%s - resource regeneration"
# An Energy resource that refills at another rate than the slot's native 10/s (the
# Crusader's Wrath, 2.5/s) gets one hidden passive with ONE effect:
# SPELL_AURA_MOD_POWER_REGEN_PERCENT on Energy, whose amount is the registry's
# energy_rate_pct (-75 for 2.5/s). Player::UpdateEnergyRegen multiplies the native
# 10/s by (100 + amount) / 100 (pinned core StatSystem.cpp:984-992) and
# Player::Regenerate pays the result with a fractional carry (Player.cpp:1939-1948).
# Unlike the Mana aura above it needs no Spirit term and no per-five amount: Energy
# has no Spirit regeneration, and the percent is on the native gain.
ENERGY_RATE = "%s - energy rate"
# diablocraft-dupme (ruling 2026-10-14): a resource the registry has the module pay
# (class_resources.csv paid_by module: every one on Rage or Runic Power, and Wrath
# on Energy) moves on the module's resource pulse (src/stats/dc_resource_pulse.cpp),
# not on the core's tick, which sends it in 2-second chunks. The class gets one
# hidden passive record with SPELL_AURA_PREVENT_REGENERATE_POWER (294) and
# MiscValue power + 1 per such resource: Player::Regenerate returns before
# touching that slot (pinned core Player.cpp:1911), so the stock tick, its
# out-of-combat loss and its regen-aura share are the pulse's alone. Stock
# classes never get the record. 294's handler only refreshes the mana regen
# fields (SpellAuraEffects.cpp:359), which no module-paid class reads.
SPELL_AURA_PREVENT_REGENERATE_POWER = 294
REGENERATION_MASK = "%s - resource pulse - core regeneration mask"
# Architect, 2026-09-21: one slow record PER SLOWING AFFIX, so the debuff the
# player is now shown says which affix did it. Two things follow.
#
# The identity below is RETIRED, not reused. It held the single shared slow
# (82409) while the aura was hidden and one name was nobody's business; the
# helper map is append-only, so its row stays in spell_helper_ids.csv, its id
# stays spent, and no later identity can be handed it. Nothing was ever
# published at that id - no migration, no client patch - so retiring it costs a
# number and nothing else.
# Archon's transformed skill set (Architect, 2026-09-22, Q5): five records
# with a name, a donor visual and no numbers, kept out of the catalogue
# because Archon swaps them in (part B). The names are d3planner's own, from
# the pinned simulator (d07RiV/d3planner@898918b, simulator/wizard.js
# :1046-1145, skills.archon_arcanestrike ... archon_teleport); their numbers
# are part B's sourced wizard_archon_values.csv. Each one's donor is the
# visuals sheet row "Archon form: <name>". Rank "Archon" tells them apart from
# the base skills of the same name (Slow Time, Teleport) in the tooltip.
ARCHON_SET = ("Arcane Strike", "Arcane Blast", "Disintegration Wave", "Slow Time", "Teleport")
ARCHON_VISUAL = "Archon form: %s"
ARCHON_RANK = "Archon"
ARCHON_SENTENCE = "Archon form ability."
# diablocraft-wizard-mechanics (ruling Q5): the five abilities' numbers, one
# sourced row each, and their geometry as skill_targeting.csv rows named by
# ARCHON_VISUAL. Disintegration Wave is a channel of the Wizard's own shape.
ARCHON_VALUES = "wizard_archon_values.csv"
ARCHON_CHANNEL = ARCHON_VISUAL % "Disintegration Wave"
ARCHON_FORM = "Archon form"
RETIRED_SHARED_SLOW = "Movement speed - elite affix slow - movement modifier"
# Every identity that has been retired this way, with the id it holds on to,
# declared rather than inferred. A retired identity keeps its row and its id
# and has NO record; an identity that is simply missing a record is a bug, and
# the difference between the two is this tuple. Pinning the id here is what
# makes the reuse visible: the map already refuses two identities on one id, so
# an identity that took 82409 would have to move the retired one off it first,
# and this says it may not. Nothing is ever removed from this tuple.
# diablocraft-wizard-mechanics: Meteor's records stopped carrying the molten
# ground in slot 1 (it moved to the METEOR_GROUND helpers), so Comet's numbers
# fit its own record again and its token storage has nothing left to hold;
# Star Pact's the same.
RETIRED_COMET_STORAGE = "Meteor - Comet - token storage"
RETIRED_STAR_PACT_STORAGE = "Meteor - Star Pact - token storage"
# diablocraft-resource-rollout-a item 4: Arcane Power moved from Mana to
# Energy, whose native 10/s is the D3 rate, so the Wizard's Mana regeneration
# aura has nothing left to do.
RETIRED_WIZARD_MANA_REGENERATION = RESOURCE_REGENERATION % "Wizard"
# The Witch Doctor's Mana is paid by the module's resource pulse (paid_by module), which reads
# every regeneration aura on the slot, so a core regeneration aura would count twice and its
# -100 percent would zero the row's own rate: a module-paid row writes none.
RETIRED_WITCH_DOCTOR_MANA_REGENERATION = RESOURCE_REGENERATION % "Witch Doctor"
RETIRED_HELPER_IDENTITIES = ((RETIRED_SHARED_SLOW, 82409), (RETIRED_COMET_STORAGE, 83320),
                             (RETIRED_STAR_PACT_STORAGE, 83321), (RETIRED_WIZARD_MANA_REGENERATION, 83319),
                             (RETIRED_WITCH_DOCTOR_MANA_REGENERATION, 86201))
# And the identity of each affix's own record. The identity is the generator's
# key and stays stable for the id map; the NAME the record carries is the affix
# name out of elite_affixes.csv, because that is what a player reads off the
# debuff.
AFFIX_SLOW_IDENTITY = "%s - affix slow"
# Which affixes slow a player is data, not a list kept here: an affix slows if
# its mechanics sheet gives it a slow_percent. Today that is Frozen Pulse and
# Knockback. Juggernaut's row is the monster's own speed and Missile
# Dampening's is a projectile, so neither is one of these.
AFFIX_SLOW_PARAMETER = "slow_percent"

TARGET_UNIT_CASTER = 1
TARGET_UNIT_TARGET_ENEMY = 6
# The cone the stock Warrior cone spells use: Shockwave (46968), Seismic Slam's
# own base, is ImplicitTargetA_1 = 104 with the cone length in the radius index
# and RangeIndex 1. skill_targeting.csv's cone_enemies rows get the same shape.
TARGET_UNIT_CONE_ENEMY = 104
# diablocraft-ground-target-circles. The client draws the ground cursor as the
# radius of the effect that takes the ground point. These skills' sheet
# `radius_yards` is how far away the point may be, which the tooltip prints and
# the circle must not; the sheet's area for them is its own targeting radius.
REACH_RADIUS_SKILLS = ("Teleport", "Slow Time", "Dashing Strike")
GROUND_TARGETS = ("ground_point_aoe", "ground_area", "line_to_point")
# A ground skill with no area still shows a marker, sized by this tunable
# (combat.csv). It reaches the client only through Spell.dbc.
GROUND_MARKER_TUNABLE = "ground_marker_radius_yards"
# diablocraft-as1z (ruling q-0930-13): Leap's landing circle is the small marker
# too. Its sheet 10 yd is what the server hits, so on the base row it is an
# exact value with no radius slot (like a reach), and the cursor is the marker.
# A rune with its own radius (Call of Arreat, Launch) keeps that area.
MARKER_CURSOR_SKILLS = ("Leap",)
CONE_TARGETS = {"cone_enemies"}
# Anything the module resolves itself (cones, ground areas, moving AoE) still
# needs a legal target for the cast to leave the client, so it aims at the
# enemy or the caster and our hit handler does the real area work.
SELF_TARGETS = {"self", "self_aoe", "self_allies", "self_summon", "self_moving_aoe"}
# GitHub #52. The core picks chain targets in Spell::SelectImplicitChainTargets,
# called only for a nearby or an explicit target, never for the caster, a cone,
# an area or a ground point (two more readers of the count need a damaging effect
# or a conditions row: test_chain_counts.py). These are the skill_targeting.csv
# types whose records take a cone, the caster or a ground point instead (emit()'s
# branches), so a donor spell's chain count on their shells can never pick a
# target. single_enemy and line_pierce (its second effect takes the unit) are not
# here: a count on those is live.
MODULE_TARGETED = CONE_TARGETS | SELF_TARGETS | set(GROUND_TARGETS)
# Natively targeted records whose donor carries a chain count on a slot the sheet does not place: Avenger's Shield's
# second effect. D3's ricochet count is the sheet's slot-1 target_count, so the donor's other slots are zeroed.
DONOR_CHAIN_SLOTS_ZEROED = ("Blessed Shield", "Blessed Shield - Shattering Throw", "Blessed Shield - Piercing Shield")
# A rune whose sentence takes its skill's bounce away ("The shield no longer bounces"): it inherits no target_count and
# its slot 1 holds the primary victim alone (1, the field's one-more-than-the-sheet form of no additional enemy).
RUNES_WITHOUT_CHAIN = {("Blessed Shield", "Piercing Shield")}

# Our reserved spell id block, starting just above the highest stock id (80864)
# so the core's index table stays compact.
FIRST_SPELL_ID = 81000
# 04-classes §6: Call of the Ancients has no mapped WoW spell. Army of the Dead
# is the placeholder summon visual until the designer picks one.
CALL_OF_THE_ANCIENTS_PLACEHOLDER = 42650
PASSIVE_BASE_SPELL = 81            # "Dodge", a plain passive aura with no effects
CAST_TIME_THREE_SECONDS = 14      # SpellCastTimes.dbc id 14 is 3000 ms
HEALTH_POTION_SPELL = 81202       # appended, preserving all earlier shell IDs
HEALTH_POTION_COOLDOWN = 30       # ruling 2026-09-14 Potion decision
# The first legendary potion (diablocraft-potion-regeneration): its own shell,
# appended after Identify All so no earlier id moves. Same heal and cooldown as
# the Health Potion; the legendary power is not built, so the shell carries no
# more than the base heal.
BOTTOMLESS_POTION_SPELL = 81205
BOTTOMLESS_POTION_NAME = "Bottomless Potion of Regeneration"
# decisions.md 2026-09-17. Two shells, appended after the potion so no earlier
# id moves. The unidentified item's spellid_1 points at the first; the hub tome
# makes the player cast the second.
#
# The client draws the green "Use:" line and the cast bar from ITS OWN
# Spell.dbc, not from the server's spell_dbc table, so both of these only
# appear in game once client-patch/dbc/Spell.dbc ships them - which is why this
# generator writes that file too and VERSION.client_patch bumps with it.
IDENTIFY_ITEM_SPELL = 81203
IDENTIFY_TOME_SPELL = 81204
# The designer's tunables live in dc_loot_tuning and the module applies them at runtime,
# the way the town portal does. These are the same numbers in the DBC so the
# CLIENT's cast bar matches the server's cast; change both together or the bar
# and the cast disagree.
def _identify_cast_ms():
    """the designer's two cast times, from loot_tuning.csv, in milliseconds.

    Read rather than written down: the module applies the same two numbers at
    runtime, and a copy here would let the client's cast bar drift away from
    the server's cast the first time the designer retunes one (review item 7).
    """
    path = TUNABLES / "loot_tuning.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["source"].strip() == "identify":
                item = float(row["identify_item_cast_seconds"])
                tome = float(row["identify_tome_cast_seconds"])
                return round(item * 1000), round(tome * 1000)
    raise SystemExit("loot_tuning.csv has no 'identify' row; the identify shells need its cast times")


IDENTIFY_ITEM_CAST_MS, IDENTIFY_TOME_CAST_MS = _identify_cast_ms()
# The look is the designer's pick, like the tome model and the rift portal display.
# 10059 is the base the Town Portal already clones: a sourced, proven
# player-cast shell with a neutral arcane visual. One constant to change.
IDENTIFY_BASE_SPELL = 10059

# --- 09-rifts stage 1 shells (F3, F5, section 2 step 2) ---------------------
# Not skills: these are cast by the server on a creature's behalf (elite affixes
# and the guardians' mapped abilities) or by the player (the town portal). They
# carry no damage in spell data like every other shell; the module computes the
# hit on the 02 section 5 monster path and picks the school from the element
# here. Only the four affixes with an implemented behaviour get a shell; the
# other 24 rows of elite_affixes.csv are name-only in stage 1.
# (name, base WoW spell cloned for icon/animation/visual, element, kind)
RIFT_SHELLS = (
    ("Molten", 62373, "fire", "affix"),
    ("Frozen", 122, "cold", "affix"),
    ("Electrified", 52960, "lightning", "affix"),
    ("Plagued", 3815, "poison", "affix"),
    ("Town Portal", 10059, "physical", "portal"),
    # 09 section 4 / rift_guardian_models.csv: the three stage-1 guardians on
    # the WoW spells that CSV maps each ability to.
    ("Agnidox - Fireball Volley", 11988, "fire", "guardian"),
    ("Agnidox - Flame Nova", 1535, "fire", "guardian"),
    ("Bloodmaw - Leap Rage", 6544, "physical", "guardian"),
    ("Bloodmaw - Frenzy", 28131, "physical", "guardian"),
    ("Cold Snap - Cold Nova", 122, "cold", "guardian"),
    ("Cold Snap - Charge", 52305, "physical", "guardian"),
    # 09-rifts stage 2: one shell per damaging elite affix. DealMonsterHit needs
    # a real SpellInfo for the school and the combat-log line, and the four
    # stage-1 shells only cover fire, cold, lightning and poison. Appended after
    # the stage-1 entries on purpose: the ids above are already stored in
    # dc_rift_affix and dc_rift_guardian, and inserting here would renumber them.
    ("Arcane Enchanted", 1449, "arcane", "affix"),
    ("Desecrator", 845, "physical", "affix"),
    ("Fire Chains", 62373, "fire", "affix"),
    ("Frozen Pulse", 122, "cold", "affix"),
    ("Jailer", 845, "physical", "affix"),
    ("Mortar", 62373, "fire", "affix"),
    ("Orbiter", 52960, "lightning", "affix"),
    ("Poison Enchanted", 3815, "poison", "affix"),
    ("Reflects Damage", 845, "physical", "affix"),
    ("Thunderstorm", 52960, "lightning", "affix"),
)

# --- 01-stats shells --------------------------------------------------------
# Not skills either: the module casts these for the player when a stat, rather
# than a button, produces damage. Thorns (stats.csv row 20) needs a real
# SpellInfo for its school and its combat-log line, exactly like the affixes
# above; it is Physical and clones the same base spell the physical affixes do.
# Appended last for the same reason RIFT_SHELLS was: inserting renumbers ids
# already stored in dc_rift_affix and dc_rift_guardian.
#
# The three Life stats need one each for the same reason. dc_sustain.cpp used to
# call ModifyHealth, which moves the bar and tells the client nothing: no green
# number, no combat-log line, so a player could not see Life Regen working at
# all. Unit::HealBySpell (Unit.cpp:8398) sends SMSG_SPELLHEALLOG, and HealInfo
# demands a SpellInfo, which is what these are.
#
# The base spells are stock heals, cloned for their icon alone - emit() zeroes
# every effect and base point (02 C2), so no stock healing comes with them, and
# HealBySpell plays no cast visual. Holy is the WoW school every stock heal
# uses; it is not a D3 element claim, and the only thing that reads it is the
# core's heal-absorb step, which nothing in this project applies.
STAT_SHELLS = (
    ("Thorns", 845, "physical", "stat"),
    ("Life Regen", 139, "holy", "stat"),          # Renew, a regeneration icon
    ("Life per Hit", 2061, "holy", "stat"),       # Flash Heal, an instant one
    ("Life per Kill", 2054, "holy", "stat"),      # Heal
)


def load_dbc(name):
    data = (DBC / name).read_bytes()
    magic, records, fields, size, string_size = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise SystemExit(f"{name}: not a WDBC file")
    body = data[20:20 + records * size]
    rows = {}
    for index in range(records):
        record = body[index * size:(index + 1) * size]
        rows[struct.unpack("<I", record[:4])[0]] = record
    return rows, data[20 + records * size:], fields, size


def cast_time_index(milliseconds):
    """The SpellCastTimes.dbc row whose base cast time is exactly this.

    Looked up rather than written down: the ids are client data, and a wrong
    one silently gives the player a cast bar of the wrong length.
    """
    rows, _, _, size = load_dbc("SpellCastTimes.dbc")
    for row_id, record in rows.items():
        # SpellCastTimes.dbc: ID, CastTime, CastTimePerLevel, MinCastTime.
        base = struct.unpack_from("<i", record, 4)[0]
        if base == milliseconds:
            return row_id
    raise SystemExit(f"SpellCastTimes.dbc has no {milliseconds} ms row")


def read_csv(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


SHOWN_KINDS = ("skill", "passive")


def shown_names():
    """{record key: the name the player reads} from shown_names.csv.

    A record's key (its name in the sheets, the value map, the legendary sheet and the saved bar) is unique across classes; the
    name the client shows need not be. Only the Spell.dbc name takes the shown one: spellbook, tooltip, aura bar, the skill bar.
    """
    return {row["key"]: row["shown_name"] for row in read_csv("shown_names.csv")}


def shown_name(shown, key):
    """The name the client shows for the record keyed `key`: its row's, a rune's is its skill's shown name before the rune
    (`Earthquake (Shaman) - Aftershock` reads `Earthquake - Aftershock`), every other key is its own name."""
    if key in shown:
        return shown[key]
    skill, dash, rune = key.partition(" - ")
    if dash and skill in shown:
        return shown[skill] + dash + rune
    return key


def class_of_names(classes):
    """{skill or passive key: sheet stem} over `classes` ({stem: (d3_class, skill rows, passive rows)}, in class_map order).

    A key two classes share would make every key-keyed lookup (the value map, the legendary sheet, the saved bar, the
    catalogue) ambiguous, so it is refused with the fix: the later class keys its record `Name (Class)` in its sheets and
    shown_names.csv gives the player the plain Name (Earthquake: the Barbarian's and the Shaman's)."""
    class_of = {}
    d3_class_of = {stem: entry[0] for stem, entry in classes.items()}
    for stem, (_d3_class, class_skills, class_passives) in classes.items():
        for name in ([row["skill_name"] for row in class_skills] + [row["passive_name"] for row in class_passives]):
            if class_of.setdefault(name, stem) != stem:
                raise SystemExit(
                    "%r is both a %s and a %s name: key the %s one %r in its sheets and give it a shown_names.csv row "
                    "that shows %r" % (name, class_of[name], stem, stem, "%s (%s)" % (name, d3_class_of[stem]), name))
    return class_of


def check_shown_names(rows, classes, class_of):
    """shown_names.csv names real keys of the right kind, and no key that carries its class shows it to the player.

    `rows` are the sheet's, `classes` and `class_of` as class_of_names takes and returns them. A key `Name (Class)` of its own
    class is the way out of a shared name, so it must have a row: without one the player reads the suffix."""
    kinds = {stem: {"skill": {r["skill_name"] for r in entry[1]}, "passive": {r["passive_name"] for r in entry[2]}}
             for stem, entry in classes.items()}
    listed = set()
    for row in rows:
        key, kind = row["key"], row["kind"]
        if kind not in SHOWN_KINDS:
            raise SystemExit("shown_names.csv: %r has kind %r, not one of %s" % (key, kind, ", ".join(SHOWN_KINDS)))
        if key in listed:
            raise SystemExit("shown_names.csv: %r is listed twice" % key)
        listed.add(key)
        if key not in class_of or key not in kinds[class_of[key]][kind]:
            raise SystemExit("shown_names.csv: %r is not a %s of any class sheet" % (key, kind))
    for key, stem in class_of.items():
        if key.endswith(" (%s)" % classes[stem][0]) and key not in listed:
            raise SystemExit("%r carries its class and has no shown_names.csv row: the player would read the suffix" % key)


def read_gem_spells():
    with GEM_SPELLS.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_gem_buffs():
    with GEM_BUFFS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_pylon_buffs():
    with PYLON_BUFFS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_power_buffs():
    with POWER_BUFFS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def power_buff_number(buff):
    """The number a legendary power buff states: its row's in data/legendary_powers.csv (the item-owned row of `owner` and `stat`),
    which must be one fixed whole number, since the record's $s1 is baked once for every wearer: above 0, below 0 for a `slow`.
    None for a `dummy` whose row is a range rolled once per item and whose text states no number (Binding of the Lost): the record
    cannot state the wearer's roll; a ranged row whose text states $s1 is still refused."""
    with LEGENDARY_POWERS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["owner"] == buff["owner"] and r["stat"] == buff["stat"] and not r["pieces"]]
    who = "legendary_power_buffs.csv: %s" % buff["owner"]
    if len(rows) != 1:
        raise SystemExit("%s: %s is not one row of data/legendary_powers.csv" % (who, buff["stat"]))
    low, high = float(rows[0]["value_min"]), float(rows[0]["value_max"])
    if buff["aura"] == "dummy" and 0 < low < high and not re.findall(r"\$s\d", buff.get("text", "")):
        return None
    if low != high or not low.is_integer() or (low >= 0 if buff["aura"] == "slow" else low <= 0):
        raise SystemExit("%s: %s is %g-%g, not one whole number of its sign" % (who, buff["stat"], low, high))
    return int(low)


def power_buff_stacks(buff):
    """How far a legendary power buff stacks: the stack_max of its owner's `stack_buff` row (Stone Gauntlets), 0 when the owner stacks
    nothing (one window, The Burning Axe of Sankis)."""
    with LEGENDARY_POWERS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["owner"] == buff["owner"] and r["stat"] == "stack_buff" and not r["pieces"]]
    return int(rows[0]["stack_max"]) if rows else 0


def pylon_tunable(name, what):
    """The number the `pylon_`/`shrine_` rows of data/tunables/combat.csv gives a buff row: the designer's value when he has set one, D3's otherwise.

    The buff's tooltip is baked from this number, so it must be a whole number (a record's $s holds nothing else).
    """
    with PYLON_TUNABLES_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["name"] == name]
    if len(rows) != 1:
        raise SystemExit("pylon_buffs.csv: %s names %r, which is not one row of data/tunables/combat.csv" % (what, name))
    cell = rows[0]["value"].strip() or rows[0]["d3_value"].strip()
    if not cell or not float(cell).is_integer():
        raise SystemExit("pylon_buffs.csv: %s: %r holds %r, not a whole number" % (what, name, cell))
    return int(float(cell))


def read_class_buffs():
    with CLASS_BUFFS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def gem_buff_number(gem_row, cell, what):
    """A gem buff sheet cell that names a legendary_gems.csv column (fixed_1, rank25_value_1...) or holds a whole number.

    The buff's amounts are the gem's own numbers, so none is written twice: a column name is read from the gem's row.
    """
    if cell.isdigit():
        return int(cell)
    value = (gem_row.get(cell) or "").strip()
    if not value or not float(value).is_integer():
        raise SystemExit("legendary_gem_buffs.csv: %s %r is not a whole number of the gem's row" % (what, cell))
    return int(float(value))


# Spell rewrite step 0 (diablocraft-spell-rewrite-0): the sheets carry
# {token} where a number used to be, and the numbers live in the two values
# sheets, keyed by (skill, rune, token, qualifier). Nothing here reads a number
# out of a sentence any more.
_VALUES = {}


def values_for(skill, rune="", passive=False, stem="barbarian"):
    """Every value row of one sheet row, in sentence order.

    `stem` is the class's sheet prefix (class_map.csv's d3_class, lower case):
    every class keeps its numbers in `<stem>_skill_values.csv` and
    `<stem>_passive_values.csv`, in the same seven columns.
    """
    name = "%s_%s_values.csv" % (stem, "passive" if passive else "skill")
    if name not in _VALUES:
        rows = {}
        for row in read_csv(name):
            rows.setdefault((row["skill"], row["rune"]), []).append(row)
        _VALUES[name] = rows
    return _VALUES[name].get((skill, rune), [])


def numbers_for(skill, rune="", passive=False, stem="barbarian"):
    """The numbers in sentence order, as the sheet spells them."""
    return [row["value"] for row in values_for(skill, rune, passive, stem)]


def value_of(skill, rune, token, qualifier="", passive=False, stem="barbarian"):
    """One named number, or None. A missing token is the caller's business."""
    for row in values_for(skill, rune, passive, stem):
        if row["token"] == token and row["qualifier"] == qualifier:
            return float(row["value"])
    return None


PLACEHOLDER = re.compile(r"\{([a-z_]+)(?::([a-z_]+))?\}")


def placeholder_keys(text):
    """The (token, qualifier) keys a tokenised sentence asks for, in order."""
    return [(token, qualifier or "") for token, qualifier in PLACEHOLDER.findall(text)]


# Step 7: the two label lines the 3.3.5 client prints for itself once the
# record carries the number. The client's tooltip builds a power line from
# ManaCost and PowerType and a cooldown line from RecoveryTime and the
# category timer, so a sentence that also carries "Cost: 20 Fury" or
# "Cooldown: 12 seconds" says it twice. Only a segment that is nothing BUT
# that label goes: "Reduce the cost to 9 Fury." and "Remove the Fury cost and
# reduce the cooldown to 6 seconds" are the rune saying what it changes, and
# they stay. So does "Cost: 1 Charge", which no field holds and the client
# cannot print, and every "Generate:" line, which is not a cost at all.
CLIENT_PRINTS = {"cost_resource": "cost", "cooldown_seconds": "cooldown"}
LABEL_LINE = re.compile(r"^(cost|cooldown)\s*:\s*\{([a-z_]+)\}[^{}]*$", re.I)


def client_printed_segments(text, carries):
    """{segment index: token} for the label lines the record now prints.

    `carries` answers, per kind, whether this record actually holds the
    number: Whirlwind is still paid by the module tick by tick, so its record
    has no ManaCost, nothing would print a cost line, and its sentence keeps
    the one it has.
    """
    found = {}
    for index, piece in enumerate(text.split("|")):
        match = LABEL_LINE.match(piece.strip())
        if not match:
            continue
        token = match[2]
        kind = CLIENT_PRINTS.get(token)
        if kind and match[1].lower() == kind and carries(kind):
            found[index] = token
    return found


# Step 11, the designer's ruling of 2026-09-20. `$d` is not a number: the client
# renders it with its own unit, "2 min" or "15 sec", so a sentence reading
# "for $d seconds" prints "for 2 min seconds". The word belongs to the client
# and is taken out of ours. `$t1` IS a bare number and keeps its word, spelled
# out in full - "seconds", never "sec" - which is the other half of the same
# Ruling. Everything else is left alone: `$<name>` values, `$s1`, `$a1` and
# the rest carry no unit of their own.
DURATION_UNIT = re.compile(r"(\$d)\s+(?:seconds?|secs?|minutes?|mins?)\b", re.I)
PERIOD_UNIT = re.compile(r"(\$t1)\s+(?:seconds?|secs?)\b", re.I)
# Step 12, Architect's ruling of 2026-09-21. A one-second period is not written
# as a number in D3: Bloodshed and Unforgiving say "every second", not "every 1
# second". The unit rules above cannot say this - they only take a word off or
# put one on, and this takes the NUMBER out - so it is its own rule, and it is
# decided by the record's own period rather than by the sheet's wording: 1000 ms
# reads "every second", anything else keeps "every $t1 seconds". The `every` is
# part of the pattern on purpose, so the rule can only collapse the phrase it is
# for and never some other sentence that happens to carry a period.
ONE_SECOND_PERIOD = re.compile(r"every\s+\$t1\s+seconds?\b", re.I)
ONE_SECOND_MS = 1000


def spell_out_units(text, period_ms=0):
    """Drop the unit `$d` supplies itself; spell out the one `$t1` does not.

    `period_ms` is the record's own `EffectAuraPeriod_1`. At exactly one second
    the number goes too: see ONE_SECOND_PERIOD above.
    """
    text = PERIOD_UNIT.sub(r"\1 seconds", DURATION_UNIT.sub(r"\1", text))
    if period_ms == ONE_SECOND_MS:
        text = ONE_SECOND_PERIOD.sub("every second", text)
    return text


def bind_marks(text, marks):
    """Substitute each {token} / {token:qualifier} by the mark of THAT key.

    Binding by key rather than by position is the whole point: the values
    sheet is a table, its row order is not a contract, and an editor who
    sorts it must not silently move Frenzy's 4 Fury into the 220% slot. A
    key the sentence asks for and the sheet does not have, a key the sheet
    has and the sentence never asks for, and a key given twice are all
    refused rather than rendered wrong.
    """
    seen = set()

    def substitute(match):
        key = (match[1], match[2] or "")
        if key not in marks:
            raise SystemExit("%s: the sentence asks for {%s} and the values sheet has no such row"
                             % (text[:40], match[1] + (":" + match[2] if match[2] else "")))
        seen.add(key)
        return marks[key]

    body = PLACEHOLDER.sub(substitute, text)
    unused = [key for key in marks if key not in seen]
    if unused:
        raise SystemExit("%s: values with no placeholder: %s" % (text[:40], sorted(unused)))
    return body


def spell_description(body, printed_by_client, category, source):
    """The description a record ships: the sentence's pieces the client does not
    already print, joined by CRLF. The client draws it verbatim, so a {brace} or
    [Name] the fill missed stops the build (text_guard); $s1, $d, $o1 and
    ${$x1-1} are the client's own tokens and pass."""
    parts = []
    for index, part in enumerate(piece.strip() for piece in body.split("|")):
        if index in printed_by_client:
            continue
        if part and part.lower() != (category or "").strip().lower():
            parts.append(part)
    description = "\r\n".join(parts)
    refuse_unfilled(source, description, pattern=UNFILLED_TOKEN_WOW)
    return description


# diablocraft-buff-text (the designer, q-1004-20, 2026-10-04). The text the client shows on
# a buff is the record's AuraDescription. The player's own buffs carry the sentence
# of the skill they stand for; a rune's buff carries the base skill's sentence first
# and then the rune's own. The rule, once:
#   * a line that is a label for casting the skill (Cost, Cooldown, Requires) is not
#     about the buff and is left out; "Generate: N Fury" stays (card q-1005-03,
#     option C, 2026-10-05: Leap's and War Cry's are the two such lines on a worn buff);
#   * nothing is written where there is no sentence;
#   * a part that comes from another record prints that record's numbers, so every
#     bare token gets the record's id (`$s1` -> `$83117s1`) and every `$<name>` is
#     read out of this record's own variable row under a prefix, `base_` for the
#     base skill's sentence on a rune's buff (both records may name `duration_seconds`).
# Enemy-side debuffs (Threatening Shout, Snow-Capped Mountain, Mutilate) are later.
WIZARD_WORN_SKILLS = WIZARD_BUFF_SKILLS + ("Diamond Skin", "Archon", "Explosive Blast")
# The Barbarian marker is a separate record from dc_abilities.cpp Mark(); the player
# wears it where Cast() marks the caster or an ally. None: the base and every rune.
BARBARIAN_WORN_MARKERS = {
    "Sprint": None, "Ignore Pain": None, "War Cry": None, "Battle Rage": None,
    "Wrath of the Berserker": None,
    "Overpower": ("Killing Spree", "Crushing Advance"),
    "Revenge": ("Best Served Cold",),
    "Leap": ("Iron Impact",),
}
BUFF_SKIPPED_LINE = re.compile(r"^(?:cost|cooldown)\s*:|^requires\b", re.I)
BARE_SPELL_TOKEN = re.compile(r"\$((?:[satxo]\d|[dhuni]))(?![A-Za-z0-9])")
VARIABLE_REFERENCE = re.compile(r"\$<([a-z_]+)>")


def buff_sentence(text, owner=None, prefix=""):
    """(a record's sentence as its buff shows it, the `$<name>` variables it asks for).

    `owner` is the spell id the sentence's numbers live on when the buff is another
    record; None leaves the tokens as they are. An unknown bare token stops the build:
    this text is drawn verbatim and nobody reads it before a player does.
    """
    text = "\r\n".join(line for line in text.split("\r\n")
                       if line and not BUFF_SKIPPED_LINE.match(line))
    names = list(dict.fromkeys(VARIABLE_REFERENCE.findall(text)))
    if owner is not None:
        text = BARE_SPELL_TOKEN.sub(lambda match: "$%d%s" % (owner, match[1]), text)
        text = VARIABLE_REFERENCE.sub(lambda match: "$<%s%s>" % (prefix, match[1]), text)
        left = re.search(r"\$(?![0-9<{])\S*", text)
        if left:
            raise SystemExit("buff text: %r has the token %s, which this writer does not know how to "
                             "point at another record" % (text, left[0]))
    return text, names


def validate_helper_map(rows, owner_of_id=None):
    """The persisted identity -> id map, refused unless it is still sound.

    The map is the only thing standing between a rerun and renumbered
    helper spells, so every way it can be wrong is a hard error: the same
    identity twice, the same id twice, an id outside the reserved block, or
    an id that some other shell in the manifest already answers to.
    """
    owner_of_id = owner_of_id or {}
    ids, by_id = {}, {}
    for row in rows:
        # (identity, id) is a Barbarian row, the only shape the map had before
        # it grew a class column; (identity, id, class) names its class.
        identity, wanted = row[0], row[1]
        stem = row[2] if len(row) > 2 else "barbarian"
        if stem not in CLASS_BLOCKS:
            raise SystemExit("spell_helper_ids.csv: %r names the class %r, which has no "
                             "reserved blocks" % (identity, stem))
        first, last = CLASS_BLOCKS[stem].helpers
        if identity in ids:
            raise SystemExit("spell_helper_ids.csv: %r is mapped twice" % identity)
        if wanted in by_id:
            raise SystemExit("spell_helper_ids.csv: id %d is mapped to both %r and %r"
                             % (wanted, by_id[wanted], identity))
        if not first <= wanted <= last:
            raise SystemExit("spell_helper_ids.csv: id %d for %r is outside the %s block %d-%d"
                             % (wanted, identity, stem, first, last))
        if owner_of_id.get(wanted, identity) != identity:
            raise SystemExit("spell_helper_ids.csv: id %d is already the shell %r, not %r"
                             % (wanted, owner_of_id[wanted], identity))
        ids[identity] = wanted
        by_id[wanted] = identity
    return ids


def validate_category_map(rows):
    """The persisted skill -> cooldown category map, refused unless sound.

    Same contract as the helper-id map above and for the same reason: the
    category is what makes a base skill and its runes share one timer, so a
    rerun that renumbered it would move every player's live cooldowns onto a
    different group. Row order is not an identity (Architect's persistent-ID
    principle, 2026-09-20); this file is.
    """
    by_skill, by_id = {}, {}
    for row in rows:
        # (skill, id) is a Barbarian row; (skill, id, class) names its class.
        skill, wanted = row[0], row[1]
        stem = row[2] if len(row) > 2 else "barbarian"
        if stem not in CLASS_BLOCKS:
            raise SystemExit("spell_cooldown_categories.csv: %r names the class %r, which has "
                             "no reserved blocks" % (skill, stem))
        first, last = CLASS_BLOCKS[stem].categories
        if skill in by_skill:
            raise SystemExit("spell_cooldown_categories.csv: %r is mapped twice" % skill)
        if wanted in by_id:
            raise SystemExit("spell_cooldown_categories.csv: category %d is mapped to both "
                             "%r and %r" % (wanted, by_id[wanted], skill))
        if not first <= wanted <= last:
            raise SystemExit("spell_cooldown_categories.csv: category %d for %r is outside the "
                             "%s block %d-%d" % (wanted, skill, stem, first, last))
        by_skill[skill] = wanted
        by_id[wanted] = skill
    return by_skill


def choose_category_id(skill, ids, stem="barbarian", reserved=None):
    """A skill keeps the category it has; a new one takes the lowest free id
    in its own class's block, or with `reserved` (pool -> (ids, message)) the lowest
    free one of the ids reserved for the current bead (spell_id_reservations.py)."""
    if skill in ids:
        return ids[skill]
    first, last = CLASS_BLOCKS[stem].categories
    used = set(ids.values())
    held = reserved("category:" + stem) if reserved is not None else None
    if held is not None:
        mine, message = held
        for candidate in mine:
            if candidate not in used:
                ids[skill] = candidate
                return candidate
        raise SystemExit(message)
    for candidate in range(first, last + 1):
        if candidate not in used:
            ids[skill] = candidate
            return candidate
    raise SystemExit("the %s cooldown category block %d-%d is full" % (stem, first, last))


def choose_helper_id(identity, ids, taken, stem="barbarian", reserved=None):
    """An identity keeps the id it has; a new one takes the lowest free id
    in its own class's block, or with `reserved` (pool -> (ids, message)) the lowest
    free one of the ids reserved for the current bead (spell_id_reservations.py)."""
    if identity in ids:
        return ids[identity]
    first, last = CLASS_BLOCKS[stem].helpers
    used = set(ids.values()) | set(taken)
    held = reserved("helper:" + stem) if reserved is not None else None
    if held is not None:
        mine, message = held
        for candidate in mine:
            if candidate not in used:
                return candidate
        raise SystemExit(message)
    for candidate in range(first, last + 1):
        if candidate not in used:
            return candidate
    raise SystemExit("no free %s helper id in %d-%d" % (stem, first, last))


_HELD = None


def reserved_ids(pool):
    """(ids reserved for the current bead in a pool, the message when there are none): the sheet is read on first use.
    None when the outputs go anywhere but the repo's data/generated (a scratch render): nothing there can collide."""
    global _HELD
    if Path(GENERATED).resolve() != (reservations.REPO / "mod-diablocraft" / "data" / "generated").resolve():
        return None
    if _HELD is None:
        _HELD = reservations.Held(reservations.pools_for(sys.modules[__name__]))
    return _HELD.allowed(pool), _HELD.shortfall(pool)


def read_tunables_csv(name):
    """One of the sheets that moved to data/tunables/ but kept its own table."""
    with (TUNABLES / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


# barbarian_runes.csv's modified_cost_cooldown_damage, as a small grammar rather
# than a per-rune special case. Clauses are separated by "|". dc_combat.cpp
# parses the same forms; anything else is an error on both sides, so a new
# CSV value can never be silently dropped. The cost forms name a resource, any
# one of the d3_name column of class_resources.csv (RESOURCES), so a class's own
# resource needs a row there and nothing here; dc_combat.cpp reads the same
# names from the generated registry.
#
# "N% increased damage" is deliberately NOT a damage override: those rows are
# buffs and debuffs ("enemies ... take 10% increased damage from all sources",
# "gain 50% increased damage"), which belong in the additive bucket once auras
# exist, not in the shell's own skill percentage.
RESOURCE_NAMES = "|".join(re.escape(name) for name in
                          sorted({entry["d3_name"] for entry in RESOURCES}, key=len, reverse=True))
RUNE_MODIFIERS = (
    (re.compile(r"^([0-9]+(?:\.[0-9]+)?)% weapon damage$"), "damage"),
    (re.compile(r"^([0-9]+(?:\.[0-9]+)?)% damage$"), "damage"),
    (re.compile(r"^([0-9]+(?:\.[0-9]+)?)% increased damage$"), "buff"),
    (re.compile(r"^Cooldown (?:reduced|increased|changed) to ([0-9]+(?:\.[0-9]+)?) seconds?$"), "cooldown"),
    (re.compile(r"^Cost reduced to ([0-9]+(?:\.[0-9]+)?) (?:%s)$" % RESOURCE_NAMES), "cost"),
    # A cost on a skill that had none (the Crusader's Heaven's Fury - Fires of Heaven): the same kind, the rune's number.
    (re.compile(r"^Cost changed to ([0-9]+(?:\.[0-9]+)?) (?:%s)$" % RESOURCE_NAMES), "cost"),
    (re.compile(r"^(?:%s) cost removed$" % RESOURCE_NAMES), "no_cost"),
    # The rune's record has no recovery and no shared category, so the parent's timer does not reach it.
    (re.compile(r"^Cooldown removed$"), "no_cooldown"),
    # A Life cost (the Necromancer's Blood runes): a percentage of Life, its own kind beside the class resource's cost.
    (re.compile(r"^Health cost ([0-9]+(?:\.[0-9]+)?)%$"), "health_cost"),
    (re.compile(r"^Health cost removed$"), "no_health_cost"),
    (re.compile(r"^Health cost doubled$"), "health_cost_doubled"),
    # What a Primary generates (the Shaman's Stormcaller and Earth Shock): the record carries no generation, the class-powers rule
    # (2b) pays it from the values sheet's generated_resource row, so the cell is read for shape and no record field takes it.
    (re.compile(r"^Generation changed to ([0-9]+(?:\.[0-9]+)?) (?:%s)$" % RESOURCE_NAMES), "generation"),
)


def rune_modifiers(text):
    """{kind: value} for one modified_cost_cooldown_damage cell."""
    out = {}
    for clause in (part.strip() for part in text.split("|")):
        if not clause:
            continue
        for pattern, kind in RUNE_MODIFIERS:
            match = pattern.match(clause)
            if match:
                out[kind] = float(match.group(1)) if match.groups() else 0.0
                break
        else:
            raise SystemExit(f"unparsed rune modifier: {clause!r}")
    return out


# A Life cost is an exact value (token health_cost_pct) the module reads; the skill code charges it (SpendLife, D3's
# percent of max Life, never below 1). The record carries no POWER_HEALTH (SharedDefines.h -2) and no ManaCostPct: the
# core would charge that as well, from the caster's base health (SpellInfo::CalcPowerCost, GetCreateHealth), on top of
# the skill's own (diablocraft-u59aj; it was the shape of stock Life Tap). POWER_HEALTH stays named for the tests.
POWER_HEALTH = -2
HEALTH_COST_TOKEN = "health_cost_pct"
HEALTH_COST_LABEL = re.compile(r"Cost:\s*([0-9]+(?:\.[0-9]+)?)% [Hh]ealth")


def life_cost_pct(skill_row, rune_row=None):
    """The Life cost in percent of a skill (its sheet's health_cost_pct) or of one of its runes (the skill's, unless
    the rune's modifier cell sets, removes or doubles it), or None. A "Cost: N% Health" label in a tooltip must say
    the same number."""
    base = float(skill_row.get("health_cost_pct") or 0) or None
    label = HEALTH_COST_LABEL.search(skill_row.get("full_tooltip_text", ""))
    if (float(label[1]) if label else None) != base:
        raise SystemExit("%s: health_cost_pct %s and its tooltip's cost label disagree"
                         % (skill_row["skill_name"], skill_row.get("health_cost_pct")))
    if rune_row is None:
        return base
    modifiers = rune_modifiers(rune_row.get("modified_cost_cooldown_damage", ""))
    label = HEALTH_COST_LABEL.search(rune_row.get("full_rune_text", ""))
    if label and modifiers.get("health_cost") != float(label[1]):
        raise SystemExit("%s - %s: the tooltip's cost label says %s%% and the modifier cell says %s"
                         % (rune_row["skill_name"], rune_row["rune_name"], label[1], modifiers.get("health_cost")))
    if "no_health_cost" in modifiers:
        return None
    if "health_cost_doubled" in modifiers:
        if base is None:
            raise SystemExit("%s - %s: doubles a Life cost its skill does not have"
                             % (rune_row["skill_name"], rune_row["rune_name"]))
        return base * 2
    return modifiers.get("health_cost", base)


def closest(available, wanted):
    """Pick the stock SpellRange/SpellRadius row nearest the wanted yardage."""
    return min(available.items(), key=lambda pair: abs(pair[1] - wanted))[0]


def targeting_for(row, rune=None, stem="barbarian"):
    """Exact runtime geometry; DBC indices only provide the client cast shape."""
    out = dict(row)
    # Radius-changing runes are sourced from their text, not shell IDs/numbers.
    # The sentence still decides WHICH runes override the geometry - only these
    # two shapes do - and the values sheet supplies the number (step 0).
    if rune:
        text = rune['full_rune_text']
        # Meteor - Molten Impact's "Greatly increases the size" names the
        # change without a number; the sheet's sourced row is the 18 yards of
        # the simulator's impact and molten ground (diablocraft-wizard-resource,
        # PM review 2026-09-22), and the sentence stays as D3 wrote it.
        for pattern in (r'Increase the range of .*?within \{radius_yards\} yards',
                        r'increasing the radius of effect to \{radius_yards\} yards',
                        r'^Greatly increases the size and increases the damage of the Meteor impact',
                        r'^Increases the Black Hole radius to \{radius_yards\} yards'):
            if re.search(pattern, text):
                yards = value_of(rune['skill_name'], rune['rune_name'], 'radius_yards', stem=stem)
                if yards is None:
                    raise SystemExit(f"{rune['rune_name']}: radius sentence with no radius_yards value")
                out['radius_yards'] = f"{yards:g}"
                break
    kind = out['target_type']
    if kind in ('line_pierce', 'line_to_point'):
        if not out.get('width_yards') or float(out['width_yards']) <= 0:
            raise ValueError(f"{out['skill']}: missing positive full line width")
    else:
        out['width_yards'] = ''
    if kind == 'cone_enemies' and not out.get('radius_yards'):
        out['radius_yards'] = out['range_yards']
    return out


def settle_chain_counts(records, columns, manifest, owned, targeting):
    """Give every chain count a record leaves the writer an owner (GitHub #52).

    A shell is cloned from a WoW spell and keeps its EffectChainTargets unless a
    values row places one (`owned`: the ids whose slot 1 a `chain` row wrote;
    D3's number wins). Any other count is the donor's, and it is live only where
    the core can reach it, so a shell whose skill_targeting.csv row says the
    module resolves its targets (MODULE_TARGETED) has the field zeroed, and
    anything else is refused: either D3 states a number and the row is missing,
    or a natively targeted shell has no number, which is the PM's question and
    not a default. A shell finds its row by its own name (the module-cast
    affixes and Thorns have one each), then by its skill's.
    Returns the zeroed fields in the donor log's shape; refuses every shell
    that has neither owner in one message, so the whole list is seen at once.
    """
    slots = [columns.index("EffectChainTargets_%d" % number) for number in (1, 2, 3)]
    zeroed, refused = [], []
    for values, entry in zip(records, manifest):
        identifier, name = entry[0], entry[1]
        if tuple(name.split(" - ", 1)) in RUNES_WITHOUT_CHAIN:
            if identifier in owned:
                raise SystemExit("%s: a rune without a chain has a chain row" % name)
            if values[slots[0]] != 1:
                zeroed.append((identifier, name, columns[slots[0]], values[slots[0]], 1,
                               "RUNES_WITHOUT_CHAIN", name, "no additional enemy"))
                values[slots[0]] = 1
            owned = owned | {identifier}
        if name in DONOR_CHAIN_SLOTS_ZEROED:
            for number, slot in enumerate(slots, 1):
                if number > 1 and values[slot]:
                    zeroed.append((identifier, name, columns[slot], values[slot], 0,
                                   "DONOR_CHAIN_SLOTS_ZEROED", name, "donor's other slot"))
                    values[slot] = 0
        carried = [slot for number, slot in enumerate(slots, 1)
                   if values[slot] and not (number == 1 and identifier in owned)]
        if not carried:
            continue
        key = next((candidate for candidate in (name, name.split(" - ")[0])
                    if candidate in targeting), None)
        kind = targeting[key]["target_type"] if key else None
        if kind not in MODULE_TARGETED:
            refused.append("  %s (spell %d): chain count %s from its donor; %s"
                           % (name, identifier, [values[slot] for slot in carried],
                              "no skill_targeting.csv row" if key is None
                              else "skill_targeting.csv %s is %s" % (key, kind)))
            continue
        for slot in carried:
            zeroed.append((identifier, name, columns[slot], values[slot], 0,
                           "skill_targeting.csv", key, kind))
            values[slot] = 0
    if refused:
        raise SystemExit(
            "chain counts nobody owns: no chain values row places them and no skill_targeting.csv "
            "row marks their targeting module-resolved. Add the values row (D3's number and source), "
            "or the row if the module applies the shell; a natively targeted shell with no D3 number "
            "is the PM's question (GitHub #52)\n" + "\n".join(refused))
    return zeroed


def generate_ancient_templates():
    sql = "-- Module-owned Ancients; runtime Life reads the designer's ancients_life_pct_of_owner tunable. Native fixture 299 supplies schema defaults, not combat numbers.\n"
    for entry,name in [(900100,"Talic"),(900101,"Korlic"),(900102,"Madawc")]:
        sql += f"DELETE FROM creature_template WHERE entry={entry};\nCREATE TEMPORARY TABLE dc_ancient_clone LIKE creature_template;\nINSERT INTO dc_ancient_clone SELECT * FROM creature_template WHERE entry=299;\n"
        sql += f"UPDATE dc_ancient_clone SET entry={entry},name='{name}',subname='',npcflag=0,unit_flags=0,unit_flags2=0,type_flags=0,faction=35,AIName='',ScriptName='dc_ancient',gossip_menu_id=0,lootid=0,pickpocketloot=0,skinloot=0,KillCredit1=0,KillCredit2=0,flags_extra=0;\nINSERT INTO creature_template SELECT * FROM dc_ancient_clone;\nDROP TEMPORARY TABLE dc_ancient_clone;\n"
        sql += f"DELETE FROM creature_template_model WHERE CreatureID={entry};\nINSERT INTO creature_template_model SELECT {entry},Idx,CreatureDisplayID,DisplayScale,Probability,VerifiedBuild FROM creature_template_model WHERE CreatureID=299;\n"
    sql += "DELETE FROM spell_script_names WHERE ScriptName='dc_ancient_bonus';\n"
    names = {"Whirlwind","Leap","Cleave","Furious Charge","Weapon Throw","Seismic Slam"}
    for r in read_csv_generated("spell_shells.csv"):
        if r["kind"] == "active" and r["name"] in names:
            sql += f"INSERT INTO spell_script_names VALUES ({r['spell_id']},'dc_ancient_bonus');\n"
    return sql

def generate_wizard_summon_templates():
    """diablocraft-wizard-mechanics: the Wizard's summons, from wizard_summons.csv, and the Monk's Mystic Ally from
    monk_summons.csv (diablocraft-a0vq0).

    Each is its donor creature's own row and model (the id and the reason are
    the sheet's), with the module's AI and no loot, gossip or credit. Life,
    level, faction and owner are set when it is summoned, from the owner.
    """
    sql = "-- The Wizard's summons: donor rows from wizard_summons.csv; runtime numbers come from the owner and the sheets.\n"
    # diablocraft-a0vq0 (Monk 2.3.13): the Mystic Ally's rows, monk_summons.csv, in the same loop.
    for sheet in ("wizard_summons.csv", "monk_summons.csv"):
        sql += summon_templates(sheet)
    return sql

def summon_templates(sheet):
    sql = ""
    for row in read_csv(sheet):
        entry, donor = int(row["entry"]), int(row["donor_creature"])
        # The Familiar "cannot be targeted or damaged by enemies"; nothing says
        # so of the images, which have Life of their own. The Hydra is the
        # totem the core summons, untargetable like the Familiar. The Mystic
        # Ally has Life of its own and is reborn when it dies, so it can be hit.
        # The Shaman's totems are the core's totems, untargetable like the Hydra.
        flags = 0x02000000 if (sheet == "wizard_summons.csv" and row["summon"] != "Mirror Image") or sheet == "shaman_summons.csv" else 0  # UNIT_FLAG_NOT_SELECTABLE
        name = row["summon"].replace("'", "''")
        sql += (f"DELETE FROM creature_template WHERE entry={entry};\n"
                "CREATE TEMPORARY TABLE dc_wizard_clone LIKE creature_template;\n"
                f"INSERT INTO dc_wizard_clone SELECT * FROM creature_template WHERE entry={donor};\n"
                f"UPDATE dc_wizard_clone SET entry={entry},name='{name}',subname='',npcflag=0,unit_flags={flags},"
                "unit_flags2=0,type_flags=0,faction=35,AIName='',"
                f"ScriptName='{row['script']}',gossip_menu_id=0,lootid=0,pickpocketloot=0,skinloot=0,"
                "KillCredit1=0,KillCredit2=0,flags_extra=0;\n"
                "INSERT INTO creature_template SELECT * FROM dc_wizard_clone;\n"
                "DROP TEMPORARY TABLE dc_wizard_clone;\n"
                f"DELETE FROM creature_template_model WHERE CreatureID={entry};\n"
                f"INSERT INTO creature_template_model SELECT {entry},Idx,CreatureDisplayID,DisplayScale,"
                f"Probability,VerifiedBuild FROM creature_template_model WHERE CreatureID={donor};\n")
    return sql

def generate_ability_data():
    """The shell table and the DB-owned tunables.

    The three positional tables this used to write - dc_ability_data.h,
    dc_ancient_data.h and dc_passive_data.h - are gone (step 4, 2026-09-20).
    Every number they held is in the spell record now and is read by name
    through DC::Combat::Numbers, so what is left here is identity, geometry
    and the tunables table.
    """
    skills = read_csv("barbarian_skills.csv")
    runes = read_csv("barbarian_runes.csv")
    manifest = read_csv_generated("spell_shells.csv")
    ids = {r["name"]: int(r["spell_id"]) for r in manifest if r["kind"] in ("active","rune")}
    geometry = {r["skill"]: r for r in read_csv("skill_targeting.csv")}
    import json
    # What each shell IS: its id, its skill and rune, and the geometry the
    # targeting sheet gives it. The numbers are deliberately not here - they
    # live in the spell records now and are read through dc_spell_numbers.h,
    # which is what made the three positional tables obsolete (step 4).
    shell_rows = []
    for r in skills + runes:
        skill, rune = r["skill_name"], r.get("rune_name", "")
        name = skill + (" - " + rune if rune else "")
        target = targeting_for(geometry[skill], r if rune else None)
        shell_rows.append("    {%d, %s, %s, %s}," % (
            ids[name], json.dumps(skill), json.dumps(rune),
            float(target.get("radius_yards") or 0)))
    shell_passives = ["    {%d, %s}," % (81138 + i, json.dumps(r["passive_name"]))
                      for i, r in enumerate(read_csv("barbarian_passives.csv"))]
    # Every other class's rows after the Barbarian's, in class_map.csv order,
    # so the Barbarian's lines are untouched. Ids are the manifest's.
    passive_ids = {r["name"]: int(r["spell_id"]) for r in manifest if r["kind"] == "passive"}
    for row in read_csv("class_map.csv"):
        stem = sheet_stem(row["d3_class"])
        if stem == "barbarian" or stem not in CLASS_BLOCKS or \
                not (DATA / ("%s_skills.csv" % stem)).is_file():
            continue
        for r in read_csv("%s_skills.csv" % stem) + read_csv("%s_runes.csv" % stem):
            skill, rune = r["skill_name"], r.get("rune_name", "")
            name = skill + (" - " + rune if rune else "")
            target = targeting_for(geometry[skill], r if rune else None, stem)
            shell_rows.append("    {%d, %s, %s, %s}," % (
                ids[name], json.dumps(skill), json.dumps(rune),
                float(target.get("radius_yards") or 0)))
        shell_passives += ["    {%d, %s}," % (passive_ids[r["passive_name"]], json.dumps(r["passive_name"]))
                           for r in read_csv("%s_passives.csv" % stem)]
    # Step 5: the SPELLMOD_COST auras, by the thing that switches each on. The
    # module casts one when its passive is live and keeps the gear one in step
    # with the stat sheet; the record carries the percentage for the passives.
    modifier_rows = ["    {%d, %s}," % (int(r["spell_id"]),
                                        json.dumps(r["name"].rsplit(" - cost modifier", 1)[0]))
                     for r in manifest if r["kind"] == "cost_modifier"]
    # The classes with generated records, in class_map.csv order: the
    # Barbarian and every row the shell loop above wrote.
    generated_classes = [row for row in read_csv("class_map.csv")
                         if sheet_stem(row["d3_class"]) in CLASS_BLOCKS
                         and (DATA / ("%s_skills.csv" % sheet_stem(row["d3_class"]))).is_file()]
    if len(modifier_rows) != len(COST_MODIFIER_PASSIVES) + len(generated_classes):
        raise SystemExit("expected the passives' cost modifiers and one gear record per class, found %d"
                         % len(modifier_rows))
    # Step 6: the same two things for the cooldown. `owner` is the passive
    # whose seconds the record carries - Boon of Bul-Kathos takes a different
    # number off each skill it names, so it has one record per amount and the
    # module casts every record of that owner - or the gear and paragon
    # reduction the module passes in as a custom value. The probe is a record
    # with a real RecoveryTime, so the module can ask the core what the
    # player's own SPELLMOD_COOLDOWN modifiers do to a duration.
    cooldown_rows = ["    {%d, %s}," % (int(r["spell_id"]),
                                        json.dumps(r["name"].rsplit(" - cooldown modifier", 1)[0]))
                     for r in manifest if r["kind"] == "cooldown_modifier"]
    if not cooldown_rows:
        raise SystemExit("no cooldown modifier records were written")
    # Issue #61: each class's gear cost and cooldown aura, by class_map.csv's
    # class_id, with two probes in that class's own block: a record that
    # carries a cost and one that carries a cooldown, so the module can ask the
    # core what the player's own modifiers do to a cost or a duration rather
    # than adding the modifiers up itself (step 5 display ruling, 2026-09-20).
    # A probe has to be the class's, because a class's aura reaches only its
    # own family; any priced (or timed) record of the class answers the same,
    # because the gear aura reaches every one of its skills' mask bits.
    value_map = read_csv_generated("spell_value_map.csv")
    helper_by_name = {r["name"]: int(r["spell_id"]) for r in manifest
                      if r["kind"] in ("cost_modifier", "cooldown_modifier", "element_cost_modifier", "skill_cost_modifier", "skill_cost_adder")}
    element_of = {int(r["spell_id"]): r["element"] for r in manifest}
    name_of = {int(r["spell_id"]): r["name"] for r in manifest}
    element_cost_rows = []
    skill_cost_rows = []
    for skill in skill_cost_skills():
        spell = helper_by_name.get(skill_cost_identity(skill))
        if not spell:
            raise SystemExit("%s: no skill cost modifier record (is it a skill of a class with generated records?)" % skill)
        skill_cost_rows.append("    {%s, %d}," % (json.dumps(skill), spell))
    skill_cost_add_rows = []
    for skill in skill_cost_add_skills():
        spell = helper_by_name.get(skill_cost_add_identity(skill))
        if not spell:
            raise SystemExit("%s: no skill cost addition record (is it a skill of a class with generated records?)" % skill)
        skill_cost_add_rows.append("    {%s, %d}," % (json.dumps(skill), spell))
    gear_rows = []
    for row in generated_classes:
        d3_class = row["d3_class"].strip()
        first, last = CLASS_BLOCKS[sheet_stem(d3_class)].records
        probes = []
        for source in ("cost", "cooldown"):
            owned = [int(r["spell_id"]) for r in value_map
                     if r["source"] == source and first <= int(r["spell_id"]) <= last]
            if not owned:
                raise SystemExit("%s: no record in %d-%d carries a %s to probe" % (d3_class, first, last, source))
            # The sheet's Resource Cost Reduction is measured on the cost probe, which a skill's own cost aura and an element's must not
            # reach: the probe is the first record of a skill and an element that have none, when the class has one.
            if source == "cost":
                uncut = [spell for spell in owned
                         if name_of[spell].split(" - ")[0] not in set(skill_cost_skills()) and element_of[spell] not in element_cost_elements()]
                owned = uncut or owned
            probes.append(min(owned))
        cost = helper_by_name.get("%s - cost modifier" % gear_identity(GEAR_COST_MODIFIER, d3_class))
        cooldown = helper_by_name.get("%s - cooldown modifier" % gear_identity(GEAR_COOLDOWN_MODIFIER, d3_class))
        if not cost or not cooldown:
            raise SystemExit("%s: no gear cost or cooldown modifier record" % d3_class)
        gear_rows.append("    {%d, %d, %d, %d, %d}, // %s" % (int(row["class_id"]), cost, probes[0],
                                                             cooldown, probes[1], d3_class))
        for element in element_cost_elements():
            # The sheet's Resource Cost Reduction is measured on the cost probe, which an element's aura must not reach.
            if element_of[probes[0]] == element:
                raise SystemExit("%s: the cost probe %d is a %s record, which the %s cost aura reaches"
                                 % (d3_class, probes[0], element, element))
            spell = helper_by_name.get(element_cost_identity(element, d3_class))
            if not spell:
                raise SystemExit("%s: no %s cost modifier record" % (d3_class, element))
            element_cost_rows.append("    {%d, %s, %d}, // %s" % (int(row["class_id"]), json.dumps(element), spell, d3_class))
        for skill in skill_cost_skills():
            # The same for a skill's own cost aura: it must not reach the probe.
            if name_of[probes[0]].split(" - ")[0] == skill:
                raise SystemExit("%s: the cost probe %d is a %s record, which its cost aura reaches" % (d3_class, probes[0], skill))
        for skill in skill_cost_add_skills():
            if name_of[probes[0]].split(" - ")[0] == skill:
                raise SystemExit("%s: the cost probe %d is a %s record, which its cost addition reaches" % (d3_class, probes[0], skill))
    # Step 8: the SPELLMOD_DURATION aura. One record per passive that lengthens
    # something, switched on the same way the others are.
    duration_rows = ["    {%d, %s}," % (int(r["spell_id"]),
                                        json.dumps(r["name"].rsplit(" - duration modifier", 1)[0]))
                     for r in manifest if r["kind"] == "duration_modifier"]
    if not duration_rows:
        raise SystemExit("no duration modifier records were written")
    # Issue #54: the aggregate movement aura is named rather than listed,
    # because the module has exactly one use for it and no owner to look up.
    # The affix slows below are the other way round - one per slowing affix,
    # looked up by the affix's name.
    movement_by_owner = {r["name"].rsplit(" - movement modifier", 1)[0]: int(r["spell_id"])
                         for r in manifest if r["kind"] == "movement_modifier"}
    if sorted(movement_by_owner) != [MOVEMENT_MODIFIER]:
        raise SystemExit("expected the aggregate movement aura alone, found %r"
                         % sorted(movement_by_owner))
    # One slow per slowing affix, keyed by the affix name the module asks with.
    # The row carries the record's own name rather than the identity, because
    # the name is what a player sees and a test can hold the generator to it.
    affix_slows = sorted((int(r["spell_id"]), r["name"].rsplit(" - affix slow", 1)[0])
                         for r in manifest if r["kind"] == "affix_slow")
    if not affix_slows:
        raise SystemExit("no affix slow records were written")
    affix_slow_rows = ["    {%d, %s}," % (spell, json.dumps(affix)) for spell, affix in affix_slows]
    # diablocraft-wizard-resource: one regeneration aura per class whose
    # resource refills by itself, looked up by class_map.csv's class_id. A
    # function rather than a table, because a realm whose classes all build
    # their resource (the Barbarian alone) has no row at all.
    class_ids = {row["d3_class"].strip(): int(row["class_id"]) for row in read_csv("class_map.csv")}
    regeneration_cases = class_lookup_cases(manifest, "resource_regeneration", " - resource regeneration", class_ids)
    mask_cases = class_lookup_cases(manifest, "regeneration_mask", " - resource pulse", class_ids)
    energy_rate_cases = class_lookup_cases(manifest, "energy_rate", " - energy rate", class_ids)
    family_rows = "\n".join("    {%d, %d}, // %s" % (class_ids[d3], CLASS_BLOCKS[sheet_stem(d3)].family, d3)
                             for d3 in class_ids if sheet_stem(d3) in CLASS_BLOCKS)
    # diablocraft-wizard-mechanics: Archon form's five abilities, and the
    # Wizard's helper records by identity - a bubble or a molten ground names
    # the record it belongs to, the one whose numbers it deals with.
    by_name = {r["name"]: int(r["spell_id"]) for r in manifest if r["kind"] in ("active", "rune")}
    archon_rows = ["    {%d, %s}," % (int(r["spell_id"]), json.dumps(r["name"]))
                   for r in manifest if r["kind"] == "archon"]
    helper_rows = []
    for r in sorted(manifest, key=lambda r: int(r["spell_id"])):
        if r["kind"] not in ("slow_bubble", "slow_follow", "meteor_ground", "wizard_control", "wizard_shield", "wizard_dot",
                             "wizard_wall", "wizard_stacks", "barbarian_buff", "class_buff", "range_modifier", "strike_helper"):
            continue
        owner = 0
        if r["kind"] in ("slow_bubble", "slow_follow", "meteor_ground", "wizard_dot", "wizard_wall"):
            owner = by_name.get(r["name"].rsplit(" - ", 1)[0])
            if owner is None:
                raise SystemExit("%s: names no skill record" % r["name"])
        helper_rows.append("    {%d, %s, %d}," % (int(r["spell_id"]), json.dumps(r["name"]), owner))
    strike_helper_rows = ["    %s," % json.dumps(r["name"]) for r in sorted(manifest, key=lambda r: int(r["spell_id"]))
                          if r["kind"] == "strike_helper"]
    if not archon_rows or not helper_rows:
        raise SystemExit("the Wizard's Archon abilities or helper records are missing")
    # Legendary gems, part 10b-3: the shell each gem's power casts, by gem id.
    gem_shell_rows = ["    {%d, %s, %s}," % (int(g["spell_id"]), json.dumps(g["gem_id"]), json.dumps(g["effect"]))
                      for g in read_gem_spells()]
    if not gem_shell_rows:
        raise SystemExit("legendary_gem_spells.csv lists no gem shell")
    gem_buff_rows = ["    {%d, %s, %s}," % (int(b["spell_id"]), json.dumps(b["gem_id"]), "true" if b["rank25"] == "1" else "false")
                     for b in read_gem_buffs()]
    if not gem_buff_rows:
        raise SystemExit("legendary_gem_buffs.csv lists no gem buff")
    # Pylons and shrines P1: the buff each kind gives, by the kind's name in data/pylon_buffs.csv.
    pylon_buff_rows = ["    {%d, %s, %s}," % (int(b["spell_id"]), json.dumps(b["kind"]), "true" if b["group"] == "pylon" else "false")
                       for b in read_pylon_buffs()]
    if not pylon_buff_rows:
        raise SystemExit("pylon_buffs.csv lists no buff")
    power_buff_rows = ["    {%d, %s, %s}," % (int(b["spell_id"]), json.dumps(b["owner"]), json.dumps(b["stat"])) for b in read_power_buffs()]
    if not power_buff_rows:
        raise SystemExit("legendary_power_buffs.csv lists no buff")
    # Issue #66: the whole catalogue, not a range. The ids are not contiguous
    # (blocks are reserved per class and feature), and a hand-kept last id went
    # stale the first time a block was appended.
    shell_ids = sorted({int(r["spell_id"]) for r in manifest})
    if len(shell_ids) != len(manifest):
        raise SystemExit("spell_shells.csv lists a spell id twice")
    shell_id_rows = "\n".join("    " + ", ".join(str(i) for i in shell_ids[n:n + 10]) + ","
                               for n in range(0, len(shell_ids), 10))
    (MODULE_ROOT / "src/combat/dc_spell_shells.h").write_text(
        "// Generated by generate_spells.py from the barbarian sheets; never hand-edit.\n"
        "// Identity and geometry only. Every NUMBER a shell carries lives in its\n"
        "// spell record and is read with DC::Combat::Numbers (dc_spell_numbers.h).\n"
        "#pragma once\n#include <cstddef>\n#include <cstdint>\n"
        "namespace DC::Combat::Shells\n{\n"
        "struct Ability { uint32_t id; char const* skill; char const* rune; double radius; };\n"
        "inline constexpr Ability Abilities[] = {\n" + "\n".join(shell_rows) + "\n};\n"
        "inline Ability const* FindAbility(uint32_t id)\n"
        "{\n    for (auto const& row : Abilities)\n        if (row.id == id)\n"
        "            return &row;\n    return nullptr;\n}\n"
        "struct Passive { uint32_t id; char const* name; };\n"
        "inline constexpr Passive Passives[] = {\n" + "\n".join(shell_passives) + "\n};\n"
        "inline Passive const* FindPassive(uint32_t id)\n"
        "{\n    for (auto const& row : Passives)\n        if (row.id == id)\n"
        "            return &row;\n    return nullptr;\n}\n"
        "// The cost-modifier auras. `owner`\n"
        "// is the passive whose percentage the record carries, or the gear and\n"
        "// paragon reduction the module passes in as a custom value.\n"
        "struct CostModifier { uint32_t id; char const* owner; };\n"
        "inline constexpr CostModifier CostModifiers[] = {\n"
        + "\n".join(modifier_rows) + "\n};\n"
        "inline uint32_t CostModifierFor(char const* owner)\n"
        "{\n    for (auto const& row : CostModifiers)\n"
        "    {\n        char const* a = row.owner;\n        char const* b = owner;\n"
        "        while (*a && *a == *b) { ++a; ++b; }\n"
        "        if (*a == *b)\n            return row.id;\n    }\n    return 0;\n}\n"
        "// The cooldown-modifier auras.\n"
        "// One owner can hold several records, because a spell modifier carries\n"
        "// one amount and Boon of Bul-Kathos takes 15 s off one skill and 30 off\n"
        "// two others; the module casts every record whose owner matches.\n"
        "struct CooldownModifier { uint32_t id; char const* owner; };\n"
        "inline constexpr CooldownModifier CooldownModifiers[] = {\n"
        + "\n".join(cooldown_rows) + "\n};\n"
        "// Issue #61: each class's gear-and-paragon cost and cooldown auras, by\n"
        "// class_map.csv's class_id. A modifier reaches only its own family, so\n"
        "// every class has its own pair, and its own two probes: records of that\n"
        "// class with a real cost and a real RecoveryTime, which the module runs\n"
        "// through the core's own Player::ApplySpellMod to read back what the\n"
        "// player's modifiers do.\n"
        "struct GearModifier { uint32_t classId; uint32_t cost; uint32_t costProbe;\n"
        "                      uint32_t cooldown; uint32_t cooldownProbe; };\n"
        "inline constexpr GearModifier GearModifiers[] = {\n"
        + "\n".join(gear_rows) + "\n};\n"
        "inline GearModifier const* GearModifierFor(uint32_t classId)\n"
        "{\n    for (auto const& row : GearModifiers)\n        if (row.classId == classId)\n"
        "            return &row;\n    return nullptr;\n}\n"
        "// Cindercoat: each class's hidden cost aura of one element, by class_map.csv's class_id. It reaches the\n"
        "// records whose SpellClassMask word three is that element's bit; the module sets its amount from the worn items' rows.\n"
        "struct ElementCostModifier { uint32_t classId; char const* element; uint32_t id; };\n"
        "inline constexpr ElementCostModifier ElementCostModifiers[] = {\n"
        + "\n".join(element_cost_rows) + "\n};\n"
        "// N-COST (Fury of the Vanished Peak): the hidden cost aura of each skill a `cost_reduction_pct` skill row names. It reaches\n"
        "// that skill's records alone (its bit in word one, its class's family); the module sets its amount from the worn items' rows.\n"
        "struct SkillCostModifier { char const* skill; uint32_t id; };\n"
        "inline constexpr SkillCostModifier SkillCostModifiers[] = {\n"
        + "\n".join(skill_cost_rows) + "\n};\n"
        "// N-COST (Aether Walker): the hidden flat cost aura of each skill a `cost_add_resource` skill row names, built as the one above is; the module\n"
        "// sets its amount, the points in the wearer's class resource's units.\n"
        "struct SkillCostAdder { char const* skill; uint32_t id; };\n"
        "inline constexpr SkillCostAdder SkillCostAdders[] = {\n"
        + "\n".join(skill_cost_add_rows) + "\n};\n"
        "// The duration-modifier auras. Inspiring\n"
        "// Presence doubles the duration of the shouts its own sentence lists,\n"
        "// and doubling a duration is what the core calls a SPELLMOD_DURATION\n"
        "// modifier: the record carries the percentage and names the skills in\n"
        "// its mask, so the module asks the core for a duration instead of\n"
        "// multiplying one by two.\n"
        "struct DurationModifier { uint32_t id; char const* owner; };\n"
        "inline constexpr DurationModifier DurationModifiers[] = {\n"
        + "\n".join(duration_rows) + "\n};\n"
        "inline uint32_t DurationModifierFor(char const* owner)\n"
        "{\n    for (auto const& row : DurationModifiers)\n"
        "    {\n        char const* a = row.owner;\n        char const* b = owner;\n"
        "        while (*a && *a == *b) { ++a; ++b; }\n"
        "        if (*a == *b)\n            return row.id;\n    }\n    return 0;\n}\n"
        "// Issue #54. The stat sheet's Movement Speed is published\n"
        "// as ONE aura, because the core takes the largest\n"
        "// SPELL_AURA_MOD_INCREASE_SPEED and not the sum: a per-source aura\n"
        "// would drop every source but the biggest. The module fills the amount\n"
        "// in from the sheet, whole percent, the same way it fills in the gear\n"
        "// cost and cooldown reductions.\n"
        "inline constexpr uint32_t MovementAggregate = " + str(movement_by_owner[MOVEMENT_MODIFIER]) + ";\n"
        "// The elite-affix slows, as the stock negative aura, so the core\n"
        "// combines them with the aggregate itself. ONE RECORD PER AFFIX:\n"
        "// the player is shown this one, and a debuff\n"
        "// has to say which affix put it there, so the record's name is the\n"
        "// affix's. Two elites with the SAME affix are still one spell id from\n"
        "// two casters, which is what SPELL_ATTR3_DOT_STACKING_RULE on each of\n"
        "// these records is for; separate ids only separate different affixes.\n"
        "struct AffixSlow { uint32_t id; char const* affix; };\n"
        "inline constexpr AffixSlow AffixSlows[] = {\n"
        + "\n".join(affix_slow_rows) + "\n};\n"
        "inline uint32_t AffixSlowFor(char const* affix)\n"
        "{\n    for (auto const& row : AffixSlows)\n"
        "    {\n        char const* a = row.affix;\n        char const* b = affix;\n"
        "        while (*a && *a == *b) { ++a; ++b; }\n"
        "        if (*a == *b)\n            return row.id;\n    }\n    return 0;\n}\n"
        "// The hidden aura that refills a class's\n"
        "// resource by itself (stock mana regeneration, rate from the class's\n"
        "// resource sheet), by class_map.csv's class_id; 0 for a class whose\n"
        "// resource does not refill by itself.\n"
        "inline uint32_t ResourceRegenerationFor(uint32_t classId)\n"
        "{\n" + (regeneration_cases or "    (void)classId;\n") + "    return 0;\n}\n"
        "// The hidden aura that keeps the core's 2-second\n"
        "// tick off a class's Rage or Runic Power resource, which the module's\n"
        "// resource pulse pays instead; 0 for a class with none there.\n"
        "inline uint32_t RegenerationMaskFor(uint32_t classId)\n"
        "{\n" + (mask_cases or "    (void)classId;\n") + "    return 0;\n}\n"
        "// The hidden passive that takes a class's Energy resource from the slot's\n"
        "// native 10 per second to its D3 rate (percent aura, rate from the class's\n"
        "// resource sheet); 0 for a class whose Energy resource is at the native rate\n"
        "// or not on Energy.\n"
        "inline uint32_t EnergyRateFor(uint32_t classId)\n"
        "{\n" + (energy_rate_cases or "    (void)classId;\n") + "    return 0;\n}\n"
        "// Each class's spell family (its records' SpellClassSet), by class_map.csv's class_id: a record's\n"
        "// SpellFamilyName names its class, so its cost reads at that class's resource scale.\n"
        "struct ClassFamily { uint32_t classId; uint32_t family; };\n"
        "inline constexpr ClassFamily ClassFamilies[] = {\n" + family_rows + "\n};\n"
        "// The class whose family it is; 0 for a family no class owns (a stock record).\n"
        "inline uint32_t ClassOfFamily(uint32_t family)\n"
        "{\n    for (auto const& row : ClassFamilies)\n        if (row.family == family)\n"
        "            return row.classId;\n    return 0;\n}\n"
        "// The abilities Archon form\n"
        "// swaps onto the bar. Not catalogue skills, so not in Abilities.\n"
        "struct ArchonAbility { uint32_t id; char const* name; };\n"
        "inline constexpr ArchonAbility ArchonAbilities[] = {\n" + "\n".join(archon_rows) + "\n};\n"
        "// The helper records the module applies by name: the Wizard's control\n"
        "// auras, shields, Slow Time's bubbles and Meteor's molten grounds, and\n"
        "// the Barbarian's Punish buff. `owner` is the skill record a bubble or\n"
        "// a ground deals with, 0 for the others.\n"
        "struct Helper { uint32_t id; char const* identity; uint32_t owner; };\n"
        "inline constexpr Helper Helpers[] = {\n" + "\n".join(helper_rows) + "\n};\n"
        "// The helper records the module strikes with (a hit of its own, in the record's school): by identity.\n"
        "inline constexpr char const* StrikeHelpers[] = {\n" + "\n".join(strike_helper_rows) + "\n};\n"
        "inline uint32_t HelperFor(char const* identity)\n"
        "{\n    for (auto const& row : Helpers)\n"
        "    {\n        char const* a = row.identity;\n        char const* b = identity;\n"
        "        while (*a && *a == *b) { ++a; ++b; }\n"
        "        if (*a == *b)\n            return row.id;\n    }\n    return 0;\n}\n"
        "// Legendary gems (data/legendary_gem_spells.csv): the shell a gem's power casts or applies,\n"
        "// by the gem's gems.csv id; `effect` is hit, heal, stagger, dot, pulse, stun, taunt, slow or absorb.\n"
        "struct GemShell { uint32_t id; char const* gem; char const* effect; };\n"
        "inline constexpr GemShell GemShells[] = {\n" + "\n".join(gem_shell_rows) + "\n};\n"
        "inline uint32_t GemShellFor(char const* gem)\n"
        "{\n    for (auto const& row : GemShells)\n"
        "    {\n        char const* a = row.gem;\n        char const* b = gem;\n"
        "        while (*a && *a == *b) { ++a; ++b; }\n"
        "        if (*a == *b)\n            return row.id;\n    }\n    return 0;\n}\n"
        "// Legendary gem buffs (data/legendary_gem_buffs.csv): the aura the player wears for a gem's\n"
        "// effect, by gem id and whether the record is the rank-25 one (a record's text cannot depend on the rank).\n"
        "struct GemBuff { uint32_t id; char const* gem; bool rank25; };\n"
        "inline constexpr GemBuff GemBuffs[] = {\n" + "\n".join(gem_buff_rows) + "\n};\n"
        "// Pylons and shrines (data/pylon_buffs.csv): the buff each kind gives, by the kind's name, and whether the kind is a\n"
        "// pylon (its record persists through death) or a shrine.\n"
        "struct PylonBuff { uint32_t id; char const* kind; bool pylon; };\n"
        "inline constexpr PylonBuff PylonBuffs[] = {\n" + "\n".join(pylon_buff_rows) + "\n};\n"
        "// Legendary powers (data/legendary_power_buffs.csv): the buff a power row shows while it is on, by the row's owner and stat.\n"
        "struct PowerBuff { uint32_t id; char const* owner; char const* stat; };\n"
        "inline constexpr PowerBuff PowerBuffs[] = {\n" + "\n".join(power_buff_rows) + "\n};\n"
        "inline bool SameGem(char const* a, char const* b)\n"
        "{\n    while (*a && *a == *b) { ++a; ++b; }\n    return *a == *b;\n}\n"
        "inline uint32_t GemBuffFor(char const* gem, bool rank25)\n"
        "{\n    for (auto const& row : GemBuffs)\n"
        "        if (row.rank25 == rank25 && SameGem(row.gem, gem))\n            return row.id;\n    return 0;\n}\n"
        "inline uint32_t PowerBuffFor(char const* owner, char const* stat)\n"
        "{\n    for (auto const& row : PowerBuffs)\n"
        "        if (SameGem(row.owner, owner) && SameGem(row.stat, stat))\n            return row.id;\n    return 0;\n}\n"
        + ("// Bounties W2: the Click objective's 4 s channel, cast on the player; its effect does nothing.\n"
           "inline constexpr uint32_t BountyClick = %d;\n" % BOUNTY_CLICK_SPELL)
        + ("// Bounties: the travel cast from the open world; the trip goes when it ends.\n"
           "inline constexpr uint32_t BountyTravel = %d;\n" % BOUNTY_TRAVEL_SPELL)
        + ("// Pylons P2: Conduit's strike, Speed's knock-up aura and the stock knockback it casts.\n"
           "inline constexpr uint32_t PylonConduitStrike = %d, PylonSpeedKnockup = %d, PylonSpeedThrow = %d;\n"
           % (PYLON_CONDUIT_STRIKE, PYLON_SPEED_KNOCKUP, PYLON_SPEED_THROW)) +
        "inline uint32_t PylonBuffFor(char const* kind)\n"
        "{\n    for (auto const& row : PylonBuffs)\n"
        "        if (SameGem(row.kind, kind))\n            return row.id;\n    return 0;\n}\n"
        "// Issue #66: every id in spell_shells.csv, sorted. The own-shell guard\n"
        "// reads this, so a shell is ours whatever its SpellFamilyName, and a new\n"
        "// block of shells is covered by the next run rather than a constant.\n"
        "inline constexpr uint32_t ShellIds[] = {\n" + shell_id_rows + "\n};\n"
        "inline bool IsShell(uint32_t id)\n"
        "{\n    std::size_t low = 0, high = sizeof(ShellIds) / sizeof(ShellIds[0]);\n"
        "    while (low < high)\n    {\n        std::size_t const mid = (low + high) / 2;\n"
        "        if (ShellIds[mid] == id)\n            return true;\n"
        "        if (ShellIds[mid] < id)\n            low = mid + 1;\n"
        "        else\n            high = mid;\n    }\n    return false;\n}\n"
        "}\n",
        encoding="utf-8", newline="\n")

    # The CSV wins on every apply (ruling 2026-09-19): ability_tunables.csv is
    # in data/tunables/, so its value is written over the table's rather than
    # only its status and notes, which left an edited number stranded in the
    # sheet on any world that already had the row.
    tunes = read_tunables_csv("ability_tunables.csv")
    sql = "-- Generated by generate_spells.py from ability_tunables.csv; never hand-edit.\nCREATE TABLE IF NOT EXISTS dc_ability_tuning (name VARCHAR(80) PRIMARY KEY, tuned_value DOUBLE NOT NULL, status VARCHAR(20) NOT NULL, notes TEXT NOT NULL);\n"
    def quoted(t): return "'" + str(t).replace("'", "''") + "'"
    for r in tunes:
        sql += "INSERT INTO dc_ability_tuning VALUES (" + ",".join([quoted(r["name"]), str(float(r["value"])), quoted(r["status"]), quoted(r["notes"])]) + ") ON DUPLICATE KEY UPDATE tuned_value=VALUES(tuned_value),status=VALUES(status),notes=VALUES(notes);\n"
    # ancients_life (a flat Life) was replaced by ancients_life_pct_of_owner (ruling 2026-09-29).
    sql += "DELETE FROM dc_ability_tuning WHERE name='ancients_life';\n"
    # The two crit procs roll the skill's own proc coefficient now (ruling 2026-09-29, q-0929-11).
    sql += "DELETE FROM dc_ability_tuning WHERE name IN ('overpower_crit_cdr_chance_pct','slaughter_eruption_chance_pct');\n"
    (GENERATED / "ability_tunables.sql").write_text(sql)
    if "--ability-migration" in sys.argv:
        migration = sys.argv[sys.argv.index("--ability-migration") + 1]
        write_migration(MODULE_ROOT, UPDATES / migration,
                        sql + generate_ancient_templates() + generate_wizard_summon_templates())

def read_csv_generated(name):
    with (GENERATED / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))

def main():
    primary_mechanics, primary_rows = primary_spells.inputs(sys.modules[__name__])
    targeting_only = '--targeting-only' in sys.argv
    if not targeting_only:
        primary_spells.write_header(sys.modules[__name__])
    if not DBC.is_dir():
        raise SystemExit(f"{DBC}: not found. Extract the client DBCs first.")
    spells, strings, fields, size = load_dbc("Spell.dbc")
    if fields != len(FMT):
        raise SystemExit(f"Spell.dbc has {fields} fields, expected {len(FMT)}")

    ranges_raw, _, _, _ = load_dbc("SpellRange.dbc")
    radii_raw, _, _, _ = load_dbc("SpellRadius.dbc")
    durations, _, _, _ = load_dbc("SpellDuration.dbc")
    icons, icon_strings, _, _ = load_dbc("SpellIcon.dbc")
    def icon_path(record):
        offset = struct.unpack_from("<I", record, 4)[0]
        return icon_strings[offset:icon_strings.index(b"\x00", offset)].decode().lower()
    potion_icon = next(key for key, record in icons.items()
                       if icon_path(record).endswith("inv_potion_54"))
    # Each class passive's own icon: data/d3/passive_icons.csv names a stock client icon for it, looked up in SpellIcon.dbc.
    # Every passive shell is a copy of one plain passive (PASSIVE_BASE_SPELL), so without this they all wear its icon.
    icon_by_name = {icon_path(record).rpartition("\\")[2]: key for key, record in icons.items()}
    passive_icon_ids = {}
    for row in read_csv("passive_icons.csv"):
        icon_id = icon_by_name.get(row["icon_name"].lower())
        if icon_id is None:
            raise SystemExit("passive_icons.csv: %s: icon %r is not in SpellIcon.dbc" % (row["passive_name"], row["icon_name"]))
        if row["passive_name"] in passive_icon_ids:
            raise SystemExit("passive_icons.csv: %s is named twice" % row["passive_name"])
        passive_icon_ids[row["passive_name"]] = icon_id
    five_seconds = min(key for key, row in durations.items()
                       if struct.unpack_from("<i", row, 4)[0] == 5000
                       and struct.unpack_from("<i", row, 12)[0] == 5000)
    ranges = {i: struct.unpack("<f", r[12:16])[0] for i, r in ranges_raw.items()}
    radii = {i: struct.unpack("<f", r[4:8])[0] for i, r in radii_raw.items()}
    stock_radii = dict(radii)
    stock_radius_rows = dict(radii_raw)
    module_radii = {}
    radius_users = {}
    with RADIUS_ROWS_SHEET.open(encoding="utf-8-sig", newline="") as stream:
        for radius_row_in_sheet in csv.DictReader(stream):
            identifier, yards = int(radius_row_in_sheet["id"]), float(radius_row_in_sheet["yards"])
            if identifier < FIRST_MODULE_RADIUS_ID or identifier in radii_raw:
                raise SystemExit("spell_radius_rows.csv: id %d is a stock row or below %d" % (identifier, FIRST_MODULE_RADIUS_ID))
            if any(abs(value - yards) < 0.0005 for value in radii.values()) or yards in module_radii.values():
                raise SystemExit("spell_radius_rows.csv: %g yards already has a row" % yards)
            module_radii[identifier] = yards
            radius_users[identifier] = {name.strip() for name in radius_row_in_sheet["used_by"].split(";") if name.strip()}
            if not radius_users[identifier]:
                raise SystemExit("spell_radius_rows.csv: id %d names no record" % identifier)
    # The records that name a module row keep the exact yardage; every other record picks from the stock table as before,
    # so no earlier class's record changes.
    radii.update(module_radii)

    # The schema also tells us which integer columns are signed: EquippedItemClass
    # and friends default to -1, and reading those as unsigned overflows the column.
    columns, unsigned = [], {}
    inside = False
    for line in CORE_SQL.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("CREATE TABLE `spell_dbc`"):
            inside = True
            continue
        if inside:
            if line.startswith(")"):
                break
            stripped = line.strip()
            if stripped.startswith("`"):
                name = stripped.split("`")[1]
                columns.append(name)
                unsigned[name] = "unsigned" in stripped
    if len(columns) != len(FMT):
        raise SystemExit(f"spell_dbc has {len(columns)} columns, expected {len(FMT)}")
    check_forced_zero(columns)

    skills = read_csv("barbarian_skills.csv")
    runes = read_csv("barbarian_runes.csv")
    passives = read_csv("barbarian_passives.csv")
    # Every class's visuals sheet, keyed by (skill, rune). The Barbarian's has
    # no d3_rune column - its runes take their skill's donor - and the
    # Wizard's names a donor per rune as well, so a rune looks for its own row
    # first and falls back to its skill's.
    visuals = {}
    for stem in CLASS_BLOCKS:
        if (DATA / ("%s_visuals.csv" % stem)).is_file():
            for row in read_csv("%s_visuals.csv" % stem):
                key = (row["d3_skill"], row.get("d3_rune", ""))
                if key in visuals:
                    raise SystemExit("%s_visuals.csv: %r is mapped twice" % (stem, key))
                visuals[key] = row
    targeting = {row["skill"]: row for row in read_csv("skill_targeting.csv")}
    # The classes after the Barbarian, in class_map.csv's order: every row
    # that has its sheets and its reserved blocks. The Barbarian is not in this
    # list because its pass is the body of this function, with the companion
    # records only it has; the others run through the generic pass below.
    other_classes = []
    for row in read_csv("class_map.csv"):
        stem = sheet_stem(row["d3_class"])
        if stem == "barbarian" or not (DATA / ("%s_skills.csv" % stem)).is_file():
            continue
        if stem not in CLASS_BLOCKS:
            raise SystemExit("class_map.csv: %s has sheets and no reserved blocks in "
                             "CLASS_BLOCKS" % row["d3_class"])
        power_of(row["d3_class"].strip())
        other_classes.append((stem, row, read_csv("%s_skills.csv" % stem),
                              read_csv("%s_runes.csv" % stem),
                              read_csv("%s_passives.csv" % stem)))
    # What each class's cost is paid in: its WoW power type and how many of
    # that power's units one D3 resource point is (Fury: 10 Rage, Arcane
    # Power: 1 Mana).
    power_of_stem = {sheet_stem(row["d3_class"]): power_of(row["d3_class"].strip())
                     for row in read_csv("class_map.csv")
                     if sheet_stem(row["d3_class"]) in CLASS_BLOCKS}
    # The class whose records are being written right now. Everything up to
    # the generic pass is the Barbarian's; that pass sets it per class, and the
    # helper and category blocks follow it.
    current = {"stem": "barbarian"}
    # A skill whose sheet names the class's second resource as what it spends (the Demon Hunter's Discipline)
    # is paid in that resource's power, with that row's scale; every other skill is paid in the primary.
    second_resource_skills = {}
    for entry in other_classes:
        stem, class_row, class_skills = entry[0], entry[1], entry[2]
        seconds = {e["key"]: e for e in RESOURCES
                   if e["d3_class"] == class_row["d3_class"].strip() and e["role"] == "second"}
        for skill_row in class_skills:
            second = seconds.get(skill_row.get("resource", "").strip().lower())
            if second:
                name = (second["power"], second["scale"])
                second_resource_skills[skill_row["skill_name"]] = (
                    second["power_id"], second["scale"],
                    CONVERSION_NAMES.get(name, "%s_x%d" % (name[0].lower().replace(" ", "_"), name[1])))
    # Which class a skill or passive key belongs to. A key two classes share would make every key-keyed lookup below
    # ambiguous, so it is refused (a shared name takes `Name (Class)` for its key and a shown_names.csv row).
    sheet_classes = {"barbarian": ("Barbarian", skills, passives)}
    sheet_classes.update({entry[0]: (entry[1]["d3_class"].strip(), entry[2], entry[4]) for entry in other_classes})
    class_of_name = class_of_names(sheet_classes)
    check_shown_names(read_csv("shown_names.csv"), sheet_classes, class_of_name)
    # Each class's family must be one no stock record uses and no other class
    # holds - the check that made 20 safe, run for every class.
    check_blocks()
    class_set_offset = columns.index("SpellClassSet") * 4
    families = {}
    for block in CLASS_BLOCKS.values():
        if block.family in families:
            raise SystemExit("family %d is both %s's and %s's" % (block.family,
                                                                families[block.family], block.stem))
        families[block.family] = block.stem
        owned_by_stock = [identifier for identifier, raw in spells.items()
                          if struct.unpack_from("<I", raw, class_set_offset)[0] == block.family
                          # the extracted input may already hold our own records
                          and not module_spell(identifier)]
        if owned_by_stock:
            raise SystemExit("family %d (%s) is used by stock spells %s"
                             % (block.family, block.stem, owned_by_stock[:5]))

    # Step 6: the shared-timer category, one per skill that has a timer, and
    # the charge recharge a charge skill shares instead of a cooldown. The
    # numbers are the values sheet's; nothing here invents one.
    category_path = GENERATED / "spell_cooldown_categories.csv"
    category_rows = [(row["skill"], int(row["category"]), row.get("class") or "barbarian")
                     for row in read_csv_generated("spell_cooldown_categories.csv")] \
        if category_path.is_file() else []
    skill_categories = validate_category_map(category_rows)
    category_class = {skill: stem for skill, _category, stem in category_rows}

    def cooldown_category(skill_name):
        stem = class_of_name.get(skill_name, "barbarian")
        if category_class.setdefault(skill_name, stem) != stem:
            raise SystemExit("spell_cooldown_categories.csv: %r is filed under %s, not %s"
                             % (skill_name, category_class[skill_name], stem))
        return choose_category_id(skill_name, skill_categories, stem, reserved_ids)

    recharge_seconds = {}
    for _stem in ["barbarian"] + [entry[0] for entry in other_classes]:
        for _row in read_csv("%s_skill_values.csv" % _stem):
            if _row["token"] == "charge_recharge_seconds" and not _row["rune"]:
                recharge_seconds[_row["skill"]] = float(_row["value"])

    def base_spell_for(skill_name, rune_name=""):
        visual = visuals.get((skill_name, rune_name)) or visuals.get((skill_name, ""))
        if visual and visual["wow_spell_id"]:
            return int(visual["wow_spell_id"])
        if skill_name == "Call of the Ancients":
            return CALL_OF_THE_ANCIENTS_PLACEHOLDER
        raise SystemExit(f"{skill_name}: no visual mapping and no placeholder")

    def field(record, index):
        raw = record[index * 4:index * 4 + 4]
        kind = FMT[index]
        if kind == "f":
            return struct.unpack("<f", raw)[0]
        return struct.unpack("<I" if unsigned.get(columns[index], True) else "<i", raw)[0]

    def text(record, index):
        offset = field(record, index)
        if not offset or offset >= len(strings):
            return ""
        return strings[offset:strings.index(b"\x00", offset)].decode("utf-8", "replace")

    def escape(value):
        text = str(value).replace("\\", "\\\\").replace("'", "''")
        # A real newline inside a row would break the one-row-per-line shape the
        # generated SQL has always had; MySQL reads these escapes back as bytes.
        return "'" + text.replace("\r", "\\r").replace("\n", "\\n") + "'"

    rows_sql = []
    manifest = []
    records = []          # (values list) per shell, for the client Spell.dbc
    targeting_rows = []
    spell_id = FIRST_SPELL_ID

    shown_by_key = shown_names()

    def emit(name, skill_row, target_row, base_id, element, passive, bleed=False,
             shell_kind=None, cooldown_override=None, rank=""):
        nonlocal spell_id
        base = spells.get(base_id)
        if base is None:
            raise SystemExit(f"{name}: base spell {base_id} is not in Spell.dbc")
        values = []
        for index, column in enumerate(columns):
            kind = FMT[index]
            # Localized text columns are blanked; the *_Lang_Mask beside each of
            # them is an integer bitmask and must stay one.
            localized_text = "_Lang_" in column and not column.endswith("_Mask")
            if kind == "s" or (kind == "x" and localized_text):
                values.append("")
            elif kind == "f":
                values.append(field(base, index))
            else:
                values.append(field(base, index))

        # A rune that reduces its parent's cooldown wins over the parent's own
        # (Ground Stomp - Deafening Crash 12 s -> 8 s, Earthquake - The
        # Mountain's Call 60 s -> 30 s).
        cooldown = skill_row.get("cooldown_seconds", "") if skill_row else ""
        if cooldown_override is not None:
            cooldown = cooldown_override
        values[F_ID] = spell_id
        values[F_NAME_ENUS] = shown_name(shown_by_key, name)
        values[F_RANK_ENUS] = rank
        values[F_SCHOOL_MASK] = SCHOOL[element]
        values[F_RECOVERY_TIME] = int(float(cooldown) * 1000) if cooldown else 0
        # Step 6: the timer the base skill and its runes share. A skill with a
        # cooldown shares that; a charge skill shares its recharge, which is
        # the only cooldown it has and which the module clears again while a
        # charge remains. Either way one category per skill, and none at all
        # for a shell with neither - a category with no time does nothing, but
        # an empty one says something untrue about the record.
        shared = values[F_RECOVERY_TIME]
        skill_name = skill_row["skill_name"] if skill_row else ""
        if not shared and skill_name:
            shared = int(recharge_seconds.get(skill_name, 0) * 1000)
        category = cooldown_category(skill_name) if shared and skill_name else 0
        values[columns.index("Category")] = category
        # The pair is one thing: a category time with no category is a number
        # the core never reads, and the Health Potion, which has a cooldown and
        # no runes to share it with, gets neither.
        values[F_CATEGORY_RECOVERY] = shared if category else 0
        # C1: no global cooldown on any Diablocraft shell.
        values[F_START_RECOVERY_CATEGORY] = 0
        values[F_START_RECOVERY_TIME] = 0
        # C2: zero damage in spell data; the module computes every hit.
        values[F_EFFECT_1] = 0 if passive else SPELL_EFFECT_DUMMY
        for column in FORCED_ZERO_EFFECTS:
            values[columns.index(column)] = 0
        if not passive:
            values[columns.index("Effect_2")] = 0
            values[columns.index("Effect_3")] = 0
            attributes = field(base, F_ATTRIBUTES) & ~SPELL_ATTR0_PASSIVE
            values[F_ATTRIBUTES] = attributes
            target = target_row["target_type"] if target_row else "self"
            if target in CONE_TARGETS:
                values[F_IMPLICIT_TARGET_A_1] = TARGET_UNIT_CONE_ENEMY
            elif target == 'line_pierce':
                values[F_IMPLICIT_TARGET_A_1] = TARGET_UNIT_CONE_ENEMY
                values[columns.index('ImplicitTargetB_1')] = TARGET_UNIT_TARGET_ENEMY
            elif target in ('ground_point_aoe', 'ground_area', 'line_to_point'):
                values[F_IMPLICIT_TARGET_A_1] = 87  # TARGET_DEST_DEST: ground cursor
            elif target in SELF_TARGETS:
                values[F_IMPLICIT_TARGET_A_1] = TARGET_UNIT_CASTER
            else:
                values[F_IMPLICIT_TARGET_A_1] = TARGET_UNIT_TARGET_ENEMY
            if target != 'line_pierce':
                values[columns.index("ImplicitTargetB_1")] = 0
            # A dummy effect has no misc value; the old index bug left ours here.
            values[F_EFFECT_MISC_VALUE_1] = 0

            yards = (target_row or {}).get("range_yards", "")
            radius = (target_row or {}).get("radius_yards", "")
            if yards == "SELF":
                values[F_RANGE_INDEX] = 1            # stock Self Only, 0 yd
            elif yards and yards not in ("MELEE", "UNSURE"):
                values[F_RANGE_INDEX] = closest(ranges, float(yards))
            # A cone measures its length in the radius index, so a cone skill
            # with no published radius uses its stated reach: Seismic Slam's
            # "enemies up to 50 yards in front of you" is a 50 yd cone, not a
            # 50 yd range with no area.
            if not radius and target in CONE_TARGETS and yards not in ("", "SELF", "MELEE", "UNSURE"):
                radius = yards
            if radius and radius != "UNSURE":
                values[F_EFFECT_RADIUS_1] = closest(stock_radii, float(radius))
            else:
                # A blank radius means the skill has no area at all; leaving the
                # cloned spell's radius gave Battle Rage a 30 yd one.
                values[F_EFFECT_RADIUS_1] = 0
        else:
            values[F_ATTRIBUTES] = field(base, F_ATTRIBUTES) | SPELL_ATTR0_PASSIVE
        # --- forced baseline (see FORCED_ZERO) ---------------------------------
        for column in FORCED_ZERO:
            values[columns.index(column)] = 0
        for column in FORCED_ZERO_REAGENTS:
            values[columns.index(column)] = 0
        # No weapon requirement: -1 is "any", and the bases all demand a weapon.
        if "EquippedItemClass" in columns:
            values[columns.index("EquippedItemClass")] = -1
        # Every D3 skill is instant (02 C1/C6). Slam's 1.5 s cast came from here.
        # The town portal is the one shell with a cast time: 09 section 2 gives
        # it 3 s, the same as D3's.
        cast_index = CAST_TIME_INSTANT
        if shell_kind == "portal":
            cast_index = CAST_TIME_THREE_SECONDS
        elif shell_kind == "identify_item":
            cast_index = cast_time_index(IDENTIFY_ITEM_CAST_MS)
        elif shell_kind == "identify_tome":
            cast_index = cast_time_index(IDENTIFY_TOME_CAST_MS)
        elif shell_kind == "bounty_click":
            cast_index = cast_time_index(BOUNTY_CLICK_CAST_MS)
        elif shell_kind == "bounty_travel":
            cast_index = cast_time_index(BOUNTY_TRAVEL_CAST_MS)
        values[columns.index("CastingTimeIndex")] = cast_index
        # AttributesEx..Ex7 carry channelling, combo points and a pile of other
        # rules none of our shells want; the base Attributes carry "on next
        # swing" (Cleave) and "hidden in combat log" (Slam).
        for index in range(1, 8):
            column = "AttributesEx" if index == 1 else f"AttributesEx{index}"
            if column in columns:
                values[columns.index(column)] = 0
        baseline = SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
        values[F_ATTRIBUTES] = baseline | (SPELL_ATTR0_PASSIVE if passive else 0)
        values[columns.index("AttributesEx3")] = SPELL_ATTR3_ALWAYS_HIT
        if target_row and not passive and not bleed and target_row['skill'] != 'Whirlwind':
            target = target_row['target_type']
            if target == 'line_to_point':
                # Destination cursor plus native cone walk redirected by patch 0011.
                values[F_IMPLICIT_TARGET_A_1] = TARGET_UNIT_CONE_ENEMY
                values[columns.index('ImplicitTargetB_1')] = 87
                values[columns.index('Effect_2')] = 149  # native CHARGE_DEST
                values[columns.index('ImplicitTargetA_2')] = 87
                values[columns.index('ImplicitTargetB_2')] = 0
            if target == 'ground_point_aoe':
                values[F_EFFECT_1] = 42  # JUMP_DEST; native jump speeds from donor
                values[F_EFFECT_MISC_VALUE_1] = field(base, F_EFFECT_MISC_VALUE_1)
            # The core's own MaxTargets gate is dropped because our layer decides
            # how many units a cast hits. Projectile Speed is NOT touched: it is
            # one of the fields the header above keeps from the base spell on
            # purpose, and zeroing it took the thrown spear out of Ancient Spear
            # (ruling 2026-09-15: "there should definitely be a spear thrown
            # animation"). test_primaries asserts a non-Primary shell keeps what
            # it was cloned with, which is what caught it.
            if skill_row.get('category') != 'Primary' or \
                    class_of_name.get(skill_row['skill_name'], 'barbarian') != 'barbarian':
                values[columns.index('MaxTargets')] = 0
                if target == 'cone_enemies':
                    # Cone reach lives in EffectRadiusIndex, not an explicit unit gate.
                    values[F_RANGE_INDEX] = 1
        if target_row and target_row['skill'] == 'Whirlwind' and not passive:
            storm = spells[46924]
            values[columns.index("AttributesEx")] = 0x4  # SPELL_ATTR1_IS_CHANNELED; Bladestorm itself is a timed aura
            # SPELL_ATTR5_ALLOW_ACTION_DURING_CHANNEL: another cast (Rend) leaves the channel running (the designer,
            # 2026-10-11, diablocraft-xecwl; the core's own rule, Unit::SetCurrentCastedSpell).
            values[columns.index("AttributesEx5")] |= 0x1
            values[columns.index("ChannelInterruptFlags")] = field(storm, columns.index("ChannelInterruptFlags"))
            # Bladestorm's spin (ruling 2026-10-11, diablocraft-vz49.3): the stock record's own visual, read here, never written down. All six
            # records shared one visual before, so the runes keep what sets them apart (their school, the module's Dust Devils).
            for column in ("SpellVisualID_1", "SpellVisualID_2"):
                values[columns.index(column)] = field(storm, columns.index(column))
            values[columns.index("InterruptFlags")] = field(storm, columns.index("InterruptFlags"))
            values[columns.index("DurationIndex")] = min(k for k,r in durations.items() if struct.unpack_from("<i",r,4)[0] == -1)
            values[F_RANGE_INDEX] = 1
            values[columns.index("Speed")] = 0
            values[F_EFFECT_1] = 6  # native APPLY_AURA; module owns paid damage ticks
            values[columns.index("EffectAura_1")] = 4  # DUMMY, no movement/attack restriction
            values[columns.index("EffectAuraPeriod_1")] = 0
            values[F_IMPLICIT_TARGET_A_1] = TARGET_UNIT_CASTER
            values[columns.index("ImplicitTargetB_1")] = 0
            values[F_EFFECT_RADIUS_1] = 0
        if target_row and (target_row['skill'] in CHANNEL_DRAIN_SKILLS or target_row['skill'] == ARCHON_CHANNEL) \
                and not passive:
            # The Wizard's three channels (the designer via Architect, 2026-09-22,
            # diablocraft-wizard-resource item 4): the third named module-paid
            # exception, in Whirlwind's shape. The record is a real channel
            # that runs until the player stops it or the module stops it at an
            # empty pool; the module drains and deals the ticks. Unlike
            # Whirlwind the skill keeps its own targeting - a beam at a unit,
            # a barrage at a point - so the client still asks for one, and the
            # interrupt rules are the stock channel's the sheet names
            # (skill_targeting.csv source_spell_id: Drain Mana, Arcane
            # Missiles, Mind Flay).
            donor = spells[int(target_row['source_spell_id'])]
            values[columns.index("AttributesEx")] = 0x4  # SPELL_ATTR1_IS_CHANNELED
            values[columns.index("ChannelInterruptFlags")] = field(donor, columns.index("ChannelInterruptFlags"))
            if target_row['skill'] in CHANNEL_ENDS_ON_MOVE_SKILLS:
                values[columns.index("ChannelInterruptFlags")] = AURA_INTERRUPT_FLAG_MOVE
            values[columns.index("InterruptFlags")] = field(donor, columns.index("InterruptFlags"))
            if target_row['skill'] in CHANNEL_WHILE_MOVING_SKILLS:
                values[columns.index("ChannelInterruptFlags")] = 0
                values[columns.index("InterruptFlags")] = 0
            values[columns.index("DurationIndex")] = min(k for k,r in durations.items() if struct.unpack_from("<i",r,4)[0] == -1)
            values[columns.index("EffectAura_1")] = 0
            values[columns.index("EffectAuraPeriod_1")] = 0
        if target_row and (target_row['skill'] in GROUND_DOT_SKILLS or name in GROUND_DOT_RUNES) \
                and not passive and shell_kind in (None, "rune") and name not in GROUND_DOT_BLOCKED:
            # The ground at the cast point (GROUND_DOT_SKILLS above). The
            # period and life are written by the sheet placement below; the
            # effect keeps the shell's destination target and radius.
            values[F_ATTRIBUTES] |= 0x04000000                # SPELL_ATTR0_AURA_IS_DEBUFF
            values[F_EFFECT_1] = 27                           # PERSISTENT_AREA_AURA
            values[columns.index("EffectAura_1")] = 226       # PERIODIC_DUMMY
            values[columns.index("ImplicitTargetB_1")] = 0    # enemies (AnyAoETargetUnitInObjectRangeCheck)
        if shell_kind == "potion":
            values[F_SPELL_ICON] = potion_icon
            values[F_RANGE_INDEX] = 1
            # No cooldown line here. The record carries RecoveryTime, so the
            # client draws one itself; step 7 took that line out of every
            # sheet-driven sentence and missed this hand-written one, which
            # also spelled it "30 Sec." against the designer's 2026-09-20 wording
            # Ruling. Both go at once (step 11).
            values[columns.index("Description_Lang_enUS")] = (
                "Instantly restores 60% of maximum Life.")
        # Rend used to be corrected here by hand, because the implicit target was
        # being written to the wrong field. skill_targeting.csv already calls it
        # self_aoe at SELF range, so the rules above now cover it.
        if bleed:
            # A native periodic damage aura: the core ticks, logs
            # SPELL_PERIODIC_DAMAGE, delivers DOT damage and raises periodic
            # procs; the module's provider (core patch 0016) supplies each
            # tick's D3 snapshot number (decisions.md 2026-09-23).
            values[F_ATTRIBUTES] |= 0x04000000  # SPELL_ATTR0_AURA_IS_DEBUFF
            values[F_EFFECT_1] = 6              # SPELL_EFFECT_APPLY_AURA
            values[columns.index("EffectAura_1")] = 3    # PERIODIC_DAMAGE
            values[columns.index("EffectAuraPeriod_1")] = 1000
            values[columns.index("DurationIndex")] = five_seconds
            values[columns.index("ImplicitTargetA_1")] = TARGET_UNIT_TARGET_ENEMY
            values[columns.index("ImplicitTargetB_1")] = 0
            values[F_RECOVERY_TIME] = 0
            # and with it the shared timer: a debuff is not on the skill's
            # cooldown category, it is the thing the skill leaves behind.
            values[F_CATEGORY_RECOVERY] = 0
            values[columns.index("Category")] = 0
            values[columns.index("Description_Lang_enUS")] = "Bleeding. Damage is snapshotted when Rend is cast and dealt over 5 seconds."

        # The Barbarian's primaries are weapon swings with their own effects;
        # another class's Primary is an ordinary shell until its own mechanics
        # exist (the Wizard's Signature spells: part B).
        barbarian_primary = (skill_row and skill_row.get('category') == 'Primary'
                             and class_of_name.get(skill_row['skill_name'], 'barbarian') == 'barbarian')
        primary_spells.configure(values, columns, name,
            skill_row if barbarian_primary else None,
            primary_mechanics, targeting, ranges, stock_radii, durations, closest, primary_rows)
        if values[F_ID] == primary_spells.HAMMER:
            # The designer chooses the proc visual; never seed a replacement from memory.
            visual = float(next(r['value'] for r in read_tunables_csv('ability_tunables.csv')
                                if r['name'] == 'throwing_hammer_visual_id'))
            if visual < 0 or not visual.is_integer():
                raise ValueError('throwing_hammer_visual_id must be a nonnegative SpellVisual ID')
            if visual and int(visual) not in load_dbc('SpellVisual.dbc')[0]:
                raise ValueError('throwing_hammer_visual_id is absent from stock SpellVisual.dbc')
            values[columns.index('SpellVisualID_1')] = int(visual)
            values[columns.index('SpellVisualID_2')] = 0
        if target_row and not passive and not bleed:
            reach = target_row['range_yards']
            targeting_rows.append((spell_id, target_row['target_type'],
                                   reach if reach in ('MELEE', 'SELF') else 'NUMERIC',
                                   0 if reach in ('MELEE', 'SELF') else float(reach),
                                   float(target_row.get('radius_yards') or 0),
                                   float(target_row.get('width_yards') or 0)))
        if passive and shell_kind is None and name in passive_icon_ids:
            values[F_SPELL_ICON] = passive_icon_ids[name]
        rendered = []
        for index, value in enumerate(values):
            if value is None:
                rendered.append("0")
            elif FMT[index] == "s" or isinstance(value, str):
                rendered.append(escape(value))
            elif FMT[index] == "f":
                rendered.append(f"{value:g}")
            else:
                rendered.append(str(int(value)))
        rows_sql.append("(" + ",".join(rendered) + ")")
        records.append(list(values))
        manifest.append((spell_id, name, element, base_id,
                         shell_kind or ("bleed" if bleed else ("passive" if passive else "active"))))
        spell_id += 1

    def skill_element(skill_row):
        # barbarian_skills.csv's own column, read from each skill's tooltip:
        # Earthquake deals Fire, every other base skill names no damage type
        # and is Physical.
        element = (skill_row.get("element") or "physical").strip().lower() or "physical"
        if element not in SCHOOL:
            raise SystemExit(f"{skill_row['skill_name']}: unmapped element {element!r}")
        return element

    for skill in skills:
        name = skill["skill_name"]
        emit(name, skill, targeting_for(targeting[name]), base_spell_for(name), skill_element(skill), False)
    for rune in runes:
        parent = rune["skill_name"]
        skill = next((s for s in skills if s["skill_name"] == parent), None)
        if skill is None:
            raise SystemExit(f"rune {rune['rune_name']}: unknown skill {parent}")
        # A rune that names no element keeps its parent skill's.
        element = (rune.get("element") or "").strip().lower() or skill_element(skill)
        if element not in SCHOOL:
            raise SystemExit(f"rune {rune['rune_name']}: unmapped element {element!r}")
        modifiers = rune_modifiers(rune.get("modified_cost_cooldown_damage", ""))
        emit(f"{parent} - {rune['rune_name']}", skill, targeting_for(targeting[parent], rune),
             base_spell_for(parent), element, False, shell_kind="rune",
             cooldown_override="" if "no_cooldown" in modifiers else modifiers.get("cooldown"),
             rank="Rune: " + rune["rune_name"])
    for passive in passives:
        emit(passive["passive_name"], None, None, PASSIVE_BASE_SPELL, "physical", True)

    rend = next(row for row in skills if row["skill_name"] == "Rend")
    emit("Rend Bleed", rend, targeting["Rend"], base_spell_for("Rend"), skill_element(rend), False, True)
    for rune in (row for row in runes if row["skill_name"] == "Rend"):
        emit("Rend Bleed - " + rune["rune_name"], rend, targeting["Rend"], base_spell_for("Rend"),
             (rune["element"] or "").strip().lower() or skill_element(rend), False, True)

    # 09-rifts stage 1. Nobody learns these: the module casts them.
    for name, base, element, kind in RIFT_SHELLS + STAT_SHELLS:
        emit(name, None, None, base, element, False, shell_kind=kind)

    frenzy_buff = None
    for name, base, element in primary_spells.secondary_shells():
        emit(name, None, None, base, element, False, shell_kind='primary_internal')
        if name == "Frenzy":
            if frenzy_buff is not None:
                raise SystemExit("two internal Frenzy shells: which one is the buff is ambiguous")
            frenzy_buff = len(records) - 1

    # Spell rewrite 13, Architect's ruling of 2026-09-22 (option A). The buff on
    # the player's aura bar had no text at all, because no record of ours has
    # ever carried an AuraDescription. THIS is the record the player wears -
    # dc_barbarian_primary_data.h's FRENZY_BUFF - and not the marker the skill sentence
    # cross-references for its number; the ruling names that marker, and the
    # id in it came from my own report, which had the two the wrong way round.
    #
    # Stock shape, read off Blizzard's own stacking auras (906 of them, e.g.
    # Furious Anger 16791 at 25 stacks: "Attack speed increased by $s2%."): the
    # sentence states ONE stack's worth with a bare token, and the record's
    # StackAmount says how far it stacks. So this record needs its own $s1 -
    # it had none, base points and die sides both 0, which would have rendered
    # "increased by 0%" - and both numbers come from Frenzy's own values sheet
    # rather than being written here.
    #
    # Display only. The module counts its own stacks and computes haste from
    # frenzy_ias_pct (dc_barbarian_primaries.cpp:151); nothing reads this aura's amount,
    # and SPELL_AURA_DUMMY has no core handler to apply one.
    if frenzy_buff is None:
        raise SystemExit("no internal Frenzy shell: the buff aura has no record")
    per_stack = value_of("Frenzy", "", "attack_speed_pct")
    stacks = value_of("Frenzy", "", "max_stacks_count")
    if per_stack is None or stacks is None:
        raise SystemExit("Frenzy's values sheet has no attack_speed_pct or max_stacks_count")
    buff = records[frenzy_buff]
    buff[columns.index("EffectBasePoints_1")] = int(per_stack) - 1   # $s1 = base + die
    buff[columns.index("EffectDieSides_1")] = 1
    buff[columns.index("CumulativeAura")] = int(stacks)
    buff[columns.index("AuraDescription_Lang_enUS")] = "Attack speed increased by $s1%."

    assert spell_id == HEALTH_POTION_SPELL, "Existing shell IDs changed; do not renumber Health Potion"
    # Stock Healing Potion 439 supplies its drink/heal visual (SpellVisual 147).
    # emit clears its healing effect, restrictions, cost, reagents and GCD.
    emit("Health Potion", None, None, 439, "holy", False, shell_kind="potion",
         cooldown_override=HEALTH_POTION_COOLDOWN)

    # decisions.md 2026-09-17. Nobody learns these: the unidentified item's
    # spellid_1 casts the first, and the hub tome's click makes the module cast
    # the second on the player. Both carry no effect - identification is the
    # module's work in dc_identify.cpp, off the successful-cast hook, exactly as
    # the town portal does its teleport.
    assert spell_id == IDENTIFY_ITEM_SPELL, "Existing shell IDs changed; do not renumber Identify"
    emit("Identify", None, None, IDENTIFY_BASE_SPELL, "arcane", False, shell_kind="identify_item")
    assert spell_id == IDENTIFY_TOME_SPELL, "Existing shell IDs changed; do not renumber Identify All"
    emit("Identify All", None, None, IDENTIFY_BASE_SPELL, "arcane", False, shell_kind="identify_tome")
    assert spell_id == BOTTOMLESS_POTION_SPELL, "Existing shell IDs changed; do not renumber the Bottomless Potion"
    emit(BOTTOMLESS_POTION_NAME, None, None, 439, "holy", False, shell_kind="potion",
         cooldown_override=HEALTH_POTION_COOLDOWN)

    # 13-elite-affixes S7/S10 and docs/test-affix-round-two.md section 8. Fire
    # Chains and Health Link are paired dummy auras: dc_rift_elites.cpp adds one
    # per champion pair and removes it with the pair, and the client draws the
    # chain from the aura's caster to the unit it is on. The matching SpellVisual,
    # SpellVisualKit and SpellChainEffects rows are generate_chain_beams.py's.
    # Ids from data/d3/chain_beam_visuals.csv, in the 83000 block between the
    # shells and the wings so no earlier id moves.
    for beam in read_csv("chain_beam_visuals.csv"):
        spell_id = int(beam["spell_id"])
        emit(beam["name"], None, None, int(beam["base_spell"]), "physical", False,
             shell_kind="beam_visual")
        values = records[-1]
        values[columns.index("Effect_1")] = 6              # SPELL_EFFECT_APPLY_AURA
        values[columns.index("EffectAura_1")] = 4          # SPELL_AURA_DUMMY
        values[columns.index("ImplicitTargetA_1")] = 1     # caster; the module adds the aura
        values[columns.index("ImplicitTargetB_1")] = 0
        values[columns.index("Effect_2")] = 0
        values[columns.index("Effect_3")] = 0
        values[columns.index("DurationIndex")] = min(
            k for k, r in durations.items() if struct.unpack_from("<i", r, 4)[0] == -1)
        values[F_RECOVERY_TIME] = 0
        values[columns.index("Speed")] = 0
        values[columns.index("MaxTargets")] = 0
        values[F_ATTRIBUTES] = (SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
            | SPELL_ATTR0_DO_NOT_DISPLAY | SPELL_ATTR0_ALLOW_WHILE_MOUNTED
            | SPELL_ATTR0_NO_AURA_CANCEL)
        values[columns.index("AttributesEx3")] = (SPELL_ATTR3_ALWAYS_HIT
            | SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD)
        values[columns.index("SpellVisualID_1")] = int(beam["visual_id"])
        values[columns.index("SpellVisualID_2")] = 0
        rows_sql[-1] = "(" + ",".join(escape(v) if isinstance(v, str) else
            (f"{v:g}" if FMT[i] == "f" else str(int(v))) for i, v in enumerate(values)) + ")"
    spell_id = max(row[0] for row in manifest) + 1

    # Legendary gems, part 10b-3 (diablocraft-y75r, docs/contracts/legendary-gems.md): the eight spells a gem's
    # power casts, from data/legendary_gem_spells.csv. Like the Rift and Stat shells the records carry identity,
    # school, donor look and the shape of the effect and no number: the damage, chance and seconds are the gem's own
    # (dc_legendary_gem), so a rank changes them without a new record. The gem's name is the shell's name, so the
    # aura bar and the combat log print what the player wore.
    gem_names = {row["gem_id"]: row["gem_name"] for row in read_csv("legendary_gems.csv") if row["gem_id"]}
    gem_shells = read_gem_spells()
    pay_rows = [r for r in read_tunables_csv("combat.csv") if r["name"] == GEM_PAY_PERIOD_TUNABLE]
    if len(pay_rows) != 1 or not (pay_rows[0]["value"] or pay_rows[0]["d3_value"]):
        raise SystemExit("combat.csv: %s needs exactly one row with a value" % GEM_PAY_PERIOD_TUNABLE)
    gem_pay_period = pay_rows[0]
    seen_gem_ids = set()
    infinite_row = min(k for k, r in durations.items() if struct.unpack_from("<i", r, 4)[0] == -1)
    for gem in gem_shells:
        gem_spell = int(gem["spell_id"])
        if not GEM_ID_FIRST <= gem_spell <= GEM_ID_LAST:
            raise SystemExit("legendary_gem_spells.csv: %d is outside the gem block %d-%d" % (gem_spell, GEM_ID_FIRST, GEM_ID_LAST))
        if gem_spell in seen_gem_ids or gem["gem_id"] in {r["gem_id"] for r in gem_shells if r is not gem}:
            raise SystemExit("legendary_gem_spells.csv: %s or %d is listed twice" % (gem["gem_id"], gem_spell))
        seen_gem_ids.add(gem_spell)
        if gem["gem_id"] not in gem_names:
            raise SystemExit("legendary_gem_spells.csv: %s is not a gem of legendary_gems.csv" % gem["gem_id"])
        if gem["effect"] not in GEM_EFFECTS:
            raise SystemExit("legendary_gem_spells.csv: %s has the unknown effect %r" % (gem["gem_id"], gem["effect"]))
        period = int(gem["period_ms"]) if gem["period_ms"] else 0
        if gem["effect"] == "stagger":
            # Moratorium's payment cadence is the designer's (combat.csv); the module reads it back off this record.
            period = int(float(gem_pay_period["value"] or gem_pay_period["d3_value"] or 0))
        if gem["effect"] in ("stagger", "dot", "pulse") and period <= 0:
            raise SystemExit("legendary_gem_spells.csv: %s (%s) needs a period_ms" % (gem["gem_id"], gem["effect"]))
        spell_id = gem_spell
        emit(gem_names[gem["gem_id"]], None, None, int(gem["base_spell"]), gem["element"], False,
             shell_kind="gem_" + gem["effect"])
        values = records[-1]
        aura = {"pulse": SPELL_AURA_PERIODIC_DUMMY, "dot": SPELL_AURA_PERIODIC_DUMMY, "stun": SPELL_AURA_MOD_STUN,
                "taunt": SPELL_AURA_MOD_TAUNT, "slow": SPELL_AURA_MOD_DECREASE_SPEED,
                "absorb": SPELL_AURA_SCHOOL_ABSORB}.get(gem["effect"])
        if aura:
            # The module applies the aura with the seconds (and the slow's amount) the gem's rank gives, so the record
            # holds none: an infinite duration, no base points. A debuff on the enemy, a buff on the player (pulse).
            values[F_ATTRIBUTES] = (SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
                                    | (0 if gem["effect"] in GEM_BUFFS else 0x04000000))  # SPELL_ATTR0_AURA_IS_DEBUFF
            values[columns.index("Effect_1")] = SPELL_EFFECT_APPLY_AURA
            values[columns.index("EffectAura_1")] = aura
            values[columns.index("ImplicitTargetA_1")] = (TARGET_UNIT_CASTER if gem["effect"] in GEM_BUFFS
                                                          else TARGET_UNIT_TARGET_ENEMY)
            values[columns.index("ImplicitTargetB_1")] = 0
            # The shield takes every school (Molten Wildebeest's "an absorb shield"); every other aura has no misc value.
            values[columns.index("EffectMiscValue_1")] = SPELL_SCHOOL_MASK_ALL if gem["effect"] == "absorb" else 0
            values[columns.index("DurationIndex")] = infinite_row
            values[columns.index("ProcTypeMask")] = 0
            values[columns.index("Mechanic")] = {"stun": MECHANIC_STUN, "slow": MECHANIC_SNARE}.get(gem["effect"], 0)
            values[F_RANGE_INDEX] = 1   # stock Self Only: the module applies it, nobody casts it
        if period:
            values[columns.index("EffectAuraPeriod_1")] = period
        if gem.get("aura_text"):
            # The buff the player wears says what it is (buff icons build 1). Only a shell that is a buff has one.
            if gem["effect"] not in GEM_BUFFS:
                raise SystemExit("legendary_gem_spells.csv: %s (%s) is not a buff, so it has no aura_text" % (gem["gem_id"], gem["effect"]))
            values[columns.index("AuraDescription_Lang_enUS")] = gem["aura_text"]
        rows_sql[-1] = "(" + ",".join(escape(v) if isinstance(v, str) else
            (f"{v:g}" if FMT[i] == "f" else str(int(v))) for i, v in enumerate(values)) + ")"

    # Legendary gem buffs (buff icons build 1, diablocraft-xumo; docs/contracts/buff-values-messages.md): the aura the
    # player wears for a gem's effect, from data/legendary_gem_buffs.csv. Frenzy's stock shape: one stack's number is
    # the record's $s1 (base points + die sides) and CumulativeAura says how far it stacks, so the client shows the
    # total for the stacks. The amounts are the gem's own numbers (named columns of legendary_gems.csv); what the
    # record cannot state (a rank's number, a live amount) is the addon line. Display only: SPELL_AURA_DUMMY has no
    # handler, the module counts the stacks and does the maths. The module applies the aura with its own seconds, so
    # the record's duration is the stock infinite one.
    gem_rows = {row["gem_id"]: row for row in read_csv("legendary_gems.csv") if row["gem_id"]}
    seen_buff_ids, seen_buff_keys = set(), set()
    for buff in read_gem_buffs():
        gem_spell = int(buff["spell_id"])
        if not GEM_ID_FIRST <= gem_spell <= GEM_ID_LAST or gem_spell in seen_gem_ids or gem_spell in seen_buff_ids:
            raise SystemExit("legendary_gem_buffs.csv: %d is outside the gem block %d-%d or listed twice" % (gem_spell, GEM_ID_FIRST, GEM_ID_LAST))
        seen_buff_ids.add(gem_spell)
        key = (buff["gem_id"], buff["rank25"])
        if buff["gem_id"] not in gem_rows or buff["rank25"] not in ("0", "1") or key in seen_buff_keys:
            raise SystemExit("legendary_gem_buffs.csv: %s rank25=%s is not a gem of legendary_gems.csv or is listed twice" % key)
        seen_buff_keys.add(key)
        gem_row = gem_rows[buff["gem_id"]]
        amounts = [gem_buff_number(gem_row, buff[column], column) if buff[column] else None for column in ("amount_1", "amount_2")]
        stacks = gem_buff_number(gem_row, buff["max_stacks"], "max_stacks") if buff["max_stacks"] else 0
        wanted_tokens = {"$s%d" % (n + 1) for n, amount in enumerate(amounts) if amount is not None}
        if set(re.findall(r"\$s\d", buff["text"])) != wanted_tokens or re.search(r"per stack", buff["text"], re.I):
            raise SystemExit("legendary_gem_buffs.csv: %d's text must state exactly its amounts (%s) as totals, never 'per stack'"
                             % (gem_spell, sorted(wanted_tokens)))
        spell_id = gem_spell
        emit(gem_names[buff["gem_id"]], None, None, int(buff["base_spell"]), "physical", False, shell_kind="gem_buff")
        values = records[-1]
        values[F_ATTRIBUTES] = SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
        values[columns.index("ProcTypeMask")] = 0
        values[columns.index("Mechanic")] = 0
        values[columns.index("DurationIndex")] = infinite_row
        values[F_RANGE_INDEX] = 1   # stock Self Only: the module applies it, nobody casts it
        # Nothing of the donor's effects stays (a periodic heal's period, its trigger, its radius): only the icon does.
        for slot in (1, 2, 3):
            for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_", "ImplicitTargetA_",
                           "ImplicitTargetB_", "EffectRadiusIndex_", "EffectAuraPeriod_", "EffectBasePoints_",
                           "EffectDieSides_", "EffectTriggerSpell_", "EffectChainTargets_", "EffectSpellClassMaskA_"):
                values[columns.index(prefix + str(slot))] = 0
        for slot in (1, 2):
            amount = amounts[slot - 1]
            if slot == 2 and amount is None:
                continue
            values[columns.index("Effect_%d" % slot)] = SPELL_EFFECT_APPLY_AURA
            values[columns.index("EffectAura_%d" % slot)] = SPELL_AURA_DUMMY
            values[columns.index("ImplicitTargetA_%d" % slot)] = TARGET_UNIT_CASTER
            values[columns.index("ImplicitTargetB_%d" % slot)] = 0
            if amount is not None:
                values[columns.index("EffectBasePoints_%d" % slot)] = amount - 1   # $sN = base + die
                values[columns.index("EffectDieSides_%d" % slot)] = 1
        if stacks > 1:
            values[columns.index("CumulativeAura")] = stacks
        values[columns.index("AuraDescription_Lang_enUS")] = buff["text"]
        rows_sql[-1] = "(" + ",".join(escape(v) if isinstance(v, str) else
            (f"{v:g}" if FMT[i] == "f" else str(int(v))) for i, v in enumerate(values)) + ")"
    spell_id = max(row[0] for row in manifest) + 1

    # Module-owned buff markers. Their duration is set from sourced metadata at
    # application; the dummy aura is real and visible, with no native damage math.
    # Control immunity by aura (diablocraft-aura-fixes, aura review row 5 / R1, ruling q-1003-11): Ignore Pain and
    # Nerves of Steel carry it on their records instead of the module filling the core's immunity list. In this core
    # (SpellInfo::_LoadImmunityInfo) aura 147's MiscValue is a lookup id, not a mask: 96 with a nonzero amount is
    # the stock "immune to every control" set (mechanics snare, root, fear, stun, sleep, charm, sapped, horror,
    # polymorph, disoriented, freeze, turn, and the aura types stun, root, fear, confuse, decrease-speed), which
    # Unit::AddAura refuses by aura type. Silence is not in it, so a second effect (aura 77, mechanic 9) carries it.
    # Knockout and daze cannot be carried beside the marker's own DUMMY effect, and no record in the module applies
    # either to a player. SPELL_ATTR1_IMMUNITY_PURGES_EFFECT makes the cast strip the holds already on the player,
    # which the module did by hand with RemoveAurasWithMechanic.
    SPELL_AURA_MECHANIC_IMMUNITY = 77
    SPELL_AURA_MECHANIC_IMMUNITY_MASK = 147
    IMMUNITY_ALL_CONTROLS = 96
    MECHANIC_SILENCE = 9
    SPELL_ATTR1_IMMUNITY_PURGES_EFFECT = 0x8000

    def carry_control_immunity(values):
        for slot, aura, misc in ((2, SPELL_AURA_MECHANIC_IMMUNITY_MASK, IMMUNITY_ALL_CONTROLS),
                                 (3, SPELL_AURA_MECHANIC_IMMUNITY, MECHANIC_SILENCE)):
            values[columns.index("Effect_%d" % slot)] = 6
            values[columns.index("EffectAura_%d" % slot)] = aura
            values[columns.index("EffectMiscValue_%d" % slot)] = misc
            # The amount is base + die (the $s1 convention above): 0 + 1 = 1, the nonzero amount the 147 lookup needs.
            values[columns.index("EffectBasePoints_%d" % slot)] = 0
            values[columns.index("EffectDieSides_%d" % slot)] = 1
            values[columns.index("ImplicitTargetA_%d" % slot)] = 1
            values[columns.index("ImplicitTargetB_%d" % slot)] = 0
        values[columns.index("AttributesEx")] |= SPELL_ATTR1_IMMUNITY_PURGES_EFFECT

    active_metadata = list(targeting_rows)
    ability_rows = skills + runes
    spell_id = 81310
    for active_id, *_ in active_metadata:
        original = next(r for r in manifest if r[0] == active_id)
        emit(original[1], None, None, original[3], original[2], False, shell_kind="ability_aura")
        values = records[-1]
        values[columns.index("Effect_1")] = 6
        values[columns.index("EffectAura_1")] = 4  # DUMMY, consumed by module
        values[columns.index("ImplicitTargetA_1")] = 1
        values[columns.index("ImplicitTargetB_1")] = 0
        values[columns.index("DurationIndex")] = min(k for k, r in durations.items()
            if struct.unpack_from("<i", r, 4)[0] == -1)
        values[F_RECOVERY_TIME] = 0
        values[columns.index("Speed")] = 0
        source_row = ability_rows[active_id - FIRST_SPELL_ID]
        skill_name, rune_name = source_row["skill_name"], source_row.get("rune_name", "")
        if skill_name == "Ignore Pain":
            carry_control_immunity(values)
        if (skill_name == "Threatening Shout" and rune_name == "Intimidate") or (skill_name == "Avalanche" and rune_name == "Snow-Capped Mountain"):
            slow = value_of(skill_name, rune_name, "slow_pct")
            if slow is None:
                raise SystemExit(f"{skill_name} - {rune_name}: no slow_pct in the values sheet")
            values[columns.index("Effect_2")] = 6
            values[columns.index("EffectAura_2")] = 33
            values[columns.index("ImplicitTargetA_2")] = 6
            values[columns.index("ImplicitTargetB_2")] = 0
            values[columns.index("EffectBasePoints_2")] = -int(slow)-1
        # Re-render after helper configuration, exactly as the main rows.
        rows_sql[-1] = "(" + ",".join(escape(v) if isinstance(v,str) else
            (f"{v:g}" if FMT[i]=="f" else str(int(v))) for i,v in enumerate(values)) + ")"

    # Separate native control executors have their own sourced durations. This
    # keeps fear/taunt expiry independent of Threatening Shout's damage debuff.
    for active_id, *_ in active_metadata:
        source_row = ability_rows[active_id - FIRST_SPELL_ID]
        skill_name, rune_name = source_row["skill_name"], source_row.get("rune_name", "")
        aura_type = (11 if skill_name == "Threatening Shout" and rune_name == "Demoralize" else
                     7 if skill_name == "Threatening Shout" and rune_name == "Terrify" else
                     12 if skill_name == "Furious Charge" and rune_name == "Cold Rush" else
                     12 if skill_name == "Avalanche" and rune_name == "Glacier" else 0)
        if skill_name == "Earthquake" and rune_name == "Chilling Earth": aura_type = 12
        if skill_name == "Ground Stomp": aura_type = 12
        if skill_name == "Call of the Ancients" and rune_name == "Duty to the Clan": aura_type = 33
        if skill_name in ("Leap",) or (skill_name == "Ancient Spear" and rune_name in ("Harpoon","Rage Flip")) or (skill_name == "Seismic Slam" and rune_name == "Permafrost"): aura_type = 33
        if skill_name == "Hammer of the Ancients" and rune_name == "Thunderstrike": aura_type = 12
        if skill_name == "Hammer of the Ancients" and rune_name == "The Devil's Anvil": aura_type = 33
        if not aura_type: continue
        original = next(r for r in manifest if r[0] == active_id)
        spell_id = 81710 + active_id - FIRST_SPELL_ID
        emit(original[1], None, None, original[3], original[2], False, shell_kind="ability_control")
        values = records[-1]
        values[columns.index("Effect_1")] = 6
        values[columns.index("EffectAura_1")] = aura_type
        values[columns.index("ImplicitTargetA_1")] = 6
        values[columns.index("ImplicitTargetB_1")] = 0
        values[columns.index("Mechanic")] = 5 if aura_type == 7 else (13 if aura_type == 12 else (11 if aura_type == 33 else 0))
        if skill_name == "Ground Stomp" or (skill_name == "Hammer of the Ancients" and rune_name == "Thunderstrike"):
            values[columns.index("Mechanic")] = 12  # STUN
        if aura_type == 33:
            # Leap states its slow on the base skill, every other row on the rune.
            owner = (skill_name, "") if skill_name == "Leap" else (skill_name, rune_name)
            percent = value_of(*owner, "slow_pct")
            if percent is None:
                percent = value_of(*owner, "chill_pct")
            if percent is None and skill_name != "Call of the Ancients":
                raise SystemExit(skill_name + " / " + rune_name + ": missing sourced slow")
            values[columns.index("EffectBasePoints_1")] = -int(percent)-1 if percent is not None else -1
            if skill_name == "Call of the Ancients":
                values[columns.index("Effect_2")] = 6
                values[columns.index("EffectAura_2")] = 197
                values[columns.index("ImplicitTargetA_2")] = 6
                values[columns.index("ImplicitTargetB_2")] = 0
                chance = value_of(skill_name, rune_name, "proc_chance_pct")
                if chance is None:
                    raise SystemExit(f"{skill_name} - {rune_name}: no proc_chance_pct")
                values[columns.index("EffectBasePoints_2")] = int(chance)-1
        if skill_name == "Leap" and rune_name == "Death from Above":
            values[columns.index("Effect_2")] = 6
            values[columns.index("EffectAura_2")] = 12
            values[columns.index("ImplicitTargetA_2")] = 6
            values[columns.index("ImplicitTargetB_2")] = 0
            values[columns.index("Mechanic")] = 12

        values[columns.index("DurationIndex")] = min(k for k, r in durations.items() if struct.unpack_from("<i", r, 4)[0] == -1)
        values[F_RECOVERY_TIME] = 0
        values[columns.index("Speed")] = 0
        rows_sql[-1] = "(" + ",".join(escape(v) if isinstance(v,str) else
            (f"{v:g}" if FMT[i]=="f" else str(int(v))) for i,v in enumerate(values)) + ")"
    # Bottomless potions P2 (diablocraft-87qlt): every other potion's own shell, the way Regeneration's 81205 is one (same heal,
    # same 30 s), and each built power's record, the ids from potion_icons.csv. A timed power is a module buff marker (a
    # DUMMY aura on the drinker, its seconds and amount set by the module at the drink, the power text as its tooltip with $s1
    # for the roll); Fear's is a fear aura on each enemy in reach; Unfettered's carries Ignore Pain's control immunity.
    import generate_potion_icons
    for potion in generate_potion_icons.rows():
        if potion["spell"] != BOTTOMLESS_POTION_SPELL:
            spell_id = potion["spell"]
            emit(potion["name"], None, None, 439, "holy", False, shell_kind="potion",
                 cooldown_override=HEALTH_POTION_COOLDOWN)
        if not potion["power_spell"]:
            continue
        spell_id = potion["power_spell"]
        emit(potion["name"], None, None, 439, "holy", False, shell_kind="potion_power")
        values = records[-1]
        values[F_SPELL_ICON] = potion_icon
        values[F_RANGE_INDEX] = 1
        values[columns.index("Effect_1")] = 6
        values[columns.index("EffectAura_1")] = 4           # DUMMY: the module does the power
        values[columns.index("ImplicitTargetA_1")] = 1
        values[columns.index("ImplicitTargetB_1")] = 0
        values[columns.index("Effect_2")] = 0
        values[columns.index("Effect_3")] = 0
        values[columns.index("DurationIndex")] = min(k for k, r in durations.items() if struct.unpack_from("<i", r, 4)[0] == -1)
        values[F_RECOVERY_TIME] = 0
        values[columns.index("Speed")] = 0
        values[columns.index("Description_Lang_enUS")] = ""
        values[columns.index("AuraDescription_Lang_enUS")] = potion["power_text"].replace("%d", "$s1").replace("%%", "%")
        if potion["power_id"] == "leg_potion_fear":
            values[columns.index("EffectAura_1")] = 7       # MOD_FEAR
            values[columns.index("ImplicitTargetA_1")] = TARGET_UNIT_TARGET_ENEMY
            values[columns.index("Mechanic")] = 5            # MECHANIC_FEAR
            values[F_ATTRIBUTES] |= 0x04000000               # SPELL_ATTR0_AURA_IS_DEBUFF
            values[columns.index("AuraDescription_Lang_enUS")] = ""
        if potion["power_id"] == "leg_potion_unfettered":
            carry_control_immunity(values)
        rows_sql[-1] = "(" + ",".join(escape(v) if isinstance(v, str) else
            (f"{v:g}" if FMT[i] == "f" else str(int(v))) for i, v in enumerate(values)) + ")"
    for helper_id, name, aura_type, parent in [(82300,"Inspiring Presence",4,"Inspiring Presence"),(82301,"Nerves of Steel",4,"Nerves of Steel"),(82302,"Unforgiving",94,"Unforgiving"),(82303,"Rampage",4,"Rampage"),(82304,"Pound of Flesh",4,"Pound of Flesh")]:
        spell_id=helper_id
        emit(name,None,None,PASSIVE_BASE_SPELL,"physical",False,shell_kind="passive_effect")
        values=records[-1]
        values[columns.index("Effect_1")]=6
        values[columns.index("EffectAura_1")]=aura_type
        values[columns.index("ImplicitTargetA_1")]=1
        values[columns.index("ImplicitTargetB_1")]=0
        values[columns.index("DurationIndex")]=min(k for k,r in durations.items() if struct.unpack_from("<i",r,4)[0]==-1)
        values[F_RECOVERY_TIME]=0
        if name == "Nerves of Steel":
            carry_control_immunity(values)
        if name in ("Rampage","Pound of Flesh"):
            stacks = value_of(name, "", "max_stacks_count", passive=True)
            if stacks is None:
                raise SystemExit(name + ": no max_stacks_count in the values sheet")
            values[columns.index("CumulativeAura")]=int(stacks)
        rows_sql[-1]="("+",".join(escape(v) if isinstance(v,str) else (f"{v:g}" if FMT[i]=="f" else str(int(v))) for i,v in enumerate(values))+")"
    storm = next(r for r in runes if r["rune_name"] == "Storm of Steel")
    storm_active = FIRST_SPELL_ID + len(skills) + runes.index(storm)
    spell_id = 81910 + storm_active - FIRST_SPELL_ID
    emit("Overpower - Storm of Steel", None, None, base_spell_for("Weapon Throw"), "physical", False, shell_kind="ability_proc")
    values = records[-1]
    values[columns.index("ImplicitTargetA_1")] = 6
    values[columns.index("ImplicitTargetB_1")] = 0
    values[F_RECOVERY_TIME] = 0
    rows_sql[-1] = "(" + ",".join(escape(v) if isinstance(v,str) else
        (f"{v:g}" if FMT[i]=="f" else str(int(v))) for i,v in enumerate(values)) + ")"
    spell_id = max(row[0] for row in manifest) + 1

    # --- spell rewrite step 1: the numbers go into the record --------------
    #
    # docs/research/wow-spell-mapping.md, sections 1-3. Every named number of
    # the 157 barbarian rows is written into the field that holds it and the
    # sentence references it with WoW's own token, so the client renders what
    # the server reads. Three rules keep this from changing behaviour:
    #
    #   * effect KINDS are never touched. A number goes into a slot only when
    #     that slot's base points are unused (Effect_n is 0 or a dummy and both
    #     EffectBasePoints_n and EffectDieSides_n are zero), so a Primary's real
    #     effects, a bleed's periodic dummy and the control shells keep theirs.
    #   * a live record-level field is written only when it is still zero, so
    #     nothing the generator already sourced (a cooldown, a radius index, a
    #     cloned proc chance) is overwritten.
    #   * a value the field cannot hold exactly - a fraction, a radius with no
    #     stock SpellRadius row, a duration with no SpellDuration row - is not
    #     rounded into it. It goes to the exact-value table, which both the
    #     client ($<name>) and the server read.
    #
    # Cost and cooldown stay out of the record on purpose: the module pays and
    # installs both today (report section 4), and steps 5 and 6 move them once
    # docs/research/d3-cost-cooldown-math.md is accepted.
    def render(values):
        return "(" + ",".join(
            escape(value) if isinstance(value, str) else
            (f"{value:g}" if FMT[index] == "f" else str(int(value)))
            for index, value in enumerate(values)) + ")"

    index_of = {}
    for position, row in enumerate(manifest):
        index_of[(row[4], row[1])] = position

    def slot_free(values, slot):
        if values[columns.index(f"EffectBasePoints_{slot}")] or values[columns.index(f"EffectDieSides_{slot}")]:
            return False
        effect = values[columns.index(f"Effect_{slot}")]
        aura = values[columns.index(f"EffectAura_{slot}")]
        return effect in (0, SPELL_EFFECT_DUMMY) or (effect == 6 and aura == 4)

    def put_base(values, slot, number):
        values[columns.index(f"EffectBasePoints_{slot}")] = int(number) - 1
        values[columns.index(f"EffectDieSides_{slot}")] = 1

    def duration_row(seconds):
        wanted = int(round(seconds * 1000))
        rows = [key for key, raw in durations.items()
                if struct.unpack_from("<i", raw, 4)[0] == wanted
                and struct.unpack_from("<i", raw, 12)[0] == wanted]
        return min(rows) if rows else None

    def radius_row(yards, name=None):
        """A SpellRadius row for exactly this many yards, or None: a stock row, or a module row the named record is listed for."""
        rows = [key for key, value in radii.items() if abs(value - yards) < 0.0005
                and (key in stock_radii or name in radius_users[key])]
        return min(rows) if rows else None

    # The persisted, append-only identity -> id map (report section 2): sorted
    # order is stable only while the input is, so an id is assigned once and
    # never reassigned.
    helper_path = GENERATED / "spell_helper_ids.csv"
    owner_of_id = {row[0]: row[1] for row in manifest}
    helper_rows = [(row["identity"], int(row["spell_id"]), row.get("class") or "barbarian")
                   for row in read_csv_generated("spell_helper_ids.csv")] \
        if helper_path.is_file() else []
    helper_ids = validate_helper_map(helper_rows, owner_of_id)

    def helper_for(identity, element, kind="token_storage"):
        """A record from the reserved block, created once and kept at its id.

        Two kinds live there: the token-storage shells that hold a number no
        slot on the real record was free for, and step 5's cost-modifier
        auras. Both are hidden passive records nobody learns.
        """
        nonlocal spell_id
        wanted = choose_helper_id(identity, helper_ids, owner_of_id, current["stem"], reserved_ids)
        if identity not in helper_ids:
            helper_ids[identity] = wanted
            helper_rows.append((identity, wanted, current["stem"]))
        if (kind, identity) in index_of:
            return index_of[(kind, identity)]
        spell_id = wanted
        emit(identity, None, None, PASSIVE_BASE_SPELL, element, True, shell_kind=kind)
        index_of[(kind, identity)] = len(records) - 1
        return len(records) - 1

    def regeneration_mask(d3_class):
        """REGENERATION_MASK: the class's record keeping the core's tick off each of its resources the module pays
        (class_resources.csv paid_by module), one effect per resource; none for a class with no such resource."""
        pulsed = [entry for entry in RESOURCES if entry["d3_class"] == d3_class and entry["paid_by"] == "module"]
        if not pulsed:
            return
        record = records[helper_for(REGENERATION_MASK % d3_class, "physical", "regeneration_mask")]
        for slot in (1, 2, 3):
            entry = pulsed[slot - 1] if slot <= len(pulsed) else None
            for prefix, value in (("Effect_", SPELL_EFFECT_APPLY_AURA), ("EffectAura_", SPELL_AURA_PREVENT_REGENERATE_POWER),
                                  ("EffectMiscValue_", entry and entry["power_id"] + 1),
                                  ("ImplicitTargetA_", TARGET_UNIT_CASTER), ("EffectMiscValueB_", 0),
                                  ("EffectBasePoints_", 0), ("EffectDieSides_", 0), ("ImplicitTargetB_", 0),
                                  ("EffectRadiusIndex_", 0), ("EffectSpellClassMaskA_", 0)):
                record[columns.index(prefix + str(slot))] = value if entry else 0
        # The player's own and never expires: the module keeps it on.
        record[columns.index("DurationIndex")] = min(
            key for key, raw in durations.items() if struct.unpack_from("<i", raw, 4)[0] == -1)

    def energy_rate_record(d3_class):
        """ENERGY_RATE: the class's record slowing or speeding Energy to its primary's rate; none at the native rate."""
        energy_rate = primary_energy_rate(d3_class)
        if energy_rate is None:
            return
        position = helper_for(ENERGY_RATE % d3_class, "physical", "energy_rate")
        record = records[position]
        for prefix, values in energy_rate_effects(power_of(d3_class)[0], energy_rate).items():
            for slot, value in enumerate(values, 1):
                record[columns.index(prefix + str(slot))] = value
        # The player's own and never expires: the module keeps it on.
        record[columns.index("DurationIndex")] = min(
            key for key, raw in durations.items() if struct.unpack_from("<i", raw, 4)[0] == -1)

    def class_buff_number(stem, reference, who):
        """A class buff sheet number: 'owner/token[/qualifier]', the owner 'passive:Name', 'Skill' or 'Skill - Rune'.

        The buff's amounts are the class sheets' own numbers, so none is written twice. A record's `$s` holds a whole
        number only, so a fraction stops the build.
        """
        if reference.startswith("tunable:"):
            # A number that is the designer's rather than the class sheet's (a class mechanic with no tooltip of its own, the
            # Shaman's Overcharge and Attunement): 'tunable:<category>/<name>' reads data/tunables/<category>.csv, the one
            # place the module reads it from, so the record's text and the server cannot drift.
            category, _, name = reference[len("tunable:"):].partition("/")
            with (TUNABLES / (category + ".csv")).open(encoding="utf-8-sig", newline="") as stream:
                found = [row for row in csv.DictReader(stream) if row["name"] == name]
            if len(found) != 1:
                raise SystemExit("class_buffs.csv: %s: %r is not a row of data/tunables/%s.csv" % (who, reference, category))
            number = float(found[0]["value"] or found[0]["d3_value"])
            if not number.is_integer():
                raise SystemExit("class_buffs.csv: %s: %r is not a whole number" % (who, reference))
            return int(number)
        owner, _, rest = reference.partition("/")
        token, _, qualifier = rest.partition("/")
        passive = owner.startswith("passive:")
        skill, rune = (owner[len("passive:"):], "") if passive else owner.partition(" - ")[::2]
        number = value_of(skill, rune, token, qualifier, passive=passive, stem=stem)
        if number is None or not float(number).is_integer():
            raise SystemExit("class_buffs.csv: %s: %r is not a whole number of the %s sheet" % (who, reference, stem))
        return int(number)

    def class_buffs(stem):
        """Buff icons build 2 (diablocraft-b3zj): this class's rows of data/class_buffs.csv.

        A `new` row is one helper record the module puts on the player, Frenzy's stock shape: one stack's number is
        the record's $s (base points + die sides) and CumulativeAura says how far it stacks, so the client shows the
        total for the stacks. An `existing` row gives a record that already is a buff its amounts and its text. Display
        only: SPELL_AURA_DUMMY has no handler, the module counts the stacks and does the maths, and the module sets
        the seconds, so the record's own duration is the stock infinite one. What a record cannot state (a live amount)
        is the addon line (docs/contracts/buff-values-messages.md).
        """
        assert current["stem"] == stem
        c = columns.index
        for row in read_class_buffs():
            if row["class"] != stem:
                continue
            who = row["identity"]
            amounts = [class_buff_number(stem, row[key], who) if row[key] else None
                       for key in ("amount_1", "amount_2", "amount_3")]
            wanted_tokens = {"$s%d" % (n + 1) for n, amount in enumerate(amounts) if amount is not None}
            if set(re.findall(r"\$s\d", row["text"])) != wanted_tokens or re.search(r"per stack", row["text"], re.I):
                raise SystemExit("class_buffs.csv: %s's text must state exactly its amounts (%s) as totals, never "
                                 "'per stack'" % (who, sorted(wanted_tokens)))
            stacks = 0
            if row["max_stacks"]:
                stacks = int(row["max_stacks"]) if row["max_stacks"].isdigit() else \
                    class_buff_number(stem, row["max_stacks"], who)
            if row["mode"] == "new":
                # The icon is a stock spell's (a donor, as the gem buffs): the classes' own records share a few icons.
                kind, _, donor_id = row["icon"].partition(":")
                donor = spells.get(int(donor_id)) if kind == "spell" and donor_id.isdigit() else None
                if donor is None:
                    raise SystemExit("class_buffs.csv: %s: icon %r is not spell:<id> of a record in Spell.dbc" % (who, row["icon"]))
                position = helper_for(who, "physical", "class_buff")
                values = records[position]
                values[F_ATTRIBUTES] = SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
                values[c("AttributesEx3")] = SPELL_ATTR3_ALWAYS_HIT
                values[c("ProcTypeMask")] = 0
                values[F_RANGE_INDEX] = 1   # stock Self Only: the module applies it, nobody casts it
                values[c("DurationIndex")] = infinite_row
                values[c("SpellIconID")] = field(donor, c("SpellIconID"))
                for slot in (1, 2, 3):
                    for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_", "ImplicitTargetA_",
                                   "ImplicitTargetB_", "EffectRadiusIndex_", "EffectAuraPeriod_", "EffectBasePoints_",
                                   "EffectDieSides_", "EffectSpellClassMaskA_"):
                        values[c(prefix + str(slot))] = 0
                # A buff with no number still wears one aura effect.
                values[c("Effect_1")] = SPELL_EFFECT_APPLY_AURA
                values[c("EffectAura_1")] = SPELL_AURA_DUMMY
                values[c("ImplicitTargetA_1")] = TARGET_UNIT_CASTER
                if row["kind"] == "absorb":
                    # A shield the core drains itself: an absorb of every school, its amount set by the module when it puts it on.
                    values[c("EffectAura_1")] = SPELL_AURA_SCHOOL_ABSORB
                    values[c("EffectMiscValue_1")] = SPELL_SCHOOL_MASK_ALL
                elif row["kind"]:
                    raise SystemExit("class_buffs.csv: %s: kind %r is not blank or absorb for a new row" % (who, row["kind"]))
            elif row["mode"] == "existing":
                position = index_of[(row["kind"], who)]
                values = records[position]
            else:
                raise SystemExit("class_buffs.csv: %s: mode %r is neither new nor existing" % (who, row["mode"]))
            for slot, amount in enumerate(amounts, 1):
                if amount is None:
                    continue
                values[c("Effect_%d" % slot)] = SPELL_EFFECT_APPLY_AURA
                values[c("EffectAura_%d" % slot)] = SPELL_AURA_DUMMY
                values[c("ImplicitTargetA_%d" % slot)] = TARGET_UNIT_CASTER
                values[c("ImplicitTargetB_%d" % slot)] = 0
                values[c("EffectBasePoints_%d" % slot)] = amount - 1   # $sN = base + die
                values[c("EffectDieSides_%d" % slot)] = 1
            if stacks > 1:
                values[c("CumulativeAura")] = stacks
            values[c("AuraDescription_Lang_enUS")] = row["text"]

    variables = {}        # spell id -> [(name, value string)]
    exact_rows = []       # the values no field holds exactly: the server table
    value_map = []        # where every value lives, for step 2 and its tests
    overrides = []        # donor fields the sheet took over, for the report
    descriptions = []     # (record index, text)
    # Which SIDE_EFFECT_DURATIONS entries actually matched a row. A rename in a
    # sheet would otherwise drop the exception in silence and quietly put a
    # taunt back on a field a modifier doubles.
    side_effects_used = set()

    def write_row(kind, name, skill, rune, text, category, passive, inherited=()):
        """One sheet row: numbers into fields, sentence into WoW tokens.

        `inherited` carries the base skill's value rows that this rune does
        not restate (Architect, 2026-09-20): a rune is the skill plus its
        change, so it copies the skill's sheet-owned fields first and then
        overrides only what its own rows state. Inherited numbers go into the
        record but never into the sentence - the rune's text is the rune's.
        """
        position = index_of.get((kind, name))
        if position is None:
            return
        values = records[position]
        identifier = manifest[position][0]
        companion = index_of.get(("passive_effect" if passive else "ability_aura", name))
        marks, used_slots = {}, {position: 1}

        def next_slot(target):
            start = used_slots.get(target, 1)
            for slot in range(start, 4):
                if slot_free(records[target], slot):
                    used_slots[target] = slot + 1
                    return slot
            used_slots[target] = 4
            return None

        def donor(field, old, new_value, row):
            """A field the sheet took over from the donor spell, for the log."""
            if old != new_value:
                overrides.append((identifier, name, field, old, new_value,
                                  row["token"], row["qualifier"], row["value"]))

        def applies_an_aura(target):
            return any(records[target][columns.index("Effect_%d" % slot)] in AURA_EFFECTS
                       for slot in (1, 2, 3))

        # The SENTENCE decides the order the numbers are placed in, not the
        # values sheet: the sheet is a table an editor may sort, and a record
        # whose slots move when a row moves is a record nobody can review.
        body, _, _ = text.partition("Unlocked")
        rows_by_key = {}
        for row in values_for(skill, rune, passive, current["stem"]):
            key = (row["token"], row["qualifier"])
            if key in rows_by_key:
                raise SystemExit("%s: two values sheet rows share the key %s" % (name, key))
            rows_by_key[key] = row
        wanted = placeholder_keys(body)
        for key in wanted:
            if key not in rows_by_key:
                raise SystemExit("%s: the sentence asks for %s and the values sheet has no such row"
                                 % (name, key))

        # Step 7: which label lines the client will print for itself. The
        # answer is the record's, not the sentence's - the cost is only the
        # core's for a skill the module has stopped paying, and the cooldown
        # only where emit() wrote one.
        def carries(kind):
            if kind == "cost":
                return skill not in MODULE_PAID_SKILLS + CHANNEL_DRAIN_SKILLS
            return bool(values[F_RECOVERY_TIME] or values[F_CATEGORY_RECOVERY])

        printed_by_client = client_printed_segments(body, carries)
        # A number whose only appearance was one of those lines needs no
        # client variable either: nothing is left to print it.
        elsewhere = {key for index, piece in enumerate(body.split("|"))
                     if index not in printed_by_client
                     for key in placeholder_keys(piece)}
        silent = {key for key in wanted
                  if key[0] in set(printed_by_client.values()) and key not in elsewhere}
        module_read = [key for key in rows_by_key
                       if key not in wanted and (key[0] in MODULE_READ_TOKENS
                                                 or (skill, rune, key[0]) in MODULE_READ_ROWS)]
        unused = [key for key in rows_by_key if key not in wanted and key not in module_read]
        if unused:
            raise SystemExit("%s: values with no placeholder: %s" % (name, sorted(unused)))

        claimed = set()

        def kind_for(token, own):
            """Where this row's number lives, for THIS record.

            The only thing that is not a property of the token name is the
            side-effect duration ruling: a record's own row named there is an
            exact value rather than a DurationIndex, so a modifier that moves
            the record's duration cannot move it.
            """
            if own and (skill, rune, token) in SIDE_EFFECT_DURATIONS:
                side_effects_used.add((skill, rune, token))
                return "exact"
            if own and (skill, rune, token) in CONDITIONAL_COOLDOWNS:
                side_effects_used.add((skill, rune, token))
                return "exact"
            # A Wizard channel's DurationIndex is the channel's own, infinite
            # until the player or an empty pool stops it (item 4 ruling,
            # 2026-09-22), so no side effect's seconds - Ray of Frost's slow,
            # a rune's debuff - may take it, own or inherited.
            if skill in CHANNEL_DRAIN_SKILLS and TOKEN_KIND.get(token) == "duration":
                return "exact"
            # A Wizard ground's DurationIndex is its dot_duration_seconds - the
            # life the stock aura ticks over - so a rune's freeze or chill
            # (Comet, Frozen Solid) may not take it.
            if (skill in GROUND_DOT_SKILLS or name in GROUND_DOT_RUNES or skill == METEOR_GROUND_SKILL) \
                    and TOKEN_KIND.get(token) == "duration" and token != "dot_duration_seconds":
                return "exact"
            if skill in WIZARD_BUFF_SKILLS and TOKEN_KIND.get(token) == "duration" \
                    and token != "duration_minutes":
                return "exact"
            return TOKEN_KIND.get(token, "exact")

        def is_reach(row):
            """A radius row that is a REACH, not an area: it has no radius slot.

            The client draws a ground-target circle as the radius of the effect
            that takes the point, so "up to 50 yards away" must not be an
            effect radius at all: Teleport's 50 yards was the circle the designer saw
            (patch 43). The number is a client variable and an exact server
            value, like any number with no field. A rune's own radius is an
            area and keeps its slot.
            """
            return row["skill"] in REACH_RADIUS_SKILLS + MARKER_CURSOR_SKILLS and not row["rune"]

        def largest_rune_radius(row):
            """The largest radius_yards number the rune's own rows state."""
            return max(float(other["value"]) for other in values_for(row["skill"], row["rune"], passive, current["stem"])
                       if other["token"] == "radius_yards")

        def place(row, wants_mark, own=True):
            """One value into the field that holds it; the mark it renders as."""
            token, qualifier = row["token"], row["qualifier"]
            number = float(row["value"])
            kind_of = kind_for(token, own)
            mark, source, holder, slot_used, conversion = None, "exact", identifier, 0, ""
            # A field holds the number, and the sentence still prints a copy of
            # it because WoW has no description token for that field (cost).
            printed_only = False
            if kind_of == "base" and number.is_integer():
                target, slot = position, next_slot(position)
                if slot is None and companion is not None:
                    target, slot = companion, next_slot(companion)
                if slot is None:
                    target = helper_for("%s - token storage" % name, manifest[position][2])
                    slot = next_slot(target)
                if slot is not None:
                    put_base(records[target], slot, number)
                    mark = "$s%d" % slot if target == position else "$%ds%d" % (
                        manifest[target][0], slot)
                    source, holder, slot_used = "base_points", manifest[target][0], slot
                    conversion = "plus_one"
            elif kind_of == "duration" and "DurationIndex" not in claimed:
                # The sheet owns the duration (Architect, 2026-09-20): a donor
                # spell's leftover 15 seconds does not outrank Rend's 5. A
                # `_minutes` token is minutes: part A wrote 10 as seconds, so
                # the armors lasted 10 s (diablocraft-wizard-mechanics).
                chosen = duration_row(number * 60 if token.endswith("_minutes") else number)
                if chosen:
                    claimed.add("DurationIndex")
                    donor("DurationIndex", values[columns.index("DurationIndex")], chosen, row)
                    values[columns.index("DurationIndex")] = chosen
                    mark, source, conversion = "$d", "duration", "milliseconds"
            elif kind_of == "radius" and "EffectRadiusIndex_1" not in claimed and not is_reach(row) \
                    and not (row["rune"] and number < largest_rune_radius(row)):
                # A rune that states several radii (Spike Trap - Lightning Rod's chain and arc) draws the largest as its
                # cursor, whichever its sentence names first.
                chosen = radius_row(number, row["skill"] + (" - " + row["rune"] if row["rune"] else ""))
                if chosen:
                    claimed.add("EffectRadiusIndex_1")
                    donor("EffectRadiusIndex_1", values[F_EFFECT_RADIUS_1], chosen, row)
                    values[F_EFFECT_RADIUS_1] = chosen
                    mark, source, slot_used, conversion = "$a1", "radius", 1, "yards"
            elif kind_of == "period" and "EffectAuraPeriod_1" not in claimed:
                column = columns.index("EffectAuraPeriod_1")
                if (number * 1000).is_integer():
                    claimed.add("EffectAuraPeriod_1")
                    donor("EffectAuraPeriod_1", values[column], int(number * 1000), row)
                    values[column] = int(number * 1000)
                    mark, source, slot_used, conversion = "$t1", "period", 1, "milliseconds"
            elif kind_of == "chain" and "EffectChainTargets_1" not in claimed:
                # The core's ChainTarget counts the primary victim. At the pin,
                # Spell::SelectImplicitChainTargets (Spell.cpp:1879) reads the
                # field, enters only on 1883 `maxTargets > 1`, and searches
                # `maxTargets - 1` more on 1892, under the comment "Chain
                # primary target is added earlier". A values sheet states the
                # ADDITIONAL enemies, so the field holds one more than the
                # sheet and everything that reads it back takes the one off:
                # the sentence renders the stock expression ${$x1-1} and the
                # module's Num() subtracts in Source::Chain (Architect,
                # decisions.md 2026-09-20). Every chain token, every class.
                column = columns.index("EffectChainTargets_1")
                if number.is_integer():
                    claimed.add("EffectChainTargets_1")
                    donor("EffectChainTargets_1", values[column], int(number) + 1, row)
                    values[column] = int(number) + 1
                    mark, source, slot_used, conversion = "${$x1-1}", "chain", 1, "field_minus_one"
            elif kind_of == "proc_chance" and "ProcChance" not in claimed:
                column = columns.index("ProcChance")
                if number.is_integer():
                    claimed.add("ProcChance")
                    donor("ProcChance", values[column], int(number), row)
                    values[column] = int(number)
                    mark, source, conversion = "$h", "proc_chance", "identity"
            elif kind_of == "stacks" and "CumulativeAura" not in claimed:
                # StackAmount is a tooltip number on a storage shell and live
                # stacking on a record that applies an aura; only the first is
                # ours to write, so the second keeps its exact value.
                column = columns.index("CumulativeAura")
                if number.is_integer() and not applies_an_aura(position):
                    claimed.add("CumulativeAura")
                    donor("CumulativeAura", values[column], int(number), row)
                    values[column] = int(number)
                    mark, source, conversion = "$u", "stacks", "identity"
            elif kind_of == "charges" and "ProcCharges" not in claimed:
                # ProcCharges is the same shape as the stack count: inert on a
                # storage shell, live on a record that applies an aura.
                column = columns.index("ProcCharges")
                if number.is_integer() and not applies_an_aura(position):
                    claimed.add("ProcCharges")
                    donor("ProcCharges", values[column], int(number), row)
                    values[column] = int(number)
                    mark, source, conversion = "$n", "charges", "identity"
            elif kind_of == "cost" and skill not in MODULE_PAID_SKILLS + CHANNEL_DRAIN_SKILLS \
                    and "ManaCost" not in claimed:
                # Step 5 (decisions.md, 2026-09-20): the record carries the
                # cost and Spell::TakePower charges it. Rage units, ten per
                # Fury point, which is what the client divides by to print
                # the cost line. The sentence still prints its own copy of
                # the number through the client variables table - the client
                # has no description token for a cost - and step 7 drops that
                # clause, because by then the record's line says it.
                # The Wizard's Arcane Power is Mana, one per point (Q4).
                power_type, per_point, cost_conversion = second_resource_skills.get(
                    skill, power_of_stem[current["stem"]])
                rage = number * per_point
                if rage.is_integer():
                    claimed.add("ManaCost")
                    donor("ManaCost", values[columns.index("ManaCost")], int(rage), row)
                    values[columns.index("ManaCost")] = int(rage)
                    donor("PowerType", values[columns.index("PowerType")], power_type, row)
                    values[columns.index("PowerType")] = power_type
                    source, conversion = "cost", cost_conversion
                    printed_only = True
            elif kind_of in ("cooldown", "recharge"):
                # Step 6 (decisions.md, 2026-09-20): the record carries the
                # cooldown and Player::AddSpellAndCategoryCooldowns installs
                # it. emit() already wrote it - RecoveryTime for the skill's
                # own, CategoryRecoveryTime for the timer its runes share, or
                # the charge recharge where that is the only timer - so this
                # checks the field against the sheet rather than writing the
                # same number a second time, which is the check the mapping
                # report asks for. The sentence keeps printing its own copy
                # through the client variables until step 7 drops the clause.
                column = F_RECOVERY_TIME if kind_of == "cooldown" else F_CATEGORY_RECOVERY
                want = number * 1000
                if not want.is_integer() or values[column] != int(want):
                    raise SystemExit(
                        "%s: the sheet says %s %g s and the record holds %g ms"
                        % (name, token, number, values[column]))
                source, conversion = kind_of, "milliseconds"
                printed_only = True
            elif kind_of == "max_targets" and "MaxTargets" not in claimed:
                column = columns.index("MaxTargets")
                if number.is_integer():
                    claimed.add("MaxTargets")
                    donor("MaxTargets", values[column], int(number), row)
                    values[column] = int(number)
                    mark, source, conversion = "$i", "max_targets", "identity"
            variable = ""
            if mark is None:
                named = token + ("_" + qualifier if qualifier else "")
                # The index names a client variable only where one was
                # written. An inherited number prints nothing, and since step
                # 7 neither does a cost or a cooldown whose label line the
                # client prints from the record itself.
                if wants_mark:
                    variables.setdefault(identifier, []).append((named, row["value"]))
                    variable = named
                mark = "$<%s>" % named
                # A printed copy is not a second home: the record owns the
                # number, so it does not go to the server's exact table.
                if not printed_only:
                    exact_rows.append((identifier, token, qualifier, row["value"]))
            if row["unit"] == "pct":
                mark += "%"
            return mark, source, holder, slot_used, conversion, variable

        # The base skill first, so its numbers hold the slots the rune's own
        # sentence does not spend, then the rune's own rows on top.
        own_kinds = {kind_for(token, True) for token, _ in wanted}

        def inherit(row, base_identifier):
            _mark, source, holder, slot_used, conversion, variable = place(row, False, own=False)
            value_map.append((identifier, skill, rune, row["token"], row["qualifier"],
                              source, holder, slot_used, conversion, variable,
                              "inherited", base_identifier))

        # The skill's numbers first, so they hold the slots and the fields the
        # rune does not spend. A skill number whose FIELD the rune claims for
        # a token of its own waits until after the rune has taken it, and then
        # keeps its identity as an exact value rather than being dropped.
        contested = []
        for base_identifier, row in inherited:
            kind_of = kind_for(row["token"], False)
            if kind_of not in ("base", "exact") and kind_of in own_kinds:
                contested.append((base_identifier, row))
            else:
                inherit(row, base_identifier)

        for key in wanted:
            row = rows_by_key[key]
            mark, source, holder, slot_used, conversion, variable = place(row, key not in silent)
            marks[key] = mark
            value_map.append((identifier, skill, rune, row["token"], row["qualifier"],
                              source, holder, slot_used, conversion, variable,
                              "own", identifier))

        for base_identifier, row in contested:
            inherit(row, base_identifier)

        # The module-read rows last: they take no slot a sentence number could
        # want, they print nothing, and they are this row's own.
        for key in module_read:
            row = rows_by_key[key]
            _mark, source, holder, slot_used, conversion, variable = place(row, False)
            value_map.append((identifier, skill, rune, row["token"], row["qualifier"],
                              source, holder, slot_used, conversion, variable,
                              "own", identifier))

        body = spell_out_units(bind_marks(body, marks),
                               values[columns.index("EffectAuraPeriod_1")])
        description = spell_description(body, printed_by_client, category,
                                        "spell %s%s" % (skill, " / " + rune if rune else ""))
        descriptions.append((position, description))

    def write_sheets(class_skills, class_runes, class_passives):
        """Every row of one class's three sentence sheets, skills first, then
        runes (which inherit from their skill), then passives."""
        for row in class_skills:
            write_row("active", row["skill_name"], row["skill_name"], "",
                      row["full_tooltip_text"], row.get("category", ""), False)
        base_identifier_of = {row["skill_name"]: manifest[index_of[("active", row["skill_name"])]][0]
                              for row in class_skills if ("active", row["skill_name"]) in index_of}
        for row in class_runes:
            skill_name, rune_name = row["skill_name"], row["rune_name"]
            name = "%s - %s" % (skill_name, rune_name)
            restated = {(value["token"], value["qualifier"])
                        for value in values_for(skill_name, rune_name, stem=current["stem"])
                        # A side-effect duration is not a restatement of the
                        # skill's: Demoralize's 4 s is a taunt inside Threatening
                        # Shout, not a shorter Threatening Shout, so the skill's
                        # own 15 s still has to reach this record's DurationIndex
                        # rather than leaving the donor's leftover there
                        # (Architect ruling, decisions.md 8d89601).
                        if (skill_name, rune_name, value["token"])
                        not in SIDE_EFFECT_DURATIONS | CONDITIONAL_COOLDOWNS}
            base_identifier = base_identifier_of.get(skill_name)
            # In the base skill's sentence order, for the same reason the rune's own
            # numbers follow its sentence: the sheet's row order is not a contract.
            base_text = next(value["full_tooltip_text"] for value in class_skills
                             if value["skill_name"] == skill_name)
            base_order = {key: position for position, key
                          in enumerate(placeholder_keys(base_text.partition("Unlocked")[0]))}
            # barbarian_runes.csv is the authority on a rune's cost, and step 5 puts
            # that cost in the record: a rune that states one must state the same
            # number its values sheet row carries, and Earthquake - The Mountain's
            # Call, whose clause removes the cost, inherits no cost at all.
            modifiers = rune_modifiers(row.get("modified_cost_cooldown_damage", ""))
            own_cost = next((value["value"] for value in values_for(skill_name, rune_name, stem=current["stem"])
                             if value["token"] == "cost_resource"), None)
            if "cost" in modifiers and float(own_cost or -1) != modifiers["cost"]:
                raise SystemExit("%s: the rune sheet says a cost of %g and the values sheet says %s"
                                 % (name, modifiers["cost"], own_cost))
            if "no_cost" in modifiers and own_cost is not None:
                raise SystemExit("%s: its cost is removed and it still has a cost value" % name)
            # Step 6: the same for a rune that shortens its parent's cooldown. The
            # record holds the rune's number, so its values sheet has to state it.
            own_cooldown = next((value["value"] for value in values_for(skill_name, rune_name, stem=current["stem"])
                                 if value["token"] == "cooldown_seconds"), None)
            if "cooldown" in modifiers and float(own_cooldown or -1) != modifiers["cooldown"]:
                raise SystemExit("%s: the rune sheet says %g s and the values sheet says %s"
                                 % (name, modifiers["cooldown"], own_cooldown))
            if "no_cooldown" in modifiers and own_cooldown is not None:
                raise SystemExit("%s: its cooldown is removed and it still has a cooldown value" % name)
            inherited = sorted(((base_identifier, value) for value in values_for(skill_name, "", stem=current["stem"])
                                if (value["token"], value["qualifier"]) not in restated
                                and not ("no_cost" in modifiers and value["token"] == "cost_resource")
                                and not ("no_cooldown" in modifiers and value["token"] == "cooldown_seconds")
                                and not ((skill_name, rune_name) in RUNES_WITHOUT_CHAIN
                                         and TOKEN_KIND.get(value["token"]) == "chain")),
                               key=lambda pair: base_order.get(
                                   (pair[1]["token"], pair[1]["qualifier"]), len(base_order))) \
                if base_identifier else []
            write_row("rune", name, skill_name, rune_name,
                      row["full_rune_text"], "", False, inherited)
        for row in class_passives:
            write_row("passive", row["passive_name"], row["passive_name"], "",
                      row["full_text"], "", True)

    write_sheets(skills, runes, passives)


    # Family and mask, so a modifier aura can reach a shell at all (report
    # section 3). The bit is the skill's, shared by its runes and by the
    # companion records that carry the same skill's numbers.
    def family_pass(class_skills, family, positions):
        """Family and mask for one class's records; returns {skill: bit}."""
        if len(class_skills) > 32:
            raise SystemExit("%d skills do not fit one 32-bit SpellClassMask word"
                             % len(class_skills))
        bits = {row["skill_name"]: 1 << position for position, row in enumerate(class_skills)}
        for position in positions:
            row = manifest[position]
            name = row[1]
            skill = name.split(" - ")[0]
            if row[4] == "archon":
                # A record of Archon's own skill set rides Archon's bit.
                bit = bits.get("Archon", 0)
            elif row[4] in ("active", "rune", "ability_aura", "ability_control", "ability_proc",
                            "bleed", "token_storage"):
                bit = bits.get(skill, 0)
            elif row[4] in ("passive", "passive_effect"):
                bit = 0
            else:
                continue
            records[position][columns.index("SpellClassSet")] = family
            records[position][columns.index("SpellClassMask_1")] = bit
            # This pass is the one home for the family and the mask (Architect,
            # 2026-09-20). The skill's bit is the whole mask, so the other two
            # words are cleared rather than left holding whatever family the
            # donor spell belonged to.
            records[position][columns.index("SpellClassMask_2")] = 0
            # Word three is the record's element (Cindercoat, diablocraft-5cqu3), on the records a skill's bit reaches.
            records[position][columns.index("SpellClassMask_3")] = SCHOOL[row[2]] if bit else 0
            # Word three of an effect's mask is the same vocabulary (the element cost auras name it): a donor's leftover
            # there (Serpent Sting's third slot) is cleared so only the element auras use it.
            for prefix in ("EffectSpellClassMaskA_", "EffectSpellClassMaskB_", "EffectSpellClassMaskC_"):
                records[position][columns.index(prefix + "3")] = 0
        return bits

    skill_bit = {row["skill_name"]: 1 << position for position, row in enumerate(skills)}
    for position, row in enumerate(manifest):
        name = row[1]
        skill = name.split(" - ")[0]
        if row[4] in ("active", "rune", "ability_aura", "ability_control", "ability_proc",
                      "bleed", "token_storage"):
            bit = skill_bit.get(skill, 0)
        elif row[4] in ("passive", "passive_effect"):
            bit = 0
        else:
            continue
        records[position][columns.index("SpellClassSet")] = BARBARIAN_FAMILY
        records[position][columns.index("SpellClassMask_1")] = bit
        # This pass is the one home for the family and the mask (Architect,
        # 2026-09-20). The skill's bit is the whole mask, so the other two
        # words are cleared rather than left holding whatever family the
        # donor spell belonged to - 20 is nobody else's family, and a bit of
        # family 4's vocabulary sitting in word three says nothing true.
        records[position][columns.index("SpellClassMask_2")] = 0
        # Word three is the record's element (Cindercoat, diablocraft-5cqu3), on the records a skill's bit reaches.
        records[position][columns.index("SpellClassMask_3")] = SCHOOL[row[2]] if bit else 0

    # Step 5, the reductions (decisions.md 2026-09-20): every Fury cost is paid
    # by the core now, so every reduction has to be something the core applies -
    # a SPELLMOD_COST aura. One record per source of reduction, each hidden and
    # cast on the player by the module when its condition holds: the two
    # passives carry their own sheet percentage, and the third is the single
    # hidden aura the module fills in from the stat sheet's item and paragon
    # RCR. The mask is every skill's bit, because RCR is not skill-specific.
    every_skill = 0
    for bit in skill_bit.values():
        every_skill |= bit

    def hidden_modifier(position, aura, spellmod, amount, mask, family):
        """One hidden spell-modifier aura on the player: every cost and
        cooldown reduction record, of every class, is this same shape."""
        record = records[position]
        record[columns.index("Effect_1")] = SPELL_EFFECT_APPLY_AURA
        record[columns.index("EffectAura_1")] = aura
        record[columns.index("EffectMiscValue_1")] = spellmod
        # A reduction is negative, and the amount is exact: no die side, so the
        # module can pass a gear number in as a custom value.
        record[columns.index("EffectBasePoints_1")] = amount
        record[columns.index("EffectDieSides_1")] = 0
        record[columns.index("ImplicitTargetA_1")] = TARGET_UNIT_CASTER
        # A SPELLMOD reaches a spell only in the modifier record's own family
        # (SpellInfo::IsAffected), so the family is the class's and the mask
        # names that class's skills.
        record[columns.index("EffectSpellClassMaskA_1")] = mask
        record[columns.index("SpellClassSet")] = family
        # It is applied to a player and it has to stay applied, so nothing of
        # the donor's own may come with it and the aura never expires.
        for slot in ("2", "3"):
            for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_",
                           "ImplicitTargetA_", "ImplicitTargetB_"):
                record[columns.index(prefix + slot)] = 0
        record[columns.index("EffectRadiusIndex_1")] = 0
        record[columns.index("DurationIndex")] = min(
            key for key, raw in durations.items() if struct.unpack_from("<i", raw, 4)[0] == -1)

    cost_modifiers = []
    for identity in COST_MODIFIER_PASSIVES + (GEAR_COST_MODIFIER,):
        percent = 0
        if identity in COST_MODIFIER_PASSIVES:
            row = next((value for value in values_for(identity, "", True)
                        if value["token"] == "cost_reduction_pct"), None)
            if row is None:
                raise SystemExit("%s: no cost_reduction_pct value to build a modifier from" % identity)
            percent = float(row["value"])
            if not percent.is_integer():
                raise SystemExit("%s: a spell modifier carries whole percent, not %s"
                                 % (identity, row["value"]))
        position = helper_for("%s - cost modifier" % identity, "physical", "cost_modifier")
        hidden_modifier(position, SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST, -int(percent),
                        every_skill, BARBARIAN_FAMILY)
        cost_modifiers.append((manifest[position][0], identity, -int(percent)))

    def element_cost_modifiers(d3_class, family):
        """The class's hidden cost aura of each element (Cindercoat, diablocraft-5cqu3): no skill bit, the element's bit in word three."""
        for element in element_cost_elements():
            position = helper_for(element_cost_identity(element, d3_class), element, "element_cost_modifier")
            hidden_modifier(position, SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST, 0, 0, family)
            records[position][columns.index("EffectSpellClassMaskA_3")] = SCHOOL[element]

    element_cost_modifiers("Barbarian", BARBARIAN_FAMILY)

    def skill_cost_modifiers(bits, family):
        """The hidden cost aura of each named skill of this class (N-COST, diablocraft-e0pt4): the skill's own bit in word one."""
        for skill in skill_cost_skills():
            if skill in bits:
                position = helper_for(skill_cost_identity(skill), "physical", "skill_cost_modifier")
                hidden_modifier(position, SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST, 0, bits[skill], family)

    skill_cost_modifiers(skill_bit, BARBARIAN_FAMILY)

    def skill_cost_adders(bits, family):
        """The hidden flat cost aura of each named skill of this class (N-COST, Aether Walker, diablocraft-iv3xg): the skill's own bit in word one."""
        for skill in skill_cost_add_skills():
            if skill in bits:
                position = helper_for(skill_cost_add_identity(skill), "physical", "skill_cost_adder")
                hidden_modifier(position, SPELL_AURA_ADD_FLAT_MODIFIER, SPELLMOD_COST, 0, bits[skill], family)

    skill_cost_adders(skill_bit, BARBARIAN_FAMILY)

    # Step 6 (decisions.md, 2026-09-20): every cooldown reduction is a
    # SPELLMOD_COOLDOWN aura, so the core applies it in its own order - flat
    # before percentage, which is what core-patches/0014 gave it. Boon of
    # Bul-Kathos takes a different number of seconds off each of the three
    # skills it names, and a modifier carries one amount, so it is one record
    # per amount with that amount's skills in the mask. The last record is the
    # one hidden percentage aura the module keeps in step with the stat
    # sheet's item and paragon Cooldown Reduction.
    cooldown_modifiers = []
    for identity in COOLDOWN_MODIFIER_PASSIVES:
        by_amount = {}
        for row in values_for(identity, "", True):
            if row["token"] != "cooldown_reduction_seconds":
                continue
            skill_name = next((name for name in skill_bit
                               if name.lower().replace(" ", "_").replace("'", "") == row["qualifier"]),
                              None)
            if skill_name is None:
                raise SystemExit("%s: %s names no skill this generator knows"
                                 % (identity, row["qualifier"]))
            seconds = float(row["value"])
            if not (seconds * 1000).is_integer():
                raise SystemExit("%s: %s is not a whole millisecond" % (identity, row["value"]))
            by_amount.setdefault(int(seconds * 1000), 0)
            by_amount[int(seconds * 1000)] |= skill_bit[skill_name]
        if not by_amount:
            raise SystemExit("%s: no cooldown_reduction_seconds value to build a modifier from"
                             % identity)
        for milliseconds, mask in sorted(by_amount.items()):
            name = "%s - cooldown modifier %ds" % (identity, milliseconds // 1000)
            position = helper_for(name, "physical", "cooldown_modifier")
            # In the milliseconds the field holds.
            hidden_modifier(position, SPELL_AURA_ADD_FLAT_MODIFIER, SPELLMOD_COOLDOWN, -milliseconds,
                            mask, BARBARIAN_FAMILY)
            cooldown_modifiers.append((manifest[position][0], identity, -milliseconds))

    position = helper_for("%s - cooldown modifier" % GEAR_COOLDOWN_MODIFIER,
                          "physical", "cooldown_modifier")
    hidden_modifier(position, SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COOLDOWN, 0,
                    every_skill, BARBARIAN_FAMILY)
    cooldown_modifiers.append((manifest[position][0], GEAR_COOLDOWN_MODIFIER, 0))

    # Step 8 (brief step 8): Inspiring Presence doubles the duration of the
    # shouts, and doubling a duration is a stock SPELLMOD_DURATION modifier.
    # The module used to multiply by two at three call sites; the record
    # carries the percentage now and the core applies it, so the client's own
    # tooltip arithmetic sees it too.
    #
    # Both halves come from the passive's sheet row. The amount is the
    # `duration_bonus_pct` value, which records what the sentence's "doubled"
    # is worth; the skills are the ones the same sentence lists under "Your
    # shouts are:", so neither this generator nor the module keeps a second
    # copy of which skills they are.
    duration_modifiers = []
    for identity in DURATION_MODIFIER_PASSIVES:
        row = next((value for value in values_for(identity, "", True)
                    if value["token"] == "duration_bonus_pct"), None)
        if row is None:
            raise SystemExit("%s: no duration_bonus_pct value to build a modifier from" % identity)
        percent = float(row["value"])
        if not percent.is_integer():
            raise SystemExit("%s: a spell modifier carries whole percent, not %s"
                             % (identity, row["value"]))
        text = next((value["full_text"] for value in passives
                     if value["passive_name"] == identity), "")
        listed = SHOUT_LIST.search(text.partition("Unlocked")[0])
        if not listed:
            raise SystemExit("%s: its sentence no longer lists the skills it lengthens" % identity)
        named = [piece.strip() for piece in listed[1].split("|") if piece.strip()]
        mask = 0
        for skill_name in named:
            if skill_name not in skill_bit:
                raise SystemExit("%s: its sentence lists %r, which names no skill this "
                                 "generator knows" % (identity, skill_name))
            mask |= skill_bit[skill_name]
        if not mask:
            raise SystemExit("%s: its sentence lists no skill to lengthen" % identity)
        position = helper_for("%s - duration modifier" % identity, "physical", "duration_modifier")
        record = records[position]
        record[columns.index("Effect_1")] = SPELL_EFFECT_APPLY_AURA
        record[columns.index("EffectAura_1")] = SPELL_AURA_ADD_PCT_MODIFIER
        record[columns.index("EffectMiscValue_1")] = SPELLMOD_DURATION
        # A lengthening is positive, and exact: no die side.
        record[columns.index("EffectBasePoints_1")] = int(percent)
        record[columns.index("EffectDieSides_1")] = 0
        record[columns.index("ImplicitTargetA_1")] = TARGET_UNIT_CASTER
        record[columns.index("EffectSpellClassMaskA_1")] = mask
        record[columns.index("SpellClassSet")] = BARBARIAN_FAMILY
        for slot in ("2", "3"):
            for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_",
                           "ImplicitTargetA_", "ImplicitTargetB_"):
                record[columns.index(prefix + slot)] = 0
        record[columns.index("EffectRadiusIndex_1")] = 0
        record[columns.index("DurationIndex")] = min(
            key for key, raw in durations.items() if struct.unpack_from("<i", raw, 4)[0] == -1)
        duration_modifiers.append((manifest[position][0], identity, int(percent), sorted(named)))

    # Issue #54: the movement auras - one aggregate, and one slow per slowing
    # affix. None of them carries a number of its own; the module passes the
    # amount in as a custom value, the aggregate from the stat sheet and each
    # slow from its affix's tuned rate, so they all take the gear cost
    # modifier's shape: one aura effect, exact amount, no die side, and no
    # duration of their own so nothing expires underneath the module.
    #
    # They part company on three things, each set inside the loop with the
    # reason beside it: who the aura lands on, whether the player is shown it,
    # and what it is called. The aggregate is the player's own hidden passive,
    # and its name is never read by anyone; a slow is the elite's, cast on the
    # player, visible, and named after the affix that cast it.
    #
    # Who gets a slow record is read from the affix sheets rather than listed:
    # `elite_affix_mechanics.csv` says which affixes have a slow_percent, and
    # `elite_affixes.csv` spells their names. A slowing affix the second sheet
    # does not know is a hard error rather than a record named after nothing.
    affix_names = {row["affix_name"] for row in read_csv("elite_affixes.csv")}
    slowing = sorted({row["affix_name"] for row in read_csv("elite_affix_mechanics.csv")
                      if row["parameter"] == AFFIX_SLOW_PARAMETER})
    unknown = [affix for affix in slowing if affix not in affix_names]
    if unknown:
        raise SystemExit("elite_affix_mechanics.csv slows %r, which elite_affixes.csv does not name"
                         % unknown)
    if not slowing:
        raise SystemExit("no affix has a %s row; the slow records would be empty"
                         % AFFIX_SLOW_PARAMETER)

    movement_modifiers = []
    plan = [(MOVEMENT_MODIFIER, "%s - movement modifier" % MOVEMENT_MODIFIER,
             "movement_modifier", SPELL_AURA_MOD_INCREASE_SPEED, None)]
    plan += [(affix, AFFIX_SLOW_IDENTITY % affix, "affix_slow",
              SPELL_AURA_MOD_DECREASE_SPEED, affix) for affix in slowing]
    for owner, identity, kind, aura, shown in plan:
        position = helper_for(identity, "physical", kind)
        record = records[position]
        record[columns.index("Effect_1")] = SPELL_EFFECT_APPLY_AURA
        record[columns.index("EffectAura_1")] = aura
        record[columns.index("EffectMiscValue_1")] = 0
        record[columns.index("EffectBasePoints_1")] = 0
        record[columns.index("EffectDieSides_1")] = 0
        # The two records are NOT cast the same way, and the record is what
        # decides where the aura lands - not the unit handed to CastCustomSpell.
        # The aggregate is the player's own, cast on itself. The slow is cast by
        # the elite ON the player, so it has to name an explicit target or the
        # core resolves TARGET_UNIT_CASTER and the elite slows itself
        # (SpellInfo.cpp's target table: 1 is the caster, 6 is the explicit
        # enemy). The module's own caster-keyed lifetimes depend on this: the
        # aura has to be on the player, cast BY the elite.
        slow = aura == SPELL_AURA_MOD_DECREASE_SPEED
        record[columns.index("ImplicitTargetA_1")] = \
            TARGET_UNIT_TARGET_ENEMY if slow else TARGET_UNIT_CASTER
        if slow:
            # The one thing the player reads. The identity above is the
            # generator's key and keeps the id stable across reruns; this is
            # the affix's own name, exactly as elite_affixes.csv spells it.
            record[columns.index("Name_Lang_enUS")] = shown
            # Architect ruling 2026-09-21: the player is to SEE the elite slow
            # (13 S10), while the aggregate stays hidden. Visibility is exactly
            # one bit - Aura::CanBeSentToClient is `!IsPassive() || ...` - and
            # the debuff frame rather than the buff frame follows on its own,
            # because SpellInfo::_IsPositiveEffect calls a MOD_DECREASE_SPEED
            # cast at anyone but the caster negative. Clearing PASSIVE costs
            # the free multi-slot stacking, so the attribute that names it
            # goes on in the same breath; the two belong together and are
            # tested together.
            record[F_ATTRIBUTES] &= ~SPELL_ATTR0_PASSIVE
            record[columns.index("AttributesEx3")] |= SPELL_ATTR3_DOT_STACKING_RULE
            # A self-only range on a record cast at someone else is the same
            # kind of mismatch. The module casts it triggered, so the core never
            # checks this, but the record should still say something true: the
            # furthest an affix can reach a player it is standing in a zone
            # with. It is a bound, not a tuning input - no affix reads it.
            record[columns.index("RangeIndex")] = closest(ranges, 100.0)
        # Not a spell modifier, so no family and no skill mask: these two act on
        # the unit's own speed, not on another record's fields.
        record[columns.index("EffectSpellClassMaskA_1")] = 0
        for slot in ("2", "3"):
            for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_",
                           "ImplicitTargetA_", "ImplicitTargetB_"):
                record[columns.index(prefix + slot)] = 0
        record[columns.index("EffectRadiusIndex_1")] = 0
        record[columns.index("DurationIndex")] = min(
            key for key, raw in durations.items() if struct.unpack_from("<i", raw, 4)[0] == -1)
        movement_modifiers.append((manifest[position][0], owner))
    if [owner for _id, owner in movement_modifiers] != [MOVEMENT_MODIFIER] + slowing:
        raise SystemExit("expected the aggregate movement aura and one slow per slowing affix "
                         "(%r), found %r" % ([MOVEMENT_MODIFIER] + slowing,
                                             [owner for _id, owner in movement_modifiers]))

    # GitHub #44: Bash - Punish's buff, the aura the player wears and sees.
    # The Frenzy buff's stock shape (above): the sentence states one stack's
    # worth with a bare $s1 and CumulativeAura says how far it stacks. Its
    # three numbers are the rune's own values sheet rows, and its icon the
    # rune record's. dc_barbarian_primaries.cpp applies it on each Bash - Punish cast
    # and reads its stack count for the damage bonus, so what the buff bar
    # shows is what the damage uses.
    punish_rune = index_of.get(("rune", PUNISH_RUNE))
    if punish_rune is None:
        raise SystemExit("%s: no rune record, so its buff has no icon" % PUNISH_RUNE)
    skill, _, rune = PUNISH_RUNE.partition(" - ")
    numbers = {token: value_of(skill, rune, token)
               for token in ("damage_bonus_pct", "duration_seconds", "max_stacks_count")}
    if None in numbers.values():
        raise SystemExit("%s: the values sheet is missing %s" % (
            PUNISH_RUNE, sorted(token for token, number in numbers.items() if number is None)))
    if not numbers["damage_bonus_pct"].is_integer() or duration_row(numbers["duration_seconds"]) is None:
        raise SystemExit("%s: %g%% needs whole percent and %g s a stock SpellDuration row"
                         % (PUNISH_RUNE, numbers["damage_bonus_pct"], numbers["duration_seconds"]))
    punish = records[helper_for(PUNISH_BUFF, manifest[punish_rune][2], "barbarian_buff")]
    punish[F_ATTRIBUTES] = SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
    punish[columns.index("AttributesEx3")] = SPELL_ATTR3_ALWAYS_HIT
    punish[columns.index("ProcTypeMask")] = 0
    punish[F_RANGE_INDEX] = 1   # stock Self Only
    punish[columns.index("DurationIndex")] = duration_row(numbers["duration_seconds"])
    punish[columns.index("CumulativeAura")] = int(numbers["max_stacks_count"])
    punish[columns.index("SpellIconID")] = records[punish_rune][columns.index("SpellIconID")]
    for slot in (1, 2, 3):
        for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_",
                       "ImplicitTargetA_", "ImplicitTargetB_", "EffectRadiusIndex_",
                       "EffectAuraPeriod_", "EffectBasePoints_", "EffectDieSides_",
                       "EffectSpellClassMaskA_"):
            punish[columns.index(prefix + str(slot))] = 0
    punish[F_EFFECT_1] = SPELL_EFFECT_APPLY_AURA
    punish[columns.index("EffectAura_1")] = SPELL_AURA_DUMMY
    punish[columns.index("ImplicitTargetA_1")] = TARGET_UNIT_CASTER
    punish[columns.index("EffectBasePoints_1")] = int(numbers["damage_bonus_pct"]) - 1   # $s1 = base + die
    punish[columns.index("EffectDieSides_1")] = 1
    punish[columns.index("AuraDescription_Lang_enUS")] = "Damage increased by $s1%."

    # Buff icons build 2 (diablocraft-b3zj): the Barbarian's class buffs and the text of the passive auras that had none.
    class_buffs("barbarian")
    regeneration_mask("Barbarian")

    # --- every other class: the generic pass ------------------------------
    # diablocraft-wizard-records. Each class's skills, runes and passives in
    # its own reserved block, written by the same write_sheets() and
    # family_pass() the Barbarian's go through, AFTER every Barbarian record so
    # no Barbarian id, row or variable moves. None of the Barbarian's companion
    # records (ability and control auras, bleeds, primaries' internals) exist
    # for another class: a number with no free slot goes to that class's own
    # helper block instead, and the class's own mechanics are later tasks.
    class_bits = {}
    for stem, class_row, class_skills, class_runes, class_passives in other_classes:
        block = CLASS_BLOCKS[stem]
        current["stem"] = stem
        first_position = len(records)
        spell_id = block.records[0]
        known = {row["skill_name"]: row for row in class_skills}
        for skill in class_skills:
            name = skill["skill_name"]
            if name not in targeting:
                raise SystemExit("%s: no skill_targeting.csv row" % name)
            emit(name, skill, targeting_for(targeting[name], stem=stem), base_spell_for(name),
                 skill_element(skill), False)
        for rune in class_runes:
            parent = known.get(rune["skill_name"])
            if parent is None:
                raise SystemExit(f"rune {rune['rune_name']}: unknown skill {rune['skill_name']}")
            element = (rune.get("element") or "").strip().lower() or skill_element(parent)
            if element not in SCHOOL:
                raise SystemExit(f"rune {rune['rune_name']}: unmapped element {element!r}")
            modifiers = rune_modifiers(rune.get("modified_cost_cooldown_damage", ""))
            # The rune's own cooldown row is its recovery, whether or not the
            # rune sheet's modifier column repeats it (the Barbarian's always
            # did; Frost Nova - Cold Snap's does not) - unless it is one of
            # the conditional cooldowns above.
            own_cooldown = value_of(parent["skill_name"], rune["rune_name"], "cooldown_seconds",
                                    stem=stem)
            if (parent["skill_name"], rune["rune_name"], "cooldown_seconds") in CONDITIONAL_COOLDOWNS:
                own_cooldown = None
            # A rune that aims differently from its skill (Inner Sanctuary - Intervene dashes to a ground point) has a
            # skill_targeting.csv row named "<skill> - <rune>"; every other rune takes its skill's row.
            emit(f"{parent['skill_name']} - {rune['rune_name']}", parent,
                 targeting_for(targeting.get(f"{parent['skill_name']} - {rune['rune_name']}")
                               or targeting[parent["skill_name"]], rune, stem),
                 base_spell_for(parent["skill_name"], rune["rune_name"]), element, False,
                 shell_kind="rune",
                 cooldown_override=own_cooldown if own_cooldown is not None
                 else "" if "no_cooldown" in modifiers else modifiers.get("cooldown"),
                 rank="Rune: " + rune["rune_name"])
        for passive in class_passives:
            emit(passive["passive_name"], None, None, PASSIVE_BASE_SPELL, "physical", True)
        if stem == "wizard":
            archon = known["Archon"]
            archon_values = read_csv(ARCHON_VALUES)
            for ability in ARCHON_SET:
                geometry = ARCHON_VISUAL % ability
                if geometry not in targeting:
                    raise SystemExit("%s: no skill_targeting.csv row" % geometry)
                # No skill name, so no cooldown category: the ability's own
                # recovery is its record's RecoveryTime and nothing shares it.
                cooldown = next((row["value"] for row in archon_values
                                 if row["ability"] == ability and row["token"] == "cooldown_seconds"), "")
                emit(ability, {"skill_name": "", "category": ARCHON_RANK, "cooldown_seconds": cooldown},
                     targeting_for(targeting[geometry], stem=stem), base_spell_for(geometry),
                     skill_element(archon), False, shell_kind="archon", rank=ARCHON_RANK)
                records[-1][columns.index("Description_Lang_enUS")] = ARCHON_SENTENCE
        if spell_id - 1 > block.records[1]:
            raise SystemExit("%s: %d records overrun the block %d-%d"
                             % (stem, spell_id - block.records[0], *block.records))
        for position in range(first_position, len(records)):
            index_of[(manifest[position][4], manifest[position][1])] = position
        write_sheets(class_skills, class_runes, class_passives)
        for skill_row, rune_row in ([(skill, None) for skill in class_skills]
                                    + [(known[rune["skill_name"]], rune) for rune in class_runes]):
            percent = life_cost_pct(skill_row, rune_row)
            if percent is None:
                continue
            if not percent.is_integer():
                raise SystemExit("%s: Life cost %g%% is not a whole percent" % (skill_row["skill_name"], percent))
            name = skill_row["skill_name"] + (" - " + rune_row["rune_name"] if rune_row else "")
            position = index_of[("rune" if rune_row else "active", name)]
            values, identifier = records[position], manifest[position][0]
            # Every Life cost is the exact token the module reads and charges (SpendLife, at D3's percent of max Life): the record
            # carries no POWER_HEALTH and no ManaCostPct, which the core would charge as well, from base health (diablocraft-u59aj).
            exact_rows.append((identifier, HEALTH_COST_TOKEN, "", "%g" % percent))
            value_map.append((identifier, skill_row["skill_name"], rune_row["rune_name"] if rune_row else "",
                              HEALTH_COST_TOKEN, "", "exact", identifier, 0, "", "", "own", identifier))
        class_bits[stem] = family_pass(class_skills, block.family, range(first_position, len(records)))
        regeneration = primary_regeneration(class_row["d3_class"].strip())
        if regeneration is not None:
            power, units, _conversion = power_of(class_row["d3_class"].strip())
            per_five = regeneration * units * POWER_REGEN_SECONDS
            if per_five != int(per_five):
                raise SystemExit("class_resources.csv: %s regen_per_second %s is not a whole number of "
                                 "%s units per %d seconds" % (class_row["d3_class"], regeneration,
                                                              class_row["wow_power_type"], POWER_REGEN_SECONDS))
            position = helper_for(RESOURCE_REGENERATION % class_row["d3_class"], "physical",
                                  "resource_regeneration")
            record = records[position]
            for slot, aura, amount in (("1", SPELL_AURA_MOD_POWER_REGEN, int(per_five)),
                                       ("2", SPELL_AURA_MOD_POWER_REGEN_PERCENT, NO_SPIRIT_REGEN_PCT)):
                record[columns.index("Effect_" + slot)] = SPELL_EFFECT_APPLY_AURA
                record[columns.index("EffectAura_" + slot)] = aura
                record[columns.index("EffectMiscValue_" + slot)] = power
                record[columns.index("EffectMiscValueB_" + slot)] = 0
                # Exact: no die side, the amount is the number.
                record[columns.index("EffectBasePoints_" + slot)] = amount
                record[columns.index("EffectDieSides_" + slot)] = 0
                record[columns.index("ImplicitTargetA_" + slot)] = TARGET_UNIT_CASTER
                record[columns.index("ImplicitTargetB_" + slot)] = 0
                record[columns.index("EffectRadiusIndex_" + slot)] = 0
                record[columns.index("EffectSpellClassMaskA_" + slot)] = 0
            for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_",
                           "ImplicitTargetA_", "ImplicitTargetB_"):
                record[columns.index(prefix + "3")] = 0
            # The player's own and never expires: the module keeps it on.
            record[columns.index("DurationIndex")] = min(
                key for key, raw in durations.items() if struct.unpack_from("<i", raw, 4)[0] == -1)
        energy_rate_record(class_row["d3_class"].strip())
        regeneration_mask(class_row["d3_class"].strip())
        # Issue #61: the class's own gear-and-paragon cost and cooldown
        # auras, in its family and over every one of its skills, so item and
        # paragon RCR and CDR reach it the way the Barbarian's reach family 20.
        class_every_skill = 0
        for bit in class_bits[stem].values():
            class_every_skill |= bit
        for base, kind, spellmod in ((GEAR_COST_MODIFIER, "cost_modifier", SPELLMOD_COST),
                                     (GEAR_COOLDOWN_MODIFIER, "cooldown_modifier", SPELLMOD_COOLDOWN)):
            position = helper_for("%s - %s" % (gear_identity(base, class_row["d3_class"].strip()),
                                               kind.replace("_", " ")), "physical", kind)
            hidden_modifier(position, SPELL_AURA_ADD_PCT_MODIFIER, spellmod, 0,
                            class_every_skill, block.family)
        element_cost_modifiers(class_row["d3_class"].strip(), block.family)
        if stem == "shaman":
            # The Overcharge and Attunement buffs: the class mechanics' icons and texts (data/class_buffs.csv).
            class_buffs(stem)
        if stem == "monk":
            position = helper_for(EPIPHANY_REACH, "holy", "range_modifier")
            hidden_modifier(position, SPELL_AURA_ADD_FLAT_MODIFIER, SPELLMOD_RANGE, EPIPHANY_REACH_YARDS,
                            class_every_skill, block.family)
            seconds = value_of("Epiphany", "", "duration_seconds", stem=stem)
            reach_duration = duration_row(seconds) if seconds else None
            if reach_duration is None:
                raise SystemExit("%s: no stock SpellDuration row for Epiphany's %r seconds" % (EPIPHANY_REACH, seconds))
            records[position][columns.index("DurationIndex")] = reach_duration
        skill_cost_modifiers(class_bits[stem], block.family)
        skill_cost_adders(class_bits[stem], block.family)
        current["stem"] = "barbarian"
    # A live class with its blocks and no skill sheets yet: only the records its resource needs, in its helper block.
    for class_row in read_csv("class_map.csv"):
        stem = sheet_stem(class_row["d3_class"])
        if stem in CLASS_BLOCKS and stem != "barbarian" and not (DATA / ("%s_skills.csv" % stem)).is_file():
            current["stem"] = stem
            energy_rate_record(class_row["d3_class"].strip())
            regeneration_mask(class_row["d3_class"].strip())
            current["stem"] = "barbarian"
    # The side-effect rename guard, once every class that could hold one (the
    # Wizard's Ice Blades freeze is written below the Barbarian) is written.
    missed = SIDE_EFFECT_DURATIONS - side_effects_used
    if missed:
        raise SystemExit("side-effect duration rows that no sheet row matched: %s"
                         % sorted(missed))

    # The same rename guard for the conditional cooldowns, once every class
    # that could hold one has been written.
    unmatched = {row for row in CONDITIONAL_COOLDOWNS
                 if class_of_name.get(row[0]) and row not in side_effects_used}
    if unmatched:
        raise SystemExit("conditional cooldown rows that no sheet row matched: %s" % sorted(unmatched))

    for position, text in descriptions:
        records[position][columns.index("Description_Lang_enUS")] = text

    # --- diablocraft-wizard-mechanics: the Wizard's stock carriers ---------
    # Every skill's effect goes on the stock thing that already does it
    # (brief B2, AGENTS.md stock first), after the sheet numbers are placed so
    # no slot a number holds is taken:
    #   * the ten-minute buffs, Diamond Skin, Archon, Explosive Blast and
    #     Frozen Mist are the record's own aura on the caster - Diamond Skin a
    #     SCHOOL_ABSORB, Ice Armor a MOD_MELEE_DAMAGE_TAKEN_PCT, Prism and
    #     Power of the Storm a flat SPELLMOD_COST, Storm Armor, Frozen Storm
    #     and Frozen Mist a PERIODIC_DUMMY the module ticks; Evocation a
    #     percentage SPELLMOD_COOLDOWN over every Wizard skill;
    #   * Teleport is SPELL_EFFECT_LEAP to the cursor (Blink's shape);
    #   * Hydra is SPELL_EFFECT_SUMMON with Searing Totem's summon properties,
    #     so the core keeps one Hydra, places it and despawns it;
    #   * Slow Time's bubble and Meteor's molten ground are persistent area
    #     auras on helper records the module casts where they belong - the
    #     bubble at the cast point, the ground where and when a meteor lands -
    #     because each record's own slots hold its sheet numbers (the bubble's
    #     radius is not the sheet's 60-yard reach) and a stock ground starts
    #     at the cast, not 1.25 s later;
    #   * freeze, stun, slow and taunt are stock control auras, and the
    #     passive and rune shields stock absorbs, on helper records the module
    #     applies with the duration and amount the sheet gives.
    # The amounts an aura needs negated or computed (a slow, a cost cut, an
    # absorb from maximum Life) come from DC::Combat::Numbers in the module's
    # AuraScripts, so a tooltip still prints the sheet's positive number.
    def wizard_mechanics(bits):
        saved_stem = current["stem"]
        current["stem"] = "wizard"
        c = columns.index
        every = 0
        for bit in bits.values():
            every |= bit
        infinite = min(key for key, raw in durations.items() if struct.unpack_from("<i", raw, 4)[0] == -1)

        def positions(skill, kinds=("active", "rune")):
            return [index for index, row in enumerate(manifest)
                    if row[4] in kinds and row[1].split(" - ")[0] == skill]

        def named(name, kinds=("active", "rune")):
            found = [index for index, row in enumerate(manifest) if row[4] in kinds and row[1] == name]
            if len(found) != 1:
                raise SystemExit("wizard mechanics: %d records named %r" % (len(found), name))
            return found[0]

        def slot_of(position, token, qualifier="", origin=None):
            identifier = manifest[position][0]
            for row in value_map:
                if (row[0] == identifier and row[3] == token and row[4] == qualifier
                        and row[5] == "base_points" and row[6] == identifier
                        and (origin is None or row[10] == origin)):
                    return row[7]
            return None

        def free_slot(values):
            for slot in (1, 2, 3):
                if not (values[c("Effect_%d" % slot)] or values[c("EffectBasePoints_%d" % slot)]
                        or values[c("EffectDieSides_%d" % slot)]):
                    return slot
            raise SystemExit("%s: no free effect slot" % values[F_NAME_ENUS])

        def set_effect(values, slot, effect, aura, target_a=TARGET_UNIT_CASTER, target_b=0, misc=0,
                       radius=None, period=None, mask=None):
            values[c("Effect_%d" % slot)] = effect
            values[c("EffectAura_%d" % slot)] = aura
            values[c("ImplicitTargetA_%d" % slot)] = target_a
            values[c("ImplicitTargetB_%d" % slot)] = target_b
            values[c("EffectMiscValue_%d" % slot)] = misc
            values[c("EffectMiscValueB_%d" % slot)] = 0
            if radius is not None:
                values[c("EffectRadiusIndex_%d" % slot)] = radius
            if period is not None:
                values[c("EffectAuraPeriod_%d" % slot)] = period
            if mask is not None:
                values[c("EffectSpellClassMaskA_%d" % slot)] = mask

        def milliseconds(skill, rune, token, qualifier=""):
            number = value_of(skill, rune, token, qualifier, stem="wizard")
            if number is None:
                number = value_of(skill, "", token, qualifier, stem="wizard")
            if number is None:
                raise SystemExit("%s - %s: no %s" % (skill, rune, token))
            return int(round(number * 1000))

        def exact_radius(yards, who):
            row = radius_row(yards)
            if row is None:
                raise SystemExit("%s: no stock SpellRadius row for %g yards" % (who, yards))
            return row

        def helper(identity, element, kind, donor=None, debuff=False):
            position = helper_for(identity, element, kind)
            values = records[position]
            values[F_ATTRIBUTES] = (SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
                                    | (0x04000000 if debuff else 0))  # SPELL_ATTR0_AURA_IS_DEBUFF
            values[c("AttributesEx3")] = SPELL_ATTR3_ALWAYS_HIT
            values[c("DurationIndex")] = infinite
            values[c("ProcTypeMask")] = 0
            for slot in (1, 2, 3):
                set_effect(values, slot, 0, 0, target_a=0)
                values[c("EffectRadiusIndex_%d" % slot)] = 0
                values[c("EffectAuraPeriod_%d" % slot)] = 0
            if donor is not None:
                for column in ("SpellVisualID_1", "SpellVisualID_2", "SpellIconID"):
                    values[c(column)] = donor[c(column)]
            return position, values

        scripted = {"dc_wizard_buff": [], "dc_wizard_slow": [], "armors": []}
        # The record is the buff.
        for skill in WIZARD_BUFF_SKILLS + ("Diamond Skin", "Archon", "Explosive Blast"):
            for position in positions(skill):
                values = records[position]
                set_effect(values, 1, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_DUMMY)
                values[c("ProcTypeMask")] = 0
                scripted["dc_wizard_buff"].append(manifest[position][0])
                if skill in WIZARD_ARMORS:
                    scripted["armors"].append(manifest[position][0])
                if values[c("CumulativeAura")]:
                    # StackAmount is live stacking on a record that applies an
                    # aura (the core multiplies the amount by the stacks), so a
                    # stack count this record's sentence printed as $u moves
                    # to the exact-value home, the same rule place() follows.
                    identifier = manifest[position][0]
                    for index, row in enumerate(value_map):
                        if row[0] == identifier and row[5] == "stacks":
                            named_value = row[3] + ("_" + row[4] if row[4] else "")
                            number = values[c("CumulativeAura")]
                            value_map[index] = row[:5] + ("exact", identifier, 0, "", named_value) + row[10:]
                            exact_rows.append((identifier, row[3], row[4], "%g" % number))
                            variables.setdefault(identifier, []).append((named_value, "%g" % number))
                            values[c("Description_Lang_enUS")] = values[c("Description_Lang_enUS")].replace(
                                "$u", "$<%s>" % named_value)
                    values[c("CumulativeAura")] = 0
                if skill == "Diamond Skin":
                    slot = slot_of(position, "absorb_capacity_life_pct")
                    set_effect(values, slot, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_SCHOOL_ABSORB,
                               misc=SPELL_SCHOOL_MASK_ALL)
                if skill == "Ice Armor":
                    slot = slot_of(position, "damage_reduction_pct")
                    set_effect(values, slot, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_MOD_MELEE_DAMAGE_TAKEN_PCT)
                if skill == "Storm Armor":
                    set_effect(values, 1, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_PERIODIC_DUMMY,
                               period=milliseconds("Storm Armor", "", "interval_seconds"))
                cost = slot_of(position, "cost_reduction_resource")
                if cost is not None:
                    # Prism, Power of the Storm: "reduce the Arcane Power cost
                    # of all skills by N while active", a flat SPELLMOD_COST
                    # over every Wizard skill's bit.
                    set_effect(values, cost, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_ADD_FLAT_MODIFIER,
                               misc=SPELLMOD_COST, mask=every)
        frozen_storm = records[named("Ice Armor - Frozen Storm")]
        set_effect(frozen_storm, free_slot(frozen_storm), SPELL_EFFECT_APPLY_AURA, SPELL_AURA_PERIODIC_DUMMY,
                   period=milliseconds("Ice Armor", "Frozen Storm", "interval_seconds"))
        mist = named("Frost Nova - Frozen Mist")
        set_effect(records[mist], 1, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_PERIODIC_DUMMY,
                   period=milliseconds("Frost Nova", "Frozen Mist", "interval_seconds"))
        records[mist][c("ProcTypeMask")] = 0
        scripted["dc_wizard_buff"].append(manifest[mist][0])
        evocation = named("Evocation", ("passive",))
        set_effect(records[evocation], slot_of(evocation, "cooldown_reduction_pct"), SPELL_EFFECT_APPLY_AURA,
                   SPELL_AURA_ADD_PCT_MODIFIER, misc=SPELLMOD_COOLDOWN, mask=every)
        scripted["dc_wizard_buff"].append(manifest[evocation][0])

        # Teleport: Blink's effect, to the cursor.
        archon = {row[1]: index for index, row in enumerate(manifest) if row[4] == "archon"}
        for position in positions("Teleport") + [archon["Teleport"]]:
            set_effect(records[position], 1, SPELL_EFFECT_LEAP, 0, target_a=TARGET_UNIT_CASTER,
                       target_b=TARGET_DEST_DEST)

        # Hydra: the stock summon, one per rune's creature.
        summons = read_csv("wizard_summons.csv")
        totem = spells[base_spell_for("Hydra")]
        for position in positions("Hydra"):
            skill, _, rune = manifest[position][1].partition(" - ")
            entry = next((int(row["entry"]) for row in summons
                          if row["skill"] == skill and row["rune"] == rune), None)
            if entry is None:
                raise SystemExit("%s: no wizard_summons.csv row" % manifest[position][1])
            values = records[position]
            set_effect(values, 1, SPELL_EFFECT_SUMMON, 0, target_a=TARGET_DEST_CASTER, misc=entry)
            values[c("EffectMiscValueB_1")] = field(totem, c("EffectMiscValueB_1"))

        # Slow Time's bubble: one helper per Slow Time record, at the cast point.
        bubble_radius = exact_radius(float(targeting["Slow Time"]["radius_yards"]), "Slow Time bubble")
        # The bubble lasts the skill's duration_seconds; a rune's own seconds
        # (Point of No Return's stun) may hold its record's DurationIndex.
        bubble_life = duration_row(milliseconds("Slow Time", "", "duration_seconds") / 1000)
        for position in positions("Slow Time"):
            values = records[position]
            bubble_position, bubble = helper(manifest[position][1] + " - bubble", manifest[position][2],
                                             "slow_bubble", donor=values, debuff=True)
            set_effect(bubble, 1, SPELL_EFFECT_PERSISTENT_AREA_AURA, SPELL_AURA_MOD_DECREASE_SPEED,
                       target_a=TARGET_DEST_DEST, radius=bubble_radius)
            set_effect(bubble, 2, SPELL_EFFECT_PERSISTENT_AREA_AURA, SPELL_AURA_MELEE_SLOW,
                       target_a=TARGET_DEST_DEST, radius=bubble_radius)
            if manifest[position][1] == "Slow Time - Stretch Time":
                # "Time is sped up for any allies standing in the area".
                set_effect(bubble, 3, SPELL_EFFECT_PERSISTENT_AREA_AURA, SPELL_AURA_MELEE_SLOW,
                           target_a=TARGET_DEST_DEST, target_b=TARGET_DEST_DYNOBJ_ALLY, radius=bubble_radius)
            bubble[c("DurationIndex")] = bubble_life
            bubble[F_RANGE_INDEX] = values[F_RANGE_INDEX]
            scripted["dc_wizard_slow"].append(manifest[bubble_position][0])
        # Crown of the Primus (diablocraft-bl9iz): Slow Time "permanently follows you". One helper per Slow Time record, worn by the
        # caster: the bubble's two enemy effects as stock enemy area auras at the bubble's size, and Stretch Time's ally effect as the
        # stock party area aura (the caster is in his own party), infinite until the module takes it off (hat off, map change, logout).
        # The owner (the record it is named after) is the rune chosen; the effect of every rune but Point of No Return is
        # given by the table's `rune` rows, read by the module (dc_wizard.cpp GivenFollow).
        for position in positions("Slow Time"):
            values = records[position]
            follow_position, follow = helper(manifest[position][1] + " - follow", manifest[position][2],
                                             "slow_follow", donor=values, debuff=True)
            set_effect(follow, 1, SPELL_EFFECT_APPLY_AREA_AURA_ENEMY, SPELL_AURA_MOD_DECREASE_SPEED, radius=bubble_radius)
            set_effect(follow, 2, SPELL_EFFECT_APPLY_AREA_AURA_ENEMY, SPELL_AURA_MELEE_SLOW, radius=bubble_radius)
            set_effect(follow, 3, SPELL_EFFECT_APPLY_AREA_AURA_PARTY, SPELL_AURA_MELEE_SLOW, radius=bubble_radius)
            scripted["dc_wizard_slow"].append(manifest[follow_position][0])
        # Archon form's Slow Time "follows you": the stock enemy area aura on
        # the caster, the base bubble's two effects at the base bubble's size.
        slow = records[archon["Slow Time"]]
        for slot, aura in ((1, SPELL_AURA_MOD_DECREASE_SPEED), (2, SPELL_AURA_MELEE_SLOW)):
            set_effect(slow, slot, SPELL_EFFECT_APPLY_AREA_AURA_ENEMY, aura, radius=bubble_radius)
        seconds = next(float(row["value"]) for row in read_csv(ARCHON_VALUES)
                       if row["ability"] == "Slow Time" and row["token"] == "duration_seconds")
        if duration_row(seconds) is None:
            raise SystemExit("Archon form Slow Time: no SpellDuration row for %g s" % seconds)
        slow[c("DurationIndex")] = duration_row(seconds)
        scripted["dc_wizard_slow"].append(manifest[archon["Slow Time"]][0])

        # Meteor's molten ground: one helper per Meteor record, cast where and
        # when each meteor lands. Its shape is the record's: radius, period,
        # A ground whose interval is not a whole number of milliseconds -
        # Black Hole's 8 frames, 0.1333 s (wizard.js:1190) - keeps the exact
        # number in the exact table, which is what the module reads, and
        # its record still needs a period or the stock aura never ticks.
        # The period is the nearest millisecond: 133 over the 2 s life is
        # the simulator's 15 ticks (120 / 8 frames), and a tick deals the
        # total over GetTotalTicks, so the total is unchanged.
        for skill in GROUND_DOT_SKILLS:
            for position in positions(skill):
                values = records[position]
                if values[F_EFFECT_1] != SPELL_EFFECT_PERSISTENT_AREA_AURA or values[c("EffectAuraPeriod_1")]:
                    continue
                _skill, _, rune = manifest[position][1].partition(" - ")
                values[c("EffectAuraPeriod_1")] = milliseconds(skill, rune, "interval_seconds")

        # visual, school; its life the record's molten duration.
        for position in positions(METEOR_GROUND_SKILL):
            values = records[position]
            skill, _, rune = manifest[position][1].partition(" - ")
            _position, ground = helper(METEOR_GROUND % manifest[position][1], manifest[position][2], "meteor_ground",
                            donor=values, debuff=True)
            # The ground is the size of one meteor's impact: the targeting
            # sheet's, or a rune's own radius - never Meteor Shower's spread,
            # which is where its seven meteors land, not how big each is.
            yards = value_of(skill, rune, "radius_yards", stem="wizard") if rune != "Meteor Shower" else None
            if yards is None:
                yards = float(targeting[METEOR_GROUND_SKILL]["radius_yards"])
            set_effect(ground, 1, SPELL_EFFECT_PERSISTENT_AREA_AURA, SPELL_AURA_PERIODIC_DUMMY,
                       target_a=TARGET_DEST_DEST, radius=exact_radius(yards, manifest[position][1]),
                       period=milliseconds(skill, rune, "interval_seconds"))
            life = value_of(skill, rune, "dot_duration_seconds", "molten", stem="wizard")
            if life is None:
                life = value_of(skill, rune, "dot_duration_seconds", stem="wizard")
            if life is None:
                life = value_of(skill, "", "dot_duration_seconds", stem="wizard")
            if life is None or duration_row(life) is None:
                raise SystemExit("%s: no molten ground duration row" % manifest[position][1])
            ground[c("DurationIndex")] = duration_row(life)
            ground[F_RANGE_INDEX] = values[F_RANGE_INDEX]

        # The control auras and the shields, applied by the module.
        frost = records[named("Frost Nova")]
        slowed = records[named("Slow Time")]
        for identity, aura, mechanic, donor in (
                ("Wizard - Frozen", SPELL_AURA_MOD_STUN, MECHANIC_FREEZE, frost),
                ("Wizard - Stunned", SPELL_AURA_MOD_STUN, MECHANIC_STUN, None),
                ("Wizard - Slowed", SPELL_AURA_MOD_DECREASE_SPEED, MECHANIC_SNARE, slowed),
                ("Wizard - Taunted", SPELL_AURA_MOD_TAUNT, 0, None)):
            _position, values = helper(identity, "arcane", "wizard_control", donor=donor, debuff=True)
            set_effect(values, 1, SPELL_EFFECT_APPLY_AURA, aura, target_a=TARGET_UNIT_TARGET_ENEMY)
            values[c("Mechanic")] = mechanic
        shield = records[named("Diamond Skin")]
        for identity in ("Galvanizing Ward - shield", "Dominance - shield", "Unstable Anomaly - shield",
                         "Magic Weapon - Deflection - shield", "Spectral Blade - Barrier Blades - shield"):
            _position, values = helper(identity, "arcane", "wizard_shield", donor=shield)
            set_effect(values, 1, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_SCHOOL_ABSORB, misc=SPELL_SCHOOL_MASK_ALL)

        # diablocraft-o2be. Flame Blades' bonus is a buff the Wizard wears: Punish's shape (above), one stacking
        # aura on the caster whose sentence states ONE stack's worth with a bare $s1 and whose CumulativeAura says
        # how far it stacks. The module sets the stack count (one per enemy hit, each stack on its own clock) and
        # reads it back for the Fire bonus, so what the buff shows is what the damage uses. The icon is the rune's;
        # the record takes no visual, so wearing it plays no spell effect.
        position = named("Spectral Blade - Flame Blades")
        flame = {token: value_of("Spectral Blade", "Flame Blades", token, stem="wizard")
                 for token in ("damage_bonus_pct", "max_bonus_pct", "bonus_duration_seconds")}
        if None in flame.values():
            raise SystemExit("Spectral Blade - Flame Blades: the values sheet is missing %s"
                             % sorted(token for token, number in flame.items() if number is None))
        if (not flame["damage_bonus_pct"].is_integer() or flame["damage_bonus_pct"] < 1
                or flame["max_bonus_pct"] % flame["damage_bonus_pct"]
                or duration_row(flame["bonus_duration_seconds"]) is None):
            raise SystemExit("Spectral Blade - Flame Blades: %g%% a stack, %g%% at most and %g s need whole stacks "
                             "and a stock SpellDuration row" % (flame["damage_bonus_pct"], flame["max_bonus_pct"],
                                                                flame["bonus_duration_seconds"]))
        _position, values = helper(FLAME_BLADES_BUFF, manifest[position][2], "wizard_stacks")
        set_effect(values, 1, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_DUMMY)
        values[F_RANGE_INDEX] = 1   # stock Self Only
        values[c("EffectBasePoints_1")] = int(flame["damage_bonus_pct"]) - 1   # $s1 = base + die
        values[c("EffectDieSides_1")] = 1
        values[c("DurationIndex")] = duration_row(flame["bonus_duration_seconds"])
        values[c("CumulativeAura")] = int(flame["max_bonus_pct"] / flame["damage_bonus_pct"])
        values[c("SpellIconID")] = records[position][c("SpellIconID")]
        values[c("AuraDescription_Lang_enUS")] = "The damage of your Fire spells is increased by $s1%."

        # Buff icons build 2 (diablocraft-b3zj): the Wizard's class buffs and the shields' text.
        class_buffs("wizard")

        # diablocraft-wizard-b3. Arcane Mines: "movement and attack speeds
        # reduced" - the movement half is Wizard - Slowed, and the attack half
        # the stock MELEE_SLOW Slow Time's bubble already uses, on its own
        # control helper so no other slow gains it.
        _position, values = helper("Wizard - Slowed attacks", "arcane", "wizard_control", donor=slowed, debuff=True)
        set_effect(values, 1, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_MELEE_SLOW, target_a=TARGET_UNIT_TARGET_ENEMY)
        values[c("Mechanic")] = MECHANIC_SNARE
        # Conflagrate's burn: the stock periodic aura on the enemy, ticking
        # every interval_seconds (wizard.js:42, 15 frames) over the rune's
        # dot_duration_seconds and stacking to its max_stacks_count
        # (:30-31); the module's tick deals damage_pct x stacks over the
        # ticks. Stock stacking refreshes the duration with each new stack.
        position = named("Magic Missile - Conflagrate")
        _position, burn = helper("Magic Missile - Conflagrate - burn", manifest[position][2], "wizard_dot",
                                 donor=records[position], debuff=True)
        set_effect(burn, 1, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_PERIODIC_DUMMY, target_a=TARGET_UNIT_TARGET_ENEMY,
                   period=milliseconds("Magic Missile", "Conflagrate", "interval_seconds"))
        life = value_of("Magic Missile", "Conflagrate", "dot_duration_seconds", stem="wizard")
        stacks = value_of("Magic Missile", "Conflagrate", "max_stacks_count", stem="wizard")
        if life is None or duration_row(life) is None or not stacks:
            raise SystemExit("Magic Missile - Conflagrate: no burn duration row or stack count")
        burn[c("DurationIndex")] = duration_row(life)
        burn[c("CumulativeAura")] = int(stacks)
        scripted["dc_wizard_buff"].append(manifest[_position][0])
        # Scorch's wall: the stock periodic aura on the caster for the wall's
        # dot_duration_seconds, ticking every interval_seconds (wizard.js:249,
        # 6 frames); the module's tick hits the line the orb burned (:217).
        position = named("Arcane Orb - Scorch")
        _position, wall = helper("Arcane Orb - Scorch - wall", manifest[position][2], "wizard_wall",
                                 donor=records[position])
        set_effect(wall, 1, SPELL_EFFECT_APPLY_AURA, SPELL_AURA_PERIODIC_DUMMY,
                   period=milliseconds("Arcane Orb", "Scorch", "interval_seconds"))
        life = value_of("Arcane Orb", "Scorch", "dot_duration_seconds", stem="wizard")
        if life is None or duration_row(life) is None:
            raise SystemExit("Arcane Orb - Scorch: no wall duration row")
        wall[c("DurationIndex")] = duration_row(life)
        scripted["dc_wizard_buff"].append(manifest[_position][0])

        # Archon form's five abilities: their sourced numbers, read by name
        # like any other (ruling Q5). A cooldown is the record's RecoveryTime,
        # which emit() wrote from the same row; the rest are exact values.
        for row in read_csv(ARCHON_VALUES):
            if not (row.get("source") or "").strip():
                raise SystemExit("%s: %s %s has no source" % (ARCHON_VALUES, row["ability"], row["token"]))
            # The form's own look (diablocraft-ie3xd): the display the player wears while Archon lasts, Torment's own client row
            # (client-patch/dbc/build_creaturedisplayinfo.py builds it from the sheet's display_id and scale, which only it reads). On the
            # Archon skill's record, its runes answer with it (Numbers::Get).
            if row["ability"] == "Archon":
                if row["token"] in ("display_id", "scale"):
                    continue
                if row["token"] != "form_display_id" or not row["value"].isdigit():
                    raise SystemExit("%s: Archon %s %r is not the form's display id" % (ARCHON_VALUES, row["token"], row["value"]))
                base = manifest[named("Archon", ("active",))][0]
                for position in positions("Archon"):
                    identifier, name = manifest[position][0], manifest[position][1]
                    exact_rows.append((identifier, row["token"], row["qualifier"], row["value"]))
                    value_map.append((identifier, "Archon", name.partition(" - ")[2], row["token"], row["qualifier"], "exact", identifier,
                                      0, "", "", "own" if identifier == base else "inherited", base))
                continue
            if row["ability"] not in archon:
                raise SystemExit("%s: %s is not an Archon form ability" % (ARCHON_VALUES, row["ability"]))
            position = archon[row["ability"]]
            identifier = manifest[position][0]
            if row["token"] == "cooldown_seconds":
                if records[position][F_RECOVERY_TIME] != int(round(float(row["value"]) * 1000)):
                    raise SystemExit("%s: Archon form %s cooldown is not the record's"
                                     % (ARCHON_VALUES, row["ability"]))
                value_map.append((identifier, ARCHON_FORM, row["ability"], row["token"], row["qualifier"],
                                  "cooldown", identifier, 0, "milliseconds", "", "own", identifier))
                continue
            exact_rows.append((identifier, row["token"], row["qualifier"], row["value"]))
            value_map.append((identifier, ARCHON_FORM, row["ability"], row["token"], row["qualifier"],
                              "exact", identifier, 0, "", "", "own", identifier))
        current["stem"] = saved_stem
        return scripted

    wizard_scripts = wizard_mechanics(class_bits["wizard"]) if "wizard" in class_bits else {}

    # diablocraft-buff-text: every Description is final here and the variable rows
    # are not built yet, so a buff that borrows a number's `$<name>` can still get
    # the row entry. The rule is at BUFF_SKIPPED_LINE.
    position_of = {}
    for position, row in enumerate(manifest):
        if row[4] not in ("active", "rune", "ability_aura"):
            continue
        if (row[4], row[1]) in position_of:
            raise SystemExit("two records are both the %s %r" % (row[4], row[1]))
        position_of[(row[4], row[1])] = position
    aura_column = columns.index("AuraDescription_Lang_enUS")
    description_column = columns.index("Description_Lang_enUS")

    def worn(buff, parts):
        """The buff record's aura text from [(source position, variable prefix)], in order."""
        pieces, borrowed = [], []
        for source, prefix in parts:
            owner = None if source == buff else manifest[source][0]
            piece, names = buff_sentence(records[source][description_column], owner, prefix)
            if not piece:
                continue
            pieces.append(piece)
            known = dict(variables.get(manifest[source][0], []))
            for name in names if owner is not None else ():
                if name not in known:
                    raise SystemExit("%s: its buff asks for $<%s> and %s has no such variable"
                                     % (manifest[buff][1], name, manifest[source][1]))
                borrowed.append((prefix + name, known[name]))
        if not pieces:
            return
        text = "\r\n".join(pieces)
        refuse_unfilled("buff %s" % manifest[buff][1], text, pattern=UNFILLED_TOKEN_WOW)
        records[buff][aura_column] = text
        have = variables.setdefault(manifest[buff][0], [])
        have.extend(entry for entry in borrowed if entry not in have)

    for (kind, name), position in position_of.items():
        skill, _, rune = name.partition(" - ")
        if kind in ("active", "rune") and skill in WIZARD_WORN_SKILLS:
            # The record is the buff.
            worn(position, ([(position_of[("active", skill)], "base_")] if rune else []) + [(position, "")])
        elif kind == "ability_aura" and skill in BARBARIAN_WORN_MARKERS \
                and (BARBARIAN_WORN_MARKERS[skill] is None or rune in BARBARIAN_WORN_MARKERS[skill]):
            # The marker is the buff and owns no number: it points at the records that do.
            own = position_of[("rune" if rune else "active", name)]
            worn(position, ([(position_of[("active", skill)], "base_")] if rune else []) + [(own, "")])
    # The exact values, as the client's variables table and as a server table.
    variable_id = FIRST_VARIABLE_ID
    variable_rows = []
    # In spell id order, not the order the classes are generated in: a class whose block sits above a later-generated
    # class's (the Crusader's 85400 up beside the Necromancer's 85100 up) takes the ids after it, so none already shipped moves.
    for position, row in sorted(enumerate(manifest), key=lambda pair: pair[1][0]):
        entries = variables.get(row[0])
        if not entries:
            continue
        # The shape the stock rows write a value in (step 11, 2026-09-20):
        # `$name=${value}`, several to a row separated by CRLF, no terminator.
        # The 30 stock rows, ids running through 181, hold 67 name=value
        # pieces: 11 wrap a plain value in `${...}`, 54 are conditional
        # expressions like `$?s56801[${6+2+5}][${6+2}]` whose branches wrap
        # their own values, and two are bare - `$junk=1` in row 29 and
        # `$base=($pl-1)*3+10` in row 181. So the stock file settles the
        # separator and says a semicolon appears nowhere in it; ours were
        # written `$name=value;`, the client did not parse them, and it
        # printed the token as text, which is what the designer saw on client 29.
        text = "\r\n".join("$%s=${%s}" % (name, value) for name, value in entries)
        records[position][columns.index("SpellDescriptionVariableID")] = variable_id
        variable_rows.append((variable_id, text))
        variable_id += 1

    # GitHub #45 (Architect, 2026-09-29): a record whose effect takes a
    # TARGET_DEST_DEST point carries the stock TARGET_FLAG_DEST_LOCATION, the
    # way 389 of the stock client's DEST_DEST spells do (Heroic Leap 6544,
    # which Leap is cloned from, among them). Without it the client never asks
    # for a ground point, so none arrives, and Spell::InitExplicitTargets puts
    # the destination on the caster: Furious Charge charged to its own feet.
    # A rule over every record, not a list of ids, so a new ground skill
    # cannot ship without it; a module-cast helper gets it too and loses
    # nothing, because a scripted cast passes its point explicitly.
    for values in records:
        if any(values[columns.index("ImplicitTarget%s_%d" % (side, slot))] == TARGET_DEST_DEST
               for side in "AB" for slot in (1, 2, 3)):
            values[columns.index("Targets")] |= TARGET_FLAG_DEST_LOCATION

    # diablocraft-ground-target-circles: a ground skill whose sheet gives no
    # area is a small marker, not whatever radius its donor spell had. Only
    # the effect that TAKES the point is sized (a cone effect keeps its reach:
    # the core reads that one), and only the record the player casts.
    marker_rows = [row for row in read_tunables_csv("combat.csv") if row["name"] == GROUND_MARKER_TUNABLE]
    if len(marker_rows) != 1 or not (marker_rows[0]["value"] or marker_rows[0]["d3_value"]):
        raise SystemExit("combat.csv: %s needs exactly one row with a value" % GROUND_MARKER_TUNABLE)
    marker_yards = float(marker_rows[0]["value"] or marker_rows[0]["d3_value"])
    marker = radius_row(marker_yards)
    if marker is None:
        raise SystemExit("combat.csv: no stock SpellRadius row for a %g yard marker" % marker_yards)
    own_area = {row[0] for row in value_map if row[3] == "radius_yards" and row[5] == "radius"}
    for position, entry in enumerate(manifest):
        if entry[4] not in ("active", "rune", "archon"):
            continue
        base = entry[1].split(" - ")[0]
        geometry = targeting.get(ARCHON_VISUAL % base if entry[4] == "archon" else base)
        if not geometry or geometry["target_type"] not in GROUND_TARGETS \
                or (geometry["radius_yards"] and base not in MARKER_CURSOR_SKILLS):
            continue
        for slot in (1, 2, 3):
            if TARGET_DEST_DEST in (records[position][columns.index("ImplicitTargetA_%d" % slot)],
                                    records[position][columns.index("ImplicitTargetB_%d" % slot)]) \
                    and records[position][columns.index("ImplicitTargetA_%d" % slot)] != TARGET_UNIT_CONE_ENEMY \
                    and (base in MARKER_CURSOR_SKILLS and entry[0] not in own_area
                         or not radii.get(records[position][columns.index("EffectRadiusIndex_%d" % slot)], 0)):
                # A rune's own radius (Teleport - Calamity's stun, Leap - Launch)
                # is an area and already drew; only a zero-yard slot becomes the
                # marker, and a marker-cursor skill's donor radius too.
                records[position][columns.index("EffectRadiusIndex_%d" % slot)] = marker

    # GitHub #52: no chain count leaves the writer without an owner. The ones
    # the module resolves are zeroed and named in the donor log below.
    overrides.extend(settle_chain_counts(
        records, columns, manifest,
        {row[6] for row in value_map if row[5] == "chain"}, targeting))

    # Pylons and shrines P1 (diablocraft-plgq2, docs/proposals/pylons.md 4.3): the buff each kind gives, from
    # data/pylon_buffs.csv. Emitted last, with explicit ids, so no id the running counter hands out above moves. Each
    # record's numbers are the pylon_/shrine_ rows of the combat tunables it names, baked as the $s tokens of its text (a record's text
    # cannot be live; the module reads the same rows live for the effect). The module applies the aura with its own
    # seconds (the row `seconds` names), so the record's duration is the stock infinite one. A pylon's record carries
    # the stock death-persistent flag, a shrine's does not, so the core takes a shrine's off at death (6.11).
    # carriers: per kind, the effect slots in order: (aura, misc value, number, in the text). A number is the sheet
    # column that names the tunables row, or an int for an effect with no number of its own; a carrier with no number
    # is a plain marker the module reads by name.
    ENERGY, MANA = 3, 0
    PYLON_CARRIERS = {
        "power": [(SPELL_AURA_DUMMY, 0, "amount_1", True)],
        # P2: the stock periodic dummy; the module strikes on its tick (dc_pylons.cpp dc_pylon_tick).
        "conduit": [(SPELL_AURA_PERIODIC_DUMMY, 0, None, False)],
        "channeling": [(SPELL_AURA_DUMMY, 0, "amount_1", True)],
        # The stock all-school immunity and the stock all-controls set (what Ignore Pain carries); the 147 lookup
        # needs a nonzero amount (base + die), hence the 1.
        "shield": [(39, SPELL_SCHOOL_MASK_ALL, None, False), (SPELL_AURA_MECHANIC_IMMUNITY_MASK, IMMUNITY_ALL_CONTROLS, 1, False)],
        "speed": [(SPELL_AURA_DUMMY, 0, "amount_1", True), (SPELL_AURA_DUMMY, 0, "amount_2", True)],
        "blessed": [(SPELL_AURA_DUMMY, 0, "amount_1", True)],
        # SPELL_AURA_MOD_POWER_REGEN_PERCENT (110) on Energy and on Mana: whichever the class regenerates doubles.
        "empowered": [(110, ENERGY, "amount_1", True), (SPELL_AURA_DUMMY, 0, "amount_2", True), (110, MANA, "amount_1", False)],
        "enlightened": [(SPELL_AURA_DUMMY, 0, "amount_1", True)],
        "fleeting": [(SPELL_AURA_DUMMY, 0, "amount_1", True)],
        "fortune": [(SPELL_AURA_DUMMY, 0, "amount_1", True), (SPELL_AURA_DUMMY, 0, "amount_2", True)],
        "frenzied": [(SPELL_AURA_DUMMY, 0, "amount_1", True)],
    }
    seen_pylon_ids, seen_pylon_kinds, pylon_icons = set(), set(), {}
    for buff in read_pylon_buffs():
        pylon_spell, kind = int(buff["spell_id"]), buff["kind"]
        who = "pylon_buffs.csv: %s" % kind
        if not PYLON_ID_FIRST <= pylon_spell <= PYLON_ID_LAST or pylon_spell in seen_pylon_ids \
                or kind not in PYLON_CARRIERS or kind in seen_pylon_kinds or buff["group"] not in ("pylon", "shrine"):
            raise SystemExit("%s: id %d is outside the pylon block %d-%d, listed twice, or the kind/group is unknown"
                             % (who, pylon_spell, PYLON_ID_FIRST, PYLON_ID_LAST))
        seen_pylon_ids.add(pylon_spell)
        seen_pylon_kinds.add(kind)
        donor_kind, _, donor_id = buff["icon"].partition(":")
        donor_id = donor_id or donor_kind        # the sheet gives the bare donor spell id
        donor = spells.get(int(donor_id)) if donor_id.isdigit() else None
        if donor is None:
            raise SystemExit("%s: icon %r is not a spell of Spell.dbc" % (who, buff["icon"]))
        slot_numbers = {}
        for slot, (aura, misc, source, in_text) in enumerate(PYLON_CARRIERS[kind], 1):
            if isinstance(source, str):
                if not buff[source]:
                    raise SystemExit("%s: effect %d wants %s and the row has none" % (who, slot, source))
                slot_numbers[slot] = pylon_tunable(buff[source], who)
            elif isinstance(source, int):
                slot_numbers[slot] = source
        for column in ("amount_1", "amount_2"):
            used = [src for _a, _m, src, _t in PYLON_CARRIERS[kind] if src == column]
            if bool(buff[column]) != bool(used):
                raise SystemExit("%s: %s is %r but the %s effects use it %d times" % (who, column, buff[column], kind, len(used)))
        wanted_tokens = {"$s%d" % slot for slot, (_a, _m, src, in_text) in enumerate(PYLON_CARRIERS[kind], 1) if in_text}
        if set(re.findall(r"\$s\d", buff["text"])) != wanted_tokens or re.search(r"per stack", buff["text"], re.I):
            raise SystemExit("%s: the text must state exactly its numbers (%s) as totals" % (who, sorted(wanted_tokens)))
        spell_id = pylon_spell
        emit(buff["name"], None, None, PASSIVE_BASE_SPELL, "physical", False, shell_kind="pylon_buff")
        values = records[-1]
        c = columns.index
        values[F_ATTRIBUTES] = SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
        values[c("AttributesEx3")] = SPELL_ATTR3_ALWAYS_HIT | (SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD if buff["group"] == "pylon" else 0)
        if kind == "shield":
            values[c("AttributesEx")] |= SPELL_ATTR1_IMMUNITY_PURGES_EFFECT   # taking it frees a held player
        values[c("ProcTypeMask")] = 0
        values[F_RANGE_INDEX] = 1   # stock Self Only: the module applies it, nobody casts it
        values[c("DurationIndex")] = infinite_row
        values[c("SpellIconID")] = field(donor, c("SpellIconID"))
        for slot in (1, 2, 3):
            for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_", "ImplicitTargetA_",
                           "ImplicitTargetB_", "EffectRadiusIndex_", "EffectAuraPeriod_", "EffectBasePoints_",
                           "EffectDieSides_", "EffectSpellClassMaskA_"):
                values[c(prefix + str(slot))] = 0
        for slot, (aura, misc, source, in_text) in enumerate(PYLON_CARRIERS[kind], 1):
            values[c("Effect_%d" % slot)] = SPELL_EFFECT_APPLY_AURA
            values[c("EffectAura_%d" % slot)] = aura
            values[c("EffectMiscValue_%d" % slot)] = misc
            values[c("ImplicitTargetA_%d" % slot)] = TARGET_UNIT_CASTER
            if slot in slot_numbers:
                values[c("EffectBasePoints_%d" % slot)] = slot_numbers[slot] - 1   # $sN = base + die
                values[c("EffectDieSides_%d" % slot)] = 1
        if kind == "conduit":
            values[c("EffectAuraPeriod_1")] = pylon_tunable("pylon_conduit_pulse_ms", who)
        values[c("AuraDescription_Lang_enUS")] = buff["text"]
        pylon_icons[kind] = values[c("SpellIconID")]
    # P2 (diablocraft-eok78, pylons.md 6.9, 6.10). Conduit's strike is a shell of its own, Lightning, that the module
    # hands to the damage formula or deals as a share of Life; it carries no effect. Speed's knock-up is its own aura
    # beside Speed's buff (so leaving the rift can take only it, 6.11): the stock periodic dummy the module ticks,
    # hidden from the buff bar (Speed's buff states it) and kept through death as the pylons' are. On each monster run
    # into the module casts the stock knockback, so the core spares what it always spares (bosses, giants, the
    # knockback-immune, the rooted: SpellEffects.cpp EffectKnockBack); its speeds are the rows', in tenths.
    for pylon_spell, kind, element, icon in ((PYLON_CONDUIT_STRIKE, "pylon_strike", "lightning", "conduit"),
                                             (PYLON_SPEED_KNOCKUP, "pylon_tick", "physical", "speed"),
                                             (PYLON_SPEED_THROW, "pylon_throw", "physical", "speed")):
        if not PYLON_ID_FIRST <= pylon_spell <= PYLON_ID_LAST or pylon_spell in seen_pylon_ids:
            raise SystemExit("pylon P2 record %d is outside the pylon block or taken by pylon_buffs.csv" % pylon_spell)
        seen_pylon_ids.add(pylon_spell)
        spell_id = pylon_spell
        emit("Dimensional " + icon.capitalize(), None, None, PASSIVE_BASE_SPELL, element, False, shell_kind=kind)
        values = records[-1]
        c = columns.index
        values[F_ATTRIBUTES] = SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
        values[c("AttributesEx3")] = SPELL_ATTR3_ALWAYS_HIT
        values[c("ProcTypeMask")] = 0
        values[F_RANGE_INDEX] = 1
        values[c("DurationIndex")] = infinite_row
        values[c("SpellIconID")] = pylon_icons[icon]
        for slot in (1, 2, 3):
            for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_", "ImplicitTargetA_",
                           "ImplicitTargetB_", "EffectRadiusIndex_", "EffectAuraPeriod_", "EffectBasePoints_",
                           "EffectDieSides_", "EffectSpellClassMaskA_"):
                values[c(prefix + str(slot))] = 0
        if kind == "pylon_tick":
            values[c("AttributesEx")] |= SPELL_ATTR1_NO_AURA_ICON
            values[c("AttributesEx3")] |= SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD
            values[c("Effect_1")] = SPELL_EFFECT_APPLY_AURA
            values[c("EffectAura_1")] = SPELL_AURA_PERIODIC_DUMMY
            values[c("ImplicitTargetA_1")] = TARGET_UNIT_CASTER
            values[c("EffectAuraPeriod_1")] = pylon_tunable("pylon_speed_knockup_tick_ms", "Speed's knock-up")
        elif kind == "pylon_throw":
            values[F_RANGE_INDEX] = RANGE_ANYWHERE
            values[c("Effect_1")] = SPELL_EFFECT_KNOCK_BACK
            values[c("ImplicitTargetA_1")] = TARGET_UNIT_TARGET_ENEMY
            # EffectKnockBack: speedxy = MiscValue / 10, speedz = the effect's value / 10.
            values[c("EffectMiscValue_1")] = pylon_tunable("pylon_speed_knockup_speed_xy", "Speed's knock-up") * 10
            values[c("EffectBasePoints_1")] = pylon_tunable("pylon_speed_knockup_speed_z", "Speed's knock-up") * 10 - 1
            values[c("EffectDieSides_1")] = 1
    spell_id = max(row[0] for row in manifest) + 1
    if seen_pylon_kinds != set(PYLON_CARRIERS):
        raise SystemExit("pylon_buffs.csv lacks %s" % sorted(set(PYLON_CARRIERS) - seen_pylon_kinds))

    # Legendary power buffs (diablocraft-pl8fc): the pylon buffs' shape. Display only: one SPELL_AURA_DUMMY whose $s1 is the power row's
    # number, infinite here, the module sets the seconds of the window; the power's effect is the row's own (dc_item_power_math.h).
    # A `slow` (Stone Gauntlets, diablocraft-ghb4o) is the stock SPELL_AURA_MOD_DECREASE_SPEED of the row's number with the Snare
    # mechanic, a debuff the core slows by and control immunity removes. A buff of an owner that stacks (`stack_buff`) has that
    # row's stack_max as its CumulativeAura: $s1 is one stack's number, the client shows the total. A `mark` (Bindings of the Lesser Gods,
    # diablocraft-zhizu) is the debuff a power puts on an ENEMY: a dummy aura aimed at an enemy and flagged a debuff, its text stating no
    # number (the module stores the rolled percent in the aura's effect amount when it applies the mark, dc_item_powers.cpp MarkEnemy).
    # A `hit` (Bovine Bardiche's cows, diablocraft-4p9j9) is no buff: a name-only record, a gem `hit`'s shape, that the power's damage
    # is dealt and logged under; no text, no effect, Physical.
    seen_power_ids, seen_power_rows = set(), set()
    for buff in read_power_buffs():
        power_spell, who = int(buff["spell_id"]), "legendary_power_buffs.csv: %s" % buff["owner"]
        if not POWER_BUFF_ID_FIRST <= power_spell <= POWER_BUFF_ID_LAST or power_spell in seen_power_ids \
                or (buff["owner"], buff["stat"]) in seen_power_rows:
            raise SystemExit("%s: id %d is outside the block %d-%d or listed twice" % (who, power_spell, POWER_BUFF_ID_FIRST, POWER_BUFF_ID_LAST))
        seen_power_ids.add(power_spell)
        seen_power_rows.add((buff["owner"], buff["stat"]))
        donor = spells.get(int(buff["icon"])) if buff["icon"].isdigit() else None
        if donor is None:
            raise SystemExit("%s: icon %r is not a spell of Spell.dbc" % (who, buff["icon"]))
        if buff["aura"] not in ("dummy", "slow", "mark", "hit"):
            raise SystemExit("%s: aura %r is not dummy, slow, mark or hit" % (who, buff["aura"]))
        mark, hit = buff["aura"] == "mark", buff["aura"] == "hit"
        number = 0 if hit else 1 if mark else power_buff_number(buff)
        if (buff["text"] != "") if hit else re.findall(r"\$s\d", buff["text"]) != ([] if mark or number is None else ["$s1"]):
            raise SystemExit("%s: the text must state its number once, as $s1 (a mark and a rolled number state none: the roll is the aura's; a hit record has no text)" % who)
        # The school: Physical unless the record names an element (Storm Crow's Fiery Ball is Fire), so the combat log and the
        # damage formula read the hit as that element's. Only a hit record names one.
        element = buff.get("element") or "physical"
        if element not in SCHOOL or (element != "physical" and not hit):
            raise SystemExit("%s: element %r is not a school, or the record is not a hit" % (who, element))
        spell_id = power_spell
        emit(buff["name"], None, None, PASSIVE_BASE_SPELL, element, False, shell_kind="power_buff")
        values = records[-1]
        c = columns.index
        values[F_ATTRIBUTES] = SPELL_ATTR0_IS_ABILITY | SPELL_ATTR0_NO_ACTIVE_DEFENSE
        values[c("AttributesEx3")] = SPELL_ATTR3_ALWAYS_HIT
        values[c("ProcTypeMask")] = 0
        values[F_RANGE_INDEX] = 1   # stock Self Only: the module applies it, nobody casts it
        values[c("DurationIndex")] = infinite_row
        values[c("SpellIconID")] = field(donor, c("SpellIconID"))
        for slot in (1, 2, 3):
            for prefix in ("Effect_", "EffectAura_", "EffectMiscValue_", "EffectMiscValueB_", "ImplicitTargetA_",
                           "ImplicitTargetB_", "EffectRadiusIndex_", "EffectAuraPeriod_", "EffectBasePoints_",
                           "EffectDieSides_", "EffectSpellClassMaskA_"):
                values[c(prefix + str(slot))] = 0
        if hit:
            continue
        values[c("Effect_1")] = SPELL_EFFECT_APPLY_AURA
        values[c("EffectAura_1")] = SPELL_AURA_DUMMY
        values[c("ImplicitTargetA_1")] = TARGET_UNIT_CASTER
        if number is not None:
            values[c("EffectBasePoints_1")] = number - 1   # $s1 = base + die
            values[c("EffectDieSides_1")] = 1
        values[c("AuraDescription_Lang_enUS")] = buff["text"]
        values[c("CumulativeAura")] = power_buff_stacks(buff)
        if mark:
            values[c("ImplicitTargetA_1")] = TARGET_UNIT_TARGET_ENEMY
            values[F_ATTRIBUTES] |= 0x04000000   # SPELL_ATTR0_AURA_IS_DEBUFF
        if buff["aura"] == "slow":
            values[c("EffectAura_1")] = SPELL_AURA_MOD_DECREASE_SPEED
            values[c("Mechanic")] = MECHANIC_SNARE
            values[F_ATTRIBUTES] |= 0x04000000   # SPELL_ATTR0_AURA_IS_DEBUFF

    # Bounties W2 (diablocraft-e719a): the Click objective's channel, in the Identify shells' shape (the Town Portal's base, a cast on
    # the player whose one effect is a dummy: the objective is the module's work when the cast ends). Its name is the cast bar's
    # ('Activating', the designer's to change). Nothing in the record interrupts it, not moving and not damage: the server stops it on damage
    # itself unless the player is immune to control (W2, dc_bounty_objectives.cpp; maxroll: "interrupted by damage, unless you are
    # immune to Crowd Control").
    spell_id = BOUNTY_CLICK_SPELL
    emit("Activating", None, None, IDENTIFY_BASE_SPELL, "physical", False, shell_kind="bounty_click")
    values = records[-1]
    for column in ("InterruptFlags", "AuraInterruptFlags", "ChannelInterruptFlags"):
        values[columns.index(column)] = 0

    # Bounties (diablocraft-dm9vg.10): the travel cast from the open world, in the same shape ('Teleporting', the designer's to change). The
    # server sets its interrupts as Town Portal's (moving, an interrupt, damage: dc_bounties.cpp TravelSpellData), so the record
    # carries none, as Town Portal's carries none.
    spell_id = BOUNTY_TRAVEL_SPELL
    emit("Teleporting", None, None, IDENTIFY_BASE_SPELL, "physical", False, shell_kind="bounty_travel")
    values = records[-1]
    for column in ("InterruptFlags", "AuraInterruptFlags", "ChannelInterruptFlags"):
        values[columns.index(column)] = 0
    spell_id = max(row[0] for row in manifest) + 1

    # Grenadier's giant grenade (a Demon Hunter helper): emitted last, so the records before it keep their strings' offsets and a
    # client patch built with it differs from the one before only by this record.
    current["stem"] = "demon_hunter"
    helper_for(GRENADIER_BLAST, "fire", "strike_helper")
    current["stem"] = "barbarian"

    rows_sql[:] = [render(values) for values in records]
    # helper_for() moved the running id into the reserved block; the DELETE
    # range below is written from it, so put it back above every shell.
    spell_id = max(row[0] for row in manifest) + 1

    # Where every one of the sheet numbers lives, so step 2 can build its index
    # from the record instead of from a table of copied literals, and so this
    # step's checker can verify each field against the sheet row that owns it.
    GENERATED.mkdir(parents=True, exist_ok=True)
    with (GENERATED / "spell_value_map.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["spell_id", "skill", "rune", "token", "qualifier",
                         "source", "holder_spell_id", "slot", "conversion", "variable",
                         "origin", "origin_spell_id"])
        writer.writerows(value_map)

    # The same map as C++ the module can index: step 2's Num() reads a number
    # out of the record this names, with the conversion this names, instead of
    # out of a generated table of literals.
    source_name = {"base_points": "BasePoints", "duration": "Duration", "radius": "Radius",
                   "period": "Period", "chain": "Chain", "proc_chance": "ProcChance",
                   "stacks": "Stacks", "charges": "Charges", "max_targets": "MaxTargets",
                   "cost": "Cost", "cooldown": "Cooldown", "recharge": "Recharge",
                   "exact": "Exact"}
    index_rows = ["    {%d, \"%s\", \"%s\", Source::%s, %d, %d, Origin::%s, %d}," % (
        row[0], row[3], row[4], source_name[row[5]], row[6], row[7],
        "Own" if row[10] == "own" else "Inherited", row[11]) for row in value_map]
    (MODULE_ROOT / "src/combat").mkdir(parents=True, exist_ok=True)
    (MODULE_ROOT / "src/combat/dc_spell_values.h").write_text(
        "// Generated by generate_spells.py from the barbarian values sheets; never hand-edit.\n"
        "// One row per number the sheets name: where it lives and how to read it back.\n"
        "#pragma once\n#include <cstdint>\n"
        "namespace DC::Combat::SpellValues\n{\n"
        "// How the number is stored in the record it lives in.\n"
        "enum class Source : uint8_t\n{\n"
        "    BasePoints, Duration, Radius, Period, Chain, ProcChance, Stacks, Charges,\n"
        "    MaxTargets, Cost, Cooldown, Recharge, Exact\n};\n"
        "// A record's cost is in its PowerType slot's units; the units per\n"
        "// resource point are the class resource registry's (dc_resources.h).\n"
        "// Whether the row states this number itself or takes it from its base skill.\n"
        "enum class Origin : uint8_t { Own, Inherited };\n"
        "struct Row\n{\n"
        "    uint32_t spell;         // the skill, rune or passive shell\n"
        "    char const* token;      // the name the sheets use\n"
        "    char const* qualifier;  // \"\" unless the token needs one\n"
        "    Source source;          // which field holds it\n"
        "    uint32_t holder;        // the record that field is on: the shell,\n"
        "                            // its companion aura or a token-storage helper\n"
        "    uint8_t slot;           // effect slot, 1-3, or 0 for a record-level field\n"
        "    Origin origin;\n"
        "    uint32_t originSpell;   // the base skill an inherited number came from\n"
        "};\n"
        "inline constexpr Row Rows[] = {\n" + "\n".join(index_rows) + "\n};\n}\n",
        encoding="utf-8", newline="\n")

    with (GENERATED / "spell_helper_ids.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        # The class column arrived with the second class: each id sits in its
        # own class's helper block, and the column says which one.
        writer.writerow(["identity", "spell_id", "class"])
        writer.writerows(sorted(helper_rows, key=lambda row: row[1]))

    # The persisted skill -> cooldown category map, written back so the next
    # run reads it instead of deriving one from row order.
    with (GENERATED / "spell_cooldown_categories.csv").open(
            "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["skill", "category", "class"])
        writer.writerows((skill, category, category_class[skill]) for skill, category
                         in sorted(skill_categories.items(), key=lambda row: row[1]))

    # ...and the rows themselves, as a DBC, because that is the only place the
    # core will look for them: SpellInfo's constructor resolves Category
    # through sSpellCategoryStore and GetCategory() answers 0 for an id with no
    # row, which would leave Player::AddSpellAndCategoryCooldowns on its "self
    # spell cooldown" branch and a rune family with no shared timer at all.
    # Every stock row is preserved; ours replace anything already sitting in
    # the reserved block, so a rerun over an already-patched file cannot
    # double a row (the same rule the Spell.dbc pass above follows).
    stock_categories = load_dbc("SpellCategory.dbc")
    category_size = stock_categories[3]
    if stock_categories[2] != 2 or category_size != 8:
        raise SystemExit("SpellCategory.dbc has %d fields of %d bytes, expected 2 of 8"
                         % (stock_categories[2], category_size))
    preserved_categories = [raw for key, raw in sorted(stock_categories[0].items())
                            if block_for_category(key) is None]
    ours = [struct.pack("<II", category, COOLDOWN_CATEGORY_FLAGS)
            for _skill, category in sorted(skill_categories.items(), key=lambda row: row[1])]
    CLIENT_CATEGORY_DBC.parent.mkdir(parents=True, exist_ok=True)
    CLIENT_CATEGORY_DBC.write_bytes(
        struct.pack("<4sIIII", b"WDBC", len(preserved_categories) + len(ours), 2,
                    category_size, 1)
        + b"".join(preserved_categories) + b"".join(ours) + b"\x00")

    # SpellRadius.dbc: the client reads the highest patch's copy instead of its own, so the file holds every stock row and ours.
    if radii_raw and next(iter(radii_raw.values())) and len(next(iter(radii_raw.values()))) != 16:
        raise SystemExit("SpellRadius.dbc rows are not 16 bytes")
    radius_records = [raw for _key, raw in sorted(stock_radius_rows.items())]
    radius_records += [struct.pack("<Ifff", identifier, yards, 0.0, yards) for identifier, yards in sorted(module_radii.items())]
    CLIENT_RADIUS_DBC.write_bytes(struct.pack("<4sIIII", b"WDBC", len(radius_records), 4, 16, 1)
                                  + b"".join(radius_records) + b"\x00")

    # The client's exact-value table. Two fields, id and one string, and the
    # record layout is the one thing in this file no copy in the repository can
    # confirm - the first client run does (report section 5).
    #
    # Every stock row is preserved, the same rule the Spell.dbc and
    # SpellCategory.dbc passes follow. Step 7 ships this file in patch-4.MPQ,
    # and the client reads the highest-numbered patch's copy INSTEAD of its
    # own: a file holding only our rows would take the description variables
    # off every Blizzard spell that uses one - 30 rows, ids 1 to 181 - and one
    # of those, 167, is still pointed at by a donor shell of ours.
    stock_variables = load_dbc("SpellDescriptionVariables.dbc")
    if stock_variables[2] != 2 or stock_variables[3] != 8:
        raise SystemExit("SpellDescriptionVariables.dbc has %d fields of %d bytes, "
                         "expected 2 of 8" % (stock_variables[2], stock_variables[3]))
    stock_block = stock_variables[1]

    def stock_variable_text(record):
        offset = struct.unpack("<I", record[4:8])[0]
        return stock_block[offset:stock_block.index(b"\x00", offset)].decode("utf-8")

    preserved_variables = [(key, stock_variable_text(raw))
                           for key, raw in sorted(stock_variables[0].items())
                           if key < FIRST_VARIABLE_ID]
    taken = {key for key, _text in preserved_variables}
    clash = sorted(taken & {identifier for identifier, _text in variable_rows})
    if clash:
        raise SystemExit("SpellDescriptionVariables.dbc: stock rows %s are ours too" % clash)
    block = bytearray(b"\x00")
    records_out = bytearray()
    rows_out = preserved_variables + list(variable_rows)
    for identifier, text in rows_out:
        offset = len(block)
        block += text.encode("utf-8") + b"\x00"
        records_out += struct.pack("<II", identifier, offset)
    CLIENT_VARIABLES_DBC.parent.mkdir(parents=True, exist_ok=True)
    CLIENT_VARIABLES_DBC.write_bytes(
        struct.pack("<4sIIII", b"WDBC", len(rows_out), 2, 8, len(block))
        + bytes(records_out) + bytes(block))
    print("  wrote client-patch/dbc/SpellDescriptionVariables.dbc "
          "(%d stock rows preserved, %d of ours)"
          % (len(preserved_variables), len(variable_rows)))

    spans = owned_spans([row[0] for row in manifest])
    header = ", ".join(f"`{column}`" for column in columns)
    lines = [
        "-- Generated by mod-diablocraft/scripts/generate/classes/generate_spells.py; do not hand-edit.",
        "-- 02-combat C2/C12: one shell per skill and per skill+rune, plus the passive",
        "-- auras. Primaries use real effects; D3 damage comes from the final provider.",
        "-- AzerothCore layers these over the client's Spell.dbc at startup.",
        "SET NAMES utf8mb4;",
    ] + [f"DELETE FROM `spell_dbc` WHERE `ID` BETWEEN {first} AND {last};" for first, last in spans]
    for offset in range(0, len(rows_sql), 25):
        lines.append(f"INSERT INTO `spell_dbc` ({header}) VALUES")
        lines.append(",\n".join(rows_sql[offset:offset + 25]) + ";")
    sql = "\n".join(lines) + "\n"
    sql += "DELETE FROM spell_script_names WHERE ScriptName='dc_rend_bleed';\n"
    sql += "INSERT INTO spell_script_names (spell_id,ScriptName) VALUES "
    sql += ",".join(f"({row[0]},'dc_rend_bleed')" for row in manifest if row[4] == "bleed") + ";\n"
    ground_ids = [row[0] for row in manifest if (row[4] in ("active", "rune")
                  and (row[1].split(" - ")[0] in GROUND_DOT_SKILLS or row[1] in GROUND_DOT_RUNES)
                  and row[1] not in GROUND_DOT_BLOCKED) or row[4] == "meteor_ground"]
    sql += f"DELETE FROM spell_script_names WHERE ScriptName='{WIZARD_GROUND_SCRIPT}';\n"
    if ground_ids:
        sql += "INSERT INTO spell_script_names (spell_id,ScriptName) VALUES "
        sql += ",".join(f"({spell},'{WIZARD_GROUND_SCRIPT}')" for spell in ground_ids) + ";\n"
    for script in ("dc_wizard_buff", "dc_wizard_slow"):
        sql += f"DELETE FROM spell_script_names WHERE ScriptName='{script}';\n"
        if wizard_scripts.get(script):
            sql += "INSERT INTO spell_script_names (spell_id,ScriptName) VALUES "
            sql += ",".join(f"({spell},'{script}')" for spell in sorted(wizard_scripts[script])) + ";\n"
    # The tick of a gem's damage over time and of Wreath of Lightning's pulse (dc_gem_powers.cpp, dc_gem_tick).
    sql += "DELETE FROM spell_script_names WHERE ScriptName='dc_gem_tick';\n"
    sql += "INSERT INTO spell_script_names (spell_id,ScriptName) VALUES "
    sql += ",".join(f"({row[0]},'dc_gem_tick')" for row in manifest if row[4] in ("gem_dot", "gem_pulse")) + ";\n"
    # The pylon and shrine buffs tell the module when they come or go (dc_pylons.cpp, dc_pylon_buff).
    sql += "DELETE FROM spell_script_names WHERE ScriptName='dc_pylon_buff';\n"
    sql += "INSERT INTO spell_script_names (spell_id,ScriptName) VALUES "
    sql += ",".join(f"({row[0]},'dc_pylon_buff')" for row in manifest if row[4] == "pylon_buff") + ";\n"
    # P2: Conduit's buff and Speed's knock-up aura tick into the module (dc_pylons.cpp, dc_pylon_tick).
    conduit_buff = [int(b["spell_id"]) for b in read_pylon_buffs() if b["kind"] == "conduit"]
    sql += "DELETE FROM spell_script_names WHERE ScriptName='dc_pylon_tick';\n"
    sql += "INSERT INTO spell_script_names (spell_id,ScriptName) VALUES "
    sql += ",".join(f"({spell},'dc_pylon_tick')" for spell in conduit_buff + [PYLON_SPEED_KNOCKUP]) + ";\n"
    sql += f"DELETE FROM spell_group WHERE id={WIZARD_ARMOR_GROUP};\n"
    sql += f"DELETE FROM spell_group_stack_rules WHERE group_id={WIZARD_ARMOR_GROUP};\n"
    if wizard_scripts.get("armors"):
        sql += "INSERT INTO spell_group (id,spell_id) VALUES "
        sql += ",".join(f"({WIZARD_ARMOR_GROUP},{spell})" for spell in sorted(wizard_scripts["armors"])) + ";\n"
        sql += ("INSERT INTO spell_group_stack_rules (group_id,stack_rule,description) VALUES "
                f"({WIZARD_ARMOR_GROUP},{SPELL_GROUP_STACK_RULE_EXCLUSIVE},'Wizard Armors: only one at a time');\n")
    primary_ids = [int(row['spell_id']) for row in primary_rows]
    sql += "DELETE FROM spell_script_names WHERE ScriptName IN ('dc_primary_spell','dc_stupefy','dc_scattering_knockup','dc_pulverize_line');\n"
    sql += "INSERT INTO spell_script_names (spell_id,ScriptName) VALUES "
    sql += ','.join(f"({i},'dc_primary_spell')" for i in primary_ids+list(primary_spells.DAMAGE_SECONDARIES))+';\n'
    sql += f"INSERT INTO spell_script_names (spell_id,ScriptName) VALUES ({primary_spells.KNOCKUP},'dc_scattering_knockup');\n"
    sql += f"INSERT INTO spell_script_names (spell_id,ScriptName) VALUES ({primary_spells.PULVERIZE},'dc_pulverize_line');\n"
    ricochet = next(r['spell_id'] for r in primary_rows if r['rune']=='Ricochet')
    sql += f"DELETE FROM spell_jump_distance WHERE ID={ricochet};\n"
    sql += f"INSERT INTO spell_jump_distance (ID,JumpDistance) VALUES ({ricochet},{primary_mechanics['ricochet_jump_yards']:g});\n"
    sql += ('CREATE TABLE IF NOT EXISTS dc_spell_targeting (spell_id INT UNSIGNED PRIMARY KEY, '
            'target_type VARCHAR(32) NOT NULL, range_kind VARCHAR(8) NOT NULL, '
            'range_yards FLOAT NOT NULL, radius_yards FLOAT NOT NULL, width_yards FLOAT NOT NULL);\n')
    sql += 'DELETE FROM dc_spell_targeting;\n'
    for row in targeting_rows:
        sql += 'INSERT INTO dc_spell_targeting VALUES (' + ','.join(
            escape(value) if isinstance(value, str) else str(value) for value in row) + ');\n'
    ability_ids = [row[0] for row in targeting_rows if row[0] not in primary_ids]
    sql += "DELETE FROM spell_script_names WHERE ScriptName='dc_ability_targets';\n"
    sql += 'INSERT INTO spell_script_names (spell_id,ScriptName) VALUES ' + ','.join(
        f"({spell},'dc_ability_targets')" for spell in ability_ids) + ';\n'

    # Only the values no record field holds exactly (report section 1). Every
    # other number is read from the spell record itself, through the positions
    # and conversions in data/generated/spell_value_map.csv, so no field-backed
    # number has a second, competing home in SQL.
    sql += ('CREATE TABLE IF NOT EXISTS dc_spell_values (spell_id INT UNSIGNED NOT NULL, '
            'token VARCHAR(48) NOT NULL, qualifier VARCHAR(48) NOT NULL DEFAULT \'\', '
            'value DOUBLE NOT NULL, PRIMARY KEY (spell_id, token, qualifier));\n')
    sql += 'DELETE FROM dc_spell_values;\n'
    for offset in range(0, len(exact_rows), 25):
        sql += 'INSERT INTO dc_spell_values (spell_id,token,qualifier,value) VALUES '
        sql += ",".join("(%d,%s,%s,%s)" % (row[0], escape(row[1]), escape(row[2]), row[3])
                        for row in exact_rows[offset:offset + 25]) + ';\n'

    # Step 6: the core installs the shared timer now, and by default it tells
    # the client only about the record that was cast - the category siblings
    # get the cooldown silently (Player.cpp, the `catrec && rec && catrec != rec`
    # argument, and ours are equal). SPELL_ATTR0_CU_FORCE_SEND_CATEGORY_COOLDOWNS
    # makes it send the whole category, which is exactly what the module's own
    # "loop the rune family and build one packet" did before this step.
    sql += "".join("DELETE FROM spell_custom_attr WHERE spell_id BETWEEN %d AND %d;\n" % span for span in spans)
    shared = sorted(row[0] for position, row in enumerate(manifest)
                    if records[position][columns.index("Category")])
    for offset in range(0, len(shared), 40):
        sql += "INSERT INTO spell_custom_attr (spell_id,attributes) VALUES "
        sql += ",".join("(%d,%d)" % (identifier, FORCE_SEND_CATEGORY_COOLDOWNS)
                        for identifier in shared[offset:offset + 40]) + ";\n"

    # Step 6, the category delivery (Architect, 2026-09-20, superseding the
    # server DBC-copy instruction): the core loads SpellCategory.dbc and then
    # overlays the stock `spellcategory_dbc` world table on top of it
    # (DBCStores.cpp:357's LOAD_DBC passes that table name, LoadDBC calls
    # storage.LoadFromDB after the file, and DBCDatabaseLoader::Load grows the
    # index table and merges its rows), so the server needs no copied file.
    # The client still reads its own SpellCategory.dbc, which this writer also
    # emits from the same map - test_spell_categories.py asserts both carry
    # the same eleven rows. Without the rows, SpellInfo::GetCategory answers 0
    # and a rune family has no shared timer at all.
    # The radius rows the module adds (data/spell_radius_rows.csv): the server overlays `spellradius_dbc` on SpellRadius.dbc the same way.
    sql += "DELETE FROM spellradius_dbc WHERE ID >= %d;\n" % FIRST_MODULE_RADIUS_ID
    if module_radii:
        sql += "INSERT INTO spellradius_dbc (ID,Radius,RadiusPerLevel,RadiusMax) VALUES "
        sql += ",".join("(%d,%g,0,%g)" % (identifier, yards, yards) for identifier, yards in sorted(module_radii.items())) + ";\n"
    sql += "DELETE FROM spellcategory_dbc WHERE ID BETWEEN %d AND %d;\n" % (
        min(block.categories[0] for block in CLASS_BLOCKS.values()),
        max(block.categories[1] for block in CLASS_BLOCKS.values()))
    sql += "INSERT INTO spellcategory_dbc (ID,Flags) VALUES "
    sql += ",".join("(%d,%d)" % (category, COOLDOWN_CATEGORY_FLAGS)
                    for _skill, category in sorted(skill_categories.items(),
                                                   key=lambda row: row[1])) + ";\n"

    sql += "DELETE FROM spell_script_names WHERE ScriptName='dc_overpower_axes';\n"
    sql += "INSERT INTO spell_script_names (spell_id,ScriptName) VALUES (" + str(81910 + storm_active - FIRST_SPELL_ID) + ",'dc_overpower_axes');\n"

    GENERATED.mkdir(parents=True, exist_ok=True)
    UPDATES.mkdir(parents=True, exist_ok=True)
    (GENERATED / "spell_shells.sql").write_bytes(sql.encode("utf-8"))
    # Existing migrations are immutable; this full replacement is a new update.
    if "--spell-migration" in sys.argv:
        migration = sys.argv[sys.argv.index("--spell-migration") + 1]
        write_migration(MODULE_ROOT, UPDATES / migration, sql)

    potion_table = (
        "-- Generated by generate_spells.py; the designer's 2026-09-14 Potion decision.\n"
        "CREATE TABLE IF NOT EXISTS dc_character_potion (\n"
        "  guid BIGINT UNSIGNED NOT NULL,\n"
        "  item_entry INT UNSIGNED NULL DEFAULT NULL,\n"
        "  PRIMARY KEY (guid)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n")
    if not targeting_only:
        (GENERATED / "character_potion.sql").write_text(potion_table, encoding="utf-8", newline="\n")
        write_migration(MODULE_ROOT,
                        MODULE_ROOT / "data/sql/db-characters/updates/classes_0003_character_potion.sql",
                        potion_table)

    with (GENERATED / "spell_shells.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["spell_id", "name", "element", "base_spell", "kind"])
        writer.writerows(manifest)

    # --- client Spell.dbc ---------------------------------------------------
    # Same override pass as the SQL above, written as real DBC records so the
    # client can draw and cast the shells. Strings are appended to the end of the
    # stock string block; every string field we do not set points at offset 0,
    # which is the empty string every WDBC starts with.
    header = struct.unpack("<4sIIII", (DBC / "Spell.dbc").read_bytes()[:20])
    stock = (DBC / "Spell.dbc").read_bytes()
    stock_records = stock[20:20 + header[1] * header[3]]
    # The extracted server input may already contain older module shells.
    # Replace our IDs, never append duplicate IDs/names into the client DBC.
    owned = {row[0] for row in manifest}
    stock_records = b''.join(stock_records[i:i+header[3]]
        for i in range(0,len(stock_records),header[3])
        if struct.unpack_from('<I',stock_records,i)[0] not in owned)
    preserved_count = len(stock_records) // header[3]
    block = bytearray(stock[20 + header[1] * header[3]:])
    appended = []
    for values in records:
        record = bytearray(header[3])
        for index in range(len(FMT)):
            kind = FMT[index]
            value = values[index]
            if kind == "s" or isinstance(value, str):
                if value:
                    offset = len(block)
                    block += value.encode("utf-8") + b"\x00"
                else:
                    offset = 0
                struct.pack_into("<I", record, index * 4, offset)
            elif kind == "f":
                struct.pack_into("<f", record, index * 4, float(value))
            else:
                packed = int(value)
                struct.pack_into("<i" if packed < 0 else "<I", record, index * 4, packed)
        appended.append(bytes(record))
    CLIENT_DBC.parent.mkdir(parents=True, exist_ok=True)
    CLIENT_DBC.write_bytes(
        struct.pack("<4sIIII", b"WDBC", preserved_count + len(appended), header[2], header[3], len(block))
        + stock_records + b"".join(appended) + bytes(block))

    counts = {}
    for row in manifest:
        counts[row[4]] = counts.get(row[4], 0) + 1
    summary = ", ".join(f"{counts[kind]} {kind}" for kind in sorted(counts))
    # Architect, 2026-09-20: where a token owns a field, the sheet wins over the
    # value the shell inherited from the spell it was cloned from. Every such
    # change is named here so a review sees it rather than discovers it.
    for identifier, name, field, old, new_value, token, qualifier, value in overrides:
        print("  donor field: %d %s %s %s -> %s (%s%s = %s)" % (
            identifier, name, field, old, new_value, token,
            ":" + qualifier if qualifier else "", value))
    print("  donor fields the sheet took over: %d" % len(overrides))
    print(f"spell records: {len(manifest)} ({summary})")
    print("  ids " + ", ".join("%d-%d" % span for span in spans))
    print("  wrote generated spell SQL; new migration only with --spell-migration")
    print(f"  wrote {CLIENT_DBC.relative_to(REPO_ROOT)} ({preserved_count + len(appended)} records, {CLIENT_DBC.stat().st_size / 1048576:.1f} MB)")
    print("  wrote %s (%d stock rows preserved, %d cooldown categories %d-%d)"
          % (CLIENT_CATEGORY_DBC.relative_to(REPO_ROOT), len(preserved_categories), len(ours),
             min(skill_categories.values()), max(skill_categories.values())))


USAGE = """usage: generate_spells.py [--targeting-only] [--spell-migration NAME] [--ability-migration NAME]

  --targeting-only          refresh targeting data only; keep the client DBC
  --spell-migration NAME    write the full spell_shells render as NAME
  --ability-migration NAME  write the ability tunables render as NAME
  -h, --help                show this message and exit without writing anything
"""


def validate_arguments(arguments):
    """Refuse help, unknown options or a migration flag with no file name
    before any writer runs, so a typo cannot rewrite generated output or an
    applied migration."""
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(0)
        if token in ("--spell-migration", "--ability-migration"):
            if index + 1 >= len(arguments):
                raise SystemExit(f"{token} needs a migration file name\n\n{USAGE}")
            index += 2
            continue
        if token == "--targeting-only":
            index += 1
            continue
        raise SystemExit(f"unknown argument: {token}\n\n{USAGE}")


if __name__ == "__main__":
    validate_arguments(sys.argv[1:])
    main()
    generate_ability_data()
    # Keep the cosmetic wing rows when rebuilding the shared client spell DBC.
    if '--targeting-only' not in sys.argv and (DATA / "wing_variants.csv").is_file():
        from generate_wings import generate as generate_cosmetic_wings
        generate_cosmetic_wings()
    # The chain beam visuals sit on top of the spells and the wings: their
    # SpellVisual/SpellVisualKit/SpellChainEffects rows reference the wing-free
    # table, so they are written after both.
    if '--targeting-only' not in sys.argv and (DATA / "chain_beam_visuals.csv").is_file():
        from generate_chain_beams import generate as generate_chain_beams
        generate_chain_beams()

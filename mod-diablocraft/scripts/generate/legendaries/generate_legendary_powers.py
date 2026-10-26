#!/usr/bin/env python3
"""Emit dc_legendary_power from data/legendary_powers.csv (legendary powers build, beads 1-4: diablocraft-w6ged, -ews9q, -r2jz4, -g0n7f; the rest, one bead a legendary: diablocraft-aa9tm, -mcrtc ...).

The item power table: one row per power effect of an item (owner = its d3_id, pieces blank) or of a set bonus (owner = the set's
name as base_items.csv spells it, pieces = the bonus level 2, 3, 4 or 6); a Bottomless potion (legendary_potions.csv) owns its power the same
way (diablocraft-1z5ye); its power is a row of kind `potion` made from that sheet (`power_id` as the stat, its roll range;
diablocraft-87qlt), read by the potion code, never by the worn-item readers. A row is `kind` `stat`: the item rolls `stat` (an
affix id of its slot's pool) in [value_min, value_max], or, on a set level (pieces set), the set's one fixed number of `stat`, one of
SET_STATS, put on the sheet while the level is worn (N-SETSTAT, diablocraft-wn9q7); `skill`: a number on one skill (`skill`, `stat` from SKILL_STATS,
the (skill, stat) modifier table of bead 2; `skill` may list several skills joined by ';', which share the row's number and its one per-item roll: Oathkeeper's four primaries, diablocraft-kaz5u); `player`: a number on the player (`stat` from PLAYER_STATS, bead 3); `effect`: something done once each time its event fires
(`stat` from EFFECT_STATS, bead 4); or `rune` (bead 5): a rune of `skill` given without choosing it, `stat` the rune's name from
`*_runes.csv` or `all` for every rune of the skill; `element` (legendary build 2 bead 2, diablocraft-li0ie): a number on the
skills of one element, the element named in `skill` (ELEMENTS); or `immune`: the wearer cannot be put under the control `stat`
names, or (`ground_effects`) is not touched by the Desecrator, Molten and Plagued pools (IMMUNITIES, value 1); or `passive` (diablocraft-tt86k): the number `stat` of the passive named in `skill` is raised to the row's
value while the item is worn (PASSIVE_NUMBERS). Any
skill, player or element row may carry a condition (`cond` from CONDITIONS, with `cond_arg` seconds and `cond_skills`, bead 3): the
number is on only while it holds; a stacking condition (`quiet_stacks`) also carries `stack_seconds` and `stack_max` and its number is
per stack. A row may name the event that fires it (`fire_on` from EVENTS, bead 4, with `fire_skills` for a cast, a `chance_pct` per
event and an `icd_seconds`); the condition `triggered` holds for `cond_arg` seconds after it fired. An item-owned row (pieces blank) is one fixed number, or a range the roller rolls once per item (diablocraft-ddnqh). Later beads add stats, conditions and kinds as rows; the table, the set counter and the
tooltip read it the same way. A power with no row is not built: the tooltip shows it inactive.
The table has one migration, legendary_powers_0075_table.sql (a full replace of the table; 0001, 0002, 0004, 0005, 0006, 0007 and 0008 stay as written, 0009 is Stone Gauntlets' first render (diablocraft-ghb4o, may be on dev), 0010 the Bottomless potions' (diablocraft-87qlt) and 0011 the two together (diablocraft-1gctq), all left as written: the newest full replacement is the whole table (each legendary-rest bead takes the next number: 0012 is Might of the Earth's 6-piece (diablocraft-aa9tm), 0013 Ashnagarr's Blood Bracer's (diablocraft-46s0p) 0014 Primordial Soul's (diablocraft-tt86k) 0015 Oathkeeper's (diablocraft-kaz5u) 0016 Starfire's (diablocraft-mcrtc) 0017 Sage's Journey's (diablocraft-xlpqw) 0018 Tasker and Theo's (diablocraft-1cv9k) 0019 The Three Hundredth Spear's (diablocraft-6dzud), 0020 Skull Grasp's (diablocraft-zub4g), 0021 Depth Diggers' (diablocraft-vijvi) and 0022 Hunter's Wrath's (diablocraft-q3ezz), which widens `skill` to VARCHAR(128), 0023 Cain's Destiny's (diablocraft-y3z8a), 0024 Dishonored Legacy's (diablocraft-a2rln) 0025 Immortal King's Call's (diablocraft-14cp4) 0026 The Shame of Delsere's (diablocraft-s5ydk) 0027 Girdle of Giants' (diablocraft-5mn2l) 0028 Deathwish's (diablocraft-zoe00) 0029 Archmage's Vicalyke's (diablocraft-6cw6f), 0030 Halo of Karini's (diablocraft-g8clb), 0031 Arreat's Law's (diablocraft-89un3), 0032 Bastion's Revered's (diablocraft-z6znd), 0033 Blade of the Warlord's (diablocraft-nsbac), 0036 Pride of Cassius' (diablocraft-yep9j), 0037 Mempo of Twilight's (diablocraft-b5p5y), 0038 The Undisputed Champion's (diablocraft-szycu), 0039 Crown of the Primus' (diablocraft-bl9iz), 0040 Dark Mage's Shade's (diablocraft-ohipa), 0041 Light of Grace's (diablocraft-n8eqs), 0042 Cosmic Strand's (diablocraft-vm1q1), 0043 Homing Pads' (diablocraft-9ebp6), 0044 Immortal King's Call's 2- and 4-piece (diablocraft-xf9oy) , 0045 Kyoshiro's Soul's (diablocraft-tvv2b) and 0046 Tzo Krin's Gaze's (diablocraft-08i4q) and 0047 Spirit Guards' (diablocraft-1ays9), 0048 Band of Rue Chambers' (diablocraft-atyj0) and 0049 the Combat legendary fold 1's (Asheara's Vestments 2-piece diablocraft-wn9q7, Vengeful Wind diablocraft-8iwwg, Dovu Energy Trap diablocraft-dxqyr, Might of the Earth 2- and 4-piece diablocraft-tydva, Gesture of Orpheus diablocraft-1i52b), 0050 The Fist of Az'Turrasq's (diablocraft-lxvl2) with Rivera Dancers' (diablocraft-y0bnd), the items legendary fold 1, and 0051 the Combat legendary fold 2's (the stat-only set levels diablocraft-a13xy, Elite Damage Reduction with Aughild's Authority and Blackthorne's Battlegear 3-piece diablocraft-5ozrm) and 0052 the Client legendary fold 1's (Gungdo Gear diablocraft-ph20t, Madstone diablocraft-b1ymb, The Laws of Seph diablocraft-cyzna) and 0053 the World legendary fold's (Crystal Fist diablocraft-9c2kv) and 0054 the UI legendary fold's (Hellrack diablocraft-n8m1a) and 0055 the Combat legendary fold A's (Electrocute's jumps diablocraft-d00zm, Velvet Camaral diablocraft-9l8ka, Fazula's Improbable Chain diablocraft-0la7a, Serpent's Sparker diablocraft-1zocv, Myken's Ball of Hate diablocraft-3j0cg) and 0056 the Combat legendary fold B's (Orb of Infinite Depth diablocraft-anpkx, Jang's Envelopment diablocraft-9qisl, Tal Rasha's Elements diablocraft-fkcp2) and 0057 the Combat legendary fold C's (Rabid Strike diablocraft-6d1jb, Warstaff of General Quang diablocraft-bxfkr, The Flow of Eternity diablocraft-fyi93, Fury of the Vanished Peak diablocraft-e0pt4, Incense Torch of the Grand Temple diablocraft-3jl7t) and 0058 the Combat legendary fold E's (Envious Blade diablocraft-i2d92, Fjord Cutter diablocraft-5i88h, Bul-Kathos's Wedding Band diablocraft-942kn, Standoff diablocraft-r2lly, Bovine Bardiche diablocraft-4p9j9) and 0059 the Combat legendary fold F's (Bracers of Destruction diablocraft-wme53, Lut Socks diablocraft-y27fd, Blackthorne's Battlegear diablocraft-vix14) and 0060 the Classes legendary fold G's (The Crudest Boots diablocraft-x1tg0, Bindings of the Lesser Gods diablocraft-zhizu) and 0071 the Classes legendary fold's (Ancient Parthan Defenders diablocraft-lqe1r, Heart of Iron diablocraft-tgiih, Hexing Pants of Mr. Yan diablocraft-7ksnv)); a migration nobody has shipped is regenerated in place, so there is no 0003).
Contract: docs/contracts/legendary-powers.md.
"""
import csv
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration

MODULE = Path(__file__).resolve().parents[3]
KINDS = ('stat', 'skill', 'player', 'effect', 'rune', 'element', 'immune', 'buff', 'passive')
# N-SETSTAT (diablocraft-wn9q7): the affix ids a set level's `stat` row may name, each one the item affix map (dc_items.cpp Mappings) puts on the
# sheet (Items::RefreshCubedStats reads the rows): the stats of the stat-only set levels (d3planner data_itemsets.js) the map already carries.
SET_STATS = ('resall', 'life', 'vit', 'str', 'dex', 'int', 'edmg', 'gf', 'mf', 'cdr', 'rcr', 'ias', 'expmul', 'regen', 'area', 'edef')
# Kind `buff` (Stone Gauntlets, diablocraft-ghb4o): a number per stack of the owner's stacking buff, which its `stack_buff` effect row puts on
# (a stack per event, at most `stack_max`, all lasting `stack_seconds` from the last). `armor_pct` adds N% armor per stack to the sheet (Percent,
# dc_item_powers.cpp StackSheet), read from the buff aura; `movement_speed_pct` is the per-stack amount of the owner's slow record (a snare,
# generate_spells.py, so control immunity drops it); `attack_speed_pct` multiplies the final attacks per second by
# max(attack_speed_floor_pct/100, 1 + stacks x N/100) while the slow is on (ItemPowers::AttackSpeedFactor), the same control check.
# N-STACKBUFF (Orb of Infinite Depth, diablocraft-anpkx): `damage_dealt_pct` multiplies the player's damage by 1 + stacks x N/100 and
# `damage_reduction_pct` the damage taken by 1 - stacks x N/100, each owner a multiplier of its own (ItemPower::StackedFactor), read from the
# stacks of the owner's record; their N is the item's roll (a range rolls once per item), the others' one fixed number (BuffValue).
# `skill_damage_pct` (Fleshrake) is `damage_dealt_pct` for one skill: the row names the skill, and only that skill's hits take the multiplier
# (ItemPowers::StackedSkillFactor).
BUFF_STATS = ('armor_pct', 'movement_speed_pct', 'attack_speed_pct', 'attack_speed_floor_pct', 'damage_dealt_pct', 'damage_reduction_pct', 'skill_damage_pct')
STACKED_BUFF_STATS = ('damage_dealt_pct', 'damage_reduction_pct', 'skill_damage_pct')
NEGATIVE_BUFF_STATS = ('movement_speed_pct', 'attack_speed_pct')
# Kind `passive` (Primordial Soul, diablocraft-tt86k): raises a number of a class passive (a `*_passive_values.csv` token) to the row's value
# while the item is worn; it never lowers one, and it does not grant the passive. PASSIVE_NUMBERS is what the code reads
# (ItemPowers::PassiveSetTo: Wizard::TargetFactor); a new number is a row here and one reader.
PASSIVE_NUMBERS = (('Elemental Exposure', 'damage_taken_pct'),)
LEVELS = (2, 3, 4, 6)
# The (skill, stat) vocabulary: what the code reads. `damage_increase_pct` multiplies the skill's damage by 1 + N/100 (the
# hit's legendary term); `dot_duration_seconds` sets the length of a skill's bleed (a skill's number of that name in
# *_skill_values.csv), never below its own; `dot_max_stacks` is how many bleeds of the skill one enemy carries (a whole number above 1; the
# skill's own is 1); `dot_payout_seconds` is the time the whole damage of the bleed is dealt in, never above its own length (bead 5);
# `attack_speed_pct` makes the skill's own swing 1 + N/100 times as fast (Bracers of the First Men, li0ie); `summon_attack_speed_pct` makes
# the skill's summons attack 1 + N/100 times as fast, not the player's cast of it (Fury of the Ancients, tab0h; SUMMON_SKILLS: the skills whose
# summons read it); `damage_by_missing_resource_pct` multiplies the skill's damage by 1 + N/100 x the percent of the primary resource missing /100 (a multiplier
# of its own, the hit's legendary term; Dishonored Legacy's Cleave at up to 300-400% by missing Fury, diablocraft-a2rln). `damage_by_resource_spent_pct` multiplies the skill's damage by 1 + N/100 x the primary resource it took / its cap (a multiplier of its own, the hit's legendary
# term), and `resource_spent_cap` is that cap in points, a fixed row beside it: the skill takes up to that much of the resource when it hits (Blade of the Warlord's
# Bash, 40 Fury for up to 400-500%, diablocraft-nsbac; SPENDING_SKILLS: the skills whose provider takes it). `duration_add_seconds` (N-DUR, Pride of Cassius's Ignore Pain, diablocraft-yep9j) lengthens the skill's duration by N seconds (ItemPowers::DurationSeconds; DURATION_SKILLS: the skills whose cast reads it). `follow_caster` makes Slow Time's
# bubble a Slow Time that follows the caster, infinite (value 1, FOLLOW_SKILLS: the Wizard's cast puts the follow record on the Wizard, dc_wizard.cpp Cast; Crown of the Primus, diablocraft-bl9iz); `pierces` (value 1, PIERCE_SKILLS)
# makes the skill's beam hit every enemy on its line, its width the tunable wizard.ray_of_frost_pierce_width_yards (Light of Grace, diablocraft-n8eqs). `idle_stacks_per_second`
# (N-SWSTACK, IDLE_STACK_SKILLS) is how many stacks the skill's vortex gains for each whole second it deals damage to no enemy, a whole number (Kyoshiro's Soul's
# Sweeping Wind, diablocraft-tvv2b; the vortex's tick); `cast_at_enemy` (value 1,
# CAST_AT_SKILLS; N-CASTAT, Tzo Krin's Gaze, diablocraft-08i4q) puts the skill's area where its cast was aimed instead of at the caster (the Wave of Light cast reads it); `mimic_damage_pct` (MIMIC_SKILLS; Rabid Strike, diablocraft-6d1jb) is the percent more damage the copy of a Spirit spender
# that Epiphany's dash teleported deals, cast again on a nearby enemy (Monk::Epiphany::Dash); `cooldown_reduction_pct`
# (N-CD, Gesture of Orpheus's Slow Time, diablocraft-1i52b) shortens the skill's cooldown to 1 - N/100 of what the core's own modifiers leave, each source its own
# multiplier (ItemPowers::CooldownFactor: Combat::SkillCooldownMilliseconds and the cast's cut of the cooldown the core installed), at most 100: 100 leaves no cooldown (Aether Walker's
# Teleport, diablocraft-iv3xg); `cost_add_resource` (N-COST, Aether Walker) puts a cost of N points of the class resource on a skill that has none: a hidden flat SPELLMOD_COST aura per named
# skill (generate_spells.py skill_cost_adders), its amount set on every worn-item change (ItemPowers CostAuras), so the core charges it and refuses a cast the player cannot pay;
# `max_stacks_add` (MAX_STACK_SKILLS)
# is whole stacks the skill holds above its own max_stacks_count (Vengeful Wind's Sweeping Wind, diablocraft-8iwwg); `rune_effect_pct` raises a rune's
# 1 + N/100 (Might of the Earth 4-piece's Iron Impact, diablocraft-tydva; RUNE_EFFECT_SKILLS: Leap's cast and its armor read it, dc_abilities.cpp); `summon_count_add` (ALLY_SKILLS) is whole allies more than the skill's one (The Crudest Boots's second Mystic Ally, diablocraft-x1tg0; Monk::MysticAlly's slots). `cost_reduction_pct` (N-COST,
# Fury of the Vanished Peak, diablocraft-e0pt4) takes N% off the skill's resource cost: a hidden SPELLMOD_COST aura per named skill (generate_spells.py
# skill_cost_modifiers), its amount set on every worn-item change (ItemPowers CostAuras), so no condition or event, at most 100, on a skill whose sheet
# states a cost_resource.
# N-DERIVED `damage_per_movement_speed_pct` multiplies the skill's damage by 1 + N/100 x the sheet's bonus movement speed/100 (Stat::MovementSpeed, a
# multiplier of its own, the hit's legendary term; Standoff's Furious Charge at [400-500]%, diablocraft-r2lly; ItemPowers::DerivedFactor: a new
# `damage_per_<stat>_pct` is a stat here and one pair in its Derived list). A new stat is a row here and one reader in dc_item_powers.cpp.
# Frenzy's three (Bastion's Revered, diablocraft-z6znd), each one fixed whole number: `buff_max_stacks` is how many
# stacks the buff holds (the skill's own is its `max_stacks_count`), `extra_hits_per_stack` how many more times a swing hits per stack held, `chain_yards`
# how far each extra hit reaches around its target, its damage split between them (dc_barbarian_primaries.cpp Landed; ItemPower::ExtraHits, ChainShare).
FRENZY_STATS = ('buff_max_stacks', 'extra_hits_per_stack', 'chain_yards')
PART_STATS = ('explosion_damage_pct',)   # N-SKPART (The Fist of Az'Turrasq, diablocraft-lxvl2): a number on one named PART of a skill, not on the skill's every hit
PART_SKILLS = ('Exploding Palm',)        # the skills whose code reads a part stat: Exploding Palm's on-death explosion (not its bleed), ExplodingPalm::Explode
REUSE_STATS = ('reuse_casts', 'reuse_window_seconds')   # N-CHG (Lut Socks, diablocraft-y27fd): casts of a skill within a window of seconds, before its cooldown begins
REUSE_SKILLS = ('Leap',)                              # the skills whose cast reads them (ItemPowers::Cast, ReuseCast)
# N-LESSER (Ranslor's Folly, diablocraft-5kkgd): a travelling twister periodically pulls in lesser enemies (not elite, not boss, Combat::IsLesser). The three fixed `skill` rows of the item, the power
# file's 'Radius' (the yards from the twister), 'Tickrate' (seconds between pulls) and 'Per Target ICD' (seconds before the same enemy is pulled again), are read together
# (EnergyTwister::Start); each is a fixed number above 0, simply on, for TRAVEL_SKILLS, beside the other two of the same item.
TWISTER_PULL_STATS = ('twister_pull_yards', 'twister_pull_seconds', 'twister_pull_target_cooldown_seconds')
# N-NEXT (Saffron Wrap, diablocraft-5o0j5): `damage_per_enemy_hit_pct` multiplies the damage of the skill's cast by 1 + N/100 x the stacks the skill's last cast left (one per enemy it hit, at most
# `enemy_hit_stacks_max`, kept `enemy_hit_stack_seconds` for the next cast, which spends them: ItemPowers::EnemyStacks, EnemyPress and EnemyHit); the two fixed rows are the item's, beside it.
ENEMY_STACK_STATS = ('damage_per_enemy_hit_pct', 'enemy_hit_stacks_max', 'enemy_hit_stack_seconds')
ENEMY_STACK_SKILLS = ('Overpower',)   # the skills whose code counts the enemies it hits (Overpower's script: dc_barbarian_overpower.cpp)
SKILL_STATS = ('damage_increase_pct', 'dot_duration_seconds', 'dot_max_stacks', 'dot_payout_seconds', 'attack_speed_pct', 'summon_attack_speed_pct',
               'damage_by_missing_resource_pct', 'damage_by_resource_spent_pct', 'resource_spent_cap', *FRENZY_STATS, 'duration_add_seconds', 'follow_caster', 'pierces', 'lasts_until_death', 'idle_stacks_per_second', 'cast_at_enemy', 'resource_generation_pct', 'summon_count_add',
               'cooldown_reduction_pct', 'cost_add_resource', 'max_stacks_add', 'rune_effect_pct', 'mark_split_factor', 'mimic_damage_pct', 'cost_reduction_pct', *PART_STATS, *REUSE_STATS,
               'jump_count_factor', 'start_stacks', 'extra_active_count', 'jump_rehit', 'straight_path', *TWISTER_PULL_STATS, 'damage_per_movement_speed_pct', 'extra_strikes', *ENEMY_STACK_STATS, 'decoy_damage_pct_per_stack', 'damage_by_wind_stacks_pct')
SUMMON_SKILLS = ('Call of the Ancients',)
UNTIL_DEATH_SKILLS = ('Call of the Ancients',)   # `lasts_until_death` (Immortal King's Call 2-piece, diablocraft-xf9oy): value 1, the summoned skill's Ancients stay until they die (Ancients::Summon)
NAMED_CUTS = ('cooldown_cut_named_seconds',)     # N-CDNAMED: an effect that names several skills (`skill` joined by ';') and cuts the running cooldown of each
PIERCE_SKILLS = ('Ray of Frost',)
ALLY_SKILLS = ('Mystic Ally',)   # `summon_count_add` (The Crudest Boots, diablocraft-x1tg0, N-EXTRA): whole allies more than the skill's one (MysticAlly's slots)
MAX_STACK_SKILLS = ('Sweeping Wind',)   # `max_stacks_add` (Vengeful Wind, diablocraft-8iwwg): whole stacks more than the skill's max_stacks_count (the vortex's MaxStacks)
FOLLOW_SKILLS = ('Slow Time',)
RUNE_EFFECT_SKILLS = ('Leap',)  # the skills whose rune code reads `rune_effect_pct` (Iron Impact's armor and duration)
IDLE_STACK_SKILLS = ('Sweeping Wind',)
CAST_AT_SKILLS = ('Wave of Light',)
STRIKE_SKILLS = ('Seven-Sided Strike',)   # `extra_strikes` (N-EXTRA, Lion's Claw, diablocraft-xureo): whole strikes more than the skill's hit_count (SevenSided::Strikes), each of the skill's own size

DECOY_SKILLS = ('Sweeping Wind',)   # `decoy_damage_pct_per_stack` (N-TAUNT, Monkey King's Garb 4-piece, diablocraft-w7wes): each whole second the vortex is up, a decoy beside the last enemy hit taunts and explodes for N% weapon damage a vortex stack (Wind::Decoy)
WIND_STACK_SKILLS = ('Lashing Tail Kick', 'Tempest Rush', 'Wave of Light')   # `damage_by_wind_stacks_pct` (Monkey King's Garb 6-piece): the skills whose damage grows by N% for each stack of the Monk's Sweeping Wind (ItemPowers::PerStackFactor, Monk::WindStacks)
ACTIVE_COUNT_SKILLS = ('Hydra',)   # the skills whose summon reads `extra_active_count` (N-HYDRA, Serpent's Sparker, diablocraft-1zocv: the Wizard's Hydra cap)
TRAVEL_SKILLS = ('Energy Twister',)   # `straight_path` (Valthek's Rebuke, diablocraft-057cl): value 1, the twister wanders no turn at all, a straight line along the aim (EnergyTwister::Start's turn limit of 0)
START_STACKS_SKILLS = ('Archon',)   # `start_stacks` (N-ARCHON, Fazula's Improbable Chain, diablocraft-0la7a): the kill stacks the form starts with (EnterArchon)
JUMP_SKILLS = ('Electrocute',)   # `jump_count_factor` (N-EXTRA, Velvet Camaral, diablocraft-9l8ka): multiplies the enemies the skill's bolt jumps to after the first (Wizard::Jumps)
MIMIC_SKILLS = ('Epiphany',)   # `mimic_damage_pct` (Rabid Strike): the row names the skill whose buff gives the copy (Monk::Epiphany::Dash reads it)
# `resource_generation_pct` multiplies the Spirit a Monk primary generates by 1 + N/100 (Band of Rue Chambers, diablocraft-atyj0). GENERATION_SKILLS: the skills whose
# payment reads it (Monk::SpiritFactor, dc_monk.cpp: Connected's per-attack pay and Crippling Wave - Rising Tide's per-enemy pay).
GENERATION_SKILLS = ('Fists of Thunder', 'Deadly Reach', 'Crippling Wave', 'Way of the Hundred Fists')
DURATION_SKILLS = ('Ignore Pain',)   # the skills whose cast reads `duration_add_seconds` (ItemPowers::DurationSeconds)
SPENDING_SKILLS = ('Bash',)
SPENT_STATS = ('damage_by_resource_spent_pct', 'resource_spent_cap')
BLEED_STATS = ('dot_duration_seconds', 'dot_max_stacks', 'dot_payout_seconds')
# The player stats: `damage_taken_pct` multiplies the damage the player takes by 1 + N/100 (N is -50 for 50% damage
# reduction), one multiplier per active source beside the sheet's armor and resistance factor (Mitigate); `damage_dealt_pct`
# multiplies every hit the player deals by 1 + N/100 (the hit's legendary term, ComputeHit); `damage_reduction_pct` is a positive N that
# multiplies the damage taken by 1 - N/100 (a ranged reduction rolls to its top for a Primal, so it is not a negative damage_taken_pct);
# `cooldown_reduction_seconds` takes N seconds off the cooldown a skill starts (ItemPowers::Cast); `resource_threshold_pct` is the
# primary-resource percent a `resource_above` row of the same item needs, read by nothing else (li0ie; the lower is the better);
# `pet_attack_speed_pct` multiplies the attacks per second of the owner's pets (the Ancients' and the Hydra's swings) by 1 + N/100, one number so a range
# rolls once per item (Tasker and Theo, diablocraft-1cv9k).
# `shield_potency_pct` multiplies every absorb amount a player's own shield sets by 1 + N/100 (ItemPowers::ShieldFactor, read where each
# shield puts its amount: Ashnagarr's Blood Bracer, diablocraft-46s0p); `deaths_breath_pct` multiplies the Death's Breath a drop grants by 1 + N/100
# (ItemPowers::DeathsBreathFactor, read where the loot roll grants it: Sage's Journey 3-piece, diablocraft-xlpqw); `extra_keystone_pct` is the percent chance each Greater Rift Keystone
# a Guardian pays comes with one extra (ItemPowers::KeystoneFactor, read by DC::Loot::ExtraKeystones: Cain's Destiny 3-piece, diablocraft-y3z8a);
# `resource_distance_yards` and `resource_over_cap` are the two fixed numbers of the item's `resource_by_distance` and `resource_refund_by_distance`
# effects (Arreat's Law, diablocraft-89un3): the yards at which the distance share is full, and the points above the resource maximum the gain may go to.
# Nothing but those two effects reads them (ItemPower::OwnerNumber).
DISTANCE_RESOURCE_STATS = ('resource_distance_yards', 'resource_over_cap')
# `fear_enemies` (N-FEAR, Maloth's Focus, diablocraft-kxdwe) is the item's one fixed number of seconds the enemies within `fear_yards` of the wearer flee in stock Fear
# (the power file's 'Fear Duration' and 'Target Area Distance'), fired by the `tick` clock: `icd_seconds` is its cooldown (the file's 'Cooldown Duration'), and after a proc the
# next one waits up to `fear_cooldown_delta_seconds` more, rolled each time (the file's 'Cooldown Delta'). The two fixed `player` rows FEAR_STATS sit beside it.
FEAR_STATS = ('fear_yards', 'fear_cooldown_delta_seconds')
# The Butcher's Sickle's fixed numbers (see the `pull_enemy` effect, below): the farthest enemy it drags, the stun, the cooldown.
PULL_STATS = ('pull_yards', 'pull_stun_seconds', 'pull_cooldown_seconds', 'pull_damage', 'pull_damage_delta')
# Wall of Man's fixed numbers (see the `bone_shield` effect, below): the seconds the shield lasts and the wait after one.
BONE_SHIELD_STATS = ('bone_shield_seconds', 'bone_shield_cooldown_seconds')
# `town_portal_bubble_pct` is the percent off the damage a Town Portal cast takes (ItemPower::PortalBubbleFactor, read by the PortalDamage hook in rifts/dc_town_portal.cpp:
# the damage scaled by 1 - N/100, and the cast goes on instead of being cancelled; Homing Pads, diablocraft-9ebp6): an item's own percent below 100, a range rolls once.
# `stun_duration_pct` stretches every stun the player applies by 1 + N/100 (ItemPowers::StunFactor: the stun auras' durations in OnCalcMaxDuration and
# each site that sets a stun's seconds itself; Dovu Energy Trap, diablocraft-dxqyr): an item's own percent, a range rolls once.
# `shrine_seconds` (N-PYLONDUR, Gloves of Worship, diablocraft-4y1jn) is the seconds every shrine effect lasts, the power file's 'Shrine Buff Duration' (ItemPowers::ShrineSeconds, read by
# Pylons::Give for a shrine, never a pylon): the highest of the worn items' numbers when it is more than the shrine's own, an item's one fixed number, simply on.
# `event_distance_yards` is the yards an event of the same item must be farther than (ItemPower::MinYards in Fire), one fixed number beside an event row.
# Tal Rasha's Elements. `hit_element` is a hit of one of SET_ELEMENTS, fired with the element's name where a skill fires with its name, so
# a row's `fire_skills` lists the elements (ItemPowers::HitElement). Its effects: `element_resist` (4-piece) puts the row's number as a percent on every resistance
# for `stack_seconds` from each attack of the element, one buff per element; `element_window` (6-piece) opens or moves the window the set's `damage_dealt_pct`
# row holds under (the condition `element_window`): `stack_seconds` long, `stack_max` stacks (elements) before the extending starts, extended by the set's two
# fixed `player` rows ELEMENT_WINDOW_STATS (seconds per extension, the most all extensions add up to); `element_meteor` (2-piece) drops a Meteor of the element
# and gives immunity to it (the tunable wizard.tal_rashas_elements_immunity_seconds).
SET_ELEMENTS = ('arcane', 'cold', 'fire', 'lightning')
# `taken_element` (N-SCHOOLEV, Krede's Flame, diablocraft-z1q6q) is a hit on the player of one of SET_ELEMENTS, fired with the element's name where a skill fires with its name
# (ItemPowers::TakenElement, from Passives::Taken, after the defence, before the hit is dealt), the Life it takes handed on beside it. Its one effect, `resource_per_life_lost_pct`, gives the
# class's primary resource: the row's number is the percent of the resource's maximum for each 1% of the maximum Life the hit took (the power file's 'Resource % Gain Per 1% HP Lost').
ELEMENT_EFFECTS = ('element_resist', 'element_window', 'element_meteor')
ELEMENT_WINDOW_STATS = ('element_extend_seconds', 'element_extend_max_seconds')
# `slow_seconds` is the length of the item's `slow_pct` effect, one fixed number beside it.
# `crit_chance_pct` (N-CRIT, Envious Blade) is critical hit chance in percentage points added to a hit's chance before it is clamped to certain
# (ItemPowers::CritBonus, read in ComputeHit); the condition `target_life_at_least` (N-TLIFE) holds while the target's Life is at least `cond_arg` percent of its maximum.
# `life_regen` is Life Regeneration per second, a flat number put on the sheet's Life Regen as a Temporary contribution (dc_item_powers.cpp StandStill; Boots of
# Disregard, diablocraft-odu01): per stack of its `standing_still` condition.
# `block_chance_pct` (N-BLOCK, Blood Brother) is Block Chance in percentage points added to the sheet's when a hit on the wearer rolls its block (ItemPowers::BlockBonus, read in
# Mitigate and held to the sheet's total cap); `blocked_damage_cut_pct` is the percent a blocked hit is cut by before the shield's flat Block Amount (ItemPowers::BlockedFactor).
# `damage_reduction_per_stunned_pct` (N-TCTRL, Ancient Parthan Defenders, diablocraft-lqe1r) multiplies the damage taken by 1 - N/100 for each stunned enemy within `stunned_radius_yards` of the
# wearer (ItemPower::StunnedReduction, read in ItemPowers::IncomingFactor), each enemy a multiplier of its own; the count is taken by the update hook once per `stunned_check_seconds`
# (StunScan). The two STUN_STATS are the item's fixed numbers, simply on, beside it and read by nothing else.
STUN_STATS = ('stunned_radius_yards', 'stunned_check_seconds')
# `damage_generation_pct` and `damage_generation_cut_pct` (N-MOVE, Hexing Pants of Mr. Yan, diablocraft-7ksnv) are a number on the wearer's damage AND on the primary resource
# a class pays itself, both at once: +N or -N in the additive pool of the hit (ItemPowers::DamageBonus, step 4 of damage_formula.csv, the DIBS bucket) and a multiplier
# 1 + N/100 or 1 - N/100 on the resource generation (ItemPowers::GenerationFactor, read where each class pays its generation). The cut is the positive number the item's text states;
# the lower is the better (ItemPower::Best). They carry the conditions `moving` and `not_moving`.
GENERATION_STATS = ('damage_generation_pct', 'damage_generation_cut_pct')
# `thorns_per_vitality_pct` (N-DERIVED, Heart of Iron, diablocraft-tgiih) gives the sheet's Thorns N% of its Vitality, a flat Thorns source (VitalityThorns, the update hook: a Temporary
# contribution of the sheet's Thorns, redone when the number changes); the sheet's Thorns bonuses multiply it after. An item's number, simply on.
# `resource_cost_reduction_pct` (N-COST, Pride's Fall, diablocraft-pruc8) takes N% off every resource cost while its condition holds: the sheet's Resource Cost Reduction gains a Temporary flat contribution
# (NoDamageCost, the update hook) that the class's gear cost aura is rebuilt from. `life_regen_by_missing_pct` (N-PLIFE, Rogar's Huge Stone, diablocraft-sifvi) raises the sheet's Life Regen by N% x the percent of Life missing / 100
# (MissingLifeRegen, a Temporary Percent contribution looked at once per the item's fixed `life_regen_tick_seconds`). `own_life_threshold_pct` (Shi Mizu's Haori, diablocraft-tudh9) is the Life percent the item's
# `own_life_below` row compares with, the higher the better.
LIFE_REGEN_STATS = ('life_regen_by_missing_pct', 'life_regen_tick_seconds')
NEW_PLAYER_STATS = ('resource_cost_reduction_pct', 'own_life_threshold_pct') + LIFE_REGEN_STATS
PLAYER_STATS = ('life_regen', 'damage_taken_pct', 'damage_dealt_pct', 'damage_reduction_pct', 'cooldown_reduction_seconds', 'resource_threshold_pct', 'life_threshold_pct', 'town_portal_bubble_pct', 'stun_duration_pct', 'shield_potency_pct', 'deaths_breath_pct', 'pet_attack_speed_pct', 'extra_keystone_pct', 'event_distance_yards', 'slow_seconds', 'shrine_seconds', 'crit_chance_pct', 'block_chance_pct', 'blocked_damage_cut_pct', 'damage_reduction_per_stunned_pct', 'thorns_per_vitality_pct', 'movement_speed_pct', 'damage_reduction_of_block_pct', 'damage_vs_impaired_pct') + NEW_PLAYER_STATS + STUN_STATS + GENERATION_STATS + DISTANCE_RESOURCE_STATS + ELEMENT_WINDOW_STATS + FEAR_STATS + PULL_STATS + BONE_SHIELD_STATS
POSITIVE_PLAYER_STATS = ('life_regen', 'damage_reduction_pct', 'cooldown_reduction_seconds', 'resource_threshold_pct', 'life_threshold_pct', 'town_portal_bubble_pct', 'stun_duration_pct', 'shield_potency_pct', 'deaths_breath_pct', 'pet_attack_speed_pct', 'extra_keystone_pct', 'event_distance_yards', 'slow_seconds', 'shrine_seconds', 'crit_chance_pct', 'block_chance_pct', 'blocked_damage_cut_pct', 'damage_reduction_per_stunned_pct', 'thorns_per_vitality_pct', 'movement_speed_pct', 'damage_reduction_of_block_pct', 'damage_vs_impaired_pct') + NEW_PLAYER_STATS + STUN_STATS + GENERATION_STATS + DISTANCE_RESOURCE_STATS + ELEMENT_WINDOW_STATS + FEAR_STATS + PULL_STATS + BONE_SHIELD_STATS
# `movement_speed_pct` (N-PSPD, Irontoe Mudsputters) is movement speed put on the sheet while the row holds: under `life_missing` it is the number per 1% of Life
# missing, kept as a Temporary contribution that is looked at again every `combat.item_power_speed_look_seconds` (ItemPowers MovementSpeed).
# `damage_reduction_of_block_pct` (N-DERIVED, Justice Lantern) is damage reduction equal to N percent of the player's Block Chance: the damage taken is multiplied by
# 1 - N x B/10000, B the Block Chance now in percent (the sheet's with what the worn items add, under the same cap), a multiplier of its own beside armor and
# resistance; a share (up to 100), always on, read in ItemPowers::IncomingFactor.
# `damage_vs_impaired_pct` (N-TCTRL, Krysbin's Sentence) is N percent increased damage against a slowed enemy, and triple N against an enemy under any other
# control-impairing effect (a stun, a freeze, a root, a fear ...): its own multiplier on the hit, read with the target (ItemPowers::TargetFactor); always on.
# The elements a skill's hit has (the shells' `element`, dc_combat.cpp SchoolOf) and what a row of kind `element` does to the skills of one:
# `damage_pct` adds N to the hit's elemental bonus (the additive:elemental bucket, beside the sheet's `dmg<element>`); `cost_reduction_pct`
# takes N% off the resource cost of the skills of that element, through the class's hidden cost aura of that element (generate_spells.py,
# dc_item_powers.cpp CostAuras; Cindercoat, diablocraft-5cqu3). The aura is set when the worn items change, so that row has no condition.
ELEMENTS = ('physical', 'fire', 'cold', 'lightning', 'poison', 'arcane', 'holy')
# `damage_per_distance_pct` (Starfire, diablocraft-mcrtc): the hits of that element are multiplied by 1 + N x steps / 100 (its own multiplier, the hit's
# legendary term), steps the whole `distance_step_yards` in the yards to the target, cut at `distance_cap_yards`; the item rolls N, and the step and the
# cap are its two fixed rows (the item's text words both), read by that row alone.
PREVENT_STATS = ('damage_prevented_pct', 'heal_of_prevented_pct')   # N-PREVENT (Countess Julia's Cameo, diablocraft-sjdct): the share of an element's damage taken that is prevented, and the share of the prevented amount that heals
PREVENT_ELEMENTS = ('arcane', 'cold', 'fire', 'lightning')   # the elements a hit's school maps to (ItemPowers' ElementOfSchool)
ELEMENT_STATS = ('damage_pct', 'cost_reduction_pct', 'damage_per_distance_pct', 'distance_step_yards', 'distance_cap_yards', *PREVENT_STATS)
DISTANCE_STATS = ('damage_per_distance_pct', 'distance_step_yards', 'distance_cap_yards')
# The controls an `immune` row keeps off the wearer (dc_item_powers.cpp Immunize): `freeze` and `root` (D3's Immobilize).
IMMUNITIES = ('freeze', 'root', 'ground_effects')   # `ground_effects`: World's N-BLACKTHORNE mark (DC::Rifts::SetGroundEffectImmune; Blackthorne's Battlegear 4-piece, diablocraft-vix14)
# The effects a fired `effect` row does (ItemPowers::Fire): `cooldown_cut_seconds` takes N seconds off the running cooldown of one skill,
# picked at random; `frenzy_stacks` sets Frenzy's buff to N stacks; `apply_skill` (names its skill, bead 5) applies the skill's bleed to the
# target of the event that fired it (APPLY_SKILLS: what the code can apply; Exploding Palm's palm through Monk::Apply, N-APPLYAURA, diablocraft-ph20t); `resource_refund` gives N points of the class's primary
# resource (The Gavel of Judgment's 25 Fury, diablocraft-2z25c); `stack_buff` adds N stacks to the owner's `buff` rows' auras (at most
# `stack_max`, lasting `stack_seconds`, refreshed by each event: Stone Gauntlets, ghb4o); `resource_by_distance` gives up to N points of it by the
# yards to the enemy hit, above the resource maximum by `resource_over_cap`, and `resource_refund_by_distance` takes that extra maximum off again and
# refunds up to N points by the same yards (Arreat's Law, diablocraft-89un3); both are fired on a `hit` and need the item's two
# DISTANCE_RESOURCE_STATS rows; `multiply_image` (Archmage's Vicalyke, diablocraft-6cw6f)
# puts one more Mirror Image where a killed one stood, with the dead one's remaining time; its chance is the designer's tunable
# wizard.archmages_vicalyke_multiply_chance_pct (the executor reads it, so the row carries no chance_pct) and it is fired by `image_death` alone;
# `cast_skill` (Dark Mage's Shade, diablocraft-ohipa) casts its `skill` as the player by code (Combat::CastSkill, a triggered cast of the bar's rune), its number the
# internal cooldown in seconds, and is fired by `life_below` (the Life falling from the item's `life_threshold_pct` level to under it) or by `land`
# (Might of the Earth 4-piece's Earthquake where Leap lands, diablocraft-tydva: a set row, number 0, the text stating no cooldown) or by
# `taken` (Vigilance's Inner Sanctuary, diablocraft-115jg: an item row with the chance_pct of being hit, the only cast_skill row with one) or by
# `hit_spender` of the skills it names (Won Khim Lau, diablocraft-vbm0q: an item row, number 0, its cooldown the tunable monk.won_khim_lau_cooldown_seconds).
# `mark_enemy` (Bindings of the Lesser Gods, diablocraft-zhizu) marks the enemy of the hit that fired it for `stack_seconds`: the enemy takes N% more
# damage from the player's `skill` (a debuff record in data/legendary_power_buffs.csv, kind `mark`, the N stored in the aura; ItemPowers::MarkFactor).
# `mark_split_factor` (a skill row on the marked skill) multiplies N for the hits of that skill's Fire Ally bombs.
# `drain_life` (Bul-Kathos's Wedding Band) takes N percent of each nearby enemy's maximum Life and heals the player what it took,
# on the `tick` clock (ItemPowers Drain; the reach and the two caps are the combat tunables bul_kathos_drain_*): an item's one fixed number.
# `summon_herd` (Bovine Bardiche, N-SUMMON) calls N cows (one whole number) beside the player, fired on a `hit` of ANY skill (no
# fire_skills); its chance, internal cooldown and the cows' numbers are the combat tunables bovine_bardiche_* the executor reads
# (ItemSummons::Herd), so the row carries no chance_pct or icd_seconds, and its damage needs the item's `hit` record in legendary_power_buffs.csv.
# N-STUN (Hellrack, diablocraft-n8m1a): a control effect puts a stock control aura on the enemy the hit struck for N seconds (dc_item_powers.cpp Control;
# ItemPower::ControlSpell names the aura): `root_seconds` a root. An item's one fixed number, fired on a `hit` and never on a control event, which the
# root itself raises (it would fire itself again). A new control is a row here and one aura in ControlSpell.
# `charm_seconds` (N-CHARM, The Tormentor, diablocraft-a3ycm) charms the enemy the hit struck for N seconds (CharmEffect::Apply: the shared charm of Combat, a monster that fights
# for the player): the same shape, an item's one fixed number on a `hit`, its chance_pct the item's own fraction and its icd_seconds the power file's cooldown.
CONTROL_EFFECTS = ('root_seconds', 'charm_seconds', 'stun_seconds')
# The condition `first_hit_on_target` (N-MARK, Madawc's Sorrow, diablocraft-ggvdt) is a `stun_seconds` effect row's: it fires only on the first hit this player lands on that creature
# (ItemPower::FirstHit over the creature's mark of the players who have hit it).
# `heal_missing_life_pct` (N-HEAL, Vambraces of Sescheron, diablocraft-uovwz) heals the player for N percent of the Life missing (a range rolls once per item), fired by `hit_generator`
# (a cast that hit, once, not per enemy) of the skills it names: an item's, with no chance_pct, icd_seconds, condition or set level (ItemPowers heals as a stock heal record).
# `bone_shield` (N-ABSGRANT, Wall of Man, diablocraft-44hz9, diablocraft-upwsv) protects the player when a monster's hit lands: the number is the item's chance in percent (a range rolls once
# per item), fired on `taken`, so the row carries no chance_pct or icd_seconds. The fixed `player` rows BONE_SHIELD_STATS are the protection's seconds and the cooldown after one (the
# executor keeps the cooldown, so a failed roll starts none); while it lasts every hit taken is smaller by the item's fixed `buff` `damage_reduction_pct` row (read from the stacks of the
# item's `damage_reduction_pct` record in data/legendary_power_buffs.csv, a dummy aura the executor puts on for the seconds).
# `slow_pct` (N-MONSLOW) slows the enemy the hit struck by N% (below 100; a range rolls once per item) for the item's
# fixed `slow_seconds` (a player row beside it, read by nothing else: ItemPower::OwnerNumber), through a stock snare (dc_item_powers.cpp Slow); fired on a hit of
# named skills, an item's, no condition.
SLOW_EFFECTS = ('slow_pct',)
# `proc_damage` (Storm Crow, N-WPROC) casts a ball of an element at the enemy the hit struck: the number is the item's chance in percent (a range rolls once per
# item), fired on a `hit` of ANY skill (no fire_skills); the ball's percent of weapon damage is a combat tunable the executor reads (ItemProc::Damage), so the row carries
# no chance_pct or icd_seconds, and the ball is dealt under the item's `hit` record in legendary_power_buffs.csv (its element is that record's).
PROC_EFFECTS = ('proc_damage',)
# `pull_enemy` (N-PULLFX, The Butcher's Sickle, diablocraft-v052u) drags the enemy a hit struck to the wearer: the number is the item's chance in percent (a range rolls once
# per item), scaled by the hit's proc coefficient, fired on a `hit` of ANY skill (no fire_skills). The power file's other numbers are the item's fixed `player` rows
# PULL_STATS: `pull_yards` (the farthest an enemy is dragged from), `pull_stun_seconds` (the stun it is held in), `pull_cooldown_seconds` (the wait after a drag) and
# `pull_damage` with `pull_damage_delta` (the hook's damage, from the minimum to the minimum plus the delta: the power file's Table(LegendaryProcDmg, 59) / 5, data/d3/legendary_proc_dmg_table.csv); the
# executor keeps the cooldown itself (a failed roll does not start it), so the row carries no chance_pct or icd_seconds (ItemPowers::Drag).
# `revive_full` (Ancestors' Grace, N-FATAL, diablocraft-omfd8) saves the wearer from a hit that would kill: the hit deals nothing, Life and every resource of the class go to
# their maximum and the worn item is destroyed (ItemPowers::Fatal -> Revive); it is an item's one fixed 1, fired by the event `fatal` (the hit takes the whole of the Life left or more)
# and by nothing else; it rolls nothing and waits for nothing, so the row carries no chance_pct, icd_seconds, condition or skill.
# `burn_trail` (Fire Walkers, N-AREA) burns the ground the wearer walks on: the number is the percent of weapon damage per second the fire deals
# to an enemy standing in it (a range rolls once per item). It is fired by the `tick` clock, whose `icd_seconds` is the interval the fire is dropped at
# while the wearer moves (ItemTrail::Drop); how long a patch burns and how far it reaches are the combat tunables fire_walkers_*, and the damage is
# dealt under the item's `hit` record in legendary_power_buffs.csv (ItemTrail::Burn), so the row has no chance_pct, skill, condition or set level.
# `random_shrine` (Ahavarion, N-PYLON) puts N random shrine buffs (one whole number) on the player (Pylons::GiveRandomShrine: a random one of the shrines, for
# its own seconds); its chance is the combat tunable ahavarion_chance_pct the executor reads, so the row carries no chance_pct or icd_seconds.
# `next_attack_pct` (N-BLOCK, Blood Brother) arms the wearer's next attack with N percent more damage until an attack connects (ItemPowers::ArmNextAttack, spent in
# NextAttackConnected); it is fired by `block`, and its record in legendary_power_buffs.csv is the aura that shows it is armed.
# `cost_free_seconds` (N-COST, Kekegi's Unbreakable Spirit, diablocraft-hk2xg) makes every ability cost nothing for N seconds (ItemPowers::OpenCostFree:
# the core's costs through the class's gear cost aura, the module's own through ItemPowers::CostFree); an item's, fired on a `hit` of any skill with its chance.
EFFECT_STATS = ('next_attack_pct', 'burn_trail', 'revive_full', 'cooldown_cut_seconds', 'frenzy_stacks', 'apply_skill', 'resource_refund', 'stack_buff', 'multiply_image', 'resource_by_distance', 'resource_refund_by_distance', 'cast_skill', 'mark_enemy', 'summon_herd', 'random_shrine', 'drain_life', 'cost_free_seconds', 'resource_per_life_lost_pct', 'fear_enemies', 'pull_enemy', 'heal_missing_life_pct', 'bone_shield', *NAMED_CUTS, *CONTROL_EFFECTS, *PROC_EFFECTS, *SLOW_EFFECTS, *ELEMENT_EFFECTS, 'thorns_on_attack_pct')
DISTANCE_EFFECTS = ('resource_by_distance', 'resource_refund_by_distance')
APPLY_SKILLS = ('Rend', 'Exploding Palm')
# The events (dc_item_powers.h): a player's cast of a skill, a hit of a spender or of a generator or primary, a kill, a kill of an elite,
# a hit taken; `hit` is every hit of a skill, named by `fire_skills` (bead 5); `image_death` is a Mirror Image killed by an enemy of its owner
# (ItemPowers::ImageDied, the Image's own AI; never a despawn); `storm_armor_shock` is Storm Armor electrocuting an enemy
# (its tick or Shocking Aspect's shock), whose distance an item's `event_distance_yards` row bounds (Halo of Karini, diablocraft-g8clb); `resource_spent`
# is Fury spent (Abilities::Spent -> ItemPowers::Spent), fires only the named cooldown cut, once per whole step of the row's `per_resource_spent` cond_arg points (N-SPENT);
# `land` is a cast that moved the player landing (Leap, ItemPowers::Landed), named by `fire_skills` (diablocraft-tydva).
# `explosion` is a skill's on-death explosion reaching an enemy, before its damage (ItemPowers::Exploded; EXPLODING_SKILLS name the skills whose code fires it,
# and `fire_skills` names the skill: Gungdo Gear's Exploding Palm, diablocraft-ph20t).
# A `hit` names its skills, but a control effect's may name none: a hit of every skill (Hellrack, diablocraft-n8m1a). `control_<kind>` (N-STUN) is a control aura the
# player put on a monster, any skill's or item's, the monster its target (dc_item_powers.cpp ControlEvents; ItemPower::ControlEvent names the kind).
# `fatal` (N-FATAL) is a hit that would take all the Life the player has left (ItemPowers::Fatal, the damage hook, before the hit is dealt); it fires `revive_full` and nothing else.
# `block` (N-BLOCK, Blood Brother) is a hit on the wearer that rolled its block (ItemPowers::Blocked, from Mitigate), the attacker its target; no fire_skills.
# `tick` is the clock (N-CLOCK): asked on every player update, a row fires once per its `icd_seconds` (the period, above 0) while
# it is worn; it fires effect rows only, with no chance_pct.
CONTROL_EVENTS = ('control_stun', 'control_freeze', 'control_blind', 'control_root')
EVENTS = ('cast', 'hit', 'hit_spender', 'hit_generator', 'kill', 'kill_elite', 'taken', 'image_death', 'storm_armor_shock', 'life_below', 'fatal', 'resource_spent', 'land', 'explosion', 'tick', 'hit_element', 'block', 'chest', 'taken_element', *CONTROL_EVENTS)
NAMED_EVENTS = ('cast', 'hit', 'land')   # the events that need fire_skills
EXPLODING_SKILLS = ('Exploding Palm',)
# The conditions (dc_item_power_math.h Holds): `channel_or_after` holds while any of `cond_skills` is channelled and for
# `cond_arg` seconds after it ends; `channel_held` while any of them has been channelled for `cond_arg` seconds. `quiet_stacks` is a stack per `stack_seconds` since the item was put on or, after the player
# took damage, since `cond_arg` seconds after that damage, at most `stack_max`; the row's number is per stack.
# `standing_still` (N-MOVE, Boots of Disregard, diablocraft-odu01) is a stack per `stack_seconds` the player has stood still while the item was worn, at most `stack_max`, all lost
# the moment the player moves; the row's number is per stack, and it takes no `cond_arg`.
# `triggered` holds for `cond_arg` seconds after the row's event fired (bead 4). `skills_active` holds while every one of `cond_skills` is
# active (its buff on the player, or its summons alive); `resource_above` while the primary resource is at least the item's own
# `resource_threshold_pct` percent of its maximum (li0ie). Neither takes `cond_arg`. `enemies_hit_at_most` is the one condition of an
# effect row (2z25c): it fires only when the cast that fired it hit at least one and at most `cond_arg` enemies (ItemPower::Fire), so its
# `element_window` holds while the set's 6-piece window is open (an `element_window` effect row of the same owner and level opens it; Tal Rasha's Elements); it takes no `cond_arg`.
# event is a cast that hit (`hit_spender`, `hit_generator`), whose caller counts the enemies (Combat::Connected). `per_resource_spent` is the other:
# the one condition of the named cooldown cut, `cond_arg` the points of the resource per step (a whole number), Holds never reads it.
# `target_slowed` (N-TCTRL, Fjord Cutter) holds while the hit's target carries a slow (a Chill is one): a skill's
# `damage_increase_pct` only, read on the hit with its target (ItemPowers::TargetFactor), no cond_arg or cond_skills.
# `first_hits` (N-NHIT, Bracers of Destruction, diablocraft-wme53) holds for a hit among the first `cond_arg` enemies (a whole number) its cast
# hits, nearest first (ItemPowers::HitPlace, set by Combat's ResolveCast); it is a skill's `damage_increase_pct` row's, the one stat read while the hit is computed.
# `per_prior_hit` (N-NHIT, Vile Ward, diablocraft-s8lut) scales the row's number by the enemies its cast has already hit when the hit is computed (the hit's place
# among the cast's hits, nearest first, less one: the first hit takes none, the 4th three of them), read while the hit is computed (ItemPowers::HitPlace, set by Combat's
# ResolveCast); a skill's `damage_increase_pct` row's, no cond_arg, cond_skills or event.
# `life_missing` (N-PLIFE, Lornelle's Sunstone) scales the row's number by the percent of Life the player is missing (the number is "per 1% Life
# missing"), read when the number is read; a `player` or `skill` row, no cond_arg, cond_skills or event; a damage reduction or damage taken
# row must stay below 100% at 100% missing.
# `target_creature_type` (N-CTF, Ahavarion) is an effect row's: it fires only when the enemy the event is about is of one of the creature types its
# `cond_skills` name (CREATURE_TYPES, WoW's, as ItemPower::CreatureTypes spells them), on an event that hands over its enemy (CREATURE_EVENTS: the killed
# creature, the enemy a skill hit); no cond_arg.
# `standing_still` (N-MOVE, Boots of Disregard, diablocraft-odu01) is a stack per `stack_seconds` the player has stood still while the item was worn, at most `stack_max`, all lost
# the moment the player moves; the row's number is per stack, and it takes no `cond_arg`.
# `moving` and `not_moving` (N-MOVE, Hexing Pants of Mr. Yan, diablocraft-7ksnv) hold while the player is moving (Unit::isMoving, read when the number is read) or is not: a `player` row's, an item's or a set
# level's, with no cond_arg, cond_skills, stack numbers or event.
# `cast_enemies_at_most` (N-NHIT, Skular's Salvation, diablocraft-cnc98) holds for a hit whose cast hits at least one and at most `cond_arg` enemies (a whole
# number) in all (ItemPowers::CastEnemies, set by Combat's ResolveCast and the Boulder Toss burst); like `first_hits` it is a skill's `damage_increase_pct` row's.
# A skill row's `skill` may be one rune of a skill, "Skill - Rune" (RUNE_JOIN; the rune a *_runes.csv sheet lists for the skill): the row is read only for the
# hits of that rune, beside the skill's own rows (ComputeHit reads the hit's "skill - rune" name too); it is a single name and a `damage_increase_pct` row's.
RUNE_JOIN = ' - '
STACKING = ('quiet_stacks', 'standing_still')
# `no_damage_for` (N-COST, Pride's Fall, diablocraft-pruc8) holds once the player has taken no damage for `cond_arg` seconds, counted from the later of the moment the item went on and the last damage taken: an item's
# `player` row, with no cond_skills or event. `own_life_below` (Shi Mizu's Haori, diablocraft-tudh9) holds while the player's Life is below the item's own `own_life_threshold_pct` (its stored roll): an item's
# `player` row, with the threshold row of the same item and no cond_arg, cond_skills or event.
# `cast_enemies_at_most` (N-NHIT, Skular's Salvation, diablocraft-cnc98) holds for a hit whose cast hits at least one and at most `cond_arg` enemies (a whole
# number) in all (ItemPowers::CastEnemies, set by Combat's ResolveCast and the Boulder Toss burst); like `first_hits` it is a skill's `damage_increase_pct` row's.
# A skill row's `skill` may be one rune of a skill, "Skill - Rune" (RUNE_JOIN; the rune a *_runes.csv sheet lists for the skill): the row is read only for the
# hits of that rune, beside the skill's own rows (ComputeHit reads the hit's "skill - rune" name too); it is a single name and a `damage_increase_pct` row's.
RUNE_JOIN = ' - '
STACKING = ('quiet_stacks', 'standing_still')
CONDITIONS = ('channel_or_after', 'channel_held', 'quiet_stacks', 'standing_still', 'triggered', 'skills_active', 'resource_above', 'enemies_hit_at_most', 'per_resource_spent', 'element_window', 'target_life_at_least', 'target_slowed', 'first_hits', 'cast_enemies_at_most', 'per_prior_hit', 'life_missing', 'target_creature_type', 'moving', 'not_moving', 'no_damage_for', 'own_life_below', 'first_hit_on_target')
COUNTED_EVENTS = ('hit_spender', 'hit_generator')
UNTIMED = ('skills_active', 'resource_above', 'standing_still', 'element_window', 'target_slowed', 'per_prior_hit', 'life_missing', 'target_creature_type', 'moving', 'not_moving', 'own_life_below', 'first_hit_on_target')
CREATURE_TYPES = ('beast', 'dragonkin', 'demon', 'elemental', 'giant', 'undead', 'humanoid', 'critter', 'mechanical', 'not_specified', 'totem', 'non_combat_pet', 'gas_cloud')
CREATURE_EVENTS = ('kill', 'kill_elite', 'hit')


def read(module, name):
    with (module / name).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream, strict=True))


def rows(module=MODULE):
    """[(owner, pieces, kind, skill, stat, min, max, cond, arg, cond_skills, stack_seconds, stack_max, fire_on, fire_skills, chance, icd)] in sheet order, validated against the item, pool and skill sheets."""
    items = {r['d3_id']: r for r in read(module, 'data/d3/base_items.csv') if r['pool_version'] == 'yes'}
    sets = {r['set_name'] for r in items.values() if r['set_name']}
    # A Bottomless potion owns its power like an item (diablocraft-1z5ye): its range rolls once per potion in StageRoll. The
    # potion slot has no affix pool, so a potion never owns a `stat` row.
    potions = read(module, 'data/d3/legendary_potions.csv')
    items.update({r['d3_id']: {'slot': 'potion', 'set_name': ''} for r in potions})
    pools = {}
    for r in read(module, 'data/d3/affix_pools.csv'):
        pools.setdefault(r['slot'], set()).add(r['affix_id'])
    skills = {r['skill_name'] for f in sorted((module / 'data/d3').glob('*_skills.csv')) for r in read(module, f'data/d3/{f.name}')}
    runes = {(r['skill_name'], r['rune_name']) for f in sorted((module / 'data/d3').glob('*_runes.csv')) for r in read(module, f'data/d3/{f.name}')}
    numbers = {(r['skill'], r['token']) for f in sorted((module / 'data/d3').glob('*_skill_values.csv'))
               for r in read(module, f'data/d3/{f.name}') if not r['rune']}
    passives = {(r['skill'], r['token']): float(r['value']) for f in sorted((module / 'data/d3').glob('*_passive_values.csv'))
                for r in read(module, f'data/d3/{f.name}') if not r['rune'] and not r['qualifier']}
    out, seen = [], set()
    sheet = read(module, 'data/legendary_powers.csv')
    buffs = {(b['owner'], b['stat'], b['aura']) for b in read(module, 'data/legendary_power_buffs.csv')} \
        if (module / 'data/legendary_power_buffs.csv').is_file() else set()   # none: no buff row can stand
    for r in sheet:
        where = f"legendary_powers.csv {r['owner']} {r['pieces']} {r['skill']} {r['stat']}"
        pieces = int(r['pieces']) if r['pieces'] else 0
        if pieces and pieces not in LEVELS:
            raise ValueError(f'{where}: pieces is blank (an item) or one of {LEVELS}')
        if pieces and r['owner'] not in sets:
            raise ValueError(f'{where}: not a set of base_items.csv')
        if not pieces and r['owner'] not in items:
            raise ValueError(f'{where}: not an item of the pool (base_items.csv pool_version yes) or a Bottomless potion')
        if r['kind'] not in KINDS:
            raise ValueError(f"{where}: kind is one of {KINDS}")
        # A skill row may name several skills joined by ';' (they share its number and its roll): none may appear in two rows of the same key.
        keys = {(r['owner'], pieces, name, r['stat'], r['cond'], r['fire_on']) for name in r['skill'].split(';')}
        if seen & keys or (r['kind'] != 'skill' and r['stat'] not in NAMED_CUTS and ';' in r['skill']) or len(keys) != len(r['skill'].split(';')):
            raise ValueError(f'{where}: listed twice (a skill is named once per owner, level and stat, and only a skill row lists several)')
        seen |= keys
        if bool(r['skill']) != (r['kind'] in ('skill', 'rune', 'element', 'passive') or r['stat'] in ('apply_skill', 'cast_skill', 'mark_enemy', 'skill_damage_pct') or r['stat'] in NAMED_CUTS):
            raise ValueError(f'{where}: a skill is named by the skill and rune rows and the apply_skill, cast_skill, mark_enemy, skill_damage_pct and named-cut effects (an element by an element row, a passive by a passive row), and by no others')
        low, high = float(r['value_min']), float(r['value_max'])
        positive = (r['kind'] != 'player' or r['stat'] in POSITIVE_PLAYER_STATS) and \
            not (r['kind'] == 'buff' and r['stat'] in NEGATIVE_BUFF_STATS)
        landing_cast = r['stat'] == 'cast_skill' and r['fire_on'] == 'land'
        # Won Khim Lau's cast on a hit: 0, the cooldown is the tunable monk.won_khim_lau_cooldown_seconds
        hit_cast = r['stat'] == 'cast_skill' and r['fire_on'] == 'hit_spender'
        if hit_cast and (low != 0 or high != 0):
            raise ValueError(f'{where}: cast_skill on a hit is 0, its cooldown the tunable monk.won_khim_lau_cooldown_seconds')
        if positive and not (0 < low <= high or ((landing_cast or hit_cast) and low == high == 0)):
            raise ValueError(f'{where}: needs 0 < value_min <= value_max')
        if not positive and not (-100 < low <= high and (low < 0 or high > 0) and (low < 0) == (high < 0)):
            raise ValueError(f'{where}: a player number is non-zero, one sign, above -100')
        if r['stat'] in ('damage_reduction_pct', 'blocked_damage_cut_pct') and high >= 100:
            raise ValueError(f'{where}: a damage reduction is below 100')
        if r['stat'] == 'block_chance_pct' and high > 100:
            raise ValueError(f'{where}: a block chance is at most 100')
        arg = float(r['cond_arg']) if r['cond_arg'] else 0.0
        every = float(r['stack_seconds']) if r['stack_seconds'] else 0.0
        most = float(r['stack_max']) if r['stack_max'] else 0.0
        listed = [x for x in r['cond_skills'].split(';') if x]
        if r['cond']:
            if r['cond'] not in CONDITIONS:
                raise ValueError(f'{where}: cond is one of {CONDITIONS}')
            if r['kind'] == 'stat':
                raise ValueError(f'{where}: a stat row (rolled on the item) carries no condition')
            if r['cond'] in UNTIMED and r['cond_arg']:
                raise ValueError(f'{where}: {r["cond"]} takes no cond_arg')
            if r['cond'] not in UNTIMED and arg <= 0:
                raise ValueError(f'{where}: {r["cond"]} needs cond_arg > 0 seconds')
            if r['cond'] == 'enemies_hit_at_most' and (r['kind'] != 'effect' or r['fire_on'] not in COUNTED_EVENTS or listed or arg != int(arg)):
                raise ValueError(f'{where}: enemies_hit_at_most is an effect row\'s, fired on {COUNTED_EVENTS}, a whole cond_arg and no cond_skills')
            if r['cond'] == 'target_slowed' and (r['kind'] != 'skill' or r['stat'] != 'damage_increase_pct' or listed or r['fire_on']):
                raise ValueError(f'{where}: target_slowed is a skill row\'s damage_increase_pct, read on the hit with its target, no cond_skills or event')
            if r['cond'] == 'first_hits' and (r['kind'] != 'skill' or r['stat'] != 'damage_increase_pct' or r['fire_on'] or listed or arg != int(arg)):
                raise ValueError(f'{where}: first_hits is a skill\'s damage_increase_pct row\'s, a whole cond_arg (enemies), no event and no cond_skills')
            if r['cond'] == 'cast_enemies_at_most' and (r['kind'] != 'skill' or r['stat'] != 'damage_increase_pct' or r['fire_on'] or listed or arg != int(arg)):
                raise ValueError(f'{where}: cast_enemies_at_most is a skill\'s damage_increase_pct row\'s, a whole cond_arg (enemies), no event and no cond_skills')
            if r['cond'] == 'no_damage_for' and (r['kind'] != 'player' or listed or r['fire_on'] or pieces):
                raise ValueError(f'{where}: no_damage_for is an item\'s player row, with a cond_arg of seconds and no cond_skills, set level or event')
            if r['cond'] == 'own_life_below' and (r['kind'] != 'player' or listed or r['fire_on'] or pieces or not any(
                    o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'player' and o['stat'] == 'own_life_threshold_pct' for o in sheet)):
                raise ValueError(f'{where}: own_life_below is an item\'s player row, with an own_life_threshold_pct row of the same item and no cond_skills or event')
            if r['cond'] == 'per_prior_hit' and (r['kind'] != 'skill' or r['stat'] != 'damage_increase_pct' or r['fire_on'] or listed):
                raise ValueError(f'{where}: per_prior_hit is a skill\'s damage_increase_pct row\'s, no cond_arg, event or cond_skills')
            if r['cond'] == 'life_missing' and (r['kind'] not in ('player', 'skill') or listed or r['fire_on']):
                raise ValueError(f'{where}: life_missing is a player or skill row\'s, simply on, no cond_skills or event')
            if r['cond'] == 'first_hit_on_target' and (r['kind'] != 'effect' or r['stat'] != 'stun_seconds' or r['fire_on'] != 'hit' or pieces):
                raise ValueError(f'{where}: first_hit_on_target is an item\'s stun_seconds effect row, fired on a hit')
            if r['cond'] == 'life_missing' and r['stat'] in ('damage_reduction_pct', 'damage_taken_pct') and max(abs(low), abs(high)) * 100 >= 100:
                raise ValueError(f'{where}: a life_missing damage reduction counts its number once per 1% of Life missing, up to 100% of it: it must stay below 100')
            if r['cond'] == 'target_creature_type' and (r['kind'] != 'effect' or r['fire_on'] not in CREATURE_EVENTS or not listed or any(x not in CREATURE_TYPES for x in listed)):
                raise ValueError(f'{where}: target_creature_type is an effect row\'s, fired on {CREATURE_EVENTS}, with cond_skills each one of {CREATURE_TYPES}')
            if r['cond'] == 'per_resource_spent' and (r['kind'] != 'effect' or r['fire_on'] != 'resource_spent' or listed or arg != int(arg)):
                raise ValueError(f'{where}: per_resource_spent is an effect row\'s, fired on resource_spent, a whole cond_arg (points per step) and no cond_skills')
            if r['cond'] == 'target_life_at_least' and (r['kind'] != 'player' or r['stat'] != 'crit_chance_pct' or listed or r['fire_on'] or arg > 100):
                raise ValueError(f'{where}: target_life_at_least is a player crit_chance_pct row\'s (the one reader that hands the target over), a cond_arg percent up to 100, no cond_skills or event')
            if r['cond'] in ('channel_or_after', 'channel_held', 'skills_active') and (not listed or any(x not in skills for x in listed)):
                raise ValueError(f'{where}: {r["cond"]} needs cond_skills, each a skill of a *_skills.csv sheet')
            if r['cond'] not in STACKING and (every or most):
                raise ValueError(f'{where}: only {STACKING} and stack_buff stack')
            if r['cond'] in STACKING and (listed or every <= 0 or most < 1 or most != int(most)):
                raise ValueError(f'{where}: {r["cond"]} needs stack_seconds > 0, a whole stack_max >= 1 and no cond_skills')
            if r['cond'] == 'standing_still' and (r['kind'] != 'player' or r['fire_on'] or pieces):
                raise ValueError(f'{where}: standing_still is an item\'s player row, with no event or set level')
            if r['cond'] in ('moving', 'not_moving') and (r['kind'] != 'player' or listed or r['fire_on']):
                raise ValueError(f'{where}: {r["cond"]} is a player row\'s, with no cond_skills or event')
            if r['cond'] == 'triggered' and (listed or not r['fire_on']):
                raise ValueError(f'{where}: triggered needs a fire_on event and no cond_skills')
            if r['cond'] == 'element_window' and (listed or not pieces or r['kind'] != 'player' or not any(
                    o['owner'] == r['owner'] and o['pieces'] == r['pieces'] and o['kind'] == 'effect' and o['stat'] == 'element_window' for o in sheet)):
                raise ValueError(f'{where}: element_window is a set bonus\'s player row, with the element_window effect row of the same set and level and no cond_skills')
            if r['cond'] == 'resource_above' and (listed or pieces or not any(
                    o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'player' and o['stat'] == 'resource_threshold_pct'
                    for o in sheet)):
                raise ValueError(f'{where}: resource_above is an item\'s, with a resource_threshold_pct row of the same item and no cond_skills')
        elif r['stat'] == 'stack_buff':
            if r['kind'] != 'effect' or every <= 0 or most < 1 or most != int(most) or low != high or low != int(low) or pieces:
                raise ValueError(f'{where}: stack_buff is an item\'s effect of whole stacks, with stack_seconds > 0 and a whole stack_max >= 1')
            if not any(o['owner'] == r['owner'] and o['kind'] == 'buff' for o in sheet):
                raise ValueError(f'{where}: stack_buff needs buff rows of the same item')
        elif r['stat'] == 'mark_enemy':
            if r['kind'] != 'effect' or every <= 0 or most or r['cond_arg'] or listed or pieces or r['chance_pct'] or r['icd_seconds']:
                raise ValueError(f'{where}: mark_enemy is an item\'s effect with stack_seconds > 0 (the mark\'s seconds) and no stack_max, cond_arg, chance_pct or icd_seconds')
            if (r['owner'], 'mark_enemy', 'mark') not in buffs:
                raise ValueError(f'{where}: mark_enemy needs its mark record in data/legendary_power_buffs.csv')
        elif r['stat'] in ('element_resist', 'element_window'):
            if r['kind'] != 'effect' or every <= 0 or r['cond_arg'] or r['cond_skills'] or low != high or not pieces:
                raise ValueError(f'{where}: {r["stat"]} is a set bonus\'s effect row, with stack_seconds > 0, one number and no cond')
            if (r['stat'] == 'element_window') != bool(most) or most != int(most):
                raise ValueError(f'{where}: element_window takes a whole stack_max (the elements that stack before it extends), element_resist none')
        elif r['cond_arg'] or r['cond_skills'] or every or most:
            raise ValueError(f'{where}: cond_arg, cond_skills and the stack numbers belong to a cond')
        fire_skills = [x for x in r['fire_skills'].split(';') if x]
        chance = float(r['chance_pct']) if r['chance_pct'] else 100.0
        icd = float(r['icd_seconds']) if r['icd_seconds'] else 0.0
        if r['fire_on']:
            if r['fire_on'] not in EVENTS:
                raise ValueError(f"{where}: fire_on is one of {EVENTS}")
            if r['kind'] == 'stat':
                raise ValueError(f'{where}: a stat row (rolled on the item) is not fired')
            if r['kind'] == 'effect' or r['cond'] == 'triggered':
                pass
            else:
                raise ValueError(f'{where}: an event fires an effect row, or starts a triggered condition')
            every_hit = r['fire_on'] == 'hit' and (r['stat'] in CONTROL_EFFECTS or r['stat'] in PROC_EFFECTS or r['stat'] in ('summon_herd', 'cost_free_seconds', 'thorns_on_attack_pct', 'pull_enemy')) and not fire_skills   # a control effect's, a proc's, the herd's or the free window's hit: every skill (Hellrack, Storm Crow, Bovine Bardiche, Kekegi's)
            if r['fire_on'] in NAMED_EVENTS and not every_hit and (not fire_skills or any(x not in skills for x in fire_skills)):
                raise ValueError(f'{where}: a cast, a hit or a landing needs fire_skills, each a skill of a *_skills.csv sheet (a control effect\'s or summon_herd\'s hit may name none: every skill)')
            if r['fire_on'] == 'explosion' and (not fire_skills or any(x not in EXPLODING_SKILLS for x in fire_skills)):
                raise ValueError(f'{where}: an explosion needs fire_skills, each one of {EXPLODING_SKILLS}')
            if r['fire_on'] in ('hit_element', 'taken_element') and (not fire_skills or any(x not in SET_ELEMENTS for x in fire_skills)):
                raise ValueError(f'{where}: {r["fire_on"]} needs fire_skills, each one of {SET_ELEMENTS}')
            if (r['stat'] == 'resource_per_life_lost_pct') != (r['fire_on'] == 'taken_element'):
                raise ValueError(f'{where}: resource_per_life_lost_pct is fired by taken_element and taken_element fires nothing else')
            if r['stat'] == 'resource_per_life_lost_pct' and (r['kind'] != 'effect' or pieces or low != high or low <= 0):
                raise ValueError(f'{where}: resource_per_life_lost_pct is an item\'s effect row of one number above 0')
            if (r['stat'] in ELEMENT_EFFECTS) != (r['fire_on'] == 'hit_element'):
                raise ValueError(f'{where}: {ELEMENT_EFFECTS} are fired by hit_element and hit_element fires nothing else')
            if (r['stat'] == 'revive_full') != (r['fire_on'] == 'fatal'):
                raise ValueError(f'{where}: revive_full is fired by fatal and fatal fires nothing else')
            if (r['stat'] == 'multiply_image') != (r['fire_on'] == 'image_death'):
                raise ValueError(f'{where}: multiply_image is fired by image_death and image_death fires nothing else')
            if r['fire_on'] == 'resource_spent' and r['stat'] not in NAMED_CUTS:
                raise ValueError(f'{where}: resource_spent fires only the named cooldown cut')
            if r['stat'] in NAMED_CUTS and r['fire_on'] not in ('resource_spent',) + COUNTED_EVENTS:
                raise ValueError(f'{where}: the named cooldown cut is fired by resource_spent, or by a spender or generator hit')
            if r['fire_on'] == 'life_below' and r['stat'] != 'cast_skill' or r['stat'] == 'cast_skill' and r['fire_on'] not in ('life_below', 'land', 'taken', 'hit_spender'):
                raise ValueError(f'{where}: cast_skill is fired by life_below, land, taken or hit_spender, and life_below fires nothing else')
            if r['stat'] == 'cast_skill' and r['fire_on'] == 'hit_spender' and not fire_skills:
                raise ValueError(f'{where}: cast_skill on a hit names the skills whose hit casts it')
            if r['fire_on'] == 'tick' and (r['kind'] != 'effect' or icd <= 0 or r['chance_pct']):
                raise ValueError(f'{where}: tick is the clock: it fires an effect row once every icd_seconds (the period, above 0), with no chance_pct')
            if r['fire_on'] not in NAMED_EVENTS + ('explosion', 'hit_element', 'taken_element') + COUNTED_EVENTS and fire_skills:
                raise ValueError(f'{where}: only a cast, a hit, a landing, an explosion, an element hit or a cast that hit names skills')
            if r['fire_on'] not in ('hit_element', 'taken_element') and any(x not in skills for x in fire_skills):
                raise ValueError(f'{where}: fire_skills are skills of a *_skills.csv sheet')
            if not 0 < chance <= 100:
                raise ValueError(f'{where}: chance_pct is above 0 and at most 100')
            if icd < 0:
                raise ValueError(f'{where}: icd_seconds is not negative')
        elif r['kind'] == 'effect' or r['cond'] == 'triggered' or fire_skills or r['chance_pct'] or r['icd_seconds']:
            raise ValueError(f'{where}: an effect, a triggered condition, fire_skills, chance_pct and icd_seconds need a fire_on event')
        if r['kind'] == 'effect':
            if r['stat'] not in EFFECT_STATS:
                raise ValueError(f'{where}: an effect stat is one of {EFFECT_STATS}')
            if r['stat'] == 'revive_full' and (low != 1 or high != 1 or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces or r['skill'] or fire_skills):
                raise ValueError(f'{where}: revive_full is an item\'s one revive (value 1), with no chance_pct, icd_seconds, condition, skill, fire_skills or set level')
            if r['stat'] == 'multiply_image' and (low != 1 or high != 1 or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces):
                raise ValueError(f'{where}: multiply_image is an item\'s one Image (value 1), with no chance_pct (the tunable is the chance), cooldown or condition')
            if r['stat'] == 'next_attack_pct':
                if r['fire_on'] != 'block':
                    raise ValueError(f'{where}: next_attack_pct is fired by block')
                if fire_skills or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces or r['skill'] or low != high or not low.is_integer():
                    raise ValueError(f'{where}: next_attack_pct is an item\'s one whole percent, with no fire_skills, chance_pct, icd_seconds, skill, condition or set level')
                if (r['owner'], 'next_attack_pct', 'dummy') not in buffs:
                    raise ValueError(f'{where}: next_attack_pct needs its dummy record in legendary_power_buffs.csv (the aura that shows the attack is armed)')
            if r['stat'] == 'summon_herd':
                if r['fire_on'] != 'hit' or fire_skills or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces:
                    raise ValueError(f'{where}: summon_herd is an item\'s, fired on every hit (no fire_skills), with no chance_pct or icd_seconds (the tunables are those), condition or set level')
                if low != high or low < 1 or low != int(low):
                    raise ValueError(f'{where}: summon_herd is one whole number of cows')
                if (r['owner'], 'summon_herd', 'hit') not in buffs:
                    raise ValueError(f'{where}: summon_herd needs its hit record in legendary_power_buffs.csv (the cows\' damage is dealt under it)')
            if r['stat'] == 'thorns_on_attack_pct':
                # N-THDEAL (Hack, diablocraft-fhpm9): N% of the player's own Thorns damage is dealt to the enemy each hit lands on
                if r['fire_on'] != 'hit' or fire_skills or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces or r['skill']:
                    raise ValueError(f'{where}: thorns_on_attack_pct is an item\'s, fired on every hit (no fire_skills), with no chance_pct, icd_seconds, skill, condition or set level')
                if not 0 < low <= high <= 100:
                    raise ValueError(f'{where}: thorns_on_attack_pct is a share of the Thorns damage in percent: above 0 and at most 100')
            if r['stat'] in PROC_EFFECTS:
                if r['fire_on'] != 'hit' or fire_skills or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces or r['skill']:
                    raise ValueError(f'{where}: {r["stat"]} is an item\'s, fired on every hit (no fire_skills), with no chance_pct, icd_seconds, skill, condition or set level (the chance is its number, the damage a tunable)')
                if not 0 < low <= high <= 100:
                    raise ValueError(f'{where}: {r["stat"]} is a chance in percent: above 0 and at most 100')
                if (r['owner'], r['stat'], 'hit') not in buffs:
                    raise ValueError(f'{where}: {r["stat"]} needs its hit record in legendary_power_buffs.csv (the ball\'s damage is dealt under it)')
            if r['stat'] == 'heal_missing_life_pct':
                if r['fire_on'] != 'hit_generator' or not fire_skills or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces or r['skill']:
                    raise ValueError(f'{where}: heal_missing_life_pct is an item\'s, fired by hit_generator of the skills it names, with no chance_pct, icd_seconds, skill, condition or set level')
                if not 0 < low <= high <= 100:
                    raise ValueError(f'{where}: heal_missing_life_pct is a percent of the Life missing: above 0 and at most 100')
            if r['stat'] == 'bone_shield':
                if r['fire_on'] != 'taken' or fire_skills or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces or r['skill']:
                    raise ValueError(f'{where}: bone_shield is an item\'s, fired on taken (no fire_skills), with no chance_pct, icd_seconds, skill, condition or set level (the chance is its number)')
                if not 0 < low <= high <= 100:
                    raise ValueError(f'{where}: bone_shield is a chance in percent: above 0 and at most 100')
                mates = {o['stat'] for o in sheet if o['owner'] == r['owner'] and o['kind'] == 'player' and o['stat'] in BONE_SHIELD_STATS
                         and not o['pieces'] and o['value_min'] == o['value_max'] and not o['cond'] and not o['fire_on']}
                if mates != set(BONE_SHIELD_STATS):
                    raise ValueError(f'{where}: bone_shield needs the item\'s fixed player rows {BONE_SHIELD_STATS}')
                if (r['owner'], 'damage_reduction_pct', 'dummy') not in buffs:
                    raise ValueError(f'{where}: bone_shield needs its damage_reduction_pct record in data/legendary_power_buffs.csv (the protection is that aura)')
                if not any(o['owner'] == r['owner'] and o['kind'] == 'buff' and o['stat'] == 'damage_reduction_pct' and o['value_min'] == o['value_max'] for o in sheet):
                    raise ValueError(f'{where}: bone_shield needs the item\'s fixed buff damage_reduction_pct row (how much smaller each hit is)')
            if r['stat'] == 'pull_enemy':
                if r['fire_on'] != 'hit' or fire_skills or r['chance_pct'] or r['icd_seconds'] or r['cond'] or pieces or r['skill']:
                    raise ValueError(f'{where}: pull_enemy is an item\'s, fired on every hit (no fire_skills), with no chance_pct, icd_seconds, skill, condition or set level (the chance is its number)')
                if not 0 < low <= high <= 100:
                    raise ValueError(f'{where}: pull_enemy is a chance in percent: above 0 and at most 100')
                mates = {o['stat'] for o in sheet if o['owner'] == r['owner'] and o['kind'] == 'player' and o['stat'] in PULL_STATS
                         and not o['pieces'] and o['value_min'] == o['value_max'] and not o['cond'] and not o['fire_on']}
                if mates != set(PULL_STATS):
                    raise ValueError(f'{where}: pull_enemy needs the item\'s fixed player rows {PULL_STATS}')
            if r['stat'] == 'random_shrine':
                if r['fire_on'] not in ('kill', 'kill_elite') or fire_skills or r['chance_pct'] or r['icd_seconds'] or pieces or r['cond'] not in ('', 'target_creature_type'):
                    raise ValueError(f'{where}: random_shrine is an item\'s, fired on a kill, with no fire_skills, chance_pct or icd_seconds (the tunable is the chance), set level or condition but target_creature_type')
                if low != high or low < 1 or low != int(low):
                    raise ValueError(f'{where}: random_shrine is one whole number of shrine effects')
            if r['stat'] == 'cast_skill':
                if ';' in r['skill'] or r['skill'] not in skills:
                    raise ValueError(f"{where}: cast_skill casts one {r['skill']}, which is not a skill of a *_skills.csv sheet")
                if r['icd_seconds'] or r['cond'] or bool(r['chance_pct']) != (r['fire_on'] == 'taken'):
                    raise ValueError(f'{where}: cast_skill\'s number is the internal cooldown in seconds: no icd_seconds or condition, and a chance_pct on taken alone')
                if landing_cast and (not pieces or low != 0 or high != 0):
                    raise ValueError(f'{where}: cast_skill on land is a set bonus\'s, number 0 (no internal cooldown)')
                if not landing_cast and pieces:
                    raise ValueError(f'{where}: cast_skill on life_below, taken or hit_spender is an item\'s, not a set level')
                if r['fire_on'] == 'life_below' and not any(o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'player' and o['stat'] == 'life_threshold_pct' for o in sheet):
                    raise ValueError(f'{where}: cast_skill needs the life_threshold_pct row of the same item: the two go together')
            if r['cond'] and r['cond'] not in ('enemies_hit_at_most', 'per_resource_spent', 'target_creature_type', 'first_hit_on_target'):
                raise ValueError(f'{where}: an effect row is fired, its one condition is enemies_hit_at_most, per_resource_spent or target_creature_type')
            if (r['cond'] == 'per_resource_spent') != (r['fire_on'] == 'resource_spent'):
                raise ValueError(f'{where}: per_resource_spent goes with the resource_spent event and the event with it')
            if r['stat'] in NAMED_CUTS and (low != high or any(name not in skills for name in r['skill'].split(';'))):
                raise ValueError(f'{where}: the named cooldown cut is one fixed number of seconds over skills of a *_skills.csv sheet')
            if bool(r['skill']) != (r['stat'] in ('apply_skill', 'cast_skill', 'mark_enemy') or r['stat'] in NAMED_CUTS):
                raise ValueError(f'{where}: only the apply_skill, cast_skill, mark_enemy and named-cut effects name a skill')
            if r['stat'] == 'cost_free_seconds' and (pieces or r['cond'] or r['fire_on'] != 'hit'):
                raise ValueError(f'{where}: cost_free_seconds is an item\'s seconds, fired on a hit, with no condition')
            if r['stat'] == 'mark_enemy' and (';' in r['skill'] or r['skill'] not in skills or r['fire_on'] != 'hit' or not fire_skills or r['cond']):
                raise ValueError(f'{where}: mark_enemy names one skill whose damage it raises, is fired on a hit of fire_skills, with no condition')
            if r['stat'] in CONTROL_EFFECTS and (pieces or r['cond'] not in ('', 'first_hit_on_target') or (r['cond'] and r['stat'] != 'stun_seconds') or r['fire_on'] != 'hit' or low != high or low <= 0):
                raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number of seconds, fired on a hit, with no condition (a stun may hold first_hit_on_target)')

            if r['stat'] == 'burn_trail':
                if r['fire_on'] != 'tick' or pieces or r['cond'] or r['skill'] or fire_skills or r['chance_pct'] or not 0 < low <= high:
                    raise ValueError(f'{where}: burn_trail is an item\'s percent of weapon damage per second (above 0), fired by tick, with no chance_pct, skill, condition or set level')
                if (r['owner'], 'burn_trail', 'hit') not in buffs:
                    raise ValueError(f'{where}: burn_trail needs its hit record in legendary_power_buffs.csv (the fire\'s damage is dealt under it)')
            if r['stat'] == 'drain_life' and (r['fire_on'] != 'tick' or pieces or r['cond'] or low != high or not 0 < low <= 100):
                raise ValueError(f'{where}: drain_life is an item\'s one fixed percent of each enemy\'s Life (above 0, at most 100), fired by tick, with no condition')
            if r['stat'] in SLOW_EFFECTS:
                if pieces or r['cond'] or r['fire_on'] != 'hit':
                    raise ValueError(f'{where}: {r["stat"]} is an item\'s, fired on a hit, with no condition')
        if r['kind'] == 'player' and r['stat'] == 'resource_cost_reduction_pct' and (pieces or r['fire_on'] or high >= 100):
            raise ValueError(f'{where}: resource_cost_reduction_pct is an item\'s percent below 100, with no set level or event')
        if r['kind'] == 'player' and r['stat'] == 'own_life_threshold_pct' and (pieces or r['cond'] or r['fire_on'] or high > 100 or not any(
                o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'player' and o['cond'] == 'own_life_below' for o in sheet)):
            raise ValueError(f'{where}: own_life_threshold_pct is an item\'s percent of Life up to 100, simply on, beside an own_life_below row of the same item')
        if r['kind'] == 'player' and r['stat'] in LIFE_REGEN_STATS:
            if pieces or r['cond'] or r['fire_on']:
                raise ValueError(f'{where}: {r["stat"]} is an item\'s number, simply on (no set level, condition or event)')
            if r['stat'] == 'life_regen_tick_seconds' and (low != high or not any(
                    o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'player' and o['stat'] == 'life_regen_by_missing_pct' for o in sheet)):
                raise ValueError(f'{where}: life_regen_tick_seconds is one fixed number beside the life_regen_by_missing_pct row of the same item')
            if r['stat'] == 'life_regen_by_missing_pct' and not any(
                    o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'player' and o['stat'] == 'life_regen_tick_seconds' for o in sheet):
                raise ValueError(f'{where}: life_regen_by_missing_pct needs the item\'s fixed life_regen_tick_seconds row')
                if high >= 100:
                    raise ValueError(f'{where}: a slow is below 100%')
                if not any(o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'player' and o['stat'] == 'slow_seconds' for o in sheet):
                    raise ValueError(f'{where}: {r["stat"]} needs the slow_seconds row of the same item: the two go together')
            if r['stat'] == 'fear_enemies':
                if pieces or r['cond'] or r['skill'] or r['fire_on'] != 'tick' or low != high or low <= 0:
                    raise ValueError(f'{where}: fear_enemies is an item\'s one fixed number of seconds above 0, fired by tick, with no condition or skill')
                mates = {o['stat'] for o in sheet if o['owner'] == r['owner'] and o['kind'] == 'player' and o['stat'] in FEAR_STATS
                         and not o['pieces'] and o['value_min'] == o['value_max'] and not o['cond'] and not o['fire_on']}
                if mates != set(FEAR_STATS):
                    raise ValueError(f'{where}: fear_enemies needs the item\'s fixed player rows {FEAR_STATS}')
            if r['stat'] in ELEMENT_EFFECTS and (not pieces or r['cond'] or r['skill']):
                raise ValueError(f'{where}: {r["stat"]} is a set bonus\'s effect, with no condition')
            if r['stat'] == 'apply_skill' and r['skill'] not in APPLY_SKILLS:
                raise ValueError(f"{where}: the code applies only {APPLY_SKILLS}")
            if r['stat'] in DISTANCE_EFFECTS:
                if pieces or r['cond'] or r['fire_on'] != 'hit' or low != high:
                    raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number, fired on a hit, with no condition')
                mates = {o['stat'] for o in sheet if o['owner'] == r['owner'] and o['kind'] == 'player' and o['stat'] in DISTANCE_RESOURCE_STATS
                         and not o['pieces'] and o['value_min'] == o['value_max'] and not o['cond'] and not o['fire_on']}
                if mates != set(DISTANCE_RESOURCE_STATS):
                    raise ValueError(f'{where}: {r["stat"]} needs the item\'s fixed player rows {DISTANCE_RESOURCE_STATS}')
        if r['kind'] == 'player' and r['stat'] in GENERATION_STATS:
            if pieces or r['fire_on'] or r['cond'] != {'damage_generation_pct': 'moving', 'damage_generation_cut_pct': 'not_moving'}[r['stat']]:
                raise ValueError(f'{where}: damage_generation_pct is an item\'s number under moving and damage_generation_cut_pct one under not_moving, with no set level or event')
            if r['stat'] == 'damage_generation_cut_pct' and high >= 100:
                raise ValueError(f'{where}: a cut is below 100')
        if r['kind'] == 'player' and r['stat'] == 'thorns_per_vitality_pct' and (pieces or r['cond'] or r['fire_on']):
            raise ValueError(f'{where}: thorns_per_vitality_pct is an item\'s percent of the sheet\'s Vitality, simply on (no set level, condition or event)')
        if r['kind'] == 'player' and r['stat'] == 'damage_reduction_per_stunned_pct':
            if pieces or r['cond'] or r['fire_on'] or high >= 100:
                raise ValueError(f'{where}: damage_reduction_per_stunned_pct is an item\'s percent below 100 for each stunned enemy, simply on (no set level, condition or event)')
            if {o['stat'] for o in sheet if o['owner'] == r['owner'] and o['kind'] == 'player' and o['stat'] in STUN_STATS and not o['pieces']
                    and o['value_min'] == o['value_max'] and not o['cond'] and not o['fire_on']} != set(STUN_STATS):
                raise ValueError(f'{where}: damage_reduction_per_stunned_pct needs the item\'s fixed player rows {STUN_STATS}')
        if r['kind'] == 'player' and r['stat'] in STUN_STATS and (pieces or low != high or r['cond'] or r['fire_on'] or not any(
                o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'player' and o['stat'] == 'damage_reduction_per_stunned_pct' for o in sheet)):
            raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number, simply on, beside the damage_reduction_per_stunned_pct row of the same item')
        if r['kind'] == 'player' and r['stat'] in FEAR_STATS and (pieces or low != high or r['cond'] or r['fire_on'] or not any(
                o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'effect' and o['stat'] == 'fear_enemies' for o in sheet)):
            raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number, simply on, beside the fear_enemies effect row of the same item')
        if r['kind'] == 'player' and r['stat'] in BONE_SHIELD_STATS and (pieces or low != high or r['cond'] or r['fire_on'] or not any(
                o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'effect' and o['stat'] == 'bone_shield' for o in sheet)):
            raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number, simply on, beside the bone_shield effect row of the same item')
        if r['stat'] == 'damage_reduction_of_block_pct' and (r['kind'] != 'player' or r['cond'] or r['fire_on'] or r['cond_skills'] or max(abs(low), abs(high)) > 100):
            raise ValueError(f'{where}: damage_reduction_of_block_pct is a player row\'s share (up to 100) of Block Chance, always on, no condition, event or cond_skills')
        if r['stat'] == 'damage_vs_impaired_pct' and (r['kind'] != 'player' or r['cond'] or r['fire_on'] or r['cond_skills']):
            raise ValueError(f'{where}: damage_vs_impaired_pct is a player row\'s, always on, read on the hit with its target, no condition, event or cond_skills')
        if r['kind'] == 'player' and r['stat'] in PULL_STATS and (pieces or low != high or r['cond'] or r['fire_on'] or not any(
                o['owner'] == r['owner'] and not o['pieces'] and o['kind'] == 'effect' and o['stat'] == 'pull_enemy' for o in sheet)):
            raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number, simply on, beside the pull_enemy effect row of the same item')
        if r['kind'] == 'player' and r['stat'] in DISTANCE_RESOURCE_STATS and (pieces or low != high or r['cond'] or r['fire_on']):
            raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number, simply on, with no condition or event')
        if r['kind'] == 'stat' and pieces and (r['stat'] not in SET_STATS or r['skill'] or low != high):
            raise ValueError(f"{where}: a set level's stat is one fixed number of one of {SET_STATS} (the affixes the sheet maps), with no skill")
        if r['kind'] == 'player' and r['stat'] in ELEMENT_WINDOW_STATS and (not pieces or low != high or r['cond'] or r['fire_on'] or not any(
                o['owner'] == r['owner'] and o['pieces'] == r['pieces'] and o['kind'] == 'effect' and o['stat'] == 'element_window' for o in sheet)):
            raise ValueError(f'{where}: {r["stat"]} is a set bonus\'s one fixed number, simply on, beside the element_window effect row of the same set and level')
        if r['kind'] == 'stat' and not pieces and r['stat'] not in pools.get(items[r['owner']]['slot'], ()):
            raise ValueError(f"{where}: {r['stat']} is not in the {items[r['owner']]['slot']} pool, so the roll would skip it")
        if r['kind'] == 'skill':
            names = r['skill'].split(';')
            if len(r['skill']) > 128:
                raise ValueError(f"{where}: the skill cell is over the table's VARCHAR(128)")
            if any(RUNE_JOIN in name for name in names) and (len(names) != 1 or r['stat'] != 'damage_increase_pct'):
                raise ValueError(f'{where}: a rune-qualified skill ("Skill{RUNE_JOIN}Rune") is the single name of a damage_increase_pct row')
            if any((name.partition(RUNE_JOIN)[0], name.partition(RUNE_JOIN)[2]) not in runes if RUNE_JOIN in name else name not in skills for name in names):
                raise ValueError(f"{where}: {r['skill']} is not a skill (or a list of skills, or a rune of a skill) of a *_skills.csv / *_runes.csv sheet")
            if r['stat'] not in SKILL_STATS:
                raise ValueError(f'{where}: a skill stat is one of {SKILL_STATS}')
            if r['stat'] in BLEED_STATS and any((name, 'dot_duration_seconds') not in numbers for name in names):
                raise ValueError(f"{where}: {r['skill']} has no dot_duration_seconds in its skill values, so it has no bleed for {r['stat']}")
            if r['stat'] == 'dot_max_stacks' and (low != high or low < 2 or low != int(low)):
                raise ValueError(f'{where}: dot_max_stacks is one whole number above 1')
            if r['stat'] in FRENZY_STATS:
                if names != ['Frenzy']:
                    raise ValueError(f'{where}: {FRENZY_STATS} are Frenzy rows (the code reads them only there)')
                if low != high or low < 1 or low != int(low):
                    raise ValueError(f'{where}: {r["stat"]} is one whole number above 0')
            if r['stat'] == 'dot_payout_seconds' and low != high:
                raise ValueError(f'{where}: dot_payout_seconds is one number')
            if r['stat'] == 'cost_reduction_pct' and (r['cond'] or r['fire_on'] or not 0 < low <= high <= 100 or any((name, 'cost_resource') not in numbers for name in names)):
                raise ValueError(f'{where}: cost_reduction_pct is 0-100 percent, simply on (the aura is set when the worn items change), on skills that state a cost_resource')
            if r['stat'] == 'pierces' and (low != 1 or high != 1 or r['cond'] or r['fire_on'] or any(name not in PIERCE_SKILLS for name in names)):
                raise ValueError(f'{where}: pierces is value 1, simply on, for {PIERCE_SKILLS} only')
            if r['stat'] == 'mark_split_factor' and (names != ['Mystic Ally'] or low != high or low < 2 or low != int(low) or r['cond'] or r['fire_on'] or pieces
                                                    or not any(o['owner'] == r['owner'] and o['stat'] == 'mark_enemy' and o['skill'] == 'Mystic Ally' for o in sheet)):
                raise ValueError(f'{where}: mark_split_factor is one whole number above 1, simply on, for Mystic Ally only, with a mark_enemy row of the same item on it')
            if r['stat'] == 'rune_effect_pct' and any(name not in RUNE_EFFECT_SKILLS for name in names):
                raise ValueError(f'{where}: rune_effect_pct is read by {RUNE_EFFECT_SKILLS} only')
            if r['stat'] == 'idle_stacks_per_second' and (names != list(IDLE_STACK_SKILLS) or low != high or low < 1 or low != int(low) or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: idle_stacks_per_second is one whole number of stacks, simply on, for {IDLE_STACK_SKILLS} only')
            if r['stat'] == 'cast_at_enemy' and (low != 1 or high != 1 or r['cond'] or r['fire_on'] or pieces or any(name not in CAST_AT_SKILLS for name in names)):
                raise ValueError(f'{where}: cast_at_enemy is an item\'s value 1, simply on, for {CAST_AT_SKILLS} only')
            if r['stat'] == 'cooldown_reduction_pct' and (low <= 0 or high > 100 or r['cond'] or r['fire_on'] or pieces):
                raise ValueError(f'{where}: cooldown_reduction_pct is an item\'s percent above 0 and at most 100 (100 is no cooldown), simply on (no condition, event or set level)')
            if r['stat'] == 'cost_add_resource' and (len(names) != 1 or low != high or low <= 0 or r['cond'] or r['fire_on'] or pieces or (names[0], 'cost_resource') in numbers):
                raise ValueError(f'{where}: cost_add_resource is an item\'s one fixed cost above 0 on one skill whose sheet states no cost_resource, simply on (the aura is set when the worn items change)')
            if r['stat'] == 'max_stacks_add' and (low != high or low < 1 or low != int(low) or r['cond'] or r['fire_on'] or pieces
                                                  or any(name not in MAX_STACK_SKILLS for name in names)):
                raise ValueError(f'{where}: max_stacks_add is one whole number above 0, an item\'s, simply on, for {MAX_STACK_SKILLS} only')
            if r['stat'] == 'summon_count_add' and (low != high or low < 1 or low != int(low) or r['cond'] or r['fire_on'] or pieces
                                                    or any(name not in ALLY_SKILLS for name in names) or len(names) != 1):
                raise ValueError(f'{where}: summon_count_add is one whole number above 0, an item\'s, simply on, for one of {ALLY_SKILLS} only')
            if r['stat'] == 'extra_strikes' and (names != list(STRIKE_SKILLS) or low != high or low < 1 or low != int(low) or r['cond'] or r['fire_on'] or pieces):
                raise ValueError(f'{where}: extra_strikes is one whole number of strikes above 0, an item\'s, simply on, for {STRIKE_SKILLS} only')

            if r['stat'] in ENEMY_STACK_STATS:
                if names != list(ENEMY_STACK_SKILLS) or r['cond'] or r['fire_on'] or pieces:
                    raise ValueError(f'{where}: {r["stat"]} is an item\'s, simply on, for {ENEMY_STACK_SKILLS} only')
                if r['stat'] != 'damage_per_enemy_hit_pct' and (low != high or low <= 0):
                    raise ValueError(f'{where}: {r["stat"]} is one fixed number above 0')
                if r['stat'] == 'enemy_hit_stacks_max' and low != int(low):
                    raise ValueError(f'{where}: enemy_hit_stacks_max is a whole number of enemies')
                if not all(any(o['owner'] == r['owner'] and o['skill'] == r['skill'] and o['stat'] == stat for o in sheet) for stat in ENEMY_STACK_STATS):
                    raise ValueError(f'{where}: the three enemy-stack rows {ENEMY_STACK_STATS} go together, for one owner and skill')
            if r['stat'] == 'decoy_damage_pct_per_stack' and (names != list(DECOY_SKILLS) or low != high or low <= 0 or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: decoy_damage_pct_per_stack is one number above 0, simply on (no condition or event), for {DECOY_SKILLS} only')
            if r['stat'] == 'damage_by_wind_stacks_pct' and (any(name not in WIND_STACK_SKILLS for name in names) or low != high or low <= 0 or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: damage_by_wind_stacks_pct is one number above 0, simply on (no condition or event), for the skills of {WIND_STACK_SKILLS} only')
            if r['stat'] == 'extra_active_count' and (names != list(ACTIVE_COUNT_SKILLS) or low != high or low < 1 or low != int(low) or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: extra_active_count is one whole number of summons, simply on, for {ACTIVE_COUNT_SKILLS} only')
            if r['stat'] == 'start_stacks' and (names != list(START_STACKS_SKILLS) or low < 1 or low != int(low) or high != int(high) or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: start_stacks is whole stacks, simply on, for {START_STACKS_SKILLS} only')
            if r['stat'] == 'jump_rehit' and (names != list(JUMP_SKILLS) or low != 1 or high != 1 or r['cond'] or r['fire_on'] or pieces):
                raise ValueError(f'{where}: jump_rehit is an item\'s value 1, simply on, for {JUMP_SKILLS} only')
            if r['stat'] in TWISTER_PULL_STATS and (names != list(TRAVEL_SKILLS) or low != high or low <= 0 or r['cond'] or r['fire_on'] or pieces or any(
                    not any(o['owner'] == r['owner'] and o['kind'] == 'skill' and o['skill'] == r['skill'] and o['stat'] == stat for o in sheet) for stat in TWISTER_PULL_STATS)):
                raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number above 0, simply on, for {TRAVEL_SKILLS} only, with the other two of {TWISTER_PULL_STATS} on the same item')
            if r['stat'] == 'straight_path' and (names != list(TRAVEL_SKILLS) or low != 1 or high != 1 or r['cond'] or r['fire_on'] or pieces):
                raise ValueError(f'{where}: straight_path is an item\'s value 1, simply on, for {TRAVEL_SKILLS} only')
            if r['stat'] == 'jump_count_factor' and (names != list(JUMP_SKILLS) or low != high or low < 2 or low != int(low) or r['cond'] or r['fire_on']
                                                     or pieces):
                raise ValueError(f'{where}: jump_count_factor is an item\'s one whole number of 2 or more, simply on, for {JUMP_SKILLS} only')
            if r['stat'] == 'mimic_damage_pct' and (names != list(MIMIC_SKILLS) or low <= 0 or high < low or r['cond'] or r['fire_on'] or pieces):
                raise ValueError(f'{where}: mimic_damage_pct is an item\'s percent above 0, simply on (no condition, event or set level), for {MIMIC_SKILLS} only')
            if r['stat'] == 'follow_caster' and (any(name not in FOLLOW_SKILLS for name in names) or low != 1 or high != 1 or pieces):
                raise ValueError(f'{where}: follow_caster is one 1, on {FOLLOW_SKILLS} only, no set')
            if r['stat'] == 'duration_add_seconds' and (any(name not in DURATION_SKILLS for name in names) or len(names) != 1 or r['cond'] or r['fire_on'] or pieces):
                raise ValueError(f'{where}: duration_add_seconds is an item\'s, simply on, for one of the skills {DURATION_SKILLS}, which read it')
            if r['stat'] == 'resource_generation_pct' and (any(name not in GENERATION_SKILLS for name in names) or r['cond'] or r['fire_on'] or pieces or low <= 0):
                raise ValueError(f'{where}: resource_generation_pct is an item\'s, simply on, a positive number, for the skills {GENERATION_SKILLS}, which pay it')
            if r['stat'] == 'lasts_until_death' and (any(name not in UNTIL_DEATH_SKILLS for name in names) or len(names) != 1 or r['cond'] or r['fire_on'] or low != 1 or high != 1):
                raise ValueError(f'{where}: lasts_until_death is value 1, simply on, for one of the skills {UNTIL_DEATH_SKILLS}, whose summons read it')
            if r['stat'] in PART_STATS and (any(name not in PART_SKILLS for name in names) or len(names) != 1 or r['cond'] or r['fire_on'] or pieces):
                raise ValueError(f'{where}: {r["stat"]} is an item\'s, simply on, for one of the skills {PART_SKILLS}, whose code reads that part')
            if r['stat'] == 'summon_attack_speed_pct' and any(name not in SUMMON_SKILLS for name in names):
                raise ValueError(f"{where}: only {SUMMON_SKILLS}' summons read summon_attack_speed_pct")
            if r['stat'] in REUSE_STATS:
                if pieces or r['cond'] or r['fire_on'] or len(names) != 1 or names[0] not in REUSE_SKILLS or low != high:
                    raise ValueError(f'{where}: {r["stat"]} is an item\'s one fixed number, simply on, for one of the skills {REUSE_SKILLS}, which read it')
                if r['stat'] == 'reuse_casts' and (low < 2 or low != int(low)):
                    raise ValueError(f'{where}: reuse_casts is a whole number of casts, at least 2 (one cast has nothing to re-use)')
                if r['stat'] == 'reuse_window_seconds' and low <= 0:
                    raise ValueError(f'{where}: reuse_window_seconds is a positive number of seconds')
                if not all(any(o['owner'] == r['owner'] and o['skill'] == r['skill'] and o['stat'] == stat for o in sheet) for stat in REUSE_STATS):
                    raise ValueError(f'{where}: the two re-use rows {REUSE_STATS} go together, for one owner and skill')
            if r['stat'] in SPENT_STATS:
                if pieces or r['cond'] or r['fire_on'] or ';' in r['skill'] or r['skill'] not in SPENDING_SKILLS:
                    raise ValueError(f'{where}: a resource-spent row is an item\'s, simply on, for one of {SPENDING_SKILLS}')
                if r['stat'] == 'resource_spent_cap' and low != high:
                    raise ValueError(f'{where}: resource_spent_cap is one fixed number')
                if not all(any(o['owner'] == r['owner'] and o['skill'] == r['skill'] and o['stat'] == stat for o in sheet) for stat in SPENT_STATS):
                    raise ValueError(f'{where}: the two resource-spent rows {SPENT_STATS} go together, for one owner and skill')
            if pieces and low != high:
                raise ValueError(f'{where}: a set bonus is one number, value_min equals value_max')
        if r['kind'] == 'rune':
            if r['skill'] not in skills:
                raise ValueError(f"{where}: {r['skill']} is not a skill of a *_skills.csv sheet")
            if r['stat'] != 'all' and (r['skill'], r['stat']) not in runes:
                raise ValueError(f"{where}: {r['stat']} is not a rune of {r['skill']} in a *_runes.csv sheet (or 'all')")
            if low != high or low != 1:
                raise ValueError(f'{where}: a granted rune is value 1 (it is given or it is not)')
            if r['cond'] or r['fire_on']:
                raise ValueError(f'{where}: a granted rune is simply on')
        if r['kind'] == 'element':
            if r['skill'] not in ELEMENTS:
                raise ValueError(f"{where}: {r['skill']} is not an element of {ELEMENTS}")
            if r['stat'] not in ELEMENT_STATS:
                raise ValueError(f'{where}: an element stat is one of {ELEMENT_STATS}')
            if r['stat'] == 'cost_reduction_pct' and (r['cond'] or r['fire_on'] or high > 100):
                raise ValueError(f'{where}: a cost reduction is at most 100% and simply on while worn')
            if r['stat'] in PREVENT_STATS:
                if r['skill'] not in PREVENT_ELEMENTS or r['cond'] or r['fire_on'] or pieces or not 0 < low <= high <= 100 or (r['stat'] == 'damage_prevented_pct' and low != high):
                    raise ValueError(f'{where}: {r["stat"]} is an item\'s percent above 0 and at most 100, simply on, for an element of {PREVENT_ELEMENTS} (the prevented share is one fixed number)')
                if r['stat'] == 'heal_of_prevented_pct' and not any(o['owner'] == r['owner'] and o['kind'] == 'element' and o['skill'] == r['skill'] and o['stat'] == 'damage_prevented_pct' for o in sheet):
                    raise ValueError(f'{where}: a heal of the prevented damage needs its damage_prevented_pct row, for the same owner and element')
            if pieces and low != high:
                raise ValueError(f'{where}: a set bonus is one number, value_min equals value_max')
            if r['stat'] in DISTANCE_STATS:
                if pieces or r['cond'] or r['fire_on']:
                    raise ValueError(f'{where}: a distance row is an item\'s, simply on, with no condition or event')
                if r['stat'] != 'damage_per_distance_pct' and low != high:
                    raise ValueError(f'{where}: {r["stat"]} is one fixed number')
                mates = {o['stat']: o for o in sheet if o['owner'] == r['owner'] and o['kind'] == 'element' and o['skill'] == r['skill']
                         and o['stat'] in DISTANCE_STATS}
                if set(mates) != set(DISTANCE_STATS):
                    raise ValueError(f'{where}: the three distance rows {DISTANCE_STATS} go together, for one owner and element')
                if float(mates['distance_cap_yards']['value_min']) < float(mates['distance_step_yards']['value_min']):
                    raise ValueError(f'{where}: the cap is at least one step')
        if r['kind'] == 'buff':
            if r['stat'] not in BUFF_STATS:
                raise ValueError(f'{where}: a buff stat is one of {BUFF_STATS}')
            if (low != high and r['stat'] not in STACKED_BUFF_STATS) or pieces or r['cond'] or r['fire_on']:
                raise ValueError(f'{where}: a buff row is an item\'s one number per stack, with no condition or event of its own')
            if r['stat'] == 'skill_damage_pct' and (';' in r['skill'] or r['skill'] not in skills):
                raise ValueError(f'{where}: skill_damage_pct names one skill of a *_skills.csv sheet')
            if r['stat'] in STACKED_BUFF_STATS:
                stack = next((o for o in sheet if o['owner'] == r['owner'] and o['stat'] == 'stack_buff'), None)
                if stack and r['stat'] == 'damage_reduction_pct' and high * float(stack['stack_max'] or 0) >= 100:
                    raise ValueError(f'{where}: a reduction stays under 100% at stack_max')
                if not any(b[0] == r['owner'] for b in buffs):
                    raise ValueError(f'{where}: {r["stat"]} is read from the stacks of a record of its owner in legendary_power_buffs.csv')
            if not any(o['owner'] == r['owner'] and o['stat'] in ('stack_buff', 'bone_shield') for o in sheet):
                raise ValueError(f'{where}: a buff row needs the stack_buff (or bone_shield) effect row of the same item')
            if r['stat'] in NEGATIVE_BUFF_STATS and not high < 0:
                raise ValueError(f'{where}: {r["stat"]} is a penalty, below 0')
            if r['stat'] == 'attack_speed_floor_pct' and high > 100:
                raise ValueError(f'{where}: attack_speed_floor_pct is at most 100')
            # The armor and the slow are read from records of data/legendary_power_buffs.csv; the attack speed from the slow's stacks.
            want = {'armor_pct': 'dummy', 'movement_speed_pct': 'slow'}.get(r['stat'])
            if want and (r['owner'], r['stat'], want) not in buffs:
                raise ValueError(f'{where}: {r["stat"]} needs its {want} record in legendary_power_buffs.csv')
            if r['stat'] in ('attack_speed_pct', 'attack_speed_floor_pct') and not any(
                    o['owner'] == r['owner'] and o['kind'] == 'buff' and o['stat'] == 'movement_speed_pct' for o in sheet):
                raise ValueError(f'{where}: the attack speed is read from the slow\'s stacks: it needs a movement_speed_pct buff row')
        if r['kind'] == 'passive':
            if (r['skill'], r['stat']) not in PASSIVE_NUMBERS:
                raise ValueError(f'{where}: the code reads only the passive numbers {PASSIVE_NUMBERS}')
            if (r['skill'], r['stat']) not in passives:
                raise ValueError(f"{where}: {r['skill']} has no {r['stat']} in a *_passive_values.csv sheet")
            if low != high or r['cond'] or r['fire_on']:
                raise ValueError(f'{where}: a passive row is one number, simply on while worn (no range, condition or event)')
            if low <= passives[(r['skill'], r['stat'])]:
                raise ValueError(f"{where}: a passive row raises the passive's own number ({passives[(r['skill'], r['stat'])]:g}); one at or under it does nothing")
        if r['kind'] == 'immune':
            if r['stat'] not in IMMUNITIES:
                raise ValueError(f'{where}: an immunity is one of {IMMUNITIES}')
            if low != high or low != 1:
                raise ValueError(f'{where}: an immunity is value 1 (it is on or it is not)')
            if r['cond'] or r['fire_on']:
                raise ValueError(f'{where}: an immunity is simply on')
        if r['kind'] == 'player':
            if r['stat'] not in PLAYER_STATS:
                raise ValueError(f'{where}: a player stat is one of {PLAYER_STATS}')
            if r['stat'] == 'life_threshold_pct':
                if pieces or r['cond'] or r['fire_on']:
                    raise ValueError(f'{where}: life_threshold_pct is an item\'s percent, simply on (no condition, event or set level)')
                if high > 100:
                    raise ValueError(f'{where}: life_threshold_pct is at most 100')
                if low != high:
                    raise ValueError(f'{where}: life_threshold_pct is one fixed number')
                if not any(o['owner'] == r['owner'] and o['kind'] == 'effect' and o['stat'] == 'cast_skill' for o in sheet):
                    raise ValueError(f'{where}: life_threshold_pct is read by the life_below event of a cast_skill row of the same item: the two go together')
            if r['stat'] == 'slow_seconds':
                if pieces or low != high or r['cond'] or r['fire_on']:
                    raise ValueError(f'{where}: slow_seconds is an item\'s one fixed number, simply on (no condition, event or set level)')
                if not any(o['owner'] == r['owner'] and o['kind'] == 'effect' and o['stat'] in SLOW_EFFECTS for o in sheet):
                    raise ValueError(f'{where}: slow_seconds is read by a slow_pct row of the same item: the two go together')
            if r['stat'] == 'life_regen' and (pieces or r['cond'] != 'standing_still' or r['fire_on']):
                raise ValueError(f'{where}: life_regen is an item\'s number per stack of standing_still (the one reader, StandStill), with no set level or event')
            if r['stat'] == 'resource_threshold_pct' and (pieces or high > 100 or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: resource_threshold_pct is an item\'s percent, at most 100, with no condition or event')
            if r['stat'] == 'town_portal_bubble_pct' and (pieces or high >= 100 or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: town_portal_bubble_pct is an item\'s percent, below 100, with no set level, condition or event')
            if r['stat'] == 'stun_duration_pct' and (pieces or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: stun_duration_pct is an item\'s percent, with no set level, condition or event')
            if r['stat'] == 'shrine_seconds' and (pieces or low != high or low <= 0 or r['cond'] or r['fire_on']):
                raise ValueError(f'{where}: shrine_seconds is an item\'s one fixed number of seconds above 0, simply on (no condition, event or set level)')
            if r['stat'] == 'event_distance_yards' and (pieces or low != high or r['cond'] or r['fire_on'] or not any(
                    o['owner'] == r['owner'] and not o['pieces'] and o['fire_on'] == 'storm_armor_shock' for o in sheet)):
                raise ValueError(f'{where}: event_distance_yards is an item\'s fixed yards, with no condition or event, beside a storm_armor_shock row of the same item')
            if pieces and low != high:
                raise ValueError(f'{where}: a set bonus is one number, value_min equals value_max')
        if r['kind'] == 'effect' and pieces and low != high:
            raise ValueError(f'{where}: a set bonus is one number, value_min equals value_max')
        if not r['source']:
            raise ValueError(f'{where}: needs a source')
        out.append((r['owner'], pieces, r['kind'], r['skill'], r['stat'], low, high, r['cond'], arg, ';'.join(listed), every, int(most),
                    r['fire_on'], ';'.join(fire_skills), chance, icd))
    # A Bottomless potion's power (diablocraft-87qlt): kind `potion`, its `power_id` as the stat, the sheet's own range, so the
    # potion rolls it once in StageRoll. The potion sheet is the one source: legendary_powers.csv never names a potion power.
    # A potion with no range (Kulle-Aid, Chaos) has no row: its power is not built.
    for r in potions:
        if r['roll_min']:
            out.append((r['d3_id'], 0, 'potion', '', r['power_id'], float(r['roll_min']), float(r['roll_max']), '', 0.0, '', 0.0, 0,
                        '', '', 100.0, 0.0))
    return out


# The width of every text column of dc_legendary_power: the table is made from these and every row is checked against them, because MySQL refuses a value
# longer than its column ("Data too long", a render that stops the worldserver at startup) and nothing else in the tests applies the render.
COLUMN_WIDTHS = {'owner': 100, 'kind': 16, 'skill': 128, 'stat': 64, 'cond': 32, 'cond_skills': 255, 'fire_on': 32, 'fire_skills': 1024}
COLUMN_ORDER = ('owner', 'pieces', 'kind', 'skill', 'stat', 'value_min', 'value_max', 'cond', 'cond_arg', 'cond_skills', 'stack_seconds', 'stack_max',
                'fire_on', 'fire_skills', 'chance_pct', 'icd_seconds')


CREATE_TABLE = ("CREATE TABLE `dc_legendary_power` (owner VARCHAR({owner}) NOT NULL, pieces TINYINT UNSIGNED NOT NULL,"
                " kind VARCHAR({kind}) NOT NULL, skill VARCHAR({skill}) NOT NULL, stat VARCHAR({stat}) NOT NULL, value_min DOUBLE NOT NULL,"
                " value_max DOUBLE NOT NULL, cond VARCHAR({cond}) NOT NULL, cond_arg DOUBLE NOT NULL, cond_skills VARCHAR({cond_skills}) NOT NULL,"
                " stack_seconds DOUBLE NOT NULL, stack_max SMALLINT UNSIGNED NOT NULL, fire_on VARCHAR({fire_on}) NOT NULL,"
                " fire_skills VARCHAR({fire_skills}) NOT NULL, chance_pct DOUBLE NOT NULL, icd_seconds DOUBLE NOT NULL,"
                " PRIMARY KEY (owner, pieces, skill, stat, cond, fire_on)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n")


def check_widths(table):
    """Raise when any text cell of a row (the tuples `rows` returns) is longer than its column."""
    for row in table:
        for name, cell in zip(COLUMN_ORDER, row):
            width = COLUMN_WIDTHS.get(name)
            if width is not None and len(cell) > width:
                raise ValueError(f"{row[0]} {row[3]} {row[4]}: {name} is {len(cell)} characters, over the table's VARCHAR({width})")


def render(module=MODULE):
    q = lambda s: "'" + s.replace("'", "''") + "'"
    table = rows(module)
    check_widths(table)
    values = [f"({q(o)},{p},{q(k)},{q(sk)},{q(s)},{lo:g},{hi:g},{q(c)},{a:g},{q(cs)},{ss:g},{sm},{q(fo)},{q(fs)},{ch:g},{ic:g})"
              for o, p, k, sk, s, lo, hi, c, a, cs, ss, sm, fo, fs, ch, ic in table]
    sql = ("-- Generated by generate_legendary_powers.py from legendary_powers.csv; do not hand-edit.\n"
           "DROP TABLE IF EXISTS `dc_legendary_power`;\n" + CREATE_TABLE.format(**COLUMN_WIDTHS))
    if values:
        sql += "INSERT INTO `dc_legendary_power` (owner,pieces,kind,skill,stat,value_min,value_max,cond,cond_arg,cond_skills,stack_seconds,stack_max,fire_on,fire_skills,chance_pct,icd_seconds) VALUES\n" + ',\n'.join(values) + ';\n'
    return sql


def generate(module=MODULE):
    sql = render(module)
    (module / 'data/generated/legendary_powers_0075_table.sql').write_text(sql, encoding='utf-8', newline='\n')
    write_migration(module, module / 'data/sql/db-world/updates/legendary_powers_0075_table.sql', sql)


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()

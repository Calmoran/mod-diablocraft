#!/usr/bin/env python3
"""Emit the three rare follower relics the Blacksmith crafts: their base items, rare affix pools, bag items, Blacksmith recipes and
the drop switch.

Sheets (data/d3): followers_rare_relics.csv (one row for each follower: the generic rare relic, its Level 12 Blacksmith recipe and
how many affixes it rolls), followers_rare_relic_pools.csv (the Rare bracket of each relic kind, the columns of
followers_relic_pools.csv) and the rare_relic_drops row of followers_relic_rules.csv (0: craft-only; 1: the rare relics also drop). It also writes the relic_ancient_primal row of
the same sheet, which followers_0006 shipped at 0 (0: the relics are Legendary only; 1: they roll Ancient and Primal Ancient).

followers_0007_rare_relics.sql (world): dc_base_item rows 103309 to 103311 (generic bases, the way the ordinary rare gear is),
their dc_follower_relic rows (no fixed power), dc_follower_relic_roll rows (so a rare relic rolls like a relic: its own counts and the
Templar's block), the item_template bag items, the Rare rows of dc_affix_pool, the three dc_blacksmith_catalog recipes with their
materials and the rows of dc_follower_relic_rule of both switches. The recipes are not in blacksmith_catalog.csv: that sheet's
migration (crafting_0006) maps only the recipes whose output is a base item of base_item_ids.csv, and these three are not.
src/crafting/dc_crafting_shared.cpp Craft reads the catalogue, src/items/dc_items_roll.cpp rolls the relic.
"""
import csv
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration, write_coupled_outputs
import generate_follower_gear as follower_gear
import generate_follower_relics as relics

MODULE = Path(__file__).resolve().parents[3]
MIGRATION = 'followers_0007_rare_relics.sql'
SWITCH = 'rare_relic_drops'
# The other switch of the sheet, whose migration (followers_0006) shipped it at 0: the sheet's value is written here.
ANCIENT = 'relic_ancient_primal'
COLUMNS = ('d3_id', 'key', 'name', 'item_entry', 'displayid', 'recipe_sno', 'item_level', 'required_level', 'gold',
           'reusable_parts', 'arcane_dust', 'veiled_crystals', 'primary_affixes', 'secondary_affixes', 'source')
# The three materials of a Blacksmith recipe, as the sheet's columns and as the D3 ids blacksmith_catalog_materials.csv keys.
MATERIALS = (('reusable_parts', 'Crafting_AssortedParts_01'), ('arcane_dust', 'Crafting_Magic_01'),
             ('veiled_crystals', 'Crafting_Rare_01'))
RARE_COLUMNS = relics.POOL_COLUMNS
# Recipe, item and bag item quality: a Rare (yellow in D3, Rare in the item_template).
QUALITY_RARE = 3
RELIC_CLASS, RELIC_SUBCLASS = follower_gear.RELIC_CLASS, follower_gear.RELIC_SUBCLASS


def read(name, module=MODULE):
    return follower_gear.read(name, module)


def quote(text):
    return follower_gear.quote(text)


def material_entries(module=MODULE):
    """{D3 id: item entry} of the materials, from the Blacksmith catalogue's own sheet, one entry each."""
    out = {}
    for row in read('blacksmith_catalog_materials.csv', module):
        if out.setdefault(row['d3_id'], row['item_entry']) != row['item_entry']:
            raise ValueError(f"blacksmith_catalog_materials.csv: {row['d3_id']} has two item entries")
    return out


def sheet(module=MODULE):
    """followers_rare_relics.csv, checked: one dict for each follower, in followers_roster.csv order."""
    roster = follower_gear.roster(module)
    _, legendary = follower_gear.sheet(module)
    taken = follower_gear.taken_item_entries(module) | {r['entry'] for r in legendary}
    entries = material_entries(module)
    existing = {int(r['recipe_sno']) for r in read('blacksmith_catalog.csv', module)}
    rows = read('followers_rare_relics.csv', module)
    if rows and list(rows[0]) != list(COLUMNS):
        raise ValueError(f"followers_rare_relics.csv: the columns are {', '.join(COLUMNS)}")
    if [r['key'] for r in rows] != list(roster):
        raise ValueError(f"followers_rare_relics.csv: one row for each of {', '.join(roster)}, in that order")
    out, next_entry = [], max(r['entry'] for r in legendary) + 1
    for row in rows:
        where = f"followers_rare_relics.csv {row['key']}"
        if not row['name'] or not row['d3_id'] or not row['source']:
            raise ValueError(f'{where}: d3_id, name and source are required')
        entry = int(row['item_entry'])
        if entry != next_entry or entry in taken:
            raise ValueError(f'{where}: item_entry {entry} is not the next free one ({next_entry}) or is taken')
        next_entry += 1
        recipe = int(row['recipe_sno'])
        if not 0 < recipe <= 0xffffffff or recipe in existing:
            raise ValueError(f'{where}: recipe_sno {recipe} is out of range or already a Blacksmith recipe')
        existing.add(recipe)
        level, required = int(row['item_level']), int(row['required_level'])
        if not 0 < level <= 70 or not 0 < required <= 70:
            raise ValueError(f'{where}: item_level and required_level are 1 to 70')
        gold = int(relics.number(row['gold'], where, 0))
        primary = int(relics.number(row['primary_affixes'], where, 0))
        secondary = int(relics.number(row['secondary_affixes'], where, 0))
        if primary + secondary < 1:
            raise ValueError(f'{where}: at least one affix')
        costs = []
        for column, d3_id in MATERIALS:
            amount = int(relics.number(row[column], where, 1))
            if d3_id not in entries:
                raise ValueError(f'{where}: blacksmith_catalog_materials.csv has no {d3_id}')
            costs.append((d3_id, int(entries[d3_id]), amount))
        if not 0 < int(row['displayid']) < 2 ** 32:
            raise ValueError(f'{where}: displayid is a positive number')
        slot, kind = relics.SLOTS[row['key']]
        out.append(dict(follower=roster[row['key']]['id'], key=row['key'], d3_id=row['d3_id'], name=row['name'], entry=entry,
                        display=int(row['displayid']), recipe=recipe, level=level, required=required, gold=gold,
                        primary=primary, secondary=secondary, costs=costs, slot=slot, kind=kind))
    return out


def switch(module=MODULE, rule=SWITCH):
    """A row of followers_relic_rules.csv, checked: 0 or 1."""
    rows = [r for r in read('followers_relic_rules.csv', module) if r['rule'] == rule]
    if len(rows) != 1:
        raise ValueError(f'followers_relic_rules.csv: one {rule} row')
    row = rows[0]
    value = relics.number(row['value'], f'followers_relic_rules.csv {rule}', 0)
    if row['unit'] != 'flag' or value not in (0, 1) or not row['source']:
        raise ValueError(f'followers_relic_rules.csv {rule}: a flag, 0 or 1, with a source')
    return int(value)


def pools(module=MODULE):
    """followers_rare_relic_pools.csv, checked: the Rare rows, holding the affixes of each relic slot's Legendary pool."""
    legendary = {}
    for row in read('followers_relic_pools.csv', module):
        if row['item_level_bracket'] == 'legendary':
            legendary.setdefault(row['slot'], set()).add((row['affix_id'], row['kind']))
    rows, seen = read('followers_rare_relic_pools.csv', module), set()
    if not rows or list(rows[0]) != list(RARE_COLUMNS):
        raise ValueError(f"followers_rare_relic_pools.csv: the columns are {', '.join(RARE_COLUMNS)}")
    for row in rows:
        where = f"followers_rare_relic_pools.csv {row['slot']} {row['affix_id']}"
        if row['slot'] not in legendary or row['kind'] not in relics.KINDS or row['item_level_bracket'] != 'rare':
            raise ValueError(f"{where}: a relic slot ({', '.join(sorted(legendary))}), primary or secondary, and the bracket rare")
        low, high = relics.number(row['value_min'], where, 0), relics.number(row['value_max'], where, 0)
        if high < low or row['is_percent'] not in ('0', '1'):
            raise ValueError(f'{where}: value_max below value_min, or is_percent not 0 or 1')
        if not row['affix_name'] or not row['source_file']:
            raise ValueError(f'{where}: affix_name and source_file are required')
        key = (row['slot'], row['affix_id'])
        if key in seen:
            raise ValueError(f'{where}: repeated')
        seen.add(key)
    for slot, want in legendary.items():
        here = {(r['affix_id'], r['kind']) for r in rows if r['slot'] == slot}
        if here != want:
            raise ValueError(f'followers_rare_relic_pools.csv {slot}: the rare rows hold other affixes than the legendary ones')
    return rows


def render(module=MODULE):
    rares = sheet(module)
    drops = switch(module)
    ancient = switch(module, ANCIENT)
    entries = ', '.join(str(r['entry']) for r in rares)
    slots = ', '.join(quote(r['slot']) for r in rares)
    ids = ', '.join(str(r['recipe']) for r in rares)
    lines = ['-- Generated by generate_rare_relics.py from followers_rare_relics.csv, followers_rare_relic_pools.csv and '
             'followers_relic_rules.csv; do not hand-edit.',
             'SET NAMES utf8mb4;',
             f'DELETE FROM dc_follower_relic_roll WHERE item_entry IN ({entries});',
             f"DELETE FROM dc_follower_relic_rule WHERE rule IN ({quote(ANCIENT)}, {quote(SWITCH)});",
             f'DELETE FROM dc_follower_relic WHERE item_entry IN ({entries});',
             f'DELETE FROM dc_base_item WHERE entry IN ({entries});',
             f"DELETE FROM dc_affix_pool WHERE slot IN ({slots}) AND item_level_bracket = 'rare';",
             f'DELETE FROM dc_blacksmith_catalog_material WHERE recipe_id IN ({ids});',
             f'DELETE FROM dc_blacksmith_catalog WHERE id IN ({ids});',
             f'DELETE FROM item_template WHERE entry IN ({entries});']
    # A generic base (no rarity), as the ordinary rare gear is: the craft names the rarity. craft_only keeps it out of every drop
    # roll while the switch is 0.
    lines.append('INSERT INTO dc_base_item (entry, d3_id, d3_name, slot, type, rarity, usable_by, item_level, level_req, '
                 'weapon_min, weapon_max, weapon_aps, preset_affixes, set_name, source_file, pool_version, designated_class, '
                 'craft_only) VALUES\n'
                 + ',\n'.join(f"({r['entry']},{quote(r['d3_id'])},{quote(r['name'])},{quote(r['slot'])},{quote(r['kind'])},'','',"
                              f"{r['level']},{r['required']},NULL,NULL,NULL,'','','followers_rare_relics.csv','yes','',"
                              f"{quote('no' if drops else 'yes')})" for r in rares) + ';')
    # No fixed power: a rare relic only wears on its own follower (dc_follower_relic), rolls its own counts and, for the Templar's,
    # block (dc_follower_relic_roll, which has no drop of its own: weight 0, tier 0).
    lines.append('INSERT INTO dc_follower_relic (item_entry, follower_id, d3_id, name, power) VALUES\n'
                 + ',\n'.join(f"({r['entry']},{r['follower']},{quote(r['d3_id'])},{quote(r['name'])},'')" for r in rares) + ';')
    lines.append('INSERT INTO dc_follower_relic_roll (item_entry, primary_affixes, secondary_affixes, drop_weight, min_tier) VALUES\n'
                 + ',\n'.join(f"({r['entry']},{r['primary']},{r['secondary']},0,0)" for r in rares) + ';')
    lines.append('INSERT INTO dc_follower_relic_rule (rule, value, unit) VALUES\n'
                 + f"({quote(ANCIENT)},{ancient},'flag'),\n({quote(SWITCH)},{drops},'flag');")
    lines.append('INSERT INTO item_template (entry,class,subclass,name,displayid,Quality,Flags,BuyCount,BuyPrice,SellPrice,'
                 'InventoryType,maxcount,stackable,BagFamily,bonding,ItemLevel,description) VALUES\n'
                 + ',\n'.join(f"({r['entry']},{RELIC_CLASS},{RELIC_SUBCLASS},{quote(r['name'])},{r['display']},{QUALITY_RARE},"
                              f"0,1,0,0,0,0,1,0,0,{r['level']},'')" for r in rares) + ';')
    lines.append('INSERT INTO dc_affix_pool (slot, affix_id, affix_name, kind, value_min, value_max, value_step, '
                 'item_level_bracket, is_percent, source_file, display_order, value_min2, value_max2, weapon_class) VALUES\n'
                 + ',\n'.join(f"({quote(r['slot'])},{quote(r['affix_id'])},{quote(r['affix_name'])},{quote(r['kind'])},"
                              f"{relics.sql_value(r['value_min'])},{relics.sql_value(r['value_max'])},{relics.sql_value(r['value_step'])},"
                              f"{quote(r['item_level_bracket'])},{r['is_percent']},{quote(r['source_file'])},"
                              f"{int(r['display_order'])},{relics.sql_value(r['value_min2'])},{relics.sql_value(r['value_max2'])},"
                              f"{quote(r['weapon_class'])})" for r in pools(module)) + ';')
    # The Blacksmith's own tables (crafting_0006_blacksmith_catalog.sql creates them); page 'armor', rarity rare, no unavailable reason.
    lines.append('INSERT INTO dc_blacksmith_catalog (id,output_entry,name,slot,category,page,rarity,item_level,required_level,'
                 'gold_d3,enabled,unavailable_reason) VALUES\n'
                 + ',\n'.join(f"({r['recipe']},{r['entry']},{quote(r['name'])},{quote(r['slot'])},{quote(r['kind'])},'armor','rare',"
                              f"{r['level']},{r['required']},{r['gold']},1,'')" for r in rares) + ';')
    lines.append('INSERT INTO dc_blacksmith_catalog_material (recipe_id,d3_id,item_entry,amount) VALUES\n'
                 + ',\n'.join(f"({r['recipe']},{quote(d3_id)},{entry},{amount})" for r in rares
                              for d3_id, entry, amount in r['costs']) + ';')
    return '\n'.join(lines) + '\n'


def generate(module=MODULE):
    text = render(module)
    target = module / 'data/sql/db-world/updates' / MIGRATION
    write_migration(module, target, text)
    write_coupled_outputs(module, target, text, [(module / 'data/generated' / MIGRATION, text)], label='Rare follower relics')
    print('Generated rare follower relics')


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()

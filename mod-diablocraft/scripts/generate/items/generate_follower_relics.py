#!/usr/bin/env python3
"""Emit the follower relics' rolls: the nine relics as legendary base items, their affix pools, how many affixes they roll and
how they drop.

Sheets (data/d3): followers.csv (the nine relics: entry, name, power; read through generate_follower_gear.sheet),
followers_relic_rolls.csv (per relic: primary and secondary affix counts, drop weight, the lowest tier it drops at),
followers_relic_pools.csv (the pool of each relic kind, same columns as affix_pools.csv) and followers_relic_rules.csv (the one
switch: whether a relic may roll Ancient and Primal Ancient).

followers_0006_relic_rolls.sql (world): dc_base_item rows 103300 to 103308 (the entries followers_0005_gear.sql already gave the
bag items), dc_affix_pool rows of the three relic slots, dc_follower_relic_roll and dc_follower_relic_rule. The relics are
base items outside base_item_ids.csv (migration 0002 froze that table's sheet), the way the Bottomless potions are
(items_0015, items_0027). src/items/dc_items.cpp reads the roll table and the rule, src/loot/dc_loot.cpp the drop columns.
"""
import csv
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration, write_coupled_outputs
import generate_follower_gear as follower_gear

MODULE = Path(__file__).resolve().parents[3]
MIGRATION = 'followers_0006_relic_rolls.sql'
# The relic slot of each follower: d3planner's item type key (slots.js itemTypes), which is also the dc_base_item.slot
# and the dc_affix_pool.slot of its relics.
SLOTS = {'templar': ('templarrelic', 'Templar Relic'), 'scoundrel': ('scoundreltoken', 'Scoundrel Token'),
         'enchantress': ('enchantressfocus', 'Enchantress Focus')}
BRACKETS = ('legendary', 'ancient', 'primal')
KINDS = ('primary', 'secondary')
POOL_COLUMNS = ('slot', 'affix_id', 'affix_name', 'kind', 'value_min', 'value_max', 'value_step', 'item_level_bracket',
                'is_percent', 'source_file', 'display_order', 'value_min2', 'value_max2', 'weapon_class')
RULES = ('relic_ancient_primal',)
# Rows of the same sheet that another migration writes (generate_rare_relics.py).
OTHER_RULES = ('rare_relic_drops',)
# What this migration shipped: a later answer of the designer's moves the sheet, not a merged migration.
SHIPPED = {'relic_ancient_primal': 0}
# A relic is a legendary base; the level is the item level the sheet gives it (D3: drops at character level 61).
RARITY = 'legendary'


def read(name, module=MODULE):
    return follower_gear.read(name, module)


def quote(text):
    return follower_gear.quote(text)


def number(text, where, minimum=None):
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f'{where}: {text!r} is not a number') from None
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f'{where}: {text!r} is not a number of at least {minimum}')
    return value


def rolls(relics, module=MODULE):
    """followers_relic_rolls.csv, checked: {d3_id: (primary, secondary, weight, min_tier)}, one row for each relic."""
    out = {}
    ids = [r['d3_id'] for r in relics]
    for row in read('followers_relic_rolls.csv', module):
        where = f"followers_relic_rolls.csv {row['d3_id']}"
        if row['d3_id'] not in ids or row['d3_id'] in out:
            raise ValueError(f'{where}: not a relic of followers.csv, or repeated')
        if not row['source']:
            raise ValueError(f'{where}: source is required')
        primary = int(number(row['primary_affixes'], where, 0))
        secondary = int(number(row['secondary_affixes'], where, 0))
        weight = int(number(row['drop_weight'], where, 1))
        tier = int(number(row['min_tier'], where, 1))
        if primary + secondary < 1 or weight > 65535 or tier > 255:
            raise ValueError(f'{where}: at least one affix, a weight up to 65535, a tier up to 255')
        out[row['d3_id']] = (primary, secondary, weight, tier)
    if sorted(out) != sorted(ids):
        raise ValueError('followers_relic_rolls.csv: one row for each of the nine relics in followers.csv')
    return out


def pools(module=MODULE):
    """followers_relic_pools.csv, checked: the rows in file order, for the three relic slots."""
    slots = {slot for slot, _ in SLOTS.values()}
    rows, seen = read('followers_relic_pools.csv', module), set()
    if not rows or list(rows[0]) != list(POOL_COLUMNS):
        raise ValueError(f"followers_relic_pools.csv: the columns are {', '.join(POOL_COLUMNS)}")
    for row in rows:
        where = f"followers_relic_pools.csv {row['slot']} {row['affix_id']} {row['item_level_bracket']}"
        if row['slot'] not in slots or row['kind'] not in KINDS or row['item_level_bracket'] not in BRACKETS:
            raise ValueError(f"{where}: a relic slot ({', '.join(sorted(slots))}), primary or secondary, "
                             f"and the bracket {', '.join(BRACKETS)}")
        low, high = number(row['value_min'], where, 0), number(row['value_max'], where, 0)
        if high < low or row['is_percent'] not in ('0', '1'):
            raise ValueError(f'{where}: value_max below value_min, or is_percent not 0 or 1')
        if not row['affix_name'] or not row['source_file']:
            raise ValueError(f'{where}: affix_name and source_file are required')
        key = (row['slot'], row['affix_id'], row['item_level_bracket'])
        if key in seen:
            raise ValueError(f'{where}: repeated')
        seen.add(key)
    for slot in slots:
        mine = {(r['affix_id'], r['kind']) for r in rows if r['slot'] == slot}
        for bracket in BRACKETS:
            here = {(r['affix_id'], r['kind']) for r in rows if r['slot'] == slot and r['item_level_bracket'] == bracket}
            if here != mine:
                raise ValueError(f'followers_relic_pools.csv {slot}: the {bracket} bracket holds other affixes than the rest')
    return rows


def rules(module=MODULE):
    # The sheet also holds rare_relic_drops, which generate_rare_relics.py writes; this migration keeps its one switch.
    rows = [r for r in read('followers_relic_rules.csv', module) if r['rule'] not in OTHER_RULES]
    if [r['rule'] for r in rows] != list(RULES):
        raise ValueError(f"followers_relic_rules.csv: the rules are {', '.join(RULES)}, in that order")
    out = []
    for row in rows:
        value = number(row['value'], f"followers_relic_rules.csv {row['rule']}", 0)
        if row['unit'] != 'flag' or value not in (0, 1) or not row['source']:
            raise ValueError(f"followers_relic_rules.csv {row['rule']}: a flag, 0 or 1, with a source")
        # followers_0006 is merged with the switch at 0; the sheet's current value is written by followers_0007_rare_relics.sql.
        out.append((row['rule'], SHIPPED[row['rule']], row['unit']))
    return out


def sql_value(text):
    return 'NULL' if text == '' else format(float(text), '.15g')


def render(module=MODULE):
    _, relics = follower_gear.sheet(module)
    rolled = rolls(relics, module)
    entries = [r['entry'] for r in relics]
    slots = ', '.join(quote(slot) for slot, _ in SLOTS.values())
    lines = ['-- Generated by generate_follower_relics.py from followers.csv, followers_relic_rolls.csv, followers_relic_pools.csv '
             'and followers_relic_rules.csv; do not hand-edit.',
             'SET NAMES utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_follower_relic_roll (item_entry INT UNSIGNED NOT NULL PRIMARY KEY, primary_affixes '
             'TINYINT UNSIGNED NOT NULL, secondary_affixes TINYINT UNSIGNED NOT NULL, drop_weight SMALLINT UNSIGNED NOT NULL, '
             'min_tier TINYINT UNSIGNED NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_follower_relic_rule (rule VARCHAR(32) NOT NULL PRIMARY KEY, value DOUBLE NOT NULL, '
             'unit VARCHAR(16) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
             'DELETE FROM dc_follower_relic_roll;', 'DELETE FROM dc_follower_relic_rule;',
             f'DELETE FROM dc_base_item WHERE entry IN ({", ".join(str(e) for e in entries)});',
             f'DELETE FROM dc_affix_pool WHERE slot IN ({slots});']
    lines.append('INSERT INTO dc_follower_relic_roll (item_entry, primary_affixes, secondary_affixes, drop_weight, min_tier) VALUES\n'
                 + ',\n'.join(f"({r['entry']},{rolled[r['d3_id']][0]},{rolled[r['d3_id']][1]},{rolled[r['d3_id']][2]},"
                              f"{rolled[r['d3_id']][3]})" for r in relics) + ';')
    lines.append('INSERT INTO dc_follower_relic_rule (rule, value, unit) VALUES\n'
                 + ',\n'.join(f'({quote(n)},{v},{quote(u)})' for n, v, u in rules(module)) + ';')
    # No usable_by and no designated class: a relic drops for any roll class (D3 ties it to no hired follower), and
    # dc_follower_relic is what keeps it to its own follower. pool_version yes puts it in the drop pool.
    lines.append('INSERT INTO dc_base_item (entry, d3_id, d3_name, slot, type, rarity, usable_by, item_level, level_req, '
                 'weapon_min, weapon_max, weapon_aps, preset_affixes, set_name, source_file, pool_version, designated_class, '
                 'craft_only) VALUES\n'
                 + ',\n'.join(f"({r['entry']},{quote(r['d3_id'])},{quote(r['name'])},{quote(SLOTS[r['key']][0])},"
                              f"{quote(SLOTS[r['key']][1])},{quote(RARITY)},'',{r['level']},{r['level']},NULL,NULL,NULL,'','',"
                              f"'followers.csv','yes','','no')" for r in relics) + ';')
    lines.append('INSERT INTO dc_affix_pool (slot, affix_id, affix_name, kind, value_min, value_max, value_step, '
                 'item_level_bracket, is_percent, source_file, display_order, value_min2, value_max2, weapon_class) VALUES\n'
                 + ',\n'.join(f"({quote(r['slot'])},{quote(r['affix_id'])},{quote(r['affix_name'])},{quote(r['kind'])},"
                              f"{sql_value(r['value_min'])},{sql_value(r['value_max'])},{sql_value(r['value_step'])},"
                              f"{quote(r['item_level_bracket'])},{r['is_percent']},{quote(r['source_file'])},"
                              f"{int(r['display_order'])},{sql_value(r['value_min2'])},{sql_value(r['value_max2'])},"
                              f"{quote(r['weapon_class'])})" for r in pools(module)) + ';')
    return '\n'.join(lines) + '\n'


def generate(module=MODULE):
    text = render(module)
    target = module / 'data/sql/db-world/updates' / MIGRATION
    write_migration(module, target, text)
    write_coupled_outputs(module, target, text, [(module / 'data/generated' / MIGRATION, text)], label='Follower relics')
    print('Generated follower relics')


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()

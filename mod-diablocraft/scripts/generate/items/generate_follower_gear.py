#!/usr/bin/env python3
"""Emit the followers' gear rows: what each follower may wear, its skills and tiers, its relics, and the stat rules.

Sheets (data/d3): followers.csv (the skills with their tiers, and the nine relic items), followers_gear.csv (which item kinds
go in which of a follower's 14 slots), followers_gear_rules.csv (the main stat multiplier, the crit damage cap, the share
to the player) and followers_stats.csv (the affixes a follower ignores and the ones it shares with its player).

followers_0005_gear.sql (world): dc_follower_gear_follower, dc_follower_gear_kind, dc_follower_skill, dc_follower_relic, dc_follower_gear_rule,
dc_follower_stat, and the nine relics' item_template rows. src/items/dc_follower_gear.cpp reads the tables at startup; the
relics are fixed bag items outside dc_base_item (migration 0002 froze that table), so a relic has no rolled affixes.

followers_0002_character_gear.sql (characters) is a schema migration and is hand-written: dc_character_follower_gear.
"""
import csv
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration, write_coupled_outputs

MODULE = Path(__file__).resolve().parents[3]
MIGRATION = 'followers_0005_gear.sql'
KEYS = ('templar', 'scoundrel', 'enchantress')
MAIN_STATS = ('strength', 'dexterity', 'intelligence')
# The 14 slots of a follower (R1a section 1), in the order the Follower window lists them.
SLOTS = ('relic', 'head', 'shoulders', 'chest', 'gloves', 'bracers', 'belt', 'pants', 'boots', 'ring1', 'ring2', 'neck',
         'mainhand', 'offhand')
# The slots a base item can go in; the relic slot holds the follower items, which are not base items.
ARMOUR_SLOTS = SLOTS[1:12]
POWERS = ('cannot_die', 'all_skills', 'cooldown_half')
TREATMENTS = ('ignored', 'shared')
RULES = ('main_stat_multiplier', 'crit_damage_cap_pct', 'player_share_pct')
TIERS = (1, 2, 3, 4)
# The D3 level each tier unlocks at (R1a section 5): the Enchantress joins later in the campaign.
TIER_LEVELS = {'templar': (5, 10, 15, 20), 'scoundrel': (5, 10, 15, 20), 'enchantress': (15, 20, 25, 30)}
RELIC_ENTRY_FIRST = 103300
RELIC_QUALITY = 5
# Misc / Junk: a relic is carried in the bags and worn only by a follower, so it has no inventory type to equip.
RELIC_CLASS, RELIC_SUBCLASS = 15, 0


def read(name, module=MODULE):
    with (module / 'data/d3' / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream, strict=True))


def quote(text):
    return "'" + str(text).replace('\\', '\\\\').replace("'", "''") + "'"


def roster(module=MODULE):
    rows = read('followers_roster.csv', module)
    if [r['key'] for r in rows] != list(KEYS):
        raise ValueError(f"followers_roster.csv: the rows are {', '.join(KEYS)}, in that order")
    return {r['key']: dict(id=int(r['follower_id']), main=r['main_stat']) for r in rows}


def taken_item_entries(module=MODULE):
    """Item entries other sheets already hold, so a relic never lands on one."""
    taken = {int(r['item_entry']) for r in read('base_item_ids.csv', module)}
    taken |= {int(r['item_entry']) for r in read('account_economy.csv', module) if r['kind'] == 'material'}
    import persistent_ids
    taken |= set(persistent_ids.gem_items(module, read('gems.csv', module)).values())
    organs = module / 'data/d3/hellfire_organs.csv'
    if organs.exists():
        taken |= {int(r['item_entry']) for r in read('hellfire_organs.csv', module)}
    return taken


def sheet(module=MODULE):
    """followers.csv, checked: (skills, relics), each a list of dicts."""
    followers = roster(module)
    skills, relics, seen = [], [], set()
    entries = taken_item_entries(module)
    next_entry = RELIC_ENTRY_FIRST
    for row in read('followers.csv', module):
        where = f"followers.csv {row['key']} {row['kind']} {row['skill_id']}"
        follower = followers.get(row['key'])
        if not follower or row['follower_id'] != str(follower['id']):
            raise ValueError(f'{where}: follower_id does not match followers_roster.csv')
        if not row['name'] or not row['source'] or not row['text']:
            raise ValueError(f'{where}: name, text and source are required')
        if (row['key'], row['kind'], row['skill_id']) in seen:
            raise ValueError(f'{where}: repeated')
        seen.add((row['key'], row['kind'], row['skill_id']))
        if row['kind'] == 'skill':
            tier = int(row['tier'])
            if tier not in TIERS or int(row['d3_level']) != TIER_LEVELS[row['key']][tier - 1]:
                raise ValueError(f'{where}: tier {row["tier"]} and d3_level {row["d3_level"]} disagree with R1a section 5')
            if row['scales_with'] not in ('', follower['main']):
                raise ValueError(f"{where}: a follower's skills scale with its own main stat ({follower['main']})")
            cooldown = float(row['cooldown_seconds']) if row['cooldown_seconds'] else None
            if cooldown is not None and not (math.isfinite(cooldown) and cooldown > 0):
                raise ValueError(f'{where}: cooldown_seconds is a positive number')
            if row['item_entry'] or row['power']:
                raise ValueError(f'{where}: a skill row carries no item columns')
            skills.append(dict(follower=follower['id'], key=row['key'], tier=tier, level=int(row['d3_level']),
                               skill=row['skill_id'], name=row['name'], cooldown=cooldown, scales=row['scales_with'],
                               weapon=row['requires_weapon'], text=row['text']))
        elif row['kind'] == 'relic':
            entry = int(row['item_entry'])
            if entry != next_entry or entry in entries:
                raise ValueError(f'{where}: item_entry {entry} is not the next free one ({next_entry}) or is taken')
            next_entry += 1
            entries.add(entry)
            if row['power'] not in POWERS:
                raise ValueError(f"{where}: power is one of {', '.join(POWERS)}")
            if row['tier'] or row['d3_level'] or row['cooldown_seconds'] or row['scales_with'] or row['requires_weapon']:
                raise ValueError(f'{where}: a relic row carries no skill columns')
            if not 0 < int(row['displayid']) < 2 ** 32 or not 1 <= int(row['drop_level']) <= 70:
                raise ValueError(f'{where}: displayid and drop_level are positive numbers (level 1 to 70)')
            relics.append(dict(follower=follower['id'], key=row['key'], entry=entry, d3_id=row['skill_id'],
                               name=row['name'], power=row['power'], display=int(row['displayid']),
                               level=int(row['drop_level']), text=row['text']))
        else:
            raise ValueError(f'{where}: kind is skill or relic')
    for key, follower in followers.items():
        mine = [s for s in skills if s['key'] == key]
        if sorted(s['tier'] for s in mine) != [1, 1, 2, 2, 3, 3, 4, 4]:
            raise ValueError(f'followers.csv {key}: eight skills, two in each of the four tiers')
        if sorted(r['power'] for r in relics if r['key'] == key) != sorted(POWERS):
            raise ValueError(f'followers.csv {key}: one relic for each of the three powers')
    return skills, relics


def gear(module=MODULE):
    """followers_gear.csv, checked against base_items.csv: [(follower id, gear slot, item slot, item type)]."""
    followers = roster(module)
    kinds = {(r['slot'], r['type']): r for r in read('base_items.csv', module)}
    out, seen = [], set()
    for row in read('followers_gear.csv', module):
        where = f"followers_gear.csv {row['key']} {row['gear_slot']} {row['item_type']}"
        follower = followers.get(row['key'])
        if not follower or row['follower_id'] != str(follower['id']):
            raise ValueError(f'{where}: follower_id does not match followers_roster.csv')
        if row['gear_slot'] not in SLOTS or row['gear_slot'] == 'relic':
            raise ValueError(f'{where}: gear_slot is one of the base-item slots {", ".join(SLOTS[1:])}')
        if (row['item_slot'], row['item_type']) not in kinds:
            raise ValueError(f'{where}: base_items.csv has no {row["item_slot"]} {row["item_type"]}')
        if row['gear_slot'] in ARMOUR_SLOTS and row['item_slot'] in ('onehand', 'twohand', 'offhand'):
            raise ValueError(f'{where}: a weapon in an armour slot')
        if row['gear_slot'] in ('mainhand', 'offhand') and row['item_slot'] not in ('onehand', 'twohand', 'offhand'):
            raise ValueError(f'{where}: armour in a hand')
        if not row['source']:
            raise ValueError(f'{where}: source is required')
        key = (row['key'], row['gear_slot'], row['item_slot'], row['item_type'])
        if key in seen:
            raise ValueError(f'{where}: repeated')
        seen.add(key)
        out.append((follower['id'], row['gear_slot'], row['item_slot'], row['item_type']))
    for key, follower in followers.items():
        mine = {g for f, g, _, _ in out if f == follower['id']}
        if not set(ARMOUR_SLOTS) | {'mainhand'} <= mine:
            raise ValueError(f'followers_gear.csv {key}: every armour slot and the main hand need a kind')
        if 'offhand' in mine and key != 'templar':
            raise ValueError(f'followers_gear.csv {key}: only the Templar has an off-hand (R1a section 1)')
    return out


def rules(module=MODULE):
    rows = read('followers_gear_rules.csv', module)
    if [r['rule'] for r in rows] != list(RULES):
        raise ValueError(f"followers_gear_rules.csv: the rules are {', '.join(RULES)}, in that order")
    out = []
    for row in rows:
        value = float(row['value'])
        if not math.isfinite(value) or value <= 0 or not row['unit'] or not row['source']:
            raise ValueError(f"followers_gear_rules.csv {row['rule']}: a positive value, a unit and a source")
        out.append((row['rule'], format(value, '.15g'), row['unit']))
    return out


def stats(module=MODULE):
    out, seen = [], set()
    for row in read('followers_stats.csv', module):
        if row['treatment'] not in TREATMENTS or row['affix_id'] in seen or not row['source']:
            raise ValueError(f"followers_stats.csv {row['affix_id']}: treatment {'/'.join(TREATMENTS)}, once, with a source")
        seen.add(row['affix_id'])
        out.append((row['affix_id'], row['treatment']))
    return out


def render(module=MODULE):
    skills, relics = sheet(module)
    lines = ['-- Generated by generate_follower_gear.py from followers.csv, followers_gear.csv, followers_gear_rules.csv and '
             'followers_stats.csv; do not hand-edit.',
             'SET NAMES utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_follower_gear_follower (follower_id TINYINT UNSIGNED NOT NULL PRIMARY KEY, '
             'follower_key VARCHAR(16) NOT NULL, main_stat VARCHAR(12) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_follower_gear_kind (follower_id TINYINT UNSIGNED NOT NULL, gear_slot VARCHAR(12) '
             'NOT NULL, item_slot VARCHAR(12) NOT NULL, item_type VARCHAR(40) NOT NULL, '
             'PRIMARY KEY (follower_id, gear_slot, item_slot, item_type)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_follower_skill (follower_id TINYINT UNSIGNED NOT NULL, tier TINYINT UNSIGNED NOT NULL, '
             'd3_level TINYINT UNSIGNED NOT NULL, skill_id VARCHAR(32) NOT NULL, name VARCHAR(64) NOT NULL, '
             'cooldown_seconds DOUBLE NULL, scales_with VARCHAR(16) NOT NULL, requires_weapon VARCHAR(16) NOT NULL, '
             'text VARCHAR(512) NOT NULL, PRIMARY KEY (follower_id, skill_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_follower_relic (item_entry INT UNSIGNED NOT NULL PRIMARY KEY, follower_id TINYINT '
             'UNSIGNED NOT NULL, d3_id VARCHAR(64) NOT NULL, name VARCHAR(64) NOT NULL, power VARCHAR(16) NOT NULL) '
             'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_follower_gear_rule (rule VARCHAR(32) NOT NULL PRIMARY KEY, value DOUBLE NOT NULL, '
             'unit VARCHAR(16) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_follower_stat (affix_id VARCHAR(16) NOT NULL PRIMARY KEY, treatment VARCHAR(8) '
             'NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
             'DELETE FROM dc_follower_gear_follower;', 'DELETE FROM dc_follower_gear_kind;', 'DELETE FROM dc_follower_skill;', 'DELETE FROM dc_follower_relic;',
             'DELETE FROM dc_follower_gear_rule;', 'DELETE FROM dc_follower_stat;']
    kinds = gear(module)
    lines.append('INSERT INTO dc_follower_gear_follower (follower_id, follower_key, main_stat) VALUES\n'
                 + ',\n'.join(f"({f['id']},{quote(k)},{quote(f['main'])})" for k, f in roster(module).items()) + ';')
    lines.append('INSERT INTO dc_follower_gear_kind (follower_id, gear_slot, item_slot, item_type) VALUES\n'
                 + ',\n'.join(f'({f},{quote(g)},{quote(s)},{quote(t)})' for f, g, s, t in kinds) + ';')
    lines.append('INSERT INTO dc_follower_skill (follower_id, tier, d3_level, skill_id, name, cooldown_seconds, scales_with, '
                 'requires_weapon, text) VALUES\n'
                 + ',\n'.join(f"({s['follower']},{s['tier']},{s['level']},{quote(s['skill'])},{quote(s['name'])},"
                              f"{'NULL' if s['cooldown'] is None else format(s['cooldown'], '.15g')},{quote(s['scales'])},"
                              f"{quote(s['weapon'])},{quote(s['text'])})" for s in skills) + ';')
    lines.append('INSERT INTO dc_follower_relic (item_entry, follower_id, d3_id, name, power) VALUES\n'
                 + ',\n'.join(f"({r['entry']},{r['follower']},{quote(r['d3_id'])},{quote(r['name'])},{quote(r['power'])})"
                              for r in relics) + ';')
    lines.append('INSERT INTO dc_follower_gear_rule (rule, value, unit) VALUES\n'
                 + ',\n'.join(f'({quote(n)},{v},{quote(u)})' for n, v, u in rules(module)) + ';')
    lines.append('INSERT INTO dc_follower_stat (affix_id, treatment) VALUES\n'
                 + ',\n'.join(f'({quote(a)},{quote(t)})' for a, t in stats(module)) + ';')
    # Plain bag items (class Misc, quality Legendary, no inventory type); the power line is the tooltip's description.
    lines.append('DELETE FROM item_template WHERE entry IN (%s);' % ','.join(str(r['entry']) for r in relics))
    lines.append('INSERT INTO item_template (entry,class,subclass,name,displayid,Quality,Flags,BuyCount,BuyPrice,SellPrice,'
                 'InventoryType,maxcount,stackable,BagFamily,bonding,ItemLevel,description) VALUES\n'
                 + ',\n'.join(f"({r['entry']},{RELIC_CLASS},{RELIC_SUBCLASS},{quote(r['name'])},{r['display']},{RELIC_QUALITY},"
                              f"0,1,0,0,0,0,1,0,0,{r['level']},{quote(r['text'])})" for r in relics) + ';')
    return '\n'.join(lines) + '\n'


def generate(module=MODULE):
    text = render(module)
    target = module / 'data/sql/db-world/updates' / MIGRATION
    write_migration(module, target, text)
    write_coupled_outputs(module, target, text, [(module / 'data/generated' / MIGRATION, text)], label='Follower gear')
    print('Generated follower gear')


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()

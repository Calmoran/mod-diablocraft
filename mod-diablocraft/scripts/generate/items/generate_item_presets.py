#!/usr/bin/env python3
"""Per-item preset ranges (diablocraft-6pmeb, extended by diablocraft-jh08v): an item's fixed stat that its slot's pool does not hold.

The roller takes a base item's presets from its slot's pool (dc_affix_pool) and skips one the pool has no row for, so
a fixed stat outside the slot (The Witching Hour's attack speed and crit damage on a belt) never rolled. A row of
data/d3/item_preset_ranges.csv gives that one item that one stat's range per bracket, sourced from d3planner; the
roller takes it only as that item's preset and never adds it to any fill pool. Writes:

  world   items_0054_item_preset_ranges_mana.sql       refills dc_item_preset_range from the sheet
                                                       (items_0024 created the table with its first six rows)
  world   items_0048_affix_metadata_wrath.sql          dc_affix_metadata

    python3 mod-diablocraft/scripts/generate/items/generate_item_presets.py [--migration <new>.sql] [--metadata-migration <new>.sql]

Both files are the whole table, so a later file supersedes an earlier one. items_0025 (the sheet) and items_0031 (the
metadata) are on nightly and keep their bytes; a changed sheet ships as a new numbered world migration that --migration
or --metadata-migration names, as generate_cube.py does (decisions.md 2026-10-16, the Cube numbering). items_0033 and
items_0034 carry the preset sweep (the pool-rolled legendary and set presets no pool row, sheet row or metadata row
named); items_0037 adds the sweep's last two lines, Holy Beacon's Holy damage and Bombardier's Rucksack's Dexterity
(the designer, q-1016-14; diablocraft-dw6gz), and items_0033 keeps its bytes. items_0038 is the sheet after both, with
Windforce's maxdisc and Wizardspike's maxap (diablocraft-a0avr) beside 0037's rows. items_0039 is the sheet after
those, with the per-class `resource` rows, and items_0036 adds Maximum Spirit (diablocraft-4ruv4). items_0042 and
items_0043 add the Necromancer's Maximum Essence rows and metadata (diablocraft-im7mr.1). items_0045 is the sheet after
those, with the ethereals' Damage to Undead, Damage to Demons and Arcane Power on Critical Hit (diablocraft-e601d).
items_0047 and items_0048 add the Crusader's Maximum Wrath rows and metadata (diablocraft-jigw7). items_0051 is the sheet
after those, with the Demon Hunter's Maximum Discipline rows on Stone of Jordan and Lidless Wall (diablocraft-vawmy.4;
the metadata, items_0048, already holds maxdisc). items_0054 is the sheet after those, with the Witch Doctor's Maximum Mana rows on the same two items
(diablocraft-vxrcu.1; the metadata, items_0036, already holds maxmana).

A row's rarity must be one the item can actually read (dc_quality_rule.h Bracket/Eligible): legendary, set and
ethereal read the legendary bracket, only legendary and set are ever ancient or primal (diablocraft-jh08v).

data/d3/affix_metadata.csv names a stat no slot's pool holds (the seven elemental damages, Bonus Experience, Magic
Find, ...): its name, kind, percent and display order, from d3planner's data_stats.js. A sheet row for such a stat
must say the name, kind and percent the metadata says (its display order is the item's own line position, the
metadata's the fallback), unless it is the item's own fixed stat. It is metadata only: no pool row, so nothing
rolls it at random.

An item whose presets list `resource` (Stone of Jordan, Lidless Wall: D3's "Maximum <the wearer's resource>") carries
one row per class under the stat's own code, named "Maximum <that class's resource>" as class_resources.csv names the
resource; the roller takes the roll class's row (dc_resource_affix_rule.h, diablocraft-4ruv4).
"""
import csv
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import require_companion_migration, write_migration

MODULE = Path(__file__).resolve().parents[3]
D3 = MODULE / 'data/d3'
UPDATES = MODULE / 'data/sql/db-world/updates'
MIGRATION = UPDATES / 'items_0054_item_preset_ranges_mana.sql'
METADATA_MIGRATION = UPDATES / 'items_0048_affix_metadata_wrath.sql'
TABLE = 'dc_item_preset_range'
# A row for the item's own fixed stat (its attribute, a built skill) names itself in its source; the metadata sheet
# holds only the stats that carry no such row.
OWN_STAT = "the item's own fixed stat"
BRACKETS = ('legendary', 'ancient', 'primal')
KINDS = ('primary', 'secondary')
# dc_quality_rule.h:47-52 Bracket: these three read the legendary bracket. :20-23 Eligible: only the first two
# are ever ancient or primal, so a row for an ethereal at those brackets would be dead data.
LEGENDARY_BRACKET = ('legendary', 'set', 'ethereal')
ANCIENT_BRACKET = ('legendary', 'set')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream, strict=True))


def number(text):
    value = float(text)
    return int(value) if value == int(value) else value


def metadata(d3=D3):
    """affix_metadata.csv by affix id: (name, kind, is_percent, display_order), for stats no slot's pool holds."""
    pooled = {r['affix_id'] for r in read(d3 / 'affix_pools.csv')}
    out = {}
    for r in read(d3 / 'affix_metadata.csv'):
        where = f"affix_metadata.csv {r['affix_id']}"
        if r['affix_id'] in out:
            raise ValueError(f'{where}: listed twice')
        if r['affix_id'] in pooled:
            raise ValueError(f"{where}: a pool row holds it; the pool's row is its metadata")
        if r['kind'] not in KINDS or r['is_percent'] not in ('0', '1') or not r['display_order'].isdigit():
            raise ValueError(f'{where}: kind must be one of {KINDS}, is_percent 0 or 1, display_order a number')
        if not r['affix_name'].strip() or not r['source'].strip():
            raise ValueError(f'{where}: no name, or no source')
        out[r['affix_id']] = (r['affix_name'], r['kind'], int(r['is_percent']), int(r['display_order']))
    return out


def resource_names(d3=D3):
    """The affix names a `resource` preset row may carry: "Maximum <d3_name>" for every class_resources.csv row."""
    return {f"Maximum {r['d3_name']}" for r in read(d3 / 'class_resources.csv')}


def rows(d3=D3):
    """The sheet's rows, each checked against the base item it names, that item's slot pool and, for a stat no pool
    holds, affix_metadata.csv."""
    bases = {r['d3_id']: r for r in read(d3 / 'base_items.csv')}
    entries = {r['d3_id']: int(r['item_entry']) for r in read(d3 / 'base_item_ids.csv')}
    pool = {(r['slot'], r['affix_id'], r['item_level_bracket']) for r in read(d3 / 'affix_pools.csv')}
    pooled = {affix for _, affix, _ in pool}
    meta = metadata(d3)
    maximums = resource_names(d3)
    out, seen = [], set()
    for r in read(d3 / 'item_preset_ranges.csv'):
        where = f"item_preset_ranges.csv {r['d3_id']} {r['affix_id']} {r['item_level_bracket']}"
        base = bases.get(r['d3_id'])
        if not base or r['d3_id'] not in entries:
            raise ValueError(f'{where}: no base_items.csv/base_item_ids.csv row')
        if base['pool_version'] != 'yes':
            raise ValueError(f'{where}: not a pool-rolled item')
        if base['rarity'] not in LEGENDARY_BRACKET:
            raise ValueError(f"{where}: a {base['rarity']!r} item reads no bracket this sheet models "
                             f'(dc_quality_rule.h Bracket)')
        if r['item_level_bracket'] in ('ancient', 'primal') and base['rarity'] not in ANCIENT_BRACKET:
            raise ValueError(f"{where}: a {base['rarity']} item is never {r['item_level_bracket']} "
                             f'(dc_quality_rule.h Eligible)')
        presets = base['preset_affixes'].split(';')
        if r['affix_id'] not in presets and not ('resource' in presets and r['affix_name'] in maximums):
            raise ValueError(f"{where}: not one of the item's preset_affixes, nor a Maximum <class resource> row "
                             "for its resource preset")
        if r['item_level_bracket'] not in BRACKETS or r['kind'] not in KINDS:
            raise ValueError(f'{where}: bracket must be one of {BRACKETS}, kind one of {KINDS}')
        if (base['slot'], r['affix_id'], r['item_level_bracket']) in pool:
            raise ValueError(f"{where}: the {base['slot']} pool already holds it; the pool's row is the range")
        low, high = number(r['value_min']), number(r['value_max'])
        if low > high or not r['source'].strip():
            raise ValueError(f'{where}: value_min above value_max, or no source')
        key = (r['d3_id'], r['affix_id'], r['item_level_bracket'])
        if key in seen:
            raise ValueError(f'{where}: listed twice')
        seen.add(key)
        said = (r['affix_name'], r['kind'], int(r['is_percent']), int(r['display_order']))
        own = OWN_STAT in r['source']
        if r['affix_id'] not in pooled and r['affix_id'] not in meta and not own:
            raise ValueError(f'{where}: no pool row in any slot and no affix_metadata.csv row')
        if r['affix_id'] in meta and r['affix_id'] not in pooled and not own and said[:3] != meta[r['affix_id']][:3]:
            raise ValueError(f"{where}: name, kind or is_percent is not affix_metadata.csv's")
        step = number(r['value_step']) if r['value_step'] else None
        out.append((entries[r['d3_id']], r['affix_id'], r['affix_name'], r['kind'], low, high, step,
                    r['item_level_bracket'], int(r['is_percent']), int(r['display_order'])))
    return sorted(out)


def sql(presets):
    def literal(value):
        if value is None:
            return 'NULL'
        return "'" + value.replace("'", "''") + "'" if isinstance(value, str) else str(value)
    lines = ['-- Generated by generate_item_presets.py from data/d3/item_preset_ranges.csv; do not hand-edit.',
             f'-- items_0024 created {TABLE}; this file is the sheet\'s whole contents, so the sheet stays the one',
             '-- source and a rerun after 0024 has been applied still converges.',
             f'DELETE FROM `{TABLE}`;']
    if presets:
        lines.append(f'INSERT INTO `{TABLE}` (`entry`, `affix_id`, `affix_name`, `kind`, `value_min`, '
                     '`value_max`, `value_step`, `item_level_bracket`, `is_percent`, `display_order`) VALUES')
        lines.append(',\n'.join('(' + ', '.join(literal(v) for v in row) + ')' for row in presets) + ';')
    return '\n'.join(lines) + '\n'


def metadata_sql(meta):
    lines = ['-- Generated by generate_item_presets.py from data/d3/affix_metadata.csv; do not hand-edit.',
             '-- A stat no slot pool holds: its tooltip name, kind, percent and order. Rolls nothing.',
             'DROP TABLE IF EXISTS `dc_affix_metadata`;',
             'CREATE TABLE `dc_affix_metadata` (',
             '  `affix_id` VARCHAR(64) NOT NULL,',
             '  `affix_name` VARCHAR(128) NOT NULL,',
             '  `kind` VARCHAR(16) NOT NULL,',
             '  `is_percent` TINYINT NOT NULL,',
             '  `display_order` INT UNSIGNED NOT NULL,',
             '  PRIMARY KEY (`affix_id`)',
             ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;']
    if meta:
        lines.append('INSERT INTO `dc_affix_metadata` (`affix_id`, `affix_name`, `kind`, `is_percent`, `display_order`) VALUES')
        lines.append(',\n'.join(f"""('{affix}', '{name.replace("'", "''")}', '{kind}', {percent}, {order})"""
                                for affix, (name, kind, percent, order) in sorted(meta.items())) + ';')
    return '\n'.join(lines) + '\n'


def generate(migration=None, metadata_migration=None):
    # Before any write: a migration the updater never reads would change nothing in the DB.
    sheet = require_companion_migration(MODULE, Path(migration) if migration else MIGRATION, UPDATES)
    named = require_companion_migration(MODULE, Path(metadata_migration) if metadata_migration else METADATA_MIGRATION,
                                        UPDATES)
    write_migration(MODULE, sheet, sql(rows()))
    write_migration(MODULE, named, metadata_sql(metadata()))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--migration', type=Path, help='the new world migration for a changed item_preset_ranges.csv')
    parser.add_argument('--metadata-migration', type=Path, help='the new world migration for a changed affix_metadata.csv')
    args = parser.parse_args()
    generate(args.migration, args.metadata_migration)

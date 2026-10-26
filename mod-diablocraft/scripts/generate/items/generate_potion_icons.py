#!/usr/bin/env python3
"""The potion generator: every Bottomless potion as an item, wearing its own icon (diablocraft-71scy, diablocraft-0knhj).

Every row of data/d3/legendary_potions.csv is a potion: its name, power text with the roll range, flavour, required
level and icon; data/potion_icons.csv gives each its item entry and display id (item_entry, display_id, d3_id;
both append-only project identities). No potion has code of its own here. Writes:

  world   items_0027_bottomless_potions.sql  item_template, dc_base_item and dc_item_tooltip of every potion, as
                                              Regeneration's hand-written items_0015 has them (legendary), with its
                                              display; pool_version 'yes': they drop through the world's legendary
                                              pool as D3's do, and no loot, vendor or kit row of their own
                                              (diablocraft-pymfu)
  client  ItemDisplayInfo.dbc                one row per display: InventoryIcon = the row's icon, no model
          Item.dbc                           the item's row with that displayid, which is where the 3.3.5a
                                             client takes the bag icon from (client-patch/dbc/README.md)

The icons are client-patch/art/Interface/Icons/<icon>.blp, made by client-patch/source/potions/draw_potion_icons.py.
items_0015_bottomless_potion.sql and client-patch/dbc/build_item.py still write Regeneration with display 24152, and
items_0023_potion_icons.sql (this generator's earlier, applied output) sets its 90300; this migration writes the
whole row again, so its name sorts after theirs. The bar's potion slot is a spell button (diablocraft-g8jnj).
"""
import csv
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration
from dbc_store import Store, schema
from generate_sql import item_description, sql_text
from text_guard import refuse_unfilled

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
CLIENT = ROOT / 'client-patch/dbc'
ICONS = ROOT / 'client-patch/art/Interface/Icons'
MIGRATION = MODULE / 'data/sql/db-world/updates/items_0027_bottomless_potions.sql'
TABLE = MODULE / 'src/classes/dc_potion_table.h'
DISPLAY_FIRST = 90300   # after the gems' 90100-90249


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream, strict=True))


def power_line(row):
    """The sheet's power text with its roll range written in, as the tooltip draws it before the item rolls."""
    text = row['power_text']
    if row['roll_min']:
        low, high = int(row['roll_min']), int(row['roll_max'])
        text = text.replace('%d', str(low) if low == high else f'{low}\u2013{high}')
    text = text.replace('%%', '%')
    refuse_unfilled(f"legendary_potions.csv {row['d3_id']}", text)
    return text


def numbers(row):
    """The power's own numbers that are not its roll, read from the row's D3 text (diablocraft-87qlt): how long a timed power
    lasts ("for 5 seconds", "over 5 seconds"), Fear's reach ("within 12 yards") and Rejuvenation's Life threshold ("below 50%%
    health"). 0 where the text names none; a duration that IS the roll ("for %d seconds") is the roll's."""
    text = row['power_text']
    found = lambda pattern: float(m[1]) if (m := re.search(pattern, text)) else 0.0
    return {'seconds': found(r'\b(?:for|over) (\d+) seconds'), 'yards': found(r'within (\d+) yards'),
            'below_life_pct': found(r'below (\d+)%% health')}


def rows():
    """[{entry, display, icon, d3_id, name, level, power, flavour}] by entry, each from its legendary_potions.csv row."""
    sheet = {r['d3_id']: r for r in read(MODULE / 'data/d3/legendary_potions.csv')}
    missing = [r['icon'] for r in sheet.values() if not (ICONS / f"{r['icon']}.blp").is_file()]
    if missing:
        raise ValueError(f'no icon in {ICONS.relative_to(ROOT)} for {missing}; run draw_potion_icons.py')
    out = []
    for r in read(MODULE / 'data/potion_icons.csv'):
        if r['d3_id'] not in sheet:
            raise ValueError(f"potion_icons.csv: {r['d3_id']} is not a legendary_potions.csv row")
        row = sheet[r['d3_id']]
        out.append({'entry': int(r['item_entry']), 'display': int(r['display_id']), 'icon': row['icon'],
                    'd3_id': row['d3_id'], 'name': row['name'], 'level': int(row['required_level']),
                    'power': power_line(row), 'flavour': row['flavor_text'], 'power_id': row['power_id'],
                    'power_text': row['power_text'], 'roll_min': row['roll_min'], 'roll_max': row['roll_max'],
                    'spell': int(r['spell_id']), 'power_spell': int(r['power_spell_id']), **numbers(row)})
    entries, displays = [p['entry'] for p in out], [p['display'] for p in out]
    if len(set(entries)) != len(out) or len(set(displays)) != len(out) or min(displays) < DISPLAY_FIRST:
        raise ValueError(f'potion_icons.csv: items and display ids must be unique, display ids from {DISPLAY_FIRST}')
    return sorted(out, key=lambda p: p['entry'])


def world_sql(potions):
    # Regeneration's columns (items_0015): a potion (class 0, subclass 1), legendary quality 5, Material 3, one per
    # slot, no on-use spell (the sheet's potion slot swaps key 7 to its shell). The sheet has one level, the
    # required level; Regeneration's item level is the same 61.
    entries = ', '.join(str(p['entry']) for p in potions)
    d3_ids = ', '.join(sql_text(p['d3_id']) for p in potions)
    items, bases, tooltips = [], [], []
    for p in potions:
        text, _ = item_description(p['power'], p['flavour'], p['d3_id'])
        items.append(f"({p['entry']}, 0, 1, {sql_text(p['name'])}, {p['display']}, 5, 0, 1, 0, 0, 0, 0, 1, 3, 0, "
                     f"{p['level']}, {p['level']}, {sql_text(text)})")
        bases.append(f"({p['entry']}, {sql_text(p['d3_id'])}, {sql_text(p['name'])}, 'potion', 'Potion', 'legendary', "
                     f"'', {p['level']}, {p['level']}, NULL, NULL, NULL, '', '', 'legendary_potions.csv', 'yes', '', 'no')")
        tooltips.append(f"({sql_text(p['d3_id'])}, '', {sql_text(p['power'])}, {sql_text(p['flavour'])})")
    return '\n'.join([
        '-- Generated by generate_potion_icons.py from legendary_potions.csv and potion_icons.csv; do not hand-edit.',
        'SET NAMES utf8mb4;',
        f'DELETE FROM `item_template` WHERE `entry` IN ({entries});',
        'INSERT INTO `item_template`',
        '  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`, `BuyCount`, `BuyPrice`, `SellPrice`,',
        '   `InventoryType`, `maxcount`, `stackable`, `Material`, `bonding`, `ItemLevel`, `RequiredLevel`, `description`)',
        'VALUES',
        ',\n'.join(items) + ';',
        f'DELETE FROM `dc_base_item` WHERE `entry` IN ({entries});',
        'INSERT INTO `dc_base_item`',
        '  (`entry`, `d3_id`, `d3_name`, `slot`, `type`, `rarity`, `usable_by`, `item_level`, `level_req`, `weapon_min`,',
        '   `weapon_max`, `weapon_aps`, `preset_affixes`, `set_name`, `source_file`, `pool_version`, `designated_class`,',
        '   `craft_only`)',
        'VALUES',
        ',\n'.join(bases) + ';',
        f'DELETE FROM `dc_item_tooltip` WHERE `d3_id` IN ({d3_ids});',
        'INSERT INTO `dc_item_tooltip` (`d3_id`, `set_id`, `power_text`, `flavour`) VALUES',
        ',\n'.join(tooltips) + ';']) + '\n'


def client_dbcs(potions):
    """(Item.dbc, ItemDisplayInfo.dbc) bytes: ours replaced where they sit, a new one appended."""
    displays = Store((CLIENT / 'ItemDisplayInfo.dbc').read_bytes(), schema(ROOT, 'itemdisplayinfo_dbc'))
    items = Store((CLIENT / 'Item.dbc').read_bytes(), schema(ROOT, 'item_dbc'))
    blank = {name: '' if kind in ('varchar', 'text') else 0 for name, kind, _ in displays.columns}
    for p in potions:
        display = p['display']
        if display in displays.rows and not displays.decode(display)['InventoryIcon_1'].startswith('DC_Potion_'):
            raise ValueError(f'display {display} already belongs to another record')
        displays.encode({**blank, 'ID': display, 'InventoryIcon_1': p['icon']})
        # The world row's class: a potion (0/1), Material 3, no inventory type; replaced where it sits, else appended.
        items.encode({'ID': p['entry'], 'ClassID': 0, 'SubclassID': 1, 'Sound_Override_Subclassid': -1, 'Material': 3,
                      'DisplayInfoID': display, 'InventoryType': 0, 'SheatheType': 0})
    return items.bytes(), displays.bytes()


def table_header(potions):
    """The server's potion table (src/classes/dc_potion_table.h): each potion's item, its shell (what key 7 casts while it is
    slotted), its power's record (0: none) and power id, and the numbers numbers() reads; the roll is the item's own."""
    lines = ['// Generated by generate_potion_icons.py from legendary_potions.csv and potion_icons.csv; do not hand-edit.',
             '#pragma once', '', '#include <cstdint>', '', 'namespace DC::Potion', '{',
             'struct Legendary', '{',
             '    std::uint32_t item, shell, power;',
             '    char const* powerId;',
             '    double seconds, yards, belowLifePct;',
             '};', '', 'inline constexpr Legendary Legendaries[] = {']
    lines += [f"    {{{p['entry']}, {p['spell']}, {p['power_spell']}, \"{p['power_id']}\", {p['seconds']:g}, {p['yards']:g}, "
              f"{p['below_life_pct']:g}}}," for p in potions]
    lines += ['};', '} // namespace DC::Potion']
    return '\n'.join(lines) + '\n'


def generate():
    potions = rows()
    sql = world_sql(potions)
    item_dbc, display_dbc = client_dbcs(potions)
    write_migration(MODULE, MIGRATION, sql)
    write_coupled_outputs(MODULE, MIGRATION, sql, [(CLIENT / 'Item.dbc', item_dbc),
                                                   (CLIENT / 'ItemDisplayInfo.dbc', display_dbc),
                                                   (TABLE, table_header(potions))],
                          label='potion icon client rows')


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()

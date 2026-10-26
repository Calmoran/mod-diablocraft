#!/usr/bin/env python3
"""Ground carriers and tunables: CSV -> generated SQL -> world updates.

Descriptors are delivered only on pickup. Existing stage-one entries stay stable.
Extra carrier range 925000-925052 was checked free in acore_world 2026-09-18.
Template 12999 / faction 114 / invisible display 11686 were verified in
acore_world on 2026-09-18. Keep its trigger flag (no threat list), but the AI
removes the trigger's default NOT_SELECTABLE before initial visibility.
920000-921113 was checked free in acore_world on 2026-09-18.
"""
import csv
import math
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import MIGRATION_FROZEN, migration_state, write_migration
from generate_sql import read_base_item_ids, shipped_entries

# Literal audit (docs/research/literal-audit-claude.md): the numbers below are
# constants, not tunables - recorded here, nothing else changes.
# Constant (audit 123, 920000, 100000, 12999, 11686, 114, 103000, 925000): carrier entry base, item base, clone template, display, faction and the extra carrier range; Identifiers.
# Constant (audit 124, 10000, 4294967295): carrier reservation size and the uint32 ceiling for count/seconds tunables; Validation of the designer's rows.

MODULE = Path(__file__).resolve().parents[3]
DATA = MODULE / 'data/d3'
# ground_loot_parameters.csv is the designer's, not D3's, so the FILE moved to
# data/tunables/ (Architect 2026-09-19, second-table ruling). It keeps this
# generator and its own generated rows, not dc_tunables; only the folder
# changed. data/tunables/README.md lists it under "Files with their own table".
TUNABLES = MODULE / 'data/tunables'
GENERATED = MODULE / 'data/generated'
UPDATES = MODULE / 'data/sql/db-world/updates'
CARRIER_BASE = 920000
ITEM_BASE = 100000  # generate_sql.py ENTRY_BASE, same sorted d3_id convention
CLONE_SOURCE = 12999
DISPLAY = 11686
FACTION = 114  # stock World Invisible Trigger, verified in the world DB
PARAMETERS = {'carrier_scale': 'multiplier', 'open_world_expiry_seconds': 'seconds',
              'boss_material_count': 'count', 'ground_delivery_enabled': 'boolean'}
# 'primal' is the quality-tier look (diablocraft-t3t8): a Primal Ancient drop wears its own beam and plate
# level, whatever its rarity. It ships in its own migration because loot_0008 is applied.
RARITIES = {'normal': 1, 'magic': 2, 'rare': 3, 'legendary': 4, 'set': 5, 'primal': 6}
# beam_spell 0 is the explicit "no beam" value (white drops, ruling 2026-09-28):
# dc_ground_loot.cpp adds no aura for it, preview and real drop alike.
NO_BEAM = 0
CARRIERS = 'loot_0005_ground_carriers.sql'
# The base items added after 0002 (the Shaman's Ritual Mace and Totem) get their carriers here: loot_0005 is applied, and
# renders the base items that shipped. An item's carrier is CARRIER_BASE + its entry - ITEM_BASE (the sheet's entry, not
# its place in the d3_id order, which a row added in the middle would move).
CARRIERS_ADDED = 'loot_0013_ground_carriers_added.sql'
# loot_0005 is applied and immutable, so a beam change ships as this
# visuals-only migration: the same REPLACE loot_0005 carries, from the sheet.
VISUALS = 'loot_0008_ground_visuals.sql'
PRIMAL_VISUAL = 'loot_0011_ground_visual_primal.sql'
# loot_0005 also pinned ground_delivery_enabled=1; the corpse-loot minimum turns ground
# delivery off for kills, so the switch ships as its own migration, from the sheet.
SWITCH = 'loot_0010_ground_delivery_switch.sql'
# The carriers have no npc_spellclick_spells rows (BeforeSpellClick claims the pickup), so the core logged one error per
# carrier on every start and stripped the flag itself. loot_0005 is applied and keeps its npcflag; this migration clears the
# bit on every carrier, so the templates are what the core leaves them and the start logs nothing.
CARRIER_FLAG = 'loot_0012_ground_carrier_npcflag.sql'
SPELLCLICK = 16777216  # UNIT_NPC_FLAG_SPELLCLICK
VISUAL_ROWS = re.compile(r'REPLACE INTO dc_ground_loot_visual .*?\);\n', re.S)


def read(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def read_tunables(name):
    """One of the sheets that moved to data/tunables/ but kept its own table."""
    with (TUNABLES / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def quote(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "''") + "'"


def read_visuals():
    visuals = read('ground_loot_visuals.csv')
    if len(visuals) != len(RARITIES) or {r['rarity'] for r in visuals} != set(RARITIES):
        raise ValueError('ground beam rarities are missing or duplicated')
    for row in visuals:
        if int(row['plate_level']) != RARITIES[row['rarity']] or int(row['beam_spell']) < NO_BEAM:
            raise ValueError('invalid beam or rarity level')
    return visuals


def visual_sql(visuals):
    return ['CREATE TABLE IF NOT EXISTS dc_ground_loot_visual (rarity VARCHAR(16) NOT NULL PRIMARY KEY, plate_level TINYINT UNSIGNED NOT NULL, beam_spell INT UNSIGNED NOT NULL);',
            'REPLACE INTO dc_ground_loot_visual (rarity,plate_level,beam_spell) VALUES',
            ',\n'.join(f"({quote(r['rarity'])},{r['plate_level']},{r['beam_spell']})" for r in visuals) + ';']


def render_visuals():
    # The five rarities only: loot_0008 is applied and stays byte-identical.
    return '\n'.join(['-- Generated by generate_ground_loot.py; do not hand-edit.',
                      '-- Rarity beams from ground_loot_visuals.csv; beam_spell 0 = no beam.',
                      'SET NAMES utf8mb4;'] + visual_sql([r for r in read_visuals() if r['rarity'] != 'primal']) + [''])


def render_primal_visual():
    return '\n'.join(['-- Generated by generate_ground_loot.py; do not hand-edit.',
                      '-- The Primal Ancient look (diablocraft-t3t8) from ground_loot_visuals.csv: its own plate level and beam.',
                      'SET NAMES utf8mb4;'] + visual_sql([r for r in read_visuals() if r['rarity'] == 'primal']) + [''])


def render_switch():
    row = next(r for r in read_tunables('ground_loot_parameters.csv') if r['parameter'] == 'ground_delivery_enabled')
    if row['tuned_value'] not in ('0', '1'):
        raise ValueError('ground switch must be 0 or 1')
    return '\n'.join(['-- Generated by generate_ground_loot.py; do not hand-edit.',
                      '-- ground_delivery_enabled from ground_loot_parameters.csv (0 = corpse loot, 1 = ground carriers).',
                      "UPDATE dc_ground_loot_parameter SET tuned_value=" + row['tuned_value'] + " WHERE parameter='ground_delivery_enabled';",
                      ''])


def render_carrier_flag():
    return '\n'.join(['-- Generated by generate_ground_loot.py; do not hand-edit.',
                      '-- Clears UNIT_NPC_FLAG_SPELLCLICK on every ground carrier: none has an npc_spellclick_spells row, so the core',
                      '-- logged "has UNIT_NPC_FLAG_SPELLCLICK but no data" for each one on every start and stripped the flag itself.',
                      f'UPDATE creature_template SET npcflag = npcflag & ~{SPELLCLICK} WHERE entry IN (SELECT creature_entry FROM dc_ground_loot_carrier);',
                      ''])


def carrier_sql(item_entry, name, carrier):
    """The statements that make one ground carrier for a base item."""
    # TRUNCATE would implicitly commit. DELETE keeps the whole template
    # batch atomic, and avoids thousands of per-statement disk flushes.
    return ['DELETE FROM dc_ground_template;',
            f'INSERT INTO dc_ground_template SELECT * FROM creature_template WHERE entry={CLONE_SOURCE};',
            f"UPDATE dc_ground_template SET entry={carrier},name={quote(name)},subname='',minlevel=1,maxlevel=1,faction={FACTION},npcflag={SPELLCLICK},unit_flags=770,flags_extra=8576,AIName='',ScriptName='dc_ground_loot_carrier',gossip_menu_id=0,lootid=0,pickpocketloot=0,skinloot=0,KillCredit1=0,KillCredit2=0,VehicleId=0,`rank`=0,RegenHealth=0;",
            f'DELETE FROM creature_template WHERE entry={carrier};',
            'INSERT INTO creature_template SELECT * FROM dc_ground_template;',
            f'DELETE FROM creature_template_model WHERE CreatureID={carrier};',
            f'INSERT INTO creature_template_model (CreatureID,Idx,CreatureDisplayID,DisplayScale,Probability) VALUES ({carrier},0,{DISPLAY},1,1);',
            f'REPLACE INTO dc_ground_loot_carrier (base_item,creature_entry) VALUES ({item_entry},{carrier});']


def item_entries(items):
    """{d3_id: entry} of the base items: base_item_ids.csv, the published identities."""
    return read_base_item_ids(DATA / 'base_item_ids.csv', {row['d3_id'] for row in items})


def render(scope=None):
    """The ground loot SQL. `scope` None is every base item; 'shipped' the ones 0002 holds (loot_0005's, which is applied)."""
    items = sorted(read('base_items.csv'), key=lambda row: row['d3_id'])
    if not items or len({row['d3_id'] for row in items}) != len(items):
        raise ValueError('base_items.csv is empty or has duplicate d3_id values')
    if len(items) >= 10000:
        raise ValueError('carrier entry reservation exhausted')
    parameters = read_tunables('ground_loot_parameters.csv')
    if len(parameters) != len(PARAMETERS) or {r['parameter'] for r in parameters} != set(PARAMETERS):
        raise ValueError('ground tunable parameters are missing or duplicated')
    for row in parameters:
        value = float(row['tuned_value'])
        if row['d3_value'] or not math.isfinite(value) or value < 0 or row['unit'] != PARAMETERS[row['parameter']]:
            raise ValueError('invalid tunable: ' + row['parameter'])
        if row['parameter'] in ('carrier_scale', 'open_world_expiry_seconds') and value <= 0:
            raise ValueError('scale and expiry must be positive')
        if row['unit'] in ('count', 'seconds') and (not value.is_integer() or value > 4294967295):
            raise ValueError('count and seconds must fit uint32')
    if any(r['parameter'] == 'ground_delivery_enabled' and r['tuned_value'] not in ('0', '1') for r in parameters):
        raise ValueError('ground switch must be 0 or 1')
    visuals = read_visuals()
    sql = ['-- Generated by generate_ground_loot.py; do not hand-edit.',
           '-- Gear, gem and material descriptors; preview and production carriers share templates.',
           'SET NAMES utf8mb4;',
           'CREATE TABLE IF NOT EXISTS dc_ground_loot_parameter (parameter VARCHAR(64) NOT NULL PRIMARY KEY, d3_value DOUBLE NULL, tuned_value DOUBLE NOT NULL, unit VARCHAR(32) NOT NULL, notes TEXT NOT NULL);',
           'INSERT INTO dc_ground_loot_parameter (parameter,d3_value,tuned_value,unit,notes) VALUES',
           ',\n'.join('(' + ','.join([quote(r['parameter']), 'NULL', r['tuned_value'], quote(r['unit']), quote(r['source'] + '; ' + r['notes'])]) + ')' for r in parameters) +
           # The CSV wins on every apply (ruling 2026-09-19): the sheet is in
           # data/tunables/ and its tuned_value is written over the table's.
           '\nON DUPLICATE KEY UPDATE d3_value=VALUES(d3_value),tuned_value=VALUES(tuned_value),unit=VALUES(unit),notes=VALUES(notes);',
           *visual_sql(visuals),
           'CREATE TABLE IF NOT EXISTS dc_ground_loot_carrier (base_item INT UNSIGNED NOT NULL PRIMARY KEY, creature_entry INT UNSIGNED NOT NULL UNIQUE);',
           '-- Clone stock schema rather than depending on creature_template column defaults.',
           '-- Engine bitmasks: unit_flags NON_ATTACKABLE|IMMUNE_TO_PC|IMMUNE_TO_NPC = 770;',
           '-- flags_extra TRIGGER|NO_TAUNT|CANNOT_ENTER_COMBAT = 8576; npcflag SPELLCLICK = 16777216.',
           'CREATE TABLE IF NOT EXISTS dc_ground_loot_material (entry INT UNSIGNED NOT NULL PRIMARY KEY,rarity VARCHAR(16) NOT NULL);',
           'REPLACE INTO dc_ground_loot_material(entry,rarity) VALUES '+','.join(f"({int(r['entry'])},{quote(r['rarity'])})" for r in read('ground_loot_materials.csv'))+';',
           'CREATE TEMPORARY TABLE dc_ground_template LIKE creature_template;',
           'START TRANSACTION;']
    definitions = sorted({(r['gem_id'],r['gem_name'],r['colour'],r['tier']) for r in read('gems.csv') if r['is_legendary'] == '0'})
    extra = [(103000+i, f'{tier} {name}') for i, (_,name,_,tier) in enumerate(definitions)]
    extra += [(int(r['entry']),r['name']) for r in read('ground_loot_materials.csv')]
    entry_of = item_entries(items)
    shipped = shipped_entries(DATA / 'base_items.csv') if scope == 'shipped' else None
    entries = [(entry_of[r['d3_id']], r['d3_name'], CARRIER_BASE + entry_of[r['d3_id']] - ITEM_BASE) for r in items
               if shipped is None or entry_of[r['d3_id']] in shipped]
    # Separate extra range leaves every stage-one base-item carrier stable.
    entries += [(entry,name,925000+i) for i,(entry,name) in enumerate(extra)]
    for item_entry, name, carrier in entries:
        sql += carrier_sql(item_entry, name, carrier)
    sql += ['COMMIT;', 'DROP TEMPORARY TABLE dc_ground_template;', '']
    return '\n'.join(sql)


def render_added_carriers():
    """The carriers of the base items added since 0002, or None: the same template rows loot_0005 writes, then the
    npcflag loot_0012 leaves on every carrier (none has a spellclick row, so the core would log one error each)."""
    items = sorted(read('base_items.csv'), key=lambda row: row['d3_id'])
    entry_of = item_entries(items)
    shipped = shipped_entries(DATA / 'base_items.csv')
    added = [(entry_of[r['d3_id']], r['d3_name'], CARRIER_BASE + entry_of[r['d3_id']] - ITEM_BASE) for r in items
             if shipped is not None and entry_of[r['d3_id']] not in shipped]
    if not added:
        return None
    sql = ['-- Generated by generate_ground_loot.py; do not hand-edit.',
           '-- The ground carriers of the base items added after loot_0005 (the Shaman\'s Ritual Mace and Totem).',
           'SET NAMES utf8mb4;',
           'CREATE TEMPORARY TABLE dc_ground_template LIKE creature_template;',
           'START TRANSACTION;']
    for item_entry, name, carrier in added:
        sql += carrier_sql(item_entry, name, carrier)
    carriers = ','.join(str(carrier) for _, _, carrier in added)
    sql += [f'UPDATE creature_template SET npcflag = npcflag & ~{SPELLCLICK} WHERE entry IN ({carriers});',
            'COMMIT;', 'DROP TEMPORARY TABLE dc_ground_template;', '']
    return '\n'.join(sql)


def main():
    sql = render()
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / 'ground_loot.sql').write_text(sql, encoding='utf-8', newline='\n')
    sql = render('shipped')
    carriers = UPDATES / CARRIERS
    # An applied loot_0005 whose only drift is the beam rows is expected: those
    # ship in loot_0008. Any other drift still reaches the guard, which warns.
    # The switch row is the other expected drift: it ships in loot_0010.
    def without_switch(text):
        return re.sub(r"\('ground_delivery_enabled',NULL,[^\n]*\)", "SWITCH_ROW", VISUAL_ROWS.sub('', text))
    beams_only = (migration_state(MODULE, carriers, sql) == MIGRATION_FROZEN and
                  without_switch(carriers.read_text(encoding='utf-8')) == without_switch(sql))
    if not beams_only:
        write_migration(MODULE, carriers, sql)
    added = render_added_carriers()
    if added:
        write_migration(MODULE, UPDATES / CARRIERS_ADDED, added)
    write_migration(MODULE, UPDATES / VISUALS, render_visuals())
    write_migration(MODULE, UPDATES / PRIMAL_VISUAL, render_primal_visual())
    write_migration(MODULE, UPDATES / SWITCH, render_switch())
    write_migration(MODULE, UPDATES / CARRIER_FLAG, render_carrier_flag())
    print('Ground loot SQL generated (gear + normal gems + boss materials; four tunables)')


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()

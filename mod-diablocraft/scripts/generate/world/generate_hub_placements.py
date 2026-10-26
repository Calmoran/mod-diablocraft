# Constant (audit 201, 910016): Identification tome entry; Content identifier.
# Constant (audit 202, 417): Identification tome model display; Appearance identity.
# Constant (audit 203, 910017): Book-stack entry; Content identifier.
# Constant (audit 204, 43): Book-stack model display; Appearance identity.
# Constant (audit 205, 5): Decorative stack gameobject type; Native enum.
# Constant (audit 207, 22): Clickable tome gameobject type; Native enum.
# Constant (audit 214, 910000): Managed hub service identity; Export allow-list; quantity is not a game magnitude.
# Constant (audit 215, 910001): Managed hub service identity; Export allow-list; quantity is not a game magnitude.
# Constant (audit 216, 910002): Managed hub service identity; Export allow-list; quantity is not a game magnitude.
# Constant (audit 217, 910003): Managed hub service identity; Export allow-list; quantity is not a game magnitude.
# Constant (audit 218, 910010): Managed hub service identity; Export allow-list; quantity is not a game magnitude.
# Constant (audit 219, 910011): Managed hub service identity; Export allow-list; quantity is not a game magnitude.
"""Export the designer's six hub services, then generate a portable tier-placement migration.

FROZEN since the hub moved to the Sanctum of Torment (diablocraft-976b): it reproduces the applied Scryer's Tier
migrations from tests/scryer_hub, and what is left of it in use is a helper library (upsert_existing, source_snapshot,
copy_from_source, launch_tier_count, near) for generate_hub_sanctum_move.py, which writes the Sanctum's placements.

--export reads the live database after `dc areas scan 530 3703`; normal runs
read only the committed CSV. Stop the server before applying generated SQL.
Walls and temporary portals are deliberately excluded.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration
from tunable_values import integer as tunable_integer, value as tunable_value, positive as tunable_positive
import argparse
import csv
import json
import math
from pathlib import Path
import struct

from generate_area_copies import Database, SIMPLE, insert, literal
from scryer_hub import LEGACY

ROOT = Path(__file__).resolve().parents[3]
# FROZEN since the hub moved to the Sanctum of Torment (diablocraft-976b): this generator wrote the applied
# migrations world_0007, 0010, 0023 and 0024 for Scryer's Tier, and it reproduces them from the old hub's
# data, which now lives in tests/scryer_hub (scryer_hub.py). The Sanctum's placements are generate_hub_sanctum_move.py's.
DATA = LEGACY / 'world_hub_placements.csv'
# 910016 is the Tome of Identification, 910017 its book stack. Both are placed
# and exported into the CSV (khe6, 2026-09-30; the rows were written by hand from
# a live read, since --export refuses once the hub has managed copies).
ENTRIES = {'c': {910000, 910001, 910002, 910003}, 'g': {910010, 910011, 910016, 910017}}
TABLES = {'c': 'creature', 'g': 'gameobject'}
NAME = 'world_0007_hub_placements.sql'
# world_0007 is applied and frozen (applied_migrations.csv): it stays the original six
# services. The tome and its book stack ship as their own migration (khe6).
ORIGINAL_ENTRIES = {'c': {910000, 910001, 910002, 910003}, 'g': {910010, 910011}}
TOME_STACK_ENTRIES = {'g': {910016, 910017}}   # TOME_ENTRY, STACK_ENTRY
TOME_STACK_NAME = 'world_0023_hub_tome_stack_placements.sql'

# --- the Tome of Identification (decisions.md 2026-09-17) --------------------
#
# Only the TEMPLATE is generated here. Its placement follows the same route as
# every other hub service and as the Jeweler before it: the designer places it in game,
# `.dc areas scan 530 3703` records it, then --export writes the row into
# world_hub_placements.csv and the normal run emits the tier copies. Nothing in
# this file invents a coordinate.
#
# Type 22 (SPELLCASTER) with spellId 0, exactly like the obelisk and the town
# portal halves. world_0006_hub_object_use.sql has the reasoning: a type-10
# goober with no quest is only clickable by a GM, while type 22 is interactive
# by type. GameObject::Use calls OnGossipHello before its type switch, so the
# module answers the click and makes the PLAYER cast the identify spell - which
# is what gives a player-owned cast bar that movement and damage interrupt. The
# object never casts anything itself; that is why spellId stays 0.
TOME_ENTRY = 910016
TOME_NAME = 'Tome of Identification'
# Read from acore_world.gameobject_template on 2026-09-17: entry 181837
# 'Sealed Tome' carries displayId 417, and that is the object the designer spawned and
# liked. The generator wrote 2770 here with a comment calling it the Sealed
# Tome, but two displays share that name - read the DB, never a comment.
TOME_DISPLAY = 417
TOME_FILE = 'world_0011_identify_tome.sql'

# The designer chose the tome floating above a book stack, so the stack is a second
# managed hub object. Read from acore_world.gameobject_template on 2026-09-17:
# entry 191128 'WotLK Light Book Stack' carries displayId 43.
STACK_ENTRY = 910017
STACK_NAME = 'Stack of Tomes'
STACK_DISPLAY = 43
# Type 5 is GAMEOBJECT_TYPE_GENERIC: it has no use table entry, so it is not
# clickable and offers no quest or gossip - what a purely decorative base needs.
STACK_TYPE = 5
# How far the tome hovers ABOVE the stack, in yards. Added to the tome's
# placement z only; the stack keeps its own z. 1.0 yd clears the stack's books
# without floating the tome away. The designer nudges this one value to raise or lower it.
def tome_float_yards():
    return tunable_value("ui", "tome_float_yards")


def launch_tier_count():
    return tunable_integer("monsters", "launch_tier_count", minimum=1)


def generate_tome(entry=TOME_ENTRY, display=TOME_DISPLAY, name=TOME_NAME,
                  stack_entry=STACK_ENTRY, stack_display=STACK_DISPLAY, stack_name=STACK_NAME):
    """Both gameobject_template rows: the tome and its decorative book stack."""
    columns = (['entry', 'type', 'displayId', 'name', 'IconName', 'castBarCaption', 'unk1', 'size']
               + [f'Data{i}' for i in range(24)] + ['AIName', 'ScriptName', 'VerifiedBuild'])
    # Data0 spellId 0: the module casts, not the object. Data2 partyOnly 0,
    # Data3 allowMounted 1 - a UI click should never dismount anyone.
    tome = [entry, 22, display, name, '', '', '', tunable_positive('ui', 'tome_scale_multiplier')] + [0, 0, 0, 1] + [0] * 20 + ['', '', 12340]
    # Type 5 has no data fields that do anything, so every DataN is 0.
    stack = [stack_entry, STACK_TYPE, stack_display, stack_name, '', '', '', tunable_positive('ui', 'stack_scale_multiplier')] + [0] * 24 + ['', '', 12340]
    return '\n'.join([
        '-- Generated by generate_hub_placements.py --tome; never edit.',
        '-- decisions.md 2026-09-17: the hub tome identifies every unidentified item',
        '-- in the bags at once, on a 2-second player cast, floating over a book stack.',
        '-- Apply to the world database.',
        '--',
        '-- Templates only. The designer places the two objects together,',
        '-- `.dc areas scan 530 3703` records them, then --export writes the placements',
        '-- into world_hub_placements.csv; the generator adds tome_float_yards() to the',
        '-- tome\'s z.',
        'SET NAMES utf8mb4;',
        f'DELETE FROM `gameobject_template` WHERE `entry` IN ({entry}, {stack_entry});',
        'INSERT INTO `gameobject_template`',
        '  (' + ', '.join(f'`{c}`' for c in columns) + ')',
        'VALUES',
        '  (' + ', '.join(literal(v) for v in tome) + '),',
        '  (' + ', '.join(literal(v) for v in stack) + ');',
        '',
    ])
FOUNTAIN = LEGACY / 'world_fountain_picker.csv'
FOUNTAIN_NAME = 'world_0010_fountain_picker.sql'
PILLAR_RESTORE_NAME = 'world_0024_difficulty_pillar_restore.sql'


def export(db, path=DATA, entries=ENTRIES):
    points = db.rows('dc_world_hub_point', "name='spawn'")
    if len(points) != 1:
        raise ValueError('Expected one named hub spawn')
    point = points[0]
    scope = f"map_id={point['map_id']} AND area_id={point['area_id']}"
    sources = db.rows('dc_area_source', scope, 'ORDER BY kind,source_guid')
    sources = [r for r in sources if r['entry'] in entries.get(r['kind'], set())]
    if len(sources) != sum(map(len, entries.values())) or any({r['entry'] for r in sources if r['kind'] == k} != ids
                                for k, ids in entries.items()):
        raise ValueError('Scan must contain exactly the requested hub services')
    if any(db.rows('dc_area_spawn', scope+f" AND kind='{r['kind']}' AND source_guid={r['source_guid']}") for r in sources):
        raise ValueError('Hub already has managed copies; use the existing CSV or a new migration')
    next_guid = {k: int(db.query(f'SELECT MAX(guid) FROM {t}')[0]) + 1
                 for k, t in TABLES.items()}
    exported = []
    for source in sources:
        kind, guid = source['kind'], source['source_guid']
        table = TABLES[kind]
        # Preserve every stored FLOAT exactly, not shortened text-protocol output.
        columns = db.query("SELECT COLUMN_NAME,DATA_TYPE FROM information_schema.columns "
                           f"WHERE TABLE_SCHEMA='{db.name}' AND TABLE_NAME='{table}' ORDER BY ORDINAL_POSITION")
        pairs = []
        for column in columns:
            name, datatype = column.split('\t')
            value = f'CAST(`{name}` AS DOUBLE)' if datatype == 'float' else f'`{name}`'
            pairs.append(f"'{name}',{value}")
        row = json.loads(db.query(f"SELECT JSON_OBJECT({','.join(pairs)}) FROM {table} WHERE guid={guid}")[0])
        if row['phaseMask'] != 1 or row['map'] != point['map_id'] or row['id'] != source['entry']:
            raise ValueError(f'Source changed since scan: {source}')
        for field in ('position_x', 'position_y', 'position_z', 'orientation'):
            valid = db.query(f'SELECT COUNT(*) FROM {table} c JOIN dc_area_source a '
                             f"ON a.kind='{kind}' AND a.source_guid=c.guid WHERE c.guid={guid} "
                             f'AND a.{field}=c.{field}')
            if valid != ['1']:
                raise ValueError(f'Stale area scan for {guid}: {field}')
        # These simple service placements have no spawn-specific relationships.
        related = dict(SIMPLE[kind])
        related.update({'pool_' + table: 'guid', 'game_event_' + table: 'guid'})
        for child, key in related.items():
            if db.rows(child, f'`{key}`={guid}'):
                raise ValueError(f'Export requires explicit handling of {child} for {guid}')
        predicates = {
            'spawn_group': f'spawnType={0 if kind == "c" else 1} AND spawnId={guid}',
            'smart_scripts': f'source_type={0 if kind == "c" else 1} AND entryorguid=-{guid}',
            'linked_respawn': f'guid={guid} OR linkedGuid={guid}',
        }
        if kind == 'c':
            predicates['creature_formations'] = f'leaderGUID={guid} OR memberGUID={guid}'
        for child, where in predicates.items():
            if db.rows(child, where):
                raise ValueError(f'Export requires explicit handling of {child} for {guid}')
        row.update(areaId=point['area_id'], zoneId=point['area_id'])
        copies = {str(tier): next_guid[kind] + tier - 2 for tier in range(2, launch_tier_count() + 1)}
        next_guid[kind] += launch_tier_count() - 1
        exported.append(dict(kind=kind, source_guid=guid,
                             copy_guids=json.dumps(copies, separators=(',', ':')),
                             placement=json.dumps(row, separators=(',', ':')),
                             source='the designer tier-1 placements, verified live core area scan'))
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(exported[0]))
        writer.writeheader()
        writer.writerows(exported)


# Guards compare against the live database, whose FLOAT columns are not the CSV's doubles: update 2
# (2026-09-30) failed to start because world_0023's guard asked for exact equality and live was
# 0.003 yd off in y (diablocraft-yeh2). Position and facing are matched within a tolerance, never
# exactly; a real move (1 yd) still fails. id, map and phaseMask stay exact.
POSITION_TOLERANCE = 0.01      # yd
ORIENTATION_TOLERANCE = 0.001  # rad (also the rotation quaternion parts)
KEEP_TOLERANCE = 0.001         # a tome z this close to the floated z is already floated: not rewritten
GEOMETRY = ('position_x', 'position_y', 'position_z', 'orientation',
            'rotation0', 'rotation1', 'rotation2', 'rotation3')


def near(key, value, tolerance=None, qualifier=''):
    """SQL: column `key` equals `value` within the tolerance for its kind of field."""
    if tolerance is None:
        tolerance = POSITION_TOLERANCE if key.startswith('position') else ORIENTATION_TOLERANCE
    return f'ABS({qualifier}`{key}`-({literal(value)}))<{tolerance}'


def upsert_existing(table, row, fields, keep_near=None):
    """INSERT the row; an existing row gets only `fields` (never its live geometry).
    `keep_near` names columns whose existing value is kept when already within KEEP_TOLERANCE."""
    updates = []
    for key in fields:
        if key in (keep_near or ()):
            updates.append(f'`{key}`=IF(ABS(`{key}`-VALUES(`{key}`))<{KEEP_TOLERANCE},`{key}`,VALUES(`{key}`))')
        else:
            updates.append(f'`{key}`=VALUES(`{key}`)')
    return insert(table, row)[:-1] + ' ON DUPLICATE KEY UPDATE ' + ','.join(updates) + ';'


def copy_from_source(table, row, source_guid):
    """A tier copy takes its geometry from the source row as it is stored, so copies never differ from
    their source by rounding; an existing copy keeps its position and gets only the other fields."""
    columns = [key for key in row]
    values = [f's.`{key}`' if key in GEOMETRY else literal(row[key]) for key in columns]
    fields = [key for key in columns if key != 'guid' and key not in GEOMETRY]
    return (f"INSERT INTO `{table}` ({','.join(f'`{c}`' for c in columns)}) SELECT {','.join(values)} "
            f"FROM `{table}` s WHERE s.guid={source_guid} ON DUPLICATE KEY UPDATE "
            + ','.join(f'`{key}`=VALUES(`{key}`)' for key in fields) + ';')


def source_snapshot(table, kind, map_id, area_id, guid):
    """dc_area_source mirrors the stored placement row, so the area copier's source check holds."""
    return (f"INSERT INTO dc_area_source (map_id,area_id,kind,source_guid,entry,source_phase,position_x,position_y,position_z,orientation) "
            f"SELECT {map_id},{area_id},'{kind}',{guid},s.id,1,s.position_x,s.position_y,s.position_z,s.orientation "
            f"FROM `{table}` s WHERE s.guid={guid} ON DUPLICATE KEY UPDATE entry=VALUES(entry),"
            "source_phase=VALUES(source_phase),position_x=VALUES(position_x),position_y=VALUES(position_y),"
            "position_z=VALUES(position_z),orientation=VALUES(orientation);")


def upsert(table, row, fields=None):
    fields = fields or [key for key in row if key != 'guid']
    return insert(table, row)[:-1] + ' ON DUPLICATE KEY UPDATE ' + ','.join(
        f'`{key}`=VALUES(`{key}`)' for key in fields) + ';'


def hub_ids():
    with (LEGACY / 'world_hub_points.csv').open(newline='', encoding='utf-8') as stream:
        rows = [r for r in csv.DictReader(stream) if r['name'] == 'spawn']
    if len(rows) != 1:
        raise ValueError('Expected one sourced hub spawn')
    return int(rows[0]['map_id']), int(rows[0]['area_id'])


def generate(path=DATA, expected=ENTRIES, only=None, summary='Requested service placements only.'):
    """`only` narrows the run to some of the CSV's services (one migration each); every
    row it leaves out must still be one of ENTRIES, so an unknown row is never ignored."""
    map_id, area_id = hub_ids()
    with path.open(encoding='utf-8', newline='') as stream:
        sources = list(csv.DictReader(stream))
    if only is not None:
        expected = only
        known = {(k, e) for k, ids in ENTRIES.items() for e in ids}
        kept = []
        for source in sources:
            key = (source['kind'], json.loads(source['placement'])['id'])
            if key in {(k, e) for k, ids in only.items() for e in ids}:
                kept.append(source)
            elif key not in known:
                raise ValueError(f"Invalid hub service source {source['source_guid']}")
        sources = kept
    guards, statements, seen, entries = [], [], set(), set()
    for source in sources:
        kind = source['kind']
        row = json.loads(source['placement'])
        guid = int(source['source_guid'])
        copies = json.loads(source['copy_guids'])
        if (kind not in TABLES or row['id'] not in expected.get(kind, set()) or row['guid'] != guid
                or row['phaseMask'] != 1 or row['map'] != map_id or row['areaId'] != area_id
                or set(copies) != {str(t) for t in range(2, launch_tier_count() + 1)} or not source['source']):
            raise ValueError(f'Invalid hub service source {guid}')
        entries.add((kind, row['id']))
        table = TABLES[kind]
        for tier, dest in [(1, guid)] + [(t, copies[str(t)]) for t in range(2, launch_tier_count() + 1)]:
            if (kind, dest) in seen or not isinstance(dest, int) or not 0 < dest < 2**32:
                raise ValueError(f'Duplicate or invalid GUID: {kind}:{dest}')
            seen.add((kind, dest))
            placed = dict(row, guid=dest, phaseMask=tier)
            tome = kind == 'g' and row['id'] == TOME_ENTRY
            if tome:
                # The tome floats over its book stack in every tier, tier 1
                # included (PM ruling for khe6, decisions.md 2026-09-17); only the
                # tome moves, by the one named offset, and the stack keeps the
                # scanned z. Rounded to the stored FLOAT; the guard below matches within a tolerance.
                placed['position_z'] = struct.unpack('<f', struct.pack('<f', row['position_z'] + tome_float_yards()))[0]
            def identity_for(z):
                return ' AND '.join([f"`{key}`={literal(placed[key])}" for key in ('id', 'map', 'phaseMask')]
                                    + [near(key, z if key == 'position_z' else placed[key])
                                       for key in ('position_x', 'position_y', 'position_z', 'orientation')])
            identity = identity_for(placed['position_z'])
            ownership = (f"EXISTS(SELECT 1 FROM dc_area_spawn WHERE map_id={map_id} AND area_id={area_id} "
                         f"AND kind='{kind}' AND source_guid={guid} AND tier={tier} AND spawn_guid={dest})")
            guard = (f'NOT EXISTS(SELECT 1 FROM {table} WHERE guid={dest}) OR '
                     f'EXISTS(SELECT 1 FROM {table} WHERE guid={dest} AND {identity})')
            if tome and tier == 1:
                # The designer's tier-1 tome was placed at the stack's z: accept that (first
                # apply) or the floated z (reapplication).
                raw = identity_for(row['position_z'])
                assert raw != identity or tome_float_yards() < POSITION_TOLERANCE
                guard += f' OR EXISTS(SELECT 1 FROM {table} WHERE guid={dest} AND {raw})'
            guards.append(guard + (f' AND {ownership}' if tier > 1 else ''))
            if tier == 1:
                statements.append(upsert_existing(table, placed, ['areaId', 'zoneId'] + (['position_z'] if tome else []),
                                                  keep_near=('position_z',) if tome else None))
                statements.append(source_snapshot(table, kind, map_id, area_id, guid))
            else:
                guards.append(f"NOT EXISTS(SELECT 1 FROM dc_area_spawn WHERE map_id={map_id} AND area_id={area_id} "
                              f"AND kind='{kind}' AND source_guid={guid} AND tier={tier} AND spawn_guid<>{dest})")
                statements.append(copy_from_source(table, placed, guid))
                statements.append(upsert('dc_area_spawn', dict(map_id=map_id, area_id=area_id,
                    kind=kind, source_guid=guid, tier=tier, spawn_guid=dest)))
    if len(sources) != sum(map(len, expected.values())) or entries != {(k, e) for k, ids in expected.items() for e in ids}:
        raise ValueError('Expected exactly the requested distinct hub services')
    header = ['-- Generated by generate_hub_placements.py from world_hub_placements.csv; never edit.',
              f'-- {summary} Stop worldserver before applying.',
              'CREATE TEMPORARY TABLE dc_hub_placement_guard (ok INT NOT NULL CHECK(ok=1));',
              'START TRANSACTION;']
    guards.insert(0, f"EXISTS(SELECT 1 FROM dc_world_areas WHERE map_id={map_id} AND area_id={area_id} AND status='open' AND phase_scope='all')")
    guards.insert(1, f'(SELECT COUNT(*) FROM dc_tier_phase WHERE tier_id BETWEEN 1 AND {launch_tier_count()} AND phase=tier_id)={launch_tier_count()}')
    return '\n'.join(header + [f'INSERT INTO dc_hub_placement_guard VALUES (({g}));' for g in guards]
                     + statements + ['COMMIT;', 'DROP TEMPORARY TABLE dc_hub_placement_guard;', ''])


def generate_fountain(path=FOUNTAIN):
    """Move the existing managed picker; refuse an unsourced centre height."""
    map_id, area_id = hub_ids()
    with path.open(encoding='utf-8', newline='') as stream:
        config = list(csv.DictReader(stream))
    if len(config) != 1:
        raise ValueError('Expected one fountain picker configuration')
    config = config[0]
    if not config['position_z'] or not config['height_source']:
        raise ValueError('Fountain placement blocked: the designer centre .gps height is required')
    with (LEGACY / 'world_fountain_display_candidates.csv').open(encoding='utf-8', newline='') as stream:
        approved = {int(r['display_id']) for r in csv.DictReader(stream) if r['status'] == 'selected_by_Alex'}
    display = int(config['display_id'])
    if display not in approved or not config['source']:
        raise ValueError('Fountain display must be selected by the designer and sourced')
    target = {}
    for key in ('position_x', 'position_y', 'position_z', 'orientation'):
        value = float(config[key])
        if not math.isfinite(value):
            raise ValueError(f'Non-finite fountain {key}')
        # Match the stored gameobject FLOATs exactly on idempotent reapplication.
        target[key] = struct.unpack('<f', struct.pack('<f', value))[0]
    if not 0 <= target['orientation'] < 2 * math.pi:
        raise ValueError('Fountain orientation must be in [0, 2*pi)')
    target.update(rotation0=0, rotation1=0,
                  rotation2=struct.unpack('<f', struct.pack('<f', math.sin(target['orientation']/2)))[0],
                  rotation3=struct.unpack('<f', struct.pack('<f', math.cos(target['orientation']/2)))[0])
    with DATA.open(encoding='utf-8', newline='') as stream:
        sources = [r for r in csv.DictReader(stream)
                   if r['kind'] == 'g' and json.loads(r['placement'])['id'] == 910010]
    if len(sources) != 1:
        raise ValueError('Expected one historical hub picker source')
    source = sources[0]
    old = json.loads(source['placement'])
    guid = int(source['source_guid'])
    copies = json.loads(source['copy_guids'])
    if set(copies) != {str(t) for t in range(2, launch_tier_count() + 1)}:
        raise ValueError('Fountain picker requires all configured managed tier copies')
    spawns = [(1, guid)] + [(t, copies[str(t)]) for t in range(2, launch_tier_count() + 1)]
    if len({g for _, g in spawns}) != launch_tier_count():
        raise ValueError('Duplicate fountain picker GUID')

    def position(row, rotation=False):
        keys = list(target) if rotation else ['position_x', 'position_y', 'position_z', 'orientation']
        return ' AND '.join(near(k, row[k]) for k in keys)

    guards = [f"EXISTS(SELECT 1 FROM dc_world_areas WHERE map_id={map_id} AND area_id={area_id} AND status='open' AND phase_scope='all')",
              f'(SELECT COUNT(*) FROM dc_tier_phase WHERE tier_id BETWEEN 1 AND {launch_tier_count()} AND phase=tier_id)={launch_tier_count()}',
              f"EXISTS(SELECT 1 FROM gameobject_template WHERE entry=910010 AND type=22 AND displayId IN ({int(config['previous_display_id'])},{display}))",
              f'(SELECT COUNT(*) FROM gameobject WHERE map={map_id} AND id=910010)={launch_tier_count()}',
              f"EXISTS(SELECT 1 FROM dc_area_source WHERE map_id={map_id} AND area_id={area_id} AND kind='g' AND source_guid={guid} AND entry=910010 AND source_phase=1 AND (({position(old)}) OR ({position(target)})))",
              f"(SELECT COUNT(*) FROM dc_area_spawn WHERE map_id={map_id} AND area_id={area_id} AND kind='g' AND source_guid={guid})={launch_tier_count() - 1}"]
    statements = []
    for tier, dest in spawns:
        guards.append(f'EXISTS(SELECT 1 FROM gameobject WHERE guid={dest} AND id=910010 AND map={map_id} AND phaseMask={tier} AND (({position(old, True)}) OR ({position(target, True)})))')
        if tier > 1:
            guards.append(f"EXISTS(SELECT 1 FROM dc_area_spawn WHERE map_id={map_id} AND area_id={area_id} AND kind='g' AND source_guid={guid} AND tier={tier} AND spawn_guid={dest})")
        statements.append('UPDATE gameobject SET ' + ','.join(f'`{k}`={literal(v)}' for k, v in target.items()) + f' WHERE guid={dest} AND id=910010 AND map={map_id};')
    statements += ['UPDATE dc_area_source SET ' + ','.join(f'`{k}`={literal(target[k])}' for k in ('position_x', 'position_y', 'position_z', 'orientation'))
                   + f" WHERE map_id={map_id} AND area_id={area_id} AND kind='g' AND source_guid={guid} AND entry=910010;",
                   f'UPDATE gameobject_template SET displayId={display} WHERE entry=910010;']
    return '\n'.join(['-- Generated by generate_hub_placements.py --fountain; never edit.',
                      '-- Sources: world_fountain_picker.csv, world_fountain_display_candidates.csv, world_hub_placements.csv.',
                      '-- Existing picker and menu retained. Apply with worldserver stopped.',
                      'CREATE TEMPORARY TABLE dc_fountain_guard (ok INT NOT NULL CHECK(ok=1));',
                      'START TRANSACTION;']
                     + [f'INSERT INTO dc_fountain_guard VALUES (({g}));' for g in guards]
                     + statements + ['COMMIT;', 'DROP TEMPORARY TABLE dc_fountain_guard;', ''])


def generate_pillar_restore(path=FOUNTAIN):
    """Put the difficulty pillar back at its CSV placement. The never-committed world_0010 moved it into
    the fountain on live (2026-09-11); a fresh install never had that move. The guard accepts each
    row at the fountain (x, y, facing from the picker CSV, z free: the CSV has no sourced height) or
    at the CSV placement, so live restores and a fresh install is a no-op; any other place is refused."""
    map_id, area_id = hub_ids()
    with path.open(encoding='utf-8', newline='') as stream:
        config = list(csv.DictReader(stream))
    if len(config) != 1:
        raise ValueError('Expected one fountain picker configuration')
    config = config[0]
    fountain = {k: float(config[k]) for k in ('position_x', 'position_y', 'orientation')}
    with DATA.open(encoding='utf-8', newline='') as stream:
        sources = [r for r in csv.DictReader(stream)
                   if r['kind'] == 'g' and json.loads(r['placement'])['id'] == 910010]
    if len(sources) != 1:
        raise ValueError('Expected one hub picker source')
    row = json.loads(sources[0]['placement'])
    guid = int(sources[0]['source_guid'])
    copies = json.loads(sources[0]['copy_guids'])
    if row['guid'] != guid or row['phaseMask'] != 1 or row['map'] != map_id \
            or set(copies) != {str(t) for t in range(2, launch_tier_count() + 1)}:
        raise ValueError('Invalid hub picker source')
    display, fountain_display = int(config['previous_display_id']), int(config['display_id'])
    # Stored FLOATs, so a reapplication matches exactly.
    target = {k: struct.unpack('<f', struct.pack('<f', float(row[k])))[0] for k in GEOMETRY}
    spawns = [(1, guid)] + [(t, copies[str(t)]) for t in range(2, launch_tier_count() + 1)]
    if len({g for _, g in spawns}) != launch_tier_count():
        raise ValueError('Duplicate hub picker GUID')

    def at(values, keys):
        return ' AND '.join(near(k, values[k]) for k in keys)

    xyo = ('position_x', 'position_y', 'orientation')
    guards = [f"EXISTS(SELECT 1 FROM dc_world_areas WHERE map_id={map_id} AND area_id={area_id} AND status='open' AND phase_scope='all')",
              f'(SELECT COUNT(*) FROM dc_tier_phase WHERE tier_id BETWEEN 1 AND {launch_tier_count()} AND phase=tier_id)={launch_tier_count()}',
              f'EXISTS(SELECT 1 FROM gameobject_template WHERE entry=910010 AND type=22 AND displayId IN ({display},{fountain_display}))',
              f'(SELECT COUNT(*) FROM gameobject WHERE map={map_id} AND id=910010)={launch_tier_count()}',
              f"EXISTS(SELECT 1 FROM dc_area_source WHERE map_id={map_id} AND area_id={area_id} AND kind='g' AND source_guid={guid} AND entry=910010 AND source_phase=1 "
              f"AND (({at(row, GEOMETRY[:4])}) OR ({at(fountain, xyo)})))",
              f"(SELECT COUNT(*) FROM dc_area_spawn WHERE map_id={map_id} AND area_id={area_id} AND kind='g' AND source_guid={guid})={launch_tier_count() - 1}"]
    statements = []
    for tier, dest in spawns:
        guards.append(f'EXISTS(SELECT 1 FROM gameobject WHERE guid={dest} AND id=910010 AND map={map_id} AND phaseMask={tier} '
                      f'AND (({at(row, GEOMETRY)}) OR ({at(fountain, xyo)})))')
        if tier > 1:
            guards.append(f"EXISTS(SELECT 1 FROM dc_area_spawn WHERE map_id={map_id} AND area_id={area_id} AND kind='g' AND source_guid={guid} AND tier={tier} AND spawn_guid={dest})")
        statements.append('UPDATE gameobject SET ' + ','.join(f'`{k}`={literal(v)}' for k, v in target.items())
                          + f' WHERE guid={dest} AND id=910010 AND map={map_id};')
    statements += ['UPDATE dc_area_source SET ' + ','.join(f'`{k}`={literal(target[k])}' for k in GEOMETRY[:4])
                   + f" WHERE map_id={map_id} AND area_id={area_id} AND kind='g' AND source_guid={guid} AND entry=910010;",
                   f'UPDATE gameobject_template SET displayId={display} WHERE entry=910010;']
    return '\n'.join(['-- Generated by generate_hub_placements.py --pillar-restore; never edit.',
                      '-- Sources: world_hub_placements.csv, world_fountain_picker.csv.',
                      '-- The difficulty pillar returns to its placement and display; the fountain orb goes.',
                      'CREATE TEMPORARY TABLE dc_pillar_guard (ok INT NOT NULL CHECK(ok=1));',
                      'START TRANSACTION;']
                     + [f'INSERT INTO dc_pillar_guard VALUES (({g}));' for g in guards]
                     + statements + ['COMMIT;', 'DROP TEMPORARY TABLE dc_pillar_guard;', ''])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pillar-restore', action='store_true', help='Generate the move that undoes the fountain picker')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--tome', action='store_true', help='Emit the Tome of Identification template')
    parser.add_argument('--fountain', action='store_true', help='Generate the additive fountain picker move')
    parser.add_argument('--mysql')
    parser.add_argument('--defaults-file')
    args = parser.parse_args()
    if args.tome:
        if args.export:
            parser.error('--tome emits a template only; the placement comes from --export later')
        sql = generate_tome()
        (ROOT / 'data/generated' / TOME_FILE).write_text(sql, encoding='utf-8', newline='\n')
        write_migration(ROOT, ROOT / 'data/sql/db-world/updates' / TOME_FILE, sql)
        print(f'{TOME_FILE}: {TOME_NAME} {TOME_ENTRY} type 22 display {TOME_DISPLAY}, '
              f'{STACK_NAME} {STACK_ENTRY} type {STACK_TYPE} display {STACK_DISPLAY}. '
              f'the designer places both, then `.dc areas scan 530 3703` and --export; the generator '
              f'floats the tome {tome_float_yards()} yd above the stack.')
        raise SystemExit(0)
    if args.pillar_restore:
        if args.export or args.fountain:
            parser.error('--pillar-restore uses sourced CSV coordinates only')
        sql = generate_pillar_restore()
        write_migration(ROOT, ROOT / 'data/sql/db-world/updates' / PILLAR_RESTORE_NAME, sql)
        write_coupled_outputs(ROOT, ROOT / 'data/sql/db-world/updates' / PILLAR_RESTORE_NAME, sql,
                              [(ROOT / 'data/generated' / PILLAR_RESTORE_NAME, sql)])
        print(f'{PILLAR_RESTORE_NAME}: difficulty pillar back at its placement in all ten tiers, display restored')
        raise SystemExit(0)
    if args.fountain:
        if args.export:
            parser.error('--fountain uses sourced CSV coordinates, not --export')
        sql = generate_fountain()
        write_migration(ROOT, ROOT / 'data/sql/db-world/updates' / FOUNTAIN_NAME, sql)
        write_coupled_outputs(ROOT, ROOT / 'data/sql/db-world/updates' / FOUNTAIN_NAME, sql,
                              [(ROOT / 'data/generated' / FOUNTAIN_NAME, sql)])
        print(f'{FOUNTAIN_NAME}: existing picker moved in all ten tiers; menu unchanged')
        raise SystemExit(0)
    if args.export:
        if not args.mysql or not args.defaults_file:
            parser.error('--export requires --mysql and --defaults-file')
        export(Database(args.mysql, args.defaults_file, 'acore_world'))
    for name, only, summary in ((NAME, ORIGINAL_ENTRIES, 'Four NPCs and two objects only.'),
                                (TOME_STACK_NAME, TOME_STACK_ENTRIES, 'The Tome of Identification and its book stack only.')):
        sql = generate(only=only, summary=summary)
        write_migration(ROOT, ROOT / 'data/sql/db-world/updates' / name, sql)
        write_coupled_outputs(ROOT, ROOT / 'data/sql/db-world/updates' / name, sql,
                              [(ROOT / 'data/generated' / name, sql)])
        count = sum(map(len, only.values()))
        print(f'{name}: {count} original placements and {count * (launch_tier_count() - 1)} tier copies; no walls or temporary portals')

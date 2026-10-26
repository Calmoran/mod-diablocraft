"""Exercise the hub migration against disposable MySQL tables, never live spawns."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import struct
import tempfile
import uuid

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_area_copies import insert
from generate_hub_placements import (DATA, FOUNTAIN, TABLES, TOME_ENTRY, STACK_ENTRY, ORIGINAL_ENTRIES,
                                     TOME_STACK_ENTRIES, generate, generate_fountain, generate_pillar_restore,
                                     tome_float_yards)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysql', default=None)
    parser.add_argument('--defaults-file', default=None)
    args = parser.parse_args()
    if not (args.mysql and args.defaults_file):
        import fixture_db
        fixture_mysql, fixture_defaults = fixture_db.mysql_and_defaults([])
        args.mysql, args.defaults_file = args.mysql or fixture_mysql, args.defaults_file or fixture_defaults
    mysql = [args.mysql, '--defaults-file=' + str(Path(args.defaults_file).resolve()),
             '--no-login-paths', '--batch', '--skip-column-names']
    scratch = 'dc_hub_placement_test_' + uuid.uuid4().hex

    def run(sql, checked=True):
        return subprocess.run(mysql, input=sql, text=True, encoding='utf-8',
                              capture_output=True, check=checked)

    def query(sql):
        return run(f'USE `{scratch}`;\n' + sql).stdout.strip()

    with DATA.open(encoding='utf-8', newline='') as stream:
        sources = list(csv.DictReader(stream))
    # The default generate() must be green on today's data (every managed service in ENTRIES,
    # the tome and the book stack included; ze2c had pinned the six, khe6 un-pinned it), and the
    # two shipped migrations together are exactly that: world_0007 (the original six, frozen since
    # it is applied) and world_0023 (the tome and its stack).
    generate()
    sql = generate(only=ORIGINAL_ENTRIES, summary='Four NPCs and two objects only.')
    sql_new = generate(only=TOME_STACK_ENTRIES)
    created = False
    try:
        run(f'CREATE DATABASE `{scratch}`;')
        created = True
        for table in ('creature', 'gameobject', 'dc_area_source', 'dc_area_spawn',
                      'dc_world_areas', 'dc_tier_phase'):
            query(f'CREATE TABLE `{table}` LIKE acore_world.`{table}`;')
        for table in ('dc_world_areas', 'dc_tier_phase'):
            query(f'INSERT INTO `{table}` SELECT * FROM acore_world.`{table}`;')
        # Live-style baseline: GM-created originals have zero area/zone metadata.
        for source in sources:
            row = json.loads(source['placement'])
            row.update(areaId=0, zoneId=0)
            query(insert(TABLES[source['kind']], row))
        # The live scan row is stale: g/8001491 names the TOME's entry and an old position.
        query("INSERT INTO dc_area_source (map_id,area_id,kind,source_guid,entry,source_phase,position_x,position_y,position_z,orientation) "
              "VALUES (530,3703,'g',8001491,910016,1,-2096.05,5492.37,50.366,1.25268);")

        stack = next(json.loads(r['placement']) for r in sources if json.loads(r['placement'])['id'] == STACK_ENTRY)
        float_yards = struct.unpack('<f', struct.pack('<f', float(tome_float_yards())))[0]

        def apply():
            query(sql)
            query(sql_new)

        def verify_tome_and_stack():
            # The tome hovers over its stack in EVERY tier, tier 1 included; the stack keeps its z.
            assert query(f'SELECT COUNT(*) FROM gameobject t JOIN gameobject b ON b.phaseMask=t.phaseMask '
                         f'AND b.id={STACK_ENTRY} WHERE t.id={TOME_ENTRY} AND t.position_x=b.position_x '
                         f'AND t.position_y=b.position_y AND t.position_z=b.position_z+{float_yards}') == '10'
            assert query(f'SELECT COUNT(*) FROM gameobject WHERE id={STACK_ENTRY} '
                         f"AND position_z={stack['position_z']}") == '10'
            assert query(f'SELECT COUNT(*) FROM gameobject WHERE id IN ({TOME_ENTRY},{STACK_ENTRY}) '
                         'AND areaId=3703 AND zoneId=3703') == '20'
            # A source scan row that named the wrong entry (live had g/8001491 as the tome) is corrected.
            assert query("SELECT entry FROM dc_area_source WHERE kind='g' AND source_guid=8001491") == str(STACK_ENTRY)
            assert query("SELECT entry FROM dc_area_source WHERE kind='g' AND source_guid=8001492") == str(TOME_ENTRY)

        def verify():
            assert query('SELECT COUNT(*) FROM creature') == '40'
            assert query('SELECT COUNT(*) FROM gameobject') == '40'
            assert query('SELECT COUNT(*) FROM dc_area_spawn') == '72'
            assert query('SELECT COUNT(*) FROM dc_area_source') == '8'
            for table, kind in (('creature', 'c'), ('gameobject', 'g')):
                assert query(f"SELECT COUNT(*) FROM {table} c JOIN dc_area_spawn m ON m.kind='{kind}' "
                             f"AND m.spawn_guid=c.guid JOIN {table} s ON s.guid=m.source_guid "
                             'WHERE c.id<>s.id OR c.map<>s.map OR c.phaseMask<>m.tier '
                             'OR c.position_x<>s.position_x OR c.position_y<>s.position_y '
                             'OR c.position_z<>s.position_z OR c.orientation<>s.orientation') == '0'
                counts = query(f'SELECT phaseMask,COUNT(*) FROM {table} GROUP BY phaseMask ORDER BY phaseMask')
                assert counts.splitlines() == [f'{tier}\t4' for tier in range(1, 11)]
            verify_tome_and_stack()
            assert query('SELECT COUNT(*) FROM gameobject WHERE id IN (180322,188215,910012,910013)') == '0'

        apply()
        verify()
        apply()
        verify()
        print('PASS existing originals, exact positions, all ten tiers and idempotent reapplication')
        for table in ('creature', 'gameobject', 'dc_area_source', 'dc_area_spawn'):
            query(f'DELETE FROM {table}')
        apply()
        verify()
        print('PASS fresh install restores original placements and all copies from CSV')

        # --- diablocraft-yeh2: guards tolerate float rounding against live, and never move live objects.
        # The incident's live values (update 2, 2026-09-30): the stack and the tome sat 0.003 yd off in y
        # and under 0.0001 in z and facing, from the CSV's stack position.
        stack_guid = next(int(r['source_guid']) for r in sources if json.loads(r['placement'])['id'] == STACK_ENTRY)
        tome_guid = next(int(r['source_guid']) for r in sources if json.loads(r['placement'])['id'] == TOME_ENTRY)
        stack_copies = json.loads(next(r['copy_guids'] for r in sources if int(r['source_guid']) == stack_guid))
        LIVE = dict(position_y=5492.43701171875, position_z=50.36644744873047, orientation=1.2244008779525757)

        def wipe():
            for table in ('creature', 'gameobject', 'dc_area_source', 'dc_area_spawn'):
                query(f'DELETE FROM {table}')

        def baseline(live_rows=True):
            wipe()
            for source in sources:
                row = json.loads(source['placement'])
                row.update(areaId=0, zoneId=0)
                query(insert(TABLES[source['kind']], row))
            if live_rows:
                for guid in (stack_guid, tome_guid):
                    query('UPDATE gameobject SET ' + ','.join(f'{k}={v!r}' for k, v in LIVE.items()) + f' WHERE guid={guid}')

        def value(table, guid, column):
            return float(query(f'SELECT CAST(`{column}` AS DOUBLE) FROM {table} WHERE guid={guid}'))

        def stored(v):
            return struct.unpack('<f', struct.pack('<f', v))[0]

        baseline()
        apply()   # the exact-equality guard rejected this on live (ERROR 3819 at line 7)
        for column, live in LIVE.items():
            assert value('gameobject', stack_guid, column) == stored(live), column   # the stack was not moved off live
        stack_now = {c: value('gameobject', stack_guid, c) for c in ('position_x', 'position_y', 'position_z', 'orientation')}
        assert abs(value('gameobject', tome_guid, 'position_y') - stored(LIVE['position_y'])) == 0   # tome xy kept too
        assert abs(value('gameobject', tome_guid, 'position_z') - (stored(LIVE['position_z']) + float_yards)) < 0.01   # the 1 yd float
        assert query(f"SELECT COUNT(*) FROM dc_area_source s JOIN gameobject g ON g.guid=s.source_guid WHERE s.kind='g' "
                     f'AND s.source_guid={stack_guid} AND s.position_x=g.position_x AND s.position_y=g.position_y '
                     'AND s.position_z=g.position_z AND s.orientation=g.orientation') == '1'   # the snapshot is the live row
        for tier, guid in stack_copies.items():   # copies made from the live source, not from the CSV
            for column, expected in stack_now.items():
                assert value('gameobject', guid, column) == expected, (tier, column)
        print('PASS a live row off by float rounding passes the guard and keeps its live position; copies follow the live source')

        # An existing copy that is off by rounding is accepted on reapplication and not rewritten.
        copy_guid = stack_copies['5']
        query(f'UPDATE gameobject SET position_y=position_y+0.003 WHERE guid={copy_guid}')
        moved = value('gameobject', copy_guid, 'position_y')
        apply()
        assert value('gameobject', copy_guid, 'position_y') == moved
        print('PASS a reapplied copy off by rounding is accepted and not moved')

        # A real distance fails: 1 yd on the source, 1 yd on a copy, 1 yd of facing is not rounding.
        for label, change in (('source 1 yd in y', f'UPDATE gameobject SET position_y=position_y+1 WHERE guid={stack_guid}'),
                              ('copy 1 yd in x', f'UPDATE gameobject SET position_x=position_x+1 WHERE guid={stack_copies["10"]}'),
                              ('source 0.05 yd in z', f'UPDATE gameobject SET position_z=position_z+0.05 WHERE guid={stack_guid}'),
                              ('copy 0.01 rad facing', f'UPDATE gameobject SET orientation=orientation+0.01 WHERE guid={stack_copies["3"]}')):
            baseline(); apply()
            query(change)
            before = query('SELECT * FROM gameobject ORDER BY guid') + query('SELECT * FROM dc_area_source ORDER BY source_guid')
            rejected = run(f'USE `{scratch}`;\n' + sql_new, checked=False)
            assert rejected.returncode != 0 and 'check constraint' in rejected.stderr.lower(), (label, rejected.stderr)
            assert query('SELECT * FROM gameobject ORDER BY guid') + query('SELECT * FROM dc_area_source ORDER BY source_guid') == before, label
        print('PASS a real distance (1 yd, 0.05 yd, 0.01 rad) fails the guard before any write')

        # Reverted: with the tolerance turned back into exact equality, the incident's rows are rejected,
        # so the rounding scenario above can fail.
        import re
        exact_new = re.sub(r"ABS\((`\w+`)-\(([^()]+)\)\)<[0-9.]+", r"\1=\2", sql_new)
        assert exact_new != sql_new
        baseline()
        rejected = run(f'USE `{scratch}`;\n' + exact_new, checked=False)
        assert rejected.returncode != 0 and 'check constraint' in rejected.stderr.lower(), rejected.stderr
        print('PASS the exact-equality guard rejects the incident rows (the tolerance is what lets them through)')
        wipe()
        for table in ('creature', 'gameobject', 'dc_area_source', 'dc_area_spawn'):
            query(f'DELETE FROM {table}')
        source = sources[0]
        row = json.loads(source['placement'])
        row.update(guid=json.loads(source['copy_guids'])['2'], phaseMask=2)
        query(insert(TABLES[source['kind']], row))
        rejected = run(f'USE `{scratch}`;\n' + sql, checked=False)
        assert rejected.returncode != 0 and 'check constraint' in rejected.stderr.lower(), rejected.stderr
        assert query('SELECT COUNT(*) FROM creature') == '1'
        assert query('SELECT COUNT(*) FROM gameobject') == '0'
        assert query('SELECT COUNT(*) FROM dc_area_spawn') == '0'
        assert query('SELECT COUNT(*) FROM dc_area_source') == '0'
        print('PASS occupied unowned GUID aborts before any placement writes')

        # Fountain uses the old migration as its portable baseline. Test-only
        # height comes from the old selector; it is never written to production CSV/SQL.
        with FOUNTAIN.open(encoding='utf-8', newline='') as stream:
            config = next(csv.DictReader(stream))
        test_dir = DATA.parents[3] / 'azerothcore-wotlk/build/_agent-scratch/scripts'
        test_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='fountain-test-', dir=test_dir) as directory:
            path = Path(directory) / 'picker.csv'

            def write_config():
                with path.open('w', encoding='utf-8', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(config))
                    writer.writeheader()
                    writer.writerow(config)

            config.update(position_z='', height_source='')
            write_config()
            try:
                generate_fountain(path)
            except ValueError as error:
                assert 'height is required' in str(error), error
            else:
                raise AssertionError('Unsourced fountain height accepted')
            picker = next(json.loads(r['placement']) for r in sources
                          if r['kind'] == 'g' and json.loads(r['placement'])['id'] == 910010)
            config.update(position_z=str(picker['position_z']), height_source='TEST FIXTURE ONLY: old selector height')
            write_config()
            fountain_sql = generate_fountain(path)

        query('CREATE TABLE gameobject_template LIKE acore_world.gameobject_template;')
        query('INSERT INTO gameobject_template SELECT * FROM acore_world.gameobject_template WHERE entry=910010;')

        def reset_fountain():
            for table in ('creature', 'gameobject', 'dc_area_source', 'dc_area_spawn'):
                query(f'DELETE FROM {table}')
            apply()
            query('UPDATE gameobject_template SET displayId=7017 WHERE entry=910010;')

        reset_fountain()
        other_before = query('SELECT * FROM gameobject WHERE id<>910010 ORDER BY guid')
        template_before = query('SELECT type,size,ScriptName,Data0,Data1,Data2,Data3,Data4 FROM gameobject_template WHERE entry=910010')
        query(fountain_sql)
        after = query('SELECT * FROM gameobject ORDER BY guid')
        query(fountain_sql)
        assert query('SELECT * FROM gameobject ORDER BY guid') == after
        stored_x, stored_y = (struct.unpack('<f', struct.pack('<f', float(config[k])))[0]
                              for k in ('position_x', 'position_y'))
        assert query('SELECT COUNT(*) FROM gameobject WHERE id=910010 AND map=530 '
                     f'AND position_x={stored_x} AND position_y={stored_y}') == '10'
        assert query('SELECT displayId FROM gameobject_template WHERE entry=910010') == config['display_id']
        assert query('SELECT type,size,ScriptName,Data0,Data1,Data2,Data3,Data4 FROM gameobject_template WHERE entry=910010') == template_before
        assert query('SELECT * FROM gameobject WHERE id<>910010 ORDER BY guid') == other_before
        assert query("SELECT COUNT(*) FROM dc_area_source s JOIN gameobject g ON g.guid=s.source_guid "
                     "WHERE s.kind='g' AND s.entry=910010 AND s.position_x=g.position_x "
                     'AND s.position_y=g.position_y AND s.position_z=g.position_z AND s.orientation=g.orientation') == '1'
        print('PASS fountain requires sourced height, moves all ten tiers, updates source, preserves other objects/template behavior, and reapplies idempotently')

        for sabotage in ("UPDATE gameobject SET position_x=0 WHERE guid=8001478;",
                         "UPDATE dc_area_spawn SET spawn_guid=1 WHERE kind='g' AND source_guid=8001468 AND tier=10;"):
            reset_fountain()
            query(sabotage)
            before = query('SELECT * FROM gameobject ORDER BY guid')
            rejected = run(f'USE `{scratch}`;\n' + fountain_sql, checked=False)
            assert rejected.returncode != 0 and 'check constraint' in rejected.stderr.lower(), rejected.stderr
            assert query('SELECT * FROM gameobject ORDER BY guid') == before
            assert query('SELECT displayId FROM gameobject_template WHERE entry=910010') == '7017'
        print('PASS fountain refuses moved spawns or lost tier ownership before any placement/template writes')

        # --- diablocraft-pillar-restore: world_0024 undoes the fountain move that live carries.
        restore_sql = generate_pillar_restore()
        assert generate_pillar_restore() == restore_sql

        def pillar_state():
            return (query('SELECT * FROM gameobject ORDER BY guid') + query('SELECT * FROM dc_area_source ORDER BY source_guid')
                    + query('SELECT displayId FROM gameobject_template WHERE entry=910010'))

        reset_fountain()                       # original state: what a fresh install holds
        original = pillar_state()
        other_before = query('SELECT * FROM gameobject WHERE id<>910010 ORDER BY guid')
        query(restore_sql)
        assert pillar_state() == original      # a fresh install is a no-op
        query(restore_sql)
        assert pillar_state() == original
        print('PASS pillar restore on the original state is a no-op and idempotent')

        query(fountain_sql)                    # live state: the picker sits in the fountain, display 6476
        assert pillar_state() != original and query('SELECT displayId FROM gameobject_template WHERE entry=910010') == '6476'
        query(restore_sql)
        assert pillar_state() == original      # all ten rows, dc_area_source and the display are back
        assert query('SELECT * FROM gameobject WHERE id<>910010 ORDER BY guid') == other_before
        query(restore_sql)
        assert pillar_state() == original
        orig_row = next(json.loads(r['placement']) for r in sources if json.loads(r['placement'])['id'] == 910010)
        assert query('SELECT COUNT(*) FROM gameobject WHERE id=910010 AND map=530 '
                     f"AND position_x={stored(orig_row['position_x'])} AND position_y={stored(orig_row['position_y'])} "
                     f"AND position_z={stored(orig_row['position_z'])} AND orientation={stored(orig_row['orientation'])} "
                     f"AND rotation2={stored(orig_row['rotation2'])} AND rotation3={stored(orig_row['rotation3'])}") == '10'
        assert query('SELECT displayId FROM gameobject_template WHERE entry=910010') == '7017'
        print('PASS pillar restore on the fountain state returns all ten rows, dc_area_source and the display, and is idempotent')

        # A third state is refused before any write, from either starting state.
        for start in (None, fountain_sql):
            for label, sabotage in (('one row elsewhere', 'UPDATE gameobject SET position_x=position_x+5 WHERE guid=8001478;'),
                                    ('source elsewhere', "UPDATE dc_area_source SET position_y=position_y+5 WHERE source_guid=8001468 AND kind='g';"),
                                    ('unknown display', 'UPDATE gameobject_template SET displayId=1 WHERE entry=910010;'),
                                    ('lost tier ownership', "UPDATE dc_area_spawn SET spawn_guid=1 WHERE kind='g' AND source_guid=8001468 AND tier=10;")):
                reset_fountain()
                if start:
                    query(start)
                query(sabotage)
                before = pillar_state() + query('SELECT * FROM dc_area_spawn ORDER BY spawn_guid')
                rejected = run(f'USE `{scratch}`;\n' + restore_sql, checked=False)
                assert rejected.returncode != 0 and 'check constraint' in rejected.stderr.lower(), (label, rejected.stderr)
                assert pillar_state() + query('SELECT * FROM dc_area_spawn ORDER BY spawn_guid') == before, label
        print('PASS pillar restore refuses a third state (moved row, moved source, unknown display, lost ownership) before any write')

        # The guard is what refuses: with it stripped, the same third state is rewritten.
        reset_fountain()
        query('UPDATE gameobject SET position_x=position_x+5 WHERE guid=8001478;')
        unguarded = '\n'.join(l for l in restore_sql.splitlines() if 'dc_pillar_guard' not in l)
        query(unguarded)
        assert pillar_state() == original
        print('PASS mutation: without the guard the third state is overwritten, so the refusal above is the guard')
    finally:
        if created:
            run(f'DROP DATABASE `{scratch}`;')


if __name__ == '__main__':
    main()

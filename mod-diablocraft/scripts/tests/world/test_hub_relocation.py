"""Apply/rerun the hub migration on a separate copy; never mutate live tables."""
import argparse
import re
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_area_copies import Database
from generate_hub_relocation import point_rows, read

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysql', default=None)
    parser.add_argument('--defaults-file', default=None)
    parser.add_argument('--fixture', default='dc_hub_test_' + __import__('time').strftime('%Y%m%d_%H%M%S') + '_' + str(__import__('os').getpid()))
    parser.add_argument('--keep', action='store_true', help='keep the fixture database for inspection')
    args = parser.parse_args()
    if not (args.mysql and args.defaults_file):
        import fixture_db
        fixture_mysql, fixture_defaults = fixture_db.mysql_and_defaults([])
        args.mysql, args.defaults_file = args.mysql or fixture_mysql, args.defaults_file or fixture_defaults
    if not re.fullmatch(r'dc_hub_test_[0-9_]+', args.fixture):
        raise ValueError('Fixture must be a dedicated dc_hub_test_<date> database')
    source = Database(args.mysql, args.defaults_file, 'acore_world')
    if source.query(f"SELECT SCHEMA_NAME FROM information_schema.schemata WHERE SCHEMA_NAME='{args.fixture}'"):
        raise ValueError('Fixture already exists; choose a fresh name')
    migration = (ROOT / 'data/generated/world_0005_shattrath_hub.sql').read_text(encoding='utf-8')
    assert migration == (ROOT / 'data/sql/db-world/updates/world_0005_shattrath_hub.sql').read_text(encoding='utf-8')
    tables = set(re.findall(r'DELETE s FROM `?(\w+)', migration))
    tables.update(('dc_world_hub', 'dc_world_areas', 'playercreateinfo', 'creature_template', 'creature_template_model'))
    setup = [f'CREATE DATABASE `{args.fixture}`;']
    for table in sorted(tables):
        setup += [f'CREATE TABLE `{args.fixture}`.`{table}` LIKE acore_world.`{table}`;',
                  f'INSERT INTO `{args.fixture}`.`{table}` SELECT * FROM acore_world.`{table}`;']
    source.query('\n'.join(setup))
    try:
        fixture = Database(args.mysql, args.defaults_file, args.fixture)
        before = {t: int(fixture.query(f'SELECT COUNT(*) FROM {t}')[0]) for t in ('creature', 'gameobject')}
        expected = {}
        for kind, table in (('c', 'creature'), ('g', 'gameobject')):
            rows = [r for r in read('world_hub_native_spawns.csv') if r['kind'] == kind]
            predicate = ' OR '.join(f"(guid={int(r['guid'])} AND id={int(r['entry'])})" for r in rows)
            expected[table] = int(fixture.query(f'SELECT COUNT(*) FROM {table} WHERE map=530 AND ({predicate})')[0])
        for attempt in (1, 2):
            fixture.query(migration)
            for table in before:
                assert int(fixture.query(f'SELECT COUNT(*) FROM {table}')[0]) == before[table] - expected[table]
            for row in point_rows():
                actual = fixture.rows('dc_world_hub_point', f"name='{row['name']}'")[0]
                for key in ('map_id', 'area_id', 'x', 'y', 'z', 'o'):
                    assert abs(float(actual[key]) - float(row[key])) < 1e-8, (key, actual, row)
            assert fixture.query("SELECT npcflag,ScriptName FROM creature_template WHERE entry=910003") == ['1\tdc_rift_keeper']
            assert fixture.query("SELECT status FROM dc_world_areas WHERE map_id=1 AND area_id=876") == ['closed']
            assert fixture.query("SELECT phase_scope,status FROM dc_world_areas WHERE map_id=530 AND area_id=3703") == ['all\topen']
            print(f'PASS apply {attempt}: exact GPS, hub rules, Rift Keeper, removed {expected}, no other spawn rows removed')
    finally:
        if args.keep:
            print(f'Fixture retained for inspection: {args.fixture}')
        else:
            source.query(f'DROP DATABASE IF EXISTS `{args.fixture}`')


if __name__ == '__main__':
    main()

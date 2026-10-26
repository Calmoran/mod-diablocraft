"""Rift floors Part F5 (diablocraft-97sz): an open zone is one more floor map.

Un'Goro Crater (rift_open_zones.csv, map 751, the rift copy of Kalimdor) joins the rift pool, so the obelisk can open it as floor 1 and an exit
portal can lead to it as a later floor, with the stock machinery of F1 and F2 and the spawner of S6. What is checked here:
  * rifts_0024 is what generate_rifts.py renders from the zone sheet and the designer's entrance (rifts.csv open_rift_entry_*), and the generated
    mirror says the same: one row, id above the dungeons', map 751 as the Map row of world_open_rift_dbc.csv has it, the name the zone's;
  * rifts_0001 is untouched (applied and frozen) and the two replayed on the fixture mysqld, twice, give 31 rows with the zone once;
  * the zone's name is the one the spawner's sheets and the exit spots use (areas and anchors exist under it), no dungeon shares its name or
    its map, and the Map row is a party instance, so the pool can make a floor of it;
  * diablocraft-hmnei: each zone has its own entrance rows (rift_open_zones.csv entry_tunable); a zone whose rows are all blank is off
    (no pool row), half an entrance is refused, none at all is refused, and each zone with one gets its own id by sheet row;
  * `.dc floor exit here` on the zone: generate_rift_survey.py --export puts the designer's spot in the zone's exit row (each zone has one, its
    farthest anchor, diablocraft-yh7el; a zone without one gets a new row after the others), and the zone's migration renders it; an unknown
    name is still refused;
  * source mutants of both generators, each turning a check red.
What needs the worldserver (a rift opening on Un'Goro, an exit leading there, the zone wall with a rift in it) is held by
docs/test-diablocraft-97sz.md on dev."""
import contextlib
import csv
import re
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_rift_survey as S0  # noqa: E402
import generate_rifts as G  # noqa: E402
import test_rift_exit as T  # noqa: E402

MODULE = T.MODULE
D3, UPDATES, SCRATCH = T.D3, T.UPDATES, T.SCRATCH
ZONE = "Un'Goro Crater"
GENERATOR = Path(G.__file__)
SURVEY = Path(S0.__file__)


def zone_rows():
    return T.csv_rows(D3 / 'rift_open_zones.csv')


def entrance(prefix='open_rift_entry'):
    """A zone's four <prefix>_ rows of rifts.csv, read here without the generator's reader."""
    rows = {r['name']: r['value'] for r in T.csv_rows(MODULE / 'data/tunables/rifts.csv')}
    return [float(rows[f'{prefix}_{axis}']) for axis in 'xyzo']


def pool_rows(migration_text):
    return re.findall(r"^\((\d+), (\d+), '((?:[^']|'')*)', (-?[\d.]+), (-?[\d.]+), (-?[\d.]+), (-?[\d.]+), (\d+), '(\w+)'\);?,?$",
                      migration_text, re.M)


def check_rows(text):
    """The migration text against the sheets, each zone's entrance and the pool of dungeons. hmnei: the designer's .gps of 2026-10-11 gave
    the other four zones their entrances, so all five are rows, in sheet order, ids 1001 up."""
    zones = zone_rows()
    assert zones[0]['key'] == 'ungoro' and zones[0]['entry_tunable'] == 'open_rift_entry' and zones[0]['name'] == ZONE
    rows = pool_rows(text)
    assert len(rows) == len(zones) >= 5, rows   # hyoic.5: the acts add zones; the first five keep their ids
    for index, (zone, row) in enumerate(zip(zones, rows), start=1):
        dungeon_id, map_id, name, x, y, z, o, kills, length = row
        assert name.replace("''", "'") == zone['name']
        assert int(map_id) == int(zone['map_id']) and int(map_id) in (751, 752, 753)   # hyoic.8, hyoic.10: Kalimdor's copy, the Eastern Kingdoms' or Outland's
        assert [float(x), float(y), float(z), float(o)] == entrance(zone['entry_tunable']), zone['key']
        assert int(dungeon_id) == 1000 + index and int(dungeon_id) > len(T.POOL)   # above the dungeons', so none takes it later
        assert (kills, length) == ('0', 'open')                                    # nothing reads either column since S3
    assert 'DELETE FROM `dc_rift_dungeon` WHERE `dungeon_id` >= 1000;' in text
    # the map is the sheet's Map row, a party instance, and no dungeon of the pool shares it
    sheet = T.csv_rows(D3 / 'world_open_rift_dbc.csv')
    assert [r['value'] for r in sheet if r['table'] == 'Map' and r['id'] == '751' and r['field'] == 'InstanceType'] == ['1']
    assert not [r for r in T.csv_rows(D3 / 'rift_dungeons.csv') if r['map_id'] == '751']


def check_replay(text):
    """rifts_0001 then the zones' migration, applied twice (the updater may apply it again): 30 dungeons and one row a zone, each zone once."""
    pool_sql = T.read(UPDATES / 'rifts_0001_dungeon_pool.sql')
    assert "751" not in pool_sql and len(re.findall(r"^\(\d+, \d+, '", pool_sql, re.M)) == 30       # applied and frozen: untouched
    with T.Scratch() as scratch:
        scratch.run(pool_sql)
        for _ in range(2):
            scratch.run(text)
        rows = scratch.db.rows('dc_rift_dungeon')
    zones_on = len(zone_rows())      # diablocraft-hyoic.5: the sheet grows with the acts, the count follows it
    assert len(rows) == 30 + zones_on
    names = [r['name'] for r in rows]
    assert len(set(names)) == 30 + zones_on and names.count(ZONE) == 1                  # the spawner and the exit spots find a map's sheets by name
    zone_names = [z['name'] for z in zone_rows()]
    assert sorted(r['dungeon_id'] for r in rows if r['name'] in zone_names) == list(range(1001, 1001 + zones_on))
    zone = next(r for r in rows if r['name'] == ZONE)
    assert zone['dungeon_id'] == 1001 and zone['map_id'] == 751 and zone['approximate_length'] == 'open'
    assert [round(zone['entry_' + a], 4) for a in 'xyzo'] == [round(v, 4) for v in entrance()]
    assert sorted(r['dungeon_id'] for r in rows if r['name'] not in zone_names) == list(range(1, 31))       # the dungeons are as they were
    assert sorted(r['map_id'] for r in rows).count(751) == sum(z['map_id'] == '751' for z in zone_rows())   # hyoic.8, hyoic.10: the rest are on 752 and 753


def check_refusals(g):
    """Each zone reads its own entrance rows: all blank is off, half is refused, none set anywhere is refused; ids follow the sheet."""
    with tempfile.TemporaryDirectory(prefix='rift-open-floor-', dir=SCRATCH) as folder:
        zones = Path(folder) / 'zones.csv'
        zones.write_text('key,name,map_id,source_map,zone_id,entry_tunable,act,notes\n'
                         'a,A,751,1,490,ea,2,\nb,B,751,1,440,eb,2,\nc,C,751,1,400,ec,2,\n', encoding='utf-8')
        def pool(sheet):
            def value(category, key, *args):
                if key not in sheet:
                    raise g.tunables_csv.MissingTunable(key)
                return sheet[key]
            with mock.patch.object(g, 'OPEN_ZONE_SOURCE', zones), mock.patch.object(g.tunables_csv, 'value', side_effect=value):
                return g.read_open_zones()
        full = lambda prefix, base: {f'{prefix}_{a}': base + n for n, a in enumerate('xyzo')}
        got = pool({**full('ea', 10.0), **full('ec', 30.0)})
        assert [(z['dungeon_id'], z['name'], z['x'], z['o']) for z in got] == [(1001, 'A', 10.0, 13.0), (1003, 'C', 30.0, 33.0)], got
        got = pool(full('eb', 20.0))
        assert [(z['dungeon_id'], z['name'], z['y']) for z in got] == [(1002, 'B', 21.0)], got
        for axis in 'xyzo':
            half = full('eb', 20.0)
            del half['eb_' + axis]
            try:
                pool(half)
            except SystemExit as stop:
                assert 'eb_' in str(stop)
            else:
                raise AssertionError('half an entrance was taken: ' + axis)
        try:
            pool({})
        except SystemExit as stop:
            assert 'no zone has an entrance' in str(stop)
        else:
            raise AssertionError('a pool with no entrance was made')


def check_wiring(source):
    assert 'write_migration(MODULE_ROOT, UPDATES / OPEN_ZONE_MIGRATION, zone_text)' in source
    assert '(GENERATED / "rift_open_zone_pool.sql").write_bytes(zone_text.encode("utf-8"))' in source


def check_generator(g, source):
    text = g.open_zone_sql(g.read_open_zones())
    check_rows(text)
    check_replay(text)
    check_refusals(g)
    check_wiring(source)


def test_the_committed_migration_is_what_the_generator_renders():
    assert G.OPEN_ZONE_MIGRATION == 'rifts_0028_open_zone_pool.sql'
    text = T.read(UPDATES / G.OPEN_ZONE_MIGRATION)
    assert text == T.read(MODULE / 'data/generated/rift_open_zone_pool.sql') == G.open_zone_sql(G.read_open_zones())


def test_the_generator_makes_the_pool_row():
    check_generator(G, GENERATOR.read_text(encoding='utf-8'))


def test_the_zone_has_the_sheets_the_spawner_and_the_exit_read():
    for zone in (z['name'] for z in zone_rows()):          # hmnei: every zone in the pool has its survey rows
        for sheet in ('rift_areas.csv', 'rift_anchors.csv'):
            assert [r for r in T.csv_rows(D3 / sheet) if r['dungeon'] == zone], f"{sheet} has no rows under {zone}"
        assert zone not in {r['name'] for r in T.csv_rows(D3 / 'rift_dungeons.csv')}
        assert len([r for r in T.csv_rows(D3 / 'rift_exit_points.csv') if r['dungeon'] == zone]) == 1   # its far point or the designer's (yh7el)


def check_export(survey):
    """the designer placed the exit of a zone that has no row yet: --export brings it home as a new row after the others. Every zone has its
    farthest anchor's row now (yh7el), so the zone's row is taken out of the scratch database first, as a zone added before its survey."""
    committed = [r for r in T.csv_rows(D3 / 'rift_exit_points.csv') if r['dungeon'] != ZONE]
    with T.Scratch() as scratch, tempfile.TemporaryDirectory(prefix='rift-open-floor-', dir=SCRATCH) as folder:
        folder = Path(folder)
        for sheet in list(survey.SHEETS) + ['rift_open_zones.csv']:
            (folder / sheet).write_bytes((D3 / sheet).read_bytes())
        scratch.run("DELETE FROM dc_rift_exit_point WHERE dungeon = 'Un''Goro Crater'")
        scratch.run("REPLACE INTO dc_rift_exit_spot VALUES ('Un''Goro Crater', -7000.5, -2200.25, -190.125, 1.5)")
        survey.export(scratch.db, folder)
        exported = T.csv_rows(folder / 'rift_exit_points.csv')
        assert [r['dungeon'] for r in exported] == [r['dungeon'] for r in committed] + [ZONE]
        zone = exported[-1]
        assert (zone['x'], zone['y'], zone['z'], zone['o'], zone['walk_yards'], zone['source']) == ('-7000.5', '-2200.25', '-190.125', '1.5', '', 'alex')
        numbers = lambda value: round(float(value), 4) if re.fullmatch(r'-?\d+(\.\d+)?', value) else value      # the MySQL round trip
        assert [{k: numbers(v) for k, v in r.items()} for r in exported[:-1]] == [{k: numbers(v) for k, v in r.items()} for r in committed]
        sheets = survey.read_sheets(folder)
        assert survey.has_alex(sheets)
        dungeons_sql = survey.render(sheets)
        zones_sql = survey.render(sheets, {ZONE})
        assert 'Un\'\'Goro' not in dungeons_sql.split('dc_rift_exit_point')[-1]       # 0001 is the dungeons'
        assert re.search(r"INSERT INTO `dc_rift_exit_point`[^;]*\('Un''Goro Crater', -7000.5, -2200.25, -190.125, 1.5, NULL, 'alex'\)", zones_sql)
        # a name that is neither a dungeon nor a zone is still refused
        scratch.run("DELETE FROM dc_rift_exit_spot; REPLACE INTO dc_rift_exit_spot VALUES ('Nowhere', 1, 2, 3, 4)")
        try:
            survey.export(scratch.db, folder)
        except ValueError as error:
            assert 'Nowhere' in str(error)
        else:
            raise AssertionError('an unknown name was exported')


def test_alexs_exit_in_the_zone_comes_home_through_export():
    check_export(S0)


MUTANTS = [
    (GENERATOR, 'G', 'a later dungeon row could take the zone\'s id', 'OPEN_ZONE_ID_BASE = 1000', 'OPEN_ZONE_ID_BASE = 0'),
    (GENERATOR, 'G', 'the entrance is the x row for every axis', 'f"{row[\'entry_tunable\']}_{axis}"', 'f"{row[\'entry_tunable\']}_x"'),
    (GENERATOR, 'G', 'every zone reads Un\'Goro\'s entrance', 'f"{row[\'entry_tunable\']}_{axis}"', 'f"open_rift_entry_{axis}"'),
    (GENERATOR, 'G', 'the row is not replaced on a second apply', 'f"DELETE FROM `dc_rift_dungeon` WHERE `dungeon_id` >= {OPEN_ZONE_ID_BASE};",', '""'),
    (GENERATOR, 'G', 'the row has another name than the zone', 'quote(z["name"])', 'quote("Ungoro")'),
    (GENERATOR, 'G', 'the row is on another map', '"map_id": int(row["map_id"]), "name"', '"map_id": 1, "name"'),
    (GENERATOR, 'G', 'the zone replaces the dungeons\' rows', 'f"DELETE FROM `dc_rift_dungeon` WHERE `dungeon_id` >= {OPEN_ZONE_ID_BASE};"', '"DELETE FROM `dc_rift_dungeon`;"'),
    (GENERATOR, 'G', 'half an entrance is taken', 'if len(point) != 4:', 'if False:'),
    (GENERATOR, 'G', 'the ids are not the sheet rows', '"dungeon_id": OPEN_ZONE_ID_BASE + index', '"dungeon_id": OPEN_ZONE_ID_BASE + len(zones) + 1'),
    (GENERATOR, 'G', 'the migration is not written', 'write_migration(MODULE_ROOT, UPDATES / OPEN_ZONE_MIGRATION, zone_text)', 'pass'),
    (SURVEY, 'S', 'the export refuses the zone\'s exit', 'for name in sorted((set(spots) & open_zone_names(directory)) - {row["dungeon"] for row in rows}):', 'for name in []:'),
    (SURVEY, 'S', 'the export adds any name', 'for name in sorted((set(spots) & open_zone_names(directory)) - {row["dungeon"] for row in rows}):', 'for name in sorted(set(spots) - {row["dungeon"] for row in rows}):'),
    (SURVEY, 'S', 'the zone\'s exit is not the designer\'s', 'row.update(x=spot["x"], y=spot["y"], z=spot["z"], o=spot["o"], walk_yards="", source="alex")', 'row.update(x=spot["x"], y=spot["y"], z=spot["z"], o=spot["o"], walk_yards="", source="survey")'),
]


def module_from(path, old, new):
    module = types.ModuleType('mutant_' + path.stem)
    module.__file__ = str(path)
    exec(compile(T.mutate(path.read_text(encoding='utf-8'), old, new), str(path), 'exec'), module.__dict__)
    return module


def test_mutants_are_killed():
    for path, who, what, old, new in MUTANTS:
        mutant = module_from(path, old, new)
        try:
            with contextlib.redirect_stdout(open('/dev/null', 'w')):
                if who == 'S':
                    check_export(mutant)
                else:
                    check_generator(mutant, T.mutate(path.read_text(encoding='utf-8'), old, new))
        except (AssertionError, ValueError, KeyError, IndexError, SystemExit, FileNotFoundError):
            print('PASS mutant killed:', what)
            continue
        raise AssertionError('mutant survived: ' + what)


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('PASS', name)

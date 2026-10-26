"""Monster spawning Part S5 (diablocraft-tyt6): patrols on the maps' own paths and the designer's recorded routes.

What runs here, against the production code as it stands:
  * the planner (src/rifts/dc_rift_spawn.h) compiled with tests/rift_spawn/harness.cpp and fed the generated sheets plus the survey's
    516 stock routes (rift_routes.csv): a patrol only where a route is tied to the picked anchor, one of that anchor's own routes, the
    patrol recipe's bodies, elite rolls and the floor's minimum on patrols, the body cap, the summary, the replay from a seed; and no
    patrol anywhere when the share is blank or the dungeon has no route (ruling 2026-10-08: no made-up routes);
  * the recording rules (src/rifts/dc_rift_patrol.h) compiled with tests/rift_patrol/harness.cpp: the sampling step, the last point,
    the anchor tie, the next path id, the SQL;
  * the generator (scripts/generate/rifts/generate_rift_patrols.py): the sheet's rules, the migration (its DELETE stays inside the designer's id range and leaves
    the stock paths alone), and the whole chain on the fixture mysqld: the SQL the recording writes -> --export -> the sheet -> the
    migration -> the same waypoint_data rows;
  * source checks on the glue the worldserver alone can run (the leader on MoveWaypoint, the followers on MoveFollow, the patrol start, the
    command and the sampler).
What it does NOT cover: a patrol walking in game (docs/test-diablocraft-tyt6.md, on dev).

Mutants: every rule has a single-rule mutant that must turn the run red (test_mutants_are_killed).
DC_RIFT_PATROL_RIFTS points the source checks at a copy of src/rifts, DC_RIFT_PATROL_GENERATOR at a mutated generator."""
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import harness_env  # noqa: E402
import test_rift_spawn as spawn  # noqa: E402

ROOT, MODULE, SCRATCH = spawn.ROOT, spawn.MODULE, spawn.SCRATCH
RIFTS = Path(os.environ.get('DC_RIFT_PATROL_RIFTS', MODULE / 'src/rifts'))
GENERATOR = Path(os.environ.get('DC_RIFT_PATROL_GENERATOR', MODULE / 'scripts/generate/rifts/generate_rift_patrols.py'))
read, csv_rows, mutate = spawn.read, spawn.csv_rows, spawn.mutate
ROUTES = spawn.ROUTES
WITH_ROUTES = [d for d in spawn.DUNGEONS if any(r['dungeon'] == d for r in ROUTES)]
ROUTE_AT = defaultdict(list)       # (dungeon, anchor) -> [path ids]
for _r in ROUTES:
    ROUTE_AT[(_r['dungeon'], int(_r['anchor']))].append(int(_r['path_id']))
RUNS = [(d, g, seed, floor, prev) for d in WITH_ROUTES for g in (0, 1) for seed in (11, 12345, 987654321) for floor, prev in ((1, 0), (2, 3))]
QUIET = {'elite_chance_pct': 0, 'elite_packs_min': 0, 'elite_packs_max': 99, 'floor_body_cap': 0}   # no elite pass, no cap


def load_generator():
    spec = importlib.util.spec_from_file_location('generate_rift_patrols_under_test', GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- the planner -------------------------------------------------------------------------------------------------------------------

def recipe_for(family):
    return spawn.RECIPE.get(('patrol', family)) or spawn.RECIPE[('patrol', '')]


def patrol_problems(header_text):
    """[problem] on what the planner does with routes; empty when every promise holds."""
    bad = []
    with spawn.Harness(header_text) as harness:
        def plan(knobs, runs=RUNS, routes=None):
            return harness.plan(spawn.sheet_text({**QUIET, **knobs}, routes=routes), runs)

        every = plan({'patrol_share_pct': 100, 'solo_share_pct': 20})
        sizes = defaultdict(set)
        for r in every:
            patrols = [p for p in r['placements'] if p['kind'] == 'patrol']
            if r.get('patrols') != len(patrols):
                bad.append(f"{r['dungeon']}: the plan counts {r.get('patrols')} patrols, lists {len(patrols)}")
            if r['sum'][0] != sum(p['kind'] != 'solo' for p in r['placements']):
                bad.append(f"{r['dungeon']}: clusters {r['sum'][0]} do not count the patrols")
            for p in r['placements']:
                own = ROUTE_AT.get((r['dungeon'], p['anchor']), [])
                if p['kind'] == 'patrol':
                    if p['route'] not in own:
                        bad.append(f"{r['dungeon']} anchor {p['anchor']}: route {p['route']} is not one of its routes {own}")
                    recipe = recipe_for(p['family'])
                    if not recipe['bodies'][0] <= len(p['monsters']) <= recipe['bodies'][1]:
                        bad.append(f"{r['dungeon']} anchor {p['anchor']}: a {p['family']} patrol of {len(p['monsters'])} bodies, recipe {recipe['bodies']}")
                    sizes[p['family']].add(len(p['monsters']))
                    if any(spawn.MONSTER[m]['solo'] for m in p['monsters']):
                        bad.append(f"{r['dungeon']} anchor {p['anchor']}: a solo monster in a patrol")
                    if p['family'] not in spawn.SETS[r['set']]['clusterable']:
                        bad.append(f"{r['dungeon']} anchor {p['anchor']}: patrol family {p['family']} cannot cluster in its set")
                elif own and p['kind'] != 'patrol':
                    bad.append(f"{r['dungeon']} anchor {p['anchor']}: a routed anchor holds a {p['kind']} at share 100")
        if not any(r['placements'] and any(p['kind'] == 'patrol' for p in r['placements']) for r in every):
            bad.append('no patrol at share 100')
        if sizes and max(max(s) for s in sizes.values()) != max(recipe_for(f)['bodies'][1] for f in sizes):
            bad.append(f'a patrol never reaches the recipe maximum: {dict((f, max(s)) for f, s in sizes.items())}')
        swarm = sizes.get('Swarm')
        if swarm and swarm != {3}:
            bad.append(f'a Swarm patrol is not exactly 3: {swarm}')

        # the share is a tunable: blank is none, and no route anywhere is none (4.11: nothing is made up)
        for r in plan({'patrol_share_pct': 0}):
            if r['patrols'] or any(p['kind'] == 'patrol' for p in r['placements']):
                bad.append(f"{r['dungeon']}: a patrol at share 0")
        for r in plan({'patrol_share_pct': 100}, routes=[]):
            if r['patrols'] or any(p['kind'] == 'patrol' for p in r['placements']):
                bad.append(f"{r['dungeon']}: a patrol where the dungeon has no route")
        half = plan({'patrol_share_pct': 50})
        walking = sum(p['kind'] == 'patrol' for r in half for p in r['placements'])
        standing = sum(p['kind'] != 'patrol' and bool(ROUTE_AT.get((r['dungeon'], p['anchor']))) for r in half for p in r['placements'])
        if not walking or not standing:
            bad.append(f'share 50 gave {walking} patrols and {standing} routed anchors that stayed clusters')

        # a patrol rolls elite like a cluster (3.9.2) and keeps its route; the floor's minimum counts patrols
        packs = plan({'patrol_share_pct': 100, 'elite_chance_pct': 100, 'elite_champion_pct': 50, 'elite_packs_max': 99})
        elite = [p for r in packs for p in r['placements'] if p['kind'] == 'patrol']
        if not elite or not all(p['elite'] and p['route'] and p['leader'] in p['monsters'] for p in elite):
            bad.append('a patrol does not roll elite, or an elite patrol loses its route or its leader')
        floor_min = plan({'patrol_share_pct': 100, 'elite_chance_pct': 0, 'elite_packs_min': 3, 'elite_packs_max': 99, 'solo_share_pct': 0})
        if not any(p['kind'] == 'patrol' and p['elite'] for r in floor_min for p in r['placements']):
            bad.append('the floor minimum does not turn a patrol elite')
        capped = plan({'patrol_share_pct': 100, 'floor_body_cap': 30})
        if any(r['sum'][3] > 30 for r in capped) or not any(r['patrols'] for r in capped):
            bad.append('the body cap does not hold on patrols')
        if plan({'patrol_share_pct': 100, 'solo_share_pct': 20}) != every:
            bad.append('a floor does not replay from its seed')

        # two routes tied to one anchor: both are used
        dungeon = WITH_ROUTES[0]
        row = next(r for r in ROUTES if r['dungeon'] == dungeon)
        twin = dict(row, path_id='123456789')
        seen = {p['route'] for r in plan({'patrol_share_pct': 100}, [(dungeon, 0, s, 1, 0) for s in range(1, 301)],
                                         routes=[row, twin]) for p in r['placements'] if p['anchor'] == int(row['anchor'])}
        if seen != {int(row['path_id']), 123456789}:
            bad.append(f'two routes on one anchor: only {seen} used')
    return bad


def test_the_planner_gives_patrols_only_routes_that_exist():
    bad = patrol_problems(read(spawn.HEADER))
    assert not bad, bad[:8]


# --- the recording rules -----------------------------------------------------------------------------------------------------------

class Recorder:
    """tests/rift_patrol/harness.cpp compiled against the production dc_rift_patrol.h (or a mutated copy)."""

    def __init__(self, patrol_header, spawn_header):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self._folder = tempfile.TemporaryDirectory(prefix='rift-patrol-', dir=SCRATCH)
        folder = Path(self._folder.name)
        (folder / 'dc_rift_patrol.h').write_text(patrol_header, encoding='utf-8')
        (folder / 'dc_rift_spawn.h').write_text(spawn_header, encoding='utf-8')
        done = subprocess.run(['c++', '-std=c++20', '-O1', '-UNDEBUG', '-Wall', '-Wextra', f'-I{folder}', str(MODULE / 'tests/rift_patrol/harness.cpp'),
                               '-o', str(folder / 'harness')], capture_output=True, text=True)
        assert done.returncode == 0, 'COMPILE ' + done.stderr[-1500:]
        self.exe = str(folder / 'harness')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._folder.cleanup()

    def run(self, lines):
        ran = harness_env.run([self.exe], input='\n'.join(lines) + '\n', capture_output=True, text=True)
        assert ran.returncode == 0, ran.stderr[-1500:]
        return [line.split('\t') for line in ran.stdout.splitlines()]


def points_of(rows):
    return [tuple(float(c) for c in r[1:]) for r in rows if r[0] == 'P']


def recording_problems(patrol_header, spawn_header):
    bad = []
    with Recorder(patrol_header, spawn_header) as rec:
        # a straight 100-yard walk sampled every yard, step 10: a point at least every 10 yards, the first at the start, the last where he stopped
        walk = ['record 10 Ragefire Chasm'] + [f'add {x} 0 0' for x in range(0, 101)] + ['finish 100 0 0', 'show']
        pts = points_of(rec.run(walk))
        if pts[0] != (0, 0, 0) or pts[-1] != (100, 0, 0):
            bad.append(f'the walk starts {pts[0]} and ends {pts[-1]}')
        if not 10 <= len(pts) <= 12 or any(b[0] - a[0] < 10 - 1e-6 for a, b in zip(pts, pts[1:-1])):
            bad.append(f'a step of 10 over 100 yards kept {len(pts)} points: {pts}')
        # the last point is where he stopped even inside a step, once
        pts = points_of(rec.run(['record 10 Dungeon', 'add 0 0 0', 'add 3 0 0', 'finish 4 0 0', 'show']))
        if pts != [(0, 0, 0), (4, 0, 0)]:
            bad.append(f'the stop is not the last point: {pts}')
        pts = points_of(rec.run(['record 10 Dungeon', 'add 0 0 0', 'add 10 0 0', 'finish 10 0 0', 'show']))
        if pts != [(0, 0, 0), (10, 0, 0)]:
            bad.append(f'the stop is added twice: {pts}')
        # height counts toward the step
        pts = points_of(rec.run(['record 10 Dungeon', 'add 0 0 0', 'add 0 0 12', 'show']))
        if len(pts) != 2:
            bad.append('a climb of 12 yards is not a step of 10')
        # the walk is on the map it started on (S5 return, diablocraft-2vh9): points from another map are not kept, a stop there adds none
        pts = points_of(rec.run(['record 10 Dungeon', 'add 0 0 0', 'map 2', 'add 50 0 0', 'add 90 0 0', 'finish 95 0 0', 'map 1', 'add 20 0 0', 'show']))
        if pts != [(0, 0, 0), (20, 0, 0)]:
            bad.append(f'points of another map were kept: {pts}')
        got = rec.run(['record 10 Dungeon', 'onmap 1', 'onmap 2'])
        if [r[1] for r in got] != ['1', '0']:
            bad.append(f'a walk started on map 1 is on maps {got}')
        # one spot is no route; two are
        usable = [r for r in rec.run(['record 10 Dungeon', 'add 1 1 1', 'finish 1 1 1', 'show']) if r[0] == 'USABLE'][0][1]
        if usable != '0':
            bad.append('a walk that never moved is a route')
        usable = [r for r in rec.run(['record 10 Dungeon', 'add 1 1 1', 'finish 2 1 1', 'show']) if r[0] == 'USABLE'][0][1]
        if usable != '1':
            bad.append('a walk of two points is no route')
        # the anchor tie: straight line with height, the lowest id on a tie
        got = rec.run(['nearest 0 0 0 7:5:0:0 8:6:0:0 9:3:0:40'])[0]
        if got[2] != '7':
            bad.append(f'nearest of three anchors is {got}')
        got = rec.run(['nearest 0 0 0 8:2:0:0 3:0:2:0'])[0]
        if got[2] != '3':
            bad.append(f'a tie does not go to the lowest id: {got}')
        got = rec.run(['nearest 0 0 0 5:1:0:30 6:9:0:0'])[0]
        if got[2] != '6':
            bad.append(f'the tie ignores height (flat 1 yard on another floor 30 up beats 9 yards on this one): {got}')
        if rec.run(['nearest 0 0 0'])[0][1] != '-1':
            bad.append('a dungeon with no anchor does not say so')
        # the next path id
        base = int(re.search(r'RouteFirst = (\d+)', patrol_header).group(1))
        last = int(re.search(r'RouteLast = (\d+)', patrol_header).group(1))
        for highest, want in ((0, base), (base - 1, base), (base, base + 1), (base + 41, base + 42), (last - 1, last), (last, 0)):
            got = int(rec.run([f'next {highest}'])[0][1])
            if got != want:
                bad.append(f'next path id after {highest} is {got}, not {want}')
        # the SQL: numbered from 1, the route row last, a quote in the dungeon's name doubled
        out = rec.run(["record 4 the designer's Keep", 'add 1 2 3', 'add 5 2 3', 'sql 17 900000042'])
        sql = [r[1] for r in out if r[0] == 'SQL']
        if len(sql) != 3 or '(900000042, 1, 1.0000, 2.0000, 3.0000)' not in sql[0] or '(900000042, 2, 5.0000, 2.0000, 3.0000)' not in sql[1]:
            bad.append(f'the point rows are wrong: {sql}')
        elif "'the designer''s Keep', 900000042, 17, 1.0000, 2.0000, 3.0000, 2, 4.0, 'alex'" not in sql[2]:
            bad.append(f'the route row is wrong: {sql[2]}')
    return bad


def test_the_recording_rules():
    bad = recording_problems(read(RIFTS / 'dc_rift_patrol.h'), read(spawn.HEADER))
    assert not bad, bad[:8]


# --- the generator, and the chain from the recording to the sheet and back ----------------------------------------------------------------------

def scratch_database(mysql, defaults, tag):
    name = f'scratch_rift_patrol_{tag}_{os.getpid()}'

    def run(statement, database=None, stdin=None):
        argv = [mysql, '--defaults-file=' + defaults, '--no-login-paths', '--batch', '--raw', '--skip-column-names'] + ([database] if database else [])
        done = subprocess.run(argv + ([] if stdin else ['-e', statement]), input=stdin, text=True, capture_output=True)
        assert done.returncode == 0, done.stderr
        return [line.split('\t') for line in done.stdout.splitlines()]
    return name, run


def chain_problems(gen, patrol_header, spawn_header):
    """Record a walk, write it as the command does, export it, check it, render it, apply it: the same waypoint_data rows come back."""
    import generate_rift_survey as survey
    from generate_area_copies import Database
    bad = []
    mysql, defaults = fixture_db.mysql_and_defaults([])
    first, run = scratch_database(mysql, defaults, 'a')
    second = first + '_b'
    for name in (first, second):
        run('DROP DATABASE IF EXISTS %s; CREATE DATABASE %s' % (name, name))
    try:
        route_table = survey.TABLES['rift_routes.csv'][1]
        for name in (first, second):
            run('CREATE TABLE waypoint_data LIKE acore_world.waypoint_data', name)
        run('CREATE TABLE dc_rift_route (%s)' % route_table, first)
        with Recorder(patrol_header, spawn_header) as rec:
            out = rec.run(['record 4 Ragefire Chasm', 'add 1.5 2.25 3', 'add 7 2.25 3', 'add 7 9 3.5', 'finish 7 12 3.5', f'sql 22 {gen.ROUTE_FIRST + 7}'])
        statements = [r[1] for r in out if r[0] == 'SQL']
        # a stock path with its survey route row is in the same tables: the export must leave it where it is
        run("INSERT INTO waypoint_data (id, point, position_x, position_y, position_z) VALUES (486480, 1, 9, 9, 9), (486480, 2, 8, 8, 8)", first)
        run("INSERT INTO dc_rift_route VALUES ('Ragefire Chasm', 486480, 22, 9, 9, 9, 2, 1.4, 'survey')", first)
        run(None, first, ';\n'.join(statements) + ';\n')
        with tempfile.TemporaryDirectory(prefix='rift-patrol-sheet-', dir=SCRATCH) as folder:
            gen.export(Database(mysql, defaults, first), folder)
            points = gen.read_csv(Path(folder) / 'rift_route_points.csv')
        want = [(gen.ROUTE_FIRST + 7, i + 1) for i in range(4)]
        if [(int(r['path_id']), int(r['point'])) for r in points] != want or {r['dungeon'] for r in points} != {'Ragefire Chasm'}:
            bad.append(f'the export is not the recorded walk: {points}')
            return bad
        routes = [dict(dungeon='Ragefire Chasm', path_id=str(gen.ROUTE_FIRST + 7), anchor='22', source='alex')]
        problems = gen.check(points, routes)
        if problems:
            bad.append(f'the exported sheet fails its own rules: {problems}')
        sql = gen.render(points)
        run("INSERT INTO waypoint_data (id, point, position_x, position_y, position_z) VALUES (486480, 1, 1, 2, 3), (%d, 1, 0, 0, 0)" % (gen.ROUTE_FIRST + 99), second)
        run(None, second, sql)
        select = 'SELECT id, point, position_x, position_y, position_z FROM waypoint_data WHERE id >= %d ORDER BY id, point' % gen.ROUTE_FIRST
        if run(select, second) != run(select, first):
            bad.append(f'the migration does not write the recorded rows back: {run(select, second)} vs {run(select, first)}')
        if run('SELECT COUNT(*) FROM waypoint_data WHERE id = 486480', second) != [['1']]:
            bad.append('the migration deleted a stock path')
        if run('SELECT COUNT(*) FROM waypoint_data WHERE id = %d' % (gen.ROUTE_FIRST + 99), second) != [['0']]:
            bad.append('the migration left a row of the range that the sheet does not hold')
        # a path in his range with no route row has no dungeon: the export stops rather than guess one
        run("INSERT INTO waypoint_data (id, point, position_x, position_y, position_z) VALUES (%d, 1, 0, 0, 0)" % (gen.ROUTE_FIRST + 500), first)
        try:
            with tempfile.TemporaryDirectory(prefix='rift-patrol-sheet-', dir=SCRATCH) as folder:
                gen.export(Database(mysql, defaults, first), folder)
            bad.append('the export took a path that has no route row')
        except SystemExit:
            pass
    finally:
        for name in (first, second):
            run('DROP DATABASE IF EXISTS %s' % name)
    return bad


def sheet_problems(gen):
    bad = []
    stock = [dict(dungeon='Ragefire Chasm', path_id='486480', anchor='22', source='survey')]
    mine = [dict(dungeon='Ragefire Chasm', path_id=str(gen.ROUTE_FIRST + 1), anchor='3', source='alex')]

    def row(path, point, dungeon='Ragefire Chasm'):
        return dict(dungeon=dungeon, path_id=str(path), point=str(point), x='1.5', y='-2', z='3')
    good = [row(gen.ROUTE_FIRST + 1, 1), row(gen.ROUTE_FIRST + 1, 2)]
    if gen.check(good, stock + mine):
        bad.append(f'a good sheet fails: {gen.check(good, stock + mine)}')
    cases = {
        'a path below the range': ([row(486480, 1), row(486480, 2)], [dict(stock[0], source='alex')]),
        'a path above the range': ([row(gen.ROUTE_LAST + 1, 1), row(gen.ROUTE_LAST + 1, 2)], [dict(mine[0], path_id=str(gen.ROUTE_LAST + 1))]),
        'points not numbered from 1': ([row(gen.ROUTE_FIRST + 1, 2), row(gen.ROUTE_FIRST + 1, 3)], mine),
        'a route of one point': ([row(gen.ROUTE_FIRST + 1, 1)], mine),
        'points with no route row': (good, stock),
        'a route of the designer\'s with no points': ([], stock + mine),
        'a coordinate that is not a number': ([row(gen.ROUTE_FIRST + 1, 1), dict(row(gen.ROUTE_FIRST + 1, 2), x='abc')], mine),
        'points under another dungeon': (good, [dict(mine[0], dungeon='Deadmines')]),
    }
    for what, (points, routes) in cases.items():
        if not gen.check(points, routes):
            bad.append(f'the sheet check lets through: {what}')
    sql = gen.render(good)
    if f'DELETE FROM `waypoint_data` WHERE `id` BETWEEN {gen.ROUTE_FIRST} AND {gen.ROUTE_LAST};' not in sql:
        bad.append('the DELETE is not the range')
    if sql.count('DELETE FROM') != 1 or re.search(r'DELETE FROM `(?!waypoint_data)', sql):
        bad.append('the migration deletes more than his range')
    if f'({gen.ROUTE_FIRST + 1}, 1, 1.5, -2, 3)' not in sql or f'({gen.ROUTE_FIRST + 1}, 2, 1.5, -2, 3)' not in sql:
        bad.append('the rows are not in the migration')
    shuffled = gen.render(list(reversed(good)))
    if shuffled != sql:
        bad.append('the migration depends on the sheet\'s row order')
    return bad


def test_the_generator_and_the_chain():
    gen = load_generator()
    bad = sheet_problems(gen)
    patrol_header = read(RIFTS / 'dc_rift_patrol.h')
    bad += chain_problems(gen, patrol_header, read(spawn.HEADER))
    ids = tuple(int(n) for n in re.search(r'RouteFirst = (\d+), RouteLast = (\d+)', patrol_header).groups())
    if ids != (gen.ROUTE_FIRST, gen.ROUTE_LAST):
        bad.append(f'the id range differs between the header {ids} and the generator')
    assert not bad, bad[:8]


def test_the_committed_sheet_and_migration_are_the_generator_s_output():
    gen = load_generator()
    points = gen.read_csv(MODULE / 'data/d3/rift_route_points.csv')
    assert gen.check(points, csv_rows(MODULE / 'data/d3/rift_routes.csv')) == []
    assert not [r for r in csv_rows(MODULE / 'data/d3/rift_routes.csv') if r['source'] == 'alex' and not any(p['path_id'] == r['path_id'] for p in points)]
    assert all(int(r['path_id']) < gen.ROUTE_FIRST for r in csv_rows(MODULE / 'data/d3/rift_routes.csv') if r['source'] == 'survey')
    sql = gen.render(points)
    for place in (MODULE / 'data/sql/db-world/updates', MODULE / 'data/generated'):
        assert read(place / gen.NAME) == sql, place


# --- the glue, by source -----------------------------------------------------------------------------------------------------------------------

SPAWNER = read(RIFTS / 'dc_rift_spawner.cpp') if (RIFTS / 'dc_rift_spawner.cpp').exists() else ''
PATROL = read(RIFTS / 'dc_rift_patrol.cpp') if (RIFTS / 'dc_rift_patrol.cpp').exists() else ''


def squash(text):
    return re.sub(r'\s+', ' ', text)


def test_the_leader_walks_the_path_and_the_rest_follow():
    walk = squash(spawn.definition(SPAWNER, 'void Walk('))
    assert 'leader->GetMotionMaster()->MoveWaypoint(path, true);' in walk
    assert 'member->GetMotionMaster()->MoveFollow(leader, leader->GetExactDist2d(member), leader->GetRelativeAngle(member));' in walk
    assert 'MovePath(' not in SPAWNER      # the one-shot spline, not the repeating walk
    elite = squash(spawn.definition(SPAWNER, 'Creature* SummonElite('))
    assert 'if (placement.kind == Kind::Patrol) Walk(elite, pack, placement.route);' in elite
    loop = squash(SPAWNER)
    assert 'if (placement.kind == Kind::Patrol && leader) Walk(leader, members, placement.route);' in loop
    assert 'if (placement.kind != Kind::Solo) Link(members);' in loop           # a patrol fights as one
    assert 'placement.kind == Kind::Patrol ? PatrolStart(dungeon->second, placement, *anchor) : *anchor' in loop
    assert 'SummonElite(map, sheet->sheets, placement, where, tier)' in loop and 'SummonAt(map, monster.entry, where,' in loop
    assert 'placement.kind == Kind::Patrol && i == 0 ? Spot{} : placement.spots[i]' in loop   # the leader stands on the first point
    start = squash(spawn.definition(SPAWNER, 'Anchor PatrolStart('))
    assert 'start.x = route.x, start.y = route.y, start.z = route.z;' in start and 'path->Nodes[1]' in start


def test_the_routes_and_the_patrol_recipe_are_loaded_and_the_share_is_the_sheet_row():
    build = squash(SPAWNER)
    assert 'FROM dc_rift_route ORDER BY dungeon, path_id' in build
    assert 'sWaypointMgr->GetPath(' in build and 'path->Nodes.size() < 2' in build
    assert 'size != "large" && size != "patrol"' in build and ': Patrol,' in build
    knobs = spawn.definition(SPAWNER, 'Knobs ReadKnobs()')
    assert 'knobs.patrolPct = number("patrol_share_pct", 0);' in knobs
    assert 'RegisterPatrol();' in squash(spawn.definition(SPAWNER, 'void RegisterScripts()'))
    rows = {r['name']: r for r in csv_rows(MODULE / 'data/tunables/rifts.csv')}
    assert rows['patrol_share_pct']['value'] == '20' and rows['patrol_record_step_yards']['value'] == '4'   # the designer's values (tpji)
    assert rows['patrol_record_step_yards']['d3_value'] == ''


def test_the_recording_command_and_its_sampler():
    text = squash(PATROL)
    assert '{"start", HandleStart, SEC_ADMINISTRATOR, Console::No}' in text and '{"stop", HandleStop, SEC_ADMINISTRATOR, Console::No}' in text
    start = squash(spawn.definition(PATROL, 'static bool HandleStart('))
    assert 'DC::Tunables::Has("rifts", "patrol_record_step_yards")' in start and 'if (step <= 0) return Fail(' in start
    stop = squash(spawn.definition(PATROL, 'static bool HandleStop('))
    assert 'Recording walk(dungeon, step, player->GetMapId());' in start
    assert 'if (!found->second.OnMap(player->GetMapId())) return Fail(' in stop
    assert stop.index('OnMap(') < stop.index('recordings.erase(')   # refused before the recording is taken, so he can go back and stop
    for needed in ('walk.Finish(player->GetMapId(), ', 'if (!walk.Usable()) return Fail(', 'NearestAnchor(anchors, walk.Points().front())', 'NextPathId(highest)',
                   'Statements(walk.Dungeon(), path, anchors[near].id, walk.Points())', 'AsyncCommitTransaction(transaction).m_future.get()',
                   'sWaypointMgr->ReloadPath(path);', 'AddRoute(walk.Dungeon(), path, anchors[near].id, first.x, first.y, first.z);'):
        assert needed in stop, needed
    assert stop.index('AsyncCommitTransaction') < stop.index('ReloadPath') < stop.index('AddRoute(')   # live only after the rows are there
    assert 'PLAYERHOOK_ON_UPDATE' in text and 'found->second.Add(player->GetMapId(),' in text
    assert 'new PatrolSampler(); new PatrolCommand();' in text


# --- mutants ----------------------------------------------------------------------------------------------------------------------------------

PLANNER_MUTANTS = [
    ('the patrol share is ignored', 'rng.Real() * 100.0 < knobs.patrolPct && !routes.empty()', '!routes.empty()'),
    ('a patrol takes any anchor\'s route', 'if (route.anchor == picked[at].anchor->id)', 'if (true)'),
    ('a solo replaces a patrol', 'if (solo && !walks)', 'if (solo)'),
    ('a patrol is built from the small recipe', 'placement.size = walks ? Patrol : sizes', 'placement.size = walks ? Small : sizes'),
    ('a patrol cannot roll elite', 'if (plan.placements[i].kind != Kind::Solo)', 'if (plan.placements[i].kind == Kind::Cluster)'),
    ('the clusters leave the patrols out', 'plan.clusters += placement.kind != Kind::Solo;', 'plan.clusters += placement.kind == Kind::Cluster;'),
    ('the patrols are not counted', 'plan.patrols += placement.kind == Kind::Patrol;', ''),
    ('a patrol keeps no route', 'placement.route = routes[rng.Below(static_cast<unsigned>(routes.size()))]->path;', 'placement.route = 0;'),
    ('the first route always', 'routes[rng.Below(static_cast<unsigned>(routes.size()))]->path', 'routes[0]->path'),
]
RECORDING_MUTANTS = [
    ('every sample is kept', 'if (!_points.empty() && !(Distance(_points.back(), point) >= _step))\n                return false;', ''),
    ('the stop is lost', 'if (_points.empty() || Distance(_points.back(), point) > 0.0)\n                _points.push_back(point);', ''),
    ('one point is a route', 'return _points.size() >= 2;', 'return _points.size() >= 1;'),
    ('the tie forgets the height', 'double const d = Distance({anchors[i].x, anchors[i].y, anchors[i].z}, point);', 'double const d = Distance({anchors[i].x, anchors[i].y, point.z}, point);'),
    ('a tie goes to the last anchor', '(d == bestDistance && anchors[i].id < anchors[best].id)', '(d == bestDistance && anchors[i].id > anchors[best].id)'),
    ('the next id repeats', 'std::uint64_t(highestInUse) + 1', 'std::uint64_t(highestInUse)'),
    ('the range has no end', 'return next > RouteLast ? 0 :', 'return false ? 0 :'),
    ('a quote is not doubled', "if (c == '\\'' || c == '\\\\')\n                out += c;", ''),
    ('points are numbered from 0', 'path, i + 1, points[i].x', 'path, i, points[i].x'),
    ('a point of another map is kept', 'if (!OnMap(mapId))\n                return false;', ''),
    ('a stop on another map adds its point', 'if (!OnMap(mapId))\n                return;', ''),
    ('the designer\'s route is marked as the survey\'s', "%zu, %.1f, 'alex')", "%zu, %.1f, 'survey')"),
]
GENERATOR_MUTANTS = [
    ('the DELETE is wide', 'WHERE `id` BETWEEN {ROUTE_FIRST} AND {ROUTE_LAST};', 'WHERE `id` >= {ROUTE_FIRST};'),
    ('a stock id is allowed', 'if not ROUTE_FIRST <= int(r["path_id"]) <= ROUTE_LAST:', 'if False:'),
    ('a route of one point is allowed', 'if len(numbers) < 2:', 'if len(numbers) < 1:'),
    ('points without a route row are allowed', 'for key in sorted(set(paths) - mine):', 'for key in []:'),
    ('a route without points is allowed', 'for key in sorted(mine - set(paths)):', 'for key in []:'),
    ('the export forgets the range', 'WHERE w.id BETWEEN {ROUTE_FIRST} AND {ROUTE_LAST} ORDER BY', 'WHERE w.id > 0 ORDER BY'),
    ('the export takes an orphan', 'if dungeon == "NULL":', 'if False:'),
    ('the rows follow the sheet\'s order', 'rows = sorted(points, key=lambda r: (int(r["path_id"]), int(r["point"])))', 'rows = list(points)'),
]


def test_mutants_are_killed():
    assert set(KILLED_BY) == {what for what, _, _ in SOURCE_MUTANTS}, 'KILLED_BY and SOURCE_MUTANTS name different mutants'
    header, spawn_header = read(RIFTS / 'dc_rift_patrol.h'), read(spawn.HEADER)
    for what, old, new in PLANNER_MUTANTS:
        try:
            bad = patrol_problems(mutate(spawn_header, old, new))
        except AssertionError as error:
            bad = [str(error)]
        assert bad, 'mutant survived: ' + what
        print('PASS mutant killed:', what)
    for what, old, new in RECORDING_MUTANTS:
        try:
            bad = recording_problems(mutate(header, old, new), spawn_header)
            bad += chain_problems(load_generator(), mutate(header, old, new), spawn_header)
        except AssertionError as error:
            bad = [str(error)]
        assert bad, 'mutant survived: ' + what
        print('PASS mutant killed:', what)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    generator_text = read(MODULE / 'scripts/generate/rifts/generate_rift_patrols.py')
    for what, old, new in GENERATOR_MUTANTS:
        with tempfile.TemporaryDirectory(prefix='rift-patrol-gen-', dir=SCRATCH) as folder:
            copy = Path(folder) / 'generate_rift_patrols.py'
            copy.write_text(mutate(generator_text, old, new), encoding='utf-8')
            ran = subprocess.run([sys.executable, str(Path(__file__)), '--generator'], capture_output=True, text=True,
                                 env={**os.environ, 'DC_RIFT_PATROL_GENERATOR': str(copy)})
        assert ran.returncode != 0, 'generator mutant survived: ' + what
        print('PASS mutant killed:', what)
    for what, old, new in SOURCE_MUTANTS:
        ran = wiring_run(what, old, new, KILLED_BY[what])
        assert ran.returncode != 0, 'source mutant survived: ' + what
        print('PASS mutant killed:', what)


def wiring_run(what, old, new, tests):
    """The wiring tests `tests` run in a fresh process on a copy of src/rifts with the source mutant `what` applied."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rift-patrol-src-', dir=SCRATCH) as folder:
        copy = Path(folder) / 'rifts'
        copy.mkdir()
        for needed in ('dc_rift_spawn.h', 'dc_rift_patrol.h', 'dc_rift_spawner.cpp', 'dc_rift_patrol.cpp'):
            (copy / needed).write_text(read(RIFTS / needed), encoding='utf-8')
        name = 'dc_rift_patrol.cpp' if what in PATROL_CPP else 'dc_rift_spawner.cpp'
        (copy / name).write_text(mutate(read(RIFTS / name), old, new), encoding='utf-8')
        return subprocess.run([sys.executable, str(Path(__file__)), '--wiring', '--only=' + ','.join(tests)], capture_output=True, text=True,
                              env={**os.environ, 'DC_RIFT_PATROL_RIFTS': str(copy)})


PATROL_CPP = {'the command is open to every GM', 'a blank step records anyway', 'the route is live before it is saved', 'the sampler never samples',
              'a one-point walk is saved',
              'the walk is not tied to its map', 'a stop on another map saves the walk', 'the sampler gives no map'}
SOURCE_MUTANTS = [
    ('the leader walks the one-shot spline', 'leader->GetMotionMaster()->MoveWaypoint(path, true);', 'leader->GetMotionMaster()->MovePath(path);'),
    ('the leader walks the path once', 'leader->GetMotionMaster()->MoveWaypoint(path, true);', 'leader->GetMotionMaster()->MoveWaypoint(path, false);'),
    ('the followers do not follow', 'member->GetMotionMaster()->MoveFollow(', 'member->GetMotionMaster()->MoveRandom('),
    ('an elite patrol does not walk', 'if (placement.kind == Kind::Patrol)\n                Walk(elite, pack, placement.route);', ''),
    ('a plain patrol does not walk', 'if (placement.kind == Kind::Patrol && leader)\n                Walk(leader, members, placement.route);', ''),
    ('a patrol does not fight as one', 'if (placement.kind != Kind::Solo)\n                Link(members);', 'if (placement.kind == Kind::Cluster)\n                Link(members);'),
    ('a patrol stands on its anchor', 'placement.kind == Kind::Patrol ? PatrolStart(dungeon->second, placement, *anchor) : *anchor', '*anchor'),
    ('the share row is not read', 'knobs.patrolPct = number("patrol_share_pct", 0);', ''),
    ('a route with no path is walked', 'if (!path || path->Nodes.size() < 2)', 'if (false)'),
    ('the patrol recipe is not loaded', 'size != "large" && size != "patrol"', 'size != "large"'),
    ('the patrols are not registered', 'new SpawnerWorld();\n        RegisterPatrol();', 'new SpawnerWorld();'),
    ('the command is open to every GM', '{"stop", HandleStop, SEC_ADMINISTRATOR, Console::No}', '{"stop", HandleStop, SEC_GAMEMASTER, Console::No}'),
    ('a blank step records anyway', 'if (step <= 0)', 'if (false)'),
    ('the route is live before it is saved', 'sWaypointMgr->ReloadPath(path);', ''),
    ('the sampler never samples', 'found->second.Add(', 'found->second.Finish('),
    ('a one-point walk is saved', 'if (!walk.Usable())', 'if (false)'),
    ('the walk is not tied to its map', 'Recording walk(dungeon, step, player->GetMapId());', 'Recording walk(dungeon, step, 0);'),
    ('a stop on another map saves the walk', 'if (!found->second.OnMap(player->GetMapId()))', 'if (false)'),
    ('the sampler gives no map', 'found->second.Add(player->GetMapId(),', 'found->second.Add(0,'),
]
WIRING = ['test_the_leader_walks_the_path_and_the_rest_follow', 'test_the_routes_and_the_patrol_recipe_are_loaded_and_the_share_is_the_sheet_row',
          'test_the_recording_command_and_its_sampler']
# The wiring tests that can see each source mutant (measured: each was run alone against the mutant; the others pass on it).
# A mutant is judged by these only; a name here that is not in WIRING, or a mutant without a row, fails the run.
KILLED_BY = {
    'the leader walks the one-shot spline': ('test_the_leader_walks_the_path_and_the_rest_follow',),
    'the leader walks the path once': ('test_the_leader_walks_the_path_and_the_rest_follow',),
    'the followers do not follow': ('test_the_leader_walks_the_path_and_the_rest_follow',),
    'an elite patrol does not walk': ('test_the_leader_walks_the_path_and_the_rest_follow',),
    'a plain patrol does not walk': ('test_the_leader_walks_the_path_and_the_rest_follow',),
    'a patrol does not fight as one': ('test_the_leader_walks_the_path_and_the_rest_follow',),
    'a patrol stands on its anchor': ('test_the_leader_walks_the_path_and_the_rest_follow',),
    'the share row is not read': ('test_the_routes_and_the_patrol_recipe_are_loaded_and_the_share_is_the_sheet_row',),
    'a route with no path is walked': ('test_the_routes_and_the_patrol_recipe_are_loaded_and_the_share_is_the_sheet_row',),
    'the patrol recipe is not loaded': ('test_the_routes_and_the_patrol_recipe_are_loaded_and_the_share_is_the_sheet_row',),
    'the patrols are not registered': ('test_the_routes_and_the_patrol_recipe_are_loaded_and_the_share_is_the_sheet_row',),
    'the command is open to every GM': ('test_the_recording_command_and_its_sampler',),
    'a blank step records anyway': ('test_the_recording_command_and_its_sampler',),
    'the route is live before it is saved': ('test_the_recording_command_and_its_sampler',),
    'the sampler never samples': ('test_the_recording_command_and_its_sampler',),
    'a one-point walk is saved': ('test_the_recording_command_and_its_sampler',),
    'the walk is not tied to its map': ('test_the_recording_command_and_its_sampler',),
    'a stop on another map saves the walk': ('test_the_recording_command_and_its_sampler',),
    'the sampler gives no map': ('test_the_recording_command_and_its_sampler',),
}
GENERATOR_TESTS = ['test_the_generator_and_the_chain']


if __name__ == '__main__':
    only = WIRING if '--wiring' in sys.argv else GENERATOR_TESTS if '--generator' in sys.argv else None
    for arg in sys.argv:
        if arg.startswith('--only='):     # a source mutant is judged by the wiring tests that can see it
            only = [name for name in arg[len('--only='):].split(',') if name]
            assert only and set(only) <= set(WIRING), 'not wiring tests: ' + arg
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn) and (only is None or name in only):
            fn()
            print('PASS', name)

"""Monster spawning Part S4 (diablocraft-vytm): the touch-up commands, `.dc anchor` and `.dc area`.

What runs here: the production header (src/rifts/dc_rift_touchup.h) is compiled with tests/rift_touchup/harness.cpp. It is fed the survey's own
rows (data/d3/rift_*.csv) and its answers are checked three ways:
  * the geometry (nearest, around, the numbers a new anchor or area gets) against the sheet's coordinates;
  * every edit's SQL, run on a scratch schema of the fixture mysqld that holds rift_survey_0001.sql, against a model of the edit written
    here: the whole of the three tables after each step must equal the model's, so a row that should not move and moves is caught, an
    apostrophe in a dungeon name (Ahn'kahet) included;
  * the way home: generate_rift_survey.py --export on the edited tables writes the sheets, only the edited rows differ from the committed
    ones, the sheets then refuse a new --survey (a removal included), the migration they render loads back to the same tables, and the two
    queries the spawner reads the tables with return the edited rows.
What needs the worldserver (the player's position, the markers, the transaction, the reload) is held by source checks on dc_rift_touchup.cpp
below and by docs/test-diablocraft-vytm.md on dev.

DC_RIFT_TOUCHUP_RIFTS points the read at a copy of src/rifts (red-on-the-base run); DC_RIFT_TOUCHUP_HEADER at a mutated header."""
import csv
import math
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import generate_rift_survey as S0  # noqa: E402
import harness_env  # noqa: E402
from generate_area_copies import Database  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
RIFTS = Path(os.environ.get('DC_RIFT_TOUCHUP_RIFTS', MODULE / 'src/rifts'))
HEADER = Path(os.environ.get('DC_RIFT_TOUCHUP_HEADER', RIFTS / 'dc_rift_touchup.h'))
SCRATCH = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
D3 = MODULE / 'data/d3'
MIGRATION = MODULE / 'data/sql/db-world/updates/rift_survey_0003.sql'
TABLES = {'area': ('dc_rift_area', ('dungeon', 'area')), 'anchor': ('dc_rift_anchor', ('dungeon', 'anchor')),
          'route': ('dc_rift_route', ('dungeon', 'path_id'))}
AHN = "Ahn'kahet: The Old Kingdom"
RAGEFIRE = 'Ragefire Chasm'


def read(path):
    return Path(path).read_text(encoding='utf-8')


def csv_rows(path):
    with open(path, encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def dungeon_rows(path):
    """A survey sheet's rows without the open zones' (Part S6, rift_survey_0002.sql): this test's scratch schema holds the dungeons' migration."""
    zones = {r['name'] for r in csv_rows(D3 / 'rift_open_zones.csv')}
    return [r for r in csv_rows(path) if r['dungeon'] not in zones]


# --- the scratch schema ---------------------------------------------------------------------------------------------------------
class Scratch:
    """A schema of the fixture mysqld holding rift_survey_0001.sql, dropped on exit."""

    def __init__(self, migration=None):
        self.mysql, self.defaults = fixture_db.mysql_and_defaults([])
        self.name = 'scratch_rift_touchup_%d_%d' % (os.getpid(), random.randrange(10 ** 6))
        self.migration = migration or read(MIGRATION)

    def _client(self, *extra, stdin=None):
        argv = [self.mysql, '--defaults-file=' + self.defaults, '--no-login-paths', '--batch', '--raw', '--skip-column-names', *extra]
        done = subprocess.run(argv, input=stdin, text=True, capture_output=True)
        assert done.returncode == 0, done.stderr
        return done.stdout

    def __enter__(self):
        self._client(stdin='DROP DATABASE IF EXISTS %s; CREATE DATABASE %s' % (self.name, self.name))
        self._client(self.name, stdin=self.migration)
        self.db = Database(self.mysql, self.defaults, self.name)
        return self

    def __exit__(self, *exc):
        self._client(stdin='DROP DATABASE IF EXISTS %s' % self.name)

    def state(self):
        """{table: {key: row}} with the numbers rounded to the sheets' four places."""
        out = {}
        for kind, (table, key) in TABLES.items():
            out[kind] = {tuple(row[k] for k in key): norm(row) for row in self.db.rows(table)}
        return out


def norm(row):
    return {k: (round(float(v), 4) if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for k, v in row.items()}


def committed_state():
    out = {}
    for kind, sheet in (('area', 'rift_areas.csv'), ('anchor', 'rift_anchors.csv'), ('route', 'rift_routes.csv')):
        out[kind] = {}
        for row in dungeon_rows(D3 / sheet):
            typed = {k: (None if v == '' else v) for k, v in row.items()}
            for k, v in typed.items():
                if v is not None and k not in ('dungeon', 'tag', 'source'):
                    typed[k] = round(float(v), 4) if '.' in v else int(v)
            out[kind][tuple(typed[k] for k in TABLES[kind][1])] = typed
    return out


# --- the compiled harness -------------------------------------------------------------------------------------------------------
class Harness:
    def __init__(self, header_text):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self._folder = tempfile.TemporaryDirectory(prefix='rift-touchup-', dir=SCRATCH)
        self.folder = Path(self._folder.name)
        (self.folder / 'dc_rift_touchup.h').write_text(header_text, encoding='utf-8')
        done = subprocess.run(['c++', '-std=c++20', '-O1', '-UNDEBUG', '-Wall', '-Wextra', f'-I{self.folder}',
                               str(MODULE / 'tests/rift_touchup/harness.cpp'), '-o', str(self.folder / 'harness')], capture_output=True, text=True)
        assert done.returncode == 0, 'COMPILE ' + done.stderr[-1500:]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._folder.cleanup()

    def ask(self, lines):
        """The answers to the lines, as lists of cells (SQL lines first cell 'SQL')."""
        (self.folder / 'in.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        ran = harness_env.run([str(self.folder / 'harness'), str(self.folder / 'in.txt')], capture_output=True, text=True)
        assert ran.returncode == 0, ran.stderr[-1500:]
        return [line.split('\t') for line in ran.stdout.splitlines()]


def rows_of(state, dungeon):
    anchors = sorted((r for (d, _), r in state['anchor'].items() if d == dungeon), key=lambda r: r['anchor'])
    areas = sorted((r for (d, _), r in state['area'].items() if d == dungeon), key=lambda r: r['area'])
    return anchors, areas


def harness_rows(state, dungeon):
    anchors, areas = rows_of(state, dungeon)
    lines = [f"anchor\t{a['anchor']}\t{a['area']}\t{a['x']}\t{a['y']}\t{a['z']}\t{a['o']}" for a in anchors]
    lines += [f"area\t{a['area']}\t{a['tag']}\t{a['natives']}\t{0 if a['density_min'] is None else 1}\t{a['density_min'] or 0}\t{a['density_max'] or 0}\t{a['nospawn']}"
              for a in areas]
    return lines


# --- the model of each edit, written here and not read from the header --------------------------------------------------------
def copy_state(state):
    return {kind: {k: dict(v) for k, v in rows.items()} for kind, rows in state.items()}


def r4(value):
    return round(float(value), 4)


def touch(s, d, area):
    s['area'][(d, area)]['source'] = 'alex'


def m_add(state, d, new_id, area, fresh, x, y, z, o, walk):
    s = copy_state(state)
    if fresh:
        s['area'][(d, area)] = dict(dungeon=d, area=area, tag='S', natives=0, density_min=None, density_max=None, nospawn=0, source='alex')
    s['anchor'][(d, new_id)] = dict(dungeon=d, anchor=new_id, area=area, x=r4(x), y=r4(y), z=r4(z), o=r4(o), pack_size=1, native_guid=None,
                                    native_entry=None, entry_walk_yards=None if walk < 0 else r4(walk), source='alex')
    touch(s, d, area)
    return s


def m_move(state, d, anchor_id, x, y, z, o, walk):
    s = copy_state(state)
    row = s['anchor'][(d, anchor_id)]
    row.update(x=r4(x), y=r4(y), z=r4(z), o=r4(o), entry_walk_yards=None if walk < 0 else r4(walk), source='alex')
    touch(s, d, row['area'])
    return s


def m_remove(state, d, anchor_id):
    s = copy_state(state)
    gone = s['anchor'].pop((d, anchor_id))
    left = [r for (dd, _), r in s['anchor'].items() if dd == d]
    for (dd, _), route in s['route'].items():
        if dd == d and route['anchor'] == anchor_id:
            route['anchor'] = min(left, key=lambda a: ((a['x'] - route['start_x']) ** 2 + (a['y'] - route['start_y']) ** 2 +
                                                       (a['z'] - route['start_z']) ** 2, a['anchor']))['anchor']
            route['source'] = 'alex'
    touch(s, d, gone['area'])
    return s


def m_area(state, d, area, **changes):
    s = copy_state(state)
    s['area'][(d, area)].update(changes, source='alex')
    return s


def diff(want, got):
    """What differs between two states, short enough to read."""
    out = []
    for kind in want:
        for key in sorted(set(want[kind]) | set(got[kind]), key=str):
            if want[kind].get(key) != got[kind].get(key):
                out.append(f"{kind} {key}: want {want[kind].get(key)} got {got[kind].get(key)}")
    return out[:4]


# --- the checks ---------------------------------------------------------------------------------------------------------------
def geometry_problems(h):
    problems = []
    rng = random.Random(8)
    state = committed_state()
    for dungeon in (AHN, RAGEFIRE, 'The Stockade', 'Gundrak'):
        anchors, areas = rows_of(state, dungeon)
        base = harness_rows(state, dungeon)
        for _ in range(40):
            seed = rng.choice(anchors)
            x, y, z = seed['x'] + rng.uniform(-30, 30), seed['y'] + rng.uniform(-30, 30), seed['z'] + rng.uniform(-6, 6)
            yards = rng.uniform(5, 60)
            dist = lambda a: math.dist((a['x'], a['y'], a['z']), (x, y, z))
            order = sorted(anchors, key=lambda a: (dist(a), a['anchor']))
            out = h.ask(base + [f"nearest\t{x}\t{y}\t{z}", f"around\t{x}\t{y}\t{z}\t{yards}"])
            near = int(out[0][1])
            if anchors[near]['anchor'] != order[0]['anchor']:
                problems.append(f'nearest at {dungeon} {x:.1f} {y:.1f}: want {order[0]["anchor"]}, got {anchors[near]["anchor"]}')
            around = [int(c) for c in out[1][1:]]
            want = [a['anchor'] for a in order if dist(a) <= yards]
            if around != want:
                problems.append(f'around at {dungeon}: want {want[:6]}, got {around[:6]}')
        out = h.ask(base + ['next'])
        if [int(c) for c in out[0][1:]] != [max(a['anchor'] for a in anchors) + 1, max(a['area'] for a in areas) + 1]:
            problems.append(f'next ids at {dungeon}: {out[0]}')
    if h.ask(['nearest\t1\t2\t3'])[0][1] != '-1':
        problems.append('nearest of nothing is not -1')
    for word, want in (('S', 83), ('m', 77), ('L', 76), ('X', 0), ('SM', 0), ('', 0)):
        got = int(h.ask([f"tag\t{word}"])[0][1])
        if got != want:
            problems.append(f'tag {word!r}: want {want}, got {got}')
    for text, want in (("Ahn'kahet", "'Ahn\\'kahet'"), ('a\\b', "'a\\\\b'"), ('plain', "'plain'")):
        got = h.ask([f"quote\t{text}"])[0][1]
        if got != want:
            problems.append(f'quote {text!r}: want {want}, got {got}')
    return problems


def run_edits(h, scratch, problems):
    """Every command's SQL on the scratch schema, one step at a time; each step's whole state must equal the model's."""
    state = scratch.state()
    if state != committed_state():
        problems.append('the scratch schema does not hold the committed sheets')

    def step(label, dungeon, command, model):
        nonlocal state
        out = h.ask(harness_rows(state, dungeon) + [command])
        statements = [cells[1] for cells in out if cells[0] == 'SQL']
        assert statements, label
        scratch.db.query(';\n'.join(statements) + ';')
        got = scratch.state()
        want = model(state)
        wrong = diff(want, got)
        if wrong:
            problems.append(f'{label}: {wrong}')
        state = got

    anchors, areas = rows_of(state, AHN)
    first = anchors[0]
    here = (first['x'] + 3.0, first['y'] + 2.0, first['z'])
    out = h.ask(harness_rows(state, AHN) + [f"nearest\t{here[0]}\t{here[1]}\t{here[2]}", 'next'])
    near = anchors[int(out[0][1])]
    new_anchor, new_area = int(out[1][1]), int(out[1][2])
    walk = 57.25
    step('add into the area of the nearest anchor', AHN,
         f"add\t{AHN}\t{new_anchor}\t{near['area']}\t0\t{here[0]:.4f}\t{here[1]:.4f}\t{here[2]:.4f}\t1.5\t{walk}",
         lambda s: m_add(s, AHN, new_anchor, near['area'], False, here[0], here[1], here[2], 1.5, walk))
    step('add into a new area', AHN, f"add\t{AHN}\t{new_anchor + 1}\t{new_area}\t1\t{here[0] + 9:.4f}\t{here[1]:.4f}\t{here[2]:.4f}\t0.25\t-1",
         lambda s: m_add(s, AHN, new_anchor + 1, new_area, True, here[0] + 9, here[1], here[2], 0.25, -1))
    step('move an anchor', AHN, f"move\t{AHN}\t{first['anchor']}\t{first['area']}\t{here[0] + 20:.4f}\t{here[1] + 1:.4f}\t{here[2]:.4f}\t3.0\t12.5",
         lambda s: m_move(s, AHN, first['anchor'], here[0] + 20, here[1] + 1, here[2], 3.0, 12.5))
    step('move an anchor with no known walk', AHN, f"move\t{AHN}\t{near['anchor']}\t{near['area']}\t{here[0] + 5:.4f}\t{here[1] + 5:.4f}\t{here[2]:.4f}\t0\t-1",
         lambda s: m_move(s, AHN, near['anchor'], here[0] + 5, here[1] + 5, here[2], 0, -1))
    tied = sorted({r['anchor'] for (d, _), r in state['route'].items() if d == RAGEFIRE})
    assert tied, 'Ragefire Chasm has no tied route in the sheet'
    victim = state['anchor'][(RAGEFIRE, tied[0])]
    step('remove an anchor a patrol path is tied to', RAGEFIRE, f"remove\t{RAGEFIRE}\t{victim['anchor']}\t{victim['area']}",
         lambda s: m_remove(s, RAGEFIRE, victim['anchor']))
    gone = sorted((r for (d, _), r in state['anchor'].items() if d == 'Gundrak'), key=lambda r: r['anchor'])[-1]
    step('remove an anchor nothing is tied to', 'Gundrak', f"remove\tGundrak\t{gone['anchor']}\t{gone['area']}",
         lambda s: m_remove(s, 'Gundrak', gone['anchor']))
    target = areas[-1]['area']
    step('tag an area', AHN, f"settag\t{AHN}\t{target}\tL", lambda s: m_area(s, AHN, target, tag='L'))
    step('set an area\'s density', AHN, f"density\t{AHN}\t{target}\t0\t2\t3", lambda s: m_area(s, AHN, target, density_min=2, density_max=3))
    step('clear an area\'s density', AHN, f"density\t{AHN}\t{target}\t1\t0\t0", lambda s: m_area(s, AHN, target, density_min=None, density_max=None))
    step('no-spawn on', AHN, f"nospawn\t{AHN}\t{target}\t1", lambda s: m_area(s, AHN, target, nospawn=1))
    step('no-spawn off', AHN, f"nospawn\t{AHN}\t{target}\t0", lambda s: m_area(s, AHN, target, nospawn=0))
    return state


def edit_problems(header_text):
    problems = []
    with Harness(header_text) as h:
        problems += geometry_problems(h)
        with Scratch() as scratch:
            run_edits(h, scratch, problems)
    return problems


# --- the way home --------------------------------------------------------------------------------------------------------------
def test_the_geometry_matches_the_sheet():
    with Harness(read(HEADER)) as h:
        problems = geometry_problems(h)
    assert not problems, problems


def test_every_edit_changes_exactly_what_it_says():
    with Harness(read(HEADER)) as h, Scratch() as scratch:
        problems = []
        run_edits(h, scratch, problems)
    assert not problems, problems


def test_the_edits_come_home_through_export():
    with Harness(read(HEADER)) as h, Scratch() as scratch:
        problems = []
        edited = run_edits(h, scratch, problems)
        assert not problems, problems
        committed = committed_state()
        with tempfile.TemporaryDirectory(prefix='rift-touchup-export-', dir=SCRATCH) as folder:
            folder = Path(folder)
            for name in ('rift_native_filter.csv',):
                (folder / name).write_text(read(D3 / name), encoding='utf-8')
            S0.export(scratch.db, folder)
            # only the edited rows differ from the committed sheets, and the exported ones are the edited tables
            exported = {}
            for kind, sheet in (('area', 'rift_areas.csv'), ('anchor', 'rift_anchors.csv'), ('route', 'rift_routes.csv')):
                exported[kind] = {}
                for row in csv_rows(folder / sheet):
                    typed = {k: (None if v == '' else v) for k, v in row.items()}
                    for k, v in typed.items():
                        if v is not None and k not in ('dungeon', 'tag', 'source'):
                            typed[k] = round(float(v), 4) if '.' in v else int(v)
                    exported[kind][tuple(typed[k] for k in TABLES[kind][1])] = typed
                assert len(exported[kind]) == len(edited[kind]), kind
            assert not diff(edited, exported), diff(edited, exported)
            changed = {(kind, key) for kind in committed for key in set(committed[kind]) | set(exported[kind])
                       if committed[kind].get(key) != exported[kind].get(key)}
            kinds = {kind for kind, _ in changed}
            assert kinds == {'area', 'anchor', 'route'}, kinds
            assert all(key[0] in (AHN, RAGEFIRE, 'Gundrak') for _, key in changed), changed
            # a new --survey refuses the sheets
            sheets = S0.read_sheets(folder)
            assert S0.has_alex(sheets)
            # the migration they render loads back to the same tables
            with Scratch(S0.render(sheets)) as again:
                assert not diff(again.state(), scratch.state()), diff(again.state(), scratch.state())
        # the spawner's two queries read the edited tables
        found = re.findall(r'query\(\s*"(SELECT .*?)",\s*"(dc_\w+)"\)', re.sub(r'"\s*\n\s*"', '', read(RIFTS / 'dc_rift_spawner.cpp')), re.S)
        queries = {table: sql for sql, table in found if table in ('dc_rift_area', 'dc_rift_anchor')}
        assert set(queries) == {'dc_rift_area', 'dc_rift_anchor'}, queries
        for table, kind in (('dc_rift_area', 'area'), ('dc_rift_anchor', 'anchor')):
            got = scratch.db.query(queries[table])
            assert len(got) == len(edited[kind]), (table, len(got), len(edited[kind]))


def test_an_export_with_no_edit_is_the_committed_sheets_in_the_same_order():
    """--export of the untouched tables: the same rows in the same order, the numbers equal. (It writes an integer-valued DOUBLE as 0.0
    where the survey wrote 0, so 3 route cells and 30 exit-point cells differ in spelling only; this compares numbers.)"""
    numbers = lambda value: round(float(value), 4) if re.fullmatch(r'-?\d+(\.\d+)?', value) else value
    with Scratch() as scratch, tempfile.TemporaryDirectory(prefix='rift-touchup-export-', dir=SCRATCH) as folder:
        S0.export(scratch.db, Path(folder))
        for sheet in S0.EXPORTED:
            ours = [{k: numbers(v) for k, v in row.items()} for row in csv_rows(Path(folder) / sheet)]
            theirs = [{k: numbers(v) for k, v in row.items()} for row in dungeon_rows(D3 / sheet)]
            assert ours == theirs, (sheet, [(a, b) for a, b in zip(ours, theirs) if a != b][:2])


def test_a_removal_alone_stops_a_new_survey():
    with Harness(read(HEADER)) as h, Scratch() as scratch:
        state = scratch.state()
        victim = state['anchor'][(RAGEFIRE, 1)]
        out = h.ask(harness_rows(state, RAGEFIRE) + [f"remove\t{RAGEFIRE}\t{victim['anchor']}\t{victim['area']}"])
        scratch.db.query(';\n'.join(c[1] for c in out if c[0] == 'SQL') + ';')
        with tempfile.TemporaryDirectory(prefix='rift-touchup-export-', dir=SCRATCH) as folder:
            (Path(folder) / 'rift_native_filter.csv').write_text(read(D3 / 'rift_native_filter.csv'), encoding='utf-8')
            S0.export(scratch.db, Path(folder))
            sheets = S0.read_sheets(Path(folder))
            assert not any(r['anchor'] == '1' for r in sheets['rift_anchors.csv'] if r['dungeon'] == RAGEFIRE)
            assert S0.has_alex(sheets), 'a removed anchor leaves no row of the designer\'s, so --survey would bring it back'


# --- source checks on the wiring the harness cannot reach ----------------------------------------------------------------------------
TOUCH = read(RIFTS / 'dc_rift_touchup.cpp') if (RIFTS / 'dc_rift_touchup.cpp').exists() else ''
SPAWNER = read(RIFTS / 'dc_rift_spawner.cpp')
SPAWNER_H = read(RIFTS / 'dc_rift_spawner.h')


def definition(text, marker):
    start = text.index(marker)
    end, depth = text.index('{', start) + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def test_the_commands_are_registered_and_looking_is_not_editing():
    table = definition(TOUCH, 'GetCommands() const override')
    for name, level in (('show', 'SEC_GAMEMASTER'), ('hide', 'SEC_GAMEMASTER'), ('add', 'SEC_ADMINISTRATOR'), ('remove', 'SEC_ADMINISTRATOR'),
                        ('move', 'SEC_ADMINISTRATOR'), ('tag', 'SEC_ADMINISTRATOR'), ('density', 'SEC_ADMINISTRATOR'), ('nospawn', 'SEC_ADMINISTRATOR')):
        assert '{"%s", Handle%s, %s, Console::No}' % (name, name.capitalize(), level) in table, name
    assert '{"anchor", anchor}, {"area", area}' in table and '{"dc", dc}' in table
    assert 'RegisterTouchUp();' in definition(SPAWNER, 'void RegisterScripts()')
    assert 'void RegisterTouchUp();' in SPAWNER_H and 'bool Reload(std::string& message);' in SPAWNER_H
    assert re.search(r'bool Reload\(std::string& message\)\s*\{\s*return Load\(message\);', SPAWNER)


def test_every_edit_is_one_transaction_and_the_spawner_reads_it_again():
    commit = definition(TOUCH, 'bool Commit(')
    assert 'WorldDatabase.BeginTransaction()' in commit and 'AsyncCommitTransaction(transaction).m_future.get()' in commit
    assert 'DirectCommitTransaction' not in TOUCH
    assert commit.index('AsyncCommitTransaction') < commit.index('Reload(message)')
    assert 'if (!Reload(message))' in commit and 'Saved, but' in commit
    for builder in ('AddAnchor', 'MoveAnchor', 'RemoveAnchor', 'SetTag', 'SetDensity', 'SetNospawn'):
        assert re.search(r'return Commit\(handler,\s*%s\(' % builder, TOUCH), builder
    assert not re.search(r'\b(INSERT|UPDATE|DELETE)\b', TOUCH), 'the SQL of an edit is the header\'s'
    assert 'spot.anchors.size() < 2' in definition(TOUCH, 'static bool HandleRemove')


def test_the_dungeon_is_the_floors_own_or_the_maps():
    locate = definition(TOUCH, 'bool Locate(')
    assert 'live.View(map->GetInstanceId(), map->GetId(), view)' in locate
    assert 'inRift ? dungeon.dungeonId == view.dungeonId : dungeon.mapId == map->GetId()' in locate
    assert 'riftMutex' in locate and 'dataMutex' in locate


def test_the_markers_are_the_stock_gm_only_waypoint():
    assert 'constexpr uint32 MARKER_ENTRY = 1;' in TOUCH
    rows = fixture_db.mysql_and_defaults([])
    done = subprocess.run([rows[0], '--defaults-file=' + rows[1], '--no-login-paths', '--batch', '--skip-column-names', '-e',
                           'SELECT name, faction, flags_extra FROM acore_world.creature_template WHERE entry = 1'], capture_output=True, text=True)
    name, faction, extra = done.stdout.strip().split('\t')
    assert name == 'Waypoint (Only GM can see it)' and faction == '35'
    assert int(extra) & 128, 'IsRiftTrash must not count the marker: it is a trigger'      # dc_rift_ai.cpp IsRiftTrash: creature->IsTrigger()
    assert 'DespawnOrUnsummon' in definition(TOUCH, 'void TakeDownMarkers(')
    show = definition(TOUCH, 'static bool HandleShow')
    assert show.index('TakeDownMarkers(player)') < show.index('SummonCreature(MARKER_ENTRY')


# --- killed mutation runs ------------------------------------------------------------------------------------------------------
MUTANTS = [
    ('nearest picks the farthest', 'Distance(rows[i], x, y, z) < Distance(rows[best], x, y, z)', 'Distance(rows[i], x, y, z) > Distance(rows[best], x, y, z)'),
    ('around ignores the yards', 'Distance(a, x, y, z) > yards', 'false'),
    ('around is not nearest first', 'return da != db ? da < db : a.id < b.id;', 'return a.id < b.id;'),
    ('a new anchor reuses the last id', 'for (AnchorRow const& a : rows)\n            top = std::max(top, a.id);\n        return top + 1;',
     'for (AnchorRow const& a : rows)\n            top = std::max(top, a.id);\n        return top;'),
    ('a quote does not escape', "if (c == '\\'' || c == '\\\\')", 'if (false)'),
    ('an edit does not mark its area', 'return "UPDATE `dc_rift_area` SET `source` = \'alex\'" + Where(dungeon, "area", area);', 'return "SELECT 1";'),
    ('a removed anchor keeps its patrol paths', 'a.`anchor` <> " + std::to_string(id)', 'a.`anchor` = " + std::to_string(id)'),
    ('a move keeps the old walk', '", `entry_walk_yards` = " + (walk < 0 ? "NULL" : Number(walk))', '", `entry_walk_yards` = `entry_walk_yards`"'),
    ('a move is not the designer\'s', ", `source` = 'alex'\" + Where(dungeon, \"anchor\", id),\n                Touch(dungeon, area)};", "\" + Where(dungeon, \"anchor\", id),\n                Touch(dungeon, area)};"),
    ('clearing the density keeps the range', 'clear ? std::string("NULL") : std::to_string(low)', 'std::to_string(low)'),
    ('no-spawn is inverted', 'on ? "1" : "0"', 'on ? "0" : "1"'),
    ('a lower-case tag is refused', 'word[0] & ~0x20', 'word[0]'),
    ('a new area is tagged L', "'S', 0, NULL, NULL, 0, 'alex')", "'L', 0, NULL, NULL, 0, 'alex')"),
]


WIRING = ['test_the_commands_are_registered_and_looking_is_not_editing', 'test_every_edit_is_one_transaction_and_the_spawner_reads_it_again',
          'test_the_dungeon_is_the_floors_own_or_the_maps', 'test_the_markers_are_the_stock_gm_only_waypoint']
SOURCE_MUTANTS = [
    ('dc_rift_touchup.cpp', 'an edit needs only a GM', '{"add", HandleAdd, SEC_ADMINISTRATOR, Console::No}', '{"add", HandleAdd, SEC_GAMEMASTER, Console::No}'),
    ('dc_rift_touchup.cpp', 'the spawner is not told', 'if (!Reload(message))', 'if (false)'),
    ('dc_rift_touchup.cpp', 'the last anchor can go', 'if (spot.anchors.size() < 2)', 'if (false)'),
    ('dc_rift_touchup.cpp', 'the floor\'s dungeon is ignored', 'inRift ? dungeon.dungeonId == view.dungeonId : dungeon.mapId == map->GetId()',
     'dungeon.mapId == map->GetId()'),
    ('dc_rift_touchup.cpp', 'the edit is committed on the sync connection', 'WorldDatabase.AsyncCommitTransaction(transaction).m_future.get()',
     'WorldDatabase.DirectCommitTransaction(transaction)'),
    ('dc_rift_touchup.cpp', 'the marker is another creature', 'constexpr uint32 MARKER_ENTRY = 1;', 'constexpr uint32 MARKER_ENTRY = 2;'),
    ('dc_rift_spawner.cpp', 'the commands are never registered', 'RegisterTouchUp();', ''),
]


# The wiring tests that can see each source mutant (measured: each was run alone against the mutant; the others pass on it).
# A mutant is judged by these only; a name here that is not in WIRING, or a mutant without a row, fails the run.
KILLED_BY = {
    'an edit needs only a GM': ('test_the_commands_are_registered_and_looking_is_not_editing',),
    'the spawner is not told': ('test_every_edit_is_one_transaction_and_the_spawner_reads_it_again',),
    'the last anchor can go': ('test_every_edit_is_one_transaction_and_the_spawner_reads_it_again',),
    "the floor's dungeon is ignored": ('test_the_dungeon_is_the_floors_own_or_the_maps',),
    'the edit is committed on the sync connection': ('test_every_edit_is_one_transaction_and_the_spawner_reads_it_again',),
    'the marker is another creature': ('test_the_markers_are_the_stock_gm_only_waypoint',),
    'the commands are never registered': ('test_the_commands_are_registered_and_looking_is_not_editing',),
}


def mutate(text, old, new):
    pattern = re.compile(r'\s+'.join(re.escape(token) for token in old.split()))
    assert len(pattern.findall(text)) == 1, 'mutant target moved: ' + old
    return pattern.sub(lambda _: new, text)


def test_mutants_are_killed():
    assert set(KILLED_BY) == {what for _, what, _, _ in SOURCE_MUTANTS}, 'KILLED_BY and SOURCE_MUTANTS name different mutants'
    header = read(HEADER)
    seen = set()
    for what, old, new in MUTANTS:
        if what in seen:
            continue
        seen.add(what)
        try:
            bad = edit_problems(mutate(header, old, new))
        except (AssertionError, subprocess.CalledProcessError) as error:      # a mutant that no longer compiles or breaks the run is a red run as well
            bad = [str(error)]
        assert bad, 'mutant survived: ' + what
        print('PASS mutant killed:', what)
    for name, what, old, new in SOURCE_MUTANTS:
        ran = wiring_run(name, old, new, KILLED_BY[what])
        assert ran.returncode != 0, 'source mutant survived: ' + what
        print('PASS mutant killed:', what)


def wiring_run(name, old, new, tests):
    """The wiring tests `tests` run in a fresh process on a copy of src/rifts whose file `name` has `old` made `new`."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rift-touchup-src-', dir=SCRATCH) as folder:
        copy = Path(folder) / 'rifts'
        copy.mkdir()
        for needed in ('dc_rift_touchup.h', 'dc_rift_touchup.cpp', 'dc_rift_spawner.cpp', 'dc_rift_spawner.h'):
            (copy / needed).write_text(read(RIFTS / needed), encoding='utf-8')
        (copy / name).write_text(mutate(read(RIFTS / name), old, new), encoding='utf-8')
        return subprocess.run([sys.executable, str(Path(__file__)), '--wiring', '--only=' + ','.join(tests)], capture_output=True, text=True,
                              env={**os.environ, 'DC_RIFT_TOUCHUP_RIFTS': str(copy)})


if __name__ == '__main__':
    only = WIRING if '--wiring' in sys.argv else None
    for arg in sys.argv:
        if arg.startswith('--only='):     # a source mutant is judged by the wiring tests that can see it
            only = [name for name in arg[len('--only='):].split(',') if name]
            assert only and set(only) <= set(WIRING), 'not wiring tests: ' + arg
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn) and (only is None or name in only):
            fn()
            print('PASS', name)

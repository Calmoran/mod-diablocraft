"""Pylons and shrines Part P4 (diablocraft-0x640): where and when they stand in rifts. The part that needs no objects (P3's) or buffs (P1's).

What runs here:
  * the production decisions (src/rifts/dc_rift_pylon.h) are compiled with tests/rift_pylon/harness.cpp: the spots a floor may roll
    (the entry clearance), the Nephalem plan (a replayed seed gives the same kinds at the same spots; the caps, the minimums, the
    kinds by class and weight, Fortune at weight 0 never; the rate over many seeds), the Greater Rift's chance, its limits (no shrine,
    no kind twice, no fifth pylon, none once the Guardian is up) and its per-spot roll, the fates of a buff when the player leaves
    the run or a Greater Rift starts, the spot lookup, and the SQL of `.dc pylon spot`;
  * that SQL runs on a scratch schema of the fixture mysqld that holds rift_pylon_spot_0002.sql: a spot is added, moved and removed,
    every other row stays, and generate_rift_survey.py --export brings the table home into the sheet in the survey's order, the designer's
    rows marked `alex`, which a new --survey or --pylon-spots then refuses to write over;
  * the sheet against the survey's own sheets (one spot at the centre of each M and L area, on an anchor of the area), the migration
    against the sheet, and the tunable rows against the plan's numbers;
  * source checks on the wiring the harness cannot reach (the command table and its levels, the registration), each held by a mutant
    that must turn a check red.
What needs the worldserver (the markers, the commands in game) is held by docs/test-diablocraft-0x640.md on dev. The objects, the
roll's call sites, rule 3's exception and the leaving hooks wait for P3's objects and P1's buffs (no stand-ins); the next session wires
and tests them.

DC_RIFT_PYLON_RIFTS points the read at a copy of src/rifts (red-on-the-base run)."""
import csv
import importlib.util
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import rifts_text  # noqa: E402
import fixture_db  # noqa: E402
import generate_rift_survey as S0  # noqa: E402
import harness_env  # noqa: E402
from generate_area_copies import Database  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
RIFTS = Path(os.environ.get('DC_RIFT_PYLON_RIFTS', MODULE / 'src/rifts'))
SCRATCH = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
D3 = MODULE / 'data/d3'
UPDATES = MODULE / 'data/sql/db-world/updates'
HEADER = RIFTS / 'dc_rift_pylon.h'
AHN = "Ahn'kahet: The Old Kingdom"
MIGRATION = 'rift_pylon_spot_0002.sql'


def read(path):
    return Path(path).read_text(encoding='utf-8')


def csv_rows(path):
    with open(path, encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def definition(text, marker):
    start = text.index(marker)
    end, depth = text.index('{', start) + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


POOL = [row for row in csv_rows(D3 / 'rift_dungeons.csv') if row['recommended'].strip().lower() == 'yes']


# --- the compiled harness ------------------------------------------------------------------------------------------------------
def run_harness(header_text, commands=None):
    """Compiles tests/rift_pylon/harness.cpp around `header_text`; returns (returncode, stdout, stderr)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rift-pylon-', dir=SCRATCH) as folder:
        folder = Path(folder)
        (folder / 'dc_rift_pylon.h').write_text(header_text, encoding='utf-8')
        for name in ('dc_rift_spawn.h', 'dc_rift_touchup.h'):
            (folder / name).write_text(read(RIFTS / name), encoding='utf-8')
        argv = [str(folder / 'harness')]
        if commands is not None:
            (folder / 'commands.txt').write_text(commands, encoding='utf-8')
            argv.append(str(folder / 'commands.txt'))
        built = subprocess.run(['c++', '-std=c++20', '-O0', '-UNDEBUG', '-Wall', '-Wextra', f'-I{folder}',
                                str(MODULE / 'tests/rift_pylon/harness.cpp'), '-o', argv[0]], capture_output=True, text=True)
        if built.returncode:
            return 99, '', 'COMPILE ' + built.stderr[-1500:]
        ran = harness_env.run(argv, capture_output=True, text=True)
        return ran.returncode, ran.stdout, ran.stderr


def test_the_decisions():
    rc, out, err = run_harness(read(HEADER))
    assert rc == 0 and 'rift pylon harness: ok' in out, (rc, err[-1500:])


# --- the SQL of `.dc pylon spot`, on a scratch schema -----------------------------------------------------------------------------
class Scratch:
    """A schema of the fixture mysqld holding rift_pylon_spot_0001.sql, dropped on exit."""

    def __init__(self):
        self.mysql, self.defaults = fixture_db.mysql_and_defaults([])
        self.name = 'scratch_rift_pylon_%d_%d' % (os.getpid(), random.randrange(10 ** 6))

    def client(self, *extra, stdin=None):
        argv = [self.mysql, '--defaults-file=' + self.defaults, '--no-login-paths', '--batch', '--raw', '--skip-column-names', *extra]
        done = subprocess.run(argv, input=stdin, text=True, capture_output=True)
        assert done.returncode == 0, done.stderr
        return done.stdout

    def __enter__(self):
        self.client(stdin='DROP DATABASE IF EXISTS %s; CREATE DATABASE %s' % (self.name, self.name))
        self.client(self.name, stdin=read(UPDATES / MIGRATION))
        self.db = Database(self.mysql, self.defaults, self.name)
        return self

    def __exit__(self, *exc):
        self.client(stdin='DROP DATABASE IF EXISTS %s' % self.name)

    def run(self, sql):
        self.client(self.name, stdin=sql)

    def spots(self, dungeon):
        return {row['spot']: (row['source'], round(row['x'], 4), round(row['y'], 4), round(row['z'], 4), round(row['o'], 4), row['entry_walk_yards'], row['area'])
                for row in self.db.rows('dc_rift_pylon_spot') if row['dungeon'] == dungeon}

    def everything(self):
        return sorted((r['dungeon'], r['spot'], r['source'], r['x'], r['y'], r['z']) for r in self.db.rows('dc_rift_pylon_spot'))


def edit_commands():
    return ("add\t%s\t100 1.5 2.5 3.5 0.25\n" % AHN) + "move\t%s\t2 -10 -20.5 30.25 1.5\n" % AHN + "remove\t%s\t3\n" % AHN + \
        "add\tRagefire Chasm\t99 7 8 9 1\n"


def test_adding_moving_and_removing_a_spot(header_text=None):
    rc, out, err = run_harness(header_text or read(HEADER), edit_commands())
    assert rc == 0, err
    statements = [line for line in out.splitlines() if line.startswith(('INSERT', 'UPDATE', 'DELETE'))]
    assert len(statements) == 4, statements
    with Scratch() as scratch:
        before = scratch.everything()
        ahn = scratch.spots(AHN)
        assert {1, 2, 3} <= set(ahn) and 100 not in ahn and all(v[0] == 'survey' for v in ahn.values())
        scratch.run(statements[0])                            # added: the designer's, no walk, no area
        added = scratch.spots(AHN)[100]
        assert added == ('alex', 1.5, 2.5, 3.5, 0.25, None, 0)
        scratch.run(statements[1])                            # moved: only spot 2, now the designer's, its walk unknown
        moved = scratch.spots(AHN)
        assert moved[2][:5] == ('alex', -10.0, -20.5, 30.25, 1.5) and moved[2][5] is None and moved[2][6] == ahn[2][6]
        assert moved[1] == ahn[1] and moved[3] == ahn[3] and moved[100] == added
        scratch.run(statements[2])                            # removed: only spot 3
        removed = scratch.spots(AHN)
        assert 3 not in removed and set(removed) == (set(ahn) | {100}) - {3} and removed[1] == ahn[1] and removed[2] == moved[2]
        scratch.run(statements[3])                            # another dungeon's add stays out of this one's rows
        assert scratch.spots(AHN) == removed and scratch.spots('Ragefire Chasm')[99][:5] == ('alex', 7.0, 8.0, 9.0, 1.0)
        after = scratch.everything()
        assert len(after) == len(before) + 1                  # +2 added, -1 removed; every other row of every dungeon is as it was
        others = [r for r in after if r[0] != AHN and (r[0], r[1]) != ('Ragefire Chasm', 99)]   # spot 99 is also a real spot number in the big open zones
        assert others == [r for r in before if r[0] != AHN]
        scratch.run(statements[2])                            # removing a spot that is gone is nothing
        assert scratch.spots(AHN) == removed


def test_an_apostrophe_in_a_dungeon_name_does_not_end_the_string():
    lines = "add\t%s\t100 1 2 3 0\n" % AHN
    rc, out, err = run_harness(read(HEADER), lines)
    assert rc == 0 and "Ahn\\'kahet" in out


# --- the sheet, the migration and --export -----------------------------------------------------------------------------------------
def sheets():
    return {name: csv_rows(D3 / name) for name in S0.SHEETS}


def test_the_sheet_is_one_spot_at_the_centre_of_each_m_and_l_area():
    s = sheets()
    spots = csv_rows(D3 / S0.PYLON_SHEET)
    assert list(spots[0]) == list(S0.PYLON_COLUMNS)
    areas = {(a['dungeon'], a['area']): a for a in s['rift_areas.csv']}
    wanted = [k for k, a in areas.items() if a['tag'] in ('M', 'L') and any((x['dungeon'], x['area']) == k for x in s['rift_anchors.csv'])]
    assert len(spots) == len(wanted) > 400
    assert sorted((r['dungeon'], r['area']) for r in spots) == sorted(wanted)
    assert all(areas[(r['dungeon'], r['area'])]['tag'] in ('M', 'L') for r in spots)      # never an S area's centre
    by_dungeon = {}
    for r in spots:
        by_dungeon.setdefault(r['dungeon'], []).append(int(r['spot']))
    assert all(ids == list(range(1, len(ids) + 1)) for ids in by_dungeon.values())       # 1.. per dungeon, in area order
    dungeons = {r['dungeon'] for r in s['rift_areas.csv']}
    assert set(by_dungeon) <= dungeons and len(by_dungeon) >= 30
    anchors = {}
    for a in s['rift_anchors.csv']:
        anchors.setdefault((a['dungeon'], a['area']), []).append(a)
    for r in spots:                                                                      # on the ground: an anchor of its area, the one nearest the centre
        members = anchors[(r['dungeon'], r['area'])]
        mean = [sum(float(m[k]) for m in members) / len(members) for k in 'xyz']
        dist = lambda m: sum((float(m[k]) - c) ** 2 for k, c in zip('xyz', mean))
        nearest = min(dist(m) for m in members)
        mine = [m for m in members if (m['x'], m['y'], m['z'], m['o'], m['entry_walk_yards']) == (r['x'], r['y'], r['z'], r['o'], r['entry_walk_yards'])]
        assert mine and dist(mine[0]) == nearest, r
        assert r['source'] == 'survey'
    assert S0.pylon_spots(s) == [dict(r, spot=int(r['spot'])) for r in spots] or [dict(r) for r in S0.pylon_spots(s)] == [
        {k: (int(v) if k == 'spot' else v) for k, v in r.items()} for r in spots]


def test_the_migration_is_the_sheet():
    spots = csv_rows(D3 / S0.PYLON_SHEET)
    sql = read(UPDATES / MIGRATION)
    assert sql == read(MODULE / 'data/generated' / MIGRATION) == S0.render_pylon_spots(spots)
    assert 'CREATE TABLE IF NOT EXISTS `dc_rift_pylon_spot`' in sql and 'PRIMARY KEY (`dungeon`, `spot`)' in sql
    with Scratch() as scratch:
        loaded = scratch.db.rows('dc_rift_pylon_spot')
        assert len(loaded) == len(spots) and all(r['source'] == 'survey' for r in loaded)
        by = {(r['dungeon'], str(r['spot'])): r for r in loaded}
        for r in spots:
            row = by[(r['dungeon'], r['spot'])]
            assert (round(row['x'], 4), round(row['y'], 4), round(row['z'], 4)) == (round(float(r['x']), 4), round(float(r['y']), 4), round(float(r['z']), 4))
        scratch.run(sql)                                                                 # re-applied: replaced, never doubled
        assert len(scratch.db.rows('dc_rift_pylon_spot')) == len(spots)
    # the survey's own migration is not touched by this table (an anchor edit of the designer's it would re-apply over stays safe)
    assert 'dc_rift_pylon_spot' not in read(UPDATES / 'rift_survey_0001.sql') and 'rift_pylon_spots.csv' not in S0.SHEETS


def test_alexs_edits_come_home_through_export():
    spots = csv_rows(D3 / S0.PYLON_SHEET)
    rc, out, err = run_harness(read(HEADER), edit_commands())
    assert rc == 0, err
    statements = [line for line in out.splitlines() if line.startswith(('INSERT', 'UPDATE', 'DELETE'))]
    with Scratch() as scratch, tempfile.TemporaryDirectory(prefix='rift-pylon-export-', dir=SCRATCH) as folder:
        folder = Path(folder)
        for sheet in list(S0.SHEETS) + [S0.PYLON_SHEET]:
            (folder / sheet).write_bytes((D3 / sheet).read_bytes())
        S0.export_pylon_spots(scratch.db, folder)                                        # untouched: the committed sheet, byte for byte
        assert (folder / S0.PYLON_SHEET).read_bytes() == (D3 / S0.PYLON_SHEET).read_bytes()
        for sql in statements:
            scratch.run(sql)
        for survey in ('rift_survey_0001.sql', 'rift_survey_0002.sql'):                   # the tables the whole export also reads
            scratch.run(read(UPDATES / survey))
        S0.export(scratch.db, folder)                                                    # the whole export, as the designer runs it
        exported = csv_rows(folder / S0.PYLON_SHEET)
        same = lambda rows: [(r['dungeon'], r['spot']) for r in rows]
        keep = [r for r in spots if not (r['dungeon'] == AHN and r['spot'] == '3')]
        assert same([r for r in exported if (r['dungeon'], r['spot']) not in {(AHN, '100'), ('Ragefire Chasm', '99')}]) == same(keep)
        byid = {(r['dungeon'], r['spot']): r for r in exported}
        assert (AHN, '3') not in byid                                                    # removed
        assert byid[(AHN, '100')]['source'] == 'alex' and byid[(AHN, '100')]['x'] == '1.5' and byid[(AHN, '100')]['entry_walk_yards'] == ''
        assert byid[(AHN, '2')]['source'] == 'alex' and byid[(AHN, '2')]['y'] == '-20.5' and byid[('Ragefire Chasm', '99')]['source'] == 'alex'
        committed = {(r['dungeon'], r['spot']): r for r in spots}
        for key, row in byid.items():                                                    # every other row is the survey's, as committed
            if key not in {(AHN, '100'), (AHN, '2'), ('Ragefire Chasm', '99')}:
                assert {k: (str(round(float(v), 4)) if k in 'xyzo' and v else v) for k, v in row.items()} == \
                       {k: (str(round(float(v), 4)) if k in 'xyzo' and v else v) for k, v in committed[key].items()}, key
        assert len(byid) == len(spots) - 1 + 2                                           # one removed, two added
        names = [d['name'] for d in S0.read_csv(D3 / 'rift_dungeons.csv')] + [z['name'] for z in S0.read_csv(D3 / S0.OPEN_ZONES)]
        order = [(names.index(r['dungeon']), int(r['spot'])) for r in exported]
        assert order == sorted(order)                                                    # the survey's order: dungeons, then zones, in sheet order
        # the sheet he comes home as refuses a new --pylon-spots and --survey, and renders a migration that loads back
        assert any(r['source'] == 'alex' for r in S0.read_pylon_spots(folder))
        with Scratch() as again:
            again.run(S0.render_pylon_spots(S0.read_pylon_spots(folder)))
            assert again.spots(AHN)[100][0] == 'alex' and 3 not in again.spots(AHN)
        # a database without the table leaves the sheet alone
        scratch.run('DROP TABLE dc_rift_pylon_spot')
        before = (folder / S0.PYLON_SHEET).read_bytes()
        S0.export_pylon_spots(scratch.db, folder)
        assert (folder / S0.PYLON_SHEET).read_bytes() == before


def test_a_sheet_with_rows_of_alexs_is_not_written_over():
    """--pylon-spots and --survey stop at rows of his; --force is the only way past (as for the survey's other sheets)."""
    source = read(MODULE / 'scripts/generate/rifts/generate_rift_survey.py')
    main = definition(source, 'def main():')
    assert re.search(r'if args\.pylon_spots:\s+if any\(r\["source"\] == "alex" for r in read_pylon_spots\(\)\) and not args\.force:\s+parser\.error', main)
    assert 'or any(r["source"] == "alex" for r in read_pylon_spots())) and not args.force' in main


# --- the tunable rows ---------------------------------------------------------------------------------------------------------------
ROWS = {      # name: (d3_value, value, unit)
    'pylon_nr_pylon_chance_pct': ('', '5', 'percent'), 'pylon_nr_shrine_chance_pct': ('', '13', 'percent'),
    'pylon_nr_pylons_min': ('', '0', 'count'), 'pylon_nr_pylons_max': ('', '2', 'count'),
    'pylon_nr_shrines_min': ('', '0', 'count'), 'pylon_nr_shrines_max': ('', '5', 'count'),
    'shrine_fortune_weight': ('', '', 'multiplier'),
    'pylon_gr_base_chance_pct': ('1', '', 'percent'), 'pylon_gr_full_chance_progress_pct': ('50', '', 'percent'),
    'pylon_gr_check_yards': ('75', '', 'yards'), 'pylon_gr_max_per_run': ('4', '', 'count'),
    'pylon_gr_check_ms': ('', '1000', 'milliseconds'),
}


def test_every_number_is_a_tunable_row():
    """The plan's starts (6.5) and D3's published figures (D10), as rows: D3's in d3_value, ours in value, Fortune's blank for the designer."""
    rows = {r['name']: r for r in csv_rows(MODULE / 'data/tunables/rifts.csv')}
    for name, (d3, value, unit) in ROWS.items():
        row = rows[name]
        assert (row['d3_value'], row['value'], row['unit']) == (d3, value, unit), name
        assert 'diablocraft-0x640' in row['notes'] or 'Pylons and shrines P4' in row['notes'], name
    for path in (MODULE / 'data/generated/tunables_0012.sql', UPDATES / 'tunables_0012.sql'):
        text = read(path)
        for name in ROWS:
            assert "'rifts', '%s'," % name in text, (path.name, name)
        assert re.search(r"\('rifts', 'shrine_fortune_weight', NULL, NULL,", text)       # blank: no Fortune Shrine until the designer sets it
        assert re.search(r"\('rifts', 'pylon_gr_full_chance_progress_pct', 50\.0, NULL,", text)


# --- the wiring the harness cannot reach --------------------------------------------------------------------------------------------
def texts():
    # 'dc_rifts.cpp' stands for the rift files joined (split_sources), so a mutant finds its line in whichever holds it
    return {name: rifts_text(RIFTS.parent) if name == 'dc_rifts.cpp' else read(RIFTS / name) for name in ('dc_rift_pylon.cpp', 'dc_rift_exit.cpp', 'dc_rifts.cpp', 'dc_rifts_internal.h',
                                                   'dc_gr_rules.cpp', 'dc_rift_spawner.cpp')}


def check_wiring(t):
    pylon, exit_, rifts, internal = (t[k] for k in ('dc_rift_pylon.cpp', 'dc_rift_exit.cpp', 'dc_rifts.cpp', 'dc_rifts_internal.h'))
    # the commands: looking is a GM's, placing and clearing an administrator's, under .dc pylon spot
    table = definition(pylon, 'GetCommands() const override')
    for name, level in (('here', 'SEC_ADMINISTRATOR'), ('show', 'SEC_GAMEMASTER'), ('clear', 'SEC_ADMINISTRATOR')):
        assert '{"%s", Handle%s, %s, Console::No}' % (name, name.capitalize(), level) in table, name
    assert '{"spot", spot}' in table and '{"pylon", pylon}' in table and '{"dc", dc}' in table
    # here: the spot near him moves, else one is added; clear removes the near one and says so when none is
    here = definition(pylon, 'static bool HandleHere(ChatHandler* handler)')
    assert here.index('NearestSpot(rows,') < here.index('MoveSql(dungeon.name, rows[near].id, at)') < here.index('AddSql(dungeon.name, id, at)')
    assert 'NextSpotId(rows)' in here and 'Exit::DungeonOf(player, dungeon)' in here
    clear = definition(pylon, 'static bool HandleClear(ChatHandler* handler)')
    assert 'NearestSpot(rows,' in clear and 'RemoveSql(dungeon.name, rows[near].id)' in clear and 'near < 0' in clear
    show = definition(pylon, 'static bool HandleShow(ChatHandler* handler, Optional<float> yards)')
    assert 'Within(row,' in show and 'SummonCreature(MARKER_ENTRY' in show and 'MARKER_MS' in show
    # the SQL is the header's, never written here
    assert not re.search(r'\b(INSERT|UPDATE|DELETE|REPLACE)\b', pylon.split('namespace DC::Rifts::Pylons')[1].split('LoadSpots')[1]), 'the SQL of an edit is the header\'s'
    load = definition(pylon, 'std::vector<Spot> LoadSpots(std::string const& dungeon)')
    assert 'FROM `dc_rift_pylon_spot` WHERE `dungeon` = {}' in load and 'ORDER BY `spot`' in load and 'row.alex = f[7].Get<std::string>() == "alex"' in load
    # the dungeon a GM means is the exit command's own lookup, shared
    assert 'bool DungeonOf(Player* player, Dungeon& out)' in exit_ and 'return DungeonHere(player, out);' in exit_
    assert 'bool DungeonOf(Player* player, Dungeon& out);' in internal and 'namespace Pylons' in internal
    assert 'Pylons::RegisterScripts();' in definition(rifts, 'void RegisterScripts()')
    assert 'new PylonSpotCommand();' in definition(pylon, 'void RegisterScripts()')
    check_placement(t)


def check_placement(t):
    """The glue of the placement (pylons.md 6.5, 6.11, 7 P4; the designer's spacing and 1000 ms check, decisions 1551ce0e)."""
    pylon, rifts, rules, spawner = (t[k] for k in ('dc_rift_pylon.cpp', 'dc_rifts.cpp', 'dc_gr_rules.cpp', 'dc_rift_spawner.cpp'))
    assert 'new LeaveRules();' in definition(pylon, 'void RegisterScripts()')
    # the map update calls it on a live floor, the map's end forgets the run's count
    update = definition(rifts, 'void OnMapUpdate(Map* map, uint32 diff) override')
    assert 'if (rift)\n                Pylons::Update(map, diff);' in update
    assert 'Pylons::FloorGone(floor.runId, lastFloor);' in rifts
    gone = definition(pylon, 'void FloorGone(std::uint64_t runId, bool runEnds)')
    assert 'if (!runEnds)\n            return;' in gone and 'runsHad.erase(runId);' in gone
    # the run's seed is the spawner's, the Nephalem plan rolls its own stream of it, from the floor's usable spots
    assert 'return found == runs.end() ? 0 : found->second.seed;' in definition(spawner, 'std::uint64_t RunSeed(std::uint64_t runId)')
    opened = definition(pylon, 'void Open(Map* map, FloorPylons& state, Rift const& view)')
    assert 'state.seed = Spawner::RunSeed(view.id);' in opened and 'state.greater = view.mode == "gr"' in opened
    assert 'Usable(LoadSpots(dungeonName), clear)' in opened and '"entry_clear_yards"' in opened
    assert 'Spawn::Rng rng = StreamOf(state.seed, state.floor);' in opened
    assert 'PlanNephalem(spots, PlacementKinds(), knobs, rng)' in opened and 'Stand(map, state, spots[placed.spot], placed.kind);' in opened
    assert '"pylon_min_spacing_yd"},\n                       k, "Nephalem")' in opened and 'static_cast<unsigned>(k[5]), k[6]}' in opened
    assert 'if (state.greater)\n            {\n                state.waiting = spots;\n                return;\n            }' in opened
    # Fortune at its own weight, the rest even; index i is the buff sheet's kind i
    kinds = definition(pylon, 'std::vector<Kind> PlacementKinds()')
    assert 'kind == Buffs::Kind::Fortune' in kinds and '"shrine_fortune_weight"' in kinds and 'Buffs::IsPylon(kind)' in kinds
    stand = definition(pylon, 'void Stand(Map* map, FloorPylons& state, Spot const& spot, std::size_t kind)')
    assert 'Buffs::Spawn(map, static_cast<Buffs::Kind>(kind), Position(spot.x, spot.y, spot.z, spot.o))' in stand
    assert 'state.placed.push_back(spot);' in stand
    # the Greater Rift: every pylon_gr_check_ms, a spot a player is near rolls once, with the run's count and the bar's share
    tick = definition(pylon, 'void Update(Map* map, uint32 diff)')
    assert '"pylon_gr_check_ms"' in tick and 'state->sinceCheck < every' in tick and 'state->sinceCheck = 0;' in tick
    assert 'if (!state->greater || state->waiting.empty())' in tick
    near = definition(pylon, 'void Approach(Map* map, FloorPylons& state)')
    assert '"pylon_min_spacing_yd"},\n                       k, "Greater Rift")' in near
    assert 'double const share = view.requiredUnits ? 100.0 * view.progress / view.requiredUnits : 0;' in near
    assert 'MayRoll(view.state, view.guardianInstance, had, knobs) != NoRoll::None' in near
    assert 'knobs.checkYards' in near and 'RunHad& had = runsHad[state.run];' in near
    # the header's checkYards default is 0 (h3vof), so the distance must come from the sheet, third in the list
    assert '{"pylon_gr_base_chance_pct", "pylon_gr_full_chance_progress_pct", "pylon_gr_check_yards",' in near
    assert 'GreaterKnobs const knobs{k[0], k[1], k[2], static_cast<unsigned>(k[3]), k[4]};' in near
    assert 'ApproachGreater(state.seed, state.floor, *spot, share, knobs, kinds, state.placed, had)' in near
    assert 'spot = state.waiting.erase(spot); // a spot rolls once' in near
    # 6.11 on arrival
    leave = definition(pylon, 'void OnPlayerMapChanged(Player* player) override')
    assert 'Leaving(onFloor, onFloor && view.mode == "gr")' in leave and 'onFloor = live.View(map->GetInstanceId(), map->GetId(), view);' in leave
    assert 'FateOf(Buffs::IsPylon(kind), kind == Buffs::Kind::Speed, *when) == Fate::Ends' in leave
    assert 'player->RemoveAurasDueToSpell(record);' in leave
    # Greater Rift rule 3: a pylon stays usable (a standing one after the Guardian too); a shrine does not
    assert 'DC::Combat::Pylons::IsPylonObject(go->GetEntry()) ||' in definition(rules, 'bool CanGameObjectGossipHello(Player* player, GameObject* go) override')


def test_the_wiring():
    check_wiring(texts())


# --- killed mutation runs ---------------------------------------------------------------------------------------------------------------
HEADER_MUTANTS = [
    ('an unknown walk is cleared at the door', 'entryClear > 0 && s.walk >= 0 && s.walk < entryClear', 'entryClear > 0 && s.walk < entryClear'),
    ('a walk equal to the clearance is cleared', 's.walk < entryClear', 's.walk <= entryClear'),
    ('usable spots lose their id order', 'std::sort(spots.begin(), spots.end(), [](Spot const& a, Spot const& b) { return a.id < b.id; });', ''),
    ('the plan shares the spawner\'s stream', 'runSeed ^ STREAM_SALT, floor', 'runSeed, floor'),
    ('a shrine rolls only in its own band', 'roll < knobs.pylonPct + knobs.shrinePct ? Shrine', 'roll < knobs.shrinePct ? Shrine'),
    ('the pylon cap is one too many', 'for (std::size_t i = max; i < of.size(); ++i)', 'for (std::size_t i = max + 1; i < of.size(); ++i)'),
    ('the shrine cap is not applied', 'trim(Shrine, knobs.shrinesMax);', ''),
    ('the pylon cap is not applied', 'trim(Pylon, knobs.pylonsMax);', ''),
    ('the pylon minimum is not applied', 'topUp(Pylon, knobs.pylonsMin);', ''),
    ('the shrine minimum is not applied', 'topUp(Shrine, knobs.shrinesMin);', ''),
    ('the minimum overshoots', 'have < min && i < empty.size()', 'have <= min && i < empty.size()'),
    ('a shrine spot can get a pylon kind', 'k.pylon == (what[i] == Pylon) ? k.weight : 0', 'k.weight'),
    ('the kinds are picked evenly whatever the weight', 'k.pylon == (what[i] == Pylon) ? k.weight : 0', 'k.pylon == (what[i] == Pylon) ? 1 : 0'),
    ('the chance has no base', 'k.baseChancePct + (100.0 - k.baseChancePct) * since / k.fullAtPct', '(100.0 - k.baseChancePct) * since / k.fullAtPct'),
    ('the chance forgets the last pylon', 'std::max(0.0, shareNow - shareAtLast)', 'std::max(0.0, shareNow)'),
    ('the chance passes 100', 'return std::clamp(k.baseChancePct + (100.0 - k.baseChancePct) * since / k.fullAtPct, 0.0, 100.0);',
     'return k.baseChancePct + (100.0 - k.baseChancePct) * since / k.fullAtPct;'),
    ('the chance rises to 100 twice as slowly', '* since / k.fullAtPct', '* since / (2 * k.fullAtPct)'),
    ('the Guardian\'s floor alone stops the rolls', 'if (guardianInstance || (state != "open"))', 'if (guardianInstance)'),
    ('only the Guardian\'s instance stops the rolls', 'if (guardianInstance || (state != "open"))', 'if (state == "guardian")'),
    ('a recorded Guardian instance does not stop the rolls', 'if (guardianInstance || (state != "open"))', 'if (state != "open")'),
    ('a fifth pylon rolls', 'had.count >= k.maxPerRun', 'had.count > k.maxPerRun'),
    ('a run is full one pylon early', 'had.count >= k.maxPerRun', 'had.count + 1 >= k.maxPerRun'),
    ('a Greater Rift spot can hold a shrine', 'k.pylon && std::find(', 'std::find('),
    ('a kind can come twice in a run', 'k.pylon && std::find(had.kinds.begin(), had.kinds.end(), k.name) == had.kinds.end()', 'k.pylon'),
    ('a lost roll stands anyway', 'return stands ? pick : -1;', 'return pick;'),
    ('every spot rolls alike', '(static_cast<std::uint64_t>(floor) << 32) | spotId', '(static_cast<std::uint64_t>(floor) << 32)'),
    ('every floor rolls alike', '(static_cast<std::uint64_t>(floor) << 32) | spotId', 'spotId'),
    ('the approach radius is exclusive', '<= yards;', '< yards;'),
    ('exactly the minimum apart is crowded', 'return Distance(spot, other) < minSpacing;', 'return Distance(spot, other) <= minSpacing;'),
    ('the Nephalem roll ignores the spacing', 'what[i] = hit != None && Crowded(spots[i], placed(), knobs.minSpacing) ? None : hit;', 'what[i] = hit;'),
    ('the top-up ignores the spacing', 'if (!Crowded(spots[empty[i]], placed(), knobs.minSpacing))', 'if (true)'),
    ('the Greater Rift roll ignores the spacing', 'if (pick < 0 || Crowded(spot, placed, k.minSpacing))', 'if (pick < 0)'),
    ('a pylon that stands does not move the chance', 'had.shareAtLast = shareNow;', ''),
    ('a pylon that stands is not counted', '++had.count;', ''),
    ('a pylon buff survives leaving the run', 'return !pylon ? Fate::Keeps : speed ? Fate::EndsKnockOnly : Fate::Ends;', 'return Fate::Keeps;'),
    ('a shrine buff ends on leaving the run', 'return !pylon ? Fate::Keeps : speed ? Fate::EndsKnockOnly : Fate::Ends;', 'return pylon ? Fate::Ends : Fate::Ends;'),
    ('Speed ends whole on leaving', 'speed ? Fate::EndsKnockOnly : Fate::Ends', 'Fate::Ends'),
    ('a Greater Rift start leaves the shrine buffs', 'return pylon ? Fate::Keeps : Fate::Ends;', 'return Fate::Keeps;'),
    ('a Greater Rift start ends the pylon buffs', 'return pylon ? Fate::Keeps : Fate::Ends;', 'return Fate::Ends;'),
    ('the spot lookup reaches too far', 'double bestD = NEAR_YARDS;', 'double bestD = NEAR_YARDS * 2;'),
    ('the spot lookup stops short', 'if (d <= bestD)', 'if (d < bestD)'),
    ('the spot lookup takes the last, not the nearest', 'bestD = d;', ''),
    ('the next spot number reuses one', 'return top + 1;', 'return top;'),
]
SQL_MUTANTS = [      # killed by the scratch schema, not by the harness's asserts
    ('an added spot is the survey\'s', ", NULL, 'alex')\";", ", NULL, 'survey')\";"),
    ('a moved spot keeps its walk', ', `entry_walk_yards` = NULL, `source` = \'alex\' WHERE', ', `source` = \'alex\' WHERE'),
    ('a moved spot stays the survey\'s', ', `entry_walk_yards` = NULL, `source` = \'alex\' WHERE', ', `entry_walk_yards` = NULL WHERE'),
    ('a move reaches every spot of the dungeon', '" AND `spot` = " + std::to_string(id);\n    }\n\n    inline std::string RemoveSql', '";\n    }\n\n    inline std::string RemoveSql'),
    ('a removal reaches every spot of the dungeon', 'TouchUp::Quote(dungeon) + " AND `spot` = " + std::to_string(id);\n    }\n} // namespace',
     'TouchUp::Quote(dungeon);\n    }\n} // namespace'),
]
SOURCE_MUTANTS = [
    ('dc_rifts.cpp', 'no placement on a floor', 'Pylons::Update(map, diff);', '(void) diff;'),
    ('dc_rifts.cpp', 'the run\'s count outlives it', 'Pylons::FloorGone(floor.runId, lastFloor);', ''),
    ('dc_rift_pylon.cpp', 'a run\'s count is forgotten at every floor', 'if (!runEnds)\n            return;', ''),
    ('dc_rift_spawner.cpp', 'no seed', 'return found == runs.end() ? 0 : found->second.seed;', 'return 0;'),
    ('dc_rift_pylon.cpp', 'every floor plans alike', 'StreamOf(state.seed, state.floor)', 'StreamOf(state.seed, 1)'),
    ('dc_rift_pylon.cpp', 'the clearance is ignored', 'Usable(LoadSpots(dungeonName), clear)', 'Usable(LoadSpots(dungeonName), 0)'),
    ('dc_rift_pylon.cpp', 'the Nephalem spacing is not read', 'static_cast<unsigned>(k[5]), k[6]}', 'static_cast<unsigned>(k[5]), 0}'),
    ('dc_rift_pylon.cpp', 'a placed object is not kept for the spacing', 'state.placed.push_back(spot);', ''),
    ('dc_rift_pylon.cpp', 'Fortune is even', 'kind == Buffs::Kind::Fortune', 'kind == Buffs::Kind::Count'),
    ('dc_rift_pylon.cpp', 'a Greater Rift places at the open', 'state.waiting = spots;\n                return;', 'state.waiting = spots;'),
    ('dc_rift_pylon.cpp', 'the check runs every tick', 'state->sinceCheck < every', 'false'),
    ('dc_rift_pylon.cpp', 'the share is the raw units', '100.0 * view.progress / view.requiredUnits', 'view.progress'),
    ('dc_rift_pylon.cpp', 'the Guardian does not stop the rolls', 'MayRoll(view.state, view.guardianInstance, had, knobs) != NoRoll::None', 'false'),
    ('dc_rift_pylon.cpp', 'a spot rolls again', 'spot = state.waiting.erase(spot); // a spot rolls once', '++spot; // a spot rolls once'),
    ('dc_rift_pylon.cpp', 'the leave rules are never made', 'new LeaveRules();', ''),
    ('dc_rift_pylon.cpp', 'a Greater Rift floor is treated as any floor', 'Leaving(onFloor, onFloor && view.mode == "gr")', 'Leaving(onFloor, false)'),
    ('dc_rift_pylon.cpp', 'Speed loses its speed in town', 'kind == Buffs::Kind::Speed, *when', 'false, *when'),
    ('dc_gr_rules.cpp', 'a pylon cannot be used in a Greater Rift', 'DC::Combat::Pylons::IsPylonObject(go->GetEntry()) ||', ''),
    ('dc_rift_pylon.cpp', 'anybody may place a spot', '{"here", HandleHere, SEC_ADMINISTRATOR, Console::No}', '{"here", HandleHere, SEC_GAMEMASTER, Console::No}'),
    ('dc_rift_pylon.cpp', 'anybody may clear a spot', '{"clear", HandleClear, SEC_ADMINISTRATOR, Console::No}', '{"clear", HandleClear, SEC_GAMEMASTER, Console::No}'),
    ('dc_rift_pylon.cpp', 'here always adds', 'MoveSql(dungeon.name, rows[near].id, at)', 'AddSql(dungeon.name, rows[near].id, at)'),
    ('dc_rift_pylon.cpp', 'clear removes without looking', 'near < 0', 'false'),
    ('dc_rift_pylon.cpp', 'show marks nothing', 'SummonCreature(MARKER_ENTRY', 'SummonCreature(0'),
    ('dc_rift_pylon.cpp', 'the spots are read in no order', 'ORDER BY `spot`', ''),
    ('dc_rift_pylon.cpp', 'a spot of the survey\'s reads as the designer\'s', '== "alex"', '!= "alex"'),
    ('dc_rift_pylon.cpp', 'the command script is never made', 'new PylonSpotCommand();', ''),
    ('dc_rifts.cpp', 'the pylon commands are never registered', 'Pylons::RegisterScripts();', ''),
    ('dc_rift_exit.cpp', 'the dungeon lookup is gone', 'return DungeonHere(player, out);', 'return false;'),
]
SHEET_MUTANTS = [    # the generator's source, mutated, must write a different sheet
    ('an S area gets a spot', 'PYLON_TAGS = ("M", "L")', 'PYLON_TAGS = ("S", "M", "L")'),
    ('only L areas get a spot', 'PYLON_TAGS = ("M", "L")', 'PYLON_TAGS = ("L",)'),
    ('the spot is the first anchor, not the nearest the centre', 'centre = min(members, key=lambda m: (', 'centre = max(members[:1], key=lambda m: ('),
    ('the spot is the farthest anchor', 'centre = min(members, key=lambda m:', 'centre = max(members, key=lambda m:'),
    ('the spot loses its walk', 'entry_walk_yards=centre["entry_walk_yards"]', 'entry_walk_yards=""'),
    ('the numbers restart nowhere', 'counts[area["dungeon"]] += 1', 'counts["all"] += 1; counts[area["dungeon"]] += 0'),
]


def mutate(text, old, new):
    pattern = re.compile(r'\s+'.join(re.escape(token) for token in old.split()))
    assert len(pattern.findall(text)) == 1, 'mutant target moved: ' + old
    return pattern.sub(lambda _: new, text)


def load_generator(source):
    with tempfile.TemporaryDirectory(prefix='rift-pylon-gen-', dir=SCRATCH) as folder:
        for name in ('applied_migrations.py', 'generate/world/generate_area_copies.py', 'generate/rifts/generate_rifts.py', 'rift_navmesh.py'):
            (Path(folder) / Path(name).name).write_bytes((MODULE / 'scripts' / name).read_bytes())
        path = Path(folder) / 'generate_rift_survey_mutant.py'
        path.write_text(source, encoding='utf-8')
        spec = importlib.util.spec_from_file_location('generate_rift_survey_mutant', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules['generate_rift_survey_mutant'] = module
        spec.loader.exec_module(module)
        return module


def test_mutants_are_killed():
    header = read(HEADER)
    for what, old, new in HEADER_MUTANTS:
        rc, out, err = run_harness(mutate(header, old, new))
        assert rc != 0 or 'rift pylon harness: ok' not in out, 'header mutant survived: ' + what
        print('PASS mutant killed:', what)
    for what, old, new in SQL_MUTANTS:
        try:
            test_adding_moving_and_removing_a_spot(mutate(header, old, new))
        except (AssertionError, subprocess.CalledProcessError):
            print('PASS mutant killed:', what)
            continue
        raise AssertionError('SQL mutant survived: ' + what)
    base = texts()
    for name, what, old, new in SOURCE_MUTANTS:
        t = dict(base)
        t[name] = mutate(t[name], old, new)
        try:
            check_wiring(t)
        except (AssertionError, ValueError):
            print('PASS mutant killed:', what)
            continue
        raise AssertionError('source mutant survived: ' + what)
    generator = read(MODULE / 'scripts/generate/rifts/generate_rift_survey.py')
    s = sheets()
    expected = S0.pylon_spots(s)
    for what, old, new in SHEET_MUTANTS:
        module = load_generator(mutate(generator, old, new))
        assert module.pylon_spots(s) != expected, 'sheet mutant survived: ' + what
        print('PASS mutant killed:', what)


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('PASS', name)

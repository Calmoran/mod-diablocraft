"""Rift floors Part F2 (diablocraft-m36x): the exit portal and the next floor.

What runs here:
  * the production decisions (src/rifts/dc_rift_exit.h) and the production run book (dc_rift_floors.h) are compiled with
    tests/rift_exit/harness.cpp: the spot the designer's placement or the survey gives, the refusals and their order, the floor a click
    leads to, the maps a new floor may roll (fed the pool's own map ids from rift_dungeons.csv: 30 rows on 29 maps, a run ends at
    29 floors with no map twice), where the obelisk portal leads once floor 1 has unloaded, and the SQL of `.dc floor exit`;
  * that SQL runs on a scratch schema of the fixture mysqld that holds rift_survey_0001.sql and the table of rifts_0021: a spot
    is placed, replaced and cleared for every one of the 30 dungeons (an apostrophe in a name included) and the survey's own
    table never moves; generate_rift_survey.py --export then writes the designer's spots into the exit sheet and nothing else, and the
    sheet he comes home as refuses a new --survey;
  * the migration the generator writes (17 templates, entry = look + 40) against rift_portals.csv, the header's offset and the
    Greater Rift exception's range in test_gr_rules.py;
  * source checks on the wiring the harness cannot reach (the hook that records a later floor, OpenNextFloor, the click, the
    placing, the obelisk portal, the commands, rule 3), each held by a mutant that must turn a check red.
What needs the worldserver (the portal standing on a floor, the click, the teleports, the loading screens) is held by
docs/test-diablocraft-m36x.md on dev.

DC_RIFT_EXIT_RIFTS points the read at a copy of src/rifts (red-on-the-base run)."""
import csv
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
import generate_rifts as G  # noqa: E402
import harness_env  # noqa: E402
from generate_area_copies import Database  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
RIFTS = Path(os.environ.get('DC_RIFT_EXIT_RIFTS', MODULE / 'src/rifts'))
SCRATCH = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
D3 = MODULE / 'data/d3'
UPDATES = MODULE / 'data/sql/db-world/updates'
HEADER = RIFTS / 'dc_rift_exit.h'
AHN = "Ahn'kahet: The Old Kingdom"


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
PORTALS = csv_rows(D3 / 'rift_portals.csv')


# --- the compiled harness ------------------------------------------------------------------------------------------------------
def run_harness(header_text, commands=None):
    """Compiles tests/rift_exit/harness.cpp around `header_text`; returns (returncode, stdout, stderr)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rift-exit-', dir=SCRATCH) as folder:
        folder = Path(folder)
        (folder / 'dc_rift_exit.h').write_text(header_text, encoding='utf-8')
        for name in ('dc_rift_floors.h', 'dc_rift_touchup.h'):
            (folder / name).write_text(read(RIFTS / name), encoding='utf-8')
        (folder / 'maps.txt').write_text('\n'.join(row['map_id'] for row in POOL), encoding='utf-8')
        argv = [str(folder / 'harness'), str(folder / 'maps.txt')]
        if commands is not None:
            (folder / 'commands.txt').write_text(commands, encoding='utf-8')
            argv.append(str(folder / 'commands.txt'))
        built = subprocess.run(['c++', '-std=c++20', '-O0', '-UNDEBUG', '-Wall', '-Wextra', f'-I{folder}',
                                str(MODULE / 'tests/rift_exit/harness.cpp'), '-o', argv[0]], capture_output=True, text=True)
        if built.returncode:
            return 99, '', 'COMPILE ' + built.stderr[-1500:]
        ran = harness_env.run(argv, capture_output=True, text=True)
        return ran.returncode, ran.stdout, ran.stderr


def test_the_decisions():
    rc, out, err = run_harness(read(HEADER))
    assert rc == 0 and 'rift exit harness: ok' in out, (rc, err[-1500:])


# --- the SQL of `.dc floor exit`, on a scratch schema -------------------------------------------------------------------------------
class Scratch:
    """A schema of the fixture mysqld holding the survey migrations (the dungeons' and the open zones', each with its exit points,
    diablocraft-yh7el) and the table rifts_0021 makes, dropped on exit."""

    def __init__(self):
        self.mysql, self.defaults = fixture_db.mysql_and_defaults([])
        self.name = 'scratch_rift_exit_%d_%d' % (os.getpid(), random.randrange(10 ** 6))

    def client(self, *extra, stdin=None):
        argv = [self.mysql, '--defaults-file=' + self.defaults, '--no-login-paths', '--batch', '--raw', '--skip-column-names', *extra]
        done = subprocess.run(argv, input=stdin, text=True, capture_output=True)
        assert done.returncode == 0, done.stderr
        return done.stdout

    def __enter__(self):
        self.client(stdin='DROP DATABASE IF EXISTS %s; CREATE DATABASE %s' % (self.name, self.name))
        self.client(self.name, stdin=read(UPDATES / S0.NAME))
        self.client(self.name, stdin=read(UPDATES / S0.OPEN_NAME))
        migration = read(UPDATES / G.EXIT_MIGRATION)
        self.client(self.name, stdin=migration[migration.index('CREATE TABLE IF NOT EXISTS `dc_rift_exit_spot`'):])   # the templates need the core's table
        self.db = Database(self.mysql, self.defaults, self.name)
        return self

    def __exit__(self, *exc):
        self.client(stdin='DROP DATABASE IF EXISTS %s' % self.name)

    def run(self, sql):
        self.client(self.name, stdin=sql)

    def spots(self):
        return {row['dungeon']: (round(row['x'], 4), round(row['y'], 4), round(row['z'], 4), round(row['o'], 4))
                for row in self.db.rows('dc_rift_exit_spot')}

    def survey_points(self):
        return sorted((row['dungeon'], row['x'], row['y'], row['z'], row['o'], row['source']) for row in self.db.rows('dc_rift_exit_point'))


def test_placing_replacing_and_clearing_a_spot_for_every_dungeon(header_text=None):
    names = [row['name'] for row in POOL]
    assert AHN in names and len(set(names)) == 30
    rng = random.Random(8)
    coords = {name: tuple(round(rng.uniform(-900, 900), 4) for _ in range(4)) for name in names}
    later = {name: tuple(round(rng.uniform(-900, 900), 4) for _ in range(4)) for name in names}
    lines = ''.join('place\t%s\t%s\n' % (n, ' '.join(map(str, coords[n]))) for n in names)
    lines += ''.join('place\t%s\t%s\n' % (n, ' '.join(map(str, later[n]))) for n in names[:10])
    lines += ''.join('clear\t%s\n' % n for n in names[10:20])
    rc, out, err = run_harness(header_text or read(HEADER), lines)
    assert rc == 0, err
    statements = [line for line in out.splitlines() if line.startswith(('REPLACE', 'DELETE'))]
    assert len(statements) == 50, len(statements)
    with Scratch() as scratch:
        before = scratch.survey_points()
        assert scratch.spots() == {}
        for sql in statements[:30]:                       # every dungeon placed
            scratch.run(sql)
        assert scratch.spots() == {n: coords[n] for n in names}
        for sql in statements[30:40]:                     # ten placed again: replaced, never doubled
            scratch.run(sql)
        assert scratch.spots() == {n: (later[n] if n in names[:10] else coords[n]) for n in names}
        for sql in statements[40:]:                       # ten cleared: only those
            scratch.run(sql)
        expect = {n: (later[n] if n in names[:10] else coords[n]) for n in names if n not in names[10:20]}
        assert scratch.spots() == expect
        assert scratch.survey_points() == before          # the survey's far points are never touched
        scratch.run(statements[-1])                       # clearing a dungeon with no spot is nothing
        assert scratch.spots() == expect


def test_alexs_spots_come_home_through_export():
    committed = csv_rows(D3 / 'rift_exit_points.csv')
    numbers = lambda value: round(float(value), 4) if re.fullmatch(r'-?\d+(\.\d+)?', value) else value
    same = lambda rows: [{k: numbers(v) for k, v in row.items()} for row in rows]
    placed = {AHN: (10.5, -20.25, 30.125, 1.5), 'Ragefire Chasm': (-390.0, 120.0, 8.0, 0.0)}
    lines = ''.join('place\t%s\t%s\n' % (n, ' '.join(map(str, at))) for n, at in placed.items())
    rc, out, err = run_harness(read(HEADER), lines)
    assert rc == 0, err
    with Scratch() as scratch, tempfile.TemporaryDirectory(prefix='rift-exit-export-', dir=SCRATCH) as folder:
        folder = Path(folder)
        for sheet in S0.SHEETS:                          # the native filter and the report are the survey's, not exported
            (folder / sheet).write_bytes((D3 / sheet).read_bytes())
        S0.export(scratch.db, folder)                    # no spot placed: the survey's points, unchanged
        assert same(csv_rows(folder / 'rift_exit_points.csv')) == same(committed)
        for sql in out.splitlines():
            if sql.startswith('REPLACE'):
                scratch.run(sql)
        S0.export(scratch.db, folder)
        exported = csv_rows(folder / 'rift_exit_points.csv')
        assert [r['dungeon'] for r in exported] == [r['dungeon'] for r in committed]           # the same order
        for ours, theirs in zip(same(exported), same(committed)):
            if ours['dungeon'] in placed:
                x, y, z, o = placed[ours['dungeon']]
                assert (ours['x'], ours['y'], ours['z'], ours['o']) == (x, y, z, o) and ours['source'] == 'alex' and ours['walk_yards'] == ''
            else:
                assert ours == theirs, ours['dungeon']       # every other row is the survey's, as committed
        assert S0.has_alex(S0.read_sheets(folder))           # and a new --survey refuses them
        # the migration the edited sheets render loads back to the same far points
        edited = [r for r in exported if r['dungeon'] in placed]
        assert len(edited) == 2
        rendered = S0.render(S0.read_sheets(folder))
        with Scratch() as again:
            again.run(rendered)
            points = {row[0]: row for row in again.survey_points()}
            assert points[AHN][5] == 'alex' and round(points[AHN][1], 4) == 10.5
        # a spot for a dungeon the sheet does not have is refused
        scratch.run("REPLACE INTO dc_rift_exit_spot VALUES ('Nowhere', 1, 2, 3, 4)")
        try:
            S0.export(scratch.db, folder)
        except ValueError as error:
            assert 'Nowhere' in str(error)
        else:
            raise AssertionError('an unknown dungeon was exported')


# --- the migration, against the sheet and the header ----------------------------------------------------------------------------------
def without_quest_ids(text):
    """Quest ids are their own namespace: the bounty quests (910200-911999, hyoic.5) overlap the exit entries in digits only (o4azk)."""
    text = re.sub(r'^INSERT INTO `(?:quest_template|quest_template_addon|dc_bounties_quest)`.*?;$', '', text, flags=re.M | re.S)
    return re.sub(r'^-- quest ids:.*$', '', text, flags=re.M)


def test_quest_ids_are_skipped_but_a_gameobject_on_an_exit_entry_is_not():
    sql = ("INSERT INTO `quest_template` (`ID`) VALUES\n  (911070),\n  (911071);\n"
           "INSERT INTO `gameobject_template` (`entry`) VALUES\n  (911072);\n-- quest ids: 911073\n")
    assert {int(n) for n in re.findall(r'(?<![\d.])91\d{4}(?![\d.])', without_quest_ids(sql))} == {911072}


def test_the_exit_templates_are_the_entrance_looks_plus_the_offset():
    """rifts_0021 (floor 2's 17 templates, frozen in its first form) and rifts_0025 (every floor led to, named 'Floor N')."""
    sql = read(UPDATES / G.EXIT_MIGRATION)
    assert sql == read(MODULE / 'data/generated/rift_floor_exit.sql') == G.exit_sql(G.read_portals())
    header = read(HEADER)
    offset = int(re.search(r'EXIT_ENTRY_OFFSET = (\d+);', header).group(1))
    assert offset == G.EXIT_ENTRY_OFFSET == 40
    stride = int(re.search(r'EXIT_FLOOR_STRIDE = (\d+);', header).group(1))
    block = int(re.search(r'EXIT_LOOK_BLOCK = (\d+);', header).group(1))
    assert (stride, block) == (G.EXIT_FLOOR_STRIDE, G.EXIT_LOOK_BLOCK) == (1000, 910000)
    # every look lies in the block, below the first exit's slot, so the header decodes an entry back to its look
    assert all(block <= int(l['entry_id']) < block + offset + 30 for l in PORTALS)
    cap = int(next(r for r in csv_rows(MODULE / 'data/tunables/rifts.csv') if r['name'] == 'rift_max_floors')['value'])
    names = read(UPDATES / G.EXIT_NAMES_MIGRATION)
    assert names == read(MODULE / 'data/generated/rift_floor_exit_names.sql') == G.exit_names_sql(G.read_portals(), cap)
    rows = re.findall(r"^\s*\((\d+), (\d+), (\d+), '([^']*)', '', '', '', ([\d.]+), 0, 0, 0, 1, (?:0, ){20}'', '', 12340\)", names, re.M)
    assert len(rows) == (cap - 1) * len(PORTALS) == 153
    expected = [(floor, look) for floor in range(2, cap + 1) for look in PORTALS]
    for (entry, gotype, display, name, size), (floor, look) in zip(rows, expected):
        assert int(entry) == int(look['entry_id']) + offset + stride * (floor - 2) and int(display) == int(look['display_id'])
        assert gotype == '22' and name == 'Floor %d' % floor and float(size) == float(look['scale'])
    deleted = re.search(r'DELETE FROM `gameobject_template` WHERE `entry` IN \(([^)]*)\)', names).group(1)
    assert [int(n) for n in deleted.split(',')] == [int(r[0]) for r in rows]
    # floor 2 is rifts_0021's entries, so 0025 replaces their name rather than leaving a second set
    first = {int(r[0]) for r in re.findall(r"^\s*\((\d+), (\d+)", sql, re.M)}
    assert first == {int(r[0]) for r in rows[:len(PORTALS)]}
    # no other gameobject template, creature or sheet row anywhere uses these entries
    mine = {int(r[0]) for r in rows}
    for path in list(UPDATES.glob('*.sql')) + list((MODULE / 'data').glob('*/*.csv')):
        if path.name in (G.EXIT_MIGRATION, G.EXIT_NAMES_MIGRATION):
            continue
        text = re.sub(r'\d{6}-\d{6}', '', read(path))   # a range named in a sheet's prose note (world_objects.csv) is not a use
        text = without_quest_ids(text)
        found = {int(n) for n in re.findall(r'(?<![\d.])91\d{4}(?![\d.])', text)} & mine
        assert not found, (path.name, found)
    # the Greater Rift exception's range in test_gr_rules.py covers exactly these entries
    gr = read(MODULE / 'scripts/tests/rifts/test_gr_rules.py')
    low, high, lo_rem, hi_rem = re.search(r'entry >= (\d+) && entry <= (\d+) && entry %% 1000 >= (\d+) && entry %% 1000 <= (\d+)', gr).groups()
    assert (int(low), int(high)) == (min(mine), max(mine))
    assert {e for e in range(int(low), int(high) + 1) if int(lo_rem) <= e % 1000 <= int(hi_rem)} == mine
    # a table the command writes and the export reads
    assert 'CREATE TABLE IF NOT EXISTS `dc_rift_exit_spot`' in sql and 'PRIMARY KEY (`dungeon`)' in sql


def test_the_floor_cap_is_a_tunable():
    rows = [r for r in csv_rows(MODULE / 'data/tunables/rifts.csv') if r['name'] == 'rift_max_floors']
    assert len(rows) == 1 and rows[0]['value'] == '10' and rows[0]['unit'] == 'count'
    for path in (MODULE / 'data/generated/tunables_0012.sql', UPDATES / 'tunables_0012.sql'):
        assert re.search(r"\('rifts', 'rift_max_floors', NULL, 10\.0,", read(path)), path.name
    assert 'Tunables::Get("rifts", "rift_max_floors")' in read(RIFTS / 'dc_rift_exit.cpp')


# --- the wiring the harness cannot reach ----------------------------------------------------------------------------------------------
def texts():
    # 'dc_rifts.cpp' stands for the rift files joined (split_sources), so a mutant finds its line in whichever holds it
    return {name: rifts_text(RIFTS.parent) if name == 'dc_rifts.cpp' else read(RIFTS / name) for name in ('dc_rifts.cpp', 'dc_rift_exit.cpp', 'dc_gr_rules.cpp', 'dc_rift_quests.cpp',
                                                  'dc_rifts_internal.h')}


def check_wiring(t):
    rifts, exit_, rules, quests, internal = (t[k] for k in ('dc_rifts.cpp', 'dc_rift_exit.cpp', 'dc_gr_rules.cpp', 'dc_rift_quests.cpp',
                                                           'dc_rifts_internal.h'))
    # a later floor is recorded by the creation hook, not made a new run
    hook = definition(rifts, 'void OnBeforeCreateInstanceScript(')
    assert hook.index('if (rift.id)') < hook.index('RecordLaterFloor(rift);') < hook.index('return;', hook.index('RecordLaterFloor(rift);')) < hook.index('INSERT INTO dc_rift (')
    later = definition(rifts, 'void RecordLaterFloor(Rift& rift)')
    assert 'live.AddFloor(rift.id, rift.instanceId, rift.mapId, rift.dungeonId)' in later and 'INSERT INTO dc_rift_floor' in later
    assert 'live.Start(' not in later and 'INSERT INTO dc_rift ' not in later
    # the next floor: unbind, create inside the scope that names the run, bind
    make = definition(rifts, 'bool OpenNextFloor(')
    assert 'next.id = from.id;' in make
    assert make.index('PlayerUnbindInstance(player->GetGUID(), dungeon.mapId') < make.index('CreateMap(dungeon.mapId, player)') \
        < make.index('BindToFloor(player, made)')
    assert 'map->GetInstanceId() != next.instanceId' in make and 'sInstanceSaveMgr->PlayerBindToInstance' not in make
    bind = definition(rifts, 'bool BindToFloor(')
    assert 'PlayerBindToInstance(player->GetGUID(), save, false, player)' in bind and 'riftMembers[floor.instanceId]' in bind
    # the obelisk portal: floor 1, else the lowest standing; the run closed or no floor: "closed"
    entrance = definition(rifts, 'void UseEntrance(Player* player, GameObject* go)')
    assert 'Exit::ObeliskFloor(standing)' in entrance and 'live.Floors(runId)' in entrance and 'IsLiveInstance' not in entrance
    assert entrance.index('Exit::ObeliskFloor') < entrance.index('EnrolledRun(') < entrance.index('IsInCombat()') < entrance.index('BindToFloor(player, target)') \
        < entrance.index('ForcedTeleport')
    assert 'run->state == "closed"' in entrance and 'arrival.mapId, arrival.x, arrival.y, arrival.z, arrival.o' in entrance
    # the click, the look and the placing
    hello = definition(rifts, 'bool CanGameObjectGossipHello(Player* player, GameObject* go) override')
    assert re.search(r'if \(IsExitPortal\(go->GetEntry\(\)\)\)\s*\{\s*Exit::Use\(player, go\);\s*return true;', hello)
    exit_check = definition(rifts, 'bool IsExitPortal(std::uint32_t entry)')
    assert 'Exit::LookOf(entry)' in exit_check and 'IsEntrancePortal(look)' in exit_check
    update = definition(rifts, 'void OnMapUpdate(Map* map, uint32 diff) override')
    assert re.search(r'if \(rift\)\s*Spawner::OpenFloor\(map, tier\);\s*(//[^\n]*\n\s*)*if \(rift\)\s*Exit::PlaceExit\(map\);', update)
    assert 'Exit::Forget(map->GetInstanceId());' in definition(rifts, 'void OnDestroyMap(Map* map) override')
    assert 'Exit::RegisterScripts();' in definition(rifts, 'void RegisterScripts()')
    status = definition(rifts, 'static bool HandleStatus(ChatHandler* handler)')
    assert 'live.Floors(rift.id)' in status and 'Exit::Describe(floor.instanceId, floor.mapId)' in status
    # the click: a member, alive, in combat or not; the next standing floor else a new one, every refusal said
    use = definition(exit_, 'void Use(Player* player, GameObject* go)')
    assert 'IsInCombat' not in use                                           # 6.3: it works in combat
    assert 'EnrolledRun(player->GetGUID(), mine) || mine.id != here.id' in use and '!player->IsAlive()' in use
    assert use.index('live.View(map->GetInstanceId(), map->GetId(), here)') < use.index('"closed"') < use.index('EnrolledRun(') \
        < use.index('IsAlive()') < use.index('NextStanding(standing, here.floor)') < use.index('MayOpenNext(') \
        < use.index('OpenNextFloor(player, here, arrival, target, error)') < use.index('ForcedTeleport')
    assert 'MayOpenNext(here.state, here.guardianInstance, highest, FloorCap(), eligible.size())' in use
    assert 'EligibleMaps(maps, used)' in use and 'used = live.UsedMaps(here.id)' in use and 'highest = live.Highest(here.id)' in use
    assert 'BindToFloor(player, target)' in use and 'uniform_int_distribution<std::size_t>(0, eligible.size() - 1)' in use
    place = definition(exit_, 'void PlaceExit(Map* map)')
    assert place.index('view.floor >= FloorCap()') < place.index('SpotFor(') < place.index('RollExitEntry(view.floor + 1)') < place.index('SummonGameObject(')
    assert 'ExitEntry(looks[' in definition(exit_, 'std::uint32_t RollExitEntry(unsigned leadsTo)') and ', leadsTo)' in exit_ and 'PortalPool()' in exit_
    spot = definition(exit_, 'std::optional<Spot> SpotFor(')
    assert spot.index('"dc_rift_exit_spot"') < spot.index('"dc_rift_exit_point"') and 'ChooseSpot(alex, survey)' in spot
    # the commands: looking is a GM's, placing and clearing an administrator's
    table = definition(exit_, 'GetCommands() const override')
    for name, level in (('here', 'SEC_ADMINISTRATOR'), ('show', 'SEC_GAMEMASTER'), ('clear', 'SEC_ADMINISTRATOR')):
        assert '{"%s", Handle%s, %s, Console::No}' % (name, name.capitalize(), level) in table, name
    assert '{"floor", floor}' in table and '{"exit", exit}' in table
    assert 'PlaceSql(dungeon.name, at)' in exit_ and 'ClearSql(dungeon.name)' in exit_
    assert not re.search(r'\b(INSERT|UPDATE|DELETE|REPLACE)\b', exit_.split('namespace DC::Rifts::Exit')[1]), 'the SQL of an edit is the header\'s'
    # rule 3 lets the exit portal through
    clickables = definition(rules, 'bool CanGameObjectGossipHello(Player* player, GameObject* go) override')
    assert 'Gr::TownPortalEntry(go->GetEntry()) || IsExitPortal(go->GetEntry())' in clickables
    # a member removed from the party is unbound from every floor still standing, and sent out from any of them
    removed = definition(quests, 'void OnRemoveMember(Group*, ObjectGuid guid, RemoveMethod method, ObjectGuid, char const*) override')
    assert 'live.Floors(rift.id)' in removed and re.search(r'for \(Floor const& floor : floors\)\s*sInstanceSaveMgr->PlayerUnbindInstance\(guid, floor\.mapId', removed)
    assert 'bool OpenNextFloor(Player* player, Rift const& from, Dungeon const& dungeon, Floor& made, std::string& error);' in internal
    assert 'bool IsExitPortal(std::uint32_t entry);' in internal and 'void PlaceExit(Map* map);' in internal


def test_the_wiring():
    check_wiring(texts())


# --- killed mutation runs -----------------------------------------------------------------------------------------------------------------
HEADER_MUTANTS = [
    ('his spot loses to the survey\'s', 'return alex ? alex : survey;', 'return survey ? survey : alex;'),
    ('a closed run opens a floor', 'if (state == "closed")\n            return Refusal::Closed;', ''),
    ('the Guardian does not stop new floors', 'if (guardianInstance || state == "guardian" || state == "complete")', 'if (false)'),
    ('the Guardian floor alone does not stop them', 'if (guardianInstance || state == "guardian"', 'if (state == "guardian"'),
    ('a complete run opens floors', ' || state == "complete")', ')'),
    ('the cap is one floor too many', 'if (highest >= cap)', 'if (highest > cap)'),
    ('the cap is one floor too few', 'if (highest >= cap)', 'if (highest + 1 >= cap)'),
    ('a run with no map left opens one', 'if (!maps)\n            return Refusal::NoMap;', ''),
    ('the cap is checked after the maps', 'if (highest >= cap)\n            return Refusal::LastFloor;\n        if (!maps)\n            return Refusal::NoMap;',
     'if (!maps)\n            return Refusal::NoMap;\n        if (highest >= cap)\n            return Refusal::LastFloor;'),
    ('the next floor is the highest', 'if (number > current && (!next || number < next))', 'if (number > current && (!next || number > next))'),
    ('the next floor can be this one', 'if (number > current &&', 'if (number >= current &&'),
    ('the obelisk leads to the highest floor', 'if (!lowest || number < lowest)', 'if (!lowest || number > lowest)'),
    ('a used map is rolled again', 'if (!used.count(poolMaps[i]))', 'if (true)'),
    ('only the first used map is out', 'if (!used.count(poolMaps[i]))', 'if (!(used.size() && poolMaps[i] == *used.begin()))'),
    ('the exit entry is the look', 'return lookEntry + EXIT_ENTRY_OFFSET + EXIT_FLOOR_STRIDE * (leadsTo > 2 ? leadsTo - 2 : 0);', 'return lookEntry + EXIT_FLOOR_STRIDE * (leadsTo > 2 ? leadsTo - 2 : 0);'),
    ('every floor shares floor 2\'s templates', 'EXIT_FLOOR_STRIDE * (leadsTo > 2 ? leadsTo - 2 : 0);', '0;'),
    ('the floor led to is one off', '(leadsTo > 2 ? leadsTo - 2 : 0)', '(leadsTo > 2 ? leadsTo - 1 : 0)'),
    ('the look is not the entry minus the offset', 'EXIT_LOOK_BLOCK + inBlock - EXIT_ENTRY_OFFSET : 0', 'EXIT_LOOK_BLOCK + inBlock : 0'),
    ('the look ignores the floor block', '% EXIT_FLOOR_STRIDE;', '% (EXIT_FLOOR_STRIDE * 100);'),
]
SQL_MUTANTS = [      # killed by the scratch schema, not by the harness's asserts
    ('placing adds a second spot', 'REPLACE INTO', 'INSERT INTO'),
    ('clearing deletes every spot', ' WHERE `dungeon` = " + TouchUp::Quote(dungeon)', '"'),
]
SOURCE_MUTANTS = [
    ('dc_rifts.cpp', 'a later floor is made a new run', 'RecordLaterFloor(rift); // rift floors Part F2: the run is recorded already\n                return;', ''),
    ('dc_rifts.cpp', 'the next floor is bound before it exists', 'PlayerUnbindInstance(player->GetGUID(), dungeon.mapId, DUNGEON_DIFFICULTY_NORMAL, true, player);\n        Rift next;',
     'Rift next;'),
    ('dc_rifts.cpp', 'the new floor takes no run id', 'next.id = from.id;', ''),
    ('dc_rifts.cpp', 'the obelisk portal reads the run, not the floors', 'unsigned const number = closed ? 0 : Exit::ObeliskFloor(standing);', 'unsigned const number = closed ? 0 : 1;'),
    ('dc_rifts.cpp', 'the exit click is not routed', 'Exit::Use(player, go);', 'UseEntrance(player, go);'),
    ('dc_rifts.cpp', 'the exit is never placed', 'if (rift)\n                Exit::PlaceExit(map);', ''),
    ('dc_rifts.cpp', 'status shows no floors', 'Exit::Describe(floor.instanceId, floor.mapId)', '""'),
    ('dc_rifts.cpp', 'a floor\'s exit record outlives its map', 'Exit::Forget(map->GetInstanceId());', ''),
    ('dc_rift_exit.cpp', 'the exit works only out of combat', '        if (!player->IsAlive())\n        {\n            handler.SendSysMessage("Use the exit portal alive.");',
     '        if (player->IsInCombat() || !player->IsAlive())\n        {\n            handler.SendSysMessage("Use the exit portal alive.");'),
    ('dc_rift_exit.cpp', 'anybody may use the exit', 'EnrolledRun(player->GetGUID(), mine) || mine.id != here.id', 'false'),
    ('dc_rift_exit.cpp', 'the Guardian floor is not asked', 'MayOpenNext(here.state, here.guardianInstance, highest,', 'MayOpenNext(here.state, 0, highest,'),
    ('dc_rift_exit.cpp', 'the cap counts the standing floors', 'highest = live.Highest(here.id);', 'highest = floors.size();'),
    ('dc_rift_exit.cpp', 'unloaded floors\' maps are rolled again', 'used = live.UsedMaps(here.id);', 'used = {};'),
    ('dc_rift_exit.cpp', 'the exit is named for its own floor', 'RollExitEntry(view.floor + 1)', 'RollExitEntry(view.floor)'),
    ('dc_rift_exit.cpp', 'the last floor has an exit', 'if (view.floor >= FloorCap())', 'if (false)'),
    ('dc_rift_exit.cpp', 'the survey is read before the designer\'s spot', 'std::optional<Spot> alex = ReadSpot("dc_rift_exit_spot", dungeon);\n            std::optional<Spot> survey = alex ? std::nullopt : ReadSpot("dc_rift_exit_point", dungeon);',
     'std::optional<Spot> alex = ReadSpot("dc_rift_exit_point", dungeon);\n            std::optional<Spot> survey = alex ? std::nullopt : ReadSpot("dc_rift_exit_spot", dungeon);'),
    ('dc_rift_exit.cpp', 'anybody may place an exit', '{"here", HandleHere, SEC_ADMINISTRATOR, Console::No}', '{"here", HandleHere, SEC_GAMEMASTER, Console::No}'),
    ('dc_gr_rules.cpp', 'rule 3 refuses the exit portal', ' || IsExitPortal(go->GetEntry())', ''),
    ('dc_rift_quests.cpp', 'a removed member keeps the later floors\' binds', 'sInstanceSaveMgr->PlayerUnbindInstance(guid, floor.mapId, DUNGEON_DIFFICULTY_NORMAL, true, left);',
     'if (floor.number == 1) sInstanceSaveMgr->PlayerUnbindInstance(guid, floor.mapId, DUNGEON_DIFFICULTY_NORMAL, true, left);'),
]


def mutate(text, old, new):
    pattern = re.compile(r'\s+'.join(re.escape(token) for token in old.split()))
    assert len(pattern.findall(text)) == 1, 'mutant target moved: ' + old
    return pattern.sub(lambda _: new, text)


def test_mutants_are_killed():
    header = read(HEADER)
    for what, old, new in HEADER_MUTANTS:
        rc, out, err = run_harness(mutate(header, old, new))
        assert rc != 0 or 'rift exit harness: ok' not in out, 'header mutant survived: ' + what
        print('PASS mutant killed:', what)
    for what, old, new in SQL_MUTANTS:
        try:
            test_placing_replacing_and_clearing_a_spot_for_every_dungeon(mutate(header, old, new))
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


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('PASS', name)

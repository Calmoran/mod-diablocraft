"""Rift floors Part F4 (diablocraft-o69g): the way back out of a rift floor.

What runs here:
  * the production decision (src/rifts/dc_rift_way_back.h) is compiled with tests/rift_way_back/harness.cpp: a member goes up a
    floor, from floor 1 to the hub, a floor above that unloaded leads to the hub, a Greater Rift shuts every way to the hub until
    its Guardian is dead (up is never shut), a closed run and a non-member just leave, the dead use nothing; the script's name is the
    generator's;
  * the generator's survey (generate_rift_way_back.py) on a made-up world: the triggers of a pool map that lead to another map are
    kept, one that leads to its own map or has no teleport row is not, a map two rows share is listed once, a pool row with no
    way out and a trigger that already has another script are refused; the AreaTrigger.dbc reader on a file the test writes;
  * the committed sheet: the survey re-run on the fixture world copy and the real AreaTrigger.dbc must equal it (30 pool rows on
    29 maps, a way out within 25.1 yards of every row's arrival point, the plan's measure), the migration and its mirror must be
    the sheet rendered, and the migration must load on a scratch schema, twice, with one row per trigger;
  * source checks on the wiring the harness cannot reach (the script's order of asks, the destinations, the registration, the
    exit portal's spot kept for the way up), each held by a mutant that must turn a check red.
What needs the worldserver (stepping on a trigger in a floor, the teleports) is held by docs/test-diablocraft-o69g.md on dev.

DC_RIFT_WAY_BACK_RIFTS points the read at a copy of src/rifts (red-on-the-base run)."""
import os
import random
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import generate_rift_way_back as W  # noqa: E402
import harness_env  # noqa: E402
from generate_area_copies import Database  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
RIFTS = Path(os.environ.get('DC_RIFT_WAY_BACK_RIFTS', MODULE / 'src/rifts'))
SCRATCH = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
DATA = ROOT / 'azerothcore-wotlk/build/server/data'
UPDATES = MODULE / 'data/sql/db-world/updates'
HEADER = RIFTS / 'dc_rift_way_back.h'


def read(path):
    return Path(path).read_text(encoding='utf-8')


def definition(text, marker):
    start = text.index(marker)
    end, depth = text.index('{', start) + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


# --- the compiled harness ------------------------------------------------------------------------------------------------------
def run_harness(header_text, *argv):
    """Compiles tests/rift_way_back/harness.cpp around `header_text`; returns (returncode, stdout, stderr)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rift-way-back-', dir=SCRATCH) as folder:
        folder = Path(folder)
        (folder / 'dc_rift_way_back.h').write_text(header_text, encoding='utf-8')
        binary = folder / 'harness'
        built = subprocess.run(['c++', '-std=c++20', '-O0', '-UNDEBUG', '-Wall', '-Wextra', f'-I{folder}',
                                str(MODULE / 'tests/rift_way_back/harness.cpp'), '-o', str(binary)], capture_output=True, text=True)
        if built.returncode:
            return 99, '', 'COMPILE ' + built.stderr[-1500:]
        ran = harness_env.run([str(binary), *argv], capture_output=True, text=True)
        return ran.returncode, ran.stdout, ran.stderr


def test_the_decisions():
    rc, out, err = run_harness(read(HEADER))
    assert rc == 0 and 'rift way back harness: ok' in out, (rc, err[-1500:])


def test_the_script_name_is_the_generators():
    rc, out, err = run_harness(read(HEADER), 'name')
    assert rc == 0 and out.split() == [W.SCRIPT_NAME, W.NONE_SCRIPT_NAME] == ['dc_rift_way_back', 'dc_rift_way_none'], (rc, out, err[-500:])
    assert 'AreaTriggerScript(WayBack::SCRIPT_NAME)' in read(RIFTS / 'dc_rift_exit.cpp')
    assert 'AreaTriggerScript(WayBack::NONE_SCRIPT_NAME)' in read(RIFTS / 'dc_rift_exit.cpp')


# --- the survey, on a made-up world -----------------------------------------------------------------------------------------------------
def pool_row(name, map_id, x=0.0):
    return {'name': name, 'map_id': str(map_id), 'entry_x': str(x), 'entry_y': '0', 'entry_z': '0', 'recommended': 'yes'}


def test_the_survey_on_a_made_up_world():
    pool = [pool_row('A', 10), pool_row('B1', 20, 0), pool_row('B2', 20, 1000), pool_row('C', 30)]
    triggers = {1: (10, 5, 0, 0), 2: (10, 9, 0, 0), 3: (20, 990, 0, 0), 4: (20, 3, 0, 0), 5: (30, 0, 7, 0), 6: (99, 0, 0, 0)}
    teleports = {1: (0, 'A out'), 2: (10, 'A inside'), 3: (0, 'B out far'), 4: (0, 'B out near'), 5: (1, 'C out'), 6: (0, 'elsewhere')}
    rows = W.survey(pool, triggers, teleports, {})
    assert [(r['trigger'], r['nearest_dungeon'], r['arrival_yards']) for r in rows] == \
        [(1, 'A', '5.0'), (4, 'B1', '3.0'), (3, 'B2', '10.0'), (5, 'C', '7.0')]       # 2 leads to its own map, 6 is on no pool map
    assert {r['map_id'] for r in rows} == {10, 20, 30}                                # map 20 is listed once, not once per row
    assert W.survey(pool, triggers, teleports, {1: W.SCRIPT_NAME})[0]['trigger'] == 1  # our own script on it is no conflict
    for scripts in ({1: 'at_other'}, {5: 'at_other'}):
        try:
            W.survey(pool, triggers, teleports, scripts)
        except ValueError as error:
            assert 'already has the script' in str(error)
        else:
            raise AssertionError('a trigger with another script was taken')
    try:
        W.survey(pool, {k: v for k, v in triggers.items() if v[0] != 30}, teleports, {})
    except ValueError as error:
        assert 'C' in str(error) and 'no way-out trigger' in str(error)
    else:
        raise AssertionError('a pool row with no way out was accepted')


def test_the_dbc_reader():
    records = [(7, 389, 1.5, 2.5, 3.5, 0.0, 31.0, 12.0, 26.0, 0.0), (8, 34, -1.0, 0.0, 9.0, 8.0, 0.0, 0.0, 0.0, 0.0)]
    blob = struct.pack('<4s4I', b'WDBC', len(records), 10, W.DBC_SIZE, 1) + b''.join(struct.pack(W.DBC_RECORD, *r) for r in records) + b'\0'
    with tempfile.TemporaryDirectory(prefix='rift-way-back-dbc-', dir=SCRATCH) as folder:
        path = Path(folder) / 'AreaTrigger.dbc'
        path.write_bytes(blob)
        assert W.read_triggers(path) == {7: (389, 1.5, 2.5, 3.5), 8: (34, -1.0, 0.0, 9.0)}
        path.write_bytes(blob.replace(b'WDBC', b'XXXX', 1))
        try:
            W.read_triggers(path)
        except ValueError:
            return
        raise AssertionError('a file that is no AreaTrigger.dbc was read')


# --- the committed sheet and migration ----------------------------------------------------------------------------------------------------
def sheet_rows():
    return W.read_csv(W.SHEET)


def world():
    mysql, defaults = fixture_db.mysql_and_defaults([])
    db = Database(mysql, defaults, 'acore_world')
    teleports = {int(a): (int(b), n) for a, b, n in (line.split('\t') for line in db.query('SELECT id, target_map, Name FROM areatrigger_teleport'))}
    scripts = {int(a): n for a, n in (line.split('\t') for line in db.query('SELECT entry, ScriptName FROM areatrigger_scripts'))}
    return teleports, scripts


def test_the_sheet_is_the_survey_of_the_world():
    teleports, scripts = world()
    pool = W.read_pool()
    assert len(pool) == 30 and len({p['map_id'] for p in pool}) == 29
    surveyed = W.survey(pool, W.read_triggers(DATA / 'dbc/AreaTrigger.dbc'), teleports, scripts)
    committed = sheet_rows()
    assert [{k: str(v) for k, v in r.items()} for r in surveyed] == committed
    assert len(committed) == 48 and len({r['trigger'] for r in committed}) == 48
    assert {r['map_id'] for r in committed} == {p['map_id'] for p in pool}
    # the plan's measure (4.5): every pool row has a way out 3 to 25 yards from where players land (Halls of Lightning 25.1)
    near = {}
    for r in committed:
        near[r['nearest_dungeon']] = min(near.get(r['nearest_dungeon'], 1e9), float(r['arrival_yards']))
    assert set(near) == {p['name'] for p in pool}, set(p['name'] for p in pool) - set(near)
    assert all(3.0 <= d <= 25.1 for d in near.values()), {k: v for k, v in near.items() if not 3.0 <= v <= 25.1}
    # no stock script of anybody's sits on a trigger we take
    assert not [r['trigger'] for r in committed if int(r['trigger']) in scripts], 'a way-out trigger already has a script'


def test_the_switched_off_triggers():
    """diablocraft-hcwjv: Pit of Saron's far exit (5683, the designer's find 7htlwoj0) is switched off in rifts; a switched-off trigger
    must be one the survey lists, and only the listed ones change script."""
    none = W.read_csv(W.NONE_SHEET)
    assert [(r['map_id'], r['trigger']) for r in none] == [('658', '5683')]
    rows = sheet_rows()
    sql = W.render(rows, none)
    assert re.findall(r"^\s+\((\d+), 'dc_rift_way_none'\)", sql, re.M) == ['5683']
    assert len(re.findall(r"^\s+\((\d+), 'dc_rift_way_back'\)", sql, re.M)) == len(rows) - 1
    try:
        W.render(rows, [{'trigger': '1'}])
    except ValueError as error:
        assert 'no way-out trigger' in str(error)
    else:
        raise AssertionError('a switched-off trigger the survey does not list was accepted')
    # the survey takes a trigger already bound to either of our scripts
    assert W.survey([pool_row('A', 10)], {1: (10, 5, 0, 0)}, {1: (0, 'A out')}, {1: W.NONE_SCRIPT_NAME})[0]['trigger'] == 1


def test_the_migration_is_the_sheet_and_loads():
    rows = sheet_rows()
    none = W.read_csv(W.NONE_SHEET)
    off = {r['trigger'] for r in none}
    sql = W.render(rows, none)
    assert read(UPDATES / W.NAME) == read(MODULE / 'data/generated/rift_way_back.sql') == sql
    assert re.findall(r"^\s+\((\d+), 'dc_rift_way_(?:back|none)'\)", sql, re.M) == [r['trigger'] for r in rows]
    mysql, defaults = fixture_db.mysql_and_defaults([])
    name = 'scratch_rift_way_back_%d_%d' % (os.getpid(), random.randrange(10 ** 6))

    def client(*extra, stdin=None):
        argv = [mysql, '--defaults-file=' + defaults, '--no-login-paths', '--batch', '--raw', '--skip-column-names', *extra]
        done = subprocess.run(argv, input=stdin, text=True, capture_output=True)
        assert done.returncode == 0, done.stderr
        return done.stdout

    client(stdin='DROP DATABASE IF EXISTS %s; CREATE DATABASE %s' % (name, name))
    try:
        client(name, stdin='CREATE TABLE areatrigger_scripts (entry INT UNSIGNED NOT NULL, ScriptName CHAR(64) NOT NULL, PRIMARY KEY (entry))')
        client(name, stdin="INSERT INTO areatrigger_scripts VALUES (%s, 'old'), (1, 'at_someone_elses')" % rows[0]['trigger'])
        for _ in range(2):                                                    # a re-run leaves the same rows
            client(name, stdin=sql)
            got = client(name, stdin='SELECT entry, ScriptName FROM areatrigger_scripts ORDER BY entry').splitlines()
            assert got == sorted(['%s\tdc_rift_way_%s' % (r['trigger'], 'none' if r['trigger'] in off else 'back') for r in rows]
                                 + ['1\tat_someone_elses'], key=lambda l: int(l.split('\t')[0]))
    finally:
        client(stdin='DROP DATABASE IF EXISTS %s' % name)


# --- the wiring the harness cannot reach ----------------------------------------------------------------------------------------------
def texts():
    return {'dc_rift_exit.cpp': read(RIFTS / 'dc_rift_exit.cpp')}


def check_wiring(t):
    exit_ = t['dc_rift_exit.cpp']
    on = definition(exit_, 'bool OnTrigger(Player* player, AreaTrigger const*) override')
    # outside a live rift floor the stock teleport runs
    assert re.search(r'if \(!map \|\| !live\.View\(map->GetInstanceId\(\), map->GetId\(\), here\)\)\s*return false;', on)
    assert on.index('live.View(') < on.index('EnrolledRun(player->GetGUID(), mine) && mine.id == here.id') < on.index('WayBack::Choose(') \
        < on.index('case WayBack::Way::Dead:') < on.index('HubLocation(hub)')
    assert 'WayBack::Choose(here.floor, player->IsAlive(), member, here.mode == "gr", here.state, standing)' in on
    assert 'floors = live.Floors(here.id);' in on and 'standing.push_back(floor.number)' in on
    # a refusal is handled (true) with no teleport; the hub is the hub, or the stock teleport when there is none
    refuse = on[on.index('case WayBack::Way::Dead:'):on.index('case WayBack::Way::Up:')]
    assert 'case WayBack::Way::Shut:' in refuse and 'return true;' in refuse and 'TeleportTo' not in refuse
    assert re.search(r'case WayBack::Way::Up:\s*return GoUp\(player, handler, floors, choice\);', on)
    assert re.search(r'if \(!DC::World::HubLocation\(hub\)\)\s*return false;', on) and 'moved->TeleportTo(hub)' in on
    assert 'IsInCombat' not in on                                              # a way out works in combat, as the stock one does
    up = definition(exit_, 'static bool GoUp(')
    assert up.index('ArrivalOf(target.dungeonId, arrival)') < up.index('BindToFloor(player, target)') < up.index('PlacedAt(target.instanceId)') \
        < up.index('ForcedTeleport(')
    assert 'Spot where{arrival.x, arrival.y, arrival.z, arrival.o};' in up and 'where = *exit;' in up
    assert 'moved->TeleportTo(target.mapId, where.x, where.y, where.z, where.o)' in up
    # the exit portal's spot is kept when it is placed, and not when none stands
    place = definition(exit_, 'void PlaceExit(Map* map)')
    assert re.search(r'Remember\(map->GetInstanceId\(\), entry,[^;]*,\s*spot\);', place)
    assert 'Remember(map->GetInstanceId(), 0,' in place
    assert re.search(r'return found == placed\.end\(\) \|\| !found->second\.entry\s*\?\s*std::nullopt\s*:\s*found->second\.at;', exit_)
    assert 'new WayBackScript();' in definition(exit_, 'void RegisterScripts()')
    # a switched-off trigger: handled (true, nothing happens) in a live rift floor, the stock teleport anywhere else
    none = exit_[exit_.index('class WayNoneScript'):]
    none = definition(none, 'bool OnTrigger(Player* player, AreaTrigger const*) override')
    assert 'return map && live.View(map->GetInstanceId(), map->GetId(), here);' in none
    assert 'TeleportTo' not in none and 'SendSysMessage' not in none
    assert 'new WayNoneScript();' in definition(exit_, 'void RegisterScripts()')


def test_the_wiring():
    check_wiring(texts())


# --- killed mutation runs -----------------------------------------------------------------------------------------------------------------
HEADER_MUTANTS = [
    ('the dead may use it', 'if (!alive)\n            return {Way::Dead, 0};', ''),
    ('up leads to this floor', 'return {Way::Up, floor - 1};', 'return {Way::Up, floor};'),
    ('up leads two floors', 'return {Way::Up, floor - 1};', 'return {Way::Up, floor - 2};'),
    ('an unloaded floor above is led to', 'std::find(standing.begin(), standing.end(), floor - 1) != standing.end()', 'true'),
    ('a Greater Rift never shuts', 'if (member && greater && !closed && state != "complete")\n            return {Way::Shut, 0};', ''),
    ('a dead Guardian leaves it shut', ' && state != "complete")', ')'),
    ('a Nephalem Rift shuts', 'if (member && greater &&', 'if (member &&'),
    ('a closed Greater Rift stays shut', 'member && greater && !closed &&', 'member && greater &&'),
    ('a stranger is shut in', 'if (member && greater &&', 'if (greater &&'),
    ('a stranger goes up', 'if (member && !closed && floor > 1', 'if (!closed && floor > 1'),
    ('a closed run leads up', 'member && !closed && floor > 1', 'member && floor > 1'),
    ('up is shut in a Greater Rift', 'return {Way::Up, floor - 1};', 'return {greater && state != "complete" ? Way::Shut : Way::Up, floor - 1};'),
    ('the script has another name', 'SCRIPT_NAME = "dc_rift_way_back"', 'SCRIPT_NAME = "dc_rift_way_forth"'),
    ('the switched-off script has another name', 'NONE_SCRIPT_NAME = "dc_rift_way_none"', 'NONE_SCRIPT_NAME = "dc_rift_way_back"'),
]
SOURCE_MUTANTS = [
    ('a player outside a rift is taken over', 'if (!map || !live.View(map->GetInstanceId(), map->GetId(), here))\n                        return false;',
     'if (!map)\n                        return false;'),
    ('anybody counts as a member', 'EnrolledRun(player->GetGUID(), mine) && mine.id == here.id', 'true'),
    ('the mode is not asked', 'here.mode == "gr"', 'false'),
    ('the state is not asked', 'member, here.mode == "gr", here.state, standing', 'member, here.mode == "gr", "complete", standing'),
    ('a refusal also teleports', 'handler.SendSysMessage(WayBack::Say(choice));\n                        return true;',
     'handler.SendSysMessage(WayBack::Say(choice));\n                        moved_to_hub:;'),
    ('the way is shut in combat', 'WayBack::Choose(here.floor, player->IsAlive(),', 'WayBack::Choose(here.floor, player->IsAlive() && !player->IsInCombat(),'),
    ('no hub leaves the stock teleport out', 'if (!DC::World::HubLocation(hub))\n                    return false;', 'DC::World::HubLocation(hub);'),
    ('up leads to the arrival point', 'if (std::optional<Spot> exit = PlacedAt(target.instanceId))\n                    where = *exit;', ''),
    ('up is not bound', '|| !BindToFloor(player, target))\n                {\n                    handler.SendSysMessage("That floor is no longer there.',
     ')\n                {\n                    handler.SendSysMessage("That floor is no longer there.'),
    ('the spot is not kept', '+ std::to_string(spot->z) + ", " + source,\n                 spot);', '+ std::to_string(spot->z) + ", " + source);'),
    ('the script is not registered', 'new WayBackScript();', ''),
    ('a switched-off trigger always runs the stock teleport', 'return map && live.View(map->GetInstanceId(), map->GetId(), here);',
     'return false;'),
    ('a switched-off trigger is swallowed outside a rift', 'return map && live.View(map->GetInstanceId(), map->GetId(), here);',
     'return true;'),
    ('the switched-off script is not registered', 'new WayNoneScript();', ''),
]


def mutate(text, old, new):
    pattern = re.compile(r'\s+'.join(re.escape(token) for token in old.split()))
    assert len(pattern.findall(text)) == 1, 'mutant target moved: ' + old
    return pattern.sub(lambda _: new, text)


def test_mutants_are_killed():
    header = read(HEADER)
    for what, old, new in HEADER_MUTANTS:
        mutant = mutate(header, old, new)
        rc, out, err = run_harness(mutant)
        killed = rc != 0 or 'rift way back harness: ok' not in out
        if not killed:                                                         # the name is the other check's
            rc, out, err = run_harness(mutant, 'name')
            killed = out.split() != [W.SCRIPT_NAME, W.NONE_SCRIPT_NAME]
        assert killed, 'header mutant survived: ' + what
        print('PASS mutant killed:', what)
    base = texts()
    for what, old, new in SOURCE_MUTANTS:
        t = dict(base)
        t['dc_rift_exit.cpp'] = mutate(t['dc_rift_exit.cpp'], old, new)
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

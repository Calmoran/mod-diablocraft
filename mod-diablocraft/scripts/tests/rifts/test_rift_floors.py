"""Rift floors Part F1 (diablocraft-p8m7): a run holds floors.

What runs here: the production run book (src/rifts/dc_rift_floors.h) and the production Rift (dc_rifts.h) are compiled with
tests/rift_floors/harness.cpp, together with the six public calls cut out of dc_rifts.cpp (Current, IsLiveInstance,
ScalingContext, GreaterRiftLevel, InRift, EntryPosition), against doubles for the core's Map, Player and Creature. The harness
drives a run with two floors: the calls answer for both, a destroyed floor map takes only that floor, the last takes the run,
an instance id reused on another map is not the old floor. The other F1 tests drive the rest of the production code the same way:
test_rift_keeper.py (a two-floor run closes both floors, the Keeper's countdown is the run's), test_gr_rules.py (one death count
across floors), test_gr_progress.py (the Guardian floor's sweep), test_rift_clear_time.py (a Guardian that died on floor 2),
test_rift_entry.py (a later floor's bind), test_urshi.py and test_gr_keeper_turnin.py (the run-keyed calls).

What needs the worldserver (the creation hook writing dc_rift_floor, the map hooks, hub objects) is held by source checks on the
wiring and by docs/test-diablocraft-p8m7.md on dev; no player-facing change, every run still has one floor.

DC_RIFT_FLOORS_HEADER and DC_RIFTS_SOURCE point the compile at mutated copies (mutation runs, below)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import RIFTS as RIFT_FILES, joined  # noqa: E402
import harness_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
RIFTS = MODULE / 'src/rifts'
HEADER = Path(os.environ.get('DC_RIFT_FLOORS_HEADER', RIFTS / 'dc_rift_floors.h'))
CPP = Path(os.environ.get('DC_RIFTS_SOURCE', RIFTS / 'dc_rifts.cpp'))
SOURCE = CPP.read_text(encoding='utf-8') + joined(RIFT_FILES[1:])   # dc_rifts.cpp, then the rest of the rift files
CORE = ROOT / 'azerothcore-wotlk'
SCRATCH = CORE / 'build/_agent-scratch'


def read(path):
    return Path(path).read_text(encoding='utf-8')


def definition(text, marker):
    start = text.index(marker)
    end, depth = text.index('{', start) + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def compile_and_run(header, source):
    """Builds the harness around `header` (dc_rift_floors.h) and the six calls cut from `source`; returns the run's stdout."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rift-floors-', dir=SCRATCH) as folder:
        folder = Path(folder)
        (folder / 'dc_rift_floors.h').write_text(header, encoding='utf-8')
        calls = [definition(source, marker) for marker in (
            'bool Current(Player const* player, Rift& rift)', 'bool EntryPosition(Player const* player, WorldLocation& entry)',
            'bool ScalingContext(Map const* map, unsigned& tier, unsigned& players)', 'unsigned GreaterRiftLevel(Map const* map)',
            'bool IsLiveInstance(std::uint32_t mapId, std::uint32_t instanceId)', 'bool InRift(Creature const* creature, unsigned& tier)')]
        (folder / 'calls.inc').write_text('\n'.join(calls), encoding='utf-8')
        binary = folder / 'harness'
        includes = [folder, RIFTS, CORE / 'src/common', CORE / 'src/common/Utilities', CORE / 'src/common/Debugging',
                    CORE / 'src/common/Cryptography', CORE / 'src/server/game/Entities/Object', CORE / 'src/server/shared/Packets',
                    CORE / 'src/server/shared', CORE / 'build']
        compiled = subprocess.run(['c++', '-std=c++20', '-O0', '-UNDEBUG', '-Wall', '-Wno-unused'] + [f'-I{i}' for i in includes]
                                  + [str(MODULE / 'tests/rift_floors/harness.cpp'), '-o', str(binary)], capture_output=True, text=True)
        if compiled.returncode:
            return 'COMPILE ' + compiled.stderr[-1500:]
        ran = harness_env.run([str(binary)], capture_output=True, text=True)
        return f'rc={ran.returncode} ' + ran.stdout + ran.stderr


def test_the_harness():
    out = compile_and_run(read(HEADER), SOURCE)
    assert out.startswith('rc=0') and 'rift floors harness: ok' in out, out


# --- source checks on the wiring the harness cannot reach ----------------------------------------------------------------
def test_every_lookup_goes_through_the_book():
    for path in sorted(RIFTS.glob('*.cpp')):
        text = read(path)
        for stale in (r'\blive\.find\(', r'\blive\[', r'\blive\.erase\(', r'\blive\.end\(', r'\blive\.count\('):
            assert not re.search(stale, text), f'{path.name} still reads the live map by instance: {stale}'
    internal = read(RIFTS / 'dc_rifts_internal.h')
    assert 'extern LiveRuns<Rift> live;' in internal and 'std::unordered_map<std::uint32_t, Rift>' not in internal


def test_the_floor_is_written_with_the_run():
    hook = definition(SOURCE, 'void OnBeforeCreateInstanceScript(')
    assert hook.index('INSERT INTO dc_rift ') < hook.index('INSERT INTO dc_rift_floor') < hook.index('live.Start(rift)')
    assert 'VALUES ({},1,{},{},{})' in hook      # floor 1, with the run's instance, map and dungeon
    migration = read(MODULE / 'data/sql/db-characters/updates/rifts_0011_rift_floor.sql')
    for column in ('run_id', 'floor', 'instance_id', 'map_id', 'dungeon_id', 'monster_set', 'opened_at', 'closed_at'):
        assert f'`{column}`' in migration, column
    assert 'PRIMARY KEY (`run_id`, `floor`)' in migration and 'KEY `idx_dc_rift_floor_instance` (`instance_id`)' in migration
    insert = re.search(r'INSERT INTO dc_rift_floor \(([^)]*)\)', hook).group(1).split(',')
    assert insert == ['run_id', 'floor', 'instance_id', 'map_id', 'dungeon_id'], insert
    check = re.search(r'if \(!CharacterDatabase\.Query\("SELECT COUNT\(\*\) FROM dc_rift_floor"\)\)\s*throw std::runtime_error\(\s*"[^"]*rifts_0011_rift_floor\.sql"', SOURCE)
    assert check, 'the startup check for dc_rift_floor names its migration'
    assert "UPDATE dc_rift_floor SET closed_at=NOW() WHERE closed_at IS NULL" in SOURCE       # a restart ends every floor
    assert 'CREATE TABLE IF NOT EXISTS `dc_rift_floor`' in migration and 'ALTER' not in migration


def test_a_destroyed_map_closes_its_floor_only():
    destroy = definition(SOURCE, 'void OnDestroyMap(Map* map) override')
    assert 'live.Remove(map->GetInstanceId(), map->GetId());' in destroy
    assert 'live.FloorCount(floor.runId) == 1' in destroy                       # only the run's last floor closes the run
    assert destroy.index('if (lastFloor)') < destroy.index('RemoveRunQuests(closing)') < destroy.index('live.Remove(')
    assert 'run->state = "closed"' in destroy and destroy.index('lastFloor = ') < destroy.index('run->state = "closed"')
    assert 'UPDATE dc_rift_floor SET closed_at=NOW() WHERE run_id={} AND floor={}' in destroy
    assert 'TownPortal::CloseInstance(map->GetInstanceId())' in destroy         # the floor's portals, not the run's
    assert 'ClosePortals(' not in destroy
    work = definition(SOURCE, 'void EraseInstanceWork(std::uint32_t instanceId)')
    assert 'pendingCloses' not in work and 'entrances' not in work and 'openings' not in work   # run work outlives one floor


def test_the_closure_reaches_every_floor():
    queue = definition(SOURCE, 'void QueueClose(Rift rift)')
    assert 'live.Views(rift.id)' in queue and 'closingRifts.insert(closingRifts.end(), floors.begin(), floors.end())' in queue
    ports = definition(SOURCE, 'void ClosePortals(std::uint64_t runId)\n    {')
    assert 'live.Floors(runId)' in ports and 'TownPortal::CloseInstance(floor.instanceId)' in ports and 'RemoveEntrance(runId)' in ports
    advance = definition(SOURCE, 'void AdvanceClosure(Map* map)')
    assert 'live.View(map->GetInstanceId(), map->GetId(), seen)' in advance and 'pendingCloses.find(runId)' in advance
    assert 'Announce(announced,' in advance                                      # the call-out reaches every floor
    announce = definition(SOURCE, 'void Announce(Rift const& rift, std::string const& text)')
    assert 'live.Floors(rift.id)' in announce and 'sMapMgr->FindMap(floor.mapId, floor.instanceId)' in announce
    rescale = definition(SOURCE, 'void RescaleForHeadcount(std::uint64_t runId)')
    assert 'live.Floors(runId)' in rescale and 'DC::Difficulty::RequestRefresh(map)' in rescale


def test_run_state_is_keyed_by_the_run():
    assert 'std::unordered_map<std::uint64_t, PendingClose> pendingCloses;' in SOURCE
    assert 'std::unordered_map<std::uint64_t, Entrance> entrances;' in SOURCE
    assert 'std::unordered_map<ObjectGuid, std::uint64_t> playerRun;' in SOURCE
    header = read(RIFTS / 'dc_rifts.h')
    for declaration in ('void JoinMembership(std::uint64_t runId, ObjectGuid player);',
                        'void LeaveMembership(std::uint64_t runId, ObjectGuid player);',
                        'void ClearMembership(std::uint64_t runId);', 'explicit HubObjectClaim(std::uint64_t runId);'):
        assert declaration in header, declaration
    assert 'unsigned floor = 1;' in header and 'std::uint32_t guardianInstance = 0;' in header
    internal = read(RIFTS / 'dc_rifts_internal.h')
    for declaration in ('void RescaleForHeadcount(std::uint64_t runId);', 'std::string UrshiBlocksClose(std::uint64_t runId);',
                        'unsigned GreaterRiftDeaths(std::uint64_t runId, std::uint32_t character);',
                        'void CompleteRunQuests(std::uint64_t runId);'):
        assert declaration in internal, declaration
    # the Guardian floor is recorded when it spawns, and only that floor's tick sweeps (rift floors 6.9)
    spawn = definition(read(MODULE / 'src/monsters/dc_monster_ai.cpp'), 'void SpawnGuardian(Player* killer, Rift& rift)')
    assert 'rift.guardianInstance = map->GetInstanceId();' in spawn and spawn.index('guardianInstance') < spawn.index('live.Store(rift)')


# --- killed mutation runs -----------------------------------------------------------------------------------------------
HEADER_MUTANTS = [
    ('a destroyed floor takes the whole run', '        if (!entry.floors.empty())\n            return Gone::Floor;', '        if (false)\n            return Gone::Floor;'),
    ('the map is not a guard', '(!mapId || floor.mapId == mapId)', '(true)'),
    ('a view keeps floor 1\'s instance', '            view.instanceId = floor.instanceId;\n', ''),
    ('a view keeps floor 1\'s map', '            view.mapId = floor.mapId;\n', ''),
    ('a view keeps floor 1\'s dungeon', '            view.dungeonId = floor.dungeonId;\n', ''),
    ('a view has no floor number', '            view.floor = floor.number;\n', ''),
    ('a write-back from a floor moves the run\'s row', '            run->instanceId = instanceId;\n', ''),
    ('floor numbers are reused', 'unsigned const number = ++entry.highest;', 'unsigned const number = entry.floors.size() + 1;'),
    ('a removed floor stays in the index', '            Unindex(gone);\n', ''),
]
SOURCE_MUTANTS = [
    ('ScalingContext asks the run id, not the floor', 'Rift const* run = live.FindByInstance(map->GetInstanceId(), map->GetId());\n        if (!run)\n            return false;\n        tier',
     'Rift const* run = live.Find(map->GetInstanceId());\n        if (!run)\n            return false;\n        tier'),
    ('IsLiveInstance ignores the map', 'live.FindByInstance(instanceId, mapId)', 'live.FindByInstance(instanceId, 0)'),
    ('EntryPosition answers floor 1', 'if (!Current(player, rift))\n            return false;\n        std::lock_guard<std::mutex> lock(dataMutex);',
     'if (!Current(player, rift))\n            return false;\n        rift.dungeonId = live.Find(rift.id)->dungeonId;\n        std::lock_guard<std::mutex> lock(dataMutex);'),
    ('Current hands back the run\'s row, not the floor', 'live.View(player->GetMap()->GetInstanceId(), 0, seen)', 'live.View(player->GetMap()->GetInstanceId(), 0, seen) && (seen = *live.Find(seen.id), true)'),
]


def mutate(text, old, new):
    pattern = re.compile(r'\s+'.join(re.escape(token) for token in old.split()))
    assert len(pattern.findall(text)) == 1, 'mutant target moved: ' + old
    return pattern.sub(lambda _: new, text)


def test_mutants_are_killed():
    header, source = read(HEADER), SOURCE
    for what, old, new in HEADER_MUTANTS:
        out = compile_and_run(mutate(header, old, new), source)
        assert not (out.startswith('rc=0') and 'ok' in out), 'header mutant survived: ' + what
        print('PASS mutant killed:', what)
    for what, old, new in SOURCE_MUTANTS:
        out = compile_and_run(header, mutate(source, old, new))
        assert not (out.startswith('rc=0') and 'ok' in out), 'source mutant survived: ' + what
        print('PASS mutant killed:', what)


if __name__ == '__main__':
    shutil.which('c++') or sys.exit('c++ is not on PATH')
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('PASS', name)

"""Core patch 0022 (the instance share hook, bounties R0 diablocraft-dm9vg.7).

The four files the patch touches are taken from the core's git at the pinned commit (core-commit.txt) and every numbered
patch in core-patches/ is applied to them in scratch, in number order, the way the core is built. The view does not read
the core's working tree, so a later patch that lands hunks beside 0022's (0025, 0026) cannot make 0022 look unapplied.
The check reads the patched InstanceMap::CannotEnter and the hook's three declarations: the module's answer is asked before the player cap, so its cap is the one held; a shared
instance skips the one-group loop and nothing else (GMs, the cap, raids in combat, LFG and Map::CannotEnter stay); the
default is stock (false). Then it proves it can fail: the pristine pin and the stack up to 0021 (no 0022 yet) are
refused, and so is each single-rule mutant of the patched text.

TORMENT_CORE overrides the core repo the pinned files are read from (default: this repo's azerothcore-wotlk). Nothing in
the core is written.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
CORE = Path(os.environ.get('TORMENT_CORE') or REPO / 'azerothcore-wotlk')
PIN = (REPO / 'core-commit.txt').read_text(encoding='utf-8').split()[0]
STACK = sorted((REPO / 'core-patches').glob('[0-9][0-9][0-9][0-9]-*.patch'))
PATCH = REPO / 'core-patches/0022-instance-share-hook.patch'
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/instance-share-hook'
MAP = 'src/server/game/Maps/Map.cpp'
GLOBAL_H = 'src/server/game/Scripting/ScriptDefines/GlobalScript.h'
GLOBAL_CPP = 'src/server/game/Scripting/ScriptDefines/GlobalScript.cpp'
MGR_H = 'src/server/game/Scripting/ScriptMgr.h'
FILES = (MAP, GLOBAL_H, GLOBAL_CPP, MGR_H)


def pristine(path):
    shot = subprocess.run(['git', '-C', str(CORE), 'show', f'{PIN}:{path}'], capture_output=True)
    assert shot.returncode == 0, f'{path} at {PIN} is not in the core repo:\n' + shot.stderr.decode()
    return shot.stdout


def replay(stack):
    """{path: text} of the four files at the pin with the patches of `stack` applied in the order given.

    The scratch tree is its own git repo so that --include matches the patch's paths; a patch that names one of the
    four files must change it, which catches a filter that matched nothing.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    try:
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
        for path in FILES:
            (tree / path).parent.mkdir(parents=True, exist_ok=True)
            (tree / path).write_bytes(pristine(path))
        include = [f'--include={path}' for path in FILES]
        for patch in stack:
            before = {path: (tree / path).read_bytes() for path in FILES}
            done = subprocess.run(['git', 'apply', *include, str(patch)], cwd=tree, capture_output=True, text=True)
            assert done.returncode == 0, f'{patch.name} does not apply on the patches before it:\n' + done.stderr
            named = set(re.findall(r'^\+\+\+ b/(\S+)', patch.read_text(encoding='utf-8'), re.M)) & set(FILES)
            for path in named:
                assert (tree / path).read_bytes() != before[path], f'{patch.name} named {path} and left it as it was'
        return {path: (tree / path).read_text(encoding='utf-8') for path in FILES}
    finally:
        shutil.rmtree(tree)


def patched():
    """{path: text} of the four files with every committed patch applied in number order."""
    assert PATCH in STACK, '0022 is not among the numbered patches'
    return replay(STACK)


def function(source, marker):
    start = source.index(marker)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def problems(files):
    """What is wrong with the patched text; empty when the hook is right."""
    out = []
    body = function(files[MAP], 'Map::EnterState InstanceMap::CannotEnter(')
    ask = body.find('bool const shared = sScriptMgr->IsInstanceShared(GetId(), GetInstanceId(), maxPlayers);')
    cap_read = body.find('uint32 maxPlayers = GetMaxPlayers();')
    cap_check = body.find('if (GetPlayersCountExceptGMs() >= (loginCheck ? maxPlayers + 1 : maxPlayers))')
    if not 0 <= cap_read < ask < cap_check:
        out.append('the module is not asked between reading the map cap and holding the player to it')
    if body.count('IsInstanceShared') != 1:
        out.append('the hook is asked more than once')
    loop = body.find('PlayerList const& playerList = GetPlayers();')
    if 'if (!shared && !playerList.IsEmpty())' not in body[loop:]:
        out.append('a shared instance still runs the one-group loop')
    if body.count('shared') != 2:
        out.append('the share answer reaches more than the one-group loop')
    for stock in ('if (player->IsGameMaster())', 'IsEncounterInProgress()', 'group->isLFGGroup()',
                  'return Map::CannotEnter(player, loginCheck);', 'CANNOT_ENTER_INSTANCE_BIND_MISMATCH'):
        if stock not in body:
            out.append('a stock rule is gone: ' + stock)
    declared = re.search(r'virtual bool IsInstanceShared\(uint32 /\*mapId\*/, uint32 /\*instanceId\*/, uint32& /\*maxPlayers\*/\) \{ return (\w+); \}',
                         files[GLOBAL_H])
    if not declared or declared.group(1) != 'false':
        out.append('the default answer is not stock (false)')
    enum = files[GLOBAL_H][files[GLOBAL_H].index('enum GlobalHook'):files[GLOBAL_H].index('GLOBALHOOK_END')]
    if 'GLOBALHOOK_IS_INSTANCE_SHARED,' not in enum:
        out.append('no hook id before GLOBALHOOK_END')
    if ('CALL_ENABLED_BOOLEAN_HOOKS_WITH_DEFAULT_FALSE(GlobalScript, GLOBALHOOK_IS_INSTANCE_SHARED, '
            'script->IsInstanceShared(mapId, instanceId, maxPlayers));') not in files[GLOBAL_CPP]:
        out.append('the dispatcher is not first-true-wins with a false default')
    if 'bool IsInstanceShared(uint32 mapId, uint32 instanceId, uint32& maxPlayers);' not in files[MGR_H]:
        out.append('ScriptMgr does not declare the hook')
    return out


MUTANTS = {
    'loop unguarded': (MAP, 'if (!shared && !playerList.IsEmpty())', 'if (!playerList.IsEmpty())'),
    'asked after the cap': (MAP, '''    uint32 maxPlayers = GetMaxPlayers();
    // a module may let strangers share this instance, under its own cap
    bool const shared = sScriptMgr->IsInstanceShared(GetId(), GetInstanceId(), maxPlayers);
    if (GetPlayersCountExceptGMs() >= (loginCheck ? maxPlayers + 1 : maxPlayers))''',
                            '''    uint32 maxPlayers = GetMaxPlayers();
    if (GetPlayersCountExceptGMs() >= (loginCheck ? maxPlayers + 1 : maxPlayers))
    // a module may let strangers share this instance, under its own cap
    bool const shared = sScriptMgr->IsInstanceShared(GetId(), GetInstanceId(), maxPlayers);'''),
    'GMs skip lost': (MAP, '''    // allow GM's to enter
    if (player->IsGameMaster())''', '''    // allow GM's to enter
    if (false)'''),
    'default true': (GLOBAL_H, '/*maxPlayers*/) { return false; }', '/*maxPlayers*/) { return true; }'),
    'any-false dispatcher': (GLOBAL_CPP, 'CALL_ENABLED_BOOLEAN_HOOKS_WITH_DEFAULT_FALSE(GlobalScript, GLOBALHOOK_IS_INSTANCE_SHARED',
                             'CALL_ENABLED_BOOLEAN_HOOKS(GlobalScript, GLOBALHOOK_IS_INSTANCE_SHARED'),
    'no hook id': (GLOBAL_H, '    GLOBALHOOK_IS_INSTANCE_SHARED,\n', ''),
}


class InstanceShareHook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = patched()

    def test_patched_core_is_right(self):
        self.assertEqual(problems(self.files), [])

    def test_unpatched_core_is_refused(self):
        stock = {path: pristine(path).decode('utf-8') for path in FILES}
        self.assertNotEqual(problems(stock), [])

    def test_stack_without_0022_is_refused(self):
        before = replay(STACK[:STACK.index(PATCH)])
        self.assertNotIn('IsInstanceShared', before[MAP])
        self.assertNotEqual(problems(before), [])

    def test_patches_after_0022_leave_the_hook_whole(self):
        self.assertGreater(len(STACK) - STACK.index(PATCH), 1, 'no patch follows 0022 to test against')
        self.assertEqual(problems(replay(STACK[:STACK.index(PATCH) + 1])), [])

    def test_every_mutant_is_refused(self):
        for name, (path, old, new) in MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertEqual(self.files[path].count(old), 1, name)
                self.assertNotEqual(problems({**self.files, path: self.files[path].replace(old, new)}), [], name)


if __name__ == '__main__':
    unittest.main()

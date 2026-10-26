"""Core patch 0026 (instance grids on demand, the rift open hang diablocraft-ho3ww).

The four files the patch touches are taken from the core's git at the pinned commit (core-commit.txt) and every numbered
patch in core-patches/ is applied to them in scratch, in number order, the way the core is built. The view does not read
the core's working tree, so a patch that lands hunks beside 0026's cannot make 0026 look unapplied.

The check reads Map::OnCreateMap and the hook's declarations: a
new instance skips Map::LoadAllGrids only when a module answers true, the module hook still runs after it, the open world
(instance id 0) never preloads, and the default is stock (false, every grid of an instance loads). Then it proves it can
fail: each single-rule mutant of the patched text must be refused.

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
PATCH = REPO / 'core-patches/0026-instance-grids-on-demand.patch'
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/instance-grids-on-demand'
MAP = 'src/server/game/Maps/Map.cpp'
ALLMAP_H = 'src/server/game/Scripting/ScriptDefines/AllMapScript.h'
ALLMAP_CPP = 'src/server/game/Scripting/ScriptDefines/AllMapScript.cpp'
MGR_H = 'src/server/game/Scripting/ScriptMgr.h'
FILES = (MAP, ALLMAP_H, ALLMAP_CPP, MGR_H)
ASK = '''    if (GetInstanceId() && !sScriptMgr->IsInstanceLoadedOnDemand(this))
        LoadAllGrids();
'''


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
    assert PATCH in STACK, '0026 is not among the numbered patches'
    return replay(STACK)


def problems(files):
    """What is wrong with the patched text; empty when the hook is right."""
    out = []
    source = files[MAP]
    start = source.index('void Map::OnCreateMap()')
    body = source[start:source.index('\n}\n', start)]
    if ASK not in body:
        out.append('the full preload is not asked of the module, for instances only')
    if source.count('IsInstanceLoadedOnDemand') != 1:
        out.append('the hook is asked other than once')
    if 'sScriptMgr->OnCreateMap(this);' not in body or body.find('LoadAllGrids') > body.find('OnCreateMap(this)'):
        out.append("the module's OnCreateMap no longer runs after the preload decision")
    declared = re.search(r'virtual bool IsInstanceLoadedOnDemand\(Map\* /\*map\*/\) \{ return (\w+); \}', files[ALLMAP_H])
    if not declared or declared.group(1) != 'false':
        out.append('the default answer is not stock (false)')
    enum = files[ALLMAP_H][files[ALLMAP_H].index('enum AllMapHook'):files[ALLMAP_H].index('ALLMAPHOOK_END')]
    if 'ALLMAPHOOK_IS_INSTANCE_LOADED_ON_DEMAND,' not in enum:
        out.append('no hook id before ALLMAPHOOK_END')
    if ('CALL_ENABLED_BOOLEAN_HOOKS_WITH_DEFAULT_FALSE(AllMapScript, ALLMAPHOOK_IS_INSTANCE_LOADED_ON_DEMAND, '
            'script->IsInstanceLoadedOnDemand(map));') not in files[ALLMAP_CPP]:
        out.append('the dispatcher is not first-true-wins with a false default')
    if 'bool IsInstanceLoadedOnDemand(Map* map);' not in files[MGR_H]:
        out.append('ScriptMgr does not declare the hook')
    return out


MUTANTS = {
    'every map asked, the open world preloads': (MAP, 'if (GetInstanceId() && !sScriptMgr->IsInstanceLoadedOnDemand(this))',
                                                 'if (!sScriptMgr->IsInstanceLoadedOnDemand(this))'),
    'the answer inverted': (MAP, '&& !sScriptMgr->IsInstanceLoadedOnDemand(this)', '&& sScriptMgr->IsInstanceLoadedOnDemand(this)'),
    'never preloads': (MAP, ASK, '''    if (GetInstanceId() && !sScriptMgr->IsInstanceLoadedOnDemand(this))
        ;
'''),
    'the module hook before the preload': (MAP, ASK + '''
    sScriptMgr->OnCreateMap(this);
''', '''    sScriptMgr->OnCreateMap(this);
''' + ASK),
    'default true': (ALLMAP_H, '/*map*/) { return false; }', '/*map*/) { return true; }'),
    'any-false dispatcher': (ALLMAP_CPP, 'CALL_ENABLED_BOOLEAN_HOOKS_WITH_DEFAULT_FALSE(AllMapScript, ALLMAPHOOK_IS_INSTANCE_LOADED_ON_DEMAND',
                             'CALL_ENABLED_BOOLEAN_HOOKS(AllMapScript, ALLMAPHOOK_IS_INSTANCE_LOADED_ON_DEMAND'),
    'no hook id': (ALLMAP_H, '    ALLMAPHOOK_IS_INSTANCE_LOADED_ON_DEMAND,\n', ''),
    'no declaration': (MGR_H, '    bool IsInstanceLoadedOnDemand(Map* map);\n', ''),
}


class InstanceGridsOnDemand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = patched()

    def test_patched_core_is_right(self):
        self.assertEqual(problems(self.files), [])

    def test_unpatched_core_is_refused(self):
        stock = {path: pristine(path).decode('utf-8') for path in FILES}
        self.assertNotEqual(problems(stock), [])

    def test_stack_without_0026_is_refused(self):
        before = replay(STACK[:STACK.index(PATCH)])
        self.assertNotIn('IsInstanceLoadedOnDemand', before[MAP])
        self.assertNotEqual(problems(before), [])

    def test_every_mutant_is_refused(self):
        for name, (path, old, new) in MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertEqual(self.files[path].count(old), 1, name)
                self.assertNotEqual(problems({**self.files, path: self.files[path].replace(old, new)}), [], name)


if __name__ == '__main__':
    unittest.main()

"""Core patch 0025 (the addon whisper drop name, the Lua error drop diablocraft-g74u4).

The four files the patch touches are taken from the core's git at the pinned commit (core-commit.txt) and every numbered
patch in core-patches/ is applied to them in scratch, in number order, the way the core is built. The view does not read
the core's working tree, so a later patch that lands hunks beside 0025's (0026) cannot make 0025 look unapplied.

The check reads the patched whisper case and the hook's three
declarations: the module is asked only for an addon whisper, after the module chat hook has seen the message and the
name is normalized, and before the target is looked up; a true answer returns with no notice; the default is stock
(false). Then it proves it can fail: each single-rule mutant of the patched text must be refused.

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
PATCH = REPO / 'core-patches/0025-addon-whisper-drop-name.patch'
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/addon-whisper-drop'
CHAT = 'src/server/game/Handlers/ChatHandler.cpp'
GLOBAL_H = 'src/server/game/Scripting/ScriptDefines/GlobalScript.h'
GLOBAL_CPP = 'src/server/game/Scripting/ScriptDefines/GlobalScript.cpp'
MGR_H = 'src/server/game/Scripting/ScriptMgr.h'
FILES = (CHAT, GLOBAL_H, GLOBAL_CPP, MGR_H)
ASK = '''                if (lang == LANG_ADDON && sScriptMgr->IsAddonWhisperDrop(to))
                    return;
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
    assert PATCH in STACK, '0025 is not among the numbered patches'
    return replay(STACK)


def problems(files):
    """What is wrong with the patched text; empty when the hook is right."""
    out = []
    chat = files[CHAT]
    start = chat.index('void WorldSession::HandleMessagechatOpcode(')
    whisper = chat.index('case CHAT_MSG_WHISPER:', chat.index('sScriptMgr->OnPlayerBeforeSendChatMessage(', start))
    case = chat[whisper:chat.index('case CHAT_MSG_PARTY', whisper)]
    if chat.count('IsAddonWhisperDrop') != 1:
        out.append('the hook is asked other than once')
    if ASK not in case:
        out.append('no addon-only ask that returns quietly in the whisper case')
    normalized = case.find('if (!normalizePlayerName(to))')
    ask = case.find('IsAddonWhisperDrop')
    lookup = case.find('ObjectAccessor::FindPlayerByName(to, false)')
    if not 0 <= normalized < ask < lookup:
        out.append('the module is not asked between normalizing the name and looking it up')
    for stock in ('SendPlayerNotFoundNotice(to);', 'GetPlayer()->Whisper(msg, Language(lang), receiver);'):
        if stock not in case:
            out.append('a stock rule is gone: ' + stock)
    declared = re.search(r'virtual bool IsAddonWhisperDrop\(std::string const& /\*to\*/\) \{ return (\w+); \}', files[GLOBAL_H])
    if not declared or declared.group(1) != 'false':
        out.append('the default answer is not stock (false)')
    enum = files[GLOBAL_H][files[GLOBAL_H].index('enum GlobalHook'):files[GLOBAL_H].index('GLOBALHOOK_END')]
    if 'GLOBALHOOK_IS_ADDON_WHISPER_DROP,' not in enum:
        out.append('no hook id before GLOBALHOOK_END')
    if ('CALL_ENABLED_BOOLEAN_HOOKS_WITH_DEFAULT_FALSE(GlobalScript, GLOBALHOOK_IS_ADDON_WHISPER_DROP, '
            'script->IsAddonWhisperDrop(to));') not in files[GLOBAL_CPP]:
        out.append('the dispatcher is not first-true-wins with a false default')
    if 'bool IsAddonWhisperDrop(std::string const& to);' not in files[MGR_H]:
        out.append('ScriptMgr does not declare the hook')
    return out


MUTANTS = {
    'every language': (CHAT, 'if (lang == LANG_ADDON && sScriptMgr->IsAddonWhisperDrop(to))',
                       'if (sScriptMgr->IsAddonWhisperDrop(to))'),
    'still a notice': (CHAT, ASK, '''                if (lang == LANG_ADDON && sScriptMgr->IsAddonWhisperDrop(to))
                    SendPlayerNotFoundNotice(to);
'''),
    'asked after the lookup': (CHAT, ASK + '''
                Player* receiver = ObjectAccessor::FindPlayerByName(to, false);
''', '''                Player* receiver = ObjectAccessor::FindPlayerByName(to, false);
''' + ASK),
    'default true': (GLOBAL_H, '/*to*/) { return false; }', '/*to*/) { return true; }'),
    'any-false dispatcher': (GLOBAL_CPP, 'CALL_ENABLED_BOOLEAN_HOOKS_WITH_DEFAULT_FALSE(GlobalScript, GLOBALHOOK_IS_ADDON_WHISPER_DROP',
                             'CALL_ENABLED_BOOLEAN_HOOKS(GlobalScript, GLOBALHOOK_IS_ADDON_WHISPER_DROP'),
    'no hook id': (GLOBAL_H, '    GLOBALHOOK_IS_ADDON_WHISPER_DROP,\n', ''),
    'no declaration': (MGR_H, '    bool IsAddonWhisperDrop(std::string const& to);\n', ''),
}


class AddonWhisperDrop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = patched()

    def test_patched_core_is_right(self):
        self.assertEqual(problems(self.files), [])

    def test_unpatched_core_is_refused(self):
        stock = {path: pristine(path).decode('utf-8') for path in FILES}
        self.assertNotEqual(problems(stock), [])

    def test_stack_without_0025_is_refused(self):
        before = replay(STACK[:STACK.index(PATCH)])
        self.assertNotIn('IsAddonWhisperDrop', before[CHAT])
        self.assertNotEqual(problems(before), [])

    def test_patches_after_0025_leave_the_hook_whole(self):
        self.assertGreater(len(STACK) - STACK.index(PATCH), 1, 'no patch follows 0025 to test against')
        self.assertEqual(problems(replay(STACK[:STACK.index(PATCH) + 1])), [])

    def test_every_mutant_is_refused(self):
        for name, (path, old, new) in MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertEqual(self.files[path].count(old), 1, name)
                self.assertNotEqual(problems({**self.files, path: self.files[path].replace(old, new)}), [], name)


if __name__ == '__main__':
    unittest.main()

"""Core patch 0031 (the Titan's Grip hook, Heavenly Strength's grip: a two-handed weapon in the main hand with a shield).

The five files the patch touches are taken from the core's git at the pinned commit (core-commit.txt) and every numbered
patch in core-patches/ is applied to them in scratch, in number order, the way the core is built. The view does not read
the core's working tree, so it cannot be fooled by a core the PM has or has not patched yet.

The check reads the patched text: Player::CanTitanGrip() is the player's own flag, then (only when the flag is not set) the
module's answer, whose default is false; the dispatcher is first-true-wins with a false default; the hook has an id before
PLAYERHOOK_END and a ScriptMgr declaration; and the stock rules that read CanTitanGrip() are all still there (IsTwoHandUsed, the
off-hand auto-unequip, the equip checks that need dual wield), so a class that is not told yes keeps the stock rules and a
class with no dual wield still cannot put a two-hander in the off hand. Then it proves it can fail: each single-rule mutant of
the patched text must be refused.

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
PATCH = REPO / 'core-patches/0031-titan-grip-hook.patch'
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/titan-grip-hook'
PLAYER_H = 'src/server/game/Entities/Player/Player.h'
PLAYER_CPP = 'src/server/game/Entities/Player/Player.cpp'
SCRIPT_H = 'src/server/game/Scripting/ScriptDefines/PlayerScript.h'
SCRIPT_CPP = 'src/server/game/Scripting/ScriptDefines/PlayerScript.cpp'
MGR_H = 'src/server/game/Scripting/ScriptMgr.h'
FILES = (PLAYER_H, PLAYER_CPP, SCRIPT_H, SCRIPT_CPP, MGR_H)
BODY = '''bool Player::CanTitanGrip() const
{
    return m_canTitanGrip || sScriptMgr->OnPlayerCanTitanGrip(this);
}
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
    """{path: text} of the five files with every committed patch applied in number order."""
    assert PATCH in STACK, '0031 is not among the numbered patches'
    return replay(STACK)


def problems(files):
    """What is wrong with the patched text; empty when the hook is right."""
    out = []
    cpp = files[PLAYER_CPP]
    if cpp.count(BODY) != 1:
        out.append('CanTitanGrip is not the flag, then the module (flag first, module only when it is not set)')
    if cpp.count('OnPlayerCanTitanGrip') != 1:
        out.append('the hook is asked other than once')
    if 'void Player::SetCanTitanGrip(bool value)\n{\n    m_canTitanGrip = value;\n}' not in cpp:
        out.append('the talent flag setter changed')
    if '[[nodiscard]] bool CanTitanGrip() const;' not in files[PLAYER_H] or 'bool CanTitanGrip() const {' in files[PLAYER_H]:
        out.append('Player.h still defines CanTitanGrip inline')
    if 'return mainItem && mainItem->GetTemplate()->InventoryType == INVTYPE_2HWEAPON && !CanTitanGrip();' not in files[PLAYER_H]:
        out.append('IsTwoHandUsed no longer follows CanTitanGrip')
    declared = re.search(r'virtual bool OnPlayerCanTitanGrip\(Player const\* /\*player\*/\) \{ return (\w+); \}', files[SCRIPT_H])
    if not declared or declared.group(1) != 'false':
        out.append('the default answer is not stock (false)')
    enum = files[SCRIPT_H][files[SCRIPT_H].index('enum PlayerHook'):files[SCRIPT_H].index('PLAYERHOOK_END')]
    if 'PLAYERHOOK_CAN_TITAN_GRIP,' not in enum:
        out.append('no hook id before PLAYERHOOK_END')
    if ('CALL_ENABLED_BOOLEAN_HOOKS_WITH_DEFAULT_FALSE(PlayerScript, PLAYERHOOK_CAN_TITAN_GRIP, '
            'script->OnPlayerCanTitanGrip(player));') not in files[SCRIPT_CPP]:
        out.append('the dispatcher is not first-true-wins with a false default')
    if 'bool OnPlayerCanTitanGrip(Player const* player);' not in files[MGR_H]:
        out.append('ScriptMgr does not declare the hook')
    return out


MUTANTS = {
    'module first': (PLAYER_CPP, 'return m_canTitanGrip || sScriptMgr->OnPlayerCanTitanGrip(this);',
                     'return sScriptMgr->OnPlayerCanTitanGrip(this) || m_canTitanGrip;'),
    'module only': (PLAYER_CPP, 'return m_canTitanGrip || sScriptMgr->OnPlayerCanTitanGrip(this);',
                    'return sScriptMgr->OnPlayerCanTitanGrip(this);'),
    'talent only': (PLAYER_CPP, 'return m_canTitanGrip || sScriptMgr->OnPlayerCanTitanGrip(this);', 'return m_canTitanGrip;'),
    'inline again': (PLAYER_H, '[[nodiscard]] bool CanTitanGrip() const;', '[[nodiscard]] bool CanTitanGrip() const { return m_canTitanGrip; }'),
    'default true': (SCRIPT_H, 'OnPlayerCanTitanGrip(Player const* /*player*/) { return false; }',
                     'OnPlayerCanTitanGrip(Player const* /*player*/) { return true; }'),
    'any-false dispatcher': (SCRIPT_CPP, 'CALL_ENABLED_BOOLEAN_HOOKS_WITH_DEFAULT_FALSE(PlayerScript, PLAYERHOOK_CAN_TITAN_GRIP',
                             'CALL_ENABLED_BOOLEAN_HOOKS(PlayerScript, PLAYERHOOK_CAN_TITAN_GRIP'),
    'no hook id': (SCRIPT_H, '    PLAYERHOOK_CAN_TITAN_GRIP,\n', ''),
    'no declaration': (MGR_H, '    bool OnPlayerCanTitanGrip(Player const* player);\n', ''),
    'two-hander ignores the grip': (PLAYER_H, '&& !CanTitanGrip();', ';'),
}


class TitanGripHook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = patched()

    def test_patched_core_is_right(self):
        self.assertEqual(problems(self.files), [])

    def test_unpatched_core_is_refused(self):
        stock = {path: pristine(path).decode('utf-8') for path in FILES}
        self.assertNotEqual(problems(stock), [])

    def test_stack_without_0031_is_refused(self):
        before = replay(STACK[:STACK.index(PATCH)])
        self.assertNotIn('OnPlayerCanTitanGrip', before[PLAYER_CPP])
        self.assertNotEqual(problems(before), [])

    def test_the_stock_rules_that_read_the_grip_are_still_there(self):
        cpp = self.files[PLAYER_CPP]
        self.assertIn('if (!force && (CanTitanGrip() || (offItem->GetTemplate()->InventoryType != INVTYPE_2HWEAPON && !IsTwoHandUsed())))', cpp)
        # the two-hander in the off hand still needs dual wield (the Crusader has none)
        storage = pristine('src/server/game/Entities/Player/PlayerStorage.cpp').decode('utf-8')
        self.assertIn('if (!CanDualWield() || !CanTitanGrip())', storage)
        self.assertIn('if (CanDualWield() && CanTitanGrip() && proto->SubClass != ITEM_SUBCLASS_WEAPON_POLEARM', storage)

    def test_every_mutant_is_refused(self):
        for name, (path, old, new) in MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertEqual(self.files[path].count(old), 1, name)
                self.assertNotEqual(problems({**self.files, path: self.files[path].replace(old, new)}), [], name)


if __name__ == '__main__':
    unittest.main()

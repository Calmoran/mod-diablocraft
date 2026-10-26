"""Core patch 0024 (the class limit, Monk part 1b diablocraft-5261j): class id 12 is valid in the core.

The three files the patch edits (SharedDefines.h, Player.cpp, StatSystem.cpp) are copied out of the core into scratch and
the patch is applied there (when the core already carries it, the copies are checked as they are). The check reads the
patched text: MAX_CLASSES holds ids 0..14, CLASSMASK_ALL_PLAYABLE holds the ten stock bits plus 11..13, and each of the
six per-class tables indexed [class - 1] has an explicit id-12 entry equal to the Warrior's (the Monk's parent). The
header's own class macros and the six tables are compiled and run: the Monk's slot is nonzero where the diminishing
formulas divide by cap * k (a zero there is 0/0 = NaN in the miss chance of every attack at a Monk), and ids 13 and 14
stay empty until their classes land. Then it proves it can fail: each single-rule mutant of the patched text is refused.

TORMENT_CORE overrides the core (default: this repo's azerothcore-wotlk). Nothing in the core is written.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
CORE = Path(os.environ.get('TORMENT_CORE') or REPO / 'azerothcore-wotlk')
PATCH = REPO / 'core-patches/0024-class-limit-monk.patch'
NECRO = REPO / 'core-patches/0030-class-limit-necromancer.patch'  # edits 0024's lines; this test judges 0024 alone
WITCH = REPO / 'core-patches/0032-class-limit-witch-doctor.patch'  # edits 0030's lines, so it comes out first
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/class-limit-test'
sys.path.insert(0, str(REPO / 'mod-diablocraft/scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

DEFS = 'src/server/shared/SharedDefines.h'
PLAYER = 'src/server/game/Entities/Player/Player.cpp'
STAT = 'src/server/game/Entities/Unit/StatSystem.cpp'
FILES = (DEFS, PLAYER, STAT)
# (file, array name)
TABLES = ((PLAYER, 'dodge_base'), (PLAYER, 'crit_to_dodge'), (STAT, 'm_diminishing_k'), (STAT, 'miss_cap'),
          (STAT, 'parry_cap'), (STAT, 'dodge_cap'))
MONK = 11  # [class - 1] for id 12


def patched(reverse=False):
    """{path: text} of the three files with 0024 applied (or, `reverse`, without it)."""
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    try:
        for name in FILES:
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(CORE / name, tree / name)
        for later in (WITCH, NECRO):
            if subprocess.run(['git', 'apply', '--reverse', '--check', str(later)], cwd=tree, capture_output=True).returncode == 0:
                undone = subprocess.run(['git', 'apply', '--reverse', str(later)], cwd=tree, capture_output=True, text=True)
                assert undone.returncode == 0, f'{later.name} does not come out of the core:\n' + undone.stderr
        carried = subprocess.run(['git', 'apply', '--reverse', '--check', str(PATCH)], cwd=tree, capture_output=True)
        if (carried.returncode != 0) != reverse:
            done = subprocess.run(['git', 'apply', *(['--reverse'] if reverse else []), str(PATCH)], cwd=tree,
                                  capture_output=True, text=True)
            assert done.returncode == 0, '0024 does not apply to the core:\n' + done.stderr
        return {name: (tree / name).read_text(encoding='utf-8') for name in FILES}
    finally:
        shutil.rmtree(tree)


def table(text, name):
    """(initializer text list, the whole declaration) of `float name[MAX_CLASSES] = {...};`."""
    found = re.search(r'float (?:const )?%s\[MAX_CLASSES\] =\s*\{(.*?)\};' % name, text, re.S)
    assert found, name + ' is missing'
    body = re.sub(r'//[^\n]*', '', found.group(1))
    return [item.strip() for item in body.split(',') if item.strip()], 'const float %s[MAX_CLASSES] = {%s};' % (name, found.group(1))


def header_macros(text):
    """The Classes enum, MAX_CLASSES and CLASSMASK_ALL_PLAYABLE as the header writes them."""
    enum = re.search(r'enum Classes\n\{.*?\n\};', text, re.S)
    limit = re.search(r'#define MAX_CLASSES[^\n]*', text)
    mask = re.search(r'#define CLASSMASK_ALL_PLAYABLE \\\n(?:[^\n]*\\\n)*[^\n]*\n', text)
    assert enum and limit and mask, 'a class macro is missing from SharedDefines.h'
    return enum.group(0) + '\n' + limit.group(0) + '\n' + mask.group(0)


def driver(files):
    """C++ that prints MAX_CLASSES, the mask and every table, built from the patched text itself."""
    out = ['#include <cstdio>', '#include <cstdint>', 'using uint32 = std::uint32_t;', header_macros(files[DEFS]),
           'int main()', '{', '    std::printf("limit %d\\nmask %d\\n", MAX_CLASSES, CLASSMASK_ALL_PLAYABLE);']
    for path, name in TABLES:
        out.insert(4, table(files[path], name)[1])
        out.append('    std::printf("%s");  for (float v : %s) std::printf(" %%.6f", v);  std::printf("\\n");' % (name, name))
    return '\n'.join(out + ['    return 0;', '}']) + '\n'


def measure(files):
    """(rows, error): the driver's output as {name: [values]} ('limit' and 'mask' too), or why it did not build."""
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT) as folder:
        cpp = Path(folder) / 'limit.cpp'
        cpp.write_text(driver(files), encoding='utf-8')
        built = subprocess.run(['c++', '-std=c++17', '-o', str(Path(folder) / 'limit'), str(cpp)], capture_output=True, text=True)
        if built.returncode != 0:
            return None, 'the header macros or a table do not compile: ' + built.stderr[-300:]
        ran = harness_env.run([str(Path(folder) / 'limit')], capture_output=True, text=True)
    return {line.split()[0]: line.split()[1:] for line in ran.stdout.splitlines()}, None


def problems(files):
    """What is wrong with the patched files; empty when the class limit is right."""
    out = []
    rows, error = measure(files)
    if error:
        return [error]
    limit, mask = int(rows['limit'][0]), int(rows['mask'][0])
    if limit < 15:
        out.append(f'MAX_CLASSES is {limit}: ids 12, 13 and 14 need 15')
    # ids 1..9 (the Death Knight is 6) and 11: bits 0..8 and 10
    stock = sum(1 << bit for bit in (0, 1, 2, 3, 4, 5, 6, 7, 8, 10))
    if mask & stock != stock:
        out.append('a stock class bit left CLASSMASK_ALL_PLAYABLE')
    if mask & (1 << 9):
        out.append('bit 9 (the unused id 10) entered the playable mask')
    for bit in (11, 12, 13):
        if not mask & (1 << bit):
            out.append(f'bit {bit} (class id {bit + 1}) is not in CLASSMASK_ALL_PLAYABLE')
    if mask >> 14:
        out.append('the playable mask holds a bit above id 14')
    for path, name in TABLES:
        initializers, _ = table(files[path], name)
        values = [float(v) for v in rows[name]]
        if len(values) != limit:
            out.append(f'{name} does not have MAX_CLASSES slots')
            continue
        if len(initializers) != MONK + 1:
            out.append(f'{name} has {len(initializers)} entries, not 12 (ids 1..11 and the Monk)')
        if values[MONK] != values[0]:
            out.append(f'{name}: the Monk\'s entry {values[MONK]} is not the Warrior\'s {values[0]}')
        if values[MONK] == 0.0 and name != 'parry_cap':
            out.append(f'{name}: the Monk\'s entry is zero')
        if any(values[12:]):
            out.append(f'{name}: ids 13 and 14 are filled before their classes exist')
    return out


# (what, file, old text, new text): each must break exactly one rule of the patch.
def mutants(files):
    yield 'the limit stays 12', DEFS, re.search(r'#define MAX_CLASSES\s+15', files[DEFS]).group(0), '#define MAX_CLASSES       12'
    yield 'the limit is 13 (no room for ids 13 and 14)', DEFS, re.search(r'#define MAX_CLASSES\s+15', files[DEFS]).group(0), '#define MAX_CLASSES       13'
    yield 'the Monk\'s bit is left out of the mask', DEFS, '(1<<11)|(1<<12)|(1<<13)', '(1<<12)|(1<<13)'
    yield 'a stock class bit is dropped from the mask', DEFS, '(1<<(CLASS_DEATH_KNIGHT-1))|', ''
    yield 'bit 9 joins the mask', DEFS, '(1<<11)|(1<<12)|(1<<13)', '(1<<9)|(1<<11)|(1<<12)|(1<<13)'
    yield 'a table\'s Monk entry is zeroed: dodge_base', PLAYER, '0.036640f  // Monk', '0.0f  // Monk'
    yield 'a table\'s Monk entry is zeroed: crit_to_dodge', PLAYER, '0.85f / 1.15f   // Monk', '0.0f   // Monk'
    yield 'a table\'s Monk entry is zeroed: m_diminishing_k', STAT, '0.9560f   // Monk', '0.0f   // Monk'
    yield 'a table\'s Monk entry is zeroed: miss_cap', STAT, '16.00f      // Monk', '0.0f      // Monk'
    yield 'a table\'s Monk entry is another class\'s: parry_cap', STAT, '47.003525f      // Monk', '145.560408f      // Monk'
    yield 'a table\'s Monk entry is zeroed: dodge_cap', STAT, '88.129021f      // Monk', '0.0f      // Monk'
    yield 'a table\'s Monk row is missing: dodge_cap', STAT, ',    // Druid\n        88.129021f      // Monk (Warrior\'s)', '     // Druid'
    yield 'id 13 is filled early: parry_cap', STAT, '47.003525f      // Monk (Warrior\'s)', '47.003525f,     // Monk (Warrior\'s)\n        47.003525f'


class ClassLimit(unittest.TestCase):
    def test_the_patch_holds_every_rule(self):
        self.assertEqual(problems(patched()), [])

    def test_the_stock_core_fails_the_check(self):
        self.assertTrue(problems(patched(reverse=True)))

    def test_each_rule_fails_when_broken(self):
        files = patched()
        for what, path, old, new in mutants(files):
            with self.subTest(mutation=what):
                self.assertEqual(files[path].count(old), 1, f'{old!r} is not unique in {path}')
                broken = dict(files, **{path: files[path].replace(old, new)})
                self.assertTrue(problems(broken), f'the check passed with: {what}')


if __name__ == '__main__':
    unittest.main()

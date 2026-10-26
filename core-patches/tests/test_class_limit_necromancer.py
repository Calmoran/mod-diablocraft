"""Core patch 0030 (the Necromancer's class-limit entries, Necromancer part 1b diablocraft-im7mr.2): class id 13 has an
entry in every per-class table, the Warlock's (its parent).

Patch 0024 raised MAX_CLASSES to 15 but wrote ids 1..12 into the six tables indexed [class - 1], so the Necromancer's
slot (index 12, the 13th entry) is zero-initialised: `0 * cap / (0 + cap * k)` is 0/0 = NaN when the defense-rating
term is 0, in the miss chance, parry and dodge of every Necromancer. The three files 0024 edits are copied out of the
core into scratch and 0030 is applied there (0024 first when the core lacks it; when the core already carries 0030 the
copies are checked as they are). The header's class macros and the six tables are compiled and run: the Necromancer's
slot equals the Warlock's, is nonzero where the formulas divide by cap * k, the Monk's and the stock entries are
untouched, id 14 stays empty until the Witch Doctor lands, and the playable mask holds id 13's bit. Then it proves it
can fail: each single-rule mutant of the patched text is refused, and the core without 0030 fails the check.

TORMENT_CORE overrides the core (default: this repo's azerothcore-wotlk). Nothing in the core is written.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_class_limit as base  # noqa: E402  (0024's test: the table reader, the driver and measure())

REPO, CORE, OUT = base.REPO, base.CORE, base.OUT
FIRST = base.PATCH
PATCH = base.NECRO
DEFS, PLAYER, STAT, FILES, TABLES = base.DEFS, base.PLAYER, base.STAT, base.FILES, base.TABLES
WARLOCK, MONK, NECROMANCER = 8, 11, 12  # [class - 1] for ids 9, 12 and 13


def patched(reverse=False):
    """{path: text} of the three files with 0030 applied (or, `reverse`, without it; 0024 stays in)."""
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    try:
        for name in FILES:
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(CORE / name, tree / name)
        # 0032 edits 0030's lines and fills id 14: this test judges 0030 alone, so 0032 comes out first
        if subprocess.run(['git', 'apply', '--reverse', '--check', str(base.WITCH)], cwd=tree, capture_output=True).returncode == 0:
            undone = subprocess.run(['git', 'apply', '--reverse', str(base.WITCH)], cwd=tree, capture_output=True, text=True)
            assert undone.returncode == 0, '0032 does not come out of the core:\n' + undone.stderr
        carried = subprocess.run(['git', 'apply', '--reverse', '--check', str(PATCH)], cwd=tree, capture_output=True)
        if (carried.returncode != 0) != reverse:
            if not reverse and subprocess.run(['git', 'apply', '--reverse', '--check', str(FIRST)], cwd=tree,
                                              capture_output=True).returncode != 0:
                first = subprocess.run(['git', 'apply', str(FIRST)], cwd=tree, capture_output=True, text=True)
                assert first.returncode == 0, '0024 does not apply to the core:\n' + first.stderr
            done = subprocess.run(['git', 'apply', *(['--reverse'] if reverse else []), str(PATCH)], cwd=tree,
                                  capture_output=True, text=True)
            assert done.returncode == 0, '0030 does not apply to the core:\n' + done.stderr
        return {name: (tree / name).read_text(encoding='utf-8') for name in FILES}
    finally:
        shutil.rmtree(tree)


def problems(files):
    """What is wrong with the patched files; empty when the Necromancer's entries are right."""
    out = []
    rows, error = base.measure(files)
    if error:
        return [error]
    limit, mask = int(rows['limit'][0]), int(rows['mask'][0])
    if limit < 15:
        out.append(f'MAX_CLASSES is {limit}: ids 12, 13 and 14 need 15')
    if not mask & (1 << 12):
        out.append('bit 12 (class id 13) is not in CLASSMASK_ALL_PLAYABLE')
    for path, name in TABLES:
        initializers, _ = base.table(files[path], name)
        values = [float(v) for v in rows[name]]
        if len(values) != limit:
            out.append(f'{name} does not have MAX_CLASSES slots')
            continue
        if len(initializers) != NECROMANCER + 1:
            out.append(f'{name} has {len(initializers)} entries, not 13 (ids 1..11, the Monk and the Necromancer)')
        if values[NECROMANCER] != values[WARLOCK]:
            out.append(f'{name}: the Necromancer\'s entry {values[NECROMANCER]} is not the Warlock\'s {values[WARLOCK]}')
        if values[NECROMANCER] == 0.0 and values[WARLOCK] != 0.0:
            out.append(f'{name}: the Necromancer\'s entry is zero')
        if values[MONK] != values[0]:
            out.append(f'{name}: the Monk\'s entry {values[MONK]} is no longer the Warrior\'s {values[0]}')
        if any(values[NECROMANCER + 1:]):
            out.append(f'{name}: id 14 is filled before its class exists')
    # the divisions the zero slot broke: a Necromancer with no defense rating must not reach 0/0
    k, miss = float(rows['m_diminishing_k'][NECROMANCER]), float(rows['miss_cap'][NECROMANCER])
    if miss * k == 0.0:
        out.append('miss_cap * m_diminishing_k is zero for the Necromancer: the defence diminishing formula divides 0 by 0')
    return out


# (what, file, old text, new text): each must break exactly one rule of the patch.
def mutants(files):
    yield 'dodge_base: the Necromancer\'s entry is zeroed', PLAYER, '0.024211f  // Necromancer', '0.0f  // Necromancer'
    yield 'dodge_base: the Necromancer\'s entry is the Warrior\'s', PLAYER, '0.024211f  // Necromancer', '0.036640f  // Necromancer'
    yield 'crit_to_dodge: the Necromancer\'s entry is zeroed', PLAYER, '0.97f / 1.15f   // Necromancer', '0.0f   // Necromancer'
    yield 'crit_to_dodge: the Necromancer\'s entry is the Mage\'s', PLAYER, '0.97f / 1.15f   // Necromancer', '1.00f / 1.15f   // Necromancer'
    yield 'm_diminishing_k: the Necromancer\'s entry is zeroed', STAT, '0.9830f   // Necromancer', '0.0f   // Necromancer'
    yield 'm_diminishing_k: the Necromancer\'s entry is the Warrior\'s', STAT, '0.9830f   // Necromancer', '0.9560f   // Necromancer'
    yield 'miss_cap: the Necromancer\'s entry is zeroed', STAT, '16.00f      // Necromancer', '0.0f      // Necromancer'
    yield 'parry_cap: the Necromancer parries like the Warrior', STAT, '0.0f            // Necromancer', '47.003525f      // Necromancer'
    yield 'dodge_cap: the Necromancer\'s entry is zeroed', STAT, '150.375940f     // Necromancer', '0.0f     // Necromancer'
    yield 'dodge_cap: the Necromancer\'s entry is the Warrior\'s', STAT, '150.375940f     // Necromancer', '88.129021f      // Necromancer'
    yield 'dodge_cap: the Necromancer\'s row is missing', STAT, ',     // Monk (Warrior\'s)\n        150.375940f     // Necromancer (Warlock\'s)', '      // Monk (Warrior\'s)'
    yield 'parry_cap: id 14 is filled early', STAT, '0.0f            // Necromancer (Warlock\'s: no parry)', '0.0f,           // Necromancer (Warlock\'s: no parry)\n        47.003525f'
    yield 'the Monk\'s entry is lost: miss_cap', STAT, '16.00f,     // Monk', '0.0f,     // Monk'
    yield 'bit 12 leaves the mask', DEFS, '(1<<11)|(1<<12)|(1<<13)', '(1<<11)|(1<<13)'
    yield 'the limit stays 12', DEFS, re.search(r'#define MAX_CLASSES\s+15', files[DEFS]).group(0), '#define MAX_CLASSES       12'


class NecromancerClassLimit(unittest.TestCase):
    def test_the_patch_holds_every_rule(self):
        self.assertEqual(problems(patched()), [])

    def test_the_core_without_0030_fails_the_check(self):
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

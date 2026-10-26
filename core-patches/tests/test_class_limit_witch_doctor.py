"""Core patch 0032 (the Witch Doctor's class-limit entries, Witch Doctor part 1b diablocraft-vxrcu.2): class id 14 has an
entry in every per-class table, the Warlock's (its parent).

Patch 0024 raised MAX_CLASSES to 15 and put bits 11-13 in the playable mask, which holds id 14 (bit 13) already; it and 0030 wrote
ids 1..13 into the six tables indexed [class - 1], so the Witch Doctor's slot (index 13, the 14th entry) is zero-initialised:
`0 * cap / (0 + cap * k)` is 0/0 = NaN when the defense-rating term is 0, in the miss chance, parry and dodge of every Witch Doctor.
The three files the patches edit are copied out of the core into scratch and 0032 is applied there (0024 and 0030 first when the
core lacks them; when the core already carries 0032 the copies are checked as they are). The header's class macros and the six
tables are compiled and run: the Witch Doctor's slot equals the Warlock's, is nonzero where the formulas divide by cap * k, the
Monk's and the Necromancer's and the stock entries are untouched, and the playable mask holds id 14's bit. Then it proves it can
fail: each single-rule mutant of the patched text is refused, and the core without 0032 fails the check.

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
PATCH = base.WITCH
DEFS, PLAYER, STAT, FILES, TABLES = base.DEFS, base.PLAYER, base.STAT, base.FILES, base.TABLES
WARLOCK, MONK, NECROMANCER, WITCH_DOCTOR = 8, 11, 12, 13  # [class - 1] for ids 9, 12, 13 and 14


def patched(reverse=False):
    """{path: text} of the three files with 0032 applied (or, `reverse`, without it; 0024 and 0030 stay in)."""
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    try:
        for name in FILES:
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(CORE / name, tree / name)
        carried = subprocess.run(['git', 'apply', '--reverse', '--check', str(PATCH)], cwd=tree, capture_output=True)
        if (carried.returncode != 0) != reverse:
            if not reverse:
                # 0030 edits 0024's lines, so a core that carries 0030 carries 0024 too; otherwise 0024 and then 0030 go on
                def carries(patch):
                    return subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=tree, capture_output=True).returncode == 0
                if not carries(base.NECRO):
                    for first in (base.PATCH, base.NECRO):
                        if first == base.NECRO or not carries(first):
                            done = subprocess.run(['git', 'apply', str(first)], cwd=tree, capture_output=True, text=True)
                            assert done.returncode == 0, f'{first.name} does not apply to the core:\n' + done.stderr
            done = subprocess.run(['git', 'apply', *(['--reverse'] if reverse else []), str(PATCH)], cwd=tree,
                                  capture_output=True, text=True)
            assert done.returncode == 0, '0032 does not apply to the core:\n' + done.stderr
        return {name: (tree / name).read_text(encoding='utf-8') for name in FILES}
    finally:
        shutil.rmtree(tree)


def problems(files):
    """What is wrong with the patched files; empty when the Witch Doctor's entries are right."""
    out = []
    rows, error = base.measure(files)
    if error:
        return [error]
    limit, mask = int(rows['limit'][0]), int(rows['mask'][0])
    if limit < 15:
        out.append(f'MAX_CLASSES is {limit}: ids 12, 13 and 14 need 15')
    if not mask & (1 << 13):
        out.append('bit 13 (class id 14) is not in CLASSMASK_ALL_PLAYABLE')
    if mask >> 14:
        out.append('the playable mask holds a bit above id 14')
    for path, name in TABLES:
        initializers, _ = base.table(files[path], name)
        values = [float(v) for v in rows[name]]
        if len(values) != limit:
            out.append(f'{name} does not have MAX_CLASSES slots')
            continue
        if len(initializers) != WITCH_DOCTOR + 1:
            out.append(f'{name} has {len(initializers)} entries, not 14 (ids 1..11, the Monk, the Necromancer and the Witch Doctor)')
        if values[WITCH_DOCTOR] != values[WARLOCK]:
            out.append(f'{name}: the Witch Doctor\'s entry {values[WITCH_DOCTOR]} is not the Warlock\'s {values[WARLOCK]}')
        if values[WITCH_DOCTOR] == 0.0 and values[WARLOCK] != 0.0:
            out.append(f'{name}: the Witch Doctor\'s entry is zero')
        if values[NECROMANCER] != values[WARLOCK]:
            out.append(f'{name}: the Necromancer\'s entry {values[NECROMANCER]} is no longer the Warlock\'s {values[WARLOCK]}')
        if values[MONK] != values[0]:
            out.append(f'{name}: the Monk\'s entry {values[MONK]} is no longer the Warrior\'s {values[0]}')
    # the divisions the zero slot broke: a Witch Doctor with no defense rating must not reach 0/0
    k, miss = float(rows['m_diminishing_k'][WITCH_DOCTOR]), float(rows['miss_cap'][WITCH_DOCTOR])
    if miss * k == 0.0:
        out.append('miss_cap * m_diminishing_k is zero for the Witch Doctor: the defence diminishing formula divides 0 by 0')
    return out


# (what, file, old text, new text): each must break exactly one rule of the patch.
def mutants(files):
    yield 'dodge_base: the Witch Doctor\'s entry is zeroed', PLAYER, '0.024211f  // Witch Doctor', '0.0f  // Witch Doctor'
    yield 'dodge_base: the Witch Doctor\'s entry is the Warrior\'s', PLAYER, '0.024211f  // Witch Doctor', '0.036640f  // Witch Doctor'
    yield 'crit_to_dodge: the Witch Doctor\'s entry is zeroed', PLAYER, '0.97f / 1.15f   // Witch Doctor', '0.0f   // Witch Doctor'
    yield 'crit_to_dodge: the Witch Doctor\'s entry is the Mage\'s', PLAYER, '0.97f / 1.15f   // Witch Doctor', '1.00f / 1.15f   // Witch Doctor'
    yield 'm_diminishing_k: the Witch Doctor\'s entry is zeroed', STAT, '0.9830f   // Witch Doctor', '0.0f   // Witch Doctor'
    yield 'm_diminishing_k: the Witch Doctor\'s entry is the Warrior\'s', STAT, '0.9830f   // Witch Doctor', '0.9560f   // Witch Doctor'
    yield 'miss_cap: the Witch Doctor\'s entry is zeroed', STAT, '16.00f      // Witch Doctor', '0.0f      // Witch Doctor'
    yield 'parry_cap: the Witch Doctor parries like the Warrior', STAT, '0.0f            // Witch Doctor', '47.003525f      // Witch Doctor'
    yield 'dodge_cap: the Witch Doctor\'s entry is zeroed', STAT, '150.375940f     // Witch Doctor', '0.0f     // Witch Doctor'
    yield 'dodge_cap: the Witch Doctor\'s entry is the Warrior\'s', STAT, '150.375940f     // Witch Doctor', '88.129021f      // Witch Doctor'
    yield 'dodge_cap: the Witch Doctor\'s row is missing', STAT, ',    // Necromancer (Warlock\'s)\n        150.375940f     // Witch Doctor (Warlock\'s)', '     // Necromancer (Warlock\'s)'
    yield 'the Necromancer\'s entry is lost: miss_cap', STAT, '16.00f,     // Necromancer', '0.0f,     // Necromancer'
    yield 'the Monk\'s entry is lost: miss_cap', STAT, '16.00f,     // Monk', '0.0f,     // Monk'
    yield 'bit 13 leaves the mask', DEFS, '(1<<11)|(1<<12)|(1<<13)', '(1<<11)|(1<<12)'
    yield 'the limit is 14', DEFS, re.search(r'#define MAX_CLASSES\s+15', files[DEFS]).group(0), '#define MAX_CLASSES       14'


class WitchDoctorClassLimit(unittest.TestCase):
    def test_the_patch_holds_every_rule(self):
        self.assertEqual(problems(patched()), [])

    def test_the_core_without_0032_fails_the_check(self):
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

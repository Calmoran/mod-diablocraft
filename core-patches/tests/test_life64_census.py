"""The narrowing census of core patch 0027, kept as a list that fails when an edit comes back (diablocraft-sbxl).

`life64_census.tsv` is every source line a build found whose Life getters refused each conversion to a type under 64 bits
(core 98 lines, core scripts 240, AutoBalance 7, mod-ale 4, and Torment's own module 44, which is the Combat and World
cutovers' to edit), with what became of it:

  edited            the line, or the statement it sits in, is different in the core 0027 leaves
  fixes itself      the callee takes 64 bits now (SetHealth, SetMaxHealth, LowerPlayerDamageReq, DealDamage, DealHeal, ModifyHealth)
  guarded           reached only when a 32-bit hit is at least the Life, so the Life is below 2^32
  widened elsewhere the variable or member that receives it is 64-bit now
  not a cut         float math, or an overload that takes 64 bits (ALE's Push)

The core's files are taken from the pinned git and the patches applied, so the test reads the core as it is built. It
fails when a line the list calls edited is back as it was, when a guarded line has lost its guard, when a callee is not
64-bit, and when the list stops adding up to the lines the census found. Then it proves it can fail: the same list is
read against the core with the three patches left out and with a file left at its pinned text.

Re-running the census itself is a full build (`_agent-scratch/sbxl-64bit/census-tools`); this keeps its result honest
between core updates, and 00-architecture.md section 8 says to re-run it at every one.
"""
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import life64_patched as lp  # noqa: E402

LIST = HERE / 'life64_census.tsv'
EXPECTED_LINES = {'core game': 98, 'core scripts': 240, 'mod-autobalance': 7, 'mod-ale': 4, 'Torment': 44}
CLASSES = {'edited', 'fixes itself', 'guarded', 'widened elsewhere', 'not a cut', 'part 2/3'}
FIXES = re.compile(r'\b(SetHealth|SetMaxHealth|LowerPlayerDamageReq|DealDamage|DealHeal|ModifyHealth)\(')
GUARD_LINE = re.compile(r'\b(if|while)\b.*(damage|dmg|GetDamage\(\)).*GetHealth\(\)|\b(if|while)\b.*GetHealth\(\).*(damage|dmg|GetDamage\(\))')


def rows():
    out = []
    for line in LIST.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        place, path, cls, lines, source = line.split('\t')
        out.append((place, path, cls, int(lines), source))
    return out


def edited(pin_lines, patched_lines, source):
    """True when some statement window around the source line in the pin has a line the patched file no longer holds."""
    now = {line.strip() for line in patched_lines}
    spots = [i for i, line in enumerate(pin_lines) if line.strip() == source]
    for i in spots:
        for line in pin_lines[max(0, i - 3):i + 4]:
            if line.strip() and line.strip() not in now:
                return True
    return False


def problems(patched, pin, autobalance):
    """What is wrong with the list read against the core; empty when it holds."""
    out = []
    for place, path, cls, lines, source in rows():
        if place == 'Torment':
            continue
        if cls not in CLASSES:
            out.append(f'{path}: unknown class {cls}')
            continue
        if place == 'mod-autobalance':
            if cls == 'edited' and source in autobalance.get(path, ''):
                out.append(f'{path}: {source!r} is back')
            continue
        if place == 'mod-ale':
            continue
        text = pin[path].split('\n')
        if source not in [line.strip() for line in text]:
            out.append(f'{path}: {source!r} is not in the pinned file')
            continue
        now = patched[path].split('\n') if path in patched else text
        if cls == 'edited' and not edited(text, now, source):
            out.append(f'{path}: {source!r} is as it was')
        if cls == 'guarded':
            at = [i for i, line in enumerate(now) if line.strip() == source]
            if not at or not any(GUARD_LINE.search(' '.join(now[max(0, i - 14):i])) for i in at):
                out.append(f'{path}: {source!r} has no guard above it')
        if cls == 'fixes itself' and not FIXES.search(source):
            out.append(f'{path}: {source!r} calls none of the 64-bit functions')
    return out


class Census(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = rows()
        cls.paths = sorted({path for place, path, *_ in cls.rows if place in ('core game', 'core scripts')})
        cls.pin = {path: lp.pristine(path).decode('utf-8') for path in cls.paths}
        cls.patched = lp.replay(cls.paths)
        cls.autobalance = lp.autobalance(lp.LIFE[0])

    def test_the_list_adds_up_to_the_lines_the_census_found(self):
        count = {}
        for place, _path, _cls, lines, _source in self.rows:
            count[place] = count.get(place, 0) + lines
        self.assertEqual(EXPECTED_LINES, count)

    def test_every_edited_line_is_still_edited_and_every_guard_is_there(self):
        self.assertEqual([], problems(self.patched, self.pin, self.autobalance))

    def test_the_census_fails_with_the_patches_left_out(self):
        stack = [patch for patch in lp.STACK if patch not in lp.LIFE]
        unpatched = lp.replay(self.paths, stack)
        found = problems(unpatched, self.pin, {})
        self.assertGreater(len([f for f in found if 'is as it was' in f]), 100, 'the list passed with the patches out')

    def test_the_census_fails_with_a_file_left_at_its_pinned_text(self):
        for path in ('src/server/game/Entities/Creature/Creature.cpp', 'src/server/scripts/Spells/spell_dk.cpp'):
            patched = dict(self.patched)
            patched[path] = self.pin[path]
            found = problems(patched, self.pin, self.autobalance)
            self.assertTrue([f for f in found if f.startswith(path) and 'is as it was' in f], f'the list passed with {path} left at the pin')

    def test_autobalance_lines_come_back_when_its_hunks_do(self):
        mutant = {path: text + '\n'.join(source for place, p, cls, _n, source in self.rows if p == path and place == 'mod-autobalance' and cls == 'edited')
                  for path, text in self.autobalance.items()}
        self.assertTrue(problems(self.patched, self.pin, mutant))


if __name__ == '__main__':
    unittest.main(verbosity=2)

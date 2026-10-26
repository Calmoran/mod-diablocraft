"""Isolated #67 migration check against the committed, applied crafting render."""

import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_crafting as crafting


MODULE = Path(__file__).resolve().parents[3]
APPLIED = MODULE / 'data/sql/db-world/updates/crafting_0003_crafting_tunables.sql'
ARTISANS = MODULE / 'data/sql/db-world/updates/crafting_0004_class_artisans.sql'
LEGACY = MODULE / 'data/sql/db-world/updates/crafting_0001_artisans.sql'
CHANGES = (
    ("pool_version='yes',designated_class='' WHERE d3_id='P66_Unique_Mojo_002'",
     "pool_version='yes',designated_class='witchdoctor' WHERE d3_id='P66_Unique_Mojo_002'"),
    ("pool_version='no',designated_class='' WHERE d3_id='P43_Unique_Fist_003_x1'",
     "pool_version='no',designated_class='monk' WHERE d3_id='P43_Unique_Fist_003_x1'"),
    ("pool_version='yes',designated_class='' WHERE d3_id='P71_Unique_Fist_003'",
     "pool_version='yes',designated_class='monk' WHERE d3_id='P71_Unique_Fist_003'"),
)


class DesignationDelta(unittest.TestCase):
    def setUp(self):
        scratch = MODULE.parent / 'azerothcore-wotlk/build/_agent-scratch'
        self.tmp = tempfile.TemporaryDirectory(prefix='crafting-delta-', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.module = Path(self.tmp.name) / 'mod-diablocraft'
        self.updates = self.module / 'data/sql/db-world/updates'
        self.updates.mkdir(parents=True)
        (self.module / 'data/generated').mkdir(parents=True)
        self.baseline = self.updates / APPLIED.name
        shutil.copyfile(LEGACY, self.updates / LEGACY.name)
        shutil.copyfile(APPLIED, self.baseline)
        self.artisans = self.updates / ARTISANS.name
        shutil.copyfile(ARTISANS, self.artisans)
        self.before = self.baseline.read_bytes()
        self.artisans_before = self.artisans.read_bytes()
        self.render = self.baseline.read_text(encoding='utf-8')
        self.changed_lines = []
        for old, new in CHANGES:
            self.assertEqual(self.render.count(old), 1)
            self.render = self.render.replace(old, new)
            self.changed_lines.append('UPDATE dc_base_item SET ' + new + ';')
        self.authority = self.module / 'data/sql/applied_migrations.csv'
        self.authority.write_text(
            'path,sha1,provenance\n'
            f'db-world/updates/{APPLIED.name},'
            f'{hashlib.sha1(self.before).hexdigest().upper()},fixture\n',
            encoding='utf-8')

    def generate(self):
        with patch.object(crafting, 'MODULE', self.module):
            crafting.write_generated(self.render, 'crafting.sql',
                                     'crafting_0001_artisans.sql')

    def test_only_the_three_approved_updates_are_emitted_and_repeat_is_quiet(self):
        self.generate()
        delta = self.updates / 'crafting_0005_crafting_tunables.sql'
        expected = '\n'.join(self.changed_lines) + '\n'
        self.assertEqual(delta.read_text(encoding='utf-8'), expected)
        self.assertEqual(self.baseline.read_bytes(), self.before)
        self.assertEqual(self.artisans.read_bytes(), self.artisans_before)
        self.assertEqual((self.module / 'data/generated/crafting.sql').read_text(encoding='utf-8'),
                         self.render)
        # A deployed delta is listed as applied. Repeating the full render must
        # neither rewrite that file nor produce crafting_0006.
        applied_delta = delta.read_bytes()
        with self.authority.open('a', encoding='utf-8') as stream:
            stream.write(f'db-world/updates/{delta.name},'
                         f'{hashlib.sha1(applied_delta).hexdigest().upper()},fixture\n')
        self.generate()
        self.assertEqual(delta.read_bytes(), applied_delta)
        self.assertEqual(self.baseline.read_bytes(), self.before)
        self.assertEqual(self.artisans.read_bytes(), self.artisans_before)
        self.assertFalse((self.updates / 'crafting_0006_crafting_tunables.sql').exists())

    def test_any_other_difference_is_not_the_approved_delta(self):
        before = [line for line in self.baseline.read_text(encoding='utf-8').splitlines()
                  if line and not line.startswith('--')]
        after = [line for line in self.render.splitlines()
                 if line and not line.startswith('--')]
        self.assertEqual(crafting.approved_designation_delta(before, after), self.changed_lines)
        self.assertIsNone(crafting.approved_designation_delta(before, after + ['SELECT 1;']))
        wrong = after.copy()
        wrong[wrong.index(self.changed_lines[0])] = self.changed_lines[0].replace(
            "designated_class='witchdoctor'", "designated_class='monk'")
        self.assertIsNone(crafting.approved_designation_delta(before, wrong))

    def test_unapplied_full_render_attempt_is_replaced_in_place(self):
        attempted = self.updates / 'crafting_0005_crafting_tunables.sql'
        attempted.write_text(self.render, encoding='utf-8')
        self.generate()
        self.assertEqual(attempted.read_text(encoding='utf-8'),
                         '\n'.join(self.changed_lines) + '\n')
        self.assertEqual(self.baseline.read_bytes(), self.before)
        self.assertEqual(self.artisans.read_bytes(), self.artisans_before)
        self.assertFalse((self.updates / 'crafting_0006_crafting_tunables.sql').exists())


if __name__ == '__main__':
    unittest.main()

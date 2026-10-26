"""Offline persistent-ID contracts; all mutations and generation stay in scratch."""
import contextlib
import csv
import io
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_crafting as crafting
import generate_jeweler as jeweler
import persistent_ids as ids
from tunable_values import integer


class PersistentIDsTests(unittest.TestCase):
    def setUp(self):
        scratch = crafting.ROOT / 'azerothcore-wotlk/build/_agent-scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='persistent-ids-test-', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.module = Path(self.tmp.name) / 'mod-diablocraft'
        shutil.copytree(crafting.MODULE / 'data', self.module / 'data')
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.multiple(crafting, MODULE=self.module,
                                               DATA=self.module/'data/d3',
                                               TUNABLES=self.module/'data/tunables'))
        self.stack.enter_context(patch.object(crafting, 'tunable_integer',
            lambda category, name, **kwargs: integer(category, name, module=self.module, **kwargs)))
        self.stack.enter_context(patch.object(jeweler, 'MODULE', self.module))

    def rows(self, name):
        with (self.module/'data'/name).open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            return reader.fieldnames, list(reader)

    def write(self, name, header, rows):
        with (self.module/'data'/name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=header, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)

    def outputs(self):
        return {str(p.relative_to(self.module)): p.read_bytes()
                for p in (self.module/'data').rglob('*.sql')}

    def generate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            crafting.generate()
            jeweler.generate()

    def test_all_existing_ids_match_immutable_history_and_reserved_slots(self):
        gems = ids.gem_items(self.module, crafting.read('gems.csv'))
        recipes = ids.blacksmith_recipes(self.module, crafting.read('blacksmith_recipes.csv'))
        tiers = ids.difficulty_tiers(self.module, crafting.read('difficulty_tiers.csv'))
        history = (self.module/'data/sql/db-world/updates/crafting_0001_artisans.sql').read_text()
        expected = {(gem, tier): int(entry) for entry,gem,tier in re.findall(
            r"INSERT INTO `dc_gem_item` VALUES \((\d+),'([^']+)','([^']+)'", history)}
        self.assertEqual(gems, expected)
        # Includes the three jewelry IDs skipped by the Blacksmith projection.
        self.assertEqual(recipes, dict(zip(('head','shoulders','neck','torso','waist','hands',
                                           'wrists','legs','feet','leftfinger','rightfinger',
                                           'mainhand','offhand'), range(1,14))))
        self.assertEqual((tiers['Normal'], tiers['Master']), (1,4))
        self.assertEqual(len(tiers),10)
        for output, input_entry, *_ in jeweler.recipe_rows():
            self.assertIn(output, gems.values())
            self.assertIn(input_entry, gems.values())

    def test_generation_preserves_history_and_is_idempotent(self):
        before = self.outputs()
        self.generate()
        first = self.outputs()
        self.assertEqual(set(first), set(before), 'No new migration is needed for unchanged IDs')
        for name in before:
            if '/sql/' in name:
                self.assertEqual(before[name], first[name], name)
            else:
                # Known CRLF description content normalizes on full crafting generation.
                self.assertEqual(before[name].decode().replace('\r\n','\n'),
                                 first[name].decode().replace('\r\n','\n'), name)
        self.generate()
        self.assertEqual(first, self.outputs())

    def test_reordered_sheets_and_headers_keep_ids_and_jeweler_rows(self):
        gem_before = ids.gem_items(self.module, crafting.read('gems.csv'))
        recipes_before = ids.blacksmith_recipes(self.module, crafting.read('blacksmith_recipes.csv'))
        combines, drops = jeweler.recipe_rows(), jeweler.drop_rows()
        for name in ('gem_items.csv','blacksmith_recipe_ids.csv','difficulty_ids.csv',
                     'd3/gems.csv','d3/blacksmith_recipes.csv','d3/difficulty_tiers.csv'):
            header, rows = self.rows(name)
            if name == 'd3/difficulty_tiers.csv':
                header = list(reversed(header))
            self.write(name, header, list(reversed(rows)))
        self.assertEqual(gem_before, ids.gem_items(self.module, crafting.read('gems.csv')))
        self.assertEqual(recipes_before, ids.blacksmith_recipes(self.module, crafting.read('blacksmith_recipes.csv')))
        self.assertEqual(combines, jeweler.recipe_rows())
        self.assertEqual(drops, jeweler.drop_rows())
        with contextlib.redirect_stdout(io.StringIO()):
            crafting.generate()
        text = (self.module/'data/generated/crafting.sql').read_text()
        actual = {slot:int(identity) for identity,slot in re.findall(
            r"INSERT INTO `dc_blacksmith_recipe` VALUES \((\d+),'([^']+)'", text)}
        self.assertEqual(actual, {slot:identity for slot,identity in recipes_before.items()
                                 if slot not in ('neck','leftfinger','rightfinger')})

    def test_duplicate_keys_and_ids_fail_before_output(self):
        before = self.outputs()
        for name, run in [('gem_items.csv', crafting.generate),
                          ('gem_items.csv', jeweler.generate),
                          ('blacksmith_recipe_ids.csv', crafting.generate),
                          ('difficulty_ids.csv', jeweler.generate)]:
            header, original = self.rows(name)
            for duplicate in ('key', 'id'):
                with self.subTest(name=name, consumer=run.__module__, duplicate=duplicate):
                    rows = [dict(r) for r in original]
                    if duplicate == 'key':
                        rows.append(dict(rows[0]))
                    else:
                        rows[1][header[-1]] = rows[0][header[-1]]
                    self.write(name, header, rows)
                    with self.assertRaisesRegex(ValueError, 'duplicate'):
                        run()
                    self.assertEqual(before, self.outputs())
            self.write(name, header, original)

    def test_missing_blank_and_invalid_ids_fail_before_output(self):
        before = self.outputs()
        for name, run in [('gem_items.csv', crafting.generate),
                          ('gem_items.csv', jeweler.generate),
                          ('blacksmith_recipe_ids.csv', crafting.generate),
                          ('difficulty_ids.csv', jeweler.generate)]:
            header, original = self.rows(name)
            for invalid in ('missing-row', '', '0', '-1', '1.5'):
                with self.subTest(name=name, consumer=run.__module__, invalid=invalid):
                    rows = [dict(r) for r in original]
                    if invalid == 'missing-row':
                        rows.pop(0)
                    else:
                        rows[0][header[-1]] = invalid
                    self.write(name, header, rows)
                    with self.assertRaises(ValueError):
                        run()
                    self.assertEqual(before, self.outputs())
            self.write(name, header, original)

    def test_renumbering_published_ids_fails_before_output(self):
        before = self.outputs()
        for name, run in [('gem_items.csv', crafting.generate),
                          ('gem_items.csv', jeweler.generate),
                          ('blacksmith_recipe_ids.csv', crafting.generate),
                          ('difficulty_ids.csv', jeweler.generate)]:
            header, original = self.rows(name)
            rows = [dict(r) for r in original]
            rows[0][header[-1]], rows[1][header[-1]] = rows[1][header[-1]], rows[0][header[-1]]
            self.write(name, header, rows)
            with self.assertRaisesRegex(ValueError, 'append-only'):
                run()
            self.assertEqual(before, self.outputs())
            self.write(name, header, original)

    def test_new_earlier_gem_needs_explicit_unused_id_without_renumbering(self):
        gems = crafting.read('gems.csv')
        before = ids.gem_items(self.module, gems)
        added = dict(next(r for r in gems if r['is_legendary']=='0'),
                     gem_id='000_fixture_only', gem_name='Fixture', colour='Fixture')
        with self.assertRaisesRegex(ValueError, 'missing IDs'):
            ids.gem_items(self.module, [added, *gems])
        header, rows = self.rows('gem_items.csv')
        # Test-only appended identity; never written to the shipped sheet.
        identity = max(before.values()) + 1
        rows.append(dict(gem_id=added['gem_id'], tier=added['tier'], item_entry=str(identity)))
        self.write('gem_items.csv', header, rows)
        after = ids.gem_items(self.module, [added, *gems])
        self.assertEqual({key:after[key] for key in before}, before)
        self.assertEqual(after[added['gem_id'], added['tier']], identity)


if __name__ == '__main__':
    unittest.main()

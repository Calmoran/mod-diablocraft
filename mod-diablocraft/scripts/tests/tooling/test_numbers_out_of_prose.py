"""Offline numeric-cell regressions; no live database or worktree generation."""
import ast
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
import generate_numeric_data as numeric
from tunable_values import integer


class NumbersOutOfProseTests(unittest.TestCase):
    def setUp(self):
        scratch = crafting.ROOT/'azerothcore-wotlk/build/_agent-scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='numeric-artisan-test-', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.module = Path(self.tmp.name)/'mod-diablocraft'
        shutil.copytree(crafting.MODULE/'data', self.module/'data')
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.multiple(crafting, MODULE=self.module,
            DATA=self.module/'data/d3', TUNABLES=self.module/'data/tunables'))
        self.stack.enter_context(patch.object(crafting, 'tunable_integer',
            lambda category, name, **kwargs: integer(category,name,module=self.module,**kwargs)))
        self.stack.enter_context(patch.object(jeweler, 'MODULE', self.module))

    def edit(self, name, change):
        path = self.module/'data/d3'/name
        with path.open(newline='', encoding='utf-8-sig') as stream:
            reader = csv.DictReader(stream)
            header, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=header, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)

    def outputs(self):
        return {str(p.relative_to(self.module)):p.read_bytes() for p in (self.module/'data').rglob('*.sql')}

    def generate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            crafting.generate()
            jeweler.generate()
            numeric.generate(self.module)

    def test_numeric_rows_equal_preexisting_generated_contract(self):
        def rows(path, table):
            return [ast.literal_eval(row) for row in re.findall(
                r'INSERT INTO `'+table+r'` VALUES (.*);', path.read_text())]
        updates = self.module/'data/sql/db-world/updates'
        # Frozen baseline: the quality column (wpt7l.2) leaves every pre-existing row as it was, under quality normal.
        self.assertEqual([(r, c, e, lo, hi) for r, c, q, e, lo, hi in crafting.salvage_rows() if q == 'normal'],
                         rows(updates/'crafting_0001_artisans.sql','dc_salvage_rule'))
        self.assertEqual(jeweler.recipe_rows(), rows(updates/'crafting_0002_jeweler.sql','dc_jeweler_recipe'))
        self.assertEqual(numeric.render(self.module), (updates/'numeric_rules_0001.sql').read_text())

    def test_display_sentences_and_names_cannot_change_gameplay_or_provenance(self):
        self.generate()
        before = self.outputs()
        self.edit('rarity_tiers.csv', lambda rows: [r.update(salvage_result='Display sentence only; no numeric grammar.') for r in rows])
        self.edit('jeweler.csv', lambda rows: [r.update(name='Same display name', inputs='Display only',
            quality='Display quality', note='Display note') for r in rows])
        self.generate()
        self.assertEqual(before, self.outputs())

    def test_numeric_cells_are_authoritative(self):
        original = crafting.salvage_rows()
        self.edit('salvage_rules.csv', lambda rows: rows[0].update(min_count=rows[0]['max_count']))
        changed = crafting.salvage_rows()
        self.assertEqual(changed[0][-2:], (original[0][-1], original[0][-1]))
        self.assertEqual(changed[1:], original[1:])
        old = jeweler.recipe_rows()
        self.edit('jeweler.csv', lambda rows: rows[0].update(input_count=str(int(rows[0]['input_count'])+1)))
        new = jeweler.recipe_rows()
        self.assertEqual([r[2] for r in new[:5]], [r[2]+1 for r in old[:5]])
        self.assertEqual(new[5:], old[5:])
        self.edit('jeweler.csv', lambda rows: next(r for r in rows if r['operation_id']=='unsocket_current').update(gold='1'))
        self.assertIn("('jeweler_unsocket_gold',1,'jeweler.csv/Remove gem (non-destroying)/gold')", numeric.render(self.module))

    def test_invalid_salvage_cells_fail_before_sql_writes(self):
        path = self.module/'data/d3/salvage_rules.csv'
        original, before = path.read_bytes(), self.outputs()
        changes = [lambda rows: rows.append(dict(rows[0])),
                   lambda rows: rows[0].update(min_count=''),
                   lambda rows: rows[0].update(min_count='-1'),
                   lambda rows: rows[0].update(min_count='1.5'),
                   lambda rows: rows[0].update(max_count='0'),
                   lambda rows: rows[0].update(crafted='2'),
                   lambda rows: rows[0].update(material_entry='0'),
                   lambda rows: rows[0].update(source_rarity='missing'),
                   lambda rows: rows[0].update(quality_id='missing'),
                   lambda rows: rows[0].update(quality_id='primal'),
                   lambda rows: rows.pop(0)]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                path.write_bytes(original)
                self.edit('salvage_rules.csv', change)
                with self.assertRaises(ValueError):
                    crafting.generate()
                self.assertEqual(before, self.outputs())

    def test_invalid_jeweler_keys_tiers_and_counts_fail_before_sql_writes(self):
        path = self.module/'data/d3/jeweler.csv'
        original, before = path.read_bytes(), self.outputs()
        changes = [lambda rows: rows[0].update(operation_id=''),
                   lambda rows: rows[1].update(operation_id=rows[0]['operation_id']),
                   lambda rows: rows[0].update(input_tier=''),
                   lambda rows: rows[0].update(output_tier='missing'),
                   lambda rows: rows[0].update(input_tier=rows[0]['output_tier']),
                   lambda rows: rows[0].update(input_count='0'),
                   lambda rows: rows[0].update(input_count=''),
                   lambda rows: next(r for r in rows if r['operation_id']=='unsocket_current').update(operation_id='missing')]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                path.write_bytes(original)
                self.edit('jeweler.csv', change)
                with self.assertRaises(ValueError):
                    jeweler.generate()
                self.assertEqual(before, self.outputs())

    def test_current_unsocket_key_is_shared_and_distinct_from_history(self):
        self.assertEqual(numeric.CELLS['jeweler_unsocket_gold'],
                         ('jeweler','operation_id','unsocket_current','gold'))
        before = numeric.render(self.module)
        self.edit('jeweler.csv', lambda rows: next(r for r in rows if r['operation_id']=='unsocket_historical').update(
            name='Remove gem (non-destroying)',gold='1'))
        self.assertEqual(before, numeric.render(self.module))
        self.edit('jeweler.csv', lambda rows: next(r for r in rows if r['operation_id']=='unsocket_historical').update(
            operation_id='unsocket_current'))
        with self.assertRaises(ValueError):
            numeric.generate(self.module)
        with self.assertRaises(ValueError):
            jeweler.generate()


if __name__ == '__main__':
    unittest.main()

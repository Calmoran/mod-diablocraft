"""Class start contract: preserved baseline, class isolation, fail-before-write."""
import contextlib
import csv
import io
from pathlib import Path
import shutil
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_sql import (CLASS_START_MIGRATION, MODULE_ROOT, DataError, class_start_rows,
                          generate_class_starts, render_class_starts, render_table, starter_candidates)


class ClassStartTests(unittest.TestCase):
    def setUp(self):
        scratch = MODULE_ROOT.parent / 'azerothcore-wotlk/build/_agent-scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='class-starts-test-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('data/d3', 'data/tunables', 'data/generated', 'data/sql/db-world/updates'):
            (self.root / directory).mkdir(parents=True)
        # Explicit, deliberately empty authority; the guard fails closed without it.
        (self.root / 'data/sql/applied_migrations.csv').write_text(
            "path,sha1,provenance\n", encoding="utf-8")
        for name in ('class_starts.csv', 'rarity_tiers.csv', 'base_items.csv'):
            shutil.copyfile(MODULE_ROOT / 'data/d3' / name, self.root / 'data/d3' / name)
        shutil.copyfile(MODULE_ROOT / 'data/tunables/crafting.csv', self.root / 'data/tunables/crafting.csv')
        shutil.copyfile(MODULE_ROOT / 'data/tunables/paragon.csv', self.root / 'data/tunables/paragon.csv')
        self.path = self.root / 'data/d3/class_starts.csv'
        # The applied, frozen class-start migrations: the legacy-character render
        # reads which classes they already profiled (diablocraft-class-parity, diablocraft-1cuvw, diablocraft-im7mr.1, diablocraft-txze9).
        self.frozen = []
        for name in ('world_0012_class_starts.sql', 'world_0040_class_starts.sql', 'world_0048_class_starts.sql',
                     'world_0060_class_starts.sql', 'world_0066_class_starts.sql', 'world_0072_class_starts.sql',
                     'world_0078_class_starts.sql'):
            self.frozen.append(self.root / 'data/sql/db-world/updates' / name)
            shutil.copyfile(MODULE_ROOT / 'data/sql/db-world/updates' / name, self.frozen[-1])

    def rows(self):
        with self.path.open(newline='') as stream:
            return list(csv.DictReader(stream))

    def write(self, rows):
        with self.path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.rows_header))
            writer.writeheader()
            writer.writerows(rows)

    @property
    def rows_header(self):
        return ['class_id', 'class_key', 'class_name', 'row_type', 'slot', 'rarity',
                'count_key', 'spell_id', 'skill_id', 'base_type', 'base_slot', 'designated_class', 'source']

    def test_barbarian_projection_and_all_proficiencies_preserved(self):
        profiles = class_start_rows(self.path)
        # The Wizard (WoW class 8) joined in diablocraft-class-parity item 5;
        # the Barbarian's profile below is unchanged by it, and by the Monk (12), the Crusader (2), the Necromancer (13) and the
        # Demon Hunter (3), the Witch Doctor (14) and the Shaman (7).
        self.assertEqual(set(profiles), {1, 2, 3, 7, 8, 12, 13, 14})
        profile = profiles[1]
        self.assertEqual((profile['class_key'], profile['class_name']), ('barbarian', 'Barbarian'))
        header = ['slot', 'rarity', 'count']
        values = [(i + 2, [str(row[key]) for key in header]) for i, row in enumerate(profile['kit'])]
        sql, count = render_table(self.path.with_name('starter_kit.csv'), ('count', '', 'slot rarity'),
                                  source_rows=(header, values))
        self.assertEqual(sql.encode(), (MODULE_ROOT / 'data/generated/starter_kit.sql').read_bytes())
        self.assertEqual(count, 12)
        self.assertEqual(sum(row['count'] for row in profile['kit']), 13)
        # The removed GrantEquipmentSkills map, recorded as the regression oracle, plus the stock Dual Wield
        # (spell 674, skill 118; ruling 2026-10-11, diablocraft-xecwl).
        self.assertEqual({(r['spell_id'], r['skill_id']) for r in profile['skills']},
                         {(196,44),(197,172),(198,54),(199,160),(200,229),(201,43),
                          (202,55),(227,136),(9116,433),(15590,473),(1180,173),(750,293),(674,118)})

    def test_fixture_second_class_has_own_rarity_and_skill_profile(self):
        # Synthetic fixture only: no second class content is enabled or shipped. Class 4 (the Rogue slot) has no profile.
        rows = self.rows()
        self.assertNotIn('4', {r['class_id'] for r in rows})
        extra = [dict(r, class_id='4', class_key='fixture', class_name='Fixture') for r in rows if r['class_id'] == '1']
        next(r for r in extra if r['slot'] == 'mainhand')['rarity'] = 'rare'
        for row in extra:
            if row['designated_class']:
                row['designated_class'] = 'fixture'
        self.write(rows + extra)
        profiles = class_start_rows(self.path)
        self.assertEqual(profiles[1]['kit'][0]['rarity'], 'legendary')
        self.assertEqual(profiles[4]['kit'][0]['rarity'], 'rare')
        self.assertEqual(len(profiles[1]['skills']), 13)
        self.assertEqual(profiles[4]['class_key'], 'fixture')

    def test_sourced_hand_candidates_and_empty_pool_refusal(self):
        profiles = class_start_rows(self.path)
        with self.path.with_name('base_items.csv').open() as stream:
            bases = list(csv.DictReader(stream))
        expected = {(1, 'mainhand'): ('Mighty Weapon', 'onehand', 'barbarian'),
                    (1, 'offhand'): ('Shield', 'offhand', ''),
                    (8, 'mainhand'): ('Wand', 'onehand', 'wizard'),
                    (8, 'offhand'): ('Source', 'offhand', 'wizard'),
                    (12, 'mainhand'): ('Fist Weapon', 'onehand', 'monk'),
                    (12, 'offhand'): ('Fist Weapon', 'onehand', 'monk'),
                    (2, 'mainhand'): ('Flail', 'onehand', 'crusader'),
                    (2, 'offhand'): ('Crusader Shield', 'offhand', 'crusader'),
                    (13, 'mainhand'): ('Scythe', 'onehand', 'necromancer'),
                    (13, 'offhand'): ('Phylactery', 'offhand', 'necromancer'),
                    (3, 'mainhand'): ('Bow', 'twohand', 'demonhunter'),
                    (3, 'offhand'): ('Quiver', 'offhand', 'demonhunter'),
                    (14, 'mainhand'): ('Ceremonial Knife', 'onehand', 'witchdoctor'),
                    (14, 'offhand'): ('Mojo', 'offhand', 'witchdoctor')}
        for (cid, slot), wanted in expected.items():
            kit = next(r for r in profiles[cid]['kit'] if r['slot'] == slot)
            candidates = starter_candidates(profiles[cid], kit, bases)
            self.assertTrue(candidates, (cid, slot))
            self.assertEqual({(r['type'], r['slot'], r['designated_class']) for r in candidates}, {wanted})
        rows = self.rows()
        next(r for r in rows if r['class_id'] == '1' and r['slot'] == 'offhand')['designated_class'] = 'barbarian'
        self.write(rows)
        with self.assertRaisesRegex(DataError, 'Empty starter pool: barbarian offhand'):
            generate_class_starts(self.root)
        self.assertEqual(sorted(self.root.rglob('*.sql')), sorted(self.frozen))

    def test_floor_is_csv_owned_and_can_be_zero(self):
        sql, _ = render_class_starts(self.root)
        self.assertIn("'paragon', 'starting_paragon_level', NULL, 200.0, 'level'", sql)
        path = self.root / 'data/tunables/paragon.csv'
        path.write_text(path.read_text().replace(',,200,level', ',,0,level'))
        self.assertIn("'starting_paragon_level', NULL, 0.0", render_class_starts(self.root)[0])

    def test_invalid_contracts_refuse_before_any_sql_write(self):
        original = self.rows()
        variants = [original + [original[0]], original + [original[-1]],
                    [r for r in original if r['row_type'] != 'skill'], [],
                    [dict(r, class_key='different') if i == 1 else r for i, r in enumerate(original)],
                    [dict(r, class_id='256') for r in original],
                    [dict(r, rarity='missing') if i == 0 else r for i, r in enumerate(original)],
                    [dict(r, count_key='missing_seed') if i == 0 else r for i, r in enumerate(original)]]
        for rows in variants:
            with self.subTest(rows=rows[:1]):
                self.write(rows)
                with self.assertRaises((DataError, ValueError)):
                    generate_class_starts(self.root)
                self.assertEqual(sorted(self.root.rglob('*.sql')), sorted(self.frozen))

    def test_copies_rerun_and_manifest_guard(self):
        import hashlib
        with contextlib.redirect_stdout(io.StringIO()):
            generate_class_starts(self.root)
            before = {p: p.read_bytes() for p in self.root.rglob('*.sql') if p not in self.frozen}
            # Mirror and migration (identical), plus the characters companion.
            self.assertEqual(len(before), 3)
            migration = self.root / 'data/sql/db-world/updates' / CLASS_START_MIGRATION
            self.assertEqual(before[migration], before[self.root / 'data/generated/class_starts.sql'])
            generate_class_starts(self.root)
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            # List the migration as applied, then change an input. The applied
            # file stays frozen and the generator warns; only the generated
            # mirror (not a migration) may change. applied_migrations.csv, not a
            # per-generator list, is what says the file is applied.
            digest = hashlib.sha1(migration.read_bytes()).hexdigest().upper()
            (self.root / 'data/sql/applied_migrations.csv').write_text(
                'path,sha1,provenance\n'
                f'db-world/updates/{CLASS_START_MIGRATION},{digest},test\n',
                encoding='utf-8', newline='\n')
            rows = self.rows()
            for row in rows:
                row['class_name'] = 'Changed label'
            self.write(rows)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                generate_class_starts(self.root)
            self.assertIn('WARNING', buffer.getvalue())
            self.assertIn(CLASS_START_MIGRATION, buffer.getvalue())
            self.assertEqual(before[migration], migration.read_bytes())


if __name__ == '__main__':
    unittest.main()

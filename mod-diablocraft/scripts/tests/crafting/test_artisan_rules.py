"""Offline artisan policy regressions; production SQL against in-memory fixtures."""
import contextlib
import csv
import io
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import crafting_source  # noqa: E402
import harness_env
import tempfile
import unittest

import generate_crafting as generator
from test_crafting_queries import cpp_queries


class ArtisanRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = crafting_source.source()
        cls.queries = cpp_queries(cls.source)

    def setUp(self):
        self.blacksmith, self.mystic = generator.artisan_rule_rows()

    def test_source_matrix_preserves_existing_policy_without_class_columns(self):
        self.assertEqual(len(self.blacksmith), 11)
        self.assertEqual(len(self.mystic), 9)
        self.assertEqual(len({r['recipe_slot'] for r in self.blacksmith}), 10)
        self.assertTrue(all(r['output_rarity'] == 'rare' and not r['base_rarity'] for r in self.blacksmith))
        self.assertFalse(any('class_id' in r for r in self.blacksmith + self.mystic))
        # diablocraft-xw2m (the designer: follow the data): Arcane Dust and Veiled Crystal, 3 each on a weapon or
        # armor and 2 each on a rare ring or amulet; a legendary or set ring or amulet pays one gem only.
        for row in self.mystic:
            jewelry = row['slot'] in ('neck', 'finger')
            gem = jewelry and row['rarity'] != 'rare'
            self.assertEqual(row['payment_kind'], 'gem' if gem else 'gold')
            if gem:
                self.assertEqual((row['material_1_entry'], row['material_2_entry'], row['material_count']), ('', '', ''))
            else:
                self.assertEqual((int(row['material_1_entry']), int(row['material_2_entry'])), (102002, 102003))
                self.assertEqual(int(row['material_count']), 2 if jewelry else 3)
            self.assertEqual(row['gem_tier'], 'Imperial' if gem else '')
            self.assertEqual(row['gem_count_rule'], 'mystic_jewelry_gem_count' if gem else '')

    def test_actual_candidate_query_includes_every_class_without_changing_recipe_ids(self):
        query, = [q for q in self.queries if q.startswith('SELECT b.entry FROM dc_base_item b JOIN dc_blacksmith_rule r ')]
        self.assertNotIn('usable_by', query)
        self.assertNotIn('class', query.lower())
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE dc_base_item(entry INTEGER,slot TEXT,rarity TEXT,pool_version TEXT,level_req INTEGER)')
            db.execute('CREATE TABLE dc_blacksmith_rule(recipe_slot TEXT,base_slot TEXT,base_rarity TEXT,output_rarity TEXT)')
            db.executemany('INSERT INTO dc_blacksmith_rule VALUES (?,?,?,?)',
                           [(r['recipe_slot'],r['base_slot'],r['base_rarity'],r['output_rarity']) for r in self.blacksmith])
            bases = generator.read('base_items.csv')
            # IDs in this SQL fixture are row indexes only, never published item IDs.
            db.executemany('INSERT INTO dc_base_item VALUES (?,?,?,?,?)',
                           [(i,r['slot'],r['rarity'],r['pool_version'],int(r['level_req']) if r['level_req'] else None)
                            for i,r in enumerate(bases)])
            slots = {r['recipe_slot'] for r in self.blacksmith}
            for slot in slots:
                matches = {i for i, in db.execute(query.format(slot, 'rare', 70))}
                expected = {i for i,r in enumerate(bases) if r['pool_version']=='yes' and not r['rarity']
                            and (not r['level_req'] or int(r['level_req'])<=70)
                            and r['slot'] in (('onehand','twohand') if slot=='mainhand' else (slot,))}
                self.assertEqual(matches, expected, slot)
                self.assertTrue(matches)
            waist = {i for i, in db.execute(query.format('waist', 'rare', 70))}
            self.assertTrue(any(bases[i]['d3_id']=='BarbBelt_206' for i in waist))
            self.assertEqual(list(db.execute(query.format('neck', 'rare', 70))), [])

    def test_actual_mystic_query_exact_slot_then_fallback_and_shared_quote_charge(self):
        query, = [q for q in self.queries if 'FROM dc_mystic_rule WHERE' in q]
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE dc_mystic_rule(rarity TEXT,slot TEXT,payment_kind TEXT,material_1_entry INTEGER,material_2_entry INTEGER,material_count INTEGER,gem_tier TEXT,gem_count_rule TEXT)')
            db.executemany('INSERT INTO dc_mystic_rule VALUES (?,?,?,?,?,?,?,?)',
                           [(r['rarity'],r['slot'],r['payment_kind'],int(r['material_1_entry'] or 0),int(r['material_2_entry'] or 0),int(r['material_count'] or 0),r['gem_tier'],r['gem_count_rule']) for r in self.mystic])
            for rarity in ('rare','legendary','set'):
                for slot in ('neck','finger','waist','onehand'):
                    row, = db.execute(query.format(rarity, slot)).fetchall()
                    gem = slot in ('neck','finger') and rarity != 'rare'
                    self.assertEqual(row[0], 'gem' if gem else 'gold')
                    self.assertEqual(row[1:4], (0,0,0) if gem else (102002,102003,2 if slot in ('neck','finger') else 3))
            self.assertEqual(list(db.execute(query.format('magic','waist'))), [])
        self.assertEqual(self.source.count('CostOf(player, instance)'), 2)
        self.assertEqual(self.source.count('mystic_cost_multiplier'), 0)
        screen = (generator.MODULE / 'lua/aio/dc_crafting.lua').read_text()
        self.assertNotIn('mystic_base_gold', screen)
        self.assertNotIn('mystic_cost_multiplier', screen)
        # Artisan() is Reachable() (the player's own half) plus the NPC check; both must stay.
        reachable = self.source.split('void Reachable(', 1)[1].split('Creature* Artisan(', 1)[0]
        artisan = self.source.split('Creature* Artisan(', 1)[1].split('std::vector<Item*> Inventory', 1)[0]
        access = reachable + artisan
        self.assertIn('player->IsAlive()', reachable)
        self.assertIn('IsInCombat', reachable)
        self.assertIn('GetTradeData', reachable)
        self.assertIn('Reachable(player);', artisan)
        self.assertIn('GetNPCIfCanInteractWith', artisan)
        self.assertNotIn('getClass()', access)

    @staticmethod
    def definition(marker, source):
        """One function cut out of the module, braces balanced, exactly as it is."""
        assert source.count(marker) == 1, marker
        begin = source.index(marker)
        index = source.index('{', begin) + 1
        depth = 1
        while depth:
            depth += (source[index] == '{') - (source[index] == '}')
            index += 1
        return source[begin:index]

    @staticmethod
    def sheet_rows(path, table):
        text = path.read_text(encoding='utf-8')
        columns, body = re.search(r"INSERT INTO `%s` \(([^)]*)\) VALUES\n(.*?);\n" % table, text, re.S).groups()
        names = [name.strip(' `') for name in columns.split(',')]
        return [dict(zip(names, next(csv.reader([line.rstrip(',')[1:-1]], quotechar="'", skipinitialspace=True))))
                for line in body.split('\n')]

    def primary_stat_program(self, source):
        """The production main-stat resolver, driven by the generated class sheet.

        diablocraft-class-roll-rules: PrimaryStat takes the item's affix class
        (the roll class for an ordinary base, the Mystic re-roller's class at an
        artisan) and the sheet; a designated base keeps its own class's stat."""
        extract = '\n'.join(self.definition(marker, source) for marker in (
            'std::string ClassKey(std::string const& d3Class)',
            'std::string StatAffix(std::string const& stat)',
            'std::set<std::string> ResolveMainStats(',
            'std::string PrimaryStat(BaseItem const& base, std::string const& affixClass,'))
        generated = generator.MODULE / 'data/generated'
        sheet = self.sheet_rows(generated / 'class_primary_stats.sql', 'dc_class_primary_stats')
        keys = [row['class_key'] for row in self.sheet_rows(generated / 'class_catalogue.sql', 'dc_class_map')]
        bases = {r['d3_id']: r for r in generator.read('base_items.csv') if r['pool_version']=='yes' and not r['rarity']}
        mighty, ordinary = bases['BarbBelt_206'], bases['Belt_207']
        self.assertEqual((mighty['usable_by'], mighty['designated_class']), ('barbarian', 'barbarian'))
        self.assertEqual((ordinary['usable_by'], ordinary['designated_class']), ('', ''))
        self.assertIn(mighty['designated_class'], keys)
        rows = ''.join('    sheet["%s"] = "%s";\n' % (row['class'], row['primary_stat']) for row in sheet)
        # Expected stats come from the same generated sheet, never a literal.
        wanted = {r['class'].lower().replace(' ', ''): {'Strength': 'str', 'Dexterity': 'dex',
                                                       'Intelligence': 'int'}[r['primary_stat']] for r in sheet}
        checks = ''.join(
            '    assert(PrimaryStat(mighty,"%s",mainStats)=="%s");\n'
            '    assert(PrimaryStat(ordinary,"%s",mainStats)=="%s");\n'
            % (key, wanted[mighty['designated_class']], key, wanted[key]) for key in keys)
        return ('#include <cassert>\n#include <cctype>\n#include <cstdint>\n#include <set>\n#include <string>\n'
                '#include <unordered_map>\n#define LOG_ERROR(...) ((void)0)\n'
                'struct BaseItem { std::uint32_t entry = 0; std::string name, designatedClass, mainStat; };\n'
                + extract + '\nint main() {\n    std::unordered_map<std::string, std::string> sheet, mainStats;\n'
                + rows + '    for (auto const& [name, stat] : sheet) mainStats[ClassKey(name)] = StatAffix(stat);\n'
                '    std::unordered_map<std::uint32_t, BaseItem> items;\n'
                '    items[1].entry = 1; items[1].designatedClass = "%s"; items[2].entry = 2;\n'
                '    assert(ResolveMainStats(items, mainStats).empty());\n'
                '    BaseItem const mighty = items[1], ordinary = items[2];\n' % mighty['designated_class']
                + checks + '}\n')

    def compile_and_run(self, program):
        scratch = generator.ROOT / 'azerothcore-wotlk/build/_agent-scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='artisan-primary-test-', dir=scratch) as tmp:
            path = Path(tmp)
            (path/'test.cpp').write_text(program)
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
            return harness_env.run([str(path/'test')]).returncode

    def test_existing_primary_stat_function_for_controlled_wizard_belts(self):
        source = items_source.source()
        # A designated (Mighty) belt keeps its own class's stat for every roll
        # class; an ordinary belt takes the roll class's stat.
        self.assertEqual(self.compile_and_run(self.primary_stat_program(source)), 0)

    def test_primary_stat_policy_mutation_is_caught(self):
        source = items_source.source()
        guard = '    if (base.designatedClass.empty())\n        if (auto found = mainStats.find(affixClass);'
        self.assertEqual(source.count(guard), 1)
        # Mutation: the roll class overrides a designated item's own stat.
        mutated = source.replace(guard, '    if (true)\n        if (auto found = mainStats.find(affixClass);')
        self.assertNotEqual(self.compile_and_run(self.primary_stat_program(mutated)), 0)

    def test_copies_idempotence_validation_and_applied_history(self):
        scratch = generator.ROOT / 'azerothcore-wotlk/build/_agent-scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='artisan-rules-test-', dir=scratch) as tmp:
            module = Path(tmp)
            shutil.copytree(generator.DATA, module/'data/d3')
            shutil.copytree(generator.TUNABLES, module/'data/tunables')
            (module/'data/generated').mkdir()
            (module/'data/sql/db-world/updates').mkdir(parents=True)
            # Explicit, deliberately empty authority; the guard fails closed without it.
            (module/'data/sql/applied_migrations.csv').write_text(
                'path,sha1,provenance\n', encoding='utf-8')
            old = generator.MODULE, generator.DATA, generator.TUNABLES, generator.tunable_integer
            from tunable_values import integer
            generator.MODULE, generator.DATA, generator.TUNABLES = module, module/'data/d3', module/'data/tunables'
            generator.tunable_integer = lambda category,name,**kwargs: integer(category,name,module=module,**kwargs)
            try:
                generator.generate_artisan_rules()
                before = {p:p.read_bytes() for p in module.rglob('*.sql')}
                self.assertEqual(len(before),2)
                self.assertEqual(len(set(before.values())),1)
                generator.generate_artisan_rules()
                self.assertEqual(before,{p:p.read_bytes() for p in before})
                # List the migration as applied. A changed render is now frozen
                # and warned about by the shared manifest guard; applied_migrations
                # .csv, not a per-generator list, is the authority.
                import hashlib
                migration = module/'data/sql/db-world/updates/crafting_0004_class_artisans.sql'
                digest = hashlib.sha1(migration.read_bytes()).hexdigest().upper()
                (module/'data/sql/applied_migrations.csv').write_text(
                    'path,sha1,provenance\n'
                    f'db-world/updates/crafting_0004_class_artisans.sql,{digest},test\n',
                    encoding='utf-8', newline='\n')
                path = generator.DATA/'mystic_rules.csv'
                original = path.read_text()
                path.write_text(original + original.splitlines()[1] + '\n')
                with self.assertRaisesRegex(ValueError,'duplicate'):
                    generator.generate_artisan_rules()
                self.assertEqual(before,{p:p.read_bytes() for p in before})
                path.write_text(original.replace('rare,neck,gold','rare,head,gold'))
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    generator.generate_artisan_rules()
                self.assertIn('WARNING', buffer.getvalue())
                self.assertIn('crafting_0004_class_artisans.sql', buffer.getvalue())
                self.assertEqual(before[migration], migration.read_bytes())
            finally:
                generator.MODULE, generator.DATA, generator.TUNABLES, generator.tunable_integer = old


if __name__ == '__main__':
    unittest.main()

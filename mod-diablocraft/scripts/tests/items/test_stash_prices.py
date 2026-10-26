"""CSV -> generated SQL -> production BuyTab/GoldCost, in disposable fixtures.

Run from the repo root: python3 mod-diablocraft/scripts/tests/items/test_stash_prices.py
The C++ harness doubles account storage; it does not test a running server.
"""
import csv
import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_account_economy as generator
import fixture_db
import harness_env
import test_stash_moves_runtime as stash

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/stash-prices"
MIGRATION = Path("data/sql/db-world/updates/stash_0002_tab_prices.sql")
MIRROR = Path("data/generated/stash_0002_tab_prices.sql")


def prices(sql):
    return {int(tab): None if price == "NULL" else int(price)
            for tab, price in re.findall(r"\((\d+),\s*(NULL|\d+)\)", sql)}


def build(folder):
    # Reuse the existing stash doubles, but compile the actual denomination
    # function: the older move harness's GoldCost double still multiplies by 10k.
    template = stash.TEMPLATE.read_text()
    template = template.replace('    constexpr uint32 GoldBarEntry = 909999;\n', '')
    template = template.replace('    inline uint64 GoldCost(uint64 gold) { return gold * 10000; }\n', '')
    template = template.replace('CanAfford(Player* player', 'CanAfford(Player const* player')
    old = '''        if (statement.find("FROM dc_stash_tuning") != std::string::npos)
            return db.price ? std::make_shared<Row>(Row{{Field{db.price}}}) : nullptr;'''
    new = '''        if (statement.find("FROM dc_stash_tuning") != std::string::npos)
        {
            unsigned next = 0;
            CHECK(std::sscanf(statement.c_str() + statement.find("next_tab="), "next_tab=%u", &next) == 1);
            auto found = generatedPrices.find(next);
            return found == generatedPrices.end() ? nullptr : std::make_shared<Row>(Row{{Field{found->second}}});
        }'''
    assert template.count(old) == 1
    template = template.replace(old, new)
    template = template.replace('struct DatabaseDouble', 'static std::map<unsigned, uint64> generatedPrices;\nstruct DatabaseDouble')
    template = '#include <fstream>\n#include "' + str(MODULE / 'src/common/dc_economy.h') + '"\n' + template
    flag, entry, flags = stash.cache_template()  # the harness's bound-cache placeholders (diablocraft-rxvzd)
    template = template.replace('@HEADER@', str(stash.HEADER)).replace('@PRODUCTION@', stash.production())
    template = template.replace('@BOUND_FLAG@', str(flag)).replace('@CACHE_ENTRY@', str(entry)).replace('@CACHE_FLAGS@', str(flags))
    template = template.replace('int main(int argc, char** argv)', 'int OriginalMain(int argc, char** argv)')
    template += r'''
int main(int argc, char** argv)
{
    using namespace DC::Stash;
    CHECK(argc == 3);
    std::ifstream input(argv[1]);
    unsigned tab;
    std::string actual;
    uint64 expected;
    std::map<unsigned, uint64> expectedPrices;
    while (input >> tab >> actual >> expected)
    {
        if (actual != "NULL") generatedPrices[tab] = std::stoull(actual);
        expectedPrices[tab] = expected;
    }
    CHECK(expectedPrices.size() == 4);
    Reset();
    auto const key = std::make_pair(Account, std::string("normal"));
    if (std::string(argv[2]) == "unset")
    {
        player.gold = expectedPrices.at(2);
        std::string message;
        CHECK(!Try([] { BuyTab(&player); }, &message));
        CHECK(message == "The price of that stash tab is not set yet.");
        CHECK(player.gold == expectedPrices.at(2));
        CHECK(db.stash.at(key).first == 1 && db.committed == 0);
        return 0;
    }
    for (auto const& entry : expectedPrices)
    {
        CHECK(entry.second > 0);
        player.gold = entry.second - 1;
        std::string message;
        CHECK(!Try([] { BuyTab(&player); }, &message));
        CHECK(player.gold == entry.second - 1);
        CHECK(db.stash.at(key).first == int(entry.first - 1));
        CHECK(db.committed == int(entry.first - 2));
        player.gold = entry.second;
        CHECK(Try([] { BuyTab(&player); }, &message));
        CHECK(player.gold == 0);
        CHECK(db.stash.at(key).first == int(entry.first));
        CHECK(containers.at(Key{Account, false}).tabs == entry.first);
        CHECK(db.committed == int(entry.first - 1));
        Relog(); // next purchase uses the durable tab count
    }
    player.gold = expectedPrices.at(5);
    std::string message;
    CHECK(!Try([] { BuyTab(&player); }, &message));
    CHECK(message == "All 5 stash tabs are already yours.");
    CHECK(player.gold == expectedPrices.at(5));
    CHECK(db.stash.at(key).first == 5 && db.committed == 4);
    std::puts("PASS generated prices: tabs 2-5, short purse, exact purse, relog, sixth refusal");
}
'''
    source = folder / "prices.cpp"
    source.write_text(template)
    binary = folder / "prices"
    subprocess.run(["g++", "-std=c++17", "-O0", "-g", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=undefined", str(source), "-o", str(binary)], check=True)
    return binary


class StashPrices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=SCRATCH)
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.binary = build(cls.folder)

    def setUp(self):
        self.root = self.folder / self._testMethodName
        self.root.mkdir()
        self.assertTrue(self.root.is_relative_to(self.folder))
        for path in ("data/tunables/economy.csv", "data/d3/account_economy.csv",
                     "data/sql/db-world/updates/stash_0001_tuning.sql"):
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(MODULE / path, dest)
        (self.root / 'data/sql/applied_migrations.csv').write_text('path,sha1,provenance\n')

    def edit(self, name, value, d3=""):
        path = self.root / "data/tunables/economy.csv"
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        matches = [row for row in rows if row['name'] == name]
        self.assertEqual(len(matches), 1, name)
        matches[0]['value'], matches[0]['d3_value'] = str(value), str(d3)
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def generate(self):
        generator.generate(self.root)
        path = self.root / MIGRATION
        # On the base the generator has no stash output: drive the same
        # production function with the existing NULL rows, not a fake price.
        if not path.exists():
            path = self.root / "data/sql/db-world/updates/stash_0001_tuning.sql"
        return path.read_text()

    def run_prices(self, sql, expected=None, mode="purchases"):
        expected = expected or dict.fromkeys(range(2, 6), 100000)
        generated = prices(sql)
        self.assertEqual(set(generated), set(expected))
        data = self.root / "prices.txt"
        data.write_text(''.join(f"{tab} {generated[tab] if generated[tab] is not None else 'NULL'} {cost}\n"
                                for tab, cost in expected.items()))
        return harness_env.run([str(self.binary), str(data), mode], capture_output=True, text=True)

    def assert_purchases(self, sql, expected=None):
        result = self.run_prices(sql, expected)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_and_short_purse_each_tab_and_sixth_refused(self):
        self.assert_purchases(self.generate())

    def test_shipped_stash_outputs_match_the_csv_render(self):
        expected = generator.render_stash_prices(self.root)
        self.assertEqual((MODULE / MIGRATION).read_text(), expected)
        self.assertEqual((MODULE / MIRROR).read_text(), expected)
        with self.assertRaises(TypeError):
            generator.render_stash_prices()

    def test_each_csv_row_controls_its_own_tab(self):
        for tab in range(2, 6):
            with self.subTest(tab=tab):
                self.edit(f"stash_tab_{tab}_price_gold", 100000 + tab)
                expected = dict.fromkeys(range(2, 6), 100000)
                expected[tab] += tab
                sql = self.generate()
                self.assertEqual(prices(sql), expected)
                self.assert_purchases(sql, expected)
                self.edit(f"stash_tab_{tab}_price_gold", 100000)

    def test_blank_price_remains_null_and_purchase_refuses(self):
        self.edit("stash_tab_2_price_gold", "")
        sql = self.generate()
        self.assertIsNone(prices(sql)[2])
        result = self.run_prices(sql, mode="unset")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_d3_fallback_and_invalid_price_values(self):
        self.edit("stash_tab_2_price_gold", "", 100001)
        self.assertEqual(prices(self.generate())[2], 100001)
        for invalid in ("-1", "1.5", "NaN", "Infinity", str(2**64)):
            with self.subTest(value=invalid):
                self.edit("stash_tab_2_price_gold", invalid)
                with self.assertRaises(ValueError):
                    self.generate()

    def test_generated_mirror_and_frozen_migration_stay_together(self):
        sql = self.generate()
        self.assertEqual((self.root / MIRROR).read_text(), sql)
        manifest = self.root / 'data/sql/applied_migrations.csv'
        with manifest.open('a') as stream:
            stream.write(f"db-world/updates/{MIGRATION.name},{hashlib.sha1(sql.encode()).hexdigest().upper()},test fixture\n")
        self.edit("stash_tab_2_price_gold", 100001)
        self.generate()
        self.assertEqual((self.root / MIGRATION).read_text(), sql)
        self.assertEqual((self.root / MIRROR).read_text(), sql)

    def test_bad_generated_price_is_caught_by_production_purchase(self):
        sql = self.generate()
        self.assertIn('(2,100000)', sql)
        mutant = sql.replace('(2,100000)', '(2,1)')
        self.assertNotEqual(self.run_prices(mutant).returncode, 0)

    def test_single_rule_generator_mutants_are_caught(self):
        # Mutations exist only in memory, never in the checkout or another
        # worker's files; interruption cannot leave mutated production behind.
        source = Path(generator.__file__).read_text()
        self.edit('stash_tab_3_price_gold', 100003)
        expected = {2: 100000, 3: 100003, 4: 100000, 5: 100000}
        self.assertEqual(prices(generator.render_stash_prices(self.root)), expected)
        mutants = (
            ('same-row', 'f"stash_tab_{tab}_price_gold"', '"stash_tab_2_price_gold"'),
            ('hardcoded-price', 'values.append(f"({tab},{price})")', 'values.append(f"({tab},100000)")'),
            ('missing-last-tab', 'range(launch + 1, maximum + 1)', 'range(launch + 1, maximum)'),
        )
        for name, old, new in mutants:
            with self.subTest(mutant=name):
                self.assertEqual(source.count(old), 1)
                namespace = {'__file__': generator.__file__, '__name__': 'stash_price_mutant'}
                exec(compile(source.replace(old, new), '<' + name + '>', 'exec'), namespace)
                self.assertNotEqual(prices(namespace['render_stash_prices'](self.root)), expected)
        self.edit('stash_tab_2_price_gold', '')
        self.assertIsNone(prices(generator.render_stash_prices(self.root))[2])
        namespace = {'__file__': generator.__file__, '__name__': 'stash_price_mutant'}
        self.assertEqual(source.count('return "NULL"'), 1)
        exec(compile(source.replace('return "NULL"', 'return "0"'), '<blank-is-free>', 'exec'), namespace)
        self.assertIsNotNone(prices(namespace['render_stash_prices'](self.root))[2])

    def test_missing_duplicate_and_wrong_unit_are_refused(self):
        path = self.root / 'data/tunables/economy.csv'
        original = path.read_text()
        row = next(line for line in original.splitlines() if line.startswith('stash_tab_2_price_gold,'))
        for mutated in (original.replace(row + '\n', ''), original + row + '\n',
                        original.replace(row, row.replace(',gold,', ',count,'))):
            with self.subTest(csv=mutated):
                path.write_text(mutated)
                with self.assertRaises(ValueError):
                    generator.render_stash_prices(self.root)

    def test_zero_and_uint64_price_remain_exact(self):
        self.edit('stash_tab_2_price_gold', 0)
        self.edit('stash_tab_3_price_gold', 2**64 - 1)
        actual = prices(generator.render_stash_prices(self.root))
        self.assertEqual(actual[2], 0)
        self.assertEqual(actual[3], 2**64 - 1)

    def test_five_tab_client_button(self):
        # Insert before the harness rebuilds the frame to test style fallbacks.
        # Its locals and actual addon callbacks are used; no product Lua changes.
        script = self.root / 'five_tabs.lua'
        extra = '''
withTabs(4, 5)
assert(buyButton().text == "BUY TAB 5")
withTabs(5, 5)
assert(buyButton().text == "ALL TABS")
assert(tab(5).unlocked)
print("PASS fifth tab: ALL TABS")
'''
        original = (MODULE / 'scripts/tests/items/test_stash_client.lua').read_text()
        marker = '-- Member by member:'
        self.assertEqual(original.count(marker), 1)
        script.write_text(original.replace(marker, extra + marker))
        subprocess.run(['lua', str(script)], cwd=ROOT, check=True)

    def test_sql_apply_replay_and_each_changed_row(self):
        database = 'dc_stash_prices_' + uuid.uuid4().hex
        command = [fixture_db.mysql_exe(), '--defaults-file=' + str(fixture_db.defaults_file()),
                   '--no-login-paths', '-N', '-B']

        def sql(text, selected=True):
            result = subprocess.run(command + (['--database=' + database] if selected else []),
                                    input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 0, 'fixture SQL command failed')
            return result.stdout.strip()

        sql(f'CREATE DATABASE {database}', selected=False)
        self.addCleanup(sql, f'DROP DATABASE {database}', False)
        base = (self.root / 'data/sql/db-world/updates/stash_0001_tuning.sql').read_text().split('-- 910002')[0]
        sql(base)
        generated = self.generate()
        # Removing the upsert must leave the base NULL prices behind. The real
        # statement must replace them and remain replayable.
        mutant = generated.replace('INSERT INTO', 'INSERT IGNORE INTO').split('ON DUPLICATE KEY')[0] + ';'
        sql(mutant)
        self.assertEqual(sql('SELECT COUNT(*) FROM dc_stash_tuning WHERE price_gold IS NULL'), '4')
        sql(generated)
        sql(generated)
        self.assertEqual(sql('SELECT next_tab,price_gold FROM dc_stash_tuning ORDER BY next_tab'),
                         '\n'.join(f'{tab}\t100000' for tab in range(2, 6)))
        for tab in range(2, 6):
            self.edit(f'stash_tab_{tab}_price_gold', 100000 + tab)
            sql(self.generate())
            self.assertEqual(sql(f'SELECT price_gold FROM dc_stash_tuning WHERE next_tab={tab}'),
                             str(100000 + tab))
            self.edit(f'stash_tab_{tab}_price_gold', 100000)
        self.edit('stash_tab_2_price_gold', '')
        sql(self.generate())
        self.assertEqual(sql('SELECT price_gold IS NULL FROM dc_stash_tuning WHERE next_tab=2'), '1')


if __name__ == '__main__':
    unittest.main(verbosity=2)

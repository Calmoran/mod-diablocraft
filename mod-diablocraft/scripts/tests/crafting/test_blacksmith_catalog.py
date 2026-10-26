"""Mapped source join and checked Blacksmith requests, using production code."""
import csv
import unittest
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import crafting_source  # noqa: E402
import generate_blacksmith_catalog as catalog
from test_crafting_window import compile_window

class Catalogue(unittest.TestCase):
    def test_all_mapped_outputs_and_exact_costs(self):
        rows=catalog.read('blacksmith_catalog.csv')
        with (catalog.MODULE.parent/'docs/research/blacksmith-recipe-coverage.csv').open(encoding='utf-8-sig') as stream:
            audit=list(csv.DictReader(stream))
        source={r['recipe_sno']:r for r in audit if r['mapping_status']=='mapped'}
        self.assertEqual(len(rows),103)
        self.assertEqual(sum(int(r['enabled']) for r in rows),32)
        for r in rows:
            self.assertEqual(r['output_entry'],source[r['recipe_sno']]['wow_entry'])
            self.assertEqual(r['gold'],source[r['recipe_sno']]['gold'])
            self.assertEqual(r['item_level'],source[r['recipe_sno']]['item_level'])
        sql=catalog.render()
        self.assertEqual(sql.count('INSERT INTO dc_blacksmith_catalog VALUES'),103)
        self.assertNotIn('DROP TABLE',sql)
        self.assertNotIn('dc_tunables',sql,'the bar row belongs to the tunables migration, not this one')
        with sqlite3.connect(':memory:') as db:
            for statement in sql.splitlines():
                if statement.startswith(('CREATE TABLE','DELETE FROM','INSERT INTO dc_blacksmith_catalog')):
                    db.execute(statement)
            self.assertEqual(db.execute('SELECT COUNT(*),SUM(enabled) FROM dc_blacksmith_catalog').fetchone(),(103,32))
            self.assertEqual(db.execute('SELECT output_entry,gold_d3 FROM dc_blacksmith_catalog WHERE id=362204').fetchone(),(100004,1000))
            self.assertEqual(db.execute('SELECT item_entry,amount FROM dc_blacksmith_catalog_material WHERE recipe_id=362204 ORDER BY item_entry').fetchall(),[(102001,15),(102002,15),(102003,14)])

class MappedCraftQueries(unittest.TestCase):
    """The three SELECTs Craft(mapped=true) runs, cut out of dc_crafting.cpp and run on the generated catalogue and
    the real base-item rows: a disabled recipe says so, the output is exactly the catalogue entry, and an entry
    outside the pool (the three disabled Guardian set pieces) can never be crafted when it is enabled later."""
    cpp=crafting_source.source()

    @classmethod
    def query(cls,fragment):
        found=[m for m in __import__('re').findall(r'"(SELECT [^"]*)"',cls.cpp) if fragment in m]
        assert len(found)==1,fragment
        return found[0].replace('{}','?')

    def database(self):
        db=sqlite3.connect(':memory:')
        for statement in catalog.render().splitlines():
            if statement.startswith(('CREATE TABLE','DELETE FROM','INSERT INTO dc_blacksmith_catalog')):
                db.execute(statement)
        db.execute('CREATE TABLE dc_base_item (entry INT, pool_version TEXT)')
        ids={r['d3_id']:int(r['item_entry']) for r in catalog.read('base_item_ids.csv')}
        for r in catalog.read('base_items.csv'):
            db.execute('INSERT INTO dc_base_item VALUES (?,?)',(ids[r['d3_id']],r['pool_version']))
        return db

    def test_recipe_row_enabled_flag_and_exact_output(self):
        db=self.database()
        recipe=self.query('FROM dc_blacksmith_catalog WHERE id=')
        self.assertEqual(db.execute(recipe,(362204,)).fetchone(),('waist',1000,'rare',65,100004,1))
        enabled=[r['recipe_sno'] for r in catalog.read('blacksmith_catalog.csv') if r['enabled']=='1']
        disabled=[r['recipe_sno'] for r in catalog.read('blacksmith_catalog.csv') if r['enabled']=='0']
        self.assertEqual((len(enabled),len(disabled)),(32,71))
        for rid in disabled:
            self.assertEqual(db.execute(recipe,(int(rid),)).fetchone()[5],0,'the server refuses a disabled recipe: '+rid)
        self.assertIsNone(db.execute(recipe,(1,)).fetchone(),'an unknown id is refused')

    def test_base_query_is_the_pool_and_only_the_output(self):
        db=self.database()
        base=self.query('SELECT entry FROM dc_base_item WHERE entry=')
        self.assertIn("pool_version='yes'",base)
        for r in catalog.read('blacksmith_catalog.csv'):
            rows=db.execute(base,(int(r['output_entry']),)).fetchall()
            self.assertLessEqual(len(rows),1)
            if r['enabled']=='1':
                self.assertEqual(rows,[(int(r['output_entry']),)],'an enabled recipe must craft exactly its output: '+r['recipe_sno'])
        for entry in (100611,100539,100783):   # the Guardian set pieces: not in the pool
            self.assertEqual(db.execute(base,(entry,)).fetchall(),[])

class Requests(unittest.TestCase):
    def test_checked_mapped_forge_and_repair_scopes(self):
        ok,output=compile_window(r'''
        Rig r;
        assert(r.artisan("forge\t362204\t58")==Outcome::Handled);
        assert(r.game.calls.back()=="forge 362204 58");
        assert(r.game.gates.back()=="0");
        for (auto payload : {"forge\t362204\t0", "forge\t0\t1", "forge\t362204", "forge\t362204\t1\t2",
                             "repairitems\t3\t0", "repairitems\t1\t123", "repairitems\t0\t0", "repairquote\t-1\t0"}) {
            auto count=r.game.calls.size();
            assert(r.artisan(payload)==Outcome::Refused && r.game.calls.size()==count);
        }
        assert(r.artisan("repairquote\t1\t0")==Outcome::Handled);
        assert(r.has("DCARTISAN\tQ|1|0|987|1"));
        assert(r.artisan("repairquote\t0\t123")==Outcome::Handled);
        assert(r.has("DCARTISAN\tQ|0|123|987|1"));
        assert(r.artisan("repairitems\t0\t123")==Outcome::Handled);
        assert(r.game.calls.back()=="repairitems 0 123");
        assert(r.artisan("repairitems\t1\t0")==Outcome::Handled);
        assert(r.game.calls.back()=="repairitems 1 0");
        assert(r.artisan("repairitems\t2\t0")==Outcome::Handled);
        assert(r.game.calls.back()=="repairitems 2 0");
        r.game.gate="Leave combat";
        auto before=r.game.calls.size();
        assert(r.artisan("forge\t362204\t58")==Outcome::Refused);
        assert(r.artisan("repairitems\t2\t0")==Outcome::Refused);
        assert(r.game.calls.size()==before);
        ''')
        self.assertTrue(ok,output)

if __name__=='__main__': unittest.main()

"""Craft Jewelry's server half (diablocraft-0vt07.15): the Jeweler catalogue against D3's own recipe file and the
sheets, the SELECTs Craft(jewelry) runs, the Hellfire organs, the Amulet's fixed main stat and the Hellfire pair leaving
the drop pool."""
import csv
import re
import sqlite3
import struct
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import crafting_source  # noqa: E402
import decode_pow  # noqa: E402
import generate_jeweler_catalog as jewelry  # noqa: E402

MODULE = jewelry.MODULE
SOVEREIGN = {364041: ('Sovereign Amulet', 'neck', 100000, 'Marquise Ruby|Marquise Emerald|Marquise Topaz'),
             364042: ('Sovereign Ring', 'finger', 100466, 'Marquise Diamond|Marquise Amethyst')}
HELLFIRE = (364711, 398284, 398285, 398286)
AMULET_STATS = {398284: 'str', 398285: 'int', 398286: 'dex'}
ORGANS = {'DemonOrgan_SkeletonKing_x1': 103200, 'DemonOrgan_Ghom_x1': 103201, 'DemonOrgan_SiegeBreaker_x1': 103202,
          'DemonOrgan_Diablo_x1': 103203}


def hash_name(name):
    value = 0
    for letter in name.lower():
        value = (value * 33 + ord(letter)) & 0xffffffff
    return value if value < 0x80000000 else value - 0x100000000


def gam_rows():
    """RecipesJeweler.gam's recipe records: name, the recipe SNO, level, flags, gold, ingredients (GBID, amount)."""
    data = decode_pow.extract('GameBalance/RecipesJeweler.gam')
    offset, size = struct.unpack_from('<ii', data, 40 + 25 * 16)
    rows = {}
    for pos in range(offset + 16, offset + 16 + size, 336):
        name = data[pos:pos + 256].split(b'\0', 1)[0].decode('ascii')
        fields = struct.unpack_from('<8i', data, pos + 256)
        ingredients = [struct.unpack_from('<2i', data, pos + 288 + i * 8) for i in range(6)]
        rows[name] = {'sno': fields[2], 'level': fields[5], 'flags': fields[4], 'gold': fields[6],
                      'ingredients': [(g, n) for g, n in ingredients if n]}
    return rows


def database():
    db = sqlite3.connect(':memory:')
    for statement in jewelry.render().splitlines():
        if statement.startswith(('CREATE TABLE', 'DELETE FROM dc_jeweler', 'INSERT INTO dc_jeweler_catalog')):
            db.execute(statement)
    return db


class Catalogue(unittest.TestCase):
    @unittest.skipUnless(decode_pow.available(), 'the D3 archives are not on this machine')
    def test_every_row_is_D3s_own_recipe(self):
        game = gam_rows()
        sheet = jewelry.read('jeweler_catalog.csv')
        costs = jewelry.read('jeweler_catalog_materials.csv')
        self.assertEqual(len(sheet), 6)
        for row in sheet:
            record = game[row['recipe']]
            self.assertEqual((int(row['recipe_sno']), int(row['gold'])), (record['sno'], record['gold']), row['recipe'])
            mine = sorted((hash_name(c['d3_id']), int(c['amount'])) for c in costs if c['recipe_sno'] == row['recipe_sno'])
            self.assertEqual(mine, sorted(record['ingredients']), row['recipe'] + ': every ingredient and count')
            # Flag 1 is D3's plan (the Hellfire pair), flag 2 a plain recipe (the Sovereign pair). Torment has no plan
            # table, so every row is enabled and none is gated.
            self.assertEqual(record['flags'], 1 if 'Hellfire' in row['recipe'] else 2, row['recipe'])
            self.assertEqual(row['enabled'], '1', row['recipe'])

    def test_sovereign_pair_matches_the_sheets_and_the_gem_items(self):
        sql = jewelry.render()
        db = database()
        gems = {line.split("'")[5]: int(re.search(r'\((\d+),', line).group(1))
                for line in (MODULE / 'data/generated/crafting.sql').read_text(encoding='utf-8').splitlines()
                if line.startswith('INSERT INTO `dc_gem_item`') and "'Marquise'" in line}
        recipes = {r['slot']: r for r in jewelry.read('blacksmith_recipes.csv') if r['rank'] == 'Sovereign' and r['row_type'] == 'recipe'
                   and r['slot'] in ('neck', 'leftfinger', 'rightfinger')}
        recipes['finger'] = recipes['leftfinger']
        self.assertEqual(recipes['leftfinger'], {**recipes['rightfinger'], 'slot': 'leftfinger'}, 'the two hands are one recipe')
        for sno, (name, slot, base, gem_names) in SOVEREIGN.items():
            self.assertEqual(db.execute('SELECT name,slot,output_entry,rarity,item_level,required_level,gold_d3,enabled,page FROM dc_jeweler_catalog WHERE id=?', (sno,)).fetchone(),
                             (name, slot, base, 'rare', 70, 70, 18000, 1, 'amulets' if slot == 'neck' else 'rings'))
            self.assertEqual(int(recipes[slot]['gold']), 18000, 'blacksmith_recipes.csv names the same price')
            self.assertEqual(db.execute('SELECT item_entry,amount FROM dc_jeweler_catalog_material WHERE recipe_id=? ORDER BY item_entry', (sno,)).fetchall(),
                             sorted((gems[g], 1) for g in gem_names.split('|')))
        self.assertIn('Marquise Ruby + 1 Marquise Emerald + 1 Marquise Topaz', recipes['neck']['note'])
        self.assertIn('Marquise Diamond + 1 Marquise Amethyst', recipes['finger']['note'])
        self.assertEqual(sql.count('INSERT INTO dc_jeweler_catalog VALUES'), 6)

    def test_hellfire_rows_are_on_with_the_organs_and_the_amulets_souls(self):
        db = database()
        for sno in HELLFIRE:
            enabled, reason, gold, rarity, stat = db.execute('SELECT enabled,unavailable_reason,gold_d3,rarity,main_stat FROM dc_jeweler_catalog WHERE id=?', (sno,)).fetchone()
            self.assertEqual((enabled, reason, gold, rarity, stat), (1, '', 50000, 'legendary', AMULET_STATS.get(sno, '')))
            organs = db.execute("SELECT d3_id,item_entry,amount FROM dc_jeweler_catalog_material WHERE recipe_id=? AND d3_id LIKE 'DemonOrgan_%' ORDER BY d3_id", (sno,)).fetchall()
            self.assertEqual(organs, sorted((d3, entry, 1) for d3, entry in ORGANS.items()), 'one of each organ')
            souls = db.execute('SELECT item_entry,amount FROM dc_jeweler_catalog_material WHERE recipe_id=? AND item_entry=102004', (sno,)).fetchall()
            self.assertEqual(souls, [(102004, 10)] if sno in AMULET_STATS else [],
                             'the Amulet costs 10 Forgotten Souls on top of the organs; the Ring does not')

    def test_the_amulet_has_one_recipe_per_main_stat_and_nothing_else_fixes_one(self):
        db = database()
        self.assertEqual(db.execute("SELECT id,main_stat,output_entry FROM dc_jeweler_catalog WHERE main_stat<>'' ORDER BY id").fetchall(),
                         [(sno, stat, 101113) for sno, stat in sorted(AMULET_STATS.items())])

    def test_the_organs_are_bag_items_with_no_drop_source(self):
        sql = jewelry.render()
        rows = re.findall(r"^\((\d+),15,0,'([^']+(?:'')?[^']*)',(\d+),1,0,1,0,0,0,0,(\d+),0,0,(\d+),", sql, re.M)
        self.assertEqual([(int(r[0]), int(r[3]), int(r[4])) for r in rows], [(e, 2000000000, 60) for e in sorted(ORGANS.values())])
        self.assertEqual([r[1].replace("''", "'") for r in rows], ["Leoric's Regret", 'Vial of Putridness', 'Idol of Terror', 'Heart of Evil'])
        sheet = jewelry.read('hellfire_organs.csv')
        self.assertEqual({r['d3_id']: int(r['item_entry']) for r in sheet}, ORGANS)
        # Nothing hands them out yet: no loot, Kadala, Cube or bounty sheet names an organ's entry.
        for path in list((MODULE / 'data').rglob('*.csv')):
            if path.name in ('jeweler_catalog_materials.csv', 'hellfire_organs.csv'):
                continue
            text = path.read_text(encoding='utf-8-sig')
            for entry in ORGANS.values():
                self.assertNotRegex(text, r'(?<!\d)%d(?!\d)' % entry, '%s names organ %d' % (path.name, entry))

    @unittest.skipUnless(decode_pow.available(), 'the D3 archives are not on this machine')
    def test_the_organs_are_D3s_own_item_rows(self):
        data = decode_pow.extract('GameBalance/Items_Other.gam')
        offset, size = struct.unpack_from('<ii', data, 40 + 1 * 16)
        game = {}
        for pos in range(offset + 16, offset + 16 + size, 1304):
            name = data[pos:pos + 256].split(b'\0', 1)[0].decode('ascii')
            game[name] = (struct.unpack_from('<i', data, pos + 280)[0], struct.unpack_from('<i', data, pos + 308)[0])
        for row in jewelry.read('hellfire_organs.csv'):
            self.assertEqual(game[row['d3_id']], (int(row['item_level']), int(row['max_stack'])), row['d3_id'])

    def test_the_generator_refuses_an_enabled_recipe_with_a_missing_ingredient(self):
        real = jewelry.read
        def broken(name):
            rows = real(name)
            if name == 'jeweler_catalog_materials.csv':
                for r in rows:
                    if r['recipe_sno'] == '364711' and r['d3_id'] == 'DemonOrgan_Diablo_x1':
                        r['item_entry'] = '0'
            return rows
        jewelry.read = broken
        try:
            with self.assertRaises(ValueError):
                jewelry.render()
        finally:
            jewelry.read = real

    def test_the_generator_refuses_a_main_stat_on_a_ring(self):
        real = jewelry.read
        def stat(name):
            rows = real(name)
            if name == 'jeweler_catalog.csv':
                for r in rows:
                    if r['recipe_sno'] == '364711':
                        r['main_stat'] = 'str'
            return rows
        jewelry.read = stat
        try:
            with self.assertRaises(ValueError):
                jewelry.render()
        finally:
            jewelry.read = real

    def test_the_blacksmith_catalogue_has_no_jewelry(self):
        slots = {r['slot'] for r in jewelry.read('blacksmith_catalog.csv')}
        self.assertFalse(slots & {'neck', 'finger'})


class CraftQueries(unittest.TestCase):
    """The three SELECTs Craft(jewelry) runs, cut out of dc_crafting_shared.cpp and run on the generated catalogue."""
    cpp = crafting_source.source()

    def query(self, fragment):
        found = [m for m in re.findall(r'"(SELECT [^"]*)"', self.cpp) if fragment in m]
        self.assertEqual(len(found), 1, fragment)
        return found[0].replace('{}', '?')

    def test_recipe_and_materials_come_from_the_jeweler_tables(self):
        db = database()
        self.assertEqual(db.execute(self.query('FROM dc_jeweler_catalog WHERE id='), (364042,)).fetchone(), ('finger', 18000, 'rare', 70, 100466, 1, ''))
        self.assertEqual(db.execute(self.query('FROM dc_jeweler_catalog WHERE id='), (398286,)).fetchone(), ('neck', 50000, 'legendary', 70, 101113, 1, 'dex'))
        self.assertIsNone(db.execute(self.query('FROM dc_jeweler_catalog WHERE id='), (362204,)).fetchone(), 'a Blacksmith id is not a jewelry recipe')
        self.assertEqual(db.execute(self.query('FROM dc_jeweler_catalog_material WHERE recipe_id='), (364042,)).fetchall(), [(103005, 1), (103015, 1)])

    def test_craft_takes_the_jeweler_and_the_catalogue_by_the_flag(self):
        body = self.cpp[self.cpp.index('void Craft(Player* player, uint32 id, uint32 count, bool mapped, bool jewelry)'):]
        self.assertIn('Artisan(player, jewelry ? Jeweler : Blacksmith);', body[:400])
        self.assertIn('jewelry\n                ? WorldDatabase.Query("SELECT slot,gold_d3,rarity,item_level,output_entry,enabled,main_stat FROM dc_jeweler_catalog', body)

    def test_sovereign_outputs_are_in_the_drop_pool_bases_the_roll_reads(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE dc_base_item (entry INT, pool_version TEXT)')
        ids = {r['d3_id']: int(r['item_entry']) for r in jewelry.read('base_item_ids.csv')}
        for r in jewelry.read('base_items.csv'):
            db.execute('INSERT INTO dc_base_item VALUES (?,?)', (ids[r['d3_id']], r['pool_version']))
        base = self.query('SELECT entry FROM dc_base_item WHERE entry=')
        for sno, (_n, _s, entry, _g) in SOVEREIGN.items():
            self.assertEqual(db.execute(base, (entry,)).fetchall(), [(entry,)], 'Sovereign crafts exactly its output base')


class MainStatWiring(unittest.TestCase):
    """The recipe's fixed main stat reaches the roller and replaces the roll class's own, as text on the production source,
    each check run on a reverted copy."""
    craft = crafting_source.read('dc_crafting_shared.cpp')
    roll = (MODULE / 'src/items/dc_items_roll.cpp').read_text(encoding='utf-8')

    def checks(self, craft, roll):
        found = []
        if re.search(r'Items::RollQuality\(player, entry, level, 0, true\), mainStat\);', craft):
            found.append('craft passes the recipe stat')
        if re.search(r'mainStat\.empty\(\)\s*\? PrimaryStat\(base, affixClass, mainStats\)\s*: mainStat;', roll):
            found.append('roll uses it for the mainstat line')
        if re.search(r'!mainStat\.empty\(\) && mainStat != "str" && mainStat != "dex" && mainStat != "int"\)\s*return nullptr;', roll):
            found.append('roll refuses another id')
        return found

    def test_all_three_hold(self):
        self.assertEqual(len(self.checks(self.craft, self.roll)), 3)

    def test_each_mutation_loses_its_check(self):
        mutants = [(self.craft.replace('Items::RollQuality(player, entry, level, 0, true), mainStat);', 'Items::RollQuality(player, entry, level, 0, true));'), self.roll),
                   (self.craft, self.roll.replace(': mainStat;', ': PrimaryStat(base, affixClass, mainStats);')),
                   (self.craft, self.roll.replace('mainStat != "dex" && ', ''))]
        for craft, roll in mutants:
            self.assertEqual(len(self.checks(craft, roll)), 2)


class HellfireIsCraftOnly(unittest.TestCase):
    def test_both_bases_are_marked_and_the_migration_carries_exactly_them(self):
        ids = {r['d3_id']: int(r['item_entry']) for r in jewelry.read('base_item_ids.csv')}
        marked = {r['d3_name']: ids[r['d3_id']] for r in jewelry.read('base_items.csv')
                  if r['d3_name'].startswith('Hellfire') and r['craft_only'] == 'yes'}
        self.assertEqual(marked, {'Hellfire Ring': 100943, 'Hellfire Amulet': 101113})
        every = [r for r in jewelry.read('base_items.csv') if r['d3_name'].startswith('Hellfire')]
        self.assertEqual(len(every), 2, 'no other base carries the name')
        text = (MODULE / 'data/sql/db-world/updates/items_0056_base_item_craft_only.sql').read_text(encoding='utf-8')
        updates = re.findall(r"UPDATE `dc_base_item` SET `craft_only`='yes' WHERE `entry` IN \(([\d, ]+)\);", text)
        self.assertEqual([sorted(int(n) for n in u.split(',')) for u in updates], [[100943, 101113]])
        generated = (MODULE / 'data/generated/base_items.sql').read_text(encoding='utf-8')
        for entry in (100943, 101113):
            line = next(l for l in generated.splitlines() if l.startswith('(%d,' % entry))
            self.assertRegex(line, r"'yes', '', 'yes'\)[,;]$")

    def test_the_drop_pool_leaves_a_craft_only_base_out(self):
        rule = (MODULE / 'src/items/dc_roll_class.h').read_text(encoding='utf-8')
        self.assertIn('craftOnly != "yes"', rule)


if __name__ == '__main__':
    unittest.main()

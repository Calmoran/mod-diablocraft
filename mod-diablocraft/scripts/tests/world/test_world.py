"""World data checks without modifying the live database."""
import csv
import random
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'client-patch/dbc'))
import build_charbaseinfo
from build_warrior_proficiencies import add_proficiencies, EQUIPMENT_SKILLS
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_sql import read_item_displays, DataError, render_base_items, classify

ROOT=Path(__file__).resolve().parents[3]

# The starter kit's pool as HubWorld::OnStartup builds it (src/common/dc_world.cpp):
# pool_version 'yes' only, equippable by a Barbarian, and never an item designated
# to another class (05-items §3, 08-world W6).
def starter_eligible(base):
    if base['pool_version']!='yes': return False
    if base['usable_by'] and 'barbarian' not in base['usable_by'].split(';'): return False
    return base['designated_class'] in ('','barbarian')


class WorldTests(unittest.TestCase):
    def test_blood_elf_equipment_rules_preserve_stock_and_other_classes(self):
        stock = [(i + 1, skill, 1, 1, 128, 0, 0, 0)
                 for i, skill in enumerate(EQUIPMENT_SKILLS)]
        body = b''.join(struct.pack('<8I', *r) for r in stock)
        raw = struct.pack('<4s4I', b'WDBC', len(stock), 8, 32, 1) + body + b'\0'
        result = add_proficiencies(raw)
        self.assertEqual(result[20:20 + len(body)], body)
        self.assertEqual(result[-1:], b'\0')
        self.assertEqual(add_proficiencies(result), result)
        new = [struct.unpack_from('<8I', result, 20 + len(body) + i * 32)
               for i in range(len(stock))]
        self.assertEqual({r[1] for r in new}, set(EQUIPMENT_SKILLS))
        self.assertTrue(all(r[2:4] == (512, 1) for r in new))
        with self.assertRaises(ValueError): add_proficiencies(raw[:-1])

    def test_option_c_builder_writes_the_playable_classes_for_every_race(self):
        """Option C (ruling q-1001-37, 61e67110): the table lists only the playable classes
        (class_map.csv: Barbarian 1, Wizard 8 and, since diablocraft-1cuvw, Monk 12, since diablocraft-im7mr.1,
        Necromancer 13, Crusader 2, since diablocraft-vawmy.1 Demon Hunter 3 and, since diablocraft-vxrcu.1, Witch Doctor 14 and, since diablocraft-xnrvn.2, Shaman 7) for all ten races, 80 rows, and the builder
        is idempotent on its own output."""
        stock = struct.pack('<4s4I', b'WDBC', 1, 2, 2, 1) + bytes([1, 1]) + bytes([0])
        rows = build_charbaseinfo.wanted_pairs()
        self.assertEqual(len(rows), 80, "ten races x eight classes")
        self.assertEqual({c for _, c in rows}, {1, 2, 3, 7, 8, 12, 13, 14}, "only Barbarian, Crusader, Demon Hunter, Shaman, Wizard, Monk, Necromancer and Witch Doctor")
        self.assertEqual({r for r, _ in rows}, set(build_charbaseinfo.RACES), "every race")
        result = build_charbaseinfo.build(stock)
        self.assertEqual(result, struct.pack('<4s4I', b'WDBC', len(rows), 2, 2, 1)
                         + b''.join(bytes(row) for row in rows) + bytes([0]))
        self.assertEqual(build_charbaseinfo.build(result), result, "a second run changes the file")
        with self.assertRaises(ValueError): build_charbaseinfo.build(stock[:-1])

    def test_starter_pools_and_display_coverage(self):
        with (ROOT/'data/d3/base_items.csv').open(encoding='utf-8-sig') as f: bases=list(csv.DictReader(f))
        from generate_sql import class_start_rows
        kit = class_start_rows(ROOT/'data/d3/class_starts.csv')[1]['kit']
        self.assertEqual(sum(int(r['count']) for r in kit),13)
        self.assertEqual(len({r['slot'] for r in kit}),len(kit))
        displays=read_item_displays(ROOT/'data/d3/item_display.csv')
        for item in bases: self.assertGreater(displays[item['slot'],item['type']],0)
        for slot in kit:
            eligible=[b for b in bases if starter_eligible(b)
                and (b['slot'] in ('onehand','twohand') if slot['slot']=='mainhand' else b['slot']==slot['slot'])
                and (b['rarity']=='legendary' if slot['rarity']=='legendary' else not b['rarity'])]
            self.assertTrue(eligible,slot)
            if slot['slot']=='mainhand':
                for base in eligible:
                    item_class,subclass,inventory=classify(base,ROOT/'data/d3/base_items.csv',0,base)
                    self.assertEqual(item_class,2,base['d3_name'])
                    self.assertEqual(inventory,13 if base['slot']=='onehand' else 17,base['d3_name'])
                    if base['slot']=='onehand':
                        # These stock melee subclasses permit a shield. Polearm
                        # subclass 6 forbids it even with a one-hand inventory type.
                        self.assertIn(subclass,(0,4,7,13,14,15),base['d3_name'])
        _,sql,count=render_base_items(ROOT/'data/d3/base_items.csv')
        self.assertEqual(count,len(bases))
        self.assertIn('displayid is joined from item_display.csv',sql)

    def test_twenty_starter_legendary_weapons_are_never_another_class_item(self):
        # 05-items §3 / 08-world W6: the mainhand slot is the only legendary in
        # the kit and the only slot that ever offered another class's item
        # (Scrimshaw, a Witch Doctor spear). Twenty draws from the pool the
        # module builds, with the seed fixed so a regression is reproducible.
        with (ROOT/'data/d3/base_items.csv').open(encoding='utf-8-sig') as f: bases=list(csv.DictReader(f))
        pool=[b for b in bases if starter_eligible(b) and b['rarity']=='legendary'
              and b['slot'] in ('onehand','twohand')]
        self.assertGreaterEqual(len(pool),20)
        names={}
        for base in bases:
            names.setdefault(base['d3_name'],[]).append(base)
        rolls=random.Random(20260907).choices(pool,k=20)
        for base in rolls:
            self.assertIn(base['designated_class'],('','barbarian'),base['d3_name'])
            self.assertEqual(base['pool_version'],'yes',base['d3_name'])
            # Rule 1: the drawn row is the only version of that name in the pool.
            versions=[v for v in names[base['d3_name']] if v['pool_version']=='yes']
            self.assertEqual(len(versions),1,base['d3_name'])
        self.assertNotIn('Scrimshaw',[b['d3_name'] for b in pool])

    def test_every_item_name_has_exactly_one_pool_version(self):
        with (ROOT/'data/d3/base_items.csv').open(encoding='utf-8-sig') as f: bases=list(csv.DictReader(f))
        counts={}
        for base in bases:
            self.assertIn(base['pool_version'],('yes','no'),base['d3_id'])
            if base['pool_version']=='yes': counts[base['d3_name']]=counts.get(base['d3_name'],0)+1
        self.assertFalse([n for n,c in counts.items() if c!=1])

if __name__=='__main__': unittest.main()

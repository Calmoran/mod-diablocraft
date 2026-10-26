"""diablocraft-1cuvw, Monk 1a, and diablocraft-im7mr.1, Necromancer 1a: a created class (class ids 12 and 13) is the
parent's rows under its own identity, and the server and the client files agree. diablocraft-txze9, Crusader 1a: a
class on a stock slot (the Paladin, class 2) keeps every stock row and gains only the start rows of the races stock
lacks.

    python3 mod-diablocraft/scripts/tests/classes/test_class_creation.py

Cross-source: the committed client DBCs and the committed migration are compared with the stock extraction they were
copied from, and with each other. Covers only what the files hold; the core accepting classes 12 and 13 is core patch
0024 (Monk 1b, Necromancer 1b) and the in-game run is the test sheets'.
"""
import csv
import re
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
sys.path.insert(0, str(HERE))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_class_catalogue as catalogue  # noqa: E402
import generate_class_creation as g  # noqa: E402
import generate_class_proficiencies as proficiencies  # noqa: E402
import generate_sql  # noqa: E402
import test_class_records  # noqa: E402
from dbc_store import Store, schema  # noqa: E402

CLIENT = ROOT / "client-patch/dbc"
UPDATES = MODULE / "data/sql/db-world/updates"
MONK, WARRIOR = 12, 1
PALADIN = 2   # the Crusader's stock slot (decisions.md 2026-09-22 roster)
HUNTER = 3   # the Demon Hunter's stock slot (the same roster)
SHAMAN = 7   # the Shaman's stock slot (the Shaman build brief, decisions.md 2026-10-23)
MONK_FAMILY = 22   # the Monk's records' SpellClassSet (generate_spells.py CLASS_BLOCKS, decisions.md 2026-10-12)
CRUSADER_FAMILY = 24   # the Crusader's records' SpellClassSet (generate_spells.py CLASS_BLOCKS)
DEMON_HUNTER_FAMILY = 25   # the Demon Hunter's records' SpellClassSet (generate_spells.py CLASS_BLOCKS)
DUAL_WIELD_SKILL = 118   # ruling 2026-10-12: the Monk is dual fist weapons, and learns it as the Barbarian does
SQL = (UPDATES / "world_0047_class_monk.sql").read_text(encoding="utf-8")
NECROMANCER, WARLOCK = 13, 9
NECROMANCER_FAMILY = 23   # the Necromancer's records' SpellClassSet (generate_spells.py CLASS_BLOCKS, diablocraft-im7mr.5)
WARLOCK_RACES = {1, 2, 5, 7, 10}   # the stock CharBaseInfo.dbc's Warlock pairs
NECROMANCER_SQL = (UPDATES / "world_0059_class_necromancer.sql").read_text(encoding="utf-8")
WITCH_DOCTOR = 14   # the second created class on the Warlock's rows (diablocraft-vxrcu.1)
SHAMAN_FAMILY = 27   # the Shaman's records' SpellClassSet (generate_spells.py CLASS_BLOCKS, diablocraft-xnrvn.6)
WITCH_DOCTOR_FAMILY = 26   # the Witch Doctor's records' SpellClassSet (generate_spells.py CLASS_BLOCKS, diablocraft-vxrcu.5)
WITCH_DOCTOR_SQL = (UPDATES / "world_0075_class_witch_doctor.sql").read_text(encoding="utf-8")
# (class, parent, migration text) of every created class, in class id order.
CREATED = ((MONK, WARRIOR, SQL), (NECROMANCER, WARLOCK, NECROMANCER_SQL), (WITCH_DOCTOR, WARLOCK, WITCH_DOCTOR_SQL))
CRUSADER_SQL = (UPDATES / "world_0063_class_crusader.sql").read_text(encoding="utf-8")
DEMON_HUNTER_SQL = (UPDATES / "world_0069_class_demon_hunter.sql").read_text(encoding="utf-8")
SHAMAN_SQL = (UPDATES / "world_0081_class_shaman.sql").read_text(encoding="utf-8")


def only_monk(change):
    """A created_classes() double that plants `change` on the Monk's entry and leaves the others as they are."""
    original = g.created_classes
    return original, lambda module=g.MODULE: [dict(c, **change) if c["name"] == "Monk" else c for c in original(module)]


def table_rows(sql, table):
    """The `(ID,Data)` pairs of one INSERT in the migration."""
    block = sql.split(f"INSERT INTO `{table}` (`ID`,`Data`) VALUES\n", 1)[1].split(";", 1)[0]
    return [(int(i), float(v)) for i, v in re.findall(r"\((\d+),([-0-9.e+]+)\)", block)]


# Classes with a start profile and no generated spells yet (test_every_class_with_a_start_profile_is_playable): none, the Shaman
# (WoW class 7) being Playable since 2a. A class that gets a profile before its spells is named here until they land.
AWAITING_PLAYABLE = set()


class Identity(unittest.TestCase):
    def test_the_sheet_and_the_map_agree(self):
        created = g.created_classes()
        self.assertEqual([(c["name"], c["id"], c["parent"], c["power"], c["token"]) for c in created],
                         [("Crusader", 2, 2, "Energy", "PALADIN"), ("Demon Hunter", 3, 3, "Energy", "HUNTER"),
                          ("Shaman", 7, 7, "Rage", "SHAMAN"), ("Monk", 12, 1, "Runic Power", "MONK"),
                          ("Necromancer", 13, 9, "Runic Power", "NECROMANCER"), ("Witch Doctor", 14, 9, "Mana", "WITCHDOCTOR")])

    def test_the_client_row_is_the_parents_with_its_own_identity(self):
        columns = schema(ROOT, "chrclasses_dbc")
        stock = Store((g.STOCK / "ChrClasses.dbc").read_bytes(), columns)
        client = Store((CLIENT / "ChrClasses.dbc").read_bytes(), columns)
        self.assertNotIn(MONK, stock.rows)
        want = dict(stock.decode(WARRIOR), ID=MONK, DisplayPower=6, Name_Lang_enUS="Monk", Filename="MONK", SpellClassSet=MONK_FAMILY)
        self.assertEqual(client.decode(MONK), want)
        # Since 2a the Necromancer's records have their own family, and its client row carries it.
        self.assertNotIn(NECROMANCER, stock.rows)
        want = dict(stock.decode(WARLOCK), ID=NECROMANCER, DisplayPower=6, Name_Lang_enUS="Necromancer", Filename="NECROMANCER",
                    SpellClassSet=NECROMANCER_FAMILY)
        self.assertEqual(client.decode(NECROMANCER), want)
        # Since 2a (diablocraft-vxrcu.5) the Witch Doctor's records have their own family and its client row carries it; Mana is the
        # Warlock's own display power, so the overlay row changes nothing there.
        self.assertNotIn(WITCH_DOCTOR, stock.rows)
        want = dict(stock.decode(WARLOCK), ID=WITCH_DOCTOR, DisplayPower=0, Name_Lang_enUS="Witch Doctor", Filename="WITCHDOCTOR",
                    SpellClassSet=WITCH_DOCTOR_FAMILY)
        self.assertEqual(client.decode(WITCH_DOCTOR), want)
        self.assertEqual(g.spells.CLASS_BLOCKS["witch_doctor"].family, WITCH_DOCTOR_FAMILY)
        self.assertEqual(g.spells.CLASS_BLOCKS["witch_doctor"].records, (86000, 86199))
        # Since 2a (diablocraft-xnrvn.6) the Shaman's records have their own family and its client row carries it (the stock row,
        # the server's, keeps the stock Shaman's 11 for the stock-spell strip); Rage is the other thing its overlay row changes.
        columns = schema(ROOT, "chrclasses_dbc")
        shaman = Store((g.STOCK / "ChrClasses.dbc").read_bytes(), columns).decode(SHAMAN)
        self.assertEqual(Store((CLIENT / "ChrClasses.dbc").read_bytes(), columns).decode(SHAMAN),
                         dict(shaman, DisplayPower=1, Name_Lang_enUS="Shaman", SpellClassSet=SHAMAN_FAMILY))
        self.assertEqual(shaman["SpellClassSet"], 11)
        self.assertEqual(g.spells.CLASS_BLOCKS["shaman"].family, SHAMAN_FAMILY)
        self.assertEqual(g.spells.CLASS_BLOCKS["shaman"].records, (86300, 86499))
        self.assertEqual(g.spells.RESERVED_BLOCKS, {})

    def test_the_client_class_set_follows_the_records_family(self):
        self.assertEqual(g.spells.CLASS_BLOCKS["necromancer"].family, NECROMANCER_FAMILY)
        columns = schema(ROOT, "chrclasses_dbc")
        warlock = Store((g.STOCK / "ChrClasses.dbc").read_bytes(), columns).decode(WARLOCK)["SpellClassSet"]
        client = Store((CLIENT / "ChrClasses.dbc").read_bytes(), columns)
        self.assertEqual(client.decode(NECROMANCER)["SpellClassSet"], NECROMANCER_FAMILY)
        # Planted: a created class with no records family keeps the parent's on the client row (the rule a next class
        # meets before its records), and the committed file is then not what the generator makes.
        saved = g.spells.CLASS_BLOCKS.pop("necromancer")
        try:
            _, files = g.render()
        finally:
            g.spells.CLASS_BLOCKS["necromancer"] = saved
        self.assertEqual(Store(files["ChrClasses.dbc"], columns).decode(NECROMANCER)["SpellClassSet"], warlock)
        self.assertNotEqual(files["ChrClasses.dbc"], (CLIENT / "ChrClasses.dbc").read_bytes())

    def test_the_client_class_set_is_the_records_family(self):
        # diablocraft-12nrw: the client applies a spell modifier only to spells of the class's own SpellClassSet, so the client row
        # carries the family every Monk record has (22), not the Warrior's 4; the other classes' rows are stock
        families = {int(r["SpellClassSet"]) for r in test_class_records.records(test_class_records.MONK).values()}
        self.assertEqual({MONK_FAMILY}, families)
        columns = schema(ROOT, "chrclasses_dbc")
        stock = Store((g.STOCK / "ChrClasses.dbc").read_bytes(), columns)
        client = Store((CLIENT / "ChrClasses.dbc").read_bytes(), columns)
        self.assertEqual(MONK_FAMILY, client.decode(MONK)["SpellClassSet"])
        self.assertNotEqual(stock.decode(WARRIOR)["SpellClassSet"], MONK_FAMILY)
        # the Paladin's slot is the Crusader's, a class on a stock slot: its client row takes its records' family 24 (2a),
        # the Hunter's slot is the Demon Hunter's: its client row takes its records' family 25 (2a),
        # and the Shaman's slot is the Shaman's: its client row takes its records' family 27 (2a)
        own = {PALADIN: CRUSADER_FAMILY, HUNTER: DEMON_HUNTER_FAMILY, SHAMAN: SHAMAN_FAMILY}
        self.assertEqual({k: own.get(k, stock.decode(k)["SpellClassSet"]) for k in stock.rows},
                         {k: client.decode(k)["SpellClassSet"] for k in stock.rows})

    def test_the_server_row_is_the_clients(self):
        columns = [c[0] for c in schema(ROOT, "chrclasses_dbc")]
        client = Store((CLIENT / "ChrClasses.dbc").read_bytes(), schema(ROOT, "chrclasses_dbc")).decode(MONK)
        row = SQL.split("INSERT INTO `chrclasses_dbc`", 1)[1].split("VALUES\n(", 1)[1].split(");", 1)[0]
        self.assertTrue(row.startswith("12,0,6,1,'Monk',"), row[:40])
        # the server keeps the parent's class set: dc_classes.cpp ClassSpellFamily strips the parent's stock spells by it (12nrw)
        warrior = Store((g.STOCK / "ChrClasses.dbc").read_bytes(), schema(ROOT, "chrclasses_dbc")).decode(WARRIOR)
        self.assertTrue(row.endswith(f",'MONK',{warrior['SpellClassSet']},{client['Flags']},0,0"), row[-30:])
        self.assertEqual(len(columns), 60)

    def test_every_class_with_a_start_profile_is_playable(self):
        # A class is Playable by its dc_class_map row, which the catalogue writes for a class whose spells are generated.
        # The start rolls Paragon's starting level, and Paragon refuses a class that is not Playable after the start has
        # destroyed the stock outfit, so a profiled class with no row logs in bare: "Paragon is not available for your
        # class yet." (the Crusader's first dev run, before its 2a).
        # A class whose profile lands before its spells is named in AWAITING_PLAYABLE until they are generated; none is today.
        profiled = set(generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv"))
        self.assertEqual(profiled - {row[3] for row in catalogue.catalogue()[4]}, AWAITING_PLAYABLE)

    def test_a_profiled_class_whose_spells_are_not_generated_is_caught(self):
        # Planted: the Crusader's sheets without their shells, the state nightly was in before 2a.
        index = catalogue.shell_index
        names = {r["skill_name"] for r in test_class_records.read(MODULE / "data/d3/crusader_skills.csv")}

        def without_crusader():
            found = index()
            found["active"] = {k: v for k, v in found["active"].items() if k not in names}
            return found
        profiled = set(generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv"))
        before = profiled - {row[3] for row in catalogue.catalogue()[4]}   # a profiled class with no skills yet (the Demon Hunter's 1a)
        catalogue.shell_index = without_crusader
        try:
            playable = {row[3] for row in catalogue.catalogue()[4]}
        finally:
            catalogue.shell_index = index
        self.assertEqual(profiled - playable, before | {PALADIN})

    def test_charbaseinfo_pairs_follow_class_map(self):
        raw = (CLIENT / "CharBaseInfo.dbc").read_bytes()
        count = struct.unpack_from("<I", raw, 4)[0]
        pairs = sorted(tuple(raw[20 + i * 2:22 + i * 2]) for i in range(count))
        with (MODULE / "data/d3/class_map.csv").open(encoding="utf-8-sig") as stream:
            mapped = [int(r["wow_class_id"]) for r in csv.DictReader(stream)]
        self.assertEqual(pairs, sorted((r, c) for r in g.build_charbaseinfo.RACES for c in mapped))
        self.assertEqual(len([p for p in pairs if p[1] == MONK]), 10)
        self.assertEqual(len([p for p in pairs if p[1] == NECROMANCER]), 10)
        self.assertEqual(len([p for p in pairs if p[1] == WITCH_DOCTOR]), 10)


class Slices(unittest.TestCase):
    def read(self, directory, file, has_id):
        return g.gt_floats((directory / (file + ".dbc")).read_bytes(), has_id)

    def test_every_gt_file_is_stock_plus_the_parents_slice(self):
        for file, table, per, has_id in g.GT_TABLES:
            with self.subTest(file):
                s_ids, s_vals = self.read(g.STOCK, file, has_id)
                c_ids, c_vals = self.read(CLIENT, file, has_id)
                self.assertEqual(c_vals[:len(s_vals)], s_vals)
                self.assertEqual(len(c_vals), len(s_vals) + per * len(CREATED))
                for cid, parent, _ in CREATED:
                    first, origin = (cid - 1) * per, (parent - 1) * per
                    self.assertEqual(c_vals[first:first + per], s_vals[origin:origin + per], cid)
                self.assertEqual(c_ids[len(s_vals):], list(range(len(s_vals) + (1 if has_id else 0),
                                                                len(s_vals) + per * len(CREATED) + (1 if has_id else 0))))

    def test_the_server_tables_carry_the_same_floats(self):
        for file, table, per, has_id in g.GT_TABLES:
            if not table:
                continue
            with self.subTest(table):
                c_ids, c_vals = self.read(CLIENT, file, has_id)
                for cid, _, sql in CREATED:
                    first = (cid - 1) * per
                    rows = table_rows(sql, table)
                    self.assertEqual([i for i, _ in rows], c_ids[first:first + per])
                    for (_, sql_value), file_value in zip(rows, c_vals[first:first + per]):
                        self.assertAlmostEqual(sql_value, file_value, places=6)

    def test_the_index_the_core_reads_lands_on_the_slice(self):
        # Player.cpp:5284 (class - 1) * GT_MAX_LEVEL + level - 1; :5371 (class - 1) * GT_MAX_RATING + cr + 1.
        _, melee = self.read(CLIENT, "gtChanceToMeleeCrit", False)
        _, stock = self.read(g.STOCK, "gtChanceToMeleeCrit", False)
        self.assertEqual(melee[(MONK - 1) * 100 + 69], stock[(WARRIOR - 1) * 100 + 69])
        self.assertEqual(melee[(NECROMANCER - 1) * 100 + 69], stock[(WARLOCK - 1) * 100 + 69])
        ids, scalar = self.read(CLIENT, "gtOCTClassCombatRatingScalar", True)
        self.assertEqual(dict(zip(ids, scalar))[(MONK - 1) * 32 + 10 + 1],
                         dict(zip(*self.read(g.STOCK, "gtOCTClassCombatRatingScalar", True)))[(WARRIOR - 1) * 32 + 10 + 1])


class Outfit(unittest.TestCase):
    def test_the_outfit_rows_are_the_parents_under_new_identities(self):
        columns = schema(ROOT, "charstartoutfit_dbc")
        stock = g.Outfits((g.STOCK / "CharStartOutfit.dbc").read_bytes(), columns).rows
        client = g.Outfits((CLIENT / "CharStartOutfit.dbc").read_bytes(), columns).rows
        preview = set(g.start_outfits(MODULE))   # the sheet's classes keep their stock rows only on the server
        self.assertEqual([r for r in client if r["ClassID"] not in preview | {MONK, NECROMANCER, WITCH_DOCTOR}],
                         [r for r in stock if r["ClassID"] not in preview])
        self.assertEqual(len({r["ID"] for r in client}), len(client), "identities are unique")
        for cid, parent_id, sql in CREATED:
            new = [r for r in client if r["ClassID"] == cid]
            parent = [r for r in stock if r["ClassID"] == parent_id and r["RaceID"] in g.build_charbaseinfo.RACES]
            self.assertEqual(len(new), len(parent))
            for mine, theirs in zip(new, parent):
                self.assertEqual(mine, dict(theirs, ID=mine["ID"], ClassID=cid))
                self.assertGreater(mine["ID"], max(r["ID"] for r in stock))
            for row in new:
                self.assertRegex(sql, rf"(?m)^\({row['ID']},{row['RaceID']},{cid},{row['SexID']},")
        # The Warlock's five stock races, both sexes; the others get none, as the Blood Elf Barbarian.
        self.assertEqual(sorted({(r["RaceID"], r["SexID"]) for r in client if r["ClassID"] == NECROMANCER}),
                         [(race, sex) for race in sorted(WARLOCK_RACES) for sex in (0, 1)])
        self.assertEqual(sorted({(r["RaceID"], r["SexID"]) for r in client if r["ClassID"] == WITCH_DOCTOR}),
                         [(race, sex) for race in sorted(WARLOCK_RACES) for sex in (0, 1)])


class PreviewOutfits(unittest.TestCase):
    """diablocraft-mb9fn: the create screen's preview outfits are the client's alone."""

    @classmethod
    def setUpClass(cls):
        cls.columns = schema(ROOT, "charstartoutfit_dbc")
        cls.client = g.Outfits((CLIENT / "CharStartOutfit.dbc").read_bytes(), cls.columns).rows
        cls.items = Store((CLIENT / "Item.dbc").read_bytes(), schema(ROOT, "item_dbc"))
        cls.displays = Store((CLIENT / "ItemDisplayInfo.dbc").read_bytes(), schema(ROOT, "itemdisplayinfo_dbc"))
        cls.enchants = Store((g.STOCK / "SpellItemEnchantment.dbc").read_bytes(), schema(ROOT, "spellitemenchantment_dbc"))
        cls.sheet = g.start_outfits(MODULE)

    def test_the_sheet_holds_the_barbarian_and_the_wizard(self):
        self.assertEqual(set(self.sheet), {1, 8})
        for gear in self.sheet.values():
            self.assertEqual([slot for slot, _, _ in gear], list(g.OUTFIT_SLOTS))

    def test_every_race_and_sex_wears_the_sheet(self):
        for cid, gear in self.sheet.items():
            rows = [r for r in self.client if r["ClassID"] == cid]
            self.assertEqual(sorted((r["RaceID"], r["SexID"]) for r in rows),
                             [(race, sex) for race in g.build_charbaseinfo.RACES for sex in (0, 1)])
            for row in rows:
                self.assertEqual(row["OutfitID"], 0)
                for n in range(1, 25):
                    if n > len(gear):
                        self.assertEqual((row[f"ItemID_{n}"], row[f"DisplayItemID_{n}"], row[f"InventoryType_{n}"]), (0, 0, 0))
                        continue
                    _, item, enchant = gear[n - 1]
                    stock = self.items.decode(item)
                    self.assertEqual(row[f"ItemID_{n}"], item)
                    self.assertEqual(row[f"InventoryType_{n}"], stock["InventoryType"])
                    if not enchant:
                        self.assertEqual(row[f"DisplayItemID_{n}"], stock["DisplayInfoID"])

    def test_the_barbarians_axe_wears_berserkings_glow(self):
        slot, item, enchant = self.sheet[1][-1]
        self.assertEqual((slot, item), ("Weapon", 47078))
        self.assertEqual(self.enchants.decode(enchant)["Name_Lang_enUS"], "Berserking")
        glow = self.enchants.decode(enchant)["ItemVisual"]
        self.assertNotEqual(glow, 0)
        for row in (r for r in self.client if r["ClassID"] == 1):
            display = row[f"DisplayItemID_{len(self.sheet[1])}"]
            self.assertTrue(g.OUTFIT_DISPLAY_FIRST <= display <= g.OUTFIT_DISPLAY_LAST)
            mine = self.displays.decode(display)
            plain = self.displays.decode(self.items.decode(item)["DisplayInfoID"])
            self.assertEqual(mine, dict(plain, ID=display, ItemVisual=glow))
            self.assertNotEqual(plain["ItemVisual"], glow)

    def test_the_server_never_sees_them(self):
        block = SQL.split("INSERT INTO `charstartoutfit_dbc`", 1)[1].split(";\n", 1)[0]
        self.assertNotRegex(block, r"(?m)^\(\d+,\d+,(1|8),")
        self.assertEqual(re.findall(r"DELETE FROM `charstartoutfit_dbc` WHERE `ClassID`=(\d+)", SQL), [str(MONK)])
        self.assertEqual(re.findall(r"DELETE FROM `charstartoutfit_dbc` WHERE `ClassID`=(\d+)", NECROMANCER_SQL),
                         [str(NECROMANCER)])
        self.assertEqual(re.findall(r"DELETE FROM `charstartoutfit_dbc` WHERE `ClassID`=(\d+)", WITCH_DOCTOR_SQL), [str(WITCH_DOCTOR)])

    # Mutants: a changed sheet row must change the committed files.
    def test_a_wrong_item_is_caught(self):
        original = g.start_outfits
        g.start_outfits = lambda module: {c: [(s, 48917 if s == "Head" and c == 1 else i, e) for s, i, e in gear]
                                          for c, gear in original(module).items()}
        try:
            _, files = g.render()
        finally:
            g.start_outfits = original
        self.assertNotEqual(files["CharStartOutfit.dbc"], (CLIENT / "CharStartOutfit.dbc").read_bytes())

    def test_a_missing_glow_is_caught(self):
        original = g.start_outfits
        g.start_outfits = lambda module: {c: [(s, i, 0) for s, i, _ in gear] for c, gear in original(module).items()}
        try:
            _, files = g.render()
        finally:
            g.start_outfits = original
        self.assertNotEqual(files["CharStartOutfit.dbc"], (CLIENT / "CharStartOutfit.dbc").read_bytes())

    def test_an_item_in_the_wrong_slot_is_refused(self):
        original = g.start_outfits
        g.start_outfits = lambda module: {1: [("Head", 45225, 0)]}
        try:
            with self.assertRaises(SystemExit):
                g.render()
        finally:
            g.start_outfits = original


class SharedSkills(unittest.TestCase):
    def test_only_the_new_bit_is_added_and_only_where_every_stock_class_has_the_row(self):
        columns = schema(ROOT, "skillraceclassinfo_dbc")
        stock = Store((g.STOCK / "SkillRaceClassInfo.dbc").read_bytes(), columns)
        client = Store((CLIENT / "SkillRaceClassInfo.dbc").read_bytes(), columns)
        stock_classes = set(Store((g.STOCK / "ChrClasses.dbc").read_bytes(), schema(ROOT, "chrclasses_dbc")).rows)
        shared = sum(1 << (c - 1) for c in stock_classes if c != 6)
        bits = {cid: 1 << (cid - 1) for cid, _, _ in CREATED}
        changed = {cid: set() for cid in bits}
        for key in stock.rows:
            before, after = stock.decode(key), client.decode(key)
            if key in proficiencies.RESERVED:
                continue
            everyone = before["ClassMask"] not in (0, -1) and before["ClassMask"] & shared == shared
            added = after["ClassMask"] & ~before["ClassMask"]
            self.assertEqual(after, dict(before, ClassMask=before["ClassMask"] | added), key)
            for cid, bit in bits.items():
                if everyone:
                    self.assertTrue(after["ClassMask"] & bit, f"row {key} should carry class {cid}")
                if added & bit:
                    changed[cid].add(key)
                    if not everyone:   # the one row added for a skill the Monk learns (class_starts.csv)
                        self.assertEqual((cid, before["SkillID"]), (MONK, DUAL_WIELD_SKILL), key)
        for cid, _, sql in CREATED:
            self.assertGreater(len(changed[cid]), 40)
            ids = {int(i) for i in re.search(r"DELETE FROM `skillraceclassinfo_dbc` WHERE `ID` IN \(([\d,]+)\)", sql).group(1).split(",")}
            self.assertEqual(ids, changed[cid], cid)

    def test_the_monks_weapons_are_granted_and_allowed(self):
        columns = schema(ROOT, "skillraceclassinfo_dbc")
        client = Store((CLIENT / "SkillRaceClassInfo.dbc").read_bytes(), columns)
        allowed = {r["SkillID"] for r in map(client.decode, client.rows) if r["ClassMask"] in (0, -1) or r["ClassMask"] & 2048}
        self.assertEqual(allowed & {DUAL_WIELD_SKILL}, {DUAL_WIELD_SKILL})
        granted = {r["skill_id"] for r in generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv")[MONK]["skills"]}
        needed = set(proficiencies.weapon_skills(MODULE, "monk"))
        self.assertEqual(granted - {DUAL_WIELD_SKILL}, needed)
        self.assertLessEqual(needed | {DUAL_WIELD_SKILL}, allowed)
        # Defense, Unarmed and the Common language are not weapons and must be allowed too.
        self.assertLessEqual({95, 162, 98}, allowed)

    def test_the_necromancers_weapons_are_granted_and_allowed(self):
        columns = schema(ROOT, "skillraceclassinfo_dbc")
        client = Store((CLIENT / "SkillRaceClassInfo.dbc").read_bytes(), columns)
        bit = 1 << (NECROMANCER - 1)
        allowed = {r["SkillID"] for r in map(client.decode, client.rows) if r["ClassMask"] in (0, -1) or r["ClassMask"] & bit}
        granted = {r["skill_id"] for r in generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv")[NECROMANCER]["skills"]}
        needed = set(proficiencies.weapon_skills(MODULE, "necromancer"))
        self.assertEqual(granted, needed)
        self.assertLessEqual(needed, allowed)
        self.assertLessEqual({95, 162, 98}, allowed)
        self.assertNotIn(DUAL_WIELD_SKILL, allowed)

    def test_the_witch_doctors_weapons_are_granted_and_allowed(self):
        columns = schema(ROOT, "skillraceclassinfo_dbc")
        client = Store((CLIENT / "SkillRaceClassInfo.dbc").read_bytes(), columns)
        bit = 1 << (WITCH_DOCTOR - 1)
        allowed = {r["SkillID"] for r in map(client.decode, client.rows) if r["ClassMask"] in (0, -1) or r["ClassMask"] & bit}
        granted = {r["skill_id"] for r in generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv")[WITCH_DOCTOR]["skills"]}
        needed = set(proficiencies.weapon_skills(MODULE, "witchdoctor"))
        self.assertEqual(granted, needed)
        self.assertLessEqual(needed, allowed)
        self.assertLessEqual({95, 162, 98}, allowed)
        self.assertNotIn(DUAL_WIELD_SKILL, allowed)

    def test_dual_wield_is_the_warriors_row_with_the_monk_added(self):
        columns = schema(ROOT, "skillraceclassinfo_dbc")
        stock = Store((g.STOCK / "SkillRaceClassInfo.dbc").read_bytes(), columns)
        client = Store((CLIENT / "SkillRaceClassInfo.dbc").read_bytes(), columns)
        rows = [k for k in stock.rows if stock.decode(k)["SkillID"] == DUAL_WIELD_SKILL and stock.decode(k)["ClassMask"] & 1]
        self.assertTrue(rows)
        for key in rows:
            self.assertEqual(client.decode(key), dict(stock.decode(key), ClassMask=stock.decode(key)["ClassMask"] | 1 << (MONK - 1)))

    def test_every_kit_candidate_is_wearable(self):
        rows = proficiencies.read_csv(MODULE / "data/d3/base_items.csv")
        for cid, _, _ in CREATED:
            profile = generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv")[cid]
            granted = {r["skill_id"] for r in profile["skills"]}
            for kit in profile["kit"]:
                pool = generate_sql.starter_candidates(profile, kit, rows)
                self.assertTrue(pool, (cid, kit["slot"]))
                for base in pool:
                    item_class, subclass, _ = generate_sql.classify(base, None, 0, [])
                    if item_class == 4:
                        self.assertEqual(subclass, 0, base["d3_id"])
                    skill = proficiencies.WEAPON_SKILLS[subclass] if item_class == 2 else 0
                    if skill:
                        self.assertIn(skill, granted, base["d3_id"])


class DualFistWeapons(unittest.TestCase):
    """ruling 2026-10-12: the Monk starts with a fist weapon in each hand and learns Dual Wield as the Barbarian does."""

    def test_both_hands_draw_from_the_monks_fist_weapons_and_dual_wield_is_learned(self):
        profile = generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv")[MONK]
        rows = proficiencies.read_csv(MODULE / "data/d3/base_items.csv")
        for slot in ("mainhand", "offhand"):
            kit = next(r for r in profile["kit"] if r["slot"] == slot)
            pool = generate_sql.starter_candidates(profile, kit, rows)
            self.assertTrue(pool, slot)
            self.assertEqual({(b["type"], b["slot"], b["designated_class"]) for b in pool}, {("Fist Weapon", "onehand", "monk")})
        self.assertIn({"spell_id": 674, "skill_id": 118}, profile["skills"])

    def test_the_server_reads_the_same_pool(self):
        sql = (UPDATES / generate_sql.CLASS_START_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("INSERT INTO dc_class_start_skill VALUES (12,674,118);", sql)
        self.assertRegex(sql, r"dc_class_starter_kit VALUES \(12,'offhand','rare',1,'Fist Weapon','onehand','monk'\)")
        # dc_world.cpp's runtime pool must let an off-hand row whose base_slot is onehand take one-handers.
        source = (MODULE / "src/common/dc_world.cpp").read_text(encoding="utf-8")
        self.assertIn('base.slot==(name=="offhand"&&baseSlot=="onehand" ? "onehand" : name)', source)


class NecromancerStart(unittest.TestCase):
    """The brief (ruling 2026-10-15): every race, a Scythe legendary and a Phylactery."""

    def test_the_hands_draw_from_the_scythes_and_the_phylacteries(self):
        profile = generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv")[NECROMANCER]
        rows = proficiencies.read_csv(MODULE / "data/d3/base_items.csv")
        hands = {"mainhand": ("legendary", {("Scythe", "onehand", "necromancer")}),
                 "offhand": ("rare", {("Phylactery", "offhand", "necromancer")})}
        for slot, (rarity, wanted) in hands.items():
            kit = next(r for r in profile["kit"] if r["slot"] == slot)
            self.assertEqual(kit["rarity"], rarity)
            pool = generate_sql.starter_candidates(profile, kit, rows)
            self.assertTrue(pool, slot)
            self.assertEqual({(b["type"], b["slot"], b["designated_class"]) for b in pool}, wanted)
        projection = lambda p: [(r["slot"], r["rarity"], r["count"]) for r in p["kit"] if r["slot"] not in hands]
        barbarian = generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv")[1]
        self.assertEqual(projection(profile), projection(barbarian))

    def test_races_without_a_stock_warlock_start_at_the_hub(self):
        self.assertEqual(g.stock_races(WARLOCK), WARLOCK_RACES)
        block = NECROMANCER_SQL.split("JOIN `dc_world_hub` h ON h.`id`=1", 1)[0].rsplit("INSERT INTO `playercreateinfo`", 1)[1]
        races = {int(r) for r in re.findall(r"SELECT (\d+)", block)}
        self.assertEqual(races, set(g.build_charbaseinfo.RACES) - WARLOCK_RACES)
        self.assertIn(f"FROM `playercreateinfo` WHERE `class`={WARLOCK} AND `race` IN (1,2,3,4,5,6,7,8,10,11);", NECROMANCER_SQL)
        # The stock Warrior pairs every race, so the Monk has none at the hub.
        self.assertEqual(g.stock_races(WARRIOR), set(g.build_charbaseinfo.RACES))
        self.assertNotIn("dc_world_hub", SQL)

    # Mutants: each plants one wrong rule and the committed migrations must differ from what it makes.
    def test_no_hub_rows_is_caught(self):
        original = g.stock_races
        g.stock_races = lambda klass: set(g.build_charbaseinfo.RACES) if klass == WARLOCK else original(klass)
        try:
            result, _ = g.render()
        finally:
            g.stock_races = original
        self.assertNotEqual(result["Necromancer"][0], NECROMANCER_SQL)
        self.assertNotIn("dc_world_hub", result["Necromancer"][0])


class SpellGeneratorWaits(unittest.TestCase):
    """generate_spells.py refuses a class_map.csv class that has a <class>_skills.csv and no CLASS_BLOCKS entry (review
    ry87x: light_check, release_gate and build.sh all run it). The Necromancer's sheets waited in docs/research/necromancer/
    until its records bead (2a, diablocraft-im7mr.5) registered its blocks; now they are in data/d3, its targeting rows in
    skill_targeting.csv."""

    SPELL_SHEETS = ("skills", "runes", "passives", "skill_values", "passive_values", "visuals", "targeting")

    def test_every_class_with_spell_sheets_has_blocks(self):
        import generate_spells
        for row in proficiencies.read_csv(MODULE / "data/d3/class_map.csv"):
            stem = row["d3_class"].strip().lower()
            if stem != "barbarian" and (MODULE / f"data/d3/{stem}_skills.csv").is_file():
                self.assertIn(stem, generate_spells.CLASS_BLOCKS, stem)

    def test_the_necromancer_has_its_blocks_and_its_sheets(self):
        import generate_spells
        self.assertIn("necromancer", generate_spells.CLASS_BLOCKS)
        for sheet in self.SPELL_SHEETS[:-1] + ("base_stats", "resource"):
            self.assertTrue((MODULE / f"data/d3/necromancer_{sheet}.csv").is_file(), sheet)
        # the targeting rows live in the one sheet the generator reads, as the Monk's and the Wizard's
        self.assertFalse((MODULE / "data/d3/necromancer_targeting.csv").exists())
        research = proficiencies.read_csv(ROOT / "docs/research/necromancer/necromancer_targeting.csv")
        shipped = {r["skill"] for r in proficiencies.read_csv(MODULE / "data/d3/skill_targeting.csv")}
        self.assertEqual([r["skill"] for r in research if r["skill"] not in shipped], [])


class Regeneration(unittest.TestCase):
    def test_the_committed_files_are_what_the_generator_makes(self):
        result, files = g.render()
        self.assertEqual(result["Monk"][0], SQL)
        self.assertEqual(result["Crusader"][0], CRUSADER_SQL)
        self.assertEqual(result["Necromancer"][0], NECROMANCER_SQL)
        for name, data in files.items():
            self.assertEqual((CLIENT / name).read_bytes(), data, name)

    def test_the_migrations_are_numbered_in_dependency_order(self):
        # A class's creation migration comes before the start profile migration that names it and before the proficiency migration (which
        # renders every class); a class with no profile yet (the Demon Hunter's waits for its skills) is owed no start migration after it.
        profiled = set(generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv"))
        for c in g.created_classes():
            self.assertTrue((UPDATES / c["migration"]).is_file(), c["migration"])
            self.assertLess(c["migration"], proficiencies.MIGRATION, c["name"])
            if c["id"] in profiled:
                self.assertLess(c["migration"], generate_sql.CLASS_START_MIGRATION, c["name"])
        for name in (generate_sql.CLASS_START_MIGRATION, proficiencies.MIGRATION):
            self.assertTrue((UPDATES / name).is_file(), name)

    # Mutants: each plants one wrong rule and the committed files must differ from what it makes.
    def test_a_wrong_parent_is_caught(self):
        original, g.created_classes = only_monk(dict(parent=8))
        try:
            _, files = g.render()
        finally:
            g.created_classes = original
        self.assertNotEqual(files["gtChanceToMeleeCrit.dbc"], (CLIENT / "gtChanceToMeleeCrit.dbc").read_bytes())
        self.assertNotEqual(files["CharStartOutfit.dbc"], (CLIENT / "CharStartOutfit.dbc").read_bytes())

    def test_a_wrong_power_slot_is_caught(self):
        original, g.created_classes = only_monk(dict(power="Rage"))
        try:
            _, files = g.render()
        finally:
            g.created_classes = original
        self.assertNotEqual(files["ChrClasses.dbc"], (CLIENT / "ChrClasses.dbc").read_bytes())

    def test_a_class_that_already_exists_is_refused(self):
        original, g.created_classes = only_monk(dict(id=8))
        try:
            with self.assertRaises(SystemExit):
                g.render()
        finally:
            g.created_classes = original


class StockSlot(unittest.TestCase):
    """The Crusader on the Paladin slot: the races stock lacks get start rows, and nothing stock is copied or replaced."""

    def stock_paladin_races(self):
        return g.stock_races(PALADIN)

    def races_in(self, sql):
        block = sql.split("INSERT INTO `playercreateinfo`", 1)[1].split(";", 1)[0]
        return sorted(int(r) for r in re.findall(r"SELECT (\d+)", block))

    def test_the_new_races_are_exactly_the_ones_stock_lacks(self):
        # cross-source: the stock CharBaseInfo extraction against the committed migration
        self.assertEqual(sorted(self.stock_paladin_races()), [1, 3, 10, 11])
        self.assertEqual(self.races_in(CRUSADER_SQL), [2, 4, 5, 6, 7, 8])
        self.assertEqual(set(self.races_in(CRUSADER_SQL)) | self.stock_paladin_races(), set(g.build_charbaseinfo.RACES))

    def test_the_rows_stand_at_the_hub_and_copy_the_attack_button(self):
        self.assertIn("JOIN `dc_world_hub` h ON h.`id`=1", CRUSADER_SQL)
        self.assertIn(f"a.`class`={PALADIN} AND a.`race`=1 AND a.`action`={g.ATTACK}", CRUSADER_SQL)

    def test_no_stock_row_is_copied_or_replaced(self):
        for table in ("chrclasses_dbc", "player_class_stats", "charstartoutfit_dbc", "skillraceclassinfo_dbc", "_dbc` WHERE `ID` BETWEEN"):
            self.assertNotIn(table, CRUSADER_SQL)
        self.assertNotIn(f"DELETE FROM `playercreateinfo` ", CRUSADER_SQL)

    def test_the_client_pairs_hold_every_race(self):
        raw = (CLIENT / "CharBaseInfo.dbc").read_bytes()
        count = struct.unpack_from("<I", raw, 4)[0]
        pairs = {tuple(raw[20 + i * 2:22 + i * 2]) for i in range(count)}
        self.assertEqual(sorted(r for r, c in pairs if c == PALADIN), sorted(g.build_charbaseinfo.RACES))

    def test_the_paladin_row_takes_energy_the_crusader_name_and_its_records_family_and_nothing_else(self):
        # the family since 2a (diablocraft-qulab): the client applies a spell modifier only inside the class's own SpellClassSet
        columns = schema(ROOT, "chrclasses_dbc")
        stock = Store((g.STOCK / "ChrClasses.dbc").read_bytes(), columns).decode(PALADIN)
        client = Store((CLIENT / "ChrClasses.dbc").read_bytes(), columns).decode(PALADIN)
        self.assertEqual(client, dict(stock, DisplayPower=3, Name_Lang_enUS="Crusader", SpellClassSet=CRUSADER_FAMILY))
        self.assertEqual(CRUSADER_FAMILY, g.spells.CLASS_BLOCKS["crusader"].family)
        self.assertNotEqual(stock["SpellClassSet"], CRUSADER_FAMILY)

    # Mutants: each plants one wrong rule.
    def test_a_stock_slot_read_as_a_created_class_is_refused(self):
        original = g.created_classes
        g.created_classes = lambda module=g.MODULE: [dict(c, parent=1) if c["name"] == "Crusader" else c for c in original(module)]
        try:
            with self.assertRaises(SystemExit):
                g.render()
        finally:
            g.created_classes = original

    def test_wrong_stock_races_are_caught(self):
        original = g.stock_races
        g.stock_races = lambda klass: original(8 if klass == PALADIN else klass)   # the Mage's races for the Paladin's
        try:
            result, files = g.render()
        finally:
            g.stock_races = original
        self.assertNotEqual(result["Crusader"][0], CRUSADER_SQL)

    def test_a_stock_slot_with_every_race_is_refused(self):
        original = g.stock_races
        g.stock_races = lambda klass: set(g.build_charbaseinfo.RACES) if klass == PALADIN else original(klass)
        try:
            with self.assertRaises(SystemExit):
                g.render()
        finally:
            g.stock_races = original

    def test_the_stock_slot_counted_as_created_loses_its_energy(self):
        import generate_class_resources as resources
        original = resources.created_class_ids
        resources.created_class_ids = lambda: original() | {PALADIN}
        try:
            sql, _, overlays = resources.display_power(resources.registry())
        finally:
            resources.created_class_ids = original
        self.assertNotIn(PALADIN, [o["ID"] for o in overlays])
        self.assertFalse(sql == (UPDATES / resources.DISPLAY_POWER_MIGRATION).read_text(encoding="utf-8"))

    def test_the_display_power_migration_overlays_the_paladin(self):
        import generate_class_resources as resources
        sql, _, overlays = resources.display_power(resources.registry())
        self.assertEqual({o["ID"]: o["DisplayPower"] for o in overlays}, {8: 3, PALADIN: 3, HUNTER: 3, SHAMAN: 1})
        self.assertEqual(sql, (UPDATES / resources.DISPLAY_POWER_MIGRATION).read_text(encoding="utf-8"))


class ShamanSlot(unittest.TestCase):
    """The Shaman on the Shaman slot, the third class on a stock slot: stock keeps its rows, the missing races start at the hub."""

    def races_in(self, sql):
        block = sql.split("INSERT INTO `playercreateinfo`", 1)[1].split(";", 1)[0]
        return sorted(int(r) for r in re.findall(r"SELECT (\d+)", block))

    def test_the_new_races_are_exactly_the_ones_stock_lacks(self):
        # cross-source: the stock CharBaseInfo extraction against the committed migration
        self.assertEqual(sorted(g.stock_races(SHAMAN)), [2, 6, 8, 11])
        self.assertEqual(self.races_in(SHAMAN_SQL), [1, 3, 4, 5, 7, 10])
        self.assertEqual(set(self.races_in(SHAMAN_SQL)) | g.stock_races(SHAMAN), set(g.build_charbaseinfo.RACES))

    def test_the_rows_stand_at_the_hub_and_copy_the_attack_button(self):
        self.assertIn("JOIN `dc_world_hub` h ON h.`id`=1", SHAMAN_SQL)
        self.assertIn(f"a.`class`={SHAMAN} AND a.`race`=2 AND a.`action`={g.ATTACK}", SHAMAN_SQL)

    def test_no_stock_row_is_copied_or_replaced(self):
        for table in ("chrclasses_dbc", "player_class_stats", "charstartoutfit_dbc", "skillraceclassinfo_dbc", "_dbc` WHERE `ID` BETWEEN"):
            self.assertNotIn(table, SHAMAN_SQL)
        self.assertNotIn("DELETE FROM `playercreateinfo` ", SHAMAN_SQL)

    def test_the_client_pairs_hold_every_race(self):
        raw = (CLIENT / "CharBaseInfo.dbc").read_bytes()
        count = struct.unpack_from("<I", raw, 4)[0]
        pairs = {tuple(raw[20 + i * 2:22 + i * 2]) for i in range(count)}
        self.assertEqual(sorted(r for r, c in pairs if c == SHAMAN), sorted(g.build_charbaseinfo.RACES))

    def test_a_shaman_read_as_a_created_class_is_refused(self):
        original = g.created_classes
        g.created_classes = lambda module=g.MODULE: [dict(c, parent=1) if c["name"] == "Shaman" else c for c in original(module)]
        try:
            with self.assertRaises(SystemExit):
                g.render()
        finally:
            g.created_classes = original

    def test_wrong_stock_races_are_caught(self):
        original = g.stock_races
        g.stock_races = lambda klass: original(8 if klass == SHAMAN else klass)   # the Mage's races for the Shaman's
        try:
            result, files = g.render()
        finally:
            g.stock_races = original
        self.assertNotEqual(result["Shaman"][0], SHAMAN_SQL)


class HunterSlot(unittest.TestCase):
    """The Demon Hunter on the Hunter slot, the second class on a stock slot: stock keeps its rows, the missing races start at the hub."""

    def races_in(self, sql):
        block = sql.split("INSERT INTO `playercreateinfo`", 1)[1].split(";", 1)[0]
        return sorted(int(r) for r in re.findall(r"SELECT (\d+)", block))

    def test_the_new_races_are_exactly_the_ones_stock_lacks(self):
        # cross-source: the stock CharBaseInfo extraction against the committed migration
        self.assertEqual(sorted(g.stock_races(HUNTER)), [2, 3, 4, 6, 8, 10, 11])
        self.assertEqual(self.races_in(DEMON_HUNTER_SQL), [1, 5, 7])
        self.assertEqual(set(self.races_in(DEMON_HUNTER_SQL)) | g.stock_races(HUNTER), set(g.build_charbaseinfo.RACES))

    def test_the_rows_stand_at_the_hub_and_copy_the_attack_button(self):
        self.assertIn("JOIN `dc_world_hub` h ON h.`id`=1", DEMON_HUNTER_SQL)
        self.assertIn(f"a.`class`={HUNTER} AND a.`race`=2 AND a.`action`={g.ATTACK}", DEMON_HUNTER_SQL)

    def test_no_stock_row_is_copied_or_replaced(self):
        for table in ("chrclasses_dbc", "player_class_stats", "charstartoutfit_dbc", "skillraceclassinfo_dbc", "_dbc` WHERE `ID` BETWEEN"):
            self.assertNotIn(table, DEMON_HUNTER_SQL)
        self.assertNotIn("DELETE FROM `playercreateinfo` ", DEMON_HUNTER_SQL)

    def test_the_client_pairs_hold_every_race(self):
        raw = (CLIENT / "CharBaseInfo.dbc").read_bytes()
        count = struct.unpack_from("<I", raw, 4)[0]
        pairs = {tuple(raw[20 + i * 2:22 + i * 2]) for i in range(count)}
        self.assertEqual(sorted(r for r, c in pairs if c == HUNTER), sorted(g.build_charbaseinfo.RACES))

    def test_the_hunter_row_takes_energy_the_name_and_the_records_family_and_nothing_else(self):
        # Its skill sheets are in data/d3 (2a), so the client row carries the records' family 25, not the stock 9.
        columns = schema(ROOT, "chrclasses_dbc")
        stock = Store((g.STOCK / "ChrClasses.dbc").read_bytes(), columns).decode(HUNTER)
        client = Store((CLIENT / "ChrClasses.dbc").read_bytes(), columns).decode(HUNTER)
        self.assertEqual(client, dict(stock, DisplayPower=3, Name_Lang_enUS="Demon Hunter", SpellClassSet=25))
        self.assertEqual(g.spells.CLASS_BLOCKS["demon_hunter"].family, 25)
        self.assertNotEqual(stock["SpellClassSet"], 25)
        self.assertTrue((MODULE / "data/d3/demon_hunter_skills.csv").exists())

    # Mutants: each plants one wrong rule.
    def test_wrong_stock_races_are_caught(self):
        original = g.stock_races
        g.stock_races = lambda klass: original(8 if klass == HUNTER else klass)   # the Mage's races for the Hunter's
        try:
            result, files = g.render()
        finally:
            g.stock_races = original
        self.assertNotEqual(result["Demon Hunter"][0], DEMON_HUNTER_SQL)

    def test_a_hunter_read_as_a_created_class_is_refused(self):
        original = g.created_classes
        g.created_classes = lambda module=g.MODULE: [dict(c, parent=1) if c["name"] == "Demon Hunter" else c for c in original(module)]
        try:
            with self.assertRaises(SystemExit):
                g.render()
        finally:
            g.created_classes = original

    def test_a_two_word_class_name_gives_its_data_the_underscore_stem(self):
        # The sheets are demon_hunter_*.csv and the item sheets spell the class demonhunter: one helper names both.
        from class_names import item_key, sheet_stem
        self.assertEqual((sheet_stem("Demon Hunter"), item_key("Demon Hunter")), ("demon_hunter", "demonhunter"))
        self.assertEqual((sheet_stem("Monk"), item_key("Monk")), ("monk", "monk"))
        self.assertTrue((MODULE / "data/d3" / ("%s_base_stats.csv" % sheet_stem("Demon Hunter"))).is_file())
        with (MODULE / "data/d3/base_items.csv").open(encoding="utf-8-sig") as stream:
            usable = {key for row in csv.DictReader(stream) for key in row["usable_by"].split(";") if key}
        self.assertIn(item_key("Demon Hunter"), usable)


if __name__ == "__main__":
    unittest.main()

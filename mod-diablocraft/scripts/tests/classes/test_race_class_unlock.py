"""diablocraft-race-class-unlock, option C (ruling q-1001-37): every race for the playable classes, the rest locked.

    python3 mod-diablocraft/scripts/tests/classes/test_race_class_unlock.py

The lock is the client's own: CharBaseInfo.dbc lists only the playable classes (class_map.csv: the Barbarian 1, the
Wizard 8, since diablocraft-1cuvw the Monk 12, since diablocraft-txze9 the Crusader on the Paladin's 2 and since
diablocraft-vawmy.1 the Demon Hunter on the Hunter's 3 and since diablocraft-vxrcu.1 the Witch Doctor 14) for each of the ten races, so the stock create screen greys,
darkens and disables every other class (a class with no row for the race is drawn disabled). The server gate
(dc_world.cpp) refuses the rest: it allows the classes of dc_class_start (class_starts.csv) and names none. Pinned
here, each so removing it fails a test:
  * CharBaseInfo.dbc is exactly the playable classes' pairs, and its classes are the gate's classes;
  * ChrClasses.dbc and the server overlay name the live classes Barbarian, Wizard, Crusader and Demon Hunter;
  * the server rows the new pairs need (world_0028);
  * the only GlueXML/FrameXML files in client-patch/art are the Monk create screen's (diablocraft-s375z) and the class
    colours' character list (CharacterSelect.lua): the client refuses to start with an edited one (Nightly 52) unless
    the release ships the glue-unlock DLL, which build.sh asks.
"""
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "client-patch/dbc"))

GATE = MODULE / "src/common/dc_world.cpp"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/race-class-unlock/tests"
UPDATES = MODULE / "data/sql/db-world/updates"

RACES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11)
CLASSES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 11)
# Classes the client's table lists (class_map.csv) that the gate does not allow yet: a class whose start profile (kit and weapon
# proficiencies) is not in class_starts.csv. None now: the Shaman's came with her Ritual Mace and Totem (diablocraft-xnrvn.3). The
# entry goes when class_starts.csv gains the class; the test below fails if it stays.
AWAITING_START = set()
# The class file name the client uses for each CLASS_ constant the gate names.
FILE_OF = {"CLASS_WARRIOR": "WARRIOR", "CLASS_MAGE": "MAGE", "CLASS_PALADIN": "PALADIN", "CLASS_HUNTER": "HUNTER",
           "CLASS_ROGUE": "ROGUE", "CLASS_PRIEST": "PRIEST", "CLASS_DEATH_KNIGHT": "DEATHKNIGHT",
           "CLASS_SHAMAN": "SHAMAN", "CLASS_WARLOCK": "WARLOCK", "CLASS_DRUID": "DRUID"}


def gate_body(cpp_text):
    body = re.search(r"bool CanAccountCreateCharacter\([^)]*\) override\s*\{(.*?)\n    \}", cpp_text, re.S)
    assert body, "the gate was not found"
    return body.group(1)


def gate_reads_data(cpp_text):
    """The gate allows the classes of dc_class_start and names no class of its own."""
    body = gate_body(cpp_text)
    return "creatableClasses.count(type)" in body and not re.search(r"CLASS_[A-Z_]+", body)


def start_classes():
    """The WoW class ids dc_class_start is generated for, from class_starts.csv."""
    import csv
    with (MODULE / "data/d3/class_starts.csv").open(encoding="utf-8-sig", newline="") as stream:
        return sorted({int(row["class_id"]) for row in csv.DictReader(stream)})


def mapped_classes():
    import csv
    with (MODULE / "data/d3/class_map.csv").open(encoding="utf-8-sig", newline="") as stream:
        return sorted(int(row["wow_class_id"]) for row in csv.DictReader(stream))



CLASS_ID_OF = {"WARRIOR": 1, "MAGE": 8, "PALADIN": 2, "HUNTER": 3, "ROGUE": 4, "PRIEST": 5, "DEATHKNIGHT": 6,
               "SHAMAN": 7, "WARLOCK": 9, "DRUID": 11}
STOCK_DBC = ROOT / "azerothcore-wotlk" / "build/server/data/dbc/CharBaseInfo.dbc"
STOCK_CREATE = ROOT / "azerothcore-wotlk" / "build/_agent-scratch/stock-gluexml-9b46c3a/Interface/GlueXML/CharacterCreate.lua"


class TheLockIsTheGatesList(unittest.TestCase):
    def pairs(self, raw=None):
        raw = raw if raw is not None else (ROOT / "client-patch/dbc/CharBaseInfo.dbc").read_bytes()
        magic, count, fields, size, strings = struct.unpack_from("<4s4I", raw)
        self.assertEqual((magic, fields, size, strings, len(raw)), (b"WDBC", 2, 2, 1, 21 + count * 2))
        return [tuple(raw[20 + i * 2:22 + i * 2]) for i in range(count)]

    def listed_classes(self, pairs):
        return sorted({c for _, c in pairs})

    def test_exactly_the_playable_pairs(self):
        rows = self.pairs()
        self.assertEqual(len(rows), 80)
        self.assertEqual(sorted(rows), sorted((r, c) for r in RACES for c in (1, 2, 3, 7, 8, 12, 13, 14)))
        self.assertEqual(sorted(rows), sorted((r, c) for r in RACES for c in mapped_classes()))

    def test_the_classes_in_the_table_are_the_classes_the_gate_allows(self):
        # The gate allows dc_class_start's classes, which class_starts.csv generates; the table lists class_map.csv's.
        self.assertTrue(gate_reads_data(GATE.read_text()))
        self.assertEqual(self.listed_classes(self.pairs()), sorted(set(start_classes()) | AWAITING_START))
        self.assertEqual(start_classes(), [1, 2, 3, 7, 8, 12, 13, 14])
        self.assertTrue(AWAITING_START.isdisjoint(start_classes()), "a class with a start profile is not awaiting one")

    def test_every_race_lists_each_gate_class(self):
        rows = set(self.pairs())
        for race in RACES:
            for cls in start_classes():
                self.assertIn((race, cls), rows)

    def test_a_class_added_to_the_gate_alone_is_caught(self):
        # Naming a class in the gate again, or dropping the data read, is caught; so is a profile with no pairs.
        cpp = GATE.read_text().replace("return creatableClasses.count(type) > 0;",
                                       "return creatableClasses.count(type) > 0 || type == CLASS_ROGUE;")
        self.assertNotEqual(cpp, GATE.read_text())
        self.assertFalse(gate_reads_data(cpp))
        self.assertNotEqual(self.listed_classes(self.pairs()), sorted(start_classes() + [4]))

    def test_a_class_added_to_the_table_alone_is_caught(self):
        import build_charbaseinfo as b
        saved = b.playable_classes
        b.playable_classes = lambda module=b.MODULE: (1, 4, 8, 12)
        try:
            extra = self.pairs(b.build(STOCK_DBC.read_bytes()))
        finally:
            b.playable_classes = saved
        self.assertNotEqual(self.listed_classes(extra), sorted(set(start_classes()) | AWAITING_START))

    def test_the_builder_makes_the_committed_file(self):
        import build_charbaseinfo as b
        built = b.build(STOCK_DBC.read_bytes())
        self.assertEqual(built, (ROOT / "client-patch/dbc/CharBaseInfo.dbc").read_bytes())
        self.assertEqual(b.build(built), built, "a second run changes the file")

    def test_the_stock_screen_disables_a_class_with_no_pair(self):
        """The mechanism option C relies on, in the approved stock transcription of the create screen."""
        if not STOCK_CREATE.is_file():
            self.skipTest("the stock GlueXML transcription is not here")
        branch = STOCK_CREATE.read_text().split("function CharacterCreateEnumerateClasses", 1)[1].split("function SetCharacterRace", 1)[0]
        self.assertIn("IsRaceClassValid(CharacterCreate.selectedRace, index)", branch)
        self.assertRegex(branch, r"button\.enable = false;\s+button:Disable\(\);\s+SetButtonDesaturated\(button, 1\);")
        self.assertIn('_G[strupper(select(i+1, ...).."_".."DISABLED")]', branch)


class NoSignedInterfaceFile(unittest.TestCase):
    def test_only_the_monk_screen_files_are_signed_interface_files(self):
        """The 3.3.5 client refuses to start with an edited GlueXML/FrameXML file (Nightly 52) unless the release ships
        the glue-unlock DLL (g9tfu, q4o3z). The Monk's create screen (s375z) and the class colours' character list are
        the files that need it."""
        art = ROOT / "client-patch/art/Interface"
        found = sorted(p.relative_to(art).as_posix() for p in art.rglob("*")
                       if p.is_file() and any(s in p.as_posix().lower() for s in ("/gluexml/", "/framexml/")))
        self.assertEqual(found, ["FrameXML/Constants.lua", "GlueXML/CharacterCreate.lua", "GlueXML/CharacterCreate.xml",
                                 "GlueXML/CharacterSelect.lua", "GlueXML/GlueStrings.lua"])

    def test_build_sh_refuses_a_glue_file_in_art(self):
        # The gate's tree has an empty _agent-scratch (release_gate.sh creates it
        # and nothing else), so the test makes its own directory: a test that
        # needs a scratch folder to exist is a test that fails in a gate tree.
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rc-build-", dir=SCRATCH) as td:
            here = Path(td) / "client-patch"
            (here / "art/Interface/GlueXML").mkdir(parents=True)
            (here / "art/Interface/GlueXML/CharacterCreate.lua").write_text("x")
            (here / "dbc").mkdir()
            shutil.copy(ROOT / "client-patch/build.sh", here / "build.sh")
            (here / "stamp_client_patch.sh").write_text("exit 0\n")
            ran = subprocess.run(["bash", str(here / "build.sh"), "--output", str(here / "o.mpq")],
                                 capture_output=True, text=True, timeout=60)
            self.assertNotEqual(ran.returncode, 0)
            self.assertIn("refusing to pack a signed interface file", ran.stderr)
            self.assertFalse((here / "o.mpq").exists())


class TheClientTables(unittest.TestCase):
    def chr_names(self):
        import generate_class_resources as gcr
        from dbc_store import Store, schema
        store = Store(gcr.CLIENT_CHRCLASSES.read_bytes(), schema(ROOT, "chrclasses_dbc"))
        return store, {i: store.decode(i)["Name_Lang_enUS"] for i in store.rows}

    def test_the_client_names_the_live_classes(self):
        _, names = self.chr_names()
        self.assertEqual(names[1], "Barbarian")
        self.assertEqual(names[8], "Wizard")
        self.assertEqual(names[2], "Crusader")
        self.assertEqual(names[4], "Rogue")        # every other class keeps its name
        self.assertEqual(names[11], "Druid")
        self.assertNotIn("Warrior", names.values())
        self.assertNotIn("Mage", names.values())
        self.assertNotIn("Paladin", names.values())

    def test_the_client_names_come_from_the_generator(self):
        import generate_class_resources as gcr
        _, client, _ = gcr.display_power(gcr.registry())
        sql, built, rows = gcr.class_names(client)
        self.assertEqual(built, gcr.CLIENT_CHRCLASSES.read_bytes())
        self.assertEqual((UPDATES / gcr.CLASS_NAMES_MIGRATION).read_text(encoding="utf-8"), sql)
        self.assertEqual([(r["ID"], r["Name_Lang_enUS"], r["DisplayPower"]) for r in rows], [(1, "Barbarian", 1), (2, "Crusader", 3), (3, "Demon Hunter", 3), (7, "Shaman", 1), (8, "Wizard", 3)])

    def test_the_server_overlay_is_in_step_with_the_client(self):
        sql = (UPDATES / "world_0027_class_names.sql").read_text(encoding="utf-8")
        self.assertIn("DELETE FROM `chrclasses_dbc` WHERE `ID` IN (1,8);", sql)
        self.assertRegex(sql, r"\n\(1,0,1,1,'Barbarian',")
        self.assertRegex(sql, r"\n\(8,0,3,1,'Wizard',")
        self.assertNotIn("'Warrior'", sql.split("VALUES", 1)[1].replace("'WARRIOR'", ""))
        self.assertNotIn("'Mage'", sql.split("VALUES", 1)[1].replace("'MAGE'", ""))

    def test_a_name_left_as_stock_is_caught(self):
        import generate_class_resources as gcr
        _, client, _ = gcr.display_power(gcr.registry())
        original = gcr.read
        try:
            def stock_names(path):
                rows = original(path)
                if Path(path).name == "class_map.csv":
                    rows = [dict(r, d3_class={"Barbarian": "Warrior", "Wizard": "Mage"}.get(r["d3_class"].strip(), r["d3_class"]))
                            for r in rows]
                return rows
            gcr.read = stock_names
            _, built, _ = gcr.class_names(client)
        finally:
            gcr.read = original
        self.assertNotEqual(built, gcr.CLIENT_CHRCLASSES.read_bytes())


class TheServerRows(unittest.TestCase):
    sql = (UPDATES / "world_0028_race_class_pairs.sql").read_text(encoding="utf-8")

    def test_the_four_missing_wizard_pairs_get_a_row_at_the_hub(self):
        self.assertIn("SELECT 2 AS `race` UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 6", self.sql)
        self.assertIn("JOIN `dc_world_hub` h ON h.`id` = 1", self.sql)
        self.assertRegex(self.sql, r"INSERT INTO `playercreateinfo` \(`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`\)\s+SELECT r.`race`, 8,")

    def test_the_new_wizards_get_no_action_rows(self):
        # WriteActionBar rewrites buttons 0-7 on every login, so a row there is dead.
        self.assertNotIn("playercreateinfo_action` WHERE `class`=8", self.sql)
        self.assertNotRegex(self.sql, r"\(\d+,8,\d+,\d+,0\)")

    def test_the_login_bar_rewrite_covers_what_a_wizard_row_would_set(self):
        cpp = (MODULE / "src/classes/dc_classes.cpp").read_text()
        self.assertIn("for (unsigned slot = 0; slot < ActiveSlots() + 2; ++slot)\n        player->removeActionButton", cpp)
        self.assertIn("WriteActionBar(player);\n    }\n\n    void OnPlayerLevelChanged", cpp)

    def test_the_blood_elf_barbarian_gets_the_barbarian_bar(self):
        self.assertIn("(10,1,72,6603,0),(10,1,73,78,0),(10,1,84,6603,0),(10,1,96,6603,0)", self.sql)

    def test_the_migration_is_new_and_numbered_after_the_last(self):
        # Adjacent, not "second to last": every later world migration is appended after it, and a slice from the end
        # went red (and had to be bumped) with each one.
        names = sorted(p.name for p in UPDATES.glob("world_00*.sql"))
        self.assertEqual(names[names.index("world_0027_class_names.sql") + 1], "world_0028_race_class_pairs.sql")


if __name__ == "__main__":
    unittest.main(verbosity=2)

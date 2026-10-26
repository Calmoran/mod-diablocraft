"""The class colour table (data/class_colours.csv) and what generate_class_colours.py writes from it.

    python3 mod-diablocraft/scripts/tests/classes/test_class_colours.py

Pinned here, each so removing it fails a test: every D3 class has one row with a six-digit hex; the committed
Constants.lua and CharacterCreate.lua blocks are exactly what the table generates, and their numbers are the CSV hex
over 255 (parsed here from the Lua, not taken from the generator); only live classes (class_map.csv) reach either
file, so a class slot keeps its stock colour until its class is live (the Paladin did until the Crusader, the Hunter until
the Demon Hunter) and a class that is not in class_map.csv is not written, and a class made live needs no other edit; the run refuses a missing or doubled row, a bad hex, a live token that is
not class_map.csv's and a ChrClasses.dbc row that does not carry the token and the D3 name. What the screens do with
the colours is test_class_colours.lua's.
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_class_colours as G  # noqa: E402

LIVE_LINE = re.compile(r'RAID_CLASS_COLORS\["(\w+)"\] = \{ r = ([\d.]+), g = ([\d.]+), b = ([\d.]+) \};')
GLUE_LINE = re.compile(r'\t\["(\w+)"\]\t= \{ r = ([\d.]+), g = ([\d.]+), b = ([\d.]+), hex = "(\w+)", name = "([\w ]+)" \},')


def block(text):
    return text[text.index(G.BEGIN):text.index(G.END)]


class Table(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.csv = {r["d3_class"]: r for r in G.read(G.TABLE)}

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def table_without(self, d3_class=None, extra=""):
        lines = G.TABLE.read_text(encoding="utf-8").splitlines()
        return self.write(f"t{len(list(self.tmp.iterdir()))}.csv", "\n".join(l for l in lines if not d3_class or not l.startswith(d3_class + ",")) +
                          "\n" + extra)

    def test_every_d3_class_has_one_colour(self):
        d3 = {r["d3_class"] for r in G.read(G.D3_CLASSES)}
        self.assertEqual(set(self.csv), d3)
        self.assertEqual(len(self.csv), 8)
        for row in self.csv.values():
            self.assertRegex(row["hex"], r"^[0-9A-F]{6}$")

    def test_the_committed_files_are_generated(self):
        self.assertEqual(G.main(["--check"]), 0)
        for path, text in G.outputs(G.rows()).items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, path)

    def test_the_numbers_are_the_csv_hex(self):
        live = {r["d3_class"] for r in G.read(G.CLASS_MAP)}
        want = {r["token"]: r for r in self.csv.values() if r["d3_class"] in live}
        frame = {m[0]: m[1:] for m in LIVE_LINE.findall(block(G.CONSTANTS.read_text(encoding="utf-8")))}
        glue = {m[0]: m[1:] for m in GLUE_LINE.findall(block(G.CREATE.read_text(encoding="utf-8")))}
        self.assertEqual(set(frame), set(want))
        self.assertEqual(set(glue), set(want))
        self.assertEqual(set(want), {"WARRIOR", "PALADIN", "MAGE", "MONK", "NECROMANCER", "HUNTER", "WITCHDOCTOR", "SHAMAN"})
        for token, row in want.items():
            rgb = [int(row["hex"][i:i + 2], 16) / 255 for i in (0, 2, 4)]
            for got in (frame[token], glue[token][:3]):
                for have, expect in zip(got, rgb):
                    self.assertAlmostEqual(float(have), expect, delta=0.0006, msg=token)
            self.assertEqual(glue[token][3], row["hex"].lower())
            self.assertEqual(glue[token][4], row["d3_class"])

    def test_a_class_not_in_the_map_is_not_written(self):
        cmap = "".join(l for l in G.CLASS_MAP.read_text(encoding="utf-8").splitlines(True) if not l.startswith("Witch Doctor,"))
        entries = G.rows(class_map=self.write("m.csv", cmap))
        self.assertNotIn('"WITCHDOCTOR"', G.render_frame(entries))
        self.assertNotIn('"WITCHDOCTOR"', G.render_glue(entries))

    def test_a_class_made_live_needs_no_other_edit(self):
        # the Witch Doctor went live with its table row, class_map.csv's row and ChrClasses.dbc's: nothing else was edited
        entries = G.rows()
        self.assertIn('RAID_CLASS_COLORS["WITCHDOCTOR"] = { r = 0.298, g = 0.859, b = 0.243 };', G.render_frame(entries))
        self.assertIn('["WITCHDOCTOR"]\t= { r = 0.298, g = 0.859, b = 0.243, hex = "4cdb3e", name = "Witch Doctor" },',
                      G.render_glue(entries))

    def test_refusals(self):
        cases = {
            "no row for": self.table_without("Monk"),
            "twice": self.table_without(extra="Monk,MONK2,FF7D0A\n"),
            "six hex digits": self.write("hex.csv", G.TABLE.read_text(encoding="utf-8").replace("FF7D0A", "FF9A2")),
            "class_map.csv puts it on": self.write("token.csv", G.TABLE.read_text(encoding="utf-8").replace(
                "Wizard,MAGE", "Wizard,WIZARD")),
            "not a D3 class": self.table_without(extra="Amazon,AMAZON,FFFFFF\n"),
        }
        for words, table in cases.items():
            with self.subTest(words), self.assertRaises(SystemExit) as caught:
                G.rows(table=table)
            self.assertIn(words, str(caught.exception))
        client = {**G.chrclasses(), 1: ("WARRIOR", "Warrior")}
        with self.assertRaises(SystemExit) as caught:
            G.rows(client=client)
        self.assertIn("ChrClasses.dbc class 1", str(caught.exception))

    def test_a_stale_file_fails_the_check(self):
        old = G.CREATE
        copy = self.tmp / "CharacterCreate.lua"
        copy.write_text(old.read_text(encoding="utf-8").replace('hex = "ff7d0a"', 'hex = "00ff96"'), encoding="utf-8")
        G.CREATE = copy
        try:
            self.assertEqual(G.main(["--check"]), 1)
            self.assertIn('hex = "00ff96"', copy.read_text(encoding="utf-8"), "--check writes nothing")
            self.assertEqual(G.main([]), 0)
            self.assertEqual(G.main(["--check"]), 0)
        finally:
            G.CREATE = old


if __name__ == "__main__":
    unittest.main()

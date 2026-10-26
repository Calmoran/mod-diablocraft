"""Legendary rest, bead diablocraft-vix14: Blackthorne's Battlegear 4-piece (any class), the set's whole bead (its 2- and 3-piece are stat-only, diablocraft-a13xy).

  "You are immune to Desecrator, Molten, and Plagued monster ground effects."
  * the text is read from d3planner (data_itemsets.js blackthorne, 4: a format, no number) and the set tooltip the crafting generator wrote; the table
    (data/legendary_powers.csv) holds ONE `immune` row at pieces 4: `ground_effects`, 1 (a flag);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator takes
    `ground_effects` as an immunity and refuses another number, a condition or an event;
  * the production rule (src/combat/dc_item_power_math.h: Immunities) is compiled and driven with the generated rows: `ground_effects` is on from the
    4th distinct piece, not at 3, not for another set's 4; Ice Climbers' freeze and root are unchanged beside it;
  * mutants of the rule and of the row fail the same driver, and mutants of the refresh (src/combat/dc_item_powers.cpp Immunize) fail the source guards:
    World's N-BLACKTHORNE mark (DC::Rifts::SetGroundEffectImmune, docs/contracts/legendary-world-pieces.md) is set from the row on EVERY refresh, after the
    item powers' lock, and `ground_effects` never reaches the core spell immunity (it is no mechanic). World's reader of the mark is its own
    test_blackthorne_immunity.py; the in-game steps are docs/test-diablocraft-vix14.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_blackthornes_battlegear/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SET = "Blackthorne's Battlegear"
SQL_SET = SET.replace("'", "''")
STAT = "ground_effects"
TEXT = "You are immune to Desecrator, Molten, and Plagued monster ground effects."
ROW = re.compile(r"\('((?:[^']|'')*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1].replace("''", "'"), int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]),
             m[13], m[14], float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    """The set's 4-piece rows; its 2- and 3-piece rows are the stat-only set levels' (test_item_power_stat_set_levels.py)."""
    return [r for r in (all_rows() if rows is None else rows) if r[0] == SET and r[1] == 4]


def ice(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == "Unique_Boots_008_x1"]


class Table(unittest.TestCase):
    def test_the_sources_give_the_four_piece_text_and_no_number(self):
        text = (REPO / "reference/d3planner/data_itemsets.js").read_text(encoding="utf-8")
        start = text.index("  blackthorne: {")
        block = text[start:text.index("\n  },\n", start)]
        self.assertIn('"4": [\n        {format: "%s"},\n      ],' % TEXT, block)
        self.assertIn("INSERT INTO `dc_set_bonus` VALUES ('blackthorne',4,'%s');" % TEXT,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))

    def test_one_row_at_four_pieces(self):
        self.assertEqual([(SET, 4, "immune", "", STAT, 1.0, 1.0, *BLANK)], mine())

    def test_the_set_has_five_pieces_that_drop(self):
        pieces = [r for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET]
        self.assertEqual(5, len(pieces))
        self.assertEqual({("yes", "no")}, {(r["pool_version"], r["craft_only"]) for r in pieces})

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == SET and r["pieces"] == "4"]
        self.assertEqual(1, len(rows))
        self.assertIn("data_itemsets.js", rows[0]["source"])
        self.assertIn("SetGroundEffectImmune", rows[0]["note"])

    def test_the_sql_row_of_the_set_immunity(self):
        sql = generator.render(MODULE)
        self.assertIn("('%s',4,'immune','','%s'," % (SQL_SET, STAT), sql)


class Generator(unittest.TestCase):
    BASE = {"owner": SET, "pieces": "4", "kind": "immune", "skill": "", "stat": STAT, "value_min": "1", "value_max": "1", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="blackthorne-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != SET]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_ground_effects_is_an_immunity(self):
        self.assertIn(STAT, generator.IMMUNITIES)
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == SET]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "another number": ({"value_min": "2", "value_max": "2"}, "an immunity is value 1"),
            "another immunity": ({"stat": "ground"}, "an immunity is one of"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "kill"}, "an immunity is simply on"),
            "an event": ({"fire_on": "kill"}, "an event fires"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemblack-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    @staticmethod
    def cases(rows):
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        for pieces in range(0, 6):   # the 4th distinct piece turns it on, the 5th keeps it
            out += clear + [(T("count", SET, pieces), None), (T("immune"), STAT if pieces >= 4 else "-")]
        out += clear + [(T("count", "Born's Command", 4), None), (T("immune"), "-")]   # another set's 4 pieces
        # beside Ice Climbers' own two, which stay as they were
        out += clear + [(T("wears", "Unique_Boots_008_x1"), None), (T("immune"), "freeze;root")]
        out += [(T("count", SET, 4), None), (T("immune"), "freeze;ground_effects;root")]
        out += [(T("count", SET, 3), None), (T("immune"), "freeze;root")]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_set_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + ice(), "real")
        self.assertEqual(10, len(want))
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows + ice(), "want")
        row_mutants = {
            "at_three_pieces": [r[:1] + (3,) + r[2:] for r in rows],
            "at_five_pieces": [r[:1] + (5,) + r[2:] for r in rows],
            "another_immunity": [r[:4] + ("root",) + r[5:] for r in rows],
            "another_kind": [r[:2] + ("player",) + r[3:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + ice(), name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "a_level_one_short": ("worn->second < row.pieces", "worn->second + 1 < row.pieces"),
            "every_row_is_ground": ("                out.insert(row.stat);\n        return out;", "                out.insert(\"ground_effects\");\n        return out;"),
        }
        for name, (old, new) in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                _, got = self.drive(real.replace(old, new), rows + ice(), name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

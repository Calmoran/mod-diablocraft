"""Legendary rest, bead diablocraft-g7c3b: Eye of Peshkov (Monk spirit stone), on N-CD (Gesture of Orpheus's piece, diablocraft-1i52b).

  "Reduce the cooldown of Breath of Heaven by [38-50]%."
  * the text and range are read from d3planner (data.json items, leg_eyeofpeshkov, min 38 max 50) and the catalogue row; the table
    (data/legendary_powers.csv) holds ONE `skill` row for the pool item Unique_SpiritStone_103_x1: Breath of Heaven, `cooldown_reduction_pct`, 38-50, a
    range the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rule (src/combat/dc_item_power_math.h: CooldownFactor) is compiled with Gesture of Orpheus's harness and driven with the generated row:
    the cooldown is 1 - N/100 of itself with the item's stored roll, only for Breath of Heaven, only while the item is worn; row and rule mutants fail it;
  * the readers are Gesture of Orpheus's (its source guards are reused), and they reach Breath of Heaven: every rune shell names the skill, every
    shell's newest record states the 15 s cooldown (RecoveryTime, the field ItemPowers::Cast's cut needs), and the Monk's Breath of Heaven code starts
    no cooldown of its own that the cut would miss. In-game steps: docs/test-diablocraft-g7c3b.md.
"""
import csv
import json
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_legendary_powers as generator  # noqa: E402
import test_item_power_gesture_of_orpheus as orpheus  # noqa: E402
from test_item_power_gesture_of_orpheus import BLANK, MATH, T, read_csv  # noqa: E402
from test_item_power_gesture_of_orpheus_wiring import COMBAT, POWERS, reader_failures  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_SpiritStone_103_x1"
SKILL = "Breath of Heaven"
STAT = "cooldown_reduction_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")


def mine():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8")) if m[1] == OWNER]


def planner():
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_sources_say_breath_of_heaven_cooldown_38_to_50(self):
        text, low, high = planner()
        self.assertEqual("Reduce the cooldown of Breath of Heaven by %d%%.", text)
        self.assertEqual((38.0, 50.0), (low, high))
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Reduce the cooldown of Breath of Heaven by [38-50]%.", catalogue[0]["power_text"])

    def test_one_row_names_breath_of_heaven_with_the_range(self):
        _, low, high = planner()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, *BLANK)], mine())

    def test_the_owner_is_the_monk_spirit_stone_that_drops(self):
        items = [r for r in read_csv("data/d3/base_items.csv") if r["d3_name"] == "Eye of Peshkov"]
        self.assertEqual([OWNER], [r["d3_id"] for r in items])   # no legacy twin
        item = items[0]
        self.assertEqual(("head", "Spirit Stone", "legendary", "monk", "yes", "no"),
                         (item["slot"], item["type"], item["rarity"], item["designated_class"], item["pool_version"], item["craft_only"]))


class Rules(orpheus.Rules):
    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        out += clear + [(T("factor", SKILL), "1")]
        out += clear + [(T("rolled", OWNER, SKILL, STAT, low), None), (T("factor", SKILL), "1")]
        # worn, each end of the roll: 38% off is 0.62 of the cooldown (15 s to 9.3 s), 50% off 0.5 (7.5 s)
        for roll in (low, high):
            out += clear + [(T("wears", OWNER, SKILL, STAT, roll), None), (T("factor", SKILL), "%.10g" % (1 - roll / 100))]
        out += clear + [(T("wears", OWNER, SKILL, STAT, low), None)]
        for other in ("Slow Time", "Inner Sanctuary", "breath of heaven", ""):
            out += [(T("factor", other), "1")]
        out += clear + [(T("wears", "Some Ring", SKILL, STAT, 40), None), (T("factor", SKILL), "1")]
        return out

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 6)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        mutants = {
            "the_skill_lost": (real, [r[:3] + ("Slow Time",) + r[4:] for r in rows]),
            "the_wrong_stat": (real, [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows]),
            "no_rows": (real, []),
            "lengthens": (real.replace("std::max(0.0, 1.0 - pct / 100.0)", "std::max(0.0, 1.0 + pct / 100.0)"), rows),
            "the_bottom_not_the_roll": (real.replace("number = found->value;", "number = row.min;"), rows),
        }
        for name, (header, mutant_rows) in mutants.items():
            with self.subTest(mutant=name):
                self.assertTrue(header != real or mutant_rows != rows, name + " did not apply")
                _, got = self.drive(header, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

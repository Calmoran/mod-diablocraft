"""Item-set bonus text (diablocraft-bmyff): every bonus of data/d3/barbarian_sets.csv is the current text of
reference/d3planner/data.json itemSets (the catalogue's source rule for set bonuses; data_itemsets.js is the older archive).

The expected text is rendered from data.json at run time, never typed here. The rule that maps data.json to the sheet's wording:
  * a `{format: ...}` entry is its text with `%%` written `%`;
  * a `{stat, value}` entry is stats[stat].format filled with the value, then a full stop;
  * the entries of one piece count are joined with one space;
  * a piece count data.json does not list holds the sheet's placeholder `None (2-piece set)`.
The sheet and data.json must name the same Barbarian sets, and data.json may list only the piece counts 2, 4 and 6.
"""
import csv
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SHEET = REPO / "mod-diablocraft/data/d3/barbarian_sets.csv"
PLANNER = REPO / "reference/d3planner/data.json"
NONE = "None (2-piece set)"
PIECES = ("2", "4", "6")


def render(planner, entries):
    out = []
    for e in entries:
        if "format" in e:
            out.append(e["format"].replace("%%", "%"))
        else:
            out.append(planner["stats"][e["stat"]]["format"] % tuple(e["value"]) + ".")
    return " ".join(out)


def planner_sets(planner):
    """name -> bonuses of the Barbarian sets in data.json itemSets."""
    found = {}
    for key, s in planner["itemSets"].items():
        if "barbarian" in (s.get("class"), s.get("tclass")):
            assert s["name"] not in found, key
            found[s["name"]] = s["bonuses"]
    return found


class SetBonuses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = json.loads(PLANNER.read_text(encoding="utf-8"))
        cls.sets = planner_sets(cls.planner)
        with SHEET.open(encoding="utf-8", newline="") as f:
            cls.rows = list(csv.DictReader(f, strict=True))

    def test_same_sets(self):
        self.assertEqual(set(self.sets), {r["set_name"] for r in self.rows})

    def test_only_two_four_six_piece_bonuses(self):
        for name, bonuses in self.sets.items():
            self.assertTrue(set(bonuses) <= set(PIECES), (name, sorted(bonuses)))

    def test_every_sheet_bonus_is_the_planner_text(self):
        self.assertTrue(self.rows)
        for r in self.rows:
            bonuses = self.sets[r["set_name"]]
            for n in PIECES:
                want = render(self.planner, bonuses[n]) if n in bonuses else NONE
                self.assertEqual(want, r["bonus_%spc" % n], (r["set_name"], r["item_name"], n))


if __name__ == "__main__":
    unittest.main()

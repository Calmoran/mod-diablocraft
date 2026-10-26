"""Legendary rest, folded bead diablocraft-a13xy: the stat-only set levels (list rows 70-82) as rows on wn9q7's N-SETSTAT reader.

  * every level's numbers and affix ids are read from d3planner (data_itemsets.js), the set's version being the one the catalogue
    (docs/research/legendary-catalogue.csv) names: aughild_v2, cain_v2 and crimson_v2 are D3's current sets; the rest have one version;
  * a level's plain stats are `stat` rows at its `pieces` (the reader puts them on the sheet through the item affix map); Aughild's 2-piece
    (dmgred 15, dmgmul 30) is two `player` rows, `damage_reduction_pct` and `damage_dealt_pct`, the standing readers of those words;
  * Aughild's 3-piece and Blackthorne's 3-piece, left out here for want of `edef` (damage from elites reduced), are built by diablocraft-5ozrm
    on its new Stat::EliteReduction (scripts/tests/monsters/test_elite_damage_reduction.py) and checked here with the rest;
  * every set stat row's id is a key of dc_items_data.cpp Mappings and of the generator's SET_STATS, and the set stat rows' contribution ids stay
    under the Cube's 256;
  * mutants of the rows fail the same check.
The reader itself (on from the level's piece count, off under it) is test_item_power_ashearas_vestments.py's; the in-game steps are in
docs/test-diablocraft-a13xy.md.
"""
import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
ROW = re.compile(r"\('((?:[^']|'')*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
# The levels this bead builds: (set, pieces). Asheara's 2-piece is wn9q7's.
BUILT = [("Asheara's Vestments", 3), ("Aughild's Authority", 2), ("Blackthorne's Battlegear", 2), ("Born's Command", 2), ("Born's Command", 3),
         ("Cain's Destiny", 2), ("Captain Crimson's Trimmings", 2), ("Demon's Hide", 3), ("Hallowed Protectors", 2), ("Krelm’s Buff Bulwark", 2),
         ("Sage's Journey", 2)]
EDEF = [("Aughild's Authority", 3), ("Blackthorne's Battlegear", 3)]   # diablocraft-5ozrm's, on Stat::EliteReduction
# d3planner ids the sheet reads as a player row, not an affix (Aughild's 2-piece)
PLAYER = {"dmgred": "damage_reduction_pct", "dmgmul": "damage_dealt_pct"}


def read_csv(name, base=MODULE):
    with (base / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1].replace("''", "'"), int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13],
             m[14], float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def version(name):
    """The d3planner key of the set the catalogue reads (its second column)."""
    keys = {r[1] for r in csv.reader((REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8").splitlines()) if len(r) > 2 and r[0] == name and r[2] == "set"}
    assert len(keys) == 1, (name, keys)
    return keys.pop()


def planner(name, pieces):
    """[(affix id, value)] of one level of the set the catalogue names."""
    text = (REPO / "reference/d3planner/data_itemsets.js").read_text(encoding="utf-8")
    start = text.index("\n  %s: {" % version(name))
    block = text[start:text.index("\n  },", start + 1)]
    level = re.search(r'"%d": \[(.*?)\n\s*\],' % pieces, block, re.S)[1]
    return [(s, float(v)) for s, v in re.findall(r'stat: "(\w+)", value: \[(\d+)\]', level)]


def want(name, pieces):
    out = []
    for stat, value in planner(name, pieces):
        kind, stat = ("player", PLAYER[stat]) if stat in PLAYER else ("stat", stat)
        out.append((name, pieces, kind, "", stat, value, value, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0))
    return sorted(out)


def mappings():
    text = items_source.read("dc_items_data.cpp")
    body = text[text.index("std::unordered_map<std::string, StatMapping> const& Mappings()"):]
    return dict(re.findall(r'\{"(\w+)", \{Stat::(\w+)', body[:body.index("return mappings;")]))


def wrong(rows):
    """What the rows get wrong against the planner and the sheet: an empty list when right."""
    out = []
    for name, pieces in BUILT + EDEF:
        got = sorted(r for r in rows if (r[0], r[1]) == (name, pieces))
        if got != want(name, pieces):
            out.append("%s %d: %s != %s" % (name, pieces, got, want(name, pieces)))
    mapped = mappings()
    for r in rows:
        if r[1] and r[2] == "stat" and (r[4] not in mapped or r[4] not in generator.SET_STATS):
            out.append("%s %d: %s is not on the sheet" % (r[0], r[1], r[4]))
    return out


class Table(unittest.TestCase):
    def test_the_rows_are_the_planners(self):
        self.assertEqual([], wrong(all_rows()))

    def test_the_current_sets_are_read(self):
        self.assertEqual(("aughild_v2", "cain_v2", "crimson_v2"),
                         (version("Aughild's Authority"), version("Cain's Destiny"), version("Captain Crimson's Trimmings")))

    def test_the_edef_levels_are_on_the_elite_reduction(self):
        self.assertEqual("EliteReduction", mappings()["edef"])
        for name, pieces in EDEF:
            self.assertIn("edef", [s for s, _ in planner(name, pieces)], name)

    def test_each_level_is_a_set_with_pieces(self):
        names = {r["set_name"] for r in read_csv("data/d3/base_items.csv")}
        self.assertEqual(set(), {n for n, _ in BUILT + EDEF} - names)

    def test_every_row_has_its_source(self):
        for r in read_csv("data/legendary_powers.csv"):
            if (r["owner"], int(r["pieces"] or 0)) in BUILT:
                self.assertIn("data_itemsets.js:", r["source"], r)
                self.assertIn("diablocraft-a13xy", r["source"], r)

    def test_the_contribution_ids_stay_under_the_cube(self):
        count = len([r for r in all_rows() if r[1] and r[2] == "stat"])
        self.assertLessEqual(3 + count - 1, 255)

    def test_the_rows_render_through_the_generator(self):
        self.assertEqual(generator.render(MODULE), GENERATED.read_text(encoding="utf-8"))


class Mutants(unittest.TestCase):
    def test_the_mutants_fail_the_same_check(self):
        rows = all_rows()

        def swap(pick, change):
            return [change(r) if pick(r) else r for r in rows]

        crimson = lambda r: r[0] == "Captain Crimson's Trimmings" and r[4] == "cdr"  # noqa: E731
        mutants = {
            "a_value_changed": swap(lambda r: r[0] == "Krelm’s Buff Bulwark", lambda r: r[:5] + (400.0, 400.0) + r[7:]),
            "the_old_crimson": swap(crimson, lambda r: r[:5] + (10.0, 10.0) + r[7:]),
            "a_level_moved": swap(lambda r: r[0] == "Demon's Hide" and r[4] == "area", lambda r: r[:1] + (2,) + r[2:]),
            "another_stat": swap(lambda r: r[0] == "Born's Command" and r[4] == "life", lambda r: r[:4] + ("vit",) + r[5:]),
            "a_row_dropped": [r for r in rows if not (r[0] == "Sage's Journey" and r[4] == "int")],
            "aughild_as_an_affix": swap(lambda r: r[0] == "Aughild's Authority" and r[4] == "damage_dealt_pct", lambda r: r[:2] + ("stat", "", "dmgmul") + r[5:]),
            "edef_dropped": [r for r in rows if not (r[0] == "Aughild's Authority" and r[1] == 3 and r[4] == "edef")],
            "edef_value": swap(lambda r: r[0] == "Blackthorne's Battlegear" and r[4] == "edef", lambda r: r[:5] + (30.0, 30.0) + r[7:]),
            "an_unmapped_stat": swap(lambda r: r[0] == "Hallowed Protectors" and r[4] == "ias", lambda r: r[:4] + ("meleedef",) + r[5:]),
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(mutant, rows, name + " changed nothing")
                self.assertTrue(wrong(mutant), name + " survived")


if __name__ == "__main__":
    unittest.main()

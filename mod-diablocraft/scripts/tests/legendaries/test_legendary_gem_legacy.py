"""diablocraft-do2wo (legendary build 2, bead 1): Legacy of Dreams; diablocraft-5s8z6: the Ancient doubling from rank 25.

  * the gem id the power names is the sheet's Legacy of Dreams, and its numbers are d3planner's: the damage per legendary
    item is value/delta/maxlevel (3.75, +3.75 a rank, cap 99), the damage-taken reduction is the 2 of its text and of its
    `dmgred: 2 * items` (reference/d3planner/data_gems.js `legacyofdreams`); the Ancient doubling is the gem's rank-25
    power (ruling 2026-10-12, diablocraft-5s8z6; d3planner's every-level reading is not followed): the sheet has it as
    the rank_25_bonus, and Ancients count once below rank 25, twice from it;
  * a set bonus is two pieces of any set, built or not (ruling 2026-10-12): every worn set's lowest bonus in d3planner's
    itemSets is 2;
  * the production rules (src/combat/dc_gem_power_math.h Resolve, LegacyItems, LegacyFactor, LegacyIncomingFactor and
    src/combat/dc_item_power_math.h AnySetBonus) are compiled and driven with the generated gem row, at 16 ranks (0, a
    mid rank, the cap and above it), 0 to 13 legendary items with and without Ancients, and the set counts that turn it
    off: two pieces of a set with built rows (Wrath of the Wastes, Bastions of Will) or without (Immortal King's Call)
    turn it off, one piece of each does not;
  * mutants of the rules fail the same driver;
  * source-text guards that the hit and both damage-taken paths read it and that the worn legendaries are kept beside the
    set counter (they prove the call is there, not that it runs; the C++ is compile-checked by syntax_check.sh and the
    in-game steps are docs/test-diablocraft-do2wo.md).
"""
import csv
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import test_legendary_gem_powers as gempowers
import test_legendary_gems as numbers

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
GEM_MATH = SRC / "combat/dc_gem_power_math.h"
ITEM_MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/legendary_gem_legacy/harness.cpp"
POWERS_SQL = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))
PLANNER_GEMS = REPO / "reference/d3planner/data_gems.js"
PLANNER_DATA = REPO / "reference/d3planner/data.json"
BASE_ITEMS = MODULE / "data/d3/base_items.csv"
SCRATCH = numbers.SCRATCH
NAME = "Legacy of Dreams"
WASTES, BASTIONS, KINGS = "Wrath of the Wastes", "Bastions of Will", "Immortal King's Call"


def legacy_id():
    return re.search(r'Legacy = "(Unique_Gem_\d+_x1)"', GEM_MATH.read_text(encoding="utf-8")).group(1)


def planner_block():
    text = PLANNER_GEMS.read_text(encoding="utf-8")
    start = text.index("  legacyofdreams: {")
    return text[start:text.index("\n  },\n", start)]


def reduction_pct():
    """The 2 of d3planner's text ("reduces your damage taken by 2%%"), which its buffs line must also use."""
    block = planner_block()
    text = float(re.search(r"reduces your damage taken by (\d+(?:\.\d+)?)%%", block).group(1))
    buffs = float(re.search(r"dmgred: (\d+(?:\.\d+)?) \* items", block).group(1))
    assert text == buffs, (text, buffs)
    return text


def set_levels():
    """set -> the levels the table has a power row for (the generated migration)."""
    levels = {}
    for owner, pieces in re.findall(r"^\('([^']*)',(\d+),", POWERS_SQL.read_text(encoding="utf-8"), re.M):
        if int(pieces):
            levels.setdefault(owner, set()).add(int(pieces))
    return levels


class Numbers(unittest.TestCase):
    def test_the_gem_is_the_sheets_legacy_of_dreams_with_d3planners_numbers(self):
        sheet = next(r for r in numbers.read(numbers.CSV) if r["gem_id"] == legacy_id())
        self.assertEqual(NAME, sheet["gem_name"])
        gem_id, value, delta, cap = numbers.planner()[NAME]
        self.assertEqual(legacy_id(), gem_id)
        row = gempowers.gem_rows()[gem_id]
        self.assertEqual((value[0], delta[0], cap), (row[0], row[1], row[4]))
        self.assertEqual(reduction_pct(), row[7])  # fixed_1

    def test_the_ancient_doubling_is_the_sheets_rank_25_power(self):
        """The source of the rank-25 gate (ruling 2026-10-12): the sheet's rank_25_bonus, not its base_effect."""
        sheet = next(r for r in numbers.read(numbers.CSV) if r["gem_id"] == legacy_id())
        self.assertEqual("This bonus is doubled for Ancient items.", sheet["rank_25_bonus"])
        self.assertNotIn("Ancient", sheet["base_effect"])
        self.assertIn("Rank25 = 25;", GEM_MATH.read_text(encoding="utf-8"))

    def test_every_worn_sets_first_bonus_is_two_pieces(self):
        """SetBonusPieces against the source: each set a player can wear (base_items.csv) has its lowest bonus at 2."""
        pieces = int(re.search(r"SetBonusPieces = (\d+);", ITEM_MATH.read_text(encoding="utf-8")).group(1))
        with BASE_ITEMS.open(encoding="utf-8") as f:
            worn = {r["set_name"] for r in csv.DictReader(f) if r["rarity"] == "set" and r["set_name"]}
        lowest = {s["name"]: min(int(k) for k in s["bonuses"])
                  for s in json.loads(PLANNER_DATA.read_text(encoding="utf-8"))["itemSets"].values() if s.get("bonuses")}
        self.assertGreater(len(worn), 50)
        self.assertEqual({}, {s: lowest.get(s) for s in worn if lowest.get(s) != pieces})

    def test_the_cases_hold_a_set_with_rows_and_one_without(self):
        levels = set_levels()
        self.assertIn(2, levels[WASTES])
        self.assertIn(2, levels[BASTIONS])
        self.assertNotIn(KINGS, levels)


class Rules(unittest.TestCase):
    SETS = ([], [(WASTES, 1)], [(WASTES, 2)], [(WASTES, 5)], [(KINGS, 1)], [(KINGS, 2)], [(KINGS, 6)],
            [(BASTIONS, 1), (WASTES, 1), (KINGS, 1)], [(BASTIONS, 2)], [(KINGS, 6), (WASTES, 3)])
    WORN = ((0, 0), (1, 0), (1, 1), (7, 3), (13, 0), (13, 6), (13, 13))

    @classmethod
    def build(cls, gem_text, item_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {**{rel: (SRC / rel).read_text(encoding="utf-8") for rel in ("common/dc_legendary_gem.h", "items/dc_legendary_gem_item.h")}, "combat/dc_gem_power_math.h": gem_text, "combat/dc_item_power_math.h": item_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="legacy-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self):
        """[(rank or None, legendaries, ancients, sets)]: every rank with every worn mix and set state, and the gem not worn."""
        out = [(rank, l, a, sets) for rank in numbers.RANKS for l, a in self.WORN for sets in self.SETS]
        out += [(None, l, a, sets) for l, a in self.WORN for sets in self.SETS[:3]]
        return out

    def want(self, rank, legendaries, ancients, sets):
        on = any(worn >= 2 for _, worn in sets)
        items = 0 if on else legendaries + (ancients if rank is not None and rank >= 25 else 0)
        if rank is None:
            return [int(on), items, 1.0, 1.0]
        value = gempowers.planner_value(legacy_id(), rank)
        return [int(on), items, 1 + value * items / 100, 1 - reduction_pct() * items / 100]

    def drive(self, gem_text, item_text, name):
        f = lambda v: "none" if v is None else repr(v)
        lines = ["\t".join(["gem", g] + [repr(c[0]), repr(c[1])] + [f(c[i]) for i in (4, 2, 3, 7, 8, 9, 5, 6)])
                 for g, c in gempowers.gem_rows().items()]
        cases = self.cases()
        for rank, l, a, sets in cases:
            lines.append("\t".join(["case", legacy_id(), "none" if rank is None else str(rank), str(l), str(a), str(len(sets))] +
                                   [x for s in sets for x in (s[0], str(s[1]))]))
        work, binary = self.build(gem_text, item_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(lines) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            got = [[float(x) for x in line.split()] for line in run.stdout.splitlines()]
            return got, [self.want(*c) for c in cases]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def real(self):
        return GEM_MATH.read_text(encoding="utf-8"), ITEM_MATH.read_text(encoding="utf-8")

    def test_every_rank_count_and_set_state_is_the_sheets(self):
        got, want = self.drive(*self.real(), "real")
        self.assertGreater(len(want), 900)
        self.assertTrue(gempowers.Sums.agrees(got, want))

    def test_rank_0_a_mid_rank_and_the_cap(self):
        """The numbers the test sheet's Checks quote: 13 legendaries, 6 of them Ancient, no set bonus."""
        self.assertEqual([0, 13, 1.4875, 0.74], self.want(0, 13, 6, []))
        self.assertEqual([0, 19, 1 + 191.25 * 19 / 100, 0.62], self.want(50, 13, 6, []))
        self.assertEqual([0, 19, 72.25, 0.62], self.want(99, 13, 6, []))
        self.assertEqual(self.want(99, 13, 6, []), self.want(150, 13, 6, []))
        self.assertEqual([1, 0, 1.0, 1.0], self.want(99, 13, 6, [(WASTES, 2)]))
        self.assertEqual([1, 0, 1.0, 1.0], self.want(99, 13, 6, [(KINGS, 2)]))

    def test_rank_24_counts_an_ancient_once_rank_25_twice(self):
        """diablocraft-5s8z6: the doubling starts at rank 25, read from the compiled rules."""
        got, want = self.drive(*self.real(), "rank25")
        cases = self.cases()
        at = lambda rank: [g[1] for c, g in zip(cases, got) if c[0] == rank and c[1:] == (7, 3, [])]
        self.assertEqual([7.0], at(24))
        self.assertEqual([10.0], at(25))
        self.assertTrue(gempowers.Sums.agrees(got, want))

    def test_the_mutants_fail_the_same_driver(self):
        gem, item = self.real()
        mutants = {
            "set ignored": (gem.replace("if (setBonusOn)\n            return 0;", ""), item),
            "ancients never twice": (gem.replace("powers.legacyAncientsTwice ? ancients : 0", "0"), item),
            "ancients twice at every rank": (gem.replace("powers.legacyAncientsTwice = rank25;",
                                                         "powers.legacyAncientsTwice = true;"), item),
            "ancients twice from rank 24": (gem.replace("powers.legacyAncientsTwice = rank25;",
                                                        "powers.legacyAncientsTwice = gem.rank >= 24;"), item),
            "reduction scales with rank": (gem.replace("powers.legacyReductionPct = Fixed(*row, 0);",
                                                       "powers.legacyReductionPct = value;"), item),
            "a multiplier per item": (gem.replace("return 1.0 + powers.legacyDamagePct * items / 100.0;",
                                                  "return std::pow(1.0 + powers.legacyDamagePct / 100.0, items);"), item),
            "not resolved": (gem.replace("gem.gemId == Legacy", "false"), item),
            "one piece of a set counts": (gem, item.replace("SetBonusPieces = 2;", "SetBonusPieces = 1;")),
            "a set counts from three": (gem, item.replace("SetBonusPieces = 2;", "SetBonusPieces = 3;")),
            "only built sets count": (gem, item.replace("if (worn >= SetBonusPieces)",
                                                        "if (worn >= SetBonusPieces && set != \"Immortal King's Call\")")),
        }
        for name, (g, i) in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual((g, i), (gem, item), name)
                got, want = self.drive(g, i, name.replace(" ", "-"))
                self.assertFalse(gempowers.Sums.agrees(got, want), name)


if __name__ == "__main__":
    unittest.main()

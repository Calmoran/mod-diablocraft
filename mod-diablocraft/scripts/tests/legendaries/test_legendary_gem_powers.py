"""diablocraft-t8e6 (Legendary gems part 10b-1): the always-on gem powers.

  * the five gem ids the powers name are the sheet's gems (name check against legendary_gems.csv);
  * the production sums (src/combat/dc_gem_power_math.h: Unique Equipped's Counted, Resolve, the damage-taken
    and primary factors) are compiled and driven with the generated number rows against d3planner's
    value/delta/maxlevel, for every power at 16 ranks, with all five worn and with duplicates;
  * mutants of the sums fail the same driver;
  * source-text guards that the hooks call them (they prove the call is there, not that it runs; the C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-legendary-gem-powers.md).
"""
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import test_legendary_gems as numbers

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_gem_power_math.h"
HARNESS = MODULE / "tests/legendary_gem_powers/harness.cpp"
SCRATCH = numbers.SCRATCH

IDS = {  # constant name in the header -> the gem the sheet names
    "Wildebeest": "Molten Wildebeest's Gizzard",
    "Boyarsky": "Boyarsky's Chip",
    "Esoteric": "Esoteric Alteration",
    "Mutilation": "Mutilation Guard",
    "Simplicity": "Simplicity's Strength",
}
RANKS = numbers.RANKS


def gem_rows():
    """gem_id -> the eleven columns of the generated INSERT (base, per_rank, base2, per2, max, r25a, r25b, f1..f3)."""
    sql = numbers.GENERATED.read_text(encoding="utf-8")
    out = {}
    for gem_id, cells in re.findall(r"^\('(Unique_Gem_\d+_x1)'," + ",".join([r"'(?:[^'\\]|''|\\.)*'"] * 3) + r",(.*)\)[,;]$", sql, re.M):
        out[gem_id] = [None if x == "NULL" else float(x) for x in cells.split(",")]
    return out


def planner_value(gem_id, rank):
    gem = next(g for g in numbers.planner().values() if g[0] == gem_id)
    top = rank if gem[3] is None else min(rank, gem[3])
    return gem[1][0] + gem[2][0] * top


class Ids(unittest.TestCase):
    def test_every_named_gem_is_the_one_the_sheet_calls_that(self):
        header = MATH.read_text(encoding="utf-8")
        sheet = {r["gem_id"]: r["gem_name"] for r in numbers.read(numbers.CSV) if r["gem_id"]}
        for const, name in IDS.items():
            gem_id = re.search(r'%s = "(Unique_Gem_\d+_x1)"' % const, header).group(1)
            self.assertEqual(name, sheet[gem_id], const)


class Sums(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {**{rel: (SRC / rel).read_text(encoding="utf-8") for rel in ("common/dc_legendary_gem.h", "items/dc_legendary_gem_item.h")}, "combat/dc_gem_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="gempowers-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self):
        """[(worn, physical, melee, primary)]: each power alone at every rank, then everything worn."""
        ids = {c: self.constant(c) for c in IDS}
        out = []
        for const, gem_id in ids.items():
            for rank in RANKS:
                for physical, melee, primary in ((1, 0, 0), (0, 1, 1), (1, 1, 0), (0, 0, 1)):
                    out.append(([(gem_id, rank)], physical, melee, primary))
        everything = [(g, 40) for g in ids.values()]
        out.append((everything, 0, 1, 1))
        # Unique Equipped: two of a kind, the highest rank counts, whatever the order
        out.append(([(ids["Esoteric"], 10), (ids["Esoteric"], 90), (ids["Mutilation"], 5)], 0, 1, 0))
        out.append(([(ids["Esoteric"], 90), (ids["Esoteric"], 10)], 0, 0, 0))
        # a gem that is not one of these five adds nothing to them (Legacy of Dreams' own numbers: test_legendary_gem_legacy.py)
        out.append(([("Unique_Gem_023_x1", 50)], 0, 1, 1))
        return out

    @staticmethod
    def constant(const):
        return re.search(r'%s = "(Unique_Gem_\d+_x1)"' % const, MATH.read_text(encoding="utf-8")).group(1)

    def want(self, worn, physical, melee, primary):
        ids = {self.constant(c): c for c in IDS}
        best = {}
        for gem_id, rank in worn:
            best[gem_id] = max(best.get(gem_id, 0), rank)
        v = {ids[g]: planner_value(g, r) for g, r in best.items() if g in ids}
        life, thorns = v.get("Wildebeest", 0), v.get("Boyarsky", 0)
        nonphys, melee_pct, prim = v.get("Esoteric", 0), v.get("Mutilation", 0), v.get("Simplicity", 0)
        incoming = (1 if physical else 1 - nonphys / 100) * (1 - melee_pct / 100 if melee else 1)
        return [life, thorns, nonphys, melee_pct, prim, incoming, 1 + prim / 100 if primary else 1]

    def drive(self, header_text, name):
        f = lambda v: "none" if v is None else repr(v)
        lines = ["row %s %r %r %s %s %s %s %s %s %s %s" % (g, c[0], c[1], f(c[4]), f(c[2]), f(c[3]), f(c[7]), f(c[8]),
                                                          f(c[9]), f(c[5]), f(c[6])) for g, c in gem_rows().items()]
        cases = self.cases()
        for worn, physical, melee, primary in cases:
            lines.append("case %d %s %d %d %d" % (len(worn), " ".join("%s %d" % w for w in worn),
                                                  physical, melee, primary))
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(lines) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            got = [[float(x) for x in line.split()] for line in run.stdout.splitlines()]
            return got, [self.want(*c) for c in cases]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @staticmethod
    def agrees(got, want):
        return len(got) == len(want) and all(
            abs(a - b) <= 1e-6 * max(1.0, abs(b)) for g, w in zip(got, want) for a, b in zip(g, w))

    def test_every_power_at_every_rank_is_d3planners_value(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 300)
        self.assertTrue(self.agrees(got, want))
        # the sheet's own text: Esoteric 10% + 0.5% a rank, capped at 60% (rank 100); Mutilation the same
        i = next(n for n, c in enumerate(self.cases()) if c[0] == [(self.constant("Esoteric"), 300)] and not c[1])
        self.assertAlmostEqual(60.0, got[i][2])
        self.assertAlmostEqual(0.4, got[i][5])

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "melee_ignored": real.replace("if (melee)\n            factor", "if (true)\n            factor"),
            "physical_inverted": real.replace("if (!physical)", "if (physical)"),
            "primary_flag_ignored": real.replace("return primary ? 1.0 +", "return true ? 1.0 +"),
            "esoteric_is_mutilation": real.replace("powers.nonPhysicalReductionPct = value;", "powers.meleeReductionPct = value;"),
            "reduction_added_not_multiplied": real.replace("factor *= 1.0 - powers.meleeReductionPct / 100.0",
                                                           "factor -= powers.meleeReductionPct / 100.0"),
            "thorns_dropped": real.replace("powers.thorns = value", "powers.thorns = 0"),
        }
        for name, mutant in mutants.items():
            self.assertNotEqual(real, mutant, "the %s mutation no longer applies" % name)
            got, want = self.drive(mutant, name)
            self.assertFalse(self.agrees(got, want), "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

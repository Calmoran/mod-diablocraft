"""diablocraft-dylx (Legendary gems part 10b-2): group B, the damage multipliers and the stacking buffs.

  * the seven gem ids the code names are the sheet's gems;
  * the production math (src/combat/dc_gem_power_math.h: Resolve, the stacking clock, the step 8 factor, Taeguk's
    step 4 percent, Gogok's Dodge and Attack Speed, Invigorating's healing factor, Zei's distance) is compiled and
    driven with the generated number rows. Every expected value comes from d3planner (value/delta/maxlevel and the
    numbers of its text), never from the code under test;
  * the clock (stacks share one expiry, each stack refreshes it, a cap, the signed wrap) against an independent model;
  * mutants of the math fail the same driver;
  * source-text guards that the hooks call it (they prove the call is there, not that it runs; the C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-legendary-gem-group-b.md).
"""
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source  # noqa: E402
import harness_env
import test_legendary_gems as numbers

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_gem_power_math.h"
HARNESS = MODULE / "tests/legendary_gem_group_b/harness.cpp"
SCRATCH = numbers.SCRATCH

IDS = {  # constant name in the header -> the gem the sheet names
    "Powerful": "Bane of the Powerful",
    "Trapped": "Bane of the Trapped",
    "Gogok": "Gogok of Swiftness",
    "Invigorating": "Invigorating Gemstone",
    "Zei": "Zei's Stone of Vengeance",
    "Taeguk": "Taeguk",
    "Stricken": "Bane of the Stricken",
}
RANKS = numbers.RANKS
# (powerful buff up, target control-impaired, attacks on the target, yards, Taeguk, Gogok, Invigorating stacks)
SCENES = [
    (1, 0, 0, 0, 0, 0, 0), (0, 1, 0, 0, 0, 0, 0), (0, 0, 7, 0, 0, 0, 0), (0, 0, 0, 30, 0, 0, 0),
    (0, 0, 0, 50, 0, 0, 0), (0, 0, 0, 80, 0, 0, 0), (0, 0, 0, 0, 10, 0, 0), (0, 0, 0, 0, 0, 15, 0),
    (0, 0, 0, 0, 0, 0, 10), (1, 1, 100, 25, 3, 4, 5), (0, 0, 1, 0, 1, 1, 1),
]


def rows():
    """gem_id -> the eleven columns of the generated INSERT (base, per_rank, base2, per2, max, r25a, r25b, f1..f3)."""
    sql = numbers.GENERATED.read_text(encoding="utf-8")
    out = {}
    for gem_id, cells in re.findall(r"^\('(Unique_Gem_\d+_x1)'," + ",".join([r"'(?:[^'\\]|''|\\.)*'"] * 3) + r",(.*)\)[,;]$", sql, re.M):
        out[gem_id] = [None if x == "NULL" else float(x) for x in cells.split(",")]
    return out


def constant(const):
    return re.search(r'%s = "(Unique_Gem_\d+_x1)"' % const, MATH.read_text(encoding="utf-8")).group(1)


def row_line(gem_id, c):
    f = lambda v: "none" if v is None else repr(v)
    return "row %s %r %r %s %s %s %s %s %s %s %s" % (gem_id, c[0], c[1], f(c[4]), f(c[2]), f(c[3]), f(c[7]), f(c[8]),
                                                    f(c[9]), f(c[5]), f(c[6]))


def build(header_text, name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    files = {**{rel: (SRC / rel).read_text(encoding="utf-8") for rel in ("common/dc_legendary_gem.h", "items/dc_legendary_gem_item.h")}, "combat/dc_gem_power_math.h": header_text}
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
    work = Path(tempfile.mkdtemp(prefix="gemgroupb-%s-" % name, dir=str(SCRATCH)))
    return work, binary


def run(header_text, name, lines):
    work, binary = build(header_text, name)
    try:
        (work / "cases.txt").write_text("\n".join(lines) + "\n")
        return harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Ids(unittest.TestCase):
    def test_every_named_gem_is_the_one_the_sheet_calls_that(self):
        sheet = {r["gem_id"]: r["gem_name"] for r in numbers.read(numbers.CSV) if r["gem_id"]}
        for const, name in IDS.items():
            self.assertEqual(name, sheet[constant(const)], const)


class Math(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d3p = numbers.planner()
        cls.text = numbers.planner_fixed()

    def val(self, key, rank, slot=0):
        gem = self.d3p[IDS[key]]
        top = rank if gem[3] is None else min(rank, gem[3])
        return gem[1][slot] + gem[2][slot] * top

    def cases(self):
        ids = {c: constant(c) for c in IDS}
        out = []
        for const, gem_id in ids.items():
            for rank in RANKS:
                for scene in SCENES:
                    out.append(([(gem_id, rank)], scene))
        for scene in SCENES:
            out.append(([(g, 40) for g in ids.values()], scene))
            # Unique Equipped: two of a kind, the highest rank counts, whatever the order
            out.append(([(ids["Taeguk"], 5), (ids["Taeguk"], 60), (ids["Zei"], 3)], scene))
            out.append(([(ids["Taeguk"], 60), (ids["Taeguk"], 5)], scene))
            # a gem that is not one of these seven adds nothing
            out.append(([("Unique_Gem_016_x1", 50)], scene))
        return out

    def want(self, worn, scene):
        powerful, trapped, stricken, yards, taeguk, gogok, invigorating = scene
        ids = {constant(c): c for c in IDS}
        best = {}
        for gem_id, rank in worn:
            best[gem_id] = max(best.get(gem_id, 0), rank)
        w = {ids[g]: r for g, r in best.items() if g in ids}
        pf = lambda k: self.text[IDS[k]]
        standalone = 1.0
        if "Powerful" in w and powerful:
            standalone *= 1 + pf("Powerful")[0] / 100            # "Gain 20% increased damage" (d3planner dmgmul 20)
        if "Trapped" in w and trapped:
            standalone *= 1 + self.val("Trapped", w["Trapped"]) / 100
        if "Stricken" in w:
            standalone *= 1 + stricken * self.val("Stricken", w["Stricken"]) / 100
        zei = 0.0
        if "Zei" in w:
            # d3planner: distance * (4 + 0.08 * rank) / 10, the distance capped at 50 yards
            zei = min(yards, pf("Zei")[1]) * self.val("Zei", w["Zei"]) / pf("Zei")[0]
            standalone *= 1 + zei / 100
        additive = taeguk * self.val("Taeguk", w["Taeguk"]) if "Taeguk" in w else 0.0
        dodge = gogok * self.val("Gogok", w["Gogok"]) if "Gogok" in w else 0.0
        ias = gogok * pf("Gogok")[0] if "Gogok" in w else 0.0
        healing = 1 + invigorating * self.val("Invigorating", w["Invigorating"]) / 100 if "Invigorating" in w else 1.0
        powerful_s = self.val("Powerful", w["Powerful"]) if "Powerful" in w else 0.0
        t_s, t_max = (pf("Taeguk")[0], pf("Taeguk")[1]) if "Taeguk" in w else (0.0, 0)
        g_s, g_max = (pf("Gogok")[1], pf("Gogok")[2]) if "Gogok" in w else (0.0, 0)
        i_s, i_max = (pf("Invigorating")[0], pf("Invigorating")[1]) if "Invigorating" in w else (0.0, 0)
        return [standalone, additive, dodge, ias, healing, zei, powerful_s, t_s, t_max, g_s, g_max, i_s, i_max]

    def drive(self, header_text, name):
        lines = [row_line(g, c) for g, c in rows().items()]
        cases = self.cases()
        for worn, scene in cases:
            lines.append("case %d %s %d %d %d %r %d %d %d" % (len(worn), " ".join("%s %d" % w for w in worn), *scene))
        done = run(header_text, name, lines)
        self.assertEqual(0, done.returncode, done.stderr)
        got = [[float(x) for x in line.split()] for line in done.stdout.splitlines()]
        return got, [self.want(*c) for c in cases]

    @staticmethod
    def agrees(got, want):
        return len(got) == len(want) and all(
            abs(a - b) <= 1e-6 * max(1.0, abs(b)) for g, w in zip(got, want) for a, b in zip(g, w))

    def test_every_power_at_every_rank_is_d3planners(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 900)
        self.assertTrue(self.agrees(got, want))
        # the sheet's own text: Zei's 4% per 10 yards and its maximum 20% at 50 yards at rank 0
        i = next(n for n, c in enumerate(self.cases()) if c == ([(constant("Zei"), 0)], (0, 0, 0, 80, 0, 0, 0)))
        self.assertAlmostEqual(20.0, got[i][5])
        i = next(n for n, c in enumerate(self.cases()) if c == ([(constant("Zei"), 0)], (0, 0, 0, 30, 0, 0, 0)))
        self.assertAlmostEqual(12.0, got[i][5])

    def test_a_gem_with_no_fixed_number_is_an_error_not_a_zero(self):
        taeguk = constant("Taeguk")
        lines = ["row %s 2 0.04 none none none none none none none none" % taeguk,
                 "case 1 %s 0 0 0 0 0 0 0 0" % taeguk]
        self.assertNotEqual(0, run(MATH.read_text(encoding="utf-8"), "nofixed", lines).returncode)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "trapped_always": ("if (trapped)", "if (!trapped)"),
            "powerful_always": ("if (powerful)", "if (!powerful)"),
            "stricken_stacks_ignored": ("powers.strickenPctPerAttack * stricken", "powers.strickenPctPerAttack * 1"),
            "zei_uncapped": ("std::min(std::max(yards, 0.0) / powers.zeiYardsPerStep * powers.zeiPctPerStep, powers.zeiMaxPct)",
                             "std::max(yards, 0.0) / powers.zeiYardsPerStep * powers.zeiPctPerStep"),
            "zei_step_is_the_50_yard_number": ("powers.zeiYardsPerStep = Fixed(*row, 0);",
                                              "powers.zeiYardsPerStep = Fixed(*row, 1);"),
            "gogok_ias_is_dodge": ("return powers.gogok.perStack2 * gogokStacks;", "return powers.gogok.perStack * gogokStacks;"),
            "heal_is_additive": ("return 1.0 + HealingPct(powers, invigoratingStacks) / 100.0;",
                                 "return HealingPct(powers, invigoratingStacks) / 100.0;"),
            "taeguk_seconds_and_max_swapped": ("powers.taeguk = {value, 0, Fixed(*row, 0), unsigned(Fixed(*row, 1))};",
                                               "powers.taeguk = {value, 0, Fixed(*row, 1), unsigned(Fixed(*row, 0))};"),
            "gogok_per_stack_unscaled": ("powers.gogok = {value, Fixed(*row, 0)", "powers.gogok = {0.5, Fixed(*row, 0)"),
            "powerful_seconds_unscaled": ("powers.powerfulSeconds = value;", "powers.powerfulSeconds = Fixed(*row, 0);"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            got, want = self.drive(real.replace(old, new), name)
            self.assertFalse(self.agrees(got, want), "mutant %s passed" % name)


class Clock(unittest.TestCase):
    """Every stack refreshes the one expiry; the cap holds; the count reads zero from the expiry on."""

    SCENES = [
        (4.0, 15, [1000 + 100 * i for i in range(20)], [1000, 1850, 2899, 2950, 6899, 6900, 7000]),
        (4.0, 15, [0, 1000, 6000], [0, 1000, 4999, 5000, 5001, 6000, 9999, 10000]),
        (1.5, 10, [500, 500, 500], [500, 1999, 2000]),
        (30.5, 1, [0, 10000, 20000], [0, 40000, 50499, 50500]),
        # the server clock wraps at 2^32 milliseconds: the buff must survive the wrap
        (4.0, 15, [4294966000, 4294967000, 500], [4294967000, 4294967295, 0, 499, 4499, 4500]),
    ]

    @staticmethod
    def model(seconds, cap, adds, queries):
        count, until = 0, 0
        for t in adds:
            live = count if t < until else 0
            count = min(live + 1, cap)
            until = t + round(seconds * 1000)
        return [count if (q if q >= adds[0] else q + 2 ** 32) < until else 0 for q in queries]

    def drive(self, header_text, name):
        lines, want = [], []
        for seconds, cap, adds, queries in self.SCENES:
            # the model works on an unwrapped clock: a time past the wrap is its real value plus 2^32
            unwrapped = [a if a >= adds[0] else a + 2 ** 32 for a in adds]
            lines.append("stack %r %d %d %s %d %s" % (seconds, cap, len(adds), " ".join(str(a) for a in adds),
                                                      len(queries), " ".join(str(q) for q in queries)))
            want.append(self.model(seconds, cap, unwrapped, queries))
        done = run(header_text, name, lines)
        self.assertEqual(0, done.returncode, done.stderr)
        return [[int(x) for x in line.split()] for line in done.stdout.splitlines()], want

    def test_the_clock_is_the_independent_model(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "clock")
        self.assertEqual(want, got)
        self.assertEqual(15, max(got[0]))  # the cap
        self.assertEqual([1, 0], got[1][-2:-1] + got[1][-1:])  # gone at the expiry, one stack after the gap

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "live_at_the_expiry": ("static_cast<std::int32_t>(stacks.untilMs - nowMs) > 0",
                                   "static_cast<std::int32_t>(stacks.untilMs - nowMs) >= 0"),
            "no_cap": ("std::min(Live(stacks, nowMs) + 1, max)", "Live(stacks, nowMs) + 1"),
            "seconds_not_milliseconds": ("std::llround(seconds * 1000.0));", "std::llround(seconds));"),
            "stacks_kept_after_expiry": ("std::min(Live(stacks, nowMs) + 1, max)", "std::min(stacks.count + 1, max)"),
            "unsigned_compare_breaks_the_wrap": ("static_cast<std::int32_t>(stacks.untilMs - nowMs) > 0",
                                                 "stacks.untilMs > nowMs"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            got, want = self.drive(real.replace(old, new), name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

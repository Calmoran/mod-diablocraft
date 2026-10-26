"""The driver two tests share: a `triggered` window that a cast of named skills opens, at a roll the item stores once.

Lefebvre's Soliloquy (a cast of Cyclone Strike opens 5 s of damage reduction) and Spirit Guards (a cast of any of the four Monk primaries
opens 3 s) are one row of the same shape, and their compiled tests were the same driver with other names and numbers. `Item` holds what
differs; `RulesTests` is the test class both subclass (`ITEM = ...`). It compiles src/combat/dc_item_power_math.h through
harness_env.build with the item's generated row and runs the events harness over the cases below; the rule and row mutants must each make
the output differ.

    test_item_power_lefebvres_soliloquy.py, test_item_power_spirit_guards.py
"""
import csv
import re
import shutil
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_events/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
STAT = "damage_reduction_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
taken = lambda p: "%g" % (1 - p / 100)  # noqa: E731
NONE = ["0"]                                   # no set counts


class Item:
    """What differs between the items.

    owner, skills          the pool item and the skills whose cast opens the window (the row's skill cell is ';'-joined)
    numbers                () -> (low, high, seconds) as the planner words them
    other                  a second item with the same shape, so a second source's window can be seen to multiply
    mid_roll               a roll between the ends of the range
    cast, recast           the skill a cast opens the window with, and the two that renew it
    quiet_skill            a skill whose cast is tried against an item that is not worn, has no stored roll or is in the bag
    ignored                skills (and "") whose cast opens nothing
    idle_roll              the stored roll the no-window cases run at
    shorter                a window shorter than the item's, for the row mutant
    skill_mutants          {mutant name: the row's skill cell}
    """

    def __init__(self, owner, skills, numbers, other, mid_roll, cast, recast, quiet_skill, ignored, idle_roll, shorter, skill_mutants, scratch_prefix):
        self.owner, self.skills, self.numbers, self.other_name = owner, skills, numbers, other
        self.cell = ";".join(skills)
        self.mid_roll, self.cast, self.recast, self.quiet_skill = mid_roll, cast, recast, quiet_skill
        self.ignored, self.idle_roll, self.shorter, self.skill_mutants, self.scratch_prefix = ignored, idle_roll, shorter, skill_mutants, scratch_prefix

    @property
    def other(self):
        return [(self.other_name, 0, "player", "", STAT, 20.0, 20.0, "triggered", 3.0, "", 0.0, 0, "cast", self.cell, 100.0, 0.0)]

    def mine(self, rows=None):
        return [r for r in (all_rows() if rows is None else rows) if r[0] == self.owner]


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


class RulesTests:
    """Subclass with `ITEM` and `run_binary(command)`, which runs the compiled harness through harness_env.run in the test file (the
    static check of test_harness_core_limit wants every runner to call the helper itself)."""
    ITEM = None

    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="%s-%s-" % (cls.ITEM.scratch_prefix, name), dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        item = self.ITEM
        owner, idle = item.owner, item.idle_roll
        low, high, seconds = item.numbers()
        ms = int(seconds * 1000)
        out = [(T("row", *r), None) for r in rows]
        fire = lambda event, skill: (T("fire", event, skill, 1, 0, *NONE), "")  # noqa: E731
        reduction = lambda want: (T("reduction", *NONE), want)  # noqa: E731

        def worn(roll, at=1000):
            return [(T("clear"), None), (T("now", at), None), (T("wears", owner, 0), None), (T("value", owner, "", STAT, roll), None)]

        # a cast opens the window at the stored roll, for every end of the range
        for roll in (low, item.mid_roll, high):
            for skill in item.skills:
                out += worn(roll) + [reduction("1"), fire("cast", skill), reduction(taken(roll))]
        # the window: the item's seconds later still on, 1 ms more over; a recast renews it
        first, second = item.recast
        out += worn(50) + [fire("cast", item.cast), (T("now", 1000 + ms), None), reduction(taken(50)),
                           (T("now", 1001 + ms), None), reduction("1")]
        out += worn(50, 10000) + [fire("cast", first), (T("now", 12000), None), fire("cast", second), (T("now", 12000 + ms - 1), None),
                                  reduction(taken(50)), (T("now", 12000 + ms + 1), None), reduction("1")]
        # nothing for another skill or event
        for other in item.ignored:
            out += worn(idle) + [fire("cast", other), reduction("1")]
        for event in ("kill", "kill_elite", "taken", "hit_generator", "hit_spender", "hit"):
            out += worn(idle) + [fire(event, item.cast), reduction("1")]
        # not worn, and worn with no stored roll
        out += [(T("clear"), None), (T("now", 1000), None), fire("cast", item.quiet_skill), reduction("1")]
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", owner, 0), None), fire("cast", item.quiet_skill), reduction("1")]
        # a value stored but the item in the bag: no power
        out += [(T("clear"), None), (T("now", 1000), None), (T("value", owner, "", STAT, 50), None), fire("cast", item.quiet_skill), reduction("1")]
        # a second source's window multiplies with this one (the driver adds another item with the same shape at 20%)
        out += worn(idle) + [(T("wears", item.other_name, 0), None), (T("value", item.other_name, "", STAT, 20), None),
                             fire("cast", item.quiet_skill), reduction("%g" % ((1 - idle / 100) * 0.8))]
        # the range rolls once per item (a Primal stores the top)
        key = "power::%s=" % STAT
        out += [(T("roll", owner, 1), key + "%g;" % high), (T("roll", owner, 0), key + "%g;" % ((low + high) / 2))]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = self.run_binary([str(binary), str(work / "cases.txt")])
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        item = self.ITEM
        want, got = self.drive(MATH.read_text(encoding="utf-8"), item.mine() + item.other, "real")
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        item = self.ITEM
        other = item.other
        real = MATH.read_text(encoding="utf-8")
        rows = item.mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows + other, "want")
        row_mutants = {name: [r[:13] + (cell,) + r[14:] for r in rows] for name, cell in item.skill_mutants.items()}
        row_mutants.update({
            "the_window_longer": [r[:8] + (8.0,) + r[9:] for r in rows],
            "the_window_shorter": [r[:8] + (item.shorter,) + r[9:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_event": [r[:12] + ("hit_generator",) + r[13:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_dealt_pct",) + r[5:] for r in rows],
            "no_condition": [r[:7] + ("",) + r[8:] for r in rows],
            "no_rows": [],
        })
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + other, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double ReductionFactor("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "added_not_multiplied": ("factor *= 1.0 - pct / 100.0;", "factor -= pct / 100.0;"),
            "percent_read_as_a_fraction": ("factor *= 1.0 - pct / 100.0;", "factor *= 1.0 - pct;"),
            "increase_not_reduction": ("factor *= 1.0 - pct / 100.0;", "factor *= 1.0 + pct / 100.0;"),
            "the_stat_ignored": ('"damage_reduction_pct"', '"damage_taken_pct"'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows + other, name)
                self.assertNotEqual(want, got, name + " survived")
        header = real.replace("(situation.now - last->second) <= static_cast<std::uint32_t>(row.arg * 1000.0)",
                              "(situation.now - last->second) < static_cast<std::uint32_t>(row.arg * 1000.0)")
        with self.subTest(mutant="the_window_exclusive"):
            self.assertNotEqual(real, header, "the_window_exclusive did not apply")
            _, got = self.drive(header, rows + other, "the_window_exclusive")
            self.assertNotEqual(want, got, "the_window_exclusive survived")

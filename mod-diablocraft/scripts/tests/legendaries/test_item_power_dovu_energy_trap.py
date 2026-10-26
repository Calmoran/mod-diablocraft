"""Legendary rest, bead diablocraft-dxqyr: Dovu Energy Trap (amulet, any class).

  "Increases duration of Stun effects by [20 - 25]%."
  * the numbers (the roll range 20-25 percent) are read from d3planner (item_neck.js, leg_dovuenergytrap); the table (data/legendary_powers.csv) holds ONE
    `player` row for the pool item Unique_Amulet_107_x1: `stun_duration_pct`, 20-25, which the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the
    stat as an item's own percent and refuses a set level, a condition, an event and a zero;
  * the production rules (src/combat/dc_item_power_math.h: PlayerFactor over the stat, StunMilliseconds, with Owned / RollPowers) are compiled and driven
    with the generated row: 1 + N/100 of the item's stored roll while the item is worn and rolled, 1 with none, two sources multiply; a Primal stores 25;
    a stun's milliseconds are stretched by the factor, a permanent (-1) duration is not;
  * mutants of the rules and of the row fail the same driver;
  * source-text guards: ItemPowers::StunFactor reads the stat; the StunDurations hook (OnCalcMaxDuration) stretches a player's MOD_STUN aura of mechanic
    Stun and leaves Ice Blast 15878 (the freeze hold) alone; every site that sets a stun's seconds itself multiplies them by StunFactor (Ground Stomp,
    Thunderstrike, the Wizard's Stun, Zei's stun, Scorpion Sting, Wall of Light). The in-game steps are in docs/test-diablocraft-dxqyr.md.
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import generate_legendary_powers as generator
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import barbarian_source  # noqa: E402
import wizard_source  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_dovu_energy_trap/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Amulet_107_x1"
STAT = "stun_duration_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731
# Every place that sets a stun's seconds itself after AddAura (so the hook's stretch is overwritten), and the multiplied call it must make.


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(low, high) percent as the planner words them."""
    text = (REPO / "reference/d3planner/item_neck.js").read_text(encoding="utf-8")
    start = text.index('id: "leg_dovuenergytrap"')
    item = text[start:text.index("},", start)]
    m = re.search(r'format: "Increases duration of Stun effects by %d%%\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_source_gives_the_range(self):
        self.assertEqual((20.0, 25.0), numbers())

    def test_one_player_row_holds_the_range(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, *BLANK)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("Increases duration of Stun effects by 20–25%", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "20", "value_max": "25", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="dovu-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_stat_is_a_positive_player_stat(self):
        self.assertIn(STAT, generator.PLAYER_STATS)
        self.assertIn(STAT, generator.POSITIVE_PLAYER_STATS)

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
            "a set bonus": ({"pieces": "2", "value_max": "20"}, STAT),
            "a condition": ({"cond": "skills_active", "cond_skills": "Sprint"}, "."),
            "an event": ({"fire_on": "cast", "fire_skills": "Sprint"}, "."),
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
        work = Path(tempfile.mkdtemp(prefix="itemdovu-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = lambda roll: clear + [(T("wears", OWNER), None), (T("value", OWNER, "", STAT, roll), None)]  # noqa: E731
        # not worn: no stretch
        out += clear + [(T("stun"), "1")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("stun"), "1")]
        # worn and rolled: 1 + N/100, at both ends and between
        for roll in (low, 22.5, high):
            out += worn(roll) + [(T("stun"), g(1 + roll / 100))]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, "", STAT, 22), None), (T("stun"), "1")]
        # a second owner's row multiplies the first's
        out += worn(high) + [(T("wears", "Other Trap"), None), (T("value", "Other Trap", "", STAT, 10), None),
                             (T("stun"), g((1 + high / 100) * (1 + 10 / 100)))]
        # a stun's milliseconds: 2000 at the top roll is 2500, rounded; permanent (-1, also under two items' 1.5625) and zero stay; no item, as it was
        out += [(T("ms", 2000, 1 + high / 100), str(round(2000 * (1 + high / 100)))), (T("ms", 1500, 1 + low / 100), str(round(1500 * (1 + low / 100)))),
                (T("ms", 333, 1.225), str(round(333 * 1.225))), (T("ms", -1, 1.25), "-1"), (T("ms", -1, 1.5625), "-1"), (T("ms", 0, 1.25), "0"), (T("ms", 2000, 1), "2000")]
        # the range rolls once per item (a Primal stores the top)
        out += [(T("roll", OWNER, 1), "power::%s=%g;" % (STAT, high)), (T("roll", OWNER, 0), "power::%s=%g;" % (STAT, (low + high) / 2))]
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

    def other(self):
        return [("Other Trap", 0, "player", "", STAT, 10.0, 10.0, *BLANK)]

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + self.other(), "real")
        self.assertGreater(len(want), 14)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        other = self.other()
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_kind_lost": [r[:2] + ("skill",) + r[3:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("shield_potency_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, _ = self.drive(real, rows + other, name + "-want")
                _, got = self.drive(real, mutant_rows + other, name)
                self.assertNotEqual(want, got, name + " survived")
        stretch = real[real.index("inline std::int32_t StunMilliseconds("):]
        stretch = stretch[:stretch.index("\n    }\n") + 7]
        factor = real[real.index("inline double PlayerFactor("):]
        factor = factor[:factor.index("\n    }\n") + 7]
        rules = {
            "not_stretched": (stretch, "std::lround(milliseconds * factor)", "std::lround(milliseconds * 1.0)"),
            "shortened": (stretch, "std::lround(milliseconds * factor)", "std::lround(milliseconds / factor)"),
            "a_permanent_one_stretched": (stretch, "milliseconds > 0 && factor > 0", "factor > 0"),
            "truncated_not_rounded": (stretch, "std::lround(milliseconds * factor)", "(milliseconds * factor)"),
            "sources_added_to_one": (factor, "factor *= 1.0 + pct / 100.0;", "factor = 1.0 + pct / 100.0;"),
            "percent_read_as_a_fraction": (factor, "factor *= 1.0 + pct / 100.0;", "factor *= 1.0 + pct;"),
        }
        for name, (body, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, _ = self.drive(real, rows + other, name + "-want")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows + other, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

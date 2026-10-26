"""Legendary rest, bead diablocraft-f5ff4: Lornelle's Sunstone (ring, any class). Builds N-PLIFE (a player number scaled by the Life the player is missing).

  "Your damage reduction is increased by [0.75-0.95]% for every 1% Life you are missing."
  * the numbers (0.75 to 0.95, step 0.01) are read from d3planner (item_finger.js, leg_lornellessunstone); the table (data/legendary_powers.csv) holds ONE
    `player` row for the pool item P6_Unique_Ring_04: `damage_reduction_pct`, 0.75-0.95, under the new condition `life_missing`, which the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the
    condition on a player or skill row with no cond_arg, skill list or event, and refuses a damage reduction that could reach 100% at no Life;
  * the production rule (src/combat/dc_item_power_math.h: LifeMissing / Counted / Holds, read by ReductionFactor, PlayerFactor, PlayerSum and SkillFactor) is
    compiled and driven with the generated row: 1 - N x M/100 of the item's stored roll, M the percent of Life missing (clamped to 0-100), nothing at full
    Life or with the item unworn or unrolled, a second source multiplies; the same condition scales a player stat and a skill stat, which is the reuse the
    later beads rely on; mutants of the rule and of the row fail the same driver;
  * source-text guards that the Life is read when the number is read (Seen, per hit taken through IncomingFactor, kept nowhere) and that the damage taken
    reads it before the hit lands; mutants of that text fail the same guards. The in-game steps are in docs/test-diablocraft-f5ff4.md.
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
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_lornelles_sunstone/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P6_Unique_Ring_04"
STAT, COND = "damage_reduction_pct", "life_missing"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
# the cells after value_max of the one row: cond, cond_arg, cond_skills, stack_seconds, stack_max, fire_on, fire_skills, chance, icd
AFTER = (COND, 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(low, high, step) as the planner words them."""
    text = (REPO / "reference/d3planner/item_finger.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},", start)]
    m = re.search(r'Your damage reduction is increased by %\.2f%% for every 1%% Life you are missing\.", min: ([\d.]+), max: ([\d.]+), step: ([\d.]+)', item)
    assert m, item
    return float(m[1]), float(m[2]), float(m[3])


class Table(unittest.TestCase):
    def test_the_source_gives_the_range(self):
        self.assertEqual((0.75, 0.95, 0.01), numbers())

    def test_one_player_row_holds_the_range_under_the_condition(self):
        low, high, _ = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, *AFTER)], mine())

    def test_the_row_has_its_source_and_says_how_it_combines(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_finger.js", rows[0]["source"])
        self.assertIn("leg_lornellessunstone", rows[0]["source"])
        self.assertIn("1 - dmgred/100", rows[0]["source"])
        self.assertIn("100 less 100 x current / maximum Life", rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Your damage reduction is increased by 0.75–0.95% for every 1% Life you are missing.", m[1])

    def test_the_condition_is_in_the_contract(self):
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertIn("| `life_missing` (N-PLIFE", text)
        self.assertIn("### Lornelle's Sunstone (`diablocraft-f5ff4`", text)


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "0.75", "value_max": "0.95", "cond": COND,
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="lornelle-gen-", dir=str(SCRATCH)))
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

    def test_the_condition_serves_other_stats_and_skills(self):
        # the later beads: a skill's damage (The Legacy of Raekor's Ancient Spear), a player stat (Rogar's Huge Stone); not a claim that these rows exist
        skill = {"kind": "skill", "skill": "Ancient Spear", "stat": "damage_increase_pct", "value_min": "2", "value_max": "2"}
        player = {"stat": "damage_dealt_pct", "value_min": "2", "value_max": "2"}
        self.assertEqual(1, len([r for r in self.render_with(skill) if r[0] == OWNER]))
        self.assertEqual(1, len([r for r in self.render_with(player) if r[0] == OWNER]))
        self.assertEqual(1, len([r for r in self.render_with({"value_min": "0.99", "value_max": "0.99"}) if r[0] == OWNER]))

    def test_it_refuses_what_the_code_does_not_read(self):
        refused = {
            "a cond_arg": {"cond_arg": "50"},
            "a skill list": {"cond_skills": "Frenzy"},
            "an event": {"fire_on": "hit_generator"},
            "an effect row": {"kind": "effect", "stat": "drain_life", "value_min": "1", "value_max": "1"},
            "a stat row rolled on the item": {"kind": "stat", "stat": "edmg", "value_min": "1", "value_max": "2"},
            "a damage reduction that reaches a hundred at no Life": {"value_min": "1", "value_max": "1"},
            "a range above it": {"value_min": "0.5", "value_max": "1.5"},
            "a damage taken cut that reaches a hundred": {"stat": "damage_taken_pct", "value_min": "-1", "value_max": "-1"},
            "no number": {"value_min": "0", "value_max": "0"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemlornelle-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        low, high, _ = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = lambda roll, life: clear + [(T("wears", OWNER), None), (T("value", OWNER, "", STAT, roll), None), (T("life", life), None)]  # noqa: E731
        reduction = lambda roll, life: g(1 - roll * (100 - life) / 100)  # noqa: E731
        # not worn: nothing, whatever the Life
        out += clear + [(T("life", 10), None), (T("reduction"), "1")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("life", 10), None), (T("reduction"), "1")]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, "", STAT, high), None), (T("life", 10), None), (T("reduction"), "1")]
        # worn and rolled but the Life never read (a reader that does not look at Life): the player counts as at full Life
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, "", STAT, high), None), (T("reduction"), "1")]
        # worn and rolled: 1 - N x M/100 at both ends of the range and between, at every Life from full to none
        for roll in (low, 0.85, high):
            for life in (100, 99, 90, 75, 50, 25, 10, 1, 0):
                out += worn(roll, life) + [(T("reduction"), reduction(roll, life))]
        # a Life past the ends is clamped: over full misses none, under none misses all
        out += worn(high, 130) + [(T("reduction"), "1"), (T("missing"), "0")]
        out += worn(high, -20) + [(T("reduction"), g(1 - high)), (T("missing"), "100")]
        # the missing percent itself, and the same item read again after Life changed (nothing is kept from the earlier read)
        out += worn(0.85, 100) + [(T("reduction"), "1"), (T("life", 40), None), (T("missing"), "60"), (T("reduction"), reduction(0.85, 40)),
                                  (T("life", 100), None), (T("reduction"), "1")]
        # a second source is a multiplier of its own (another item's fixed 20%), at full Life too
        out += worn(high, 50) + [(T("wears", "Other Ring"), None), (T("reduction"), g((1 - high * 50 / 100) * (1 - 20 / 100)))]
        out += worn(high, 100) + [(T("wears", "Other Ring"), None), (T("reduction"), g(1 - 20 / 100))]
        # two worn copies of the condition (another item's ranged row, stored 0.5) multiply
        out += worn(high, 50) + [(T("wears", "Scaled Ring"), None), (T("value", "Scaled Ring", "", STAT, 0.5), None),
                                 (T("reduction"), g((1 - high * 50 / 100) * (1 - 0.5 * 50 / 100)))]
        # reuse: the condition scales any player stat and a skill stat; at full Life the row is absent
        for life, per in ((100, 1.0), (50, 1.25), (0, 1.5)):
            out += clear + [(T("wears", "Dealt Ring"), None), (T("life", life), None), (T("factor", "damage_dealt_pct"), g(per)),
                            (T("sum", "damage_dealt_pct"), g((per - 1) * 100))]
        out += clear + [(T("wears", "Dealt Ring"), None), (T("life", 75), None), (T("skill", "Ancient Spear", "damage_increase_pct"), g(1 + 2 * 25 / 100)),
                        (T("skill", "Leap", "damage_increase_pct"), "1")]
        # the range rolls once per item (a Primal stores the top)
        out += [(T("roll", OWNER, 1), "power::%s=%g;" % (STAT, high)), (T("roll", OWNER, 0), "power::%s=%g;" % (STAT, (low + high) / 2))]
        return out

    def other(self):
        return [("Other Ring", 0, "player", "", STAT, 20.0, 20.0, *BLANK),
                ("Scaled Ring", 0, "player", "", STAT, 0.25, 0.5, *AFTER),
                ("Dealt Ring", 0, "player", "", "damage_dealt_pct", 0.5, 0.5, *AFTER),
                ("Dealt Ring", 0, "skill", "Ancient Spear", "damage_increase_pct", 2.0, 2.0, *AFTER)]

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

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + self.other(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows + self.other(), "want")
        row_mutants = {
            "the_row_lost": [],
            "the_condition_dropped": [r[:7] + BLANK[:1] + r[8:] for r in rows],
            "the_number_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_stat_changed": [r[:4] + ("damage_dealt_pct",) + r[5:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + self.other(), name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "life_taken_for_missing": real.replace("std::clamp(100.0 - situation.lifePct, 0.0, 100.0)", "std::clamp(situation.lifePct, 0.0, 100.0)"),
            "missing_not_clamped": real.replace("std::clamp(100.0 - situation.lifePct, 0.0, 100.0)", "(100.0 - situation.lifePct)"),
            "missing_off_by_a_hundred": real.replace("std::clamp(100.0 - situation.lifePct, 0.0, 100.0)", "std::clamp(1.0 - situation.lifePct / 100.0, 0.0, 1.0)"),
            "counted_once": real.replace('return row.cond == "life_missing" ? LifeMissing(situation) :', 'return row.cond == "life_missing" ? 1.0 :'),
            "counted_not_scaled_by_the_condition": real.replace('return row.cond == "life_missing" ? LifeMissing(situation) :', 'return false ? LifeMissing(situation) :'),
            "the_condition_never_holds": real.replace('if (row.cond == "life_missing")\n            return LifeMissing(situation) > 0;', 'if (row.cond == "life_missing_x")\n            return LifeMissing(situation) > 0;'),
            "holds_at_full_life": real.replace("return LifeMissing(situation) > 0;", "return LifeMissing(situation) < 0;"),
            "number_not_counted": real.replace("out.push_back(number * Counted(row, situation));", "out.push_back(number);"),
            "life_defaults_to_none": real.replace("double lifePct = 100; ", "double lifePct = 0;   "),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows + self.other(), name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

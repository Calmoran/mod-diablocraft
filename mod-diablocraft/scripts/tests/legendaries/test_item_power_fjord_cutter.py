"""Legendary rest, bead diablocraft-5i88h: Fjord Cutter (Barbarian mighty weapon), which builds N-TCTRL (a damage power on a state of the hit's
target).

  "Seismic Slam attacks 50% faster and also deals [100-150]% increased damage against Slowed or Chilled enemies."
  * the text and range are read from d3planner (data.json items P67_Unique_Mighty_1H_006, leg_fjordcutter_p67, min 100 max 150) and the catalogue
    row; the table (data/legendary_powers.csv) holds TWO `skill` rows for the pool item: Seismic Slam `attack_speed_pct` 50 (fixed, in the text) and
    Seismic Slam `damage_increase_pct` 100-150 under the new condition `target_slowed`;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses
    `target_slowed` on anything but a skill's damage_increase_pct, with cond_arg, cond_skills or an event;
  * the production rules (src/combat/dc_item_power_math.h: TargetFactor, Holds' `target_slowed`, SkillFactor) are compiled and driven with the
    generated rows: Seismic Slam is 1 + N/100 against a slowed target with the item's stored roll, 1 against one that is not, only Seismic Slam,
    only while worn; the skill multiplier with no target state never counts the target row (it counts once), and the attack speed is 1.5 always;
  * mutants of the rules and of the rows fail the same driver, and mutants of the two readers fail the source guards on them: ComputeHit
    (dc_combat.cpp) multiplies the hit's legendary term by ItemPowers::TargetFactor with the hit's target, and ItemPowers::TargetFactor
    (dc_item_powers.cpp) marks the target slowed by its strongest slow below 0 (a Chill is a slow aura here). The C++ is compile-checked by
    syntax_check.sh and the in-game steps are in docs/test-diablocraft-5i88h.md.
"""
import csv
import json
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
HARNESS = MODULE / "tests/item_power_fjord_cutter/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P67_Unique_Mighty_1H_006"
SKILL = "Seismic Slam"
DMG = "damage_increase_pct"
SPEED = "attack_speed_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def planner():
    """(text, min, max) of the pool item's power in d3planner's data.json."""
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


def speed_in_text():
    return float(re.search(r"attacks (\d+)%% faster", planner()[0])[1])


class Table(unittest.TestCase):
    def test_the_sources_say_50_faster_and_100_to_150_against_slowed_or_chilled(self):
        text, low, high = planner()
        self.assertEqual("Seismic Slam attacks 50%% faster and also deals %d%% increased damage against Slowed or Chilled enemies.", text)
        self.assertEqual((100.0, 150.0), (low, high))
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Seismic Slam attacks 50% faster and also deals [100-150]% increased damage against Slowed or Chilled enemies.",
                         catalogue[0]["power_text"])
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])

    def test_two_rows_name_seismic_slam(self):
        _, low, high = planner()
        speed = speed_in_text()
        self.assertEqual(sorted([(OWNER, 0, "skill", SKILL, SPEED, speed, speed, *BLANK),
                                 (OWNER, 0, "skill", SKILL, DMG, low, high, "target_slowed", *BLANK[1:])]), sorted(mine()))


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": DMG, "value_min": "100", "value_max": "150", "cond": "target_slowed",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="fjord-gen-", dir=str(SCRATCH)))
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

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        why = "target_slowed is a skill row's damage_increase_pct"
        refused = {
            "another stat": ({"stat": "attack_speed_pct", "value_min": "50", "value_max": "50"}, why),
            "a player row": ({"kind": "player", "skill": "", "stat": "damage_dealt_pct"}, why),
            "cond_skills": ({"cond_skills": SKILL}, why),
            "a cond_arg": ({"cond_arg": "3"}, "takes no cond_arg"),
            "an event": ({"fire_on": "hit", "fire_skills": SKILL}, why),
            "an unknown target state": ({"cond": "target_frozen"}, "cond is one of"),
        }
        for name, (edit, reason) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, reason):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    OTHER = ("Other Axe", 0, "skill", SKILL, DMG, 1.0, 200.0, "target_slowed", *BLANK[1:])   # a ranged row: the driver sets its stored roll
    PLAIN = ("Plain Axe", 0, "skill", SKILL, DMG, 40.0, 40.0, *BLANK)                     # SkillFactor's row, not the target's
    ODD = ("Odd Axe", 0, "skill", SKILL, SPEED, 30.0, 30.0, "target_slowed", *BLANK[1:])   # a target row of another stat (the driver's own)

    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemfjord-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        _, low, high = planner()
        speed = speed_in_text()
        out = [(T("row", *r), None) for r in rows + [self.OTHER, self.PLAIN, self.ODD]]
        clear = [(T("clear"), None)]
        both = lambda want: [(T("slowed", 1), None), (T("target", SKILL), want)]  # noqa: E731
        # not worn: nothing, slowed or not, even with the item's roll known
        out += clear + both("1") + [(T("rolled", OWNER, SKILL, DMG, low), None)] + both("1")
        out += [(T("skill", SKILL, SPEED), "1")]
        # worn, each end of the roll: x2 at 100, x2.5 at 150 against a slowed target; x1 against one that is not
        for roll in (low, high):
            out += clear + [(T("wears", OWNER, SKILL, DMG, roll), None)] + both("%.10g" % (1 + roll / 100))
            out += [(T("slowed", 0), None), (T("target", SKILL), "1")]
        # the skill multiplier, read with no target state (ComputeHit's SkillFactor), never counts the target row: it counts once, in TargetFactor
        out += clear + [(T("wears", OWNER, SKILL, DMG, low), None), (T("skill", SKILL, DMG), "1")]
        # the attack speed is on whatever the target, 1.5 for 50% faster
        out += [(T("skill", SKILL, SPEED), "%.10g" % (1 + speed / 100)), (T("slowed", 0), None), (T("skill", SKILL, SPEED), "%.10g" % (1 + speed / 100))]
        # only Seismic Slam
        out += [(T("slowed", 1), None)]
        for other in ("Earthquake", "Seismic Slamx", "seismic slam", ""):
            out += [(T("target", other), "1")]
        # a second source multiplies: x2 x 1.2
        out += [(T("wears", "Other Axe", SKILL, DMG, 20), None), (T("target", SKILL), "%.10g" % ((1 + low / 100) * 1.2))]
        # a plain damage row (SkillFactor's) and a target row of another stat are not the target's damage
        out += clear + [(T("wears", "Plain Axe", SKILL, DMG, 40), None), (T("wears", "Odd Axe", SKILL, SPEED, 30), None)] + both("1")
        # another owner's item alone does not carry this row
        out += clear + [(T("wears", "Some Ring", SKILL, DMG, 120), None)] + both("1")
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

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 15)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(real, rows, "want")
        damage = [r for r in rows if r[4] == DMG]
        speed = [r for r in rows if r[4] == SPEED]
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Earthquake",) + r[4:] for r in damage] + speed,
            "no_condition": [r[:7] + ("",) + r[8:] for r in damage] + speed,
            "no_speed": damage,
            "speed_100": damage + [r[:5] + (100.0, 100.0) + r[7:] for r in speed],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double TargetFactor("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "a_cut_not_a_bonus": ("1.0 + number / 100.0", "1.0 - number / 100.0"),
            "adds_the_sources": ("factor *= 1.0 + number / 100.0;", "factor += number / 100.0;"),
            "percent_as_a_fraction": ("1.0 + number / 100.0", "1.0 + number"),
            "any_condition": ('row.cond.rfind("target_", 0) == 0', "true"),
            "any_stat": ('row.stat == "damage_increase_pct"', "true"),
            "skill_ignored": ("NamesSkill(row.skill, skill)", "true"),
            "state_ignored": ("Owned(row, counts, situation, number) && Holds(row, situation)", "Owned(row, counts, situation, number)"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "slowed_always": real.replace("return (situation.targetControl & TargetSlowed) != 0;", "return true;"),
            "slowed_never": real.replace("return (situation.targetControl & TargetSlowed) != 0;", "return false;"),
            "the_bottom_not_the_roll": real.replace("number = found->value;", "number = row.min;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

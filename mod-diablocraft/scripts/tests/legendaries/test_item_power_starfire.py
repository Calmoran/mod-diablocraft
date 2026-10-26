"""Legendary rest, bead diablocraft-mcrtc: Starfire (Wizard wand), "Lightning damage is increased by [10-15]% for every 10 yards you are from
the target up to a maximum of 40 yards."

  * the item's text is read out of reference/d3planner/data.json (the catalogue's source for a rolled power: format, min, max) and the table
    (data/legendary_powers.csv) must hold exactly its numbers: three `element` rows on lightning, the rolled `damage_per_distance_pct`
    [10, 15] and the two fixed numbers the text words, `distance_step_yards` 10 and `distance_cap_yards` 40; the owner is a Wizard wand
    that drops; the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rule (src/combat/dc_item_power_math.h: DistanceFactor, with Owned / Holds / RollPowers) is compiled and driven with the
    generated rows: the factor is a multiplier of its own, 1 + roll x whole steps / 100 with the distance cut at the cap, on lightning only,
    only while the wand is worn and only at a stored roll; the range rolls once, a Primal takes 15, the step and cap do not roll;
  * mutants of the rule and of the rows fail the same driver;
  * the generator refuses a distance row it cannot stand behind;
  * source-text guards that the hit multiplies the factor into its legendary term with the target and the shell's element, and that the
    distance is read the way Power Hungry reads it (player->GetDistance(target)); the C++ is compile-checked by syntax_check.sh and the
    in-game steps are in docs/test-diablocraft-mcrtc.md.
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
import wizard_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_starfire/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
STARFIRE = "P42_Unique_Wand_003_x1"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
TEXT = re.compile(r"Lightning damage is increased by %d%% for every (\d+) yards you are from the target up to a maximum of (\d+) yards\.")


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def planner_custom():
    """Starfire's power in the planner's data.json: (format text, min, max); asserts it is the one item of that id."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("id") == STARFIRE:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8")))
    assert len(found) == 1, found
    custom = found[0]["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


def numbers():
    """(roll low, roll high, yards per step, cap in yards) from the item's text."""
    text, low, high = planner_custom()
    m = TEXT.fullmatch(text)
    assert m, text
    return low, high, float(m[1]), float(m[2])


def generated_rows(text=None):
    text = GENERATED.read_text(encoding="utf-8") if text is None else text
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(text)]


def mine():
    return [r for r in generated_rows() if r[0] == STARFIRE]


BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)


class Table(unittest.TestCase):
    def test_the_text_is_the_catalogues(self):
        low, high, step, cap = numbers()
        self.assertEqual((10.0, 15.0, 10.0, 40.0), (low, high, step, cap))
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            row = next(r for r in csv.DictReader(stream) if r["d3_id"] == STARFIRE)
        self.assertIn("Lightning damage is increased by [10-15]% for every 10 yards", row["power_text"])

    def test_three_lightning_rows_with_the_texts_numbers(self):
        low, high, step, cap = numbers()
        want = {
            (STARFIRE, 0, "element", "lightning", "damage_per_distance_pct", low, high, *BLANK),
            (STARFIRE, 0, "element", "lightning", "distance_step_yards", step, step, *BLANK),
            (STARFIRE, 0, "element", "lightning", "distance_cap_yards", cap, cap, *BLANK),
        }
        self.assertEqual(want, set(mine()))
        self.assertEqual(3, len(mine()))

    def test_the_tooltip_shows_the_rolled_range(self):
        low, high, _, _ = numbers()
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % STARFIRE,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertIn("%g–%g%%" % (low, high), m[1])

    def test_the_earlier_table_stays_as_written(self):
        self.assertNotIn(STARFIRE, (MODULE / "data/sql/db-world/updates/legendary_powers_0012_table.sql").read_text(encoding="utf-8"))

    def test_the_newest_table_is_not_yet_shipped(self):
        applied = (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertNotIn(GENERATED.name, applied)


class Generator(unittest.TestCase):
    BASE = {"owner": STARFIRE, "pieces": "", "kind": "element", "skill": "lightning", "stat": "damage_per_distance_pct", "value_min": "10",
            "value_max": "15", "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "",
            "fire_skills": "", "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        """The generator run on a copy of the module whose sheet is the real one with Starfire's rows replaced by `edits` (dicts over BASE)."""
        work = Path(tempfile.mkdtemp(prefix="starfire-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != STARFIRE]
            fields = list(sheet[0].keys())
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fields)
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def sibling(self, stat, value):
        return {"stat": stat, "value_min": str(value), "value_max": str(value)}

    def test_the_real_three_rows_pass(self):
        rows = self.render_with({}, self.sibling("distance_step_yards", 10), self.sibling("distance_cap_yards", 40))
        self.assertEqual(3, len([r for r in rows if r[0] == STARFIRE]))

    def test_it_refuses_what_it_cannot_carry(self):
        step, cap = self.sibling("distance_step_yards", 10), self.sibling("distance_cap_yards", 40)
        refused = {
            "no step": [{}, cap],
            "no cap": [{}, step],
            "step alone": [step, cap],
            "a step that rolls": [{}, {**step, "value_max": "12"}, cap],
            "a cap below the step": [{}, step, self.sibling("distance_cap_yards", 5)],
            "a condition": [{"cond": "triggered", "cond_arg": "3", "fire_on": "kill"}, step, cap],
            "a set bonus": [{"pieces": "2"}, step, cap],
            "a negative number": [{"value_min": "-15", "value_max": "-10"}, step, cap],
            "not an element": [{"skill": "lightningx"}, step, cap],
        }
        for name, edits in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(*edits)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itempower-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output)]: the expectations come from the item's text, not from the code."""
        low, high, step, cap = numbers()
        out = [("\t".join(["row", *map(str, (r[0], r[1], r[2], r[3], r[4], "%g" % r[5], "%g" % r[6], r[7], "%g" % r[8], r[9], "%g" % r[10],
                                              r[11], r[12], r[13], "%g" % r[14], "%g" % r[15]))]), None) for r in rows]
        out.append(("wears\t%s" % STARFIRE, None))
        for roll in (low, (low + high) / 2, high):
            out.append(("value\t%s\tlightning\tdamage_per_distance_pct\t%g" % (STARFIRE, roll), None))
            for yards in (0, 5, 9.99, 10, 19.99, 20, 29.99, 30, 39.99, 40, 41, 60, 100):
                steps = int(min(yards, cap) // step)
                out.append(("distance\tlightning\t%g" % yards, "%g" % (1 + roll * steps / 100)))
            # a hit of any other element is not touched
            for element in ("fire", "cold", "arcane", "physical"):
                out.append(("distance\t%s\t40" % element, "1"))
            out.append(("clear", None))
            out.append(("wears\t%s" % STARFIRE, None))
            # (the stored roll is added again at the next pass; clear drops the situation)
        # a second wand beside it (another owner of the same rows): each source is a multiplier of its own, so the factors multiply
        other = [("row\tOther Wand\t0\telement\tlightning\t%s\t%g\t%g\t\t0\t\t0\t0\t\t\t100\t0" % (stat, v, v)) for stat, v in
                 (("damage_per_distance_pct", 10), ("distance_step_yards", 10), ("distance_cap_yards", 40))]
        out += [(line, None) for line in other]
        out += [("wears\tOther Wand", None), ("value\tOther Wand\tlightning\tdamage_per_distance_pct\t10", None),
                ("value\t%s\tlightning\tdamage_per_distance_pct\t%g" % (STARFIRE, high), None)]
        for yards in (5, 25, 45):
            steps = int(min(yards, cap) // step)
            out.append(("distance\tlightning\t%g" % yards, "%g" % ((1 + high * steps / 100) * (1 + 10 * steps / 100))))
        # no stored roll for the ranged row: no value, no power
        out.append(("clear", None))
        out.append(("wears\t%s" % STARFIRE, None))
        out.append(("distance\tlightning\t40", "1"))
        # not worn: nothing, whatever the stored roll
        out.append(("clear", None))
        out.append(("value\t%s\tlightning\tdamage_per_distance_pct\t%g" % (STARFIRE, high), None))
        out.append(("distance\tlightning\t40", "1"))
        # the range is rolled once, its middle here; a Primal Ancient takes the top; the step and cap are fixed and never roll
        out.append(("roll\t%s\t0" % STARFIRE, "power:lightning:damage_per_distance_pct=%g;" % ((low + high) / 2)))
        out.append(("roll\t%s\t1" % STARFIRE, "power:lightning:damage_per_distance_pct=%g;" % high))
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return run.stdout.split("\n")[:-1], [w for _, w in cases if w is not None]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(3, len(rows))

        body = real[real.index("inline double DistanceFactor"):]
        body = body[:body.index("\n    }\n") + 7]
        mutants = {
            # the rows
            "row_cap_lost": (real, [r for r in rows if r[4] != "distance_cap_yards"]),
            "row_step_lost": (real, [r for r in rows if r[4] != "distance_step_yards"]),
            "row_cap_doubled": (real, [r[:5] + (80.0, 80.0) + r[7:] if r[4] == "distance_cap_yards" else r for r in rows]),
            "row_step_five": (real, [r[:5] + (5.0, 5.0) + r[7:] if r[4] == "distance_step_yards" else r for r in rows]),
            "row_range_halved": (real, [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == "damage_per_distance_pct" else r for r in rows]),
            "row_element_fire": (real, [r[:3] + ("fire",) + r[4:] for r in rows]),
        }
        rules = {
            "whole_steps_rounded_up": ("std::floor(", "std::ceil("),
            "no_cap": ("std::min(distance, cap)", "distance"),
            "cap_is_step": ("std::min(distance, cap)", "std::min(distance, step)"),
            "not_a_multiplier": ("factor *= 1.0 + number * steps / 100.0;", "factor += number * steps / 100.0;"),
            "steps_ignored": ("number * steps / 100.0", "number / 100.0"),
            "element_ignored": ("row.skill != element ||", ""),
            "worn_ignored": ("!Owned(row, counts, situation, number) ||", ""),
            "wrong_stat": ('row.stat != "damage_per_distance_pct"', 'row.stat != "distance_cap_yards"'),
        }
        for name, (old, new) in rules.items():
            self.assertIn(old, body, name + " does not apply")
            mutants[name] = (real.replace(body, body.replace(old, new, 1)), rows)
        for name, (header, mutant_rows) in mutants.items():
            with self.subTest(mutant=name):
                got, want = self.drive(header, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

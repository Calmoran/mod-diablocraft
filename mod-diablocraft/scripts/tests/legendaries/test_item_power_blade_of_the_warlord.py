"""Legendary rest, bead diablocraft-nsbac: Blade of the Warlord (Barbarian one-hand Mighty Weapon).

  "Bash consumes up to 40 Fury to deal up to [400 - 500]% increased damage."
  * the numbers (40 Fury, the roll range 400-500) are read from d3planner (item_onehand.js, leg_bladeofthewarlord) and from the legendaries sheet
    (barbarian_legendaries.csv), the skill from barbarian_skills.csv, apart from the table; the table (data/legendary_powers.csv) holds TWO `skill`
    rows for the pool item P4_Unique_Mighty_1H_005, both on Bash: `damage_by_resource_spent_pct` 400-500 (rolled once per item) and
    `resource_spent_cap` 40 (fixed, the "40 Fury" of the text);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    accepts the two stats on Bash and refuses them alone, a ranged cap, another skill, a condition and a set bonus;
  * the production rules (src/combat/dc_item_power_math.h: ResourceSpend, ResourceSpentFactor, with Owned / Holds / RollPowers) are compiled and
    driven with the generated rows: Bash takes what the player has up to the cap (continuous), and the hit is multiplied by 1 + N/100 x
    taken/cap ("up to N%": the whole N at the cap, none at no Fury); only Bash, only while the item is worn and rolled; a Primal stores 500;
  * mutants of the rules and of the rows fail the same driver (a sum in place of a product, with two weapons worn);
  * source-text guards that the primary provider takes the Fury after the hit is computed and before the cast's Fury grant, that the hit
    multiplies the factor into its legendary term with the base skill name, and that the Pulverize shockwave carries the cast's amount; the C++
    is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-nsbac.md.
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

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_blade_of_the_warlord/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P4_Unique_Mighty_1H_005"
SKILL = "Bash"
DAMAGE = "damage_by_resource_spent_pct"
CAP = "resource_spent_cap"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
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
    """(cap, low, high) as the planner words them, checked against the legendaries sheet."""
    text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Bash consumes up to (\d+) Fury to deal up to %d%% increased damage\.", min: (\d+), max: (\d+)', item)
    assert m, item
    sheet = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Blade of the Warlord")
    assert sheet == "Bash consumes up to %s Fury to deal up to [%s - %s]%% increased damage." % (m[1], m[2], m[3]), sheet
    return float(m[1]), float(m[2]), float(m[3])


class Table(unittest.TestCase):
    def test_the_sources_name_bash_fury_and_the_numbers(self):
        self.assertEqual((40.0, 400.0, 500.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])
        fury = [r for r in read_csv("data/d3/class_resources.csv") if r["d3_class"] == "Barbarian" and r["role"] == "primary"]
        self.assertEqual(["fury"], [r["resource_key"] for r in fury])

    def test_two_rows_name_bash(self):
        cap, low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, DAMAGE, low, high, *BLANK), (OWNER, 0, "skill", SKILL, CAP, cap, cap, *BLANK)], mine())

    def test_bash_is_a_shell_and_a_primary(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertRegex(shells, r'\{\d+, "%s", "", ' % SKILL)
        self.assertRegex((SRC / "classes/barbarian/dc_barbarian_primary_data.h").read_text(encoding="utf-8"), r'\{\d+, "%s", \d+, \d+, Behavior::plain' % SKILL)

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("up to 40 Fury", m[1])
        self.assertIn("400–500%", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": DAMAGE, "value_min": "400", "value_max": "500", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}
    CAP = {**BASE, "stat": CAP, "value_min": "40", "value_max": "40"}

    def render_with(self, *edits, keep_cap=True):
        """The generator run on a copy of the module whose sheet is the real one with the owner's rows replaced by `edits` (dicts over BASE;
        a dict with "cap": True is over the cap row)."""
        work = Path(tempfile.mkdtemp(prefix="blade-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            rows = [{**self.BASE, **e} for e in edits]
            if keep_cap:
                rows.append(dict(self.CAP))
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + rows)
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        own = "needs 0 < value_min <= value_max"
        refused = {
            "a zero number": ([{"value_min": "0", "value_max": "0"}], {}, own),
            "a negative number": ([{"value_min": "-500", "value_max": "-400"}], {}, own),
            "not a skill": ([{"skill": "Bashx"}], {}, "is not a skill"),
            "a skill that takes nothing": ([{"skill": "Cleave"}], {}, "simply on, for one of"),
            "a condition": ([{"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Bash"}], {}, "simply on, for one of"),
            "a set bonus": ([{"pieces": "2"}], {}, "not a set"),
            "no cap beside it": ([{}], {"keep_cap": False}, "go together"),
        }
        for name, (edits, kw, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(*edits, **kw)

    def test_it_refuses_a_cap_alone_and_a_ranged_cap(self):
        with self.assertRaisesRegex(ValueError, "go together"):
            work_rows = self.render_with({"stat": CAP, "value_min": "40", "value_max": "40"}, keep_cap=False)
        with self.assertRaisesRegex(ValueError, "one fixed number"):
            self.render_with({}, {"stat": CAP, "value_min": "30", "value_max": "40"}, keep_cap=False)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemblade-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        cap, low, high = numbers()
        # two decoy owners of fixed rows: one on Cleave with its cap, one on Rend with no cap at all (the generator refuses it; the rule must still not divide by it)
        decoys = [("Decoy", 0, "skill", "Cleave", DAMAGE, 100.0, 100.0, *BLANK), ("Decoy", 0, "skill", "Cleave", CAP, 40.0, 40.0, *BLANK),
                  ("Capless", 0, "skill", "Rend", DAMAGE, 100.0, 100.0, *BLANK)]
        out = [(T("row", *r), None) for r in list(rows) + decoys]
        clear = [(T("clear"), None)]
        factor = lambda roll, taken: g(1 + roll / 100 * taken / cap)  # noqa: E731
        worn = lambda roll: clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, DAMAGE, roll), None)]  # noqa: E731
        # not worn: nothing taken, no bonus, whatever the player has
        out += clear + [(T("spend", SKILL, 100), "0"), (T("spent", SKILL, 40), "1")]
        # worn, no roll stored yet: no value, no power, so nothing is taken for nothing
        out += clear + [(T("wears", OWNER), None), (T("spend", SKILL, 100), "0"), (T("spent", SKILL, 40), "1")]
        # worn and rolled: Bash takes what the player has up to the cap, continuous
        for roll in (low, 450, high):
            out += worn(roll)
            for have in (-5, 0, 1, 6, 12.5, 39.5, 40, 40.5, 55, 100):
                out += [(T("spend", SKILL, have), g(max(0, min(have, cap))))]
            # "up to N%": none at nothing taken, the whole N at the cap, in proportion between, and no more than N past it
            for taken in (0, 1, 10, 12.5, 20, 33.3, 39.9, 40):
                out += [(T("spent", SKILL, taken), factor(roll, taken))]
            out += [(T("spent", SKILL, 55), factor(roll, cap)), (T("spent", SKILL, -5), "1")]
        out += worn(high) + [(T("spent", SKILL, 0), "1"), (T("spent", SKILL, cap), g(1 + high / 100))]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, DAMAGE, 450), None), (T("spend", SKILL, 100), "0"), (T("spent", SKILL, 40), "1")]
        # only Bash: no other skill, a name that merely starts or contains it, nothing for the empty name
        out += worn(high)
        for other in ("Cleave", "Frenzy", "Rend", "Whirlwind", "Hammer of the Ancients", "Magic Missile", "Bas", "Bash Rune", "Bashes", ""):
            out += [(T("spend", other, 100), "0"), (T("spent", other, 40), "1")]
        # the rule reads the skill it is asked for: another worn owner's Cleave rows act on Cleave only, and a damage row with no cap is no bonus and takes nothing
        out += worn(high) + [(T("wears", "Decoy"), None), (T("wears", "Capless"), None), (T("spend", "Cleave", 20), "20"), (T("spent", "Cleave", 20), g(1 + 100 / 100 * 20 / 40)),
                             (T("spend", SKILL, 20), "20"), (T("spent", SKILL, 20), factor(high, 20)), (T("spend", "Rend", 20), "0"), (T("spent", "Rend", 20), "1"),
                             (T("spend", "Frenzy", 20), "0")]
        # the range rolls once per item under the skill's name (a Primal stores the top); the fixed cap stores nothing
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, DAMAGE, high)),
                (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, DAMAGE, (low + high) / 2))]
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
        self.assertGreater(len(want), 80)
        self.assertEqual(want, got)

    def two_sources(self, header_text, name):
        """The factor for two weapons that each own the rows, worn together, with 20 of 40 taken."""
        cap, low, high = numbers()
        other = [("Other Weapon", 0, "skill", SKILL, DAMAGE, 100.0, 100.0, *BLANK), ("Other Weapon", 0, "skill", SKILL, CAP, 40.0, 40.0, *BLANK)]
        cases = [T("row", *r) for r in mine() + other] + [T("wears", OWNER), T("value", OWNER, SKILL, DAMAGE, high), T("wears", "Other Weapon"),
                                                          T("value", "Other Weapon", SKILL, DAMAGE, 100), T("spent", SKILL, 20)]
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_two_sources_multiply(self):
        """A second owner of the stat is a multiplier of its own: the factors multiply, and a sum fails."""
        cap, low, high = numbers()
        real = MATH.read_text(encoding="utf-8")
        self.assertEqual([g((1 + high / 100 * 20 / 40) * (1 + 100 / 100 * 20 / 40))], self.two_sources(real, "two"))
        old = "factor *= 1.0 + pct / 100.0 * fraction;"
        self.assertIn(old, real)
        self.assertNotEqual(self.two_sources(real, "two"), self.two_sources(real.replace(old, "factor += pct / 100.0 * fraction;"), "sum"))

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Rend",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == DAMAGE else r for r in rows],
            "the_cap_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == CAP else r for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] if r[4] == DAMAGE else r for r in rows],
            "no_cap_row": [r for r in rows if r[4] != CAP],
            "no_damage_row": [r for r in rows if r[4] != DAMAGE],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("// The Fury a skill takes (Blade of the Warlord"):]
        body = body[:body.index("// The multiplier of a `player` `_pct` stat")]
        rules = {
            "spend_ignores_the_cap": ("std::min(have, cap)", "have"),
            "spend_takes_the_cap_always": ("std::min(have, cap)", "cap"),
            "spend_may_go_negative": ("std::max(0.0, std::min(have, cap))", "std::min(have, cap)"),
            "spend_without_a_roll": ('ActiveValues(rows, counts, "skill", skill, "damage_by_resource_spent_pct", situation).empty()', "false"),
            "spend_the_wrong_stat": ('"skill", skill, "resource_spent_cap"', '"skill", skill, "damage_by_resource_spent_pct"'),
            "spend_the_skill_ignored": ('"skill", skill, "resource_spent_cap"', '"skill", "Bash", "resource_spent_cap"'),
            "factor_unclamped_high": ("std::clamp(spent / cap, 0.0, 1.0)", "std::max(spent / cap, 0.0)"),
            "factor_unclamped_low": ("std::clamp(spent / cap, 0.0, 1.0)", "std::min(spent / cap, 1.0)"),
            "factor_whole_points_only": ("std::clamp(spent / cap, 0.0, 1.0)", "std::clamp(std::floor(spent) / cap, 0.0, 1.0)"),
            "factor_by_spent_only": ("pct / 100.0 * fraction", "pct / 100.0 * spent"),
            "factor_ignores_the_amount": ("pct / 100.0 * fraction", "pct / 100.0"),
            "factor_percent_unscaled": ("pct / 100.0 * fraction", "pct * fraction"),
            "factor_the_stat_dropped": ('"skill", skill, "damage_by_resource_spent_pct", situation))\n            factor', '"skill", skill, "damage_increase_pct", situation))\n            factor'),
            "factor_the_skill_ignored": ('"skill", skill, "damage_by_resource_spent_pct", situation))\n            factor', '"skill", "Bash", "damage_by_resource_spent_pct", situation))\n            factor'),
            "factor_ignores_a_zero_cap": ("if (cap <= 0.0)", "if (false)"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

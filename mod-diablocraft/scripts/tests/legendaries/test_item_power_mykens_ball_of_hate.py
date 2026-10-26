"""Legendary rest, bead diablocraft-3j0cg: Myken's Ball of Hate (Wizard source), on diablocraft-d00zm's `mayRehit` seam.

  "Electrocute can chain to enemies that have already been hit."
  * the text is read from d3planner (item_offhand.js, leg_mykensballofhate, args 0: no number) and the catalogue row; the table (data/legendary_powers.csv)
    holds ONE `skill` row for Unique_Orb_102_x1: Electrocute, `jump_rehit`, 1 (a flag, nothing to roll);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat
    for Electrocute only, as a 1, and refuses another number, a range, another skill, a condition or event, and a set bonus's row;
  * the production rules (src/combat/dc_item_power_math.h SkillSetTo, src/classes/wizard/dc_wizard_chain.h JumpCount, Next and Walk) are compiled and driven
    with the generated rows as Wizard::Jumps composes them: worn, a fresh enemy comes first, even farther off than one already hit (A B C, not A B A), and a bolt on two enemies jumps back and forth
    (A B A) once none is fresh, with Velvet Camaral too (A B A B A);
    alone it still has nowhere to jump; without the orb each enemy is hit once;
  * mutants of the rules and of the row fail the same driver, and mutants of Wizard::Jumps (src/classes/wizard/dc_wizard_electrocute.cpp) fail the source guards on it.
    The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-3j0cg.md.
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
import harness_env  # noqa: E402
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
MATH = MODULE / "src/combat/dc_item_power_math.h"
CHAIN = MODULE / "src/classes/wizard/dc_wizard_chain.h"
HARNESS = MODULE / "tests/item_power_mykens_ball_of_hate/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Orb_102_x1"
VELVET = "Unique_WizardHat_102_x1"
SKILL = "Electrocute"
STAT = "jump_rehit"
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


def velvet():
    return [r for r in all_rows() if r[0] == VELVET]


def counts():
    """Electrocute's own numbers: the skill's additional enemies and Chain Lightning's most enemies (wizard_skill_values.csv)."""
    values = {r["rune"]: float(r["value"]) for r in read_csv("data/d3/wizard_skill_values.csv")
              if r["skill"] == SKILL and r["token"] == "target_count"}
    return values[""], values["Chain Lightning"]


class Table(unittest.TestCase):
    def test_the_sources_give_the_rule_and_no_number(self):
        text = (REPO / "reference/d3planner/item_offhand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('custom: {id: "leg_mykensballofhate", name: "Electrocute Can Chain Back", format: "Electrocute can chain to enemies that have '
                      'already been hit.", args: 0}', item)
        self.assertIn('preset: ["mainstat", "chc"]', item)   # no Electrocute damage affix on the item
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Electrocute can chain to enemies that have already been hit.", catalogue[0]["power_text"])

    def test_one_row_lets_electrocute_rehit(self):
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, 1.0, 1.0, *BLANK)], mine())

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_offhand.js", rows[0]["source"])
        self.assertIn("leg_mykensballofhate", rows[0]["source"])
        self.assertIn("mayRehit", rows[0]["note"])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "1", "value_max": "1", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="mykens-gen-", dir=str(SCRATCH)))
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

    def test_it_refuses_what_it_cannot_carry(self):
        why = "jump_rehit is an item's value 1"
        refused = {
            "two": ({"value_min": "2", "value_max": "2"}, why),
            "a range": ({"value_min": "1", "value_max": "2"}, why),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "another skill": ({"skill": "Arcane Orb"}, why),
            "two skills": ({"skill": "Electrocute;Arcane Orb"}, why),
            "not a skill": ({"skill": "Electrocutex"}, "is not a skill"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, why),
            "an event": ({"fire_on": "cast", "fire_skills": SKILL}, "an event fires"),
            "a set bonus": ({"pieces": "2"}, "not a set|" + why),
        }
        for name, (edit, reason) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, reason):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, chain_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text, "wizard/dc_wizard_chain.h": chain_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemmykens-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        skill, chain = counts()
        out = [(T("row", *r), None) for r in rows + velvet()]
        clear = [(T("clear"), None)]
        two, three, alone, far = "0,1", "0,1,2", "0", "0,20"
        # B at 5 yd and C at 18 yd: from B the enemy already hit (A, 5 yd) is nearer than the fresh one (C, 13 yd); C is out of A's reach
        stray = "0,5,18"
        # without the orb: each enemy once (d00zm)
        out += clear + [(T("walk", "", skill, two), "0 1"), (T("walk", "", skill, three), "0 1 2"), (T("walk", "", skill, alone), "0")]
        # worn: a fresh enemy first, however far in reach; back to one already hit only when none is fresh, never to the one the bolt is on;
        # nowhere to go alone or out of reach
        out += clear + [(T("wears", OWNER), None)]
        out += [(T("walk", "", skill, two), "0 1 0"), (T("walk", "Surge of Power", skill, two), "0 1 0"), (T("walk", "", skill, stray), "0 1 2"), (T("walk", "", skill, alone), "0"),
                (T("walk", "", skill, far), "0"), (T("walk", "Chain Lightning", chain, two), "0 1 0 1 0 1 0 1 0 1"),
                (T("walk", "Lightning Blast", skill, two), "0"), (T("walk", "Arc Lightning", skill, two), "0")]
        # with Velvet Camaral too: the doubled jumps bounce as well
        out += [(T("wears", VELVET), None), (T("walk", "", skill, two), "0 1 0 1 0"), (T("walk", "", skill, stray), "0 1 2 1 0")]
        # the hat alone does not rehit; another owner's orb does nothing
        out += clear + [(T("wears", VELVET), None), (T("walk", "", skill, two), "0 1")]
        out += clear + [(T("wears", "Other Orb"), None), (T("walk", "", skill, two), "0 1")]
        return out

    def drive(self, math_text, chain_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(math_text, chain_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), CHAIN.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 10)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        math, chain = MATH.read_text(encoding="utf-8"), CHAIN.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(math, chain, rows, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Arcane Orb",) + r[4:] for r in rows],
            "the_wrong_stat": [r[:4] + ("jump_count_factor",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(math, chain, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = math[math.index("inline double SkillSetTo("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "never_raises": ("if (value > base)", "if (value < base)"),
            "reads_the_player_rows": ('"skill", skill, stat', '"player", skill, stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(math.replace(body, body.replace(old, new, 1)), chain, rows, name)
                self.assertNotEqual(want, got, name + " survived")
        chain_mutants = {
            "rehit_ignored": ("(mayRehit ? again : -1)", "-1"),
            "stays_on_the_enemy": ("if (c.current)", "if (false)"),
            "always_rehits": ("(mayRehit ? again : -1)", "again"),
            "nearest_of_all": ("c.hit ? again : fresh", "mayRehit ? fresh : (c.hit ? again : fresh)"),
            "rehit_before_fresh": ("fresh >= 0 ? fresh :", "mayRehit && again >= 0 ? again : fresh >= 0 ? fresh :"),
        }
        for name, (old, new) in chain_mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, chain.count(old), name + " does not apply once")
                _, got = self.drive(math, chain.replace(old, new), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

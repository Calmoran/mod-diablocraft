"""Legendary rest, bead diablocraft-9l8ka: Velvet Camaral (Wizard hat), N-EXTRA on diablocraft-d00zm's Electrocute jumps.

  "Double the number of enemies your Electrocute jumps to."
  * the text is read from d3planner (item_head.js, leg_velvetcamaral, args 0: the 2 is "Double") and the catalogue row; the table (data/legendary_powers.csv)
    holds ONE `skill` row for Unique_WizardHat_102_x1: Electrocute, `jump_count_factor`, 2 (fixed, nothing to roll);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat
    for Electrocute, refuses a number under 2 or not whole, a range, another skill, a condition or event, and a set bonus's row;
  * the production rules (src/combat/dc_item_power_math.h SkillSetTo, src/classes/wizard/dc_wizard_chain.h JumpCount and Walk) are compiled and driven with
    the generated row as Wizard::Jumps composes them: worn, the skill, Surge of Power and Forked Lightning jump to 4 (a pack of 5 is all hit), Chain
    Lightning to 18 (19 enemies); Lightning Blast and Arc Lightning still never jump; without the hat it is d00zm's 2 and 9;
  * mutants of the rules and of the row fail the same driver, and mutants of Wizard::Jumps (src/classes/wizard/dc_wizard_electrocute.cpp) fail the source guards on it.
    The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-9l8ka.md.
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
HARNESS = MODULE / "tests/item_power_velvet_camaral/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_WizardHat_102_x1"
SKILL = "Electrocute"
STAT = "jump_count_factor"
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


def counts():
    """Electrocute's own numbers: the skill's additional enemies and Chain Lightning's most enemies (wizard_skill_values.csv)."""
    values = {r["rune"]: float(r["value"]) for r in read_csv("data/d3/wizard_skill_values.csv")
              if r["skill"] == SKILL and r["token"] == "target_count"}
    return values[""], values["Chain Lightning"]


class Table(unittest.TestCase):
    def test_the_sources_say_double_and_give_no_other_number(self):
        text = (REPO / "reference/d3planner/item_head.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('custom: {id: "leg_velvetcamaral", name: "Double Electrocute Jumps", format: "Double the number of enemies your Electrocute '
                      'jumps to.", args: 0}', item)
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Double the number of enemies your Electrocute jumps to.", catalogue[0]["power_text"])

    def test_one_row_doubles_electrocute(self):
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, 2.0, 2.0, *BLANK)], mine())

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_head.js", rows[0]["source"])
        self.assertIn("leg_velvetcamaral", rows[0]["source"])
        self.assertIn("Chain Lightning 9 -> 18", rows[0]["note"])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "2", "value_max": "2", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="velvet-gen-", dir=str(SCRATCH)))
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

    def test_a_whole_value_of_three_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({"value_min": "3", "value_max": "3"}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        why = "jump_count_factor is an item's one whole number of 2 or more"
        refused = {
            "one": ({"value_min": "1", "value_max": "1"}, why),
            "a part number": ({"value_min": "2.5", "value_max": "2.5"}, why),
            "a range": ({"value_min": "2", "value_max": "3"}, why),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "another skill": ({"skill": "Chain Lightning"}, "is not a skill|" + why),
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
        work = Path(tempfile.mkdtemp(prefix="itemvelvet-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        skill, chain = counts()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # without the hat: d00zm's jumps
        out += clear + [(T("jumps", "", skill), "2"), (T("jumps", "Chain Lightning", chain), "9"), (T("reach", "", skill, 8), "3")]
        # worn: doubled, every rune that jumps; the beam and the cone still do not
        out += clear + [(T("wears", OWNER), None)]
        out += [(T("jumps", "", skill), "4"), (T("jumps", "Surge of Power", skill), "4"), (T("jumps", "Forked Lightning", skill), "4"),
                (T("jumps", "Chain Lightning", chain), "18"), (T("jumps", "Lightning Blast", skill), "0"), (T("jumps", "Arc Lightning", skill), "0")]
        # a pack of 5 close together is all hit; Chain Lightning reaches 19 of 25; a pack of 3 is still 3
        out += [(T("reach", "", skill, 5), "5"), (T("reach", "", skill, 8), "5"), (T("reach", "Chain Lightning", chain, 25), "19"),
                (T("reach", "", skill, 3), "3")]
        # another owner's hat does nothing
        out += clear + [(T("wears", "Other Hat"), None), (T("jumps", "", skill), "2")]
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
            "tripled": [r[:5] + (3.0, 3.0) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
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
            "chain_lightning_counts_jumps": ('rune == "Chain Lightning" ? targetCount - 1 : targetCount', "targetCount"),
            "the_beam_jumps": ('rune == "Lightning Blast" || ', ""),
        }
        for name, (old, new) in chain_mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, chain.count(old), name + " does not apply once")
                _, got = self.drive(math, chain.replace(old, new), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

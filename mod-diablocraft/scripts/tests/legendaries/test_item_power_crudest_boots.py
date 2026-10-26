"""Legendary rest, bead diablocraft-x1tg0: The Crudest Boots (Monk boots, list row 247, K1, N-EXTRA).

  "Mystic Ally summons two Mystic Allies that fight by your side. They deal [150-200]% increased damage and are able to attack with their
  active forms longer."
  * the text and numbers are read from the catalogue's P71 row and d3planner's older entry (item_feet.js, leg_thecrudestboots: only the first
    sentence); the table (data/legendary_powers.csv) holds TWO `skill` rows for the pool item P71_Unique_Boots_010, both on Mystic Ally:
    `summon_count_add` 1 (fixed, the new stat of this bead: one more ally than the skill's one) and `damage_increase_pct` 150-200 (rolled
    once per item; the standing S-DMG multiplier of ComputeHit). "Active forms longer" has no number in any source: the designer's card q-1014-20 (c)
    answers it as a percent, the monk tunable mystic_ally_boots_form_duration_pct = 50 (no row);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    refuses a bad `summon_count_add` row;
  * the production rules are compiled and driven with the generated rows: SkillSetTo (dc_item_power_math.h) gives the extra only while the
    item is worn, AllyCount (dc_monk_mystic_ally.h) then keeps two allies instead of one, and FormSeconds makes an active form a percent
    longer, by its own seconds, only with the Boots worn and a percent above 0;
  * the Monk's file reads them (source guards with their own mutants): the extra is asked before the file's lock, on the poll, and the slots
    follow the count; every Active acts on every living ally; Enduring Ally's heal is paid once per press by each living ally (two
    allies heal twice); the forms' seconds go through FormSeconds;
  * mutants of the rows, of the rules and of the header fail. The C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-x1tg0.md.
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
ALLY_H = SRC / "classes/monk/dc_monk_mystic_ally.h"
HARNESS = MODULE / "tests/item_power_crudest_boots/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P71_Unique_Boots_010"
SKILL = "Mystic Ally"
STAT = "summon_count_add"
TUNABLE = "mystic_ally_boots_form_duration_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
TEXT = ("Mystic Ally summons two Mystic Allies that fight by your side. They deal [150-200]% increased damage and are able to attack with "
        "their active forms longer.")


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_two_allies_and_150_to_200(self):
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual(TEXT, catalogue[0]["power_text"])
        planner = (REPO / "reference/d3planner/item_feet.js").read_text(encoding="utf-8")
        self.assertIn('format: "Mystic Ally summons two Mystic Allies that fight by your side."', planner)

    def test_two_rows_on_mystic_ally(self):
        self.assertEqual(sorted([(OWNER, 0, "skill", SKILL, STAT, 1.0, 1.0, *BLANK), (OWNER, 0, "skill", SKILL, "damage_increase_pct", 150.0, 200.0, *BLANK)]),
                         sorted(mine()))

    def test_active_forms_longer_is_alexs_percent_tunable_and_no_row(self):
        self.assertEqual({STAT, "damage_increase_pct"}, {r["stat"] for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER})
        row = next(r for r in read_csv("data/tunables/monk.csv") if r["name"] == TUNABLE)
        self.assertEqual(("", "50", "percent"), (row["d3_value"], row["value"], row["unit"]))
        self.assertIn("q-1014-20", row["notes"])
        self.assertIn(f"('monk', '{TUNABLE}',", (MODULE / "data/sql/db-world/updates/tunables_0014.sql").read_text(encoding="utf-8"))


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "1", "value_max": "1", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="crudest-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if not (r["owner"] == OWNER and r["stat"] == STAT)]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a range": {"value_min": "1", "value_max": "2"},
            "a part ally": {"value_min": "1.5", "value_max": "1.5"},
            "zero": {"value_min": "0", "value_max": "0"},
            "another skill": {"skill": "Fists of Thunder"},
            "two skills": {"skill": "Mystic Ally;Fists of Thunder"},
            "a condition": {"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL},
            "an event": {"fire_on": "cast", "fire_skills": SKILL},
            "a set bonus": {"pieces": "2"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, ally_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text, "classes/monk/dc_monk_mystic_ally.h": ally_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemcrudest-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: one ally, no extra, nothing lengthened whatever the percent says
        out += clear + [(T("setto", SKILL, STAT, 0), "0"), (T("allies"), "1"), (T("form", 3, 50), "3"), (T("form", 6, 0), "6")]
        # worn: two allies; each form is a percent longer, by its own seconds, only by a percent above 0
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 0), "1"), (T("allies"), "2"), (T("form", 3, 50), "4.5"),
                        (T("form", 6, 50), "9"), (T("form", 6, 100), "12"), (T("form", 3, 0), "3"), (T("form", 3, -10), "3")]
        # whole allies only
        out += [(T("count", 0), "1"), (T("count", 0.5), "1"), (T("count", 1), "2"), (T("count", 2.0), "3"), (T("count", -1), "1")]
        # only Mystic Ally's `summon_count_add`
        for other in ("Fists of Thunder", "Mystic Allyx", "mystic ally", ""):
            out += [(T("setto", other, STAT, 0), "0")]
        for other in ("damage_increase_pct", "max_stacks_add", "summon_count", ""):
            out += [(T("setto", SKILL, other, 0), "0")]
        # another owner's item does nothing
        out += clear + [(T("wears", "Other Boots"), None), (T("setto", SKILL, STAT, 0), "0"), (T("allies"), "1"), (T("form", 3, 50), "3")]
        return out

    def drive(self, math_text, ally_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(math_text, ally_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), ALLY_H.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 15)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real, ally = MATH.read_text(encoding="utf-8"), ALLY_H.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(real, ally, rows, "want")
        count_row = [r for r in rows if r[4] == STAT]
        others = [r for r in rows if r[4] != STAT]
        row_mutants = {
            "the_skill_lost": others + [r[:3] + ("Fists of Thunder",) + r[4:] for r in count_row],
            "two_more": others + [r[:5] + (2.0, 2.0) + r[7:] for r in count_row],
            "the_wrong_stat": others + [r[:4] + ("max_stacks_add",) + r[5:] for r in count_row],
            "no_count_row": others,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, ally, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double SkillSetTo("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "never_raises": ("if (value > base)", "if (value < base)"),
            "reads_the_player_rows": ('"skill", skill, stat', '"player", skill, stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), ally, rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {}
        count = ally[ally.index("inline unsigned AllyCount("):]
        count = count[:count.index("\n    }\n") + 7]
        form = ally[ally.index("inline double FormSeconds("):]
        form = form[:form.index("\n    }\n") + 7]
        for name, (old, new) in {"the_extra_ignored": (count, count.replace("unsigned(extra + 1e-9)", "0u")),
                                 "a_second_ally_for_everyone": (count, count.replace("return 1 +", "return 2 +")),
                                 "forms_always_longer": (form, form.replace("power && pct > 0", "pct > 0")),
                                 "a_negative_percent_shortens": (form, form.replace("power && pct > 0 ? seconds * (1 + pct / 100) : seconds", "power ? seconds * (1 + pct / 100) : seconds")),
                                 "seconds_added_not_percent": (form, form.replace("seconds * (1 + pct / 100)", "seconds + pct")),
                                 "only_the_extra_part": (form, form.replace("seconds * (1 + pct / 100)", "seconds * (pct / 100)")),
                                 "forms_replaced": (form, form.replace("seconds * (1 + pct / 100)", "pct"))}.items():
            self.assertIn(old, ally, name + " does not apply")
            self.assertNotEqual(old, new, name + " is the same text")
            header_mutants[name] = (real, ally.replace(old, new))
        for name, (math_text, ally_text) in header_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(math_text, ally_text, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

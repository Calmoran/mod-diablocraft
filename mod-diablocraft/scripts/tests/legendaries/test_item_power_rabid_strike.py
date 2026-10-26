"""Legendary rest, bead diablocraft-6d1jb: Rabid Strike (Monk fist weapon), K4: a skill cast again by code.

  "Spirit spenders that teleport you while Epiphany is active are also mimicked on a nearby target with [350-450]% increased damage for free."
  * the text and range are read from d3planner (data.json, leg_rabidstrike_p71, min 350 max 450) and the catalogue row; the "nearby" is the item's
    power file (Power/P43_ItemPassive_Unique_Ring_003.pow SF_0 'Target Search Radius' 15), the tunable monk.rabid_strike_search_radius_yards;
  * the table holds ONE `skill` row for P71_Unique_Fist_003: Epiphany, `mimic_damage_pct`, 350-450 (rolled once per item); the generated SQL and the
    migration are what the generator renders, the migration the newest full table; the generator refuses another skill, a non-positive number, an
    inverted range, a condition, an event and a set bonus's row;
  * the production rules are compiled and driven with the generated row: SkillSetTo (src/combat/dc_item_power_math.h) gives the worn item's roll to
    the dash, and Epiphany's Mimics / MimicTarget / MimicFactor (src/classes/monk/dc_monk_epiphany.h) decide that a Spirit spender's dash is copied,
    on which enemy (the nearest other, or the dash's own target alone) and at 1 + N/100;
  * mutants of the rules and the row fail the same driver, and mutants of the wiring fail the source guards: Epiphany::Dash (after its teleport)
    copies through Monk::Mimic under Combat::CopyFactor and puts it back; Monk::Mimic is Exploding Palm's palm or the skill's own hit (no dash, so no
    copy of a copy); ComputeHit's legendary term multiplies by CopyFactor; Exploding Palm's run takes it into its ticks. The C++ is compile-checked
    by syntax_check.sh and the in-game steps are in docs/test-diablocraft-6d1jb.md.
"""
import csv
import json
import re
import shutil
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
MATH = MODULE / "src/combat/dc_item_power_math.h"
RULES = MODULE / "src/classes/monk/dc_monk_epiphany.h"
EPIPHANY = MODULE / "src/classes/monk/dc_monk_epiphany.cpp"
HARNESS = MODULE / "tests/item_power_rabid_strike/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P71_Unique_Fist_003"
SKILL = "Epiphany"
STAT = "mimic_damage_pct"
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


class Table(unittest.TestCase):
    def test_the_sources_give_the_text_and_the_range(self):
        items = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"]
        item = next(i for i in (items if isinstance(items, list) else items.values()) if isinstance(i, dict) and i.get("id") == OWNER)
        custom = item["required"]["custom"]
        self.assertEqual(("leg_rabidstrike_p71", 350, 450), (custom["id"], custom["min"], custom["max"]))
        self.assertEqual("Spirit spenders that teleport you while Epiphany is active are also mimicked on a nearby target with %d%% increased "
                         "damage for free.", custom["format"])
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertIn("[350-450]% increased damage for free", catalogue[0]["power_text"])

    def test_one_row_on_epiphany_rolled_once(self):
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, 350.0, 450.0, *BLANK)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("mimicked on a nearby target with 350", m[1])

    def test_nearby_is_the_power_files_search_radius(self):
        row = next(r for r in read_csv("data/tunables/monk.csv") if r["name"] == "rabid_strike_search_radius_yards")
        self.assertEqual(("15", "", "yards"), (row["d3_value"], row["value"], row["unit"]))
        self.assertIn("P43_ItemPassive_Unique_Ring_003.pow SF_0 'Target Search Radius' = 15", row["notes"])

    def test_the_spirit_spenders_epiphany_dashes(self):
        # Epiphany's dash list (dc_monk_epiphany.cpp Dashing) holds two skills that cost Spirit: the copy's skills.
        text = EPIPHANY.read_text(encoding="utf-8")
        dashing = re.findall(r'"([^"]+)"', text[text.index("Dashing = {"):text.index("};", text.index("Dashing = {"))])
        cost = {r["skill"]: r["value"] for r in read_csv("data/d3/monk_skill_values.csv") if r["token"] == "cost_resource" and not r["rune"]}
        self.assertEqual(["Lashing Tail Kick", "Exploding Palm"], [s for s in dashing if float(cost.get(s) or 0) > 0])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "350", "value_max": "450", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="rabid-gen-", dir=str(SCRATCH)))
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
        why = "mimic_damage_pct is an item's percent above 0"
        refused = {
            "another skill": ({"skill": "Lashing Tail Kick"}, why),
            "two skills": ({"skill": "Epiphany;Lashing Tail Kick"}, why),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min|" + why),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, why),
            "an event": ({"fire_on": "cast", "fire_skills": SKILL}, "an event fires|" + why),
            "a set bonus": ({"pieces": "2"}, "not a set|" + why),
        }
        for name, (edit, reason) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, reason):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, rules_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text, "classes/monk/dc_monk_epiphany.h": rules_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemrabid-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: no copy
        out += clear + [(T("copy", 50), "0")]
        # worn with its roll: a spender's dash is copied at 1 + N/100; a skill that costs nothing is not
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, 400), None), (T("copy", 50), "5"), (T("copy", 40), "5"),
                        (T("copy", 0), "0")]
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, 350), None), (T("copy", 50), "4.5")]
        # another item's roll does nothing
        out += clear + [(T("wears", "Other Fist"), None), (T("value", "Other Fist", SKILL, STAT, 400), None), (T("copy", 50), "0")]
        # the copy's enemy: the nearest other, the dash's own target alone, none when there is nobody
        out += [(T("pick", -1), "-1"), (T("pick", 0, 5), "0"), (T("pick", 0, 5, 8, 3), "2"), (T("pick", 1, 9, 2, 4), "2"),
                (T("pick", -1, 7, 3), "1"), (T("pick", 2, 6, 6, 1), "0")]
        return out

    def drive(self, math_text, rules_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(math_text, rules_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), RULES.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 10)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        math = MATH.read_text(encoding="utf-8")
        rules = RULES.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(math, rules, rows, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Lashing Tail Kick",) + r[4:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(math, rules, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        rule_mutants = {
            "cost_ignored": ("return pct > 0 && cost > 0;", "return pct > 0;"),
            "item_ignored": ("return pct > 0 && cost > 0;", "return cost > 0;"),
            "farthest": ("distances[i] < distances[std::size_t(best)]", "distances[i] > distances[std::size_t(best)]"),
            "the_dash_target_preferred": ("if (int(i) != primary && (best < 0", "if ((best < 0"),
            "no_fallback": ("return best >= 0 ? best : primary;", "return best;"),
            "factor_without_the_skill": ("return 1.0 + pct / 100.0;", "return pct / 100.0;"),
            "factor_whole_percent": ("return 1.0 + pct / 100.0;", "return 1.0 + pct;"),
        }
        for name, (old, new) in rule_mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, rules.count(old), name + " does not apply once")
                _, got = self.drive(math, rules.replace(old, new), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

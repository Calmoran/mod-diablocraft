"""Legendary rest, bead diablocraft-ohipa: Dark Mage's Shade (Wizard hat), which builds N-LIFEEV (an event when Life falls below a level) and N-CAST (a skill cast by code).

  "Automatically cast Diamond Skin when you fall below 35% Life. This effect may occur once every [15-20] seconds."
  * the numbers (35 percent, the roll range 15-20) are read from d3planner (item_head.js, leg_darkmagesshade) and from the catalogue row and the
    item's tooltip, the skill from wizard_skills.csv, apart from the table; the table (data/legendary_powers.csv) holds TWO rows for the pool item
    Unique_WizardHat_001_x1: a `player` row `life_threshold_pct` 35 (fixed, the item's own level as Berserker Rage's resource_threshold_pct is) and an
    `effect` row `cast_skill` on Diamond Skin, fired on the new event `life_below`, whose number is the internal cooldown in seconds (15-20, rolled once per item);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts
    the event, the effect and the stat, and refuses them half built (no threshold row, no cast_skill row, a ranged threshold, a chance, a
    cooldown column, a condition, an unknown skill, another event);
  * the production rules (src/combat/dc_item_power_math.h: Fire on `life_below` with LifeFell and the item's threshold, Owned / WornValues / RollPowers)
    are compiled and driven with the generated rows: it fires on the hit that takes Life from the level or above to under it ("fall below"), not
    on a hit that stays above, not on one that finds Life already under, not on the level itself; once per rolled number of seconds (the end
    exact); only for the worn, rolled item; a Primal stores 20;
  * mutants of the rules and of the rows fail the same driver;
  * source-text guards that the hit's damage reaches the event before it is dealt and only when it does not kill, that the effect casts the skill by code
    through the one narrow function in dc_combat.h, and that function casts the bar's own spell (the chosen rune) as the core's triggered cast; the C++
    is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-ohipa.md.
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
HARNESS = MODULE / "tests/item_power_dark_mages_shade/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_WizardHat_001_x1"
SKILL = "Diamond Skin"
THRESHOLD = "life_threshold_pct"
CAST = "cast_skill"
EVENT = "life_below"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
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
    """(level, low, high) as the planner words them."""
    text = (REPO / "reference/d3planner/item_head.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Automatically cast Diamond Skin when you fall below (\d+)%% Life\. This effect may occur once every %d seconds\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2]), float(m[3])


def read_csv_path(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def fixed(stat, low, high, kind="player", skill="", fire_on=""):
    return (OWNER, 0, kind, skill, stat, low, high, "", 0.0, "", 0.0, 0, fire_on, "", 100.0, 0.0)


class Table(unittest.TestCase):
    def test_the_sources_name_diamond_skin_and_the_numbers(self):
        level, low, high = numbers()
        self.assertEqual((35.0, 15.0, 20.0), (level, low, high))
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")])
        catalogue = [r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertIn("below 35% Life", catalogue[0]["power_text"])
        self.assertIn("[15-20] seconds", catalogue[0]["power_text"])

    def test_two_rows_name_the_level_and_the_cast(self):
        level, low, high = numbers()
        self.assertEqual([fixed(THRESHOLD, level, level), fixed(CAST, low, high, "effect", SKILL, EVENT)], mine())

    def test_diamond_skin_is_a_wizard_shell(self):
        self.assertRegex((SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"), r'\{\d+, "%s", "' % SKILL)

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("below 35% Life", m[1])
        self.assertIn("15–20 seconds", m[1])


class Generator(unittest.TestCase):
    LEVEL = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": THRESHOLD, "value_min": "35", "value_max": "35", "cond": "",
             "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
             "icd_seconds": "", "source": "s", "note": "n"}
    CAST = {**LEVEL, "kind": "effect", "skill": SKILL, "stat": CAST, "value_min": "15", "value_max": "20", "fire_on": EVENT}

    def render_with(self, level=None, cast=None):
        """The generator run on a copy of the module whose sheet is the real one with the owner's rows replaced (None leaves a row out)."""
        work = Path(tempfile.mkdtemp(prefix="shade-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            rows = ([{**self.LEVEL, **level}] if level is not None else []) + ([{**self.CAST, **cast}] if cast is not None else [])
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + rows)
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len([r for r in self.render_with({}, {}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "no level row": (None, {}, "go together"),
            "no cast row": ({}, None, "go together"),
            "a level above 100": ({"value_min": "101", "value_max": "101"}, {}, "at most 100"),
            "a ranged level": ({"value_min": "30", "value_max": "35"}, {}, "one fixed number"),
            "a level with a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Diamond Skin"}, {}, "simply on"),
            "an unknown skill": ({}, {"skill": "Diamond Skinx"}, "is not a skill"),
            "a cooldown column": ({}, {"icd_seconds": "5"}, "cast_skill"),
            "a chance column": ({}, {"chance_pct": "50"}, "cast_skill"),
            "a condition on the cast": ({}, {"cond": "resource_above"}, "cast_skill"),
            "the cast on another event": ({}, {"fire_on": "taken"}, "cast_skill"),
            "a zero cooldown": ({}, {"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
        }
        for name, (level, cast, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(level, cast)

    def test_another_effect_may_not_fire_on_the_event(self):
        with self.assertRaisesRegex(ValueError, "cast_skill"):
            self.render_with({}, {"stat": "resource_refund", "skill": "", "value_min": "9", "value_max": "12"})


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemshade-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        level, low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = lambda roll: clear + [(T("stored", "power:%s:%s" % (SKILL, CAST), roll), None), (T("wears", OWNER), None)]  # noqa: E731
        did = lambda roll: "%s=%s@%s;" % (CAST, g(roll), SKILL)  # noqa: E731
        fell = lambda before, after: [(T("life", before, after), None)]  # noqa: E731
        # not worn: nothing, whatever fell
        out += clear + fell(100, 10) + [(T("fire", EVENT), "")]
        # a roll stored and the numbers known, but the item in the bag
        out += clear + [(T("stored", "power:%s:%s" % (SKILL, CAST), 17), None), (T("bag", OWNER), None)] + fell(100, 10) + [(T("fire", EVENT), "")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None)] + fell(100, 10) + [(T("fire", EVENT), "")]
        for roll in (low, 17.5, high):
            out += wear(roll)
            # "fall below 35%": from the level or above to under it
            for before, after, fires in ((100, 34, True), (100, 34.9, True), (36, 34, True), (35, 34, True), (35.0001, 34.9999, True), (100, 0, True),
                                         (100, 35, False), (100, 36, False), (36, 35, False), (35, 35, False), (34, 30, False), (20, 10, False),
                                         (34.9, 34.8, False), (0, 0, False), (100, 100, False)):
                out += [(T("clear"), None), (T("stored", "power:%s:%s" % (SKILL, CAST), roll), None), (T("wears", OWNER), None)] + fell(before, after)
                out += [(T("fire", EVENT), did(roll) if fires else "")]
            # the event is its own: another event with the same fall fires nothing
            out += wear(roll) + fell(100, 10) + [(T("fire", "taken"), ""), (T("fire", "hit"), ""), (T("fire", "cast"), "")]
            # once every `roll` seconds: the end exact, a minute later again; a refused one does not restart the wait
            ms = int(roll * 1000)
            out += wear(roll) + fell(100, 10) + [(T("now", 1000), None), (T("fire", EVENT), did(roll)),
                                                    (T("now", 1000 + ms - 1), None), (T("fire", EVENT), ""),
                                                    (T("now", 1000 + ms), None), (T("fire", EVENT), did(roll)),
                                                    (T("now", 1000 + ms + ms - 1), None), (T("fire", EVENT), ""),
                                                    (T("now", 1000 + 2 * ms), None), (T("fire", EVENT), did(roll))]
        # the level is the item's own number: a different stored level (a row at 50) moves the line, none means never
        # a Primal stores the top of the range; the fixed level stores nothing
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, CAST, high)),
                (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, CAST, (low + high) / 2))]
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
        self.assertGreater(len(want), 70)
        self.assertEqual(want, got)

    def test_the_level_is_the_items_own_row(self):
        """A table whose level row says 50 moves the line to 50; with no level row the event never fires."""
        rows = mine()
        moved = [r[:5] + (50.0, 50.0) + r[7:] if r[4] == THRESHOLD else r for r in rows]
        cases = [T("row", *r) for r in moved] + [T("clear"), T("stored", "power:%s:%s" % (SKILL, CAST), 16), T("wears", OWNER), T("life", 60, 49),
                                                 T("fire", EVENT), T("life", 60, 51), T("fire", EVENT)]
        none = [T("row", *r) for r in rows if r[4] != THRESHOLD] + [T("clear"), T("stored", "power:%s:%s" % (SKILL, CAST), 16), T("wears", OWNER),
                                                                    T("life", 100, 1), T("fire", EVENT)]
        work, binary = self.build(MATH.read_text(encoding="utf-8"), "level")
        try:
            outs = []
            for name, lines in (("moved", cases), ("none", none)):
                (work / (name + ".txt")).write_text("\n".join(lines) + "\n")
                run = harness_env.run([str(binary), str(work / (name + ".txt"))], capture_output=True, text=True)
                self.assertEqual(0, run.returncode, run.stderr)
                outs.append(run.stdout.split("\n")[:-1])
        finally:
            shutil.rmtree(work, ignore_errors=True)
        self.assertEqual(["%s=16@%s;" % (CAST, SKILL), ""], outs[0])
        self.assertEqual([""], outs[1])

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Rend",) + r[4:] if r[4] == CAST else r for r in rows],
            "the_level_moved": [r[:5] + (50.0, 50.0) + r[7:] if r[4] == THRESHOLD else r for r in rows],
            "the_cooldown_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == CAST else r for r in rows],
            "the_cooldown_fixed": [r[:5] + (r[5], r[5]) + r[7:] if r[4] == CAST else r for r in rows],
            "the_wrong_event": [r[:12] + ("taken",) + r[13:] if r[4] == CAST else r for r in rows],
            "no_level_row": [r for r in rows if r[4] != THRESHOLD],
            "no_cast_row": [r for r in rows if r[4] != CAST],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("// Dark Mage's Shade. The event"):]
        body = body[:body.index("// Whether a row's condition holds")]
        rules = {
            "fell_includes_the_level": ("after < level", "after <= level"),
            "fell_needs_no_start": ("before >= level && after < level", "after < level"),
            "fell_start_is_above_only": ("before >= level &&", "before > level &&"),
            "fell_reads_the_start_only": ("before >= level && after < level", "before >= level"),
            "level_stat_dropped": ('value.stat == "life_threshold_pct"', 'value.stat == "resource_threshold_pct"'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        fire = real[real.index("inline std::vector<Fired> Fire("):]
        fire = fire[:fire.index("\n    }\n")]
        fire_rules = {
            "no_level_gate": ('row.fireOn == "life_below"', 'row.fireOn == "never"'),
            "level_ignored": ("!LifeThreshold(row.owner, situation, level) || !LifeFell(situation.lifeBeforePct, situation.lifeAfterPct, level)", "false"),
            "cooldown_from_the_column": ('row.stat == "cast_skill" ? (number > 0 ? number : situation.castCooldownSeconds) : row.icdSeconds', "row.icdSeconds"),
            "cooldown_in_milliseconds": ('(number > 0 ? number : situation.castCooldownSeconds)', '(number > 0 ? number / 1000.0 : situation.castCooldownSeconds)'),
            "cooldown_end_exclusive": ("< static_cast<std::uint32_t>(icd * 1000.0)", "<= static_cast<std::uint32_t>(icd * 1000.0)"),
        }
        for name, (old, new) in fire_rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, fire, name + " does not apply")
                want, got = self.drive(real.replace(fire, fire.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

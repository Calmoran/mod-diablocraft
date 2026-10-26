"""Legendary rest, bead diablocraft-a3ycm: The Tormentor (a two-hand staff, list row 65, K3), and the use of N-CHARM it builds.

  "Chance to charm enemies when you hit them."
  * the words are d3planner's (item_twohand.js, Unique_Staff_007_x1: custom leg_thetormentor, no number); the numbers are the power file's, read through decode_pow.py
    (Item_Power_Passive itemPassive_Unique_Staff_007.pow: 0.03, the item's own fraction read as the chance, decisions.md 2026-10-10 (a); SF_0 'Charm Duration' = 10,
    SF_1 'Cooldown Duration' = 1). The table (data/legendary_powers.csv) holds ONE `effect` row for the staff: `charm_seconds` 10 on `hit` of any skill, `chance_pct` 3
    and `icd_seconds` 1. Every number is the file's: built by D3's rule, no tunable, no card;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts `charm_seconds`
    only as an item's one fixed number of seconds above 0, fired on a hit, with no condition or set level;
  * the production rules (src/combat/dc_item_power_math.h: Fire) are compiled and driven with the generated row: a hit of any skill (or none) charms at 3 percent
    scaled by the hit's proc coefficient (a hit that states none never charms), the cooldown of 1 second (the end inclusive) is spent only by a charm that fell on
    the roll, and nothing else, unworn, another owner's or another event fires it; mutants of the row and the rules fail the same driver;
  * source-text guards that the executor charms the enemy the hit struck through the shared charm (CharmEffect::Apply, the 10 seconds the row carries). The C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-a3ycm.md.
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
EFFECTS = SRC / "combat/dc_item_powers_effects.cpp"
HARNESS = MODULE / "tests/item_power_the_tormentor/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Staff_007_x1"
STAT = "charm_seconds"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
SECONDS, CHANCE, COOLDOWN = 10.0, 3.0, 1.0


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_chance_to_charm_enemies_when_you_hit_them(self):
        text = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('format: "Chance to charm enemies when you hit them.", args: 0', item)
        self.assertIn("Chance to charm enemies when you hit them.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda *a: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), *a], capture_output=True, text=True).stdout  # noqa: E731
        power = run("power", "itemPassive_Unique_Staff_007")
        self.assertRegex(power, r"'Charm Duration' = 10\b")
        self.assertRegex(power, r"'Cooldown Duration' = 1\b")
        self.assertIn("itemPassive_Unique_Staff_007.pow: 0.03", run("item", OWNER))

    def test_one_effect_row_on_every_hit(self):
        self.assertEqual([(OWNER, 0, "effect", "", STAT, SECONDS, SECONDS, "", 0.0, "", 0.0, 0, "hit", "", CHANCE, COOLDOWN)], mine())

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0067_table.sql")


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "10", "value_max": "10", "cond": "", "cond_arg": "",
            "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit", "fire_skills": "", "chance_pct": "3", "icd_seconds": "1",
            "source": "s", "note": "n"}

    def render_with(self, edit):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="tormentor-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **edit}])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "on a kill": {"fire_on": "kill"},
            "on a cast": {"fire_on": "cast", "fire_skills": "Frenzy"},
            "a range": {"value_max": "12"},
            "no seconds": {"value_min": "0", "value_max": "0"},
            "negative seconds": {"value_min": "-1", "value_max": "-1"},
            "a set level": {"pieces": "2"},
            "a condition": {"cond": "triggered", "cond_arg": "5"},
            "a stat row": {"kind": "player"},
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
        for other in ("dc_item_proc_math.h", "dc_proc_math.h"):
            files["combat/" + other] = (SRC / "combat" / other).read_text(encoding="utf-8")
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemtormentor-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the power file's numbers, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = clear + [(T("wears", OWNER), None)]
        proc = "%s:%g" % (STAT, SECONDS)
        # worn: a hit of any skill, or of none, charms at 3 percent: the draw falls when it is below the chance
        for skill in ("", "Frenzy", "Whirlwind", "Magic Missile"):
            out += wear + [(T("now", 5000), None), (T("fire", "hit", skill, 1, 2.99), proc)]
            out += wear + [(T("now", 5000), None), (T("fire", "hit", skill, 1, 3), "none")]
        # scaled by the hit's proc coefficient: half of it is 1.5 percent, none is never
        for scale, draw, want in ((0.5, 1.49, proc), (0.5, 1.5, "none"), (0.13, 0.38, proc), (0.13, 0.39, "none"), (0, 0, "none"), (-1, 0, "none"), (0, -1, "none"), (-1, -5, "none")):
            out += wear + [(T("now", 5000), None), (T("fire", "hit", "Frenzy", scale, draw), want)]
        # the cooldown of 1 second, the end inclusive, spent only by a charm that fell on the roll
        out += wear + [(T("now", 5000), None), (T("fire", "hit", "Frenzy", 1, 0), proc)]
        for t, want in ((5000, "none"), (5001, "none"), (5999, "none"), (6000, proc)):
            out += [(T("now", t), None), (T("fire", "hit", "Frenzy", 1, 0), want)]
        out += wear + [(T("now", 5000), None), (T("fire", "hit", "Frenzy", 1, 50), "none"), (T("fire", "hit", "Frenzy", 1, 0), proc)]   # a failed roll starts no wait
        # not on another event, not unworn, not another owner's staff
        out += wear + [(T("now", 5000), None)] + [(T("fire", e, "Frenzy", 1, 0), "none") for e in ("kill", "cast", "taken", "tick", "block", "chest", "hits", "")]
        out += clear + [(T("now", 5000), None), (T("fire", "hit", "Frenzy", 1, 0), "none")]
        out += clear + [(T("wears", "Other Staff"), None), (T("now", 5000), None), (T("fire", "hit", "Frenzy", 1, 0), "none")]
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
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row = rows[0]
        row_mutants = {
            "a_chance_of_four": [row[:14] + (4.0,) + row[15:]],
            "a_cooldown_of_two": [row[:15] + (2.0,)],
            "no_cooldown": [row[:15] + (0.0,)],
            "another_event": [row[:12] + ("kill",) + row[13:]],
            "named_skills_only": [row[:13] + ("Frenzy",) + row[14:]],
            "five_seconds": [row[:5] + (5.0, 5.0) + row[7:]],
            "no_row": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        for name, (old, new) in {
            "the_chance_ignores_the_coefficient": ("roll(row.chancePct * scale)", "roll(row.chancePct)"),
            "no_coefficient_is_certain": ("row.chancePct * scale > 0 && ", ""),
            "the_cooldown_end_is_exclusive": ("(situation.now - last->second) < static_cast<std::uint32_t>(icd * 1000.0)", "(situation.now - last->second) <= static_cast<std::uint32_t>(icd * 1000.0)"),
            "a_failed_roll_starts_the_wait": ("            if (row.chancePct < 100 && !(row.chancePct * scale > 0 && roll(row.chancePct * scale)))\n                continue;\n            situation.fired[key] = situation.now;", "            situation.fired[key] = situation.now;\n            if (row.chancePct < 100 && !(row.chancePct * scale > 0 && roll(row.chancePct * scale)))\n                continue;"),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def charm_failures(effects):
    """What is wrong with the charm branch of the executor in `effects` ([] when it is right)."""
    flat = re.sub(r"\s+", " ", effects)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the shared charm is included", '#include "dc_charm_effect.h"' in flat)
    need("the record the charm picks its first enemy by is the stock charm cap", "constexpr std::uint32_t CharmRecord = 26740;" in flat)
    need("the branch charms the enemy the hit struck for the row's seconds",
         'else if (one.stat == "charm_seconds" && target) CharmEffect::Apply(player, target, CharmRecord, one.value);' in flat)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_charm_branch(self):
        self.assertEqual([], charm_failures(EFFECTS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        real = EFFECTS.read_text(encoding="utf-8")
        mutants = {
            "no_include": ('#include "dc_charm_effect.h"\n', ""),
            "another_record": ("constexpr std::uint32_t CharmRecord = 26740;", "constexpr std::uint32_t CharmRecord = 5782;"),
            "no_target": ('one.stat == "charm_seconds" && target', 'one.stat == "charm_seconds"'),
            "another_stat": ('one.stat == "charm_seconds" && target', 'one.stat == "charm_second" && target'),
            "the_wrong_seconds": ("CharmEffect::Apply(player, target, CharmRecord, one.value);", "CharmEffect::Apply(player, target, CharmRecord, 5.0);"),
            "charms_the_wearer": ("CharmEffect::Apply(player, target, CharmRecord, one.value);", "CharmEffect::Apply(player, player, CharmRecord, one.value);"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], charm_failures(real.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()

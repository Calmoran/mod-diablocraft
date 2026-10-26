"""Legendary rest, bead diablocraft-115jg: Vigilance (Monk polearm), N-CAST (a skill cast by code, Dark Mage's Shade's) on the event `taken`.

  "Getting hit has a chance to automatically cast Inner Sanctuary."
  * the numbers come from D3's power file (docs/research/legendary-pow-data.csv row Vigilance: the item's own number 0.05 read as the chance,
    decisions.md 2026-10-10 a59b3b3e; SF_7 the internal cooldown, 10); the table (data/legendary_powers.csv) holds ONE row for the pool item
    Unique_Polearm_001_x1: an `effect` row `cast_skill` on Inner Sanctuary, fired on `taken` with chance_pct 5, its number the internal cooldown 10;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator takes a
    chance on `taken` alone, and refuses the row half built (no chance, a chance on another event, a cooldown column, a condition, a set level);
  * the production rules (src/combat/dc_item_power_math.h: Fire on `taken`) are compiled and driven with the generated row: being hit asks the roll
    for 5 percent (at proc coefficient 1), casts on a roll that falls, not on one that fails, and a failed roll starts no cooldown; once every 10
    seconds (the end exact); only for the worn item; no other event; the fixed number stores nothing;
  * mutants of the rules and of the row fail the same driver;
  * source-text guards that a monster's hit reaches `taken` at proc coefficient 1 and that the effect casts the skill by code (the cast itself is
    Dark Mage's Shade's, guarded by test_item_power_dark_mages_shade); the in-game steps are in docs/test-diablocraft-115jg.md.
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
HARNESS = MODULE / "tests/item_power_vigilance/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Polearm_001_x1"
SKILL = "Inner Sanctuary"
CAST = "cast_skill"
EVENT = "taken"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def mine():
    return [r for r in ((m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13],
                         m[14], float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))) if r[0] == OWNER]


def numbers():
    """(chance percent, internal cooldown seconds) as D3's power file has them."""
    row = next(r for r in read_csv(REPO / "docs/research/legendary-pow-data.csv") if r["item_or_set"] == "Vigilance")
    icd = re.search(r"SF_7 Internal coolup/down = ([\d.]+)", row["script_formulas"])
    assert row["power_file"] == "ItemPassive_Unique_Polearm_001_x1.pow" and icd, row
    return round(float(row["item_number"]) * 100, 6), float(icd[1])


class Table(unittest.TestCase):
    def test_the_sources_name_the_skill_and_the_numbers(self):
        self.assertEqual((5.0, 10.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv(MODULE / "data/d3/monk_skills.csv")])
        catalogue = [r for r in read_csv(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(["Getting hit has a chance to automatically cast Inner Sanctuary."], [r["power_text"] for r in catalogue])
        planner = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
        self.assertIn('id: "leg_vigilance"', planner)

    def test_one_row_names_the_chance_and_the_cooldown(self):
        chance, icd = numbers()
        self.assertEqual([(OWNER, 0, "effect", SKILL, CAST, icd, icd, "", 0.0, "", 0.0, 0, EVENT, "", chance, 0.0)], mine())


class Generator(unittest.TestCase):
    CAST = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": SKILL, "stat": CAST, "value_min": "10", "value_max": "10", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": EVENT, "fire_skills": "", "chance_pct": "5",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, cast):
        work = Path(tempfile.mkdtemp(prefix="vigilance-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv(MODULE / "data/legendary_powers.csv")
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows([r for r in sheet if r["owner"] != OWNER] + [{**self.CAST, **cast}])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "no chance": ({"chance_pct": ""}, "cast_skill"),
            "a chance above 100": ({"chance_pct": "101"}, "at most 100"),
            "a cooldown column": ({"icd_seconds": "10"}, "cast_skill"),
            "a condition": ({"cond": "enemies_hit_at_most", "cond_arg": "1"}, "cast_skill"),
            "a set level": ({"owner": "Might of the Earth", "pieces": "2"}, "cast_skill"),
            "a chance on land": ({"fire_on": "land", "fire_skills": "Leap", "owner": "Might of the Earth", "pieces": "4", "value_min": "0",
                                  "value_max": "0"}, "cast_skill"),
            "another event": ({"fire_on": "kill"}, "cast_skill"),
            "an unknown skill": ({"skill": "Inner Sanctuaryx"}, "is not a skill"),
            "a zero cooldown": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
        }
        for name, (cast, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(cast)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemvigilance-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and D3's numbers, not from the code."""
        chance, icd = numbers()
        ms = int(icd * 1000)
        did = "%s=%g@%s;" % (CAST, icd, SKILL)
        asked = "%g," % chance
        out = [(T("row", *r), None) for r in rows]
        wear = [(T("clear"), None), (T("wears", OWNER), None)]
        hit = lambda falls, then: [(T("fire", EVENT, falls, 1), then)]  # noqa: E731
        # not worn, or in the bag: nothing asked, nothing cast
        out += [(T("clear"), None)] + hit(1, "|")
        out += [(T("clear"), None), (T("bag", OWNER), None)] + hit(1, "|")
        # worn: being hit asks for the chance; it falls, Inner Sanctuary; it fails, nothing
        out += wear + hit(1, asked + "|" + did)
        out += wear + hit(0, asked + "|")
        # only being hit: no other event asks or casts
        for event in ("hit", "cast", "kill", "life_below", "land", "resource_spent"):
            out += wear + [(T("fire", event, 1, 1), "|")]
        # once every 10 seconds, the end exact; inside it nothing is even asked; a failed roll starts no wait
        out += wear + [(T("now", 1000), None)] + hit(1, asked + "|" + did)
        out += [(T("now", 1000 + ms - 1), None)] + hit(1, "|")
        out += [(T("now", 1000 + ms), None)] + hit(0, asked + "|")
        out += [(T("now", 1000 + ms + 1), None)] + hit(1, asked + "|" + did)
        out += [(T("now", 1000 + 2 * ms), None)] + hit(1, "|")
        out += [(T("now", 1001 + 2 * ms), None)] + hit(1, asked + "|" + did)
        # the item's number is fixed: a roll stores nothing
        out += [(T("roll", OWNER, 1), ""), (T("roll", OWNER, 0), "")]
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
        self.assertEqual(1, len(rows))
        r = rows[0]
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Serenity",) + r[4:]],
            "the_cooldown_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:]],
            "the_cooldown_in_the_column": [r[:5] + (1.0, 1.0) + r[7:15] + (r[5],)],
            "the_chance_doubled": [r[:14] + (r[14] * 2,) + r[15:]],
            "always": [r[:14] + (100.0,) + r[15:]],
            "the_wrong_event": [r[:12] + ("hit",) + r[13:]],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        fire = real[real.index("inline std::vector<Fired> Fire("):]
        fire = fire[:fire.index("\n    }\n")]
        fire_rules = {
            "chance_ignored": ("row.chancePct < 100 && ", "false && "),
            "a_failed_roll_waits": ("            situation.fired[key] = situation.now;\n", ""),
            "cooldown_from_the_column": ('row.stat == "cast_skill" ? (number > 0 ? number : situation.castCooldownSeconds) : row.icdSeconds', "row.icdSeconds"),
            "cooldown_end_exclusive": ("< static_cast<std::uint32_t>(icd * 1000.0)", "<= static_cast<std::uint32_t>(icd * 1000.0)"),
        }
        for name, (old, new) in fire_rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, fire, name + " does not apply")
                mutated = fire.replace(old, new, 1)
                if name == "a_failed_roll_waits":  # the time is recorded before the roll instead of after it
                    mutated = mutated.replace("            if (row.chancePct < 100", "            situation.fired[key] = situation.now;\n"
                                              "            if (row.chancePct < 100", 1)
                want, got = self.drive(real.replace(fire, mutated), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

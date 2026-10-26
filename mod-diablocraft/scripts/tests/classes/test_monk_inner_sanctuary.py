"""diablocraft-yyglx (Monk 2.3.18): Inner Sanctuary and its five runes.

What this proves, and how:

  * **The circle's rules.** tests/monk_inner_sanctuary/harness.cpp compiles the real dc_monk_inner_sanctuary.h and feeds
    it the sheets' own numbers (55% cut, Intervene's 107284 shield, Safe Haven's 35779 a second and 7% of Life per
    Second, 6 s and Sanctified Ground's 8 s, the power file's 0.3 s tick, the 11 yd radius): who stands in it, the cut,
    the shield, the ticks, the heal per tick and the push to the edge. Mutations planted in a scratch copy must each make
    it fail.
  * **The code reads what the sheets state.** Every number dc_monk_inner_sanctuary.cpp reads by name is a row of
    monk_skill_values.csv for the skill (or a rune of it) or of data/tunables/monk.csv; the tick carries the power file's.
  * **The wiring.** Combat::Mitigate multiplies Monk::TakenFactor among its percentage layers and returns through
    Monk::Absorb; dc_monk.cpp hands the cast to the skill's file; the skill's name is in no code outside
    src/classes/monk/.

What it does not prove: anything on a running server. The heal, the immunity, the slow and the push are
docs/test-diablocraft-yyglx.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_inner_sanctuary.py
"""

import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/monk/dc_monk_inner_sanctuary.h"
SOURCE = "src/classes/monk/dc_monk_inner_sanctuary.cpp"
SOURCES = [HEADER, "tests/monk_inner_sanctuary/harness.cpp"]
SKILL = "Inner Sanctuary"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def values():
    return read(D3 / "monk_skill_values.csv")


def value(rune, token, qualifier=""):
    rows = [r for r in values()
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "monk.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def radius():
    rows = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
    assert len(rows) == 1
    return float(rows[0]["radius_yards"])


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_inner_sanctuary/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_reduction_pct"), value("Intervene", "absorb_life"),
               value("Safe Haven", "heal_per_second_life"), value("Safe Haven", "life_per_second_share_pct"),
               value("", "duration_seconds"), value("Sanctified Ground", "duration_seconds"),
               tune("inner_sanctuary_tick_seconds"), radius()]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_circle_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the cut is the percent kept", (HEADER, "1.0 - pct / 100.0", "pct / 100.0")),
            ("the edge is out", (HEADER, "dy * dy <= zone.radius", "dy * dy < zone.radius")),
            ("the end is not asked", (HEADER, "return now < zone.until && map", "return map")),
            ("the instance is not asked", (HEADER, "instance == zone.instance &&", "")),
            ("the shield takes everything", (HEADER, "return damage - taken;", "return 0;")),
            ("a part tick counts", (HEADER, "std::floor(seconds / tickSeconds + 1e-9)", "std::ceil(seconds / tickSeconds)")),
            ("the heal is per second, not per tick", (HEADER, "* std::max(0.0, tickSeconds)", "")),
            ("Life per Second adds whole", (HEADER, "lifePerSecond * sharePct / 100.0", "lifePerSecond")),
            ("the push is the radius", (HEADER, "radius - distance : 0.0", "radius : 0.0")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "duration_seconds", "damage_reduction_pct")],
                         [20, 6, 55])
        self.assertEqual([value("Intervene", t) for t in ("absorb_life", "absorb_duration_seconds", "radius_yards")],
                         [107284, 3, 11])
        self.assertEqual(value("Sanctified Ground", "duration_seconds"), 8)
        self.assertEqual((value("Safe Haven", "heal_per_second_life"), value("Safe Haven", "life_per_second_share_pct")),
                         (35779, 7))
        self.assertEqual(value("Forbidden Palace", "slow_pct"), 80)

    def test_the_tick_is_the_power_files(self):
        self.assertEqual(tune("inner_sanctuary_tick_seconds"), 0.3)
        self.assertIn("X1_Monk_InnerSanctuary.pow SF_6", tunables()["inner_sanctuary_tick_seconds"]["notes"])

    def test_the_circle_is_at_the_monk_with_the_sheets_radius(self):
        rows = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
        self.assertEqual((rows[0]["target_type"], rows[0]["radius_yards"]), ("self_aoe", "11"))
        shells = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'\{\d+, "Inner Sanctuary", "[^"]*", 11\.0\}', shells)), 6)

    def test_every_name_the_code_reads_exists(self):
        text = (MODULE / SOURCE).read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("inner_sanctuary_")})
        tokens = set(re.findall(r'Numbers::Num\((?:spellId|id|zone->spellId), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in values() if r["skill"] == SKILL}
        self.assertTrue(tokens)
        self.assertEqual(tokens - sheet_tokens, set())

    def test_every_rune_has_code(self):
        text = (MODULE / SOURCE).read_text(encoding="utf-8")
        asked = set(re.findall(r'IsRune\((?:spellId|id|zone\.spellId), "([^"]+)"\)', text)) | \
            set(re.findall(r'Covering\(ally, Now\(\), "([^"]+)"\)', text))
        runes = {r["rune_name"] for r in read(D3 / "monk_runes.csv") if r["skill_name"] == SKILL}
        self.assertEqual(asked, runes)


if __name__ == "__main__":
    unittest.main()

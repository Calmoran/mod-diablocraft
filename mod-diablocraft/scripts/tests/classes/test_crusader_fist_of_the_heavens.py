"""Fist of the Heavens and its five runes (src/classes/crusader/dc_crusader_fist_of_the_heavens.h and .cpp, and the zone).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_fist_of_the_heavens/harness.cpp compiles the real
    dc_crusader_fist_of_the_heavens.h and dc_crusader_dot.h with the sheets' own rune names and numbers: each rune name is its
    rune; the 6 bolts leave the explosion evenly round the circle from the way it was aimed; a bolt's lane is its travel long and
    its width wide; Divine Well's zap reaches its 18 yards from the ray and no further; the fissure's burn has the ticks that fit
    its 5 seconds, adding up to 410%. Six mutations planted in a scratch copy (two runes share a name, the bolts all go one way,
    the lane has no width, the lane is unbounded, the zap is measured to the line and not the ray, the burn's ticks are not
    divided) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_fist_of_the_heavens.cpp reads by name is a row of
    crusader_skill_values.csv for Fist of the Heavens (or the rune that states it), the generated value map says whose record
    holds it, and the numbers are the researched ones: 545% for the explosion within 8 yards and 6 bolts of 255% for 30 Wrath,
    Heaven's Tempest 100% a second for 5 seconds over 8 yards, Reverberation slow 80% for 4 seconds, Fissure 410% over 5 seconds
    and 135% for each arc, Divine Well 40% within 18 yards, Retribution 270% for the hit, 435% for the explosion and 6 bolts of
    185%. Every tunable it reads is a row of data/tunables/crusader.csv: the power file's numbers, and the designer's answers for the
    bolts' lane (3 yards, which serves Retribution's fist and Fissure's arcs) and the knockback (5 yards).
  * **The engine's hit is the explosion** (the ground area it resolves): the skill's `explosion` row, Retribution's own 435%, for
    every rune, since the other runes' unqualified damage_pct is the cloud's, the zaps' and the fissure's.

What it does not prove: anything on a running server. The explosion, the bolts, the cloud, the fissures, the zaps and the slow are
docs/test-diablocraft-7t4gv.9.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_fist_of_the_heavens.py
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
HEADER = "src/classes/crusader/dc_crusader_fist_of_the_heavens.h"
DOT = "src/classes/crusader/dc_crusader_dot.h"
SOURCES = [HEADER, DOT, "tests/crusader_fist_of_the_heavens/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_fist_of_the_heavens.cpp"
SKILL = "Fist of the Heavens"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "crusader_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "crusader_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "crusader.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/crusader_fist_of_the_heavens/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "projectile_count"), tune("fist_bolt_travel_yards"), value("Fissure", "dot_duration_seconds"),
               tune("fist_fissure_tick_seconds"), value("Fissure", "damage_pct", "dot"), value("Divine Well", "radius_yards")] + runes() + [tune("fist_bolt_width_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 19, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::DivineWell;", "return Rune::Fissure;")),
            ("the bolts all go one way", (HEADER, "return count ? first + 2 * 3.14159265358979323846 * index / count : first;", "return first;")),
            ("the lane has no width", (HEADER, "return width > 0 && along >= 0 && along <= length && std::fabs(across) <= width / 2;",
                                       "return along >= 0 && along <= length;")),
            ("the lane is unbounded", (HEADER, "return width > 0 && along >= 0 && along <= length && std::fabs(across) <= width / 2;",
                                       "return width > 0 && along >= 0 && std::fabs(across) <= width / 2;")),
            ("the zap is measured to the line", (HEADER, "        if (along < 0)\n            return std::hypot(along, across);\n", "")),
            ("the burn's ticks are not divided", (DOT, "return ticks ? totalPct / ticks : 0.0;", "return ticks ? totalPct : 0.0;")),
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
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["Heaven's Tempest", "Reverberation", "Fissure", "Divine Well", "Retribution"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct", "explosion"), value("", "radius_yards"),
                          value("", "projectile_count"), value("", "damage_pct", "bolt")], [30, 545, 8, 6, 255])
        self.assertEqual([value("Heaven's Tempest", t) for t in ("radius_yards", "duration_seconds", "damage_pct")], [8, 5, 100])
        self.assertEqual((value("Reverberation", "slow_pct"), value("Reverberation", "slow_duration_seconds")), (80, 4))
        self.assertEqual([value("Fissure", "damage_pct", "dot"), value("Fissure", "dot_duration_seconds"), value("Fissure", "damage_pct", "arc")],
                         [410, 5, 135])
        self.assertEqual((value("Divine Well", "radius_yards"), value("Divine Well", "damage_pct")), (18, 40))
        self.assertEqual([value("Retribution", "damage_pct", q) for q in ("hit", "explosion", "bolt")], [270, 435, 185])
        self.assertEqual((value("Retribution", "radius_yards"), value("Retribution", "projectile_count")), (8, 6))

    def test_the_tunables(self):
        rows = tunables()
        for name, number, source in (("fist_bolt_travel_yards", "85", "SF_8"), ("fist_tempest_tick_seconds", "1", "SF_14"),
                                     ("fist_fissure_radius_yards", "8", "SF_31"), ("fist_fissure_tick_seconds", "0.5", "SF_21"),
                                     ("fist_fissure_arc_yards", "6", "SF_32")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])
        # The designer's answers (cards q-1021-14 and -17): the lane is 3 yards wide and Reverberation's knock 5; no placeholder mark is left.
        for name, number, card in (("fist_bolt_width_yards", "3", "q-1021-14"), ("fist_knockback_yards", "5", "q-1021-17")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), ("", number), name)
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)
            self.assertIn(card, rows[name]["notes"], name)

    def test_the_bolt_lane_is_3_yards_for_the_bolts_the_fist_and_the_arcs_and_the_knock_5(self):
        self.assertEqual((tune("fist_bolt_width_yards"), tune("fist_knockback_yards")), (3, 5))
        code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        # One width serves the three: the bolts, Retribution's fist and Fissure's arcs.
        self.assertEqual(code.count('Tune("fist_bolt_width_yards")'), 4)
        self.assertIn('Abilities::Knockback(player, enemy, Tune("fist_knockback_yards"));', code)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("fist_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"projectile_count", "damage_pct", "radius_yards", "duration_seconds", "dot_duration_seconds",
                                  "slow_pct", "slow_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "projectile_count", ""), ("", "damage_pct", "bolt"), ("", "damage_pct", "explosion"),
                                       ("Heaven's Tempest", "radius_yards", ""), ("Heaven's Tempest", "duration_seconds", ""),
                                       ("Heaven's Tempest", "damage_pct", ""), ("Reverberation", "slow_pct", ""),
                                       ("Reverberation", "slow_duration_seconds", ""), ("Fissure", "damage_pct", "dot"),
                                       ("Fissure", "damage_pct", "arc"), ("Fissure", "dot_duration_seconds", ""),
                                       ("Divine Well", "radius_yards", ""), ("Divine Well", "damage_pct", ""),
                                       ("Retribution", "damage_pct", "hit"), ("Retribution", "damage_pct", "explosion"),
                                       ("Retribution", "damage_pct", "bolt"), ("Retribution", "projectile_count", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], "own")
        # The bolts and the explosion reach every other rune by inheritance.
        for rune in ("Heaven's Tempest", "Reverberation", "Fissure", "Divine Well"):
            for token, qualifier in (("projectile_count", ""), ("damage_pct", "bolt"), ("damage_pct", "explosion")):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], "inherited", (rune, token))

    def test_the_engines_hit_is_the_explosion(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('return Numbers::Get(spellId, "damage_pct", "explosion");', text)


if __name__ == "__main__":
    unittest.main()

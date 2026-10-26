"""Shield Bash and its five runes (src/classes/crusader/dc_crusader_shield_bash.h and .cpp, and the Block Chance share).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_shield_bash/harness.cpp compiles the real dc_crusader_shield_bash.h
    and dc_crusader_block_share.h and feeds them the sheets' own rune names and numbers and the power file's reaches: each
    rune name is its rune, only Crumble and Pound are the bash's own hit, 300% of a 30% Block Chance is 90 points on 700,
    the charge stops 4 yards short of the enemy on the line to it, the cone along that line (17 yards, 30 degrees; Pound 8
    and 5), the fragments' wider cone minus the bash's own, and the four arms of the cross. Eight mutations planted in a
    scratch copy (two runes share a name, Shattered Shield replaces the hit, the share is not divided by 100, the charge
    stops at the enemy, the cone has no angle, a fragment is also hit by the bash, the arms are one, a cross of no length has
    arms) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_shield_bash.cpp reads by name is a row of
    crusader_skill_values.csv for Shield Bash (or the rune that states it), the generated value map says whose record holds
    it, and the numbers are the researched ones: 700% plus 300% of the Block Chance, Crumble 875%, Shattered Shield 740% plus
    335%, Shield Cross 155% plus 100%, Pound 1320% plus 500% within 8 yards, One on One 1.5 seconds. Every tunable it reads is
    a row of data/tunables/crusader.csv: the power file's numbers where it states them, and the three it does not (the
    cross's length and width, the knockback) the designer's answers (20 yards, 5 yards, 5 yards).
  * **The skills that need a shield** in the code are the skills whose tooltip in crusader_skills.csv says "Requires Shield".

What it does not prove: anything on a running server. The charge, the cone, the cross and the stun are
docs/test-diablocraft-7t4gv.5.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_shield_bash.py
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
HEADER = "src/classes/crusader/dc_crusader_shield_bash.h"
SHARE = "src/classes/crusader/dc_crusader_block_share.h"
SOURCES = [HEADER, SHARE, "src/combat/dc_damage_buckets.h", "tests/crusader_shield_bash/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_shield_bash.cpp"
SKILL = "Shield Bash"


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
    binary = harness_env.build([MODULE / "tests/crusader_shield_bash/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_pct"), value("", "block_chance_share_pct"), tune("shield_bash_stop_yards"),
               tune("shield_bash_area_yards"), tune("shield_bash_arc_degrees"), value("Pound", "radius_yards"),
               tune("shield_bash_pound_arc_degrees"), tune("shield_bash_fragment_extra_yards"),
               tune("shield_bash_fragment_extra_degrees")] + runes() + [tune("shield_bash_cross_length_yards"),
                                                                        tune("shield_bash_cross_width_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 30, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Pound;", "return Rune::Crumble;")),
            ("Shattered Shield replaces the hit", (HEADER, "return rune == Rune::Crumble || rune == Rune::Pound;",
                                                   "return rune == Rune::Crumble || rune == Rune::Pound || rune == Rune::ShatteredShield;")),
            ("the share is not divided by 100", (SHARE, "return damagePct + sharePct * blockChancePct / 100.0;",
                                                 "return damagePct + sharePct * blockChancePct;")),
            ("the charge stops at the enemy", (HEADER, "double const share = (distance - stop) / distance;",
                                               "double const share = 1.0;")),
            ("the cone has no angle", (HEADER, "return radius > 0 && distance <= radius && angleOff <= arc / 2;",
                                       "return radius > 0 && distance <= radius;")),
            ("a fragment is also hit by the bash", (HEADER, "!InCone(distance, angleOff, radius, arc);", "true;")),
            ("the arms are one", (HEADER, "for (int arm = 0; arm < 4; ++arm)", "for (int arm = 0; arm < 1; ++arm)")),
            ("a cross of no length has arms", (HEADER, "if (length <= 0 || width <= 0)\n            return false;", "")),
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
        self.assertEqual(runes(), ["Crumble", "Shattered Shield", "Shield Cross", "Pound", "One on One"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct"), value("", "block_chance_share_pct")], [30, 700, 300])
        self.assertEqual(value("Crumble", "damage_pct"), 875)
        self.assertEqual((value("Shattered Shield", "damage_pct"), value("Shattered Shield", "block_chance_share_pct")), (740, 335))
        self.assertEqual((value("Shield Cross", "damage_pct"), value("Shield Cross", "block_chance_share_pct")), (155, 100))
        self.assertEqual([value("Pound", t) for t in ("damage_pct", "block_chance_share_pct", "radius_yards")], [1320, 500, 8])
        self.assertEqual(value("One on One", "stun_duration_seconds"), 1.5)

    def test_the_tunables(self):
        rows = tunables()
        for name, number, source in (("shield_bash_stop_yards", "4", "SF_35"), ("shield_bash_area_yards", "17", "SF_1"),
                                     ("shield_bash_arc_degrees", "30", "SF_2"), ("shield_bash_pound_arc_degrees", "5", "SF_31"),
                                     ("shield_bash_fragment_extra_yards", "10", "SF_18"),
                                     ("shield_bash_fragment_extra_degrees", "30", "SF_19")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])
        # The designer's answers (cards q-1021-05, -06 and -07): his column is filled and none of the three is a placeholder any more.
        for name, number, card in (("shield_bash_cross_length_yards", "20", "q-1021-05"), ("shield_bash_cross_width_yards", "5", "q-1021-06"),
                                   ("shield_bash_knockback_yards", "5", "q-1021-07")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), ("", number), name)
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)
            self.assertIn(card, rows[name]["notes"], name)

    def test_the_cross_is_20_yards_long_and_5_wide_and_the_knockback_5_yards(self):
        self.assertEqual((tune("shield_bash_cross_length_yards"), tune("shield_bash_cross_width_yards")), (20, 5))
        self.assertEqual(tune("shield_bash_knockback_yards"), 5)
        code = CODE.read_text(encoding="utf-8")
        self.assertIn('Tune("shield_bash_knockback_yards")', code)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)) | set(re.findall(r'"(shield_bash_[a-z_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("shield_bash_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "block_chance_share_pct", "radius_yards", "stun_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("", "block_chance_share_pct"), ("Crumble", "damage_pct"),
                            ("Shattered Shield", "damage_pct"), ("Shattered Shield", "block_chance_share_pct"),
                            ("Shield Cross", "damage_pct"), ("Shield Cross", "block_chance_share_pct"),
                            ("Pound", "damage_pct"), ("Pound", "block_chance_share_pct"), ("Pound", "radius_yards"),
                            ("One on One", "stun_duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, "")]["origin"], "own")

    def test_the_skills_that_need_a_shield_are_the_sheets(self):
        code = (MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8")
        listed = set(re.findall(r'"([A-Za-z\' ]+)"', re.search(r"NeedShield = \{([^}]*)\}", code)[1]))
        sheet = {r["skill_name"] for r in read(D3 / "crusader_skills.csv") if "Requires Shield" in r["full_tooltip_text"]}
        self.assertEqual(listed, sheet)
        self.assertEqual(sheet, {"Punish", "Shield Bash", "Blessed Shield", "Shield Glare"})


if __name__ == "__main__":
    unittest.main()

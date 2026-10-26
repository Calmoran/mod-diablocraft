"""diablocraft-eg0m7 (Monk 2.3.14): Epiphany and its five runes.

What this proves, and how:

  * **The rules.** tests/monk_epiphany/harness.cpp compiles the real dc_monk_epiphany.h with the sheets' and the
    tunables' numbers: the dash only past 7 yards and up to 100, landing 5 short of the enemy on the line from the Monk,
    the 0.5 s internal cooldown, Inner Fire's fireball line (60 long, 8 either side, ahead only, turning with the
    facing), fifteen Spirit payments for the 15 s, Ascendance's 10 yards. Six mutations planted in a scratch copy must
    each make it fail.
  * **The code reads what the sheets state.** Every number dc_monk_epiphany.cpp reads by name is an Epiphany row of
    monk_skill_values.csv (or generated_resource, read on the cast that triggered Inner Fire) or an epiphany_ row of
    data/tunables/monk.csv, with the value the sheets and Power/X1_Monk_Epiphany.pow give.
  * **The wiring.** dc_monk.cpp asks Epiphany for the punch first and dashes before Fists of Thunder's own Begin; the
    OnCast hook in dc_combat.cpp calls Monk::Casting beside Wizard::Begin (every cast: Inner Fire, Soothing Mist,
    Ascendance's decision), Monk::Landed hands every hit to Epiphany (Ascendance's stun) and Monk::Cast starts the buff.

What it does not prove: anything on a running server (the teleport, the heal, the stun, the fire, the Spirit ticks
and the damage reduction are docs/test-diablocraft-eg0m7.md's, live).

    python mod-diablocraft/scripts/tests/classes/test_monk_epiphany.py
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
HEADER = "src/classes/monk/dc_monk_epiphany.h"
SOURCES = [HEADER, "tests/monk_epiphany/harness.cpp"]
SKILL = "Epiphany"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def values():
    return read(D3 / "monk_skill_values.csv")


def value(rune, token, qualifier=""):
    rows = [r for r in values() if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "monk.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


CONE_SKILLS = ("Crippling Wave", "Way of the Hundred Fists", "Lashing Tail Kick")


def radius_of(skill):
    rows = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == skill]
    assert len(rows) == 1 and rows[0]["target_type"] == "cone_enemies", skill
    return float(rows[0]["radius_yards"])


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits the header."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        old, new = mutate
        key = HEADER[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_epiphany/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("epiphany_dash_min_yards"), tune("epiphany_dash_max_yards"), tune("epiphany_dash_offset_yards"),
               tune("epiphany_dash_icd_seconds"), tune("epiphany_fireball_length_yards"),
               tune("epiphany_fireball_radius_yards"), value("", "duration_seconds"),
               value("Ascendance", "distance_yards")]
    numbers += [radius_of(skill) for skill in CONE_SKILLS]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 33, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the minimum itself dashes", ("distance > minYards", "distance >= minYards")),
            ("the landing ignores the offset", ("(distance - offset) / distance", "1.0")),
            ("the cooldown never holds", ("if (last && now < *last + ms)", "if (false)")),
            ("the fireball hits behind", ("return along >= 0 && along", "return along")),
            ("one payment too many", ("unsigned(seconds + 1e-9)", "unsigned(seconds + 1e-9) + 1")),
            ("the stun does not spend the stride", ("void Spend()\n        {\n            moved = 0;",
                                                    "void Spend()\n        {")),
            ("the dash does not arm the attack it carries",
             ("if (stride.Armed(needed) && cast != spellId)", "if (false)")),
            ("a later hit of the same spell still stuns", ("if (*struckAt == now)", "if (true)")),
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
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "regen_per_second_resource", "duration_seconds")],
                         [60, 20, 15])
        self.assertEqual(value("Desert Shroud", "damage_reduction_pct"), 50)
        self.assertEqual([value("Soothing Mist", t) for t in ("radius_yards", "heal_life")], [30, 16093])
        self.assertEqual(value("Insight", "regen_per_second_resource"), 45)
        self.assertEqual(value("Inner Fire", "damage_pct"), 353)
        self.assertEqual([value("Ascendance", t) for t in ("distance_yards", "stun_duration_seconds")], [10, 1.5])

    def test_the_tunables_are_the_power_files(self):
        expected = {"epiphany_dash_min_yards": 7, "epiphany_dash_max_yards": 100, "epiphany_dash_offset_yards": 5,
                    "epiphany_dash_icd_seconds": 0.5, "epiphany_on_cast_icd_seconds": 0.5,
                    "epiphany_fireball_length_yards": 60, "epiphany_fireball_radius_yards": 8,
                    "epiphany_missile_count": 6, "epiphany_missile_radius_yards": 50,
                    "epiphany_move_sample_seconds": 0.1}
        rows = tunables()
        self.assertEqual({n for n in rows if n.startswith("epiphany_")}, set(expected))
        for name, number in expected.items():
            with self.subTest(name):
                self.assertEqual(float(rows[name]["d3_value"]), number)
                self.assertFalse(rows[name]["value"], "a power-file number is d3_value, the designer's column stays open")
                self.assertIn("X1_Monk_Epiphany.pow SF_", rows[name]["notes"])

    def test_every_name_the_code_reads_exists(self):
        text = (MODULE / "src/classes/monk/dc_monk_epiphany.cpp").read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        # Rabid Strike's copy (diablocraft-6d1jb) runs in the dash and reads its own radius
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("epiphany_")} | {"rabid_strike_search_radius_yards"})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|rune), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in values() if r["skill"] == SKILL}
        self.assertTrue(tokens)
        # Rabid Strike's copy asks the dashing skill's own cost, not Epiphany's (diablocraft-6d1jb)
        self.assertTrue({"Lashing Tail Kick", "Exploding Palm"} <= {r["skill"] for r in values() if r["token"] == "cost_resource"})
        self.assertEqual(tokens - sheet_tokens - {"cost_resource"}, set())
        self.assertIn('Numbers::Get(castSpellId, "generated_resource")', text)


if __name__ == "__main__":
    unittest.main()

"""Demon Hunter Shadow Power and its five runes (src/classes/demon_hunter/dc_demon_hunter_shadow_power.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_shadow_power/harness.cpp compiles the real
    dc_demon_hunter_shadow_power.h with the sheets' own rune names and numbers: each rune name is its rune; the Life per Hit is the
    power file's share of D3's Healing table at the level (the sheet's 26821 at level 70) plus a share of Life per Kill, and
    Blood Moon doubles the total. Six mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The skill is a self-cast spell (a `self` row of skill_targeting.csv) the generator already
    writes with the runes' sheet costs and durations, so there is no spell migration, only the tunables'.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Shadow Power
    (or the rune that states it); the one tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_ShadowPower.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch calls the cast; the cast gives the Life per Hit for the rune's seconds; Night Bane slows the
    enemies around, Shadow Glide gives the speed and Gloom the damage reduction, each for as long.

What it does not prove: anything on a running server. The Life per Hit, the slow, the speed and the reduction are
docs/test-diablocraft-vawmy.20.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_shadow_power.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/demon_hunter/dc_demon_hunter_shadow_power.h"
SOURCES = [HEADER, "tests/demon_hunter_shadow_power/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_shadow_power.cpp"
SKILL = "Shadow Power"
RUNES = ["Night Bane", "Shadow Glide", "Gloom", "Well of Darkness", "Blood Moon"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "demon_hunter_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "demon_hunter_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "demonhunter.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def healing_table():
    text = (MODULE / "src/combat/dc_healing_table.h").read_text(encoding="utf-8")
    body = text[text.index("Table[71] = {"):text.index("};", text.index("Table[71] = {"))]
    numbers = [float(n) for n in re.findall(r"\d+", body.split("{", 1)[1])]
    assert len(numbers) == 71
    return numbers


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_shadow_power/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    table = healing_table()
    numbers = runes() + [tune("shadow_power_life_on_hit_healing_share"), table[70], table[30], value("", "life_per_kill_share_pct"),
                         value("", "heal_per_hit_life")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 11, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Gloom")\n            return Rune::Gloom;', 'if (name == "Gloom")\n            return Rune::ShadowGlide;')),
            ("Blood Moon does not double", (HEADER, "return rune == Rune::BloodMoon ? 2.0 * base : base;", "return base;")),
            ("every rune doubles", (HEADER, "return rune == Rune::BloodMoon ? 2.0 * base : base;", "return 2.0 * base;")),
            ("Life per Kill is not added", (HEADER, "healingShare * healingAtLevel + killSharePct / 100.0 * lifePerKill", "healingShare * healingAtLevel")),
            ("the Life per Kill share is a whole", (HEADER, "killSharePct / 100.0 * lifePerKill", "killSharePct * lifePerKill")),
            ("the level is ignored", (HEADER, "healingShare * healingAtLevel +", "healingShare * 536421.0 +")),
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
        self.assertEqual(runes(), RUNES)

    def test_the_record_is_the_engines_self_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual(rows[SKILL]["target_type"], "self")
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "duration_seconds"), value("", "life_per_kill_share_pct")], [14, 5, 25])
        self.assertEqual([value("Night Bane", "radius_yards"), value("Night Bane", "slow_pct"), value("Night Bane", "slow_duration_seconds")],
                         [30, 80, 5])
        self.assertEqual(value("Shadow Glide", "movement_speed_pct"), 30)
        self.assertEqual(value("Gloom", "damage_reduction_pct"), 35)
        self.assertEqual(value("Well of Darkness", "cost_resource"), 8)

    def test_the_tunable(self):
        row = tunables()["shadow_power_life_on_hit_healing_share"]
        self.assertEqual((row["d3_value"], row["value"]), ("0.05", ""))
        self.assertIn("SF_1", row["notes"])
        self.assertIn("Power/DemonHunter_ShadowPower.pow", row["notes"])
        self.assertNotIn("placeholder", row["notes"].lower())
        self.assertAlmostEqual(tune("shadow_power_life_on_hit_healing_share") * healing_table()[70], value("", "heal_per_hit_life"), delta=1.0)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("shadow_power_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "duration_seconds", "own"), ("Gloom", "duration_seconds", "inherited"),
                                    ("Night Bane", "radius_yards", "own"), ("Night Bane", "slow_pct", "own"),
                                    ("Shadow Glide", "movement_speed_pct", "own"), ("Gloom", "damage_reduction_pct", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_ShadowPower.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(0), value("", "duration_seconds"))
        self.assertAlmostEqual(number(6), value("", "cost_resource"))
        self.assertAlmostEqual(number(7), value("Well of Darkness", "cost_resource"))
        self.assertAlmostEqual(number(3), value("Night Bane", "radius_yards"))
        self.assertAlmostEqual(number(10) * 100, value("Night Bane", "slow_pct"))
        self.assertAlmostEqual(number(11), value("Night Bane", "slow_duration_seconds"))
        self.assertAlmostEqual(number(2) * 100, value("Shadow Glide", "movement_speed_pct"))
        self.assertAlmostEqual(number(4) * 100, value("Gloom", "damage_reduction_pct"))
        self.assertAlmostEqual(number(12) * 100, value("", "life_per_kill_share_pct"))
        self.assertAlmostEqual(number(13) * 100, value("", "life_per_kill_share_pct"))
        self.assertIn("0.05 * Table(Healing,Effective_Level)", str(sf[1]))
        self.assertIn("0.05 * Table(Healing,Effective_Level)", str(sf[8]))
        self.assertAlmostEqual(0.05, tune("shadow_power_life_on_hit_healing_share"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_calls_the_cast(self):
        self.assertEqual(self.dispatch.count("ShadowPower::Cast(player, spellId, targets);"), 1)

    def test_the_life_per_hit_is_given_for_the_runes_seconds(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('double const seconds = Numbers::Num(spellId, "duration_seconds");', cast)
        self.assertIn("Buffs::Stack(player, spellId, Stat::LifePerHit, Bucket::Flat,", cast)
        self.assertIn('LifePerHit(rune, Tune("shadow_power_life_on_hit_healing_share"), Healing::At(player->GetLevel()), Numbers::Num(spellId, "life_per_kill_share_pct"), LifePerKill(player)), 1, seconds);', cast)

    def test_the_runes_part(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"));', cast)
        self.assertIn('Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards"))', cast)
        self.assertIn('Buffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped, Numbers::Num(spellId, "movement_speed_pct"), 1, seconds);', cast)
        self.assertIn('Buffs::Stack(player, spellId, Stat::SpecificReduction, Bucket::Flat, Numbers::Num(spellId, "damage_reduction_pct"), 1, seconds);', cast)


if __name__ == "__main__":
    unittest.main()

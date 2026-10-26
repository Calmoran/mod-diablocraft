"""Demon Hunter Smoke Screen and its five runes (src/classes/demon_hunter/dc_demon_hunter_smoke_screen.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_smoke_screen/harness.cpp compiles the real
    dc_demon_hunter_smoke_screen.h with the sheets' own rune names and numbers: each rune name is its rune; Displacement states its own
    speed and every other rune the power file's; the ticks of Healing Vapors give the percent of the maximum Life for each second; the
    cooldown is held back for the whole invisibility, Lingering Fog's longer one included. Six mutations planted in a scratch copy must
    each make it fail.
  * **The record needs no change.** The skill is a self-cast spell (a `self` row of skill_targeting.csv); the generator already gives
    Vanishing Powder no cost and the runes their sheet cooldowns, costs and durations, so there is no spell migration, only the tunables'.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Smoke Screen
    (or the rune that states it); the one tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_SmokeScreen.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch calls the cast; the cast makes the Demon Hunter invisible for the rune's seconds, gives the speed for
    as long, heals through Healing Vapors only, and pushes the shared cooldown back.

What it does not prove: anything on a running server. Whether the enemies lose the Demon Hunter, the speed and the cooldown are
docs/test-diablocraft-vawmy.19.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_smoke_screen.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_smoke_screen.h"
SOURCES = [HEADER, "tests/demon_hunter_smoke_screen/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_smoke_screen.cpp"
SKILL = "Smoke Screen"
RUNES = ["Vanishing Powder", "Lingering Fog", "Healing Vapors", "Special Recipe", "Displacement"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_smoke_screen/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("smoke_screen_movement_speed_pct"), value("Displacement", "movement_speed_pct"),
                         value("Healing Vapors", "life_regen_pct"), value("", "duration_seconds"), value("Lingering Fog", "duration_seconds"),
                         tune("smoke_screen_regen_tick_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 13, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Lingering Fog")\n            return Rune::LingeringFog;',
                                        'if (name == "Lingering Fog")\n            return Rune::VanishingPowder;')),
            ("Displacement gains the base speed", (HEADER, "return rune == Rune::Displacement ? runePct : basePct;", "return basePct;")),
            ("every rune gains Displacement's speed", (HEADER, "return rune == Rune::Displacement ? runePct : basePct;", "return runePct;")),
            ("a tick gives the whole second", (HEADER, "maxLife * pctPerSecond / 100.0 * tickSeconds", "maxLife * pctPerSecond / 100.0")),
            ("the cooldown waits seconds as milliseconds", (HEADER, "std::max(0.0, invisibleSeconds) * 1000.0 + 0.5", "std::max(0.0, invisibleSeconds) + 0.5")),
            ("the cooldown does not wait", (HEADER, "return std::uint64_t(std::max(0.0, invisibleSeconds) * 1000.0 + 0.5);", "return 0;")),
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
        self.assertEqual([value("", "cost_resource"), value("", "cooldown_seconds"), value("", "duration_seconds")], [14, 1.5, 1])
        self.assertEqual(value("Vanishing Powder", "cooldown_seconds"), 6)
        self.assertEqual(value("Lingering Fog", "duration_seconds"), 1.5)
        self.assertEqual(value("Healing Vapors", "life_regen_pct"), 15)
        self.assertEqual(value("Special Recipe", "cost_resource"), 8)
        self.assertEqual(value("Displacement", "movement_speed_pct"), 100)

    def test_the_tunable(self):
        row = tunables()["smoke_screen_movement_speed_pct"]
        self.assertEqual((row["d3_value"], row["value"]), ("15", ""))
        self.assertIn("SF_12", row["notes"])
        self.assertIn("Power/DemonHunter_SmokeScreen.pow", row["notes"])
        self.assertNotIn("placeholder", row["notes"].lower())

    def test_the_regen_tick_is_alexs_standing_default_row_and_no_tick_is_typed_into_the_code(self):
        # Neither the power file (SF_10 only) nor the tooltip gives Healing Vapors a tick rate, so the row is the designer's: a heal over time
        # ticks like a burn, every 0.5 s (AGENTS.md "Numbers", 2026-10-22; the Architect's ruling), in his column with no D3 value.
        row = tunables()["smoke_screen_regen_tick_seconds"]
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("", "0.5", "seconds"))
        self.assertIn("standing default", row["notes"])
        self.assertNotIn("placeholder", row["notes"].lower())
        self.assertIn("SF_10", row["notes"])
        code = CODE.read_text(encoding="utf-8")
        self.assertNotIn("RegenTickSeconds", code)
        self.assertNotRegex(code, r"constexpr double \w*Tick\w* =")
        self.assertIn('Tune("smoke_screen_regen_tick_seconds")', code)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("smoke_screen_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "duration_seconds", "own"), ("Lingering Fog", "duration_seconds", "own"),
                                    ("Healing Vapors", "duration_seconds", "inherited"), ("Healing Vapors", "life_regen_pct", "own"),
                                    ("Displacement", "movement_speed_pct", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))
        self.assertNotIn(("Vanishing Powder", "cost_resource"), mapped)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_SmokeScreen.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        def ternary(n):
            return float(str(sf[n]).split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(13), value("", "cost_resource"))
        self.assertAlmostEqual(number(13) - ternary(11), value("Special Recipe", "cost_resource"))
        self.assertAlmostEqual(number(9), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(3), value("Vanishing Powder", "cooldown_seconds"))
        self.assertAlmostEqual(number(14), value("", "duration_seconds"))
        self.assertAlmostEqual(number(14) + ternary(7), value("Lingering Fog", "duration_seconds"))
        self.assertAlmostEqual(ternary(10) * 100, value("Healing Vapors", "life_regen_pct"))
        self.assertAlmostEqual(ternary(12) * 100, value("Displacement", "movement_speed_pct"))
        self.assertAlmostEqual(float(str(sf[12]).split(":")[1]) * 100, tune("smoke_screen_movement_speed_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_calls_the_cast(self):
        self.assertEqual(self.dispatch.count("SmokeScreen::Cast(player, spellId, targets);"), 1)

    def test_the_cast_vanishes_for_the_runes_seconds_with_the_speed_for_as_long(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('double const seconds = Numbers::Num(spellId, "duration_seconds");', cast)
        self.assertIn("Vanish(player, seconds);", cast)
        self.assertIn('Buffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped, SpeedPct(rune, rune == Rune::Displacement ? Numbers::Num(spellId, "movement_speed_pct") : 0.0, Tune("smoke_screen_movement_speed_pct")), 1, seconds);', cast)

    def test_only_healing_vapors_heals_and_the_cooldown_is_pushed_back(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("if (rune == Rune::HealingVapors)", cast)
        self.assertIn('RegenPerTick(player->GetMaxHealth(), Numbers::Num(spellId, "life_regen_pct"), tick)', cast)
        self.assertIn("if (Skill == ability.skill && player->GetSpellCooldownDelay(ability.id))", cast)
        self.assertIn("player->ModifySpellCooldown(ability.id, std::int32_t(CooldownDelayMs(seconds)));", cast)


if __name__ == "__main__":
    unittest.main()

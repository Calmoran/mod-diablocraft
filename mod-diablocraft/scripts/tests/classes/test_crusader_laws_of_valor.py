"""Laws of Valor and its five runes, and the state every Law shares (src/classes/crusader/dc_crusader_laws.h and
dc_crusader_laws_of_valor.h and .cpp, dc_crusader_laws.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_laws/harness.cpp compiles the real dc_crusader_laws.h and
    dc_crusader_laws_of_valor.h with the sheets' own rune names and numbers: each rune name is its rune; Frozen in Terror's
    roll stuns under the chance and not at it; a holder wears the active speed while the window is open and the passive speed
    otherwise, never both; nothing cast leaves every Law on, a cast makes one Law the only one on and ends the last one's
    window, another Crusader's Laws are not touched; Answered Prayer's kills add a second each to the open window up to the
    maximum and no more, not to a closed window, another Law's or another Crusader's, and a new cast starts the count again.
    Fourteen mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token the two .cpp files read by name is a row of crusader_skill_values.csv
    for Laws of Valor (or the rune that states it), the generated value map says whose record holds it, and the numbers are the
    researched ones: Attack Speed 8% passive and 15% active for 5 seconds, Invincible 21457 Life on Hit, Frozen in Terror 100%
    to stun within 10 yards for 5 seconds, Critical 50% Critical Hit Damage, Unstoppable Force 50% for 5 seconds, Answered
    Prayer 1 second a kill up to 10.
  * **The Law deals no damage on the cast.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server, and the one reading of the sheet it takes: that the active number
replaces the passive one while the Law is empowered, and that Answered Prayer's 10 seconds is the most time kills add.

    python mod-diablocraft/scripts/tests/classes/test_crusader_laws_of_valor.py
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
LAWS = "src/classes/crusader/dc_crusader_laws.h"
VALOR = "src/classes/crusader/dc_crusader_laws_of_valor.h"
SOURCES = [LAWS, VALOR, "src/common/dc_common.h", "tests/crusader_laws/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_laws_of_valor.cpp"
MECHANISM = MODULE / "src/classes/crusader/dc_crusader_laws.cpp"
SKILL = "Laws of Valor"


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
    binary = harness_env.build([MODULE / "tests/crusader_laws/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "attack_speed_pct", "passive"), value("", "attack_speed_pct", "active"), value("", "duration_seconds"),
               value("Answered Prayer", "duration_seconds", "per_kill"), value("Answered Prayer", "duration_seconds", "max"),
               value("Frozen in Terror", "proc_chance_pct")] + runes()
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
            ("two runes share a name", (VALOR, "return Rune::AnsweredPrayer;", "return Rune::Critical;")),
            ("the roll is inclusive", (VALOR, "return roll < chancePct;", "return roll <= chancePct;")),
            ("the roll is not checked", (VALOR, "return roll < chancePct;", "return chancePct > 0;")),
            ("the active adds to the passive", (LAWS, "return boosted ? active : passive;", "return boosted ? active + passive : passive;")),
            ("the passive wins over the active", (LAWS, "return boosted ? active : passive;", "return passive;")),
            ("a cast leaves another Law on", (LAWS, "return found == detail::states.end() || found->second.active == law;",
                                                "return true;")),
            ("the window never closes", (LAWS, "now < found->second.boostUntil;\n    }\n\n    // When",
                                         "true;\n    }\n\n    // When")),
            ("the window is open for another Law", (LAWS, "found->second.active == law && now < found->second.boostUntil;",
                                                    "now < found->second.boostUntil;")),
            ("a kill adds more than the cap", (LAWS, "std::min(perKillMs, room)", "perKillMs")),
            ("a kill extends a closed window", (LAWS, " || now >= found->second.boostUntil)", ")")),
            ("a new cast keeps the count", (LAWS, "detail::states[crusader] = {law, now + boostMs, 0};",
                                            "detail::states[crusader].active = law; detail::states[crusader].boostUntil = now + boostMs;")),
            ("a logout forgets nothing", (LAWS, "detail::states.erase(crusader);", "(void)crusader;")),
            ("two Crusaders share a contribution", (LAWS, "return (crusader << 32) | (id & 0xFFFFFFFFull);", "return id & 0xFFFFFFFFull;")),
            ("a pulse's hold has no grace", (LAWS, "(std::max(0.0, periodSeconds) + std::max(0.0, graceSeconds))", "std::max(0.0, periodSeconds)")),
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
        self.assertEqual(runes(), ["Invincible", "Frozen in Terror", "Critical", "Unstoppable Force", "Answered Prayer"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "duration_seconds")], [30, 5])
        self.assertEqual([value("", "attack_speed_pct", "passive"), value("", "attack_speed_pct", "active")], [8, 15])
        self.assertEqual(value("Invincible", "heal_per_hit_life"), 21457)
        self.assertEqual([value("Frozen in Terror", t) for t in ("proc_chance_pct", "radius_yards", "stun_duration_seconds")], [100, 10, 5])
        self.assertEqual(value("Critical", "crit_damage_pct"), 50)
        self.assertEqual([value("Unstoppable Force", "cost_reduction_pct"), value("Unstoppable Force", "duration_seconds")], [50, 5])
        self.assertEqual([value("Answered Prayer", "duration_seconds", "per_kill"), value("Answered Prayer", "duration_seconds", "max")], [1, 10])

    def test_the_aura_reaches_sixty_yards_and_the_skill_has_no_pulse_number_on_the_sheet(self):
        targeting = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
        self.assertEqual(len(targeting), 1)
        self.assertEqual(float(targeting[0]["radius_yards"]), 60)
        tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertFalse({t for t in tokens if "interval" in t or "pulse" in t}, "a pulse number would be a sheet row")

    def test_every_token_the_code_reads_is_a_sheet_row_the_engine_can_read(self):
        text = CODE.read_text(encoding="utf-8")
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"attack_speed_pct", "heal_per_hit_life", "crit_damage_pct", "proc_chance_pct",
                                  "stun_duration_seconds", "radius_yards", "cost_reduction_pct", "duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "attack_speed_pct", "passive"), ("", "attack_speed_pct", "active"),
                                       ("", "duration_seconds", ""), ("Invincible", "heal_per_hit_life", ""),
                                       ("Frozen in Terror", "proc_chance_pct", ""), ("Frozen in Terror", "radius_yards", ""),
                                       ("Frozen in Terror", "stun_duration_seconds", ""), ("Critical", "crit_damage_pct", ""),
                                       ("Unstoppable Force", "cost_reduction_pct", ""), ("Unstoppable Force", "duration_seconds", ""),
                                       ("Answered Prayer", "duration_seconds", "per_kill"), ("Answered Prayer", "duration_seconds", "max")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertIn((rune, token, qualifier), mapped)
        # The speeds and the window reach every rune: on its own record or by inheritance.
        for rune in runes():
            for token, qualifier in (("attack_speed_pct", "passive"), ("attack_speed_pct", "active"), ("duration_seconds", "")):
                self.assertIn((rune, token, qualifier), mapped, (rune, token, qualifier))


if __name__ == "__main__":
    unittest.main()

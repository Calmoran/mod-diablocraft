"""Provoke and its five runes (src/classes/crusader/dc_crusader_provoke.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_provoke/harness.cpp compiles the real dc_crusader_provoke.h with the
    sheets' own rune names and numbers: each rune name is its rune; only Flee Fool frightens; the cast pays the base Wrath
    and the extra for each enemy; Cleanse stacks once per enemy; Charged Up lasts until its end time and its rider is owed
    only by the rune, only while it lasts, and never for its own hit. Nine mutations planted in a scratch copy (two runes
    share a name, every rune frightens, the base is lost with no enemy, the extra is paid once, a negative number pays,
    Charged Up outlasts its end, the rider lands on its own hit, any rune adds a rider, Cleanse stacks once) must each make
    it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_provoke.cpp reads by name is a row of
    crusader_skill_values.csv for Provoke (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: 30 Wrath and 5 for each enemy taunted, a 4 second taunt (Flee Fool's fear 8),
    Cleanse 1073 Life on Hit for 5 seconds, Too Scared to Run 50% attack speed and 80% slow for 4 seconds, Charged Up 50%
    for 4 seconds, Hit Me 50% Block Chance for 4 seconds. It reads no tunable: every number is a sheet row.
  * **Provoke deals no damage.** BasePct answers 0 for the skill and every rune.
  * **The stock auras are what the helpers say.** The client's Spell.dbc: "Challenging Shout" (1161) is one apply-aura
    effect, MOD_TAUNT, and "Slow" (10371) one MOD_MELEE_HASTE.

What it does not prove: anything on a running server, and which enemies the core lets be taunted.

    python mod-diablocraft/scripts/tests/classes/test_crusader_provoke.py
"""

import csv
import re
import struct
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/crusader/dc_crusader_provoke.h"
SOURCES = [HEADER, "tests/crusader_provoke/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_provoke.cpp"
SKILL = "Provoke"
CHALLENGING_SHOUT, SLOW = 1161, 10371


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
    binary = harness_env.build([MODULE / "tests/crusader_provoke/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "generated_resource", "base"), value("", "generated_resource", "per_enemy"),
               value("Charged Up", "damage_pct")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        extra = "(perEnemy > 0 ? perEnemy * enemies : 0.0)"
        rider = "return rune == Rune::ChargedUp && charged && !ownHit && pct > 0 ? pct : 0.0;"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::HitMe;", "return Rune::ChargedUp;")),
            ("every rune frightens", (HEADER, "return rune == Rune::FleeFool;", "return true;")),
            ("the base is lost with no enemy", (HEADER, "(base > 0 ? base : 0.0) + ", "")),
            ("the extra is paid once", (HEADER, "perEnemy * enemies", "perEnemy")),
            ("a negative number pays", (HEADER, extra, "(perEnemy * enemies)")),
            ("Charged Up outlasts its end", (HEADER, "return now < until;", "return now <= until;")),
            ("the rider lands on its own hit", (HEADER, rider, rider.replace(" && !ownHit", ""))),
            ("any rune adds a rider", (HEADER, rider, rider.replace("rune == Rune::ChargedUp && ", ""))),
            ("Cleanse stacks once", (HEADER, "? enemies : 0u", "? 1u : 0u")),
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
        self.assertEqual(runes(), ["Cleanse", "Flee Fool", "Too Scared to Run", "Charged Up", "Hit Me"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "duration_seconds"),
                          value("", "generated_resource", "base"), value("", "generated_resource", "per_enemy")], [20, 4, 30, 5])
        self.assertEqual((value("Cleanse", "heal_per_hit_life"), value("Cleanse", "duration_seconds")), (1073, 5))
        self.assertEqual(value("Flee Fool", "fear_duration_seconds"), 8)
        self.assertEqual([value("Too Scared to Run", t) for t in ("attack_speed_pct", "slow_pct", "slow_duration_seconds")], [50, 80, 4])
        self.assertEqual((value("Charged Up", "damage_pct"), value("Charged Up", "duration_seconds")), (50, 4))
        self.assertEqual((value("Hit Me", "block_pct"), value("Hit Me", "duration_seconds")), (50, 4))

    def test_the_skill_states_its_taunt_as_the_one_the_code_reads(self):
        # A rune that states a `duration_seconds` of its own (Cleanse 5, Charged Up 4, Hit Me 4) states the time of its bonus;
        # the taunt is the skill's, read from the skill's own record.
        self.assertIn("BaseId(Skill), \"duration_seconds\"", CODE.read_text(encoding="utf-8"))

    def test_no_tunable_is_read(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertNotIn("Tune(", text)
        self.assertNotIn("Tunables::", text)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"duration_seconds", "fear_duration_seconds", "generated_resource", "heal_per_hit_life",
                                  "slow_pct", "slow_duration_seconds", "attack_speed_pct", "damage_pct", "block_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "duration_seconds", ""), ("", "generated_resource", "base"),
                                       ("", "generated_resource", "per_enemy"),
                                       ("Cleanse", "heal_per_hit_life", ""), ("Cleanse", "duration_seconds", ""),
                                       ("Flee Fool", "fear_duration_seconds", ""),
                                       ("Too Scared to Run", "attack_speed_pct", ""), ("Too Scared to Run", "slow_pct", ""),
                                       ("Too Scared to Run", "slow_duration_seconds", ""),
                                       ("Charged Up", "damage_pct", ""), ("Charged Up", "duration_seconds", ""),
                                       ("Hit Me", "block_pct", ""), ("Hit Me", "duration_seconds", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertIn((rune, token, qualifier), mapped)
        # The Wrath reaches every rune: on its own record or by inheritance.
        for rune in runes():
            for qualifier in ("base", "per_enemy"):
                self.assertIn((rune, "generated_resource", qualifier), mapped, (rune, qualifier))


class StockRecords(unittest.TestCase):
    def record(self, spell_id):
        dbc = REPO / "azerothcore-wotlk/build/server/data/dbc/Spell.dbc"
        schema = REPO / "azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql"
        if not dbc.is_file() or not schema.is_file():
            raise unittest.SkipTest("no client Spell.dbc")
        columns, inside = [], False
        for line in schema.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("CREATE TABLE `spell_dbc`"):
                inside = True
            elif inside and line.startswith(")"):
                break
            elif inside and line.strip().startswith("`"):
                columns.append(line.strip().split("`")[1])
        data = dbc.read_bytes()
        _magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
        self.assertEqual(len(columns), fields)
        for i in range(count):
            row = struct.unpack_from("<%dI" % fields, data, 20 + i * size)
            if row[0] == spell_id:
                return dict(zip(columns, row))
        self.fail(f"no spell {spell_id}")

    def test_challenging_shout_is_a_plain_taunt(self):
        record = self.record(CHALLENGING_SHOUT)
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))   # SPELL_EFFECT_APPLY_AURA only
        self.assertEqual(11, record["EffectAura_1"])                                                # SPELL_AURA_MOD_TAUNT

    def test_slow_is_a_plain_attack_speed_cut(self):
        record = self.record(SLOW)
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))
        self.assertEqual(138, record["EffectAura_1"])                                               # SPELL_AURA_MOD_MELEE_HASTE


if __name__ == "__main__":
    unittest.main()

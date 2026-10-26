"""diablocraft-7k24o (Monk 2.3.15): Blinding Flash and its five runes.

What this proves, and how:

  * **The rules that need no core type.** tests/monk_blinding_flash/harness.cpp compiles the real dc_monk_blinding_flash.h
    with the sheets' numbers: an ordinary enemy is disoriented for the whole blind, an elite only as long as the tunable
    says (none while it is blank) and it alone misses 30% of its swings, for the blind and no longer; each enemy and each
    new flash is its own; Crippling Light waits for the end of the blind. Seven mutations planted in a scratch copy must
    each make it fail.
  * **The code reads what the sheets state.** Every number dc_monk_blinding_flash.cpp reads by name is a row of
    monk_skill_values.csv for that rune (or the skill, which a rune inherits): 3 seconds of blind over 20 yards and a 30%
    miss, Faith in the Light 29% for 3 seconds, Replenishing Light 10 Spirit, Mystifying Light 80% for 5 seconds, Self
    Reflection 6 seconds, Crippling Light 25% for 5 seconds. The elite's recovery time is a blank tunable (no source). The two
    stock spells that carry the blind and the slow exist in Spell.dbc with the one aura each is used for.
  * **The wiring.** dc_monk.cpp hands the skill's spell ids to its own file in Cast and answers MissChance; dc_combat.cpp
    asks it in the hit table's roll, after the module zeroes the avoid chances.

What it does not prove: anything on a running server. The blind, the miss, the slow and the Spirit need the Monk's records
(3mk78) and are docs/test-diablocraft-7k24o.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_blinding_flash.py
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
SOURCES = ["src/classes/monk/dc_monk_blinding_flash.h", "tests/monk_blinding_flash/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_blinding_flash.h"
CODE = MODULE / "src/classes/monk/dc_monk_blinding_flash.cpp"
SKILL = "Blinding Flash"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "monk_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "monk.csv")}


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
    binary = harness_env.build([MODULE / "tests/monk_blinding_flash/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "blind_duration_seconds"), value("Self Reflection", "blind_duration_seconds"),
               value("", "miss_chance_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("an elite is disoriented the whole blind", (HEADER, "std::min(std::max(eliteSeconds, 0.0), blindSeconds)", "blindSeconds")),
            ("an elite recovers after longer than the blind", (HEADER, "std::min(std::max(eliteSeconds, 0.0), blindSeconds)",
                                                               "std::max(eliteSeconds, 0.0)")),
            ("an ordinary enemy misses too", (HEADER, "return elite && missPct > 0 ? missPct : 0.0;", "return missPct > 0 ? missPct : 0.0;")),
            ("the blind never ends", (HEADER, "if (now >= found->second.untilMs)", "if (false)")),
            ("the blind ends a moment late", (HEADER, "if (now >= found->second.untilMs)", "if (now > found->second.untilMs)")),
            ("every enemy shares one blind", (HEADER, "book_[enemy] = {untilMs, missPct};", "book_[0] = {untilMs, missPct};")),
            ("the weakening begins at once", (HEADER, "blindSeconds * 1000.0 + 0.5", "0.0 * blindSeconds")),
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
    def test_the_numbers_the_code_reads_are_the_sheets(self):
        self.assertEqual((value("", "blind_duration_seconds"), value("", "radius_yards"), value("", "miss_chance_pct"),
                          value("", "cooldown_seconds")), (3, 20, 30, 15))
        self.assertEqual((value("Faith in the Light", "damage_bonus_pct"), value("Faith in the Light", "duration_seconds")), (29, 3))
        self.assertEqual(value("Replenishing Light", "gain_resource"), 10)
        self.assertEqual((value("Mystifying Light", "slow_pct"), value("Mystifying Light", "slow_duration_seconds")), (80, 5))
        self.assertEqual(value("Self Reflection", "blind_duration_seconds"), 6)
        self.assertEqual((value("Crippling Light", "enemy_damage_pct"), value("Crippling Light", "duration_seconds")), (25, 5))
        row = next(r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual((row["target_type"], float(row["radius_yards"])), ("self_aoe", 20))

    def test_the_elite_recovery_is_alexs_value(self):
        # no sheet or power file gives it: the designer's card q-1014-10, final (bead fwrjm)
        row = tunables()["blinding_flash_elite_disorient_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("", "1.5"))
        self.assertIn("diablocraft-7k24o", row["notes"])
        self.assertIn("q-1014-10", row["notes"])

    def test_every_name_the_code_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text)) | set(re.findall(r'Has\("monk", "([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("blinding_flash_")})
        tokens = set(re.findall(r'Numbers::Num\((?:spellId), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"blind_duration_seconds", "miss_chance_pct", "damage_bonus_pct", "duration_seconds",
                                  "radius_yards", "slow_pct", "slow_duration_seconds", "enemy_damage_pct", "gain_resource"})

    def test_the_stock_carriers_are_one_aura_each(self):
        carriers = {name: int(number) for name, number in re.findall(r"constexpr std::uint32_t (\w+) = (\d+);",
                                                                       CODE.read_text(encoding="utf-8"))}
        self.assertEqual(carriers, {"Dizzy": 9992, "Slowed": 50259})
        dbc = REPO / "azerothcore-wotlk/build/server/data/dbc/Spell.dbc"
        if not dbc.exists():
            self.skipTest("no stock Spell.dbc in this checkout")
        data = dbc.read_bytes()
        _, count, fields, size, _ = struct.unpack("<4sIIII", data[:20])
        body = data[20:20 + count * size]
        rows = {}
        for index in range(count):
            record = body[index * size:(index + 1) * size]
            rows[struct.unpack("<I", record[:4])[0]] = struct.unpack("<%dI" % fields, record)
        # Spell.dbc 3.3.5: Effect_1..3 at fields 71-73, EffectAura_1..3 at 95-97. Aura 5 is MOD_CONFUSE, 33 MOD_DECREASE_SPEED.
        for name, spell, aura in (("Dizzy", 9992, 5), ("Slowed", 50259, 33)):
            fields_of = rows[spell]
            used = [(effect, auras) for effect, auras in zip(fields_of[71:74], fields_of[95:98]) if effect]
            self.assertEqual(used, [(6, aura)], f"{name} ({spell}) is one apply-aura effect of aura {aura}")


if __name__ == "__main__":
    unittest.main()

"""Horrify and its five runes (src/classes/witch_doctor/dc_witch_doctor_horrify.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_horrify/harness.cpp compiles the real dc_witch_doctor_horrify.h with
    the sheet's own rune names: each rune name is its rune, the five are five, the base skill and every rune but Phobia
    immobilize what they frighten, and Phobia does not. Three mutations planted in a scratch copy (two runes share a name,
    every rune immobilizes, only the base skill immobilizes) must each make it fail. The same harness compiles the timed-numbers
    rules (dc_witch_doctor_buffs.h) a rune's Armor and run speed ride on: stacks rise to the cap, a second cast restarts the
    time, a buff that ran out starts again from one stack, and it is worth nothing from its end moment on. Five more mutations
    (no cap, the time is not restarted, a buff that ran out keeps its stacks, it outlasts its end, it is worth one stack
    whatever the count) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_witch_doctor_horrify.cpp reads by name is a row of
    witch_doctor_skill_values.csv for Horrify, the generated value map says whose record holds it (a rune's own, or its skill's
    by inheritance), and the numbers are the researched ones: an 18 yard circle (Face of Death 24), a 3 second fear (Phobia 5),
    Frightening Aspect 50% Armor for 8 seconds, Ruthless Terror 55 Mana per horrified enemy, Stalker 20% movement speed for
    4 seconds. It reads no tunable: every number is a sheet row.
  * **The sheet is D3's.** The numbers above are the ones D3's power file holds (Power/Witchdoctor_Horrify.pow, read with
    scripts/decode_pow.py): radius 18 plus 6, fear 3 plus 2, Armor 0.5 for 8, Mana 55, run speed 20% for 4.
  * **The wiring.** The engine calls WitchDoctor::Cast for every resolved cast, the class's dispatch hands Horrify's spells to
    its file, Phobia alone skips the root, and the circle is the record's own radius around the Witch Doctor.
  * **The stock auras are what the helpers say.** The client's Spell.dbc: "Fear" (5782) is a MOD_FEAR effect (mechanic Fear) with
    the fleeing creature's own run speed (MOD_INCREASE_SPEED, 25%) beside it, and "Earthgrab" (64695) one MOD_ROOT.

What it does not prove: anything on a running server, which enemies the core lets be frightened, and that a frightened
enemy stands still (a MOD_FEAR over a MOD_ROOT is the test sheet's, live).

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_horrify.py
"""

import csv
import re
import struct
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/witch_doctor/dc_witch_doctor_horrify.h"
BUFFS = "src/classes/witch_doctor/dc_witch_doctor_buffs.h"
SOURCES = [HEADER, BUFFS, "tests/witch_doctor_horrify/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_horrify.cpp"
DISPATCH = MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp"
RESOLVE = MODULE / "src/combat/dc_combat_resolve.cpp"
SKILL = "Horrify"
FEAR, EARTHGRAB = 5782, 64695


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "witch_doctor_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "witch_doctor_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
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
    binary = harness_env.build([MODULE / "tests/witch_doctor_horrify/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)] + runes(), capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 8, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        stays = "return rune != Rune::Phobia;"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Stalker;", "return Rune::Phobia;")),
            ("every rune immobilizes", (HEADER, stays, "return true;")),
            ("only the base skill immobilizes", (HEADER, stays, "return rune == Rune::None;")),
            ("no cap on the stacks", (BUFFS, "std::min(held.stacks + adds, std::max(1u, maxStacks))", "held.stacks + adds")),
            ("the time is not restarted", (BUFFS, "held.until = now + ms;", "held.until = held.until ? held.until : now + ms;")),
            ("a buff that ran out keeps its stacks", (BUFFS, "if (held.until <= now)\n            held.stacks = 0;", "")),
            ("the buff outlasts its end", (BUFFS, "return held.until <= now;", "return held.until < now;")),
            ("worth ignores the count", (BUFFS, "perStack * held.stacks", "perStack")),
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
        self.assertEqual(runes(), ["Frightening Aspect", "Face of Death", "Phobia", "Ruthless Terror", "Stalker"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "radius_yards"), value("", "fear_duration_seconds")],
                         [10, 18, 3])
        self.assertEqual((value("Frightening Aspect", "armor_pct"), value("Frightening Aspect", "duration_seconds")), (50, 8))
        self.assertEqual(value("Face of Death", "radius_yards"), 24)
        self.assertEqual(value("Phobia", "fear_duration_seconds"), 5)
        self.assertEqual(value("Ruthless Terror", "gain_resource"), 55)
        self.assertEqual((value("Stalker", "movement_speed_pct"), value("Stalker", "duration_seconds")), (20, 4))

    def test_the_numbers_are_the_power_files(self):
        out = subprocess.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", "Witchdoctor_Horrify"],
                             capture_output=True, text=True)
        if out.returncode:
            raise unittest.SkipTest("no D3 power files on this machine")
        sf = {}
        for line in out.stdout.splitlines():
            found = re.match(r"\s*SF_(\d+) '([^']*)' = (.*)$", line)
            if found:
                sf[int(found.group(1))] = found.group(3)
        self.assertEqual(float(sf[0]), value("", "radius_yards"))                              # Base: Horrify Radius
        self.assertEqual(float(sf[0]) + 6, value("Face of Death", "radius_yards"))             # + B: Radius Modifier
        self.assertEqual(float(sf[11]), value("", "fear_duration_seconds"))                    # Base: Fear Duration
        self.assertEqual(float(sf[11]) + 2, value("Phobia", "fear_duration_seconds"))          # + C: Fear Duration Modifier
        self.assertEqual(float(sf[8]), value("Ruthless Terror", "gain_resource"))              # D: Mana per monster feared
        self.assertEqual(float(sf[9]), value("Stalker", "movement_speed_pct"))                 # E: Increased Run Speed %
        self.assertEqual(float(sf[10]), value("Stalker", "duration_seconds"))                  # E: duration
        self.assertEqual(float(sf[12]), value("Frightening Aspect", "duration_seconds"))       # A: Seconds
        self.assertIn("Rune_A ? 0.5", sf[5])                                                   # A: Armor 50%
        self.assertEqual(float(sf[15]), value("", "cooldown_seconds"))                         # Base: Cooldown

    def test_no_tunable_is_read(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertNotIn("Tune(", text)
        self.assertNotIn("Tunables::", text)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"fear_duration_seconds", "radius_yards", "armor_pct", "duration_seconds",
                                  "movement_speed_pct", "gain_resource"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        # The circle and the fear reach every record: its own row, or its skill's by inheritance.
        for rune in [""] + runes():
            for token in ("fear_duration_seconds", "radius_yards"):
                with self.subTest(rune=rune, token=token):
                    self.assertIn((rune, token, ""), mapped)
        for rune, token in (("Frightening Aspect", "armor_pct"), ("Frightening Aspect", "duration_seconds"),
                            ("Stalker", "movement_speed_pct"), ("Stalker", "duration_seconds"),
                            ("Ruthless Terror", "gain_resource")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Wiring(unittest.TestCase):
    def test_the_engine_asks_the_class_for_every_resolved_cast(self):
        self.assertIn("WitchDoctor::Cast(player, shell.spellId, targets);", RESOLVE.read_text(encoding="utf-8"))

    def test_the_dispatch_hands_horrify_to_its_file(self):
        text = DISPATCH.read_text(encoding="utf-8")
        self.assertIn("Horrify::Cast(player, spellId);", text)
        self.assertIn('#include "dc_witch_doctor_horrify.h"', text)

    def test_only_phobia_skips_the_root(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertRegex(text, r"if \(Immobilizes\(rune\)\)\s*Root\(player, enemy, fear\);")
        self.assertEqual(text.count("Root("), 1)

    def test_the_circle_is_the_records_own_radius_around_the_caster(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertRegex(text, r'Enemies\(player, spellId, player->GetPosition\(\), Numbers::Num\(spellId, "radius_yards"\)\)')

    def test_ruthless_terror_pays_for_the_enemies_the_fear_took_hold_of(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertRegex(text, r"if \(Fear\(player, enemy, fear\)\)\s*\{\s*\+\+horrified;")
        self.assertIn('Numbers::Num(spellId, "gain_resource"), horrified);', text)


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

    def test_fear_is_a_plain_fear(self):
        record = self.record(FEAR)
        self.assertEqual((6, 6, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))   # SPELL_EFFECT_APPLY_AURA twice
        self.assertEqual((7, 31), (record["EffectAura_1"], record["EffectAura_2"]))                 # MOD_FEAR, MOD_INCREASE_SPEED
        self.assertEqual(5, record["Mechanic"])                                                     # MECHANIC_FEAR

    def test_earthgrab_is_a_plain_root(self):
        record = self.record(EARTHGRAB)
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))
        self.assertEqual(26, record["EffectAura_1"])                                                # SPELL_AURA_MOD_ROOT


if __name__ == "__main__":
    unittest.main()

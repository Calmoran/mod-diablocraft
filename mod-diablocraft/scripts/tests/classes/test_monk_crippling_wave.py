"""diablocraft-fcmj0 (Monk 2.3.03): Crippling Wave and its five runes.

What this proves, and how:

  * **The logic that needs no core type.** tests/monk_crippling_wave/harness.cpp compiles the real
    dc_monk_crippling_wave.h (with Fists of Thunder's Combo) and feeds it the sheets' own numbers: which swing is the
    third, the reach (the targeting sheet's 11 yards, Tsunami's 17 for the third swing only), the 180 degree arc in
    radians, Rising Tide's 2.5 Spirit for each enemy hit, the slows as negative amounts. Six mutations planted in a
    scratch copy (the third hit is any hit, Tsunami's reach for every swing, the arc in the wrong unit, Rising Tide
    paid once, a positive slow, the base reach lost) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_monk_crippling_wave.cpp reads by name is a row of
    monk_skill_values.csv for Crippling Wave (or for the rune that states it), every tunable it reads is a row of
    data/tunables/monk.csv, with the values the research gives: 155% (255% Mangle), 11 yards, slow 30%, attack speed
    20%, 3 seconds, Tsunami 17 yards and a 1 second freeze, Concussion 20%, Rising Tide 2.5, Breaking Wave 10%; the
    cone 180 degrees. The three stock spells that carry the daze and the freeze exist in Spell.dbc with the one aura
    each is used for.
  * **The wiring.** The cast path asks Monk::Begin before the hits and Monk::Cast after them (Fists of Thunder's
    existing hooks), dc_monk.cpp hands a Crippling Wave spell to Wave::Begin / Wave::Cast and pays its per-attack
    Spirit from Wave::PerAttack; Concussion goes through Effects::Weaken, Breaking Wave through Effects::Taken.

What it does not prove: anything on a running server. The swings, the daze, the freeze, the debuffs and the Spirit
need the Monk's records (3mk78) and are docs/test-diablocraft-fcmj0.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_crippling_wave.py
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
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import barbarian_source  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
SOURCES = ["src/classes/monk/dc_monk_crippling_wave.h", "src/classes/monk/dc_monk_fists.h",
           "tests/monk_crippling_wave/harness.cpp"]
SKILL = "Crippling Wave"
CODE = MODULE / "src/classes/monk/dc_monk_crippling_wave.cpp"
HEADER = "src/classes/monk/dc_monk_crippling_wave.h"


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


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def target_radius():
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
    binary = harness_env.build([MODULE / "tests/monk_crippling_wave/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("fists_combo_window_frames"), tune("fists_combo_frames_per_second"), target_radius(),
               value("Tsunami", "radius_yards"), tune("crippling_wave_cone_degrees"),
               value("Rising Tide", "generated_resource"), value("", "slow_pct"), value("", "attack_speed_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("every hit is the third", (HEADER, "return stage == 3;", "return stage >= 1;")),
            ("Tsunami's reach for every swing", (HEADER, "return IsThird(stage) && runeYards > baseYards ? runeYards : baseYards;",
                                                 "return runeYards > baseYards ? runeYards : baseYards;")),
            ("the base reach is lost", (HEADER, "return IsThird(stage) && runeYards > baseYards ? runeYards : baseYards;",
                                        "return IsThird(stage) ? runeYards : baseYards;")),
            ("the arc in the wrong unit", (HEADER, "return degrees * 3.14159265358979323846 / 180.0;",
                                           "return degrees * 3.14159265358979323846 / 360.0;")),
            ("Rising Tide paid once", (HEADER, "return perEnemy > 0 ? perEnemy * enemiesHit : 0.0;",
                                       "return perEnemy > 0 && enemiesHit ? perEnemy : 0.0;")),
            ("the slow is positive", (HEADER, "return -static_cast<int>(std::lround(pct));",
                                      "return static_cast<int>(std::lround(pct));")),
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
        self.assertEqual([value("", token) for token in
                          ("generated_resource", "damage_pct", "radius_yards", "slow_pct", "attack_speed_pct",
                           "duration_seconds")], [12, 155, 11, 30, 20, 3])
        self.assertEqual(value("Mangle", "damage_pct"), 255)
        self.assertEqual((value("Tsunami", "radius_yards"), value("Tsunami", "freeze_duration_seconds")), (17, 1))
        self.assertEqual((value("Concussion", "enemy_damage_pct"), value("Concussion", "duration_seconds")), (20, 3))
        self.assertEqual(value("Rising Tide", "generated_resource"), 2.5)
        self.assertEqual((value("Breaking Wave", "damage_taken_pct"), value("Breaking Wave", "duration_seconds")), (10, 3))
        self.assertEqual(target_radius(), 11)

    def test_the_tunables(self):
        row = tunables()["crippling_wave_cone_degrees"]
        self.assertEqual((row["d3_value"], row["value"]), ("180", ""))
        self.assertIn("SF_6", row["notes"])

    def test_the_arc_is_not_a_fists_tunable(self):
        # test_monk_fists.py compares only the fists_* names with dc_monk.cpp's reads.
        self.assertNotIn("crippling_wave_cone_degrees",
                         set(re.findall(r'Tune\("([a-z0-9_]+)"\)',
                                        (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8"))))

    def test_every_name_the_code_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {"fists_combo_window_frames", "fists_combo_frames_per_second",
                                         "crippling_wave_cone_degrees"})
        for name in read_tunables:
            self.assertIn(name, tunables())
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\((?:spellId|rune), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertGreaterEqual(len(tokens), 8)

    def test_the_stock_carriers_are_the_auras_they_are_used_for(self):
        text = CODE.read_text(encoding="utf-8")
        carriers = {name: int(number) for name, number in
                    re.findall(r"constexpr std::uint32_t (\w+) = (\d+);", text)}
        self.assertEqual(carriers, {"FreezeHold": 15878, "DazeMovement": 50259, "DazeAttacks": 10371})
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
        # Spell.dbc 3.3.5: Effect_1..3 at fields 71-73, EffectAura_1..3 at 95-97.
        for name, spell, aura in (("FreezeHold", 15878, 12), ("DazeMovement", 50259, 33), ("DazeAttacks", 10371, 138)):
            fields_of = rows[spell]
            used = [(effect, auras) for effect, auras in zip(fields_of[71:74], fields_of[95:98]) if effect]
            self.assertEqual(used, [(6, aura)], f"{name} ({spell}) is one apply-aura effect of aura {aura}")


if __name__ == "__main__":
    unittest.main()

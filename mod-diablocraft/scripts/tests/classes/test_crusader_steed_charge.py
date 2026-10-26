"""Steed Charge and its five runes (src/classes/crusader/dc_crusader_steed_charge.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_steed_charge/harness.cpp compiles the real
    dc_crusader_steed_charge.h with the sheets' own rune names and numbers: each rune name is its rune; a per-second number
    is paid in ticks that add up to the second; Rejuvenation heals its percentage of the maximum Life in total over the ride (Endurance's longer one too), not each second; the speed bonus is a
    percentage; Nightmare's first pool is always dropped and the next only after the spacing; Draw and Quarter draws only an
    enemy farther than the distance, to that distance. Eleven mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_steed_charge.cpp reads by name is a row of
    crusader_skill_values.csv for Steed Charge, the generated value map says whose record holds it, and the numbers are the
    researched ones: 2 seconds (Endurance 3), Spiked Barding 500% of Thorns, Rejuvenation 15% of the maximum Life,
    Nightmare 550%, Draw and Quarter 5 enemies at 185%. Every tunable it reads is a row of data/tunables/crusader.csv with
    the power file's number (Power/X1_Crusader_SteedCharge.pow) as its D3 value and none of the designer's.
  * **Steed Charge deals no damage of its own.** BasePct answers 0 for the skill and every rune.
  * **The stock horse is what the code says.** The client's Spell.dbc: "Summon Charger" (34767) is two apply-aura effects,
    MOUNTED then the mounted speed, which is the effect the code sets to 0.

What it does not prove: anything on a running server, or how the client draws the horse.

    python mod-diablocraft/scripts/tests/classes/test_crusader_steed_charge.py
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
HEADER = "src/classes/crusader/dc_crusader_steed_charge.h"
SOURCES = [HEADER, "tests/crusader_steed_charge/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_steed_charge.cpp"
SKILL = "Steed Charge"
SUMMON_CHARGER = 34767
POW = "Power/X1_Crusader_SteedCharge.pow"


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
    return {r["name"]: r for r in read(MODULE / "data/tunables/crusader.csv") if r["name"].startswith("steed_charge_")}


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
    binary = harness_env.build([MODULE / "tests/crusader_steed_charge/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    rows = tunables()
    numbers = [value("Spiked Barding", "thorns_share_pct"), value("Rejuvenation", "heal_pct"),
               float(rows["steed_charge_tick_seconds"]["d3_value"]), float(rows["steed_charge_movement_speed_bonus"]["d3_value"]),
               float(rows["steed_charge_draw_distance_yards"]["d3_value"])] + runes() + [
               value("", "duration_seconds"), value("Endurance", "duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::DrawAndQuarter;", "return Rune::Nightmare;")),
            ("a tick pays the whole second", (HEADER, "perSecond * tickSeconds : 0.0", "perSecond : 0.0")),
            ("the heal ignores the maximum Life", (HEADER, "maxLife * healPct / 100.0", "healPct / 100.0")),
            ("every tick heals the whole percentage", (HEADER, "/ 100.0 / ticks : 0.0", "/ 100.0 : 0.0")),
            ("the heal is paid per second, four ticks to the second", (HEADER, "/ 100.0 / ticks : 0.0", "/ 100.0 / 4.0 : 0.0")),
            ("the bonus is not a percentage", (HEADER, "bonus * 100.0", "bonus")),
            ("the first pool is lost", (HEADER, "!hasLast || distanceFromLast >= spacing", "hasLast && distanceFromLast >= spacing")),
            ("a pool falls at once", (HEADER, "distanceFromLast >= spacing", "distanceFromLast >= 0")),
            ("an enemy at the distance is drawn", (HEADER, "distance > keep;", "distance >= keep;")),
            ("the fraction is upside down", (HEADER, "keep / distance : 1.0", "distance / keep : 1.0")),
            ("no distance draws all", (HEADER, "keep > 0 && distance > keep", "distance > keep")),
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
        self.assertEqual(runes(), ["Spiked Barding", "Endurance", "Rejuvenation", "Nightmare", "Draw and Quarter"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "duration_seconds")], [16, 2])
        self.assertEqual(value("Endurance", "duration_seconds"), 3)
        self.assertEqual(value("Spiked Barding", "thorns_share_pct"), 500)
        self.assertEqual(value("Rejuvenation", "heal_pct"), 15)
        self.assertEqual(value("Nightmare", "damage_pct"), 550)
        self.assertEqual((value("Draw and Quarter", "target_count"), value("Draw and Quarter", "damage_pct")), (5, 185))

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"duration_seconds", "thorns_share_pct", "heal_pct", "damage_pct", "target_count"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "duration_seconds"), ("Endurance", "duration_seconds"), ("Spiked Barding", "thorns_share_pct"),
                            ("Rejuvenation", "heal_pct"), ("Nightmare", "damage_pct"), ("Draw and Quarter", "damage_pct"),
                            ("Draw and Quarter", "target_count")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)
        for rune in runes():
            self.assertIn((rune, "duration_seconds", ""), mapped, rune)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "steed_charge_tick_seconds": "0.25",                  # SF_5 = 1 / SF_6 (4)
        "steed_charge_movement_speed_bonus": "1.5",           # SF_1
        "steed_charge_spiked_barding_radius_yards": "6.5",    # SF_12
        "steed_charge_nightmare_pool_radius_yards": "6",      # SF_23
        "steed_charge_nightmare_pool_seconds": "1.4",         # SF_24
        "steed_charge_nightmare_pool_tick_seconds": "0.2",    # SF_21
        "steed_charge_nightmare_pool_spacing_yards": "3.1623",  # sqrt(SF_26 = 10)
        "steed_charge_draw_radius_yards": "15",               # SF_28
        "steed_charge_draw_distance_yards": "10",             # SF_33
    }

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        self.assertEqual(set(rows), set(self.NUMBERS))
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertIn(POW, rows[name]["notes"])
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))

    def test_the_spacing_is_the_square_root_of_the_power_files_ten(self):
        self.assertAlmostEqual(float(tunables()["steed_charge_nightmare_pool_spacing_yards"]["d3_value"]), 10 ** 0.5, places=3)


class StockRecords(unittest.TestCase):
    def test_summon_charger_is_the_mount_then_its_speed(self):
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if not dbc.is_file():
            raise unittest.SkipTest("no client Spell.dbc")
        data = dbc.read_bytes()
        _magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
        self.assertEqual(fields, 234)
        for i in range(count):
            row = struct.unpack_from("<%dI" % fields, data, 20 + i * size)
            if row[0] == SUMMON_CHARGER:
                # Effect_1, Effect_2 are SPELL_EFFECT_APPLY_AURA; EffectAura_1 is MOUNTED (78), EffectAura_2 the mounted speed (32).
                self.assertEqual((row[71], row[72]), (6, 6))
                self.assertEqual((row[95], row[96]), (78, 32))
                return
        self.fail(f"no spell {SUMMON_CHARGER}")

    def test_the_code_sets_the_second_effect_to_nothing(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn("constexpr std::uint32_t Horse = 34767;", text)
        self.assertIn("mount->GetEffect(EFFECT_1)", text)
        self.assertIn("speed->ChangeAmount(0);", text)


if __name__ == "__main__":
    unittest.main()

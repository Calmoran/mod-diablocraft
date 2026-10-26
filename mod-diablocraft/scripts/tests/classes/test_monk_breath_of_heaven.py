"""diablocraft-exsmi (Monk 2.3.16): Breath of Heaven and its five runes.

What this proves, and how:

  * **The logic that needs no core type.** tests/monk_breath_of_heaven/harness.cpp compiles the real
    dc_monk_breath_of_heaven.h and feeds it the sheets' numbers: the heal between the minimum and the maximum by a roll (held
    to the range), Circle of Life's double, the share of the Health Globe Healing Bonus, Infused with Light's window and its
    extra Spirit, Zephyr's amount. Seven mutations planted in a scratch copy (the roll ignores the spread, the roll is not
    held, the globe share is lost, the window never ends, outside the window still pays, a non-generating attack pays, a
    negative speed) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_monk_breath_of_heaven.cpp reads by name is a row of
    monk_skill_values.csv for Breath of Heaven (or the rune that states it): 15 seconds, 12 yards, 69735 - 91192 Life and
    30% of the Health Globe Healing Bonus, Circle of Scorn 505%, Circle of Life 139469 - 182383, Blazing Wrath 10% for 9
    seconds, Infused with Light 14 Spirit for 5 seconds, Zephyr 30% for 3 seconds. The power file agrees with the sheet on
    every number (SF_16 cooldown 15, SF_4 radius 12, SF_5 5.05, SF_6 x2, SF_8 9, SF_9 0.1, SF_11 5, SF_12 14, SF_13 3, SF_14
    0.3, SF_15 0.3), so no sheet row changes. The stock speed carrier exists in Spell.dbc with the one aura it is used for.
  * **The wiring.** dc_monk.cpp hands a Breath of Heaven cast to Breath::Cast and every connected attack to Breath::Attack.

What it does not prove: anything on a running server. The heal, the speed and the window need the Monk's records and are
docs/test-diablocraft-exsmi.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_breath_of_heaven.py
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
SOURCES = ["src/classes/monk/dc_monk_breath_of_heaven.h", "tests/monk_breath_of_heaven/harness.cpp"]
SKILL = "Breath of Heaven"
CODE = MODULE / "src/classes/monk/dc_monk_breath_of_heaven.cpp"
HEADER = "src/classes/monk/dc_monk_breath_of_heaven.h"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "monk_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


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
    binary = harness_env.build([MODULE / "tests/monk_breath_of_heaven/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "heal_min_life"), value("", "heal_max_life"), value("Circle of Life", "heal_min_life"),
               value("Circle of Life", "heal_max_life"), value("", "healing_bonus_share_pct"),
               value("Infused with Light", "gain_resource"), value("Infused with Light", "duration_seconds"),
               value("Zephyr", "movement_speed_pct")]
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
            ("the roll ignores the spread", (HEADER, "return minLife + spread * (maxLife - minLife) +",
                                             "return minLife + 0 * spread * (maxLife - minLife) +")),
            ("the roll is not held to the range", (HEADER, "std::clamp(roll, 0.0, 1.0)", "roll")),
            ("the globe share is lost", (HEADER, " + sharePct / 100.0 * globeBonusLife;", ";")),
            ("the window never ends", (HEADER, "return now < until;", "return true;")),
            ("outside the window still pays", (HEADER, "return inWindow && generates && gain > 0 ? gain : 0.0;",
                                               "return generates && gain > 0 ? gain : 0.0;")),
            ("an attack that generates nothing pays", (HEADER, "return inWindow && generates && gain > 0 ? gain : 0.0;",
                                                       "return inWindow && gain > 0 ? gain : 0.0;")),
            ("the speed is negative", (HEADER, "return static_cast<int>(std::lround(pct));",
                                       "return -static_cast<int>(std::lround(pct));")),
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
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "radius_yards", "heal_min_life", "heal_max_life",
                                                "healing_bonus_share_pct")], [15, 12, 69735, 91192, 30])
        self.assertEqual(value("Circle of Scorn", "damage_pct"), 505)
        self.assertEqual([value("Circle of Life", t) for t in ("heal_min_life", "heal_max_life", "healing_bonus_share_pct")],
                         [139469, 182383, 30])
        self.assertEqual((value("Blazing Wrath", "damage_bonus_pct"), value("Blazing Wrath", "duration_seconds")), (10, 9))
        self.assertEqual((value("Infused with Light", "gain_resource"), value("Infused with Light", "duration_seconds")), (14, 5))
        self.assertEqual((value("Zephyr", "movement_speed_pct"), value("Zephyr", "duration_seconds")), (30, 3))

    def test_the_power_file_and_the_sheet_agree(self):
        # Power/Monk_BreathOfHeaven.pow (decoded, read-only): SF_16 cooldown 15, SF_4 radius 12, SF_5 A damage 5.05, SF_6 B
        # bonus heal x2, SF_8 C duration 9, SF_9 C 0.1, SF_11 D duration 5, SF_12 D spirit 14, SF_13 E duration 3, SF_14 E
        # speed 0.3, SF_15 globe scalar 0.3; SF_22 0.13 and SF_23 0.04 of the Healing table: max / min = 0.17 / 0.13.
        self.assertEqual(value("", "cooldown_seconds"), 15)
        self.assertEqual(value("Circle of Scorn", "damage_pct") / 100, 5.05)
        self.assertEqual(value("Blazing Wrath", "duration_seconds"), 9)
        self.assertEqual(value("Blazing Wrath", "damage_bonus_pct") / 100, 0.1)
        self.assertEqual(value("Infused with Light", "duration_seconds"), 5)
        self.assertEqual(value("Zephyr", "duration_seconds"), 3)
        self.assertEqual(value("Zephyr", "movement_speed_pct") / 100, 0.3)
        self.assertEqual(value("", "healing_bonus_share_pct") / 100, 0.3)
        self.assertEqual(round(value("", "heal_max_life") / value("", "heal_min_life"), 3), round(0.17 / 0.13, 3))
        self.assertAlmostEqual(value("Circle of Life", "heal_min_life") / value("", "heal_min_life"), 2, places=4)
        self.assertAlmostEqual(value("Circle of Life", "heal_max_life") / value("", "heal_max_life"), 2, places=4)

    def test_every_name_the_code_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(spellId, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertGreaterEqual(len(tokens), 8)
        self.assertNotIn("Tune(", text)  # every number is a sheet row: no tunable of this bead

    def test_the_stock_carrier_is_the_aura_it_is_used_for(self):
        text = CODE.read_text(encoding="utf-8")
        carriers = {name: int(number) for name, number in re.findall(r"constexpr std::uint32_t (\w+) = (\d+);", text)}
        self.assertEqual(carriers, {"Hasted": 14530})
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
        fields_of = rows[14530]
        used = [(effect, auras) for effect, auras in zip(fields_of[71:74], fields_of[95:98]) if effect]
        self.assertEqual(used, [(6, 31)], "Speed (14530) is one apply-aura effect of MOD_INCREASE_SPEED")


if __name__ == "__main__":
    unittest.main()

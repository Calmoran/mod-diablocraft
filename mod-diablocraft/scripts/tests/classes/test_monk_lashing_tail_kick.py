"""diablocraft-m2bk4 (Monk 2.3.05): Lashing Tail Kick and its five runes.

What this proves, and how:

  * **The logic that needs no core type.** tests/monk_lashing_tail_kick/harness.cpp compiles the real
    dc_monk_lashing_tail_kick.h and feeds it the sheets' and the power file's numbers: the 180 degree arc in radians, the
    column of Spinning Flame Kick (ahead, the far end, past it, behind, the strip's edges, any facing, no width), the
    ticks of Vulture Claw Kick's burn and their shares adding up to 230%, the slow as a negative amount. Nine mutations
    planted in a scratch copy (the arc in the wrong unit, a column that reaches behind the Monk, a column that ignores
    its width, a burn that pays its total at every tick, a partial tick rounded up, a positive slow, a
    column with no length limit) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_monk_lashing_tail_kick.cpp reads by name is a row of
    monk_skill_values.csv for Lashing Tail Kick, every tunable it reads is a row of data/tunables/monk.csv, with the
    numbers the research gives: 50 Spirit and 755%, Vulture Claw Kick 10 yards, 755% and 230% over 3 seconds, Spinning Flame
    Kick 755%, Hand of Ytar 80% for 3 seconds, Sweeping Armada 825% over 15 yards, Scorpion Sting 2 seconds; the cone 180
    degrees and the column 50 yards. The power file agrees with the sheet on every duration, so no sheet row changes. The
    column's width and the burn's tick are blank tunables (no source). The two stock spells that carry the slow and the
    stun exist in Spell.dbc with the one aura each is used for.
  * **The wiring.** dc_monk.cpp hands a Lashing Tail Kick spell to Kick::BasePct and Kick::Cast; the kick has no
    Spirit generation.

What it does not prove: anything on a running server. The kick, the burn, the slow and the stun need the Monk's records
(3mk78) and are docs/test-diablocraft-m2bk4.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_lashing_tail_kick.py
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
SOURCES = ["src/classes/monk/dc_monk_lashing_tail_kick.h", "tests/monk_lashing_tail_kick/harness.cpp"]
SKILL = "Lashing Tail Kick"
CODE = MODULE / "src/classes/monk/dc_monk_lashing_tail_kick.cpp"
HEADER = "src/classes/monk/dc_monk_lashing_tail_kick.h"


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
    binary = harness_env.build([MODULE / "tests/monk_lashing_tail_kick/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("lashing_tail_kick_cone_degrees"), tune("lashing_tail_kick_column_yards"),
               value("Vulture Claw Kick", "damage_pct", "dot"), value("Vulture Claw Kick", "dot_duration_seconds"),
               value("Hand of Ytar", "slow_pct")]
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
            ("the arc in the wrong unit", (HEADER, "return degrees * 3.14159265358979323846 / 180.0;",
                                           "return degrees * 3.14159265358979323846 / 360.0;")),
            ("the column reaches behind the Monk", (HEADER, "return along >= 0 && along <= length &&",
                                                    "return along <= length &&")),
            ("the column ignores its width", (HEADER, " && std::fabs(across) <= width / 2;", ";")),
            ("the column has no end", (HEADER, "along >= 0 && along <= length &&", "along >= 0 &&")),
            ("the burn pays its total at every tick", (HEADER, "return ticks ? totalPct / ticks : 0.0;",
                                                       "return ticks ? totalPct : 0.0;")),
            ("a partial tick is rounded up", (HEADER, "std::floor(seconds / tickSeconds + 1e-9)",
                                              "std::ceil(seconds / tickSeconds)")),
            ("a dead enemy is thrown", (HEADER, "return struck && alive;", "return struck;")),
            ("an enemy the kick missed is thrown", (HEADER, "return struck && alive;", "return alive;")),
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
        self.assertEqual((value("", "cost_resource"), value("", "damage_pct")), (50, 755))
        vulture = "Vulture Claw Kick"
        self.assertEqual([value(vulture, "radius_yards"), value(vulture, "damage_pct", "hit"),
                          value(vulture, "damage_pct", "dot"), value(vulture, "dot_duration_seconds")], [10, 755, 230, 3])
        self.assertEqual(value("Spinning Flame Kick", "damage_pct"), 755)
        self.assertEqual((value("Hand of Ytar", "slow_pct"), value("Hand of Ytar", "slow_duration_seconds")), (80, 3))
        self.assertEqual((value("Sweeping Armada", "damage_pct"), value("Sweeping Armada", "radius_yards")), (825, 15))
        self.assertEqual(value("Scorpion Sting", "stun_duration_seconds"), 2)

    def test_the_tunables(self):
        tuned = tunables()
        self.assertEqual((tuned["lashing_tail_kick_cone_degrees"]["d3_value"], tuned["lashing_tail_kick_cone_degrees"]["value"]),
                         ("180", ""))
        self.assertIn("SF_7", tuned["lashing_tail_kick_cone_degrees"]["notes"])
        self.assertEqual(tune("lashing_tail_kick_column_yards"), 50)
        self.assertIn("SF_16", tuned["lashing_tail_kick_column_yards"]["notes"])
        # No source gives these two: the designer's values (bead 760kv, cards q-1014-01..04): a 5 yard column, a 1 second burn tick.
        for name, alex in (("lashing_tail_kick_column_width_yards", "5"), ("lashing_tail_kick_dot_tick_seconds", "1")):
            self.assertEqual((tuned[name]["d3_value"], tuned[name]["value"]), ("", alex), name)
            self.assertIn("diablocraft-760kv", tuned[name]["notes"], name)

    def test_the_knockback_numbers_are_the_power_files(self):
        # Power/Monk_LashingTailKick.pow: SF_3 = SF_22 45 x SF_23 1, SF_4 = 2.0 x SF_23, SF_5 = -0.05. The unit of 45 is
        # unread, so its tunable is blank; the other two are the D3 numbers, not read by the code (the stock record's
        # speeds are baked into it).
        tuned = tunables()
        self.assertEqual((tuned["lashing_tail_kick_knockback_magnitude"]["d3_value"],
                          tuned["lashing_tail_kick_knockback_magnitude"]["value"]), ("", ""))
        self.assertEqual(tune("lashing_tail_kick_knockback_height"), 2)
        self.assertEqual(tune("lashing_tail_kick_knockback_gravity"), -0.05)
        for suffix, source in (("magnitude", "SF_3"), ("height", "SF_4"), ("gravity", "SF_5")):
            self.assertIn(source, tuned["lashing_tail_kick_knockback_" + suffix]["notes"])
        text = CODE.read_text(encoding="utf-8")
        self.assertNotIn("knockback_magnitude\"", text)

    def test_the_tunables_are_not_fists_tunables(self):
        # test_monk_fists.py compares only the fists_* names with dc_monk.cpp's reads.
        text = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.assertFalse({n for n in re.findall(r'Tune\("([a-z0-9_]+)"\)', text) if n.startswith("lashing")})

    def test_every_name_the_code_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'(?:Tune|Has\("monk",)\s*\(?"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {"lashing_tail_kick_cone_degrees", "lashing_tail_kick_column_yards",
                                         "lashing_tail_kick_column_width_yards", "lashing_tail_kick_dot_tick_seconds"})
        for name in read_tunables:
            self.assertIn(name, tunables())
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|rune), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertGreaterEqual(len(tokens), 6)

    def test_the_power_file_and_the_sheet_agree_on_the_durations(self):
        # Power/Monk_LashingTailKick.pow (decoded, read-only): SF_27 A DoT Duration 3, SF_21 C Slow Duration 3,
        # SF_18 C Slow Amount 0.80, SF_8 E Stun Duration 2, SF_9 / SF_13 the A and D radii, SF_26 the DoT scalar 2.3,
        # SF_20 base 7.55. The decode is not in the repo; the figures are pinned here from it.
        self.assertEqual(value("Vulture Claw Kick", "dot_duration_seconds"), 3)
        self.assertEqual(value("Hand of Ytar", "slow_duration_seconds"), 3)
        self.assertEqual(value("Hand of Ytar", "slow_pct") / 100, 0.80)
        self.assertEqual(value("Scorpion Sting", "stun_duration_seconds"), 2)
        self.assertEqual((value("Vulture Claw Kick", "radius_yards"), value("Sweeping Armada", "radius_yards")), (10, 15))
        self.assertEqual(value("Vulture Claw Kick", "damage_pct", "dot") / 100, 2.3)
        self.assertEqual(value("", "damage_pct") / 100, 7.55)
        self.assertEqual(round(value("Sweeping Armada", "damage_pct") / value("", "damage_pct"), 6), 1.092715)

    def test_the_stock_carriers_are_the_auras_they_are_used_for(self):
        text = CODE.read_text(encoding="utf-8")
        carriers = {name: int(number) for name, number in re.findall(r"constexpr std::uint32_t (\w+) = (\d+);", text)}
        self.assertEqual(carriers, {"Slowed": 50259, "Stunned": 56})
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
        for name, spell, aura in (("Slowed", 50259, 33), ("Stunned", 56, 12)):
            fields_of = rows[spell]
            used = [(effect, auras) for effect, auras in zip(fields_of[71:74], fields_of[95:98]) if effect]
            self.assertEqual(used, [(6, aura)], f"{name} ({spell}) is one apply-aura effect of aura {aura}")


if __name__ == "__main__":
    unittest.main()

"""diablocraft-348cz (Monk 2.3.10): Sweeping Wind and its five runes.

What this proves, and how:

  * **The logic that needs no core type.** tests/monk_sweeping_wind/harness.cpp compiles the real dc_monk_sweeping_wind.h and
    feeds it the sheets' and the tunables' numbers: a second of the vortex at full stacks deals the sheet's 315%, the
    stacks stop at the maximum, the stacks come from a Spirit Generator's attacks and the tornado from one at full stacks, a tornado's arcs, Inner Storm's
    Spirit once a whole second, and Master of Wind's run of consecutive damage (the tick that completes it, a gap that
    breaks it, the cooldown on the next freeze). Ten mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_monk_sweeping_wind.cpp reads by name is a row of
    monk_skill_values.csv for Sweeping Wind (or for the rune that states it), every tunable it reads is a row of
    data/tunables/monk.csv, with the numbers the research and the power file give: 75 Spirit, 105% a stack and 315% at
    3 stacks over 10 yards for 6 seconds, Blade Storm 145% and 435%, Fire Storm 14 yards, Cyclone's 95% for 3 seconds from
    3 stacks, Inner Storm's 8 Spirit a second, Master of Wind's 3 consecutive seconds, 2 second freeze and 3 second
    cooldown. The power file agrees with the sheet on every duration (SF_7 6, SF_21 3, SF_26 3, SF_27 2), so no sheet row
    changes. The stock freeze carrier exists in Spell.dbc with the one aura it is used for.
  * **The wiring.** dc_monk.cpp hands a Sweeping Wind spell to Wind::BasePct / Cast, every landed hit to Wind::Landed, and Monk::Connected tells
    Wind::Attack of every attack of a Spirit Generator.

What it does not prove: anything on a running server. The vortex, the stacks, the tornado, the Spirit and the freeze need the
Monk's records (3mk78) and are docs/test-diablocraft-348cz.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_sweeping_wind.py
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
SOURCES = ["src/classes/monk/dc_monk_sweeping_wind.h", "tests/monk_sweeping_wind/harness.cpp"]
SKILL = "Sweeping Wind"
CODE = MODULE / "src/classes/monk/dc_monk_sweeping_wind.cpp"
HEADER = "src/classes/monk/dc_monk_sweeping_wind.h"


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
    binary = harness_env.build([MODULE / "tests/monk_sweeping_wind/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_pct", "base"), value("", "damage_pct", "max"), value("", "max_stacks_count"),
               tune("sweeping_wind_tick_seconds"),
               value("Cyclone", "duration_seconds"), tune("sweeping_wind_tornado_tick_seconds"),
               value("Master of Wind", "duration_seconds"), value("Master of Wind", "internal_cooldown_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the stacks do not count", (HEADER, "return perStackPct * stacks * tickSeconds;",
                                         "return perStackPct * tickSeconds;")),
            ("a tick pays a whole second", (HEADER, "return perStackPct * stacks * tickSeconds;",
                                            "return perStackPct * stacks;")),
            ("the stacks have no maximum", (HEADER, "return generates ? std::min(stacks + 1, maxStacks) : stacks;",
                                           "return generates ? stacks + 1 : stacks;")),
            ("any attack adds a stack", (HEADER, "return generates ? std::min(stacks + 1, maxStacks) : stacks;",
                                         "return std::min(stacks + 1, maxStacks);")),
            ("the tornado below the maximum", (HEADER, "return generates && stacks >= maxStacks;", "return generates;")),
            ("the tornado from any attack", (HEADER, "return generates && stacks >= maxStacks;", "return stacks >= maxStacks;")),
            ("Spirit paid every tick", (HEADER, "return std::floor(index * tickSeconds + 1e-9) > std::floor((index - 1) * tickSeconds + 1e-9);",
                                        "return true;")),
            ("a gap does not break the run", (HEADER, "if (since == 0 || now > last + tickMs + tickMs / 2)", "if (since == 0)")),
            ("no cooldown on the freeze", (HEADER, "if (frozen != 0 && now < frozen + icdMs)", "if (false)")),
            ("the run is a tick short", (HEADER, "if (now - since + tickMs < needMs)", "if (now - since < needMs)")),
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
        self.assertEqual([value("", token) for token in ("cost_resource", "radius_yards", "duration_seconds", "max_stacks_count")],
                         [75, 10, 6, 3])
        self.assertEqual((value("", "damage_pct", "base"), value("", "damage_pct", "max")), (105, 315))
        self.assertEqual(value("", "damage_pct", "base") * value("", "max_stacks_count"), value("", "damage_pct", "max"))
        self.assertEqual((value("Blade Storm", "damage_pct", "base"), value("Blade Storm", "damage_pct", "max")), (145, 435))
        self.assertEqual(value("Fire Storm", "radius_yards"), 14)
        self.assertEqual((value("Cyclone", "stack_threshold_count"), value("Cyclone", "damage_pct"),
                          value("Cyclone", "duration_seconds")), (3, 95, 3))
        self.assertEqual((value("Inner Storm", "stack_threshold_count"), value("Inner Storm", "regen_per_second_resource")), (3, 8))
        wind = "Master of Wind"
        self.assertEqual([value(wind, t) for t in ("stack_threshold_count", "duration_seconds", "freeze_duration_seconds",
                                                  "internal_cooldown_seconds")], [3, 3, 2, 3])

    def test_the_power_file_and_the_sheet_agree_on_the_durations(self):
        # Power/Monk_SweepingWind.pow (decoded, read-only): SF_7 vortex duration 6, SF_21 tornado duration 3, SF_26
        # consecutive seconds until freeze 3, SF_27 freeze duration 2, SF_10 max stacks 3, SF_12 radius 10, SF_19 Fire
        # Storm +4, SF_5 1.05 and SF_14 Blade Storm 1.38095 (1.45), SF_23 Inner Storm 8, SF_29 Cyclone 0.95.
        self.assertEqual(value("", "duration_seconds"), 6)
        self.assertEqual(value("Cyclone", "duration_seconds"), 3)
        self.assertEqual(value("Master of Wind", "duration_seconds"), 3)
        self.assertEqual(value("Master of Wind", "freeze_duration_seconds"), 2)
        self.assertEqual(value("Fire Storm", "radius_yards"), value("", "radius_yards") + 4)
        self.assertEqual(round(value("Blade Storm", "damage_pct", "base") / value("", "damage_pct", "base"), 6), 1.380952)
        self.assertEqual(value("Cyclone", "damage_pct") / 100, 0.95)

    def test_the_tunables(self):
        tuned = tunables()
        for name, number, source in (("sweeping_wind_tick_seconds", 0.25, "SF_11"),
                                     ("sweeping_wind_tornado_tick_seconds", 0.6, "SF_28"),
                                     ("sweeping_wind_tornado_seek_yards", 30, "SF_30"), ("sweeping_wind_tornado_arcs", 1, "SF_32")):
            self.assertEqual(tune(name), number, name)
            self.assertEqual(tuned[name]["value"], "", name)
            self.assertIn(source, tuned[name]["notes"], name)

    def test_the_tunables_are_not_fists_tunables(self):
        text = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.assertFalse({n for n in re.findall(r'Tune\("([a-z0-9_]+)"\)', text) if n.startswith("sweeping")})

    def test_every_name_the_code_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {"sweeping_wind_tick_seconds",
                                         "sweeping_wind_tornado_tick_seconds", "sweeping_wind_tornado_seek_yards",
                                         "sweeping_wind_tornado_arcs"})
        for name in read_tunables:
            self.assertIn(name, tunables())
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\((?:spellId|landing|rune)(?:, "([a-z_]+)")', text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertGreaterEqual(len(tokens), 8)

    def test_the_vortex_duration_is_what_the_rune_inherits(self):
        # Cyclone's and Master of Wind's own duration_seconds (3) is the tornado's and the run of damage, not the vortex's 6.
        self.assertIn('Numbers::Inherited(spellId, "duration_seconds")', CODE.read_text(encoding="utf-8"))

    def test_the_stock_carrier_is_the_aura_it_is_used_for(self):
        text = CODE.read_text(encoding="utf-8")
        carriers = {name: int(number) for name, number in re.findall(r"constexpr std::uint32_t (\w+) = (\d+);", text)}
        self.assertEqual(carriers, {"FreezeHold": 15878})
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
        fields_of = rows[15878]
        used = [(effect, auras) for effect, auras in zip(fields_of[71:74], fields_of[95:98]) if effect]
        self.assertEqual(used, [(6, 12)], "Ice Blast (15878) is one apply-aura effect of MOD_STUN")


if __name__ == "__main__":
    unittest.main()

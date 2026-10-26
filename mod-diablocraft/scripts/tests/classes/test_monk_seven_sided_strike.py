"""diablocraft-7kbmf (Monk 2.3.12): Seven-Sided Strike and its five runes.

What this proves, and how:

  * **The strikes.** tests/monk_seven_sided_strike/harness.cpp compiles the real dc_monk_seven_sided_strike.h and feeds
    it the sheets' own numbers (5677% and Sudden Assault's 8285% over 7 strikes from monk_skill_values.csv, the first
    strike and the interval from data/tunables/monk.csv, Incinerate's 630% over 3 s): a strike is a seventh (811%, the
    power file's SF_3), the strikes land at 0.1 s then 0.15 s apart, one enemy takes all seven, three take them in turn,
    a fallen one is passed over, and the burn is built only with a tick length. Five mutations planted in a scratch copy
    must each make it fail.
  * **The code reads what the sheets state.** Every number dc_monk_seven_sided_strike.cpp reads by name is a row of
    monk_skill_values.csv for the skill (or a rune of it) or of data/tunables/monk.csv; the tunables carry the power
    file's numbers, and the burn's tick is blank (a question on the bead).
  * **The wiring.** The cast path asks Monk::Delayed after the aim resolves and before Monk::Begin, and returns when it
    takes the cast; dc_monk.cpp hands Seven-Sided Strike to its file for the loader's percentage and the cast; the
    skill's name is in no code outside src/classes/monk/.

What it does not prove: anything on a running server. The dash, the teleport, the freeze and the cooldown that starts
again after the strikes are docs/test-diablocraft-7kbmf.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_seven_sided_strike.py
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
HEADER = "src/classes/monk/dc_monk_seven_sided_strike.h"
SOURCE = "src/classes/monk/dc_monk_seven_sided_strike.cpp"
SOURCES = [HEADER, "tests/monk_seven_sided_strike/harness.cpp"]
SKILL = "Seven-Sided Strike"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def values():
    return read(D3 / "monk_skill_values.csv")


def value(rune, token, qualifier=""):
    rows = [r for r in values()
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
    binary = harness_env.build([MODULE / "tests/monk_seven_sided_strike/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_pct"), value("Sudden Assault", "damage_pct"), value("", "hit_count"),
               tune("seven_sided_strike_first_strike_seconds"), tune("seven_sided_strike_interval_seconds"),
               value("Incinerate", "damage_pct"), value("Incinerate", "dot_duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_strikes_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the total is not split", (HEADER, "totalPct / std::floor(strikes)", "totalPct")),
            ("the interval is not added", (HEADER, "+ i * std::max(0.0, intervalMs)", "")),
            ("the list does not wrap", (HEADER, "% n;", ";\n            if (i >= n)\n                return -1;")),
            ("a fallen enemy is struck", (HEADER, "if (standing[i])", "if (true)")),
            ("a part tick counts", (HEADER, "std::floor(seconds / tickSeconds + 1e-9)", "std::ceil(seconds / tickSeconds)")),
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
        self.assertEqual([value("", t) for t in ("cost_resource", "cooldown_seconds", "damage_pct", "hit_count")],
                         [50, 30, 5677, 7])
        self.assertEqual(value("Sudden Assault", "damage_pct"), 8285)
        self.assertEqual((value("Incinerate", "damage_pct"), value("Incinerate", "dot_duration_seconds")), (630, 3))
        self.assertEqual(value("Pandemonium", "freeze_duration_seconds"), 7)
        self.assertEqual(value("Sustained Attack", "cooldown_seconds"), 14)
        self.assertEqual((value("Fulminating Onslaught", "damage_pct"), value("Fulminating Onslaught", "radius_yards")),
                         (877, 7))

    def test_the_tunables_are_the_power_files(self):
        self.assertEqual(tune("seven_sided_strike_first_strike_seconds"), 0.1)
        self.assertEqual(tune("seven_sided_strike_interval_seconds"), 0.15)
        self.assertEqual(tune("seven_sided_strike_teleport_yards"), 50)
        burn = tunables()["seven_sided_strike_burn_tick_seconds"]
        self.assertEqual((burn["d3_value"], burn["value"]), ("", "1"), "no D3 number: the PM default, 1 s")
        self.assertIn("docs/decisions.md 2026-10-14", burn["notes"])
        for name in ("seven_sided_strike_first_strike_seconds", "seven_sided_strike_interval_seconds",
                     "seven_sided_strike_teleport_yards", "seven_sided_strike_burn_tick_seconds"):
            self.assertIn("Monk_SevenSidedStrike.pow", tunables()[name]["notes"], name)

    def test_the_search_radius_is_the_sheets(self):
        rows = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["target_type"], rows[0]["radius_yards"]), ("self_aoe", "25"))

    def test_every_name_the_code_reads_exists(self):
        text = (MODULE / SOURCE).read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("seven_sided_strike_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|id|source), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in values() if r["skill"] == SKILL}
        self.assertTrue(tokens)
        self.assertEqual(tokens - sheet_tokens, set())

    def test_the_rune_names_the_code_asks_for_are_the_sheets(self):
        text = (MODULE / SOURCE).read_text(encoding="utf-8")
        asked = set(re.findall(r'IsRune\((?:spellId|id), "([^"]+)"\)', text))
        runes = {r["rune_name"] for r in read(D3 / "monk_runes.csv") if r["skill_name"] == SKILL}
        self.assertEqual(asked - runes, set())
        self.assertEqual(asked, runes - {"Sustained Attack"},
                         "every rune but Sustained Attack (its cooldown is the record's) has code")


if __name__ == "__main__":
    unittest.main()

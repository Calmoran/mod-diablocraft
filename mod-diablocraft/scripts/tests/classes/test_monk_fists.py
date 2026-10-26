"""diablocraft-1tiy2 (Monk 2.3.01): Fists of Thunder and its five runes.

What this proves, and how:

  * **The combo and the share.** tests/monk_fists/harness.cpp compiles the real dc_monk_fists.h and feeds it the
    sheets' own numbers (the window from data/tunables/monk.csv, the hit and third-hit percentages from
    monk_skill_values.csv): the stages count 1, 2, 3 and start again, a punch a second keeps counting, a pause past the
    window starts again, the third hit's 400% is shared by the enemies it strikes. Four mutations planted in a scratch
    copy (the window never ends the combo, the third punch does not end it, the share is not divided, the window frames
    are not rounded up) must each make it fail.
  * **The code reads what the sheets state.** Every number dc_monk.cpp reads by name is a row of monk_skill_values.csv
    for that very rune (or its skill, which a rune inherits) or of data/tunables/monk.csv, with the value the research
    gives: 200% a punch and 400% the third, Thunderclap's 120% over 6 yards, Bounding Light's 240% to 3, Static Charge's 6 s,
    40 yards and 40% with its 0.427 / 0.308 proc coefficients, Wind Blast's 2 s, Quickening's 20 Spirit; the window
    72 frames at 60 a second, the third hit's sphere of 6 yards, the knockback 3, the arcs' search 18. The stage-3 cone
    tunable is gone (docs/research/monk/fists-of-thunder-rules.md section 6.2: a sphere centred on the primary).
  * **The wiring.** The cast path asks Monk::Begin before the hits, shares the primary's hit through the stage's
    percentage, calls Monk::Cast after the Wizard's and Monk::Landed from both hit paths; the loader asks Monk::BasePct.

What it does not prove: anything on a running server. The punches, the knockback, the freeze, the arcs and Static
Charge's follow-up hit need the Monk's records (3mk78) and are docs/test-diablocraft-1tiy2.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_fists.py
"""

import csv
import re
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
SOURCES = ["src/classes/monk/dc_monk_fists.h", "tests/monk_fists/harness.cpp"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def values():
    return read(D3 / "monk_skill_values.csv")


def value(skill, rune, token, qualifier=""):
    rows = [r for r in values()
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, token, qualifier)]
    assert len(rows) == 1, (skill, rune, token, qualifier, len(rows))
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
    binary = harness_env.build([MODULE / "tests/monk_fists/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("fists_combo_window_frames"), tune("fists_combo_frames_per_second"),
               value("Fists of Thunder", "", "damage_pct", "hit"),
               value("Fists of Thunder", "", "damage_pct", "third_hit")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_combo_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        path = "src/classes/monk/dc_monk_fists.h"
        mutations = [
            ("the window never ends the combo", (path, "if (now > expires)\n                count = 0;", "")),
            ("the third punch does not end the combo", (path, "            else\n                count = 0;", "")),
            ("the share is not divided", (path, "return enemies ? totalPct / enemies : 0.0;", "return totalPct;")),
            ("the frames are not rounded up", (path, "std::ceil(frames / attacksPerSecond)", "(frames / attacksPerSecond)")),
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
        fists = "Fists of Thunder"
        self.assertEqual(value(fists, "", "damage_pct", "hit"), 200)
        self.assertEqual(value(fists, "", "damage_pct", "third_hit"), 400)
        self.assertEqual(value(fists, "", "generated_resource"), 14)
        self.assertEqual(value(fists, "Quickening", "generated_resource"), 20)
        self.assertEqual((value(fists, "Thunderclap", "damage_pct"), value(fists, "Thunderclap", "radius_yards")), (120, 6))
        self.assertEqual((value(fists, "Bounding Light", "damage_pct"), value(fists, "Bounding Light", "target_count")),
                         (240, 3))
        self.assertEqual([value(fists, "Static Charge", token) for token in ("duration_seconds", "radius_yards", "damage_pct")],
                         [6, 40, 40])
        self.assertEqual((value(fists, "Static Charge", "proc_coefficient", "hit"),
                          value(fists, "Static Charge", "proc_coefficient", "third_hit")), (0.427, 0.308))
        self.assertEqual(value(fists, "Wind Blast", "freeze_duration_seconds"), 2)

    def test_the_tunables_are_the_researched_ones(self):
        self.assertEqual(tune("fists_combo_window_frames"), 72)
        self.assertEqual(tune("fists_combo_frames_per_second"), 60)
        self.assertEqual(tune("fists_stage3_radius_yards"), 6)
        self.assertEqual(tune("fists_knockback_yards"), 3)
        self.assertEqual(tune("fists_arc_search_radius_yards"), 18)
        self.assertNotIn("fists_stage3_cone_degrees", tunables())
        for name, row in tunables().items():
            self.assertTrue(row["notes"].strip(), name)

    def test_every_name_the_code_reads_exists(self):
        text = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("fists_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|rune), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in values() if r["skill"] == "Fists of Thunder"}
        self.assertEqual(tokens - sheet_tokens, set())

    def test_the_proc_coefficient_rows_have_a_source_that_says_where(self):
        rows = [r for r in values() if r["token"] == "proc_coefficient" and r["skill"] == "Fists of Thunder"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIn("monk.js:105-114", row["source"])
            self.assertIn("721216-721218", row["source"])


if __name__ == "__main__":
    unittest.main()

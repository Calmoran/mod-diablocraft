"""diablocraft-91siy (Monk 2.3.09): Exploding Palm and its five runes.

What this proves, and how:

  * **The rules that need no core type.** tests/monk_exploding_palm/harness.cpp compiles the real dc_monk_exploding_palm.h
    with the sheets' numbers: the bleed's ticks add up to its total at any attack speed, a palm is on an enemy for its
    seconds and is taken once when the enemy dies (only the palms that still last, each Monk's and each rune's own), a new
    run replaces the old one, Shocking Grasp picks the nearest enemy within its radius. Eight mutations planted in a
    scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every number dc_monk_exploding_palm.cpp reads by name is a row of
    monk_skill_values.csv for that rune (or the skill, which a rune inherits) or a tunable of data/tunables/monk.csv with
    the power file's value: 1200% over 9 seconds, 2770% explosion, 6305% for Impending Doom, 15% more damage taken for 9
    seconds, 15 Spirit a head, Essence Burn's 1875% and 3260% over 9 and 3 seconds, the arc of 15 yards, the explosion's 15
    yards and the burn's 0.25 s tick.
  * **The wiring.** dc_monk.cpp hands the skill's spell ids to its own file in BasePct and Cast and registers the death
    script; dc_combat.cpp calls Monk::RegisterScripts beside the Wizard's.

What it does not prove: anything on a running server. The bleed, the explosion on death, the Spirit and the arc need the
Monk's records (3mk78) and are docs/test-diablocraft-91siy.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_exploding_palm.py
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
SOURCES = ["src/classes/monk/dc_monk_exploding_palm.h", "tests/monk_exploding_palm/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_exploding_palm.h"
SKILL = "Exploding Palm"


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
    binary = harness_env.build([MODULE / "tests/monk_exploding_palm/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_pct", "dot"), value("", "dot_duration_seconds"),
               value("Essence Burn", "damage_pct", "explosion"), value("Essence Burn", "dot_duration_seconds", "explosion"),
               tune("exploding_palm_burn_tick_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 30, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a palm that ran out still explodes", (HEADER, "if (now < at->second.untilMs)", "if (true)")),
            ("a palm lasts one tick too long", (HEADER, "found->second.spellId == spellId && now < found->second.untilMs",
                                                "found->second.spellId == spellId && now <= found->second.untilMs")),
            ("the death leaves the palms on", (HEADER, "at = marks_.erase(at);", "++at;")),
            ("Monks share a palm", (HEADER, "marks_[{enemy, caster}] =", "marks_[{enemy, 0}] =")),
            ("a tick is the whole bleed", (HEADER, "return ticks ? totalPct / ticks : 0.0;", "return ticks ? totalPct : 0.0;")),
            ("a partial tick is paid", (HEADER, "std::floor(seconds * perSecond + 1e-9)", "std::ceil(seconds * perSecond)")),
            ("an old run keeps ticking", (HEADER, "return found != stamps_.end() && found->second == stamp;",
                                          "return found != stamps_.end();")),
            ("the arc picks the farthest", (HEADER, "distancesSquared[i] < distancesSquared[best]",
                                            "distancesSquared[i] > distancesSquared[best]")),
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
        self.assertEqual((value("", "damage_pct", "dot"), value("", "dot_duration_seconds"), value("", "damage_pct", "explosion")),
                         (1200, 9, 2770))
        self.assertEqual(value("", "cost_resource"), 40)
        self.assertEqual(value("Shocking Grasp", "radius_yards"), 15)
        self.assertEqual(value("Impending Doom", "damage_pct"), 6305)
        self.assertEqual((value("The Flesh is Weak", "damage_taken_pct"), value("The Flesh is Weak", "duration_seconds")), (15, 9))
        self.assertEqual(value("Strong Spirit", "gain_resource"), 15)
        self.assertEqual((value("Essence Burn", "damage_pct", "dot"), value("Essence Burn", "dot_duration_seconds", "dot")),
                         (1875, 9))
        self.assertEqual((value("Essence Burn", "damage_pct", "explosion"),
                          value("Essence Burn", "dot_duration_seconds", "explosion")), (3260, 3))

    def test_the_tunables_are_the_power_files(self):
        self.assertEqual(tune("exploding_palm_explosion_radius_yards"), 15)
        row = next(r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual(float(row["radius_yards"]), tune("exploding_palm_explosion_radius_yards"))
        self.assertEqual(tune("exploding_palm_burn_tick_seconds"), 0.25)

    def test_every_name_the_code_reads_exists(self):
        text = (MODULE / "src/classes/monk/dc_monk_exploding_palm.cpp").read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("exploding_palm_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|rune), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "dot_duration_seconds", "damage_taken_pct", "duration_seconds",
                                  "gain_resource", "radius_yards"})


if __name__ == "__main__":
    unittest.main()

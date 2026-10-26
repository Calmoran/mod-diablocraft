"""diablocraft-cvm3v (Monk 2.3.02): Deadly Reach and its five runes.

What this proves, and how:

  * **The rules that need no core type.** tests/monk_deadly_reach/harness.cpp compiles the real dc_monk_deadly_reach.h with the
    tunables' own numbers: the third hit's longer line (the enemies between the cast's 12 yards and the 25 it reaches, inside
    the 4-yard width, in the direction faced, none behind or beside), Scattered Blows' fists on random enemies, Strike from
    Beyond's pending discount (per enemy, capped at the whole cost, spent by one spender) and the Spirit paid back. Eight
    mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every number dc_monk_deadly_reach.cpp reads by name is a row of
    monk_skill_values.csv for that very rune (or the skill, which a rune inherits) or a tunable of data/tunables/monk.csv, with
    the value the sheets give: 150% a punch, a 50% knock-up chance (100% with Piercing Trident), 12 Spirit, Foresight's 15% for
    5 seconds, Scattered Blows' 215% over 25 yards, Strike from Beyond's 8%, Searing Grasp's 260%; the line 12, the reach 25 and
    the width 4 equal skill_targeting.csv's row and the power file's.
  * **The wiring.** dc_monk.cpp hands Deadly Reach's spell ids to its own file in BasePct, Begin and Cast and tells it of every
    cast so the discount is paid back; the knock-up is the stock knockback record the Pylons' Speed knock-up uses.

What it does not prove: anything on a running server. The line, the knock-up, Foresight's buff, the fists and the discount need
the Monk's records (3mk78) and are docs/test-diablocraft-cvm3v.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_deadly_reach.py
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
SOURCES = ["src/classes/monk/dc_monk_deadly_reach.h", "tests/monk_deadly_reach/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_deadly_reach.h"
SKILL = "Deadly Reach"


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
    binary = harness_env.build([MODULE / "tests/monk_deadly_reach/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("deadly_reach_line_yards"), tune("deadly_reach_stage3_reach_yards"), tune("deadly_reach_width_yards"),
               tune("deadly_reach_scattered_fists"), value("Strike from Beyond", "cost_reduction_pct"),
               tune("deadly_reach_piercing_trident_area_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 32, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the width is not halved", (HEADER, "across <= width / 2.0", "across <= width")),
            ("the extras start at the Monk", (HEADER, "along >= from &&", "along >= 0 &&")),
            ("the line has no far end", (HEADER, "along >= from && along <= to && across", "along >= from && across")),
            ("a pick past the end is not held", (HEADER, "std::min(enemies - 1, static_cast<std::size_t>(pick(enemies)))",
                                                 "static_cast<std::size_t>(pick(enemies))")),
            ("no enemy still throws fists", (HEADER, "if (!enemies)\n            return out;", "")),
            ("the discount is not capped", (HEADER, "pct = std::min(100.0, pct + std::max(0.0, more));",
                                            "pct = pct + std::max(0.0, more);")),
            ("the spender does not spend it", (HEADER, "pct = 0;\n            return taken;", "return taken;")),
            ("the refund is not capped", (HEADER, "std::min(100.0, pct)", "pct")),
            ("Trident widens nothing", (HEADER, "width * (1.0 + areaPct / 100.0)", "width")),
            ("Trident widens the first hit too", (HEADER, "trident && stage >= 2 &&", "trident && stage >= 1 &&")),
            ("every rune widens", (HEADER, "return trident && stage >= 2 &&", "return stage >= 2 &&")),
            ("a negative percent narrows", (HEADER, "areaPct > 0 ? width", "true ? width")),
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
        self.assertEqual((value("", "damage_pct"), value("", "proc_chance_pct"), value("", "generated_resource")), (150, 50, 12))
        self.assertEqual(value("Piercing Trident", "proc_chance_pct"), 100)
        self.assertEqual((value("Foresight", "damage_bonus_pct"), value("Foresight", "duration_seconds")), (15, 5))
        self.assertEqual((value("Scattered Blows", "damage_pct"), value("Scattered Blows", "radius_yards")), (215, 25))
        self.assertEqual(value("Strike from Beyond", "cost_reduction_pct"), 8)
        self.assertEqual(value("Searing Grasp", "damage_pct"), 260)

    def test_the_line_the_reach_and_the_width_are_the_targeting_rows_and_the_power_files(self):
        row = next(r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual(row["target_type"], "line_pierce")
        self.assertEqual(tune("deadly_reach_line_yards"), float(row["range_yards"]))
        self.assertEqual(tune("deadly_reach_width_yards"), float(row["width_yards"]))
        self.assertEqual(tune("deadly_reach_line_yards"), 12)
        self.assertEqual(tune("deadly_reach_stage3_reach_yards"), 25)
        self.assertEqual(tune("deadly_reach_width_yards"), 4)
        self.assertEqual(tune("deadly_reach_scattered_fists"), 6)

    def test_every_name_the_code_reads_exists(self):
        text = (MODULE / "src/classes/monk/dc_monk_deadly_reach.cpp").read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("deadly_reach_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|SkillId\(\)), "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "proc_chance_pct", "damage_bonus_pct", "duration_seconds",
                                  "cost_reduction_pct", "radius_yards"})


if __name__ == "__main__":
    unittest.main()

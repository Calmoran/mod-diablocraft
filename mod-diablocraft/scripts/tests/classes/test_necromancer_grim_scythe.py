"""Grim Scythe and its five runes (src/classes/necromancer/dc_necromancer_grim_scythe*.h/.cpp, dc_necromancer_buffs.*, the
per-enemy Essence in dc_necromancer.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_grim_scythe/harness.cpp compiles the real
    dc_necromancer_grim_scythe_math.h and dc_necromancer_buffs.h with the sheets' own rune names and numbers: each rune name
    is its rune; the Essence is paid for each enemy hit; Blood Scythe heals a share of maximum Life for each enemy;
    Execution kills only below the threshold and only for a roll under the chance; Frost Scythe's stacks come one for each
    enemy, stop at the cap, restart the whole time and end on the moment; Dual Scythes draws an enemy to the line the
    Necromancer faces, never behind it. Planted differences in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_grim_scythe.cpp reads by name is a row of
    necromancer_skill_values.csv for Grim Scythe (or the rune that states it), the generated value map says whose record
    holds it, and the numbers are the researched ones: 150% on the cone, 12 Essence per enemy, Blood Scythe 1% of Life,
    Execution 5% below 20% health, Frost Scythe 1% attack speed for 5 seconds up to 15 stacks, Dual Scythes 150% and 12
    Essence, Cursed Scythe 15%. No tunable: the skill needs none.
  * **The wiring.** The dispatch gives Grim Scythe its Cast and pays the Essence per enemy for the skills whose tooltip says
    "per enemy hit" (read from the sheet) and once for the rest.

What it does not prove: anything on a running server. Cursed Scythe's curse waits for the Curses category and is not built.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_grim_scythe.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
MATH = "src/classes/necromancer/dc_necromancer_grim_scythe_math.h"
BUFFS = "src/classes/necromancer/dc_necromancer_buffs.h"
HARNESS = MODULE / "tests/necromancer_grim_scythe/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_grim_scythe.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Grim Scythe"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token):
    rows = [r for r in read(D3 / "necromancer_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, "")]
    assert len(rows) == 1, (rune, token, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "necromancer_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (MATH, BUFFS)}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "generated_resource"), value("Blood Scythe", "heal_pct"), value("Execution", "life_threshold_pct"),
               value("Execution", "proc_chance_pct"), value("Frost Scythe", "attack_speed_pct"),
               value("Frost Scythe", "duration_seconds"), value("Frost Scythe", "max_stacks_count")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 28, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (MATH, 'if (name == "Frost Scythe")\n            return Rune::FrostScythe;', 'if (name == "Frost Scythe")\n            return Rune::Execution;')),
            ("the Essence is paid once", (MATH, "perEnemy * enemies", "perEnemy")),
            ("no enemy still pays", (MATH, "return perEnemy > 0 ? perEnemy * enemies : 0.0;", "return perEnemy * std::max(1u, enemies);")),
            ("a negative Essence is paid", (MATH, "perEnemy > 0 ?", "perEnemy != 0 ?")),
            ("the heal is a share of the wrong thing", (MATH, "maxLife * healPct / 100.0 * enemies", "maxLife * healPct / 100.0")),
            ("the heal is not a percent", (MATH, "maxLife * healPct / 100.0 * enemies", "maxLife * healPct * enemies")),
            ("an enemy at the threshold dies", (MATH, "lifePct < thresholdPct", "lifePct <= thresholdPct")),
            ("a healthy enemy dies", (MATH, "lifePct < thresholdPct", "lifePct > -1")),
            ("a roll at the chance kills", (MATH, "roll < chancePct", "roll <= chancePct")),
            ("every roll kills", (MATH, "&& roll < chancePct", "")),
            ("a stack is lost to a second enemy", (BUFFS, "held.stacks + std::max(1u, adds)", "held.stacks + 1")),
            ("stacks have no cap", (BUFFS, "std::max(1u, maxStacks));", "1000u);")),
            ("a cast does not restart the time", (BUFFS, "held.until = now + ms;", "held.until = held.until ? held.until : now + ms;")),
            ("the time ends a moment late", (BUFFS, "return held.until <= now;", "return held.until < now;")),
            ("a buff that ran out keeps its stacks", (BUFFS, "if (held.until <= now)\n            held.stacks = 0;", "")),
            ("the sheet keeps an ended buff", (BUFFS, "return Over(held, now) ? 0.0 : perStack * held.stacks;", "return perStack * held.stacks;")),
            ("the speed is not per stack", (BUFFS, "perStack * held.stacks", "perStack")),
            ("the push goes behind", (MATH, "return std::max(0.0, (ex - px) * fx + (ey - py) * fy);", "return (ex - px) * fx + (ey - py) * fy;")),
            ("the push ignores the facing", (MATH, "(ex - px) * fx + (ey - py) * fy", "(ex - px) + (ey - py)")),
            ("the push is level with the world", (MATH, "(ex - px) * fx + (ey - py) * fy", "(ex) * fx + (ey) * fy")),
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
        self.assertEqual(runes(), ["Blood Scythe", "Execution", "Frost Scythe", "Dual Scythes", "Cursed Scythe"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "generated_resource"), value("", "damage_pct")], [12, 150])
        self.assertEqual(value("Blood Scythe", "heal_pct"), 1)
        self.assertEqual([value("Execution", t) for t in ("life_threshold_pct", "proc_chance_pct")], [20, 5])
        self.assertEqual([value("Frost Scythe", t) for t in ("attack_speed_pct", "duration_seconds", "max_stacks_count")], [1, 5, 15])
        self.assertEqual([value("Dual Scythes", t) for t in ("generated_resource", "damage_pct")], [12, 150])
        self.assertEqual(value("Cursed Scythe", "proc_chance_pct"), 15)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"heal_pct", "life_threshold_pct", "proc_chance_pct", "attack_speed_pct", "max_stacks_count",
                                  "duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "generated_resource"), ("", "damage_pct"), ("Blood Scythe", "heal_pct"),
                            ("Execution", "life_threshold_pct"), ("Execution", "proc_chance_pct"),
                            ("Frost Scythe", "attack_speed_pct"), ("Frost Scythe", "duration_seconds"),
                            ("Frost Scythe", "max_stacks_count"), ("Dual Scythes", "generated_resource"),
                            ("Dual Scythes", "damage_pct"), ("Cursed Scythe", "proc_chance_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)

    def test_the_skills_that_pay_per_enemy_are_the_ones_the_tooltip_says(self):
        says = {r["skill_name"] for r in read(D3 / "necromancer_skills.csv") if "Essence per enemy hit" in r["full_tooltip_text"]}
        text = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))
        listed = re.search(r"PaysPerEnemy = \{([^}]*)\}", text)[1]
        self.assertEqual(set(re.findall(r'"([^"]+)"', listed)), says)
        self.assertEqual(says, {SKILL})


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))

    def test_the_dispatch_gives_the_cast_and_pays_per_enemy(self):
        self.assertIn("GrimScythe::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("GrimScythe::EssenceOfHits(*points, enemies) : *points", self.dispatch)
        self.assertIn("Generate(player, spellId, enemies);", self.dispatch)

    def test_each_rune_does_its_one_thing(self):
        self.assertIn('Heal(player, spellId, HealOfHits(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), enemies));', self.code)
        self.assertIn("Unit::Kill(player, enemy);", self.code)
        self.assertIn("Buffs::Stack(player, spellId, Stat::AttackSpeed, Bucket::Flat", self.code)
        self.assertIn("Abilities::Pull(enemy, Level(player, enemy));", self.code)

    def test_execution_rolls_for_each_enemy_struck_and_never_for_the_dead(self):
        self.assertIn("if (enemy->IsAlive() && Decapitated(enemy->GetHealthPct(),", self.code)

    def test_frost_scythe_gives_a_stack_for_each_enemy(self):
        self.assertIn('Numbers::Num(spellId, "duration_seconds"), enemies);', self.code)


if __name__ == "__main__":
    unittest.main()

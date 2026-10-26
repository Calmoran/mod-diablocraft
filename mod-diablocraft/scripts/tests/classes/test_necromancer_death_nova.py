"""Death Nova and its five runes (src/classes/necromancer/dc_necromancer_death_nova*.h/.cpp, the dispatch in
dc_necromancer.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_death_nova/harness.cpp compiles the real
    dc_necromancer_death_nova_math.h with the sheets' own rune names and numbers: each rune name is its rune; Bone Nova and
    Unstable Compound are the runes that strike for themselves; Unstable Compound's radius grows with each cast in a row and
    stops at the cap, from the rune's own 20 yards; Tendril Nova heals a share of maximum Life for each enemy; Blight's patch is whole pulses of its time.
    Planted differences in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_death_nova.cpp reads by name is a row of
    necromancer_skill_values.csv for Death Nova (or the rune that states it), the generated value map says whose record holds
    it, and the numbers are the researched ones: 350% in 25 yards for 20 Essence, Tendril Nova 225% and 1%, Bone Nova 475% in
    12 yards, Blood Nova 450%, Blight 60% and 15% for 1 second, Unstable Compound 5 yards up to 2 times. Every tunable is a
    row of data/tunables/necromancer.csv: Blood Nova's cost with its source, the patch's time a named placeholder.
  * **The wiring.** The two runes that strike for themselves have no hit of the engine's; Blood Nova pays its Life when the
    cast begins; any other skill ends Unstable Compound's growth; Blight uses the shared enemy effects.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_death_nova.py
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
MATH = "src/classes/necromancer/dc_necromancer_death_nova_math.h"
HARNESS = MODULE / "tests/necromancer_death_nova/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_death_nova.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Death Nova"


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


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


def scratch_tree(mutate=None):
    key = MATH[len("src/"):]
    files = {key: (MODULE / MATH).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {MATH}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [float(tunables()["unstable_compound_base_radius_yards"]["d3_value"]), value("Unstable Compound", "radius_yards"), value("Unstable Compound", "max_stacks_count"),
               value("Tendril Nova", "heal_pct")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 14, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Blight")\n            return Rune::Blight;', 'if (name == "Blight")\n            return Rune::BloodNova;')),
            ("Bone Nova leaves the engine's", ("return rune == Rune::BoneNova || rune == Rune::UnstableCompound;", "return rune == Rune::UnstableCompound;")),
            ("every rune strikes for itself", ("return rune == Rune::BoneNova || rune == Rune::UnstableCompound;", "return rune != Rune::None;")),
            ("Unstable Compound leaves the engine's", ("return rune == Rune::BoneNova || rune == Rune::UnstableCompound;", "return rune == Rune::BoneNova;")),
            ("the radius does not grow", ("std::max(0.0, perStackYards) * std::min(stacks, maxStacks)", "0.0")),
            ("the radius grows without end", ("std::min(stacks, maxStacks)", "stacks")),
            ("the radius grows a stack early", ("std::min(stacks, maxStacks)", "std::min(stacks + 1, maxStacks)")),
            ("a negative growth shrinks it", ("std::max(0.0, perStackYards)", "perStackYards")),
            ("the heal is once for all", ("maxLife * healPct / 100.0 * enemies", "maxLife * healPct / 100.0")),
            ("the heal is not a percent", ("maxLife * healPct / 100.0 * enemies", "maxLife * healPct * enemies")),
            ("a patch has a pulse too many", ("std::floor(seconds / pulseSeconds + 1e-9)", "std::floor(seconds / pulseSeconds + 1.0)")),
            ("a pulse is lost to rounding", ("std::floor(seconds / pulseSeconds + 1e-9)", "std::floor(seconds / pulseSeconds)")),
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
        self.assertEqual(runes(), ["Tendril Nova", "Bone Nova", "Blood Nova", "Blight", "Unstable Compound"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cost_resource", "damage_pct", "radius_yards")], [20, 350, 25])
        self.assertEqual([value("Tendril Nova", t) for t in ("heal_pct", "damage_pct")], [1, 225])
        self.assertEqual([value("Bone Nova", t) for t in ("damage_pct", "radius_yards")], [475, 12])
        self.assertEqual([value("Blood Nova", t) for t in ("damage_pct", "radius_yards")], [450, 25])
        self.assertEqual([value("Blight", t) for t in ("slow_pct", "enemy_damage_pct", "duration_seconds")], [60, 15, 1])
        self.assertEqual([value("Unstable Compound", t) for t in ("radius_yards", "max_stacks_count")], [5, 2])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"duration_seconds", "slow_pct", "enemy_damage_pct", "heal_pct", "radius_yards", "max_stacks_count"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "cost_resource"), ("", "damage_pct"), ("", "radius_yards"), ("Tendril Nova", "heal_pct"),
                            ("Tendril Nova", "damage_pct"), ("Bone Nova", "damage_pct"), ("Bone Nova", "radius_yards"),
                            ("Blood Nova", "damage_pct"), ("Blight", "slow_pct"), ("Blight", "enemy_damage_pct"),
                            ("Blight", "duration_seconds"), ("Unstable Compound", "radius_yards"),
                            ("Unstable Compound", "max_stacks_count")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"blood_nova_life_cost_pct": "10", "blight_patch_seconds": "1", "unstable_compound_base_radius_yards": "20",
               "unstable_compound_stack_seconds": "2", "blight_pulse_seconds": "0.5"}

    def test_the_rows_hold_the_sourced_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                if number:
                    self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                else:
                    self.assertTrue(rows[name]["notes"].startswith("PLACEHOLDER for the designer"))

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))

    def test_the_cost_is_the_runes_tooltip(self):
        tooltip = [r["full_rune_text"] for r in read(D3 / "necromancer_runes.csv") if (r["skill_name"], r["rune_name"]) == (SKILL, "Blood Nova")][0]
        self.assertIn("Spend 10% health", tooltip)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto nova = DeathNova::BasePct(spellId)) return nova;", self.dispatch)
        self.assertIn("DeathNova::Casting(player, spellId);", self.dispatch)
        self.assertIn("DeathNova::Cast(player, spellId, targets);", self.dispatch)

    def test_the_runes_that_strike_for_themselves_have_no_engine_hit(self):
        self.assertIn("RowOf(spellId, Skill) && StrikesForItself(RuneAt(spellId)) ? std::optional<double>(0.0) : std::nullopt", self.code)

    def test_blood_nova_pays_when_the_cast_begins(self):
        self.assertIn('if (RowOf(spellId, Skill) && RuneAt(spellId) == Rune::BloodNova) SpendLife(player, Tune("blood_nova_life_cost_pct"));', self.code)

    def test_unstable_compounds_stacks_run_out_after_their_seconds_and_no_other_skill_ends_them(self):
        self.assertIn('Buffs::Add(held, Now(), std::uint64_t(Tune("unstable_compound_stack_seconds") * 1000.0), most);', self.code)
        self.assertIn("before = Buffs::Over(held, Now()) ? 0 : held.stacks;", self.code)
        self.assertNotIn("stacks.erase", self.code)

    def test_bone_nova_and_unstable_compound_strike_from_the_necromancer(self):
        self.assertIn('Combat::StrikeArea(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards"));', self.code)
        self.assertIn('GrownRadius(Tune("unstable_compound_base_radius_yards"), Numbers::Num(spellId, "radius_yards"), before, most)', self.code)

    def test_blight_slows_and_weakens_through_the_shared_effects(self):
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), seconds);', self.code)
        self.assertIn('EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), seconds);', self.code)
        # the pulse is a row, not a constant: the patch is felt again every blight_pulse_seconds
        self.assertNotIn("PatchPulseSeconds", self.code)
        self.assertIn('double PulseSeconds() { return Tune("blight_pulse_seconds"); }', self.code)
        self.assertIn('PatchPulses(Tune("blight_patch_seconds"), PulseSeconds())', self.code)
        self.assertEqual(self.code.count("PulseSeconds() * 1000"), 2)

    def test_tendril_nova_heals_for_the_enemies_the_nova_hit(self):
        self.assertIn('HealOfEnemies(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), unsigned(targets.size()))', self.code)


if __name__ == "__main__":
    unittest.main()

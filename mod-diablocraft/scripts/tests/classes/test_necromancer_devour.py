"""Devour and its five runes (src/classes/necromancer/dc_necromancer_devour*.h/.cpp, the dispatch in dc_necromancer.cpp, the
shared minions' Count and DismissAll).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_devour/harness.cpp compiles the real
    dc_necromancer_devour_math.h and the shared dc_corpses_math.h with the sheets' own rune names and numbers (the corpse cap
    and lifetime, blank until the designer answers q-1021-35, are set in the harness): each rune name is its rune; the Essence is paid
    for each corpse; Cannibalize heals a share of maximum Life for each corpse; the aura's radius is its own and a share of the
    gold pickup radius; the cast needs a corpse (for Ruthless a minion will do); only the aura rune is an aura, whose clock
    counts whole pulses; a cast takes every corpse within the reach. Planted differences in a scratch copy must each make it
    fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_devour.cpp reads by name is a row of
    necromancer_skill_values.csv for Devour (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: 10 Essence a corpse within 60 yards, Cannibalize 3%, Ruthless 10 a minion,
    Voracious 2% for 5 seconds, Devouring Aura 15 yards and 11 Essence with 50% of the pickup radius, Satiated 2% for 2 seconds.
    The tunables are rows of data/tunables/necromancer.csv from the power file (decode_pow.py power P6_Necro_Devour): the stack
    cap of 25, the aura's 0.65 second look, its most extra radius (20) and the 5 corpses a look (the designer, q-1021-54).
  * **The wiring.** The cast is refused with nothing to consume, the corpses go nearest first without a most, the stacking
    runes use the shared timed stacks, and the aura goes with the rune on the bar.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_devour.py
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
MATH = "src/classes/necromancer/dc_necromancer_devour_math.h"
CORPSES = "src/combat/dc_corpses_math.h"
HARNESS = MODULE / "tests/necromancer_devour/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_devour.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Devour"


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
    return [r["rune_name"].strip() for r in rows]


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (MATH, CORPSES)}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "radius_yards"), value("", "gain_resource"), value("Cannibalize", "heal_pct"),
               value("Devouring Aura", "radius_yards"), value("Devouring Aura", "radius_share_pct")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 22, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (MATH, 'if (name == "Satiated")\n            return Rune::Satiated;', 'if (name == "Satiated")\n            return Rune::Voracious;')),
            ("the Essence is for the cast", (MATH, "perOne * double(count)", "perOne")),
            ("a negative Essence is paid", (MATH, "return perOne > 0 ? perOne * double(count) : 0.0;", "return perOne * double(count);")),
            ("the heal is for the cast", (MATH, "maxLife * healPct / 100.0 * double(corpses)", "maxLife * healPct / 100.0")),
            ("the heal is not a percent", (MATH, "maxLife * healPct / 100.0 * double(corpses)", "maxLife * healPct * double(corpses)")),
            ("the aura loses its own radius", (MATH, "std::max(0.0, baseYards) +", "")),
            ("the aura takes the whole pickup radius", (MATH, "pickupYards * sharePct / 100.0", "pickupYards")),
            ("the aura's increase has no most", (MATH, "if (maxIncreaseYards > 0)\n            increase = std::min(increase, maxIncreaseYards);", "")),
            ("the aura's increase is the most", (MATH, "increase = std::min(increase, maxIncreaseYards);", "increase = maxIncreaseYards;")),
            ("the aura ignores the pickup radius", (MATH, "sharePct > 0 && pickupYards > 0 ? pickupYards * sharePct / 100.0 : 0.0", "0.0")),
            ("a corpse is not enough", (MATH, "return corpses > 0 || (rune == Rune::Ruthless && minions > 0);", "return corpses > 0 && minions > 0;")),
            ("every rune may consume minions alone", (MATH, "(rune == Rune::Ruthless && minions > 0)", "(minions > 0)")),
            ("Ruthless may not", (MATH, "(rune == Rune::Ruthless && minions > 0)", "false")),
            ("every rune is an aura", (MATH, "return rune == Rune::DevouringAura;", "return rune != Rune::None;")),
            ("the aura rune is no aura", (MATH, "return rune == Rune::DevouringAura;", "return false;")),
            ("the clock loses its rest", (MATH, "clockMs -= pulseSeconds * 1000.0;", "clockMs = 0;")),
            ("a pulse is never on the moment", (MATH, "while (clockMs >= pulseSeconds * 1000.0)", "while (clockMs > pulseSeconds * 1000.0)")),
            ("the pile stops at one", (CORPSES, "if (near.size() > max)", "if (near.size() > 1)")),
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
        self.assertEqual(runes(), ["Cannibalize", "Ruthless", "Voracious", "Devouring Aura", "Satiated"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("radius_yards", "gain_resource")], [60, 10])
        self.assertEqual(value("Cannibalize", "heal_pct"), 3)
        self.assertEqual(value("Ruthless", "gain_resource"), 10)
        self.assertEqual([value("Voracious", t) for t in ("cost_reduction_pct", "duration_seconds")], [2, 5])
        self.assertEqual([value("Devouring Aura", t) for t in ("radius_yards", "gain_resource", "radius_share_pct")], [15, 11, 50])
        self.assertEqual([value("Satiated", t) for t in ("max_life_pct", "duration_seconds")], [2, 2])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"radius_yards", "radius_share_pct", "gain_resource", "heal_pct", "cost_reduction_pct",
                                  "duration_seconds", "max_life_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "radius_yards"), ("", "gain_resource"), ("Cannibalize", "heal_pct"), ("Ruthless", "gain_resource"),
                            ("Voracious", "cost_reduction_pct"), ("Voracious", "duration_seconds"),
                            ("Devouring Aura", "radius_yards"), ("Devouring Aura", "gain_resource"),
                            ("Devouring Aura", "radius_share_pct"), ("Satiated", "max_life_pct"), ("Satiated", "duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)

    def test_the_skill_states_its_reach_as_the_tooltip_does(self):
        tooltip = [r["full_tooltip_text"] for r in read(D3 / "necromancer_skills.csv") if r["skill_name"] == SKILL][0]
        self.assertIn("Consume corpses within {radius_yards} yards", tooltip)


class Tunables(unittest.TestCase):
    def test_the_rows_hold_the_decoded_numbers_and_alexs_five(self):
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}
        for name, number in (("devour_max_stacks", "25"), ("devour_aura_tick_seconds", "0.65"),
                             ("devour_aura_max_radius_increase_yards", "20"), ("devour_aura_corpses_per_tick", "5")):
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        names = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', CODE.read_text(encoding="utf-8")))
        self.assertEqual(names, {"devour_max_stacks", "devour_aura_tick_seconds", "devour_aura_max_radius_increase_yards",
                                 "devour_aura_corpses_per_tick"})


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))
        self.minions = (MODULE / "src/combat/dc_minions.h").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("Devour::CanCast(player, spellId)", self.dispatch)
        self.assertIn("Devour::Cast(player, spellId);", self.dispatch)
        self.assertIn("Devour::RegisterScripts();", self.dispatch)

    def test_the_cast_needs_a_corpse_or_for_ruthless_a_minion_and_the_aura_is_always_castable(self):
        self.assertIn("|| TogglesAnAura(RuneAt(spellId))) return SPELL_CAST_OK;", self.code)
        self.assertIn("Minions::Count(player)", self.code)
        self.assertIn("SPELL_CAST_OK : SPELL_FAILED_NO_VALID_TARGETS", self.code)

    def test_every_corpse_within_reach_goes_without_a_most(self):
        self.assertIn("Corpses::Consume(player, player->GetPosition(), float(Reach(player, spellId)),", self.code)
        self.assertIn(": std::numeric_limits<std::size_t>::max());", self.code)

    def test_ruthless_consumes_the_minions_and_pays_for_each(self):
        self.assertIn('essence += EssenceOf(Numbers::Num(spellId, "gain_resource"), Minions::DismissAll(player));', self.code)
        self.assertIn("unsigned DismissAll(Player* owner);", self.minions)
        self.assertIn("unsigned Count(Player* owner);", self.minions)

    def test_voracious_and_satiated_stack_for_each_corpse_through_the_shared_stacks(self):
        self.assertIn("Buffs::Stack(player, spellId, Stat::ResourceCostReduction, Bucket::Flat", self.code)
        self.assertIn("Buffs::Stack(player, spellId, Stat::LifePercent, Bucket::Flat", self.code)
        self.assertEqual(self.code.count("StackCap(), Numbers::Num(spellId, \"duration_seconds\"), unsigned(taken.size()))"), 2)
        self.assertIn('return unsigned(Tune("devour_max_stacks"));', self.code)

    def test_the_aura_looks_every_tick_for_a_few_corpses_within_the_capped_radius(self):
        self.assertIn('Tune("devour_aura_tick_seconds")', self.code)
        self.assertIn('Tune("devour_aura_max_radius_increase_yards")', self.code)
        self.assertIn('TogglesAnAura(rune) ? std::size_t(Tune("devour_aura_corpses_per_tick")) : std::numeric_limits<std::size_t>::max()', self.code)

    def test_the_aura_reads_the_pickup_radius_and_goes_with_the_rune_on_the_bar(self):
        self.assertIn("(*sheet)[Stat::GoldPickupRange]", self.code)
        self.assertIn("RuneAt(Slotted(player, Skill)) != Rune::DevouringAura", self.code)
        self.assertIn("PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED", self.code)


if __name__ == "__main__":
    unittest.main()

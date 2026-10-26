"""Corpse Lance and its five runes (src/classes/necromancer/dc_necromancer_corpse_lance*.h/.cpp, the dispatch in
dc_necromancer.cpp, the cast check and the crit term in dc_combat.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_corpse_lance/harness.cpp compiles the real
    dc_necromancer_corpse_lance_math.h, dc_necromancer_buffs.h and the shared dc_corpses_math.h with the sheets' own rune
    names and numbers (the corpse cap and lifetime, blank until the designer answers q-1021-35, are set in the harness): each rune name
    is its rune; a corpse near either the Necromancer or the target is a corpse in reach and the one near the target goes
    first; Ricochet needs a roll under its chance and a reach; Shredding Splinters' slow is a stack's worth up to the cap, the
    time restarting with each lance; Brittle Touch holds until its end. Planted differences in a scratch copy must each make
    it fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_corpse_lance.cpp reads by name is a row of
    necromancer_skill_values.csv for Corpse Lance (or the rune that states it), the generated value map says whose record
    holds it, and the numbers are the researched ones: 1750%, Ricochet 20%, Brittle Touch 5% for 5 seconds, Blood Lance 525%,
    Visceral Impact 3 seconds, Shredding Splinters 10% and 6% for 10 seconds up to 5 stacks. Every tunable is a row of
    data/tunables/necromancer.csv: the two search reaches (75, 35) and Blood Lance's cost with their sources, the ricochet's
    reach a named placeholder.
  * **The wiring.** The cast refuses with no corpse in reach, the first impact takes the corpse, Blood Lance keeps the skill's
    number for the main lance, the engine asks the class for the crit chance and the cast check.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_corpse_lance.py
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
MATH = "src/classes/necromancer/dc_necromancer_corpse_lance_math.h"
BUFFS = "src/classes/necromancer/dc_necromancer_buffs.h"
CORPSES = "src/combat/dc_corpses_math.h"
HARNESS = MODULE / "tests/necromancer_corpse_lance/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_corpse_lance.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Corpse Lance"


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
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (MATH, BUFFS, CORPSES)}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    rows = tunables()
    numbers = [float(rows["corpse_lance_reach_near_caster_yards"]["d3_value"]), float(rows["corpse_lance_reach_near_target_yards"]["d3_value"]),
               value("Ricochet", "proc_chance_pct"), value("Shredding Splinters", "slow_pct"),
               value("Shredding Splinters", "duration_seconds"), value("Shredding Splinters", "max_stacks_count")] + runes()
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
            ("two runes share a name", (MATH, 'if (name == "Blood Lance")\n            return Rune::BloodLance;', 'if (name == "Blood Lance")\n            return Rune::Ricochet;')),
            ("Blood Lance loses the skill's number", (MATH, "return rune == Rune::BloodLance;", "return false;")),
            ("every rune keeps the skill's number", (MATH, "return rune == Rune::BloodLance;", "return rune != Rune::None;")),
            ("a corpse near the Necromancer is not enough", (MATH, "return nearTheNecromancer > 0 || nearTheTarget > 0;", "return nearTheTarget > 0;")),
            ("a corpse near the target is not enough", (MATH, "return nearTheNecromancer > 0 || nearTheTarget > 0;", "return nearTheNecromancer > 0;")),
            ("a lance needs both corpses", (MATH, "return nearTheNecromancer > 0 || nearTheTarget > 0;", "return nearTheNecromancer > 0 && nearTheTarget > 0;")),
            ("the corpse is taken near the Necromancer first", (MATH, "return nearTheTarget > 0;\n    }\n\n    // \"has a", "return nearTheTarget == 0;\n    }\n\n    // \"has a")),
            ("a roll at the chance ricochets", (MATH, "roll < chancePct", "roll <= chancePct")),
            ("every roll ricochets", (MATH, "&& roll < chancePct", "")),
            ("no reach still ricochets", (MATH, "chancePct > 0 && reachYards > 0 &&", "chancePct > 0 &&")),
            ("the slow is for the cast", (MATH, "perStack * std::min(stacks, maxStacks)", "perStack")),
            ("the slow has no cap", (MATH, "std::min(stacks, maxStacks)", "stacks")),
            ("a negative slow speeds up", (MATH, "return perStack > 0 ? perStack * std::min(stacks, maxStacks) : 0.0;", "return perStack * std::min(stacks, maxStacks);")),
            ("the mark holds a moment too long", (MATH, "return nowMs < untilMs;", "return nowMs <= untilMs;")),
            ("the mark never ends", (MATH, "return nowMs < untilMs;", "return true;")),
            ("a lance does not stack", (BUFFS, "held.stacks + std::max(1u, adds)", "std::max(1u, adds)")),
            ("a lance does not restart the time", (BUFFS, "held.until = now + ms;", "held.until = held.until ? held.until : now + ms;")),
            ("the pile takes the farthest corpse", (CORPSES, "GroundDistance(corpses_[a].spot, x, y) <", "GroundDistance(corpses_[a].spot, x, y) >")),
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
        self.assertEqual(runes(), ["Ricochet", "Brittle Touch", "Blood Lance", "Visceral Impact", "Shredding Splinters"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual(value("", "damage_pct"), 1750)
        self.assertEqual(value("Ricochet", "proc_chance_pct"), 20)
        self.assertEqual([value("Brittle Touch", t) for t in ("crit_taken_pct", "duration_seconds")], [5, 5])
        self.assertEqual(value("Blood Lance", "damage_pct"), 525)
        self.assertEqual(value("Visceral Impact", "stun_duration_seconds"), 3)
        self.assertEqual([value("Shredding Splinters", t) for t in ("slow_pct", "enemy_damage_pct", "duration_seconds", "max_stacks_count")],
                         [10, 6, 10, 5])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "proc_chance_pct", "crit_taken_pct", "duration_seconds", "stun_duration_seconds",
                                  "slow_pct", "enemy_damage_pct", "max_stacks_count"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("Ricochet", "proc_chance_pct"), ("Brittle Touch", "crit_taken_pct"),
                            ("Brittle Touch", "duration_seconds"), ("Blood Lance", "damage_pct"),
                            ("Visceral Impact", "stun_duration_seconds"), ("Shredding Splinters", "slow_pct"),
                            ("Shredding Splinters", "enemy_damage_pct"), ("Shredding Splinters", "duration_seconds"),
                            ("Shredding Splinters", "max_stacks_count")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"corpse_lance_reach_near_caster_yards": "75", "corpse_lance_reach_near_target_yards": "35",
               "blood_lance_life_cost_pct": "2", "corpse_lance_ricochet_yards": "35", "brittle_touch_max_stacks": "99"}

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

    def test_brittle_touch_stacks_to_the_power_files_most_and_the_time_starts_over(self):
        code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('Buffs::Add(mark.held, Now(), std::uint64_t(Numbers::Num(spellId, "duration_seconds") * 1000.0), unsigned(Tune("brittle_touch_max_stacks")));', code)
        self.assertIn('StackedPct(found->second.pct, found->second.held.stacks, unsigned(Tune("brittle_touch_max_stacks")))', code)
        self.assertIn("decode_pow.py power P6_Necro_CorpseLance", tunables()["brittle_touch_max_stacks"]["notes"])

    def test_the_search_reaches_are_the_power_files(self):
        row = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL][0]
        self.assertIn("75 near the caster and 35 near the target (SF_1, SF_2)", row["source"])

    def test_the_cost_is_the_runes_tooltip(self):
        tooltip = [r["full_rune_text"] for r in read(D3 / "necromancer_runes.csv") if (r["skill_name"], r["rune_name"]) == (SKILL, "Blood Lance")][0]
        self.assertIn("Spend 2% of your total health", tooltip)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))
        self.combat = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("return CorpseLance::BasePct(spellId);", self.dispatch)
        self.assertIn("CorpseLance::CanCast(player, spellId, target)", self.dispatch)
        self.assertIn("CorpseLance::Casting(player, spellId);", self.dispatch)
        self.assertIn("CorpseLance::Impact(player, target, spellId, index)", self.dispatch)
        self.assertIn("CorpseLance::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("return CorpseLance::CritBonus(player, target) + CommandGolem::CritBonus(player, target);", self.dispatch)

    def test_the_engine_asks_for_the_target_and_the_crit_chance(self):
        self.assertIn("spell->m_targets.GetUnitTarget());", self.combat)
        self.assertIn("+Crusader::CritBonus(player, target, shell.spellId)+Necromancer::CritBonus(player, target)+DemonHunter::CritBonus(player, target, shell.spellId)+", self.combat)

    def test_the_cast_refuses_with_no_corpse_in_reach(self):
        self.assertIn("SPELL_CAST_OK : SPELL_FAILED_NO_VALID_TARGETS", self.code)
        self.assertIn("Corpses::Count(player, player->GetPosition(), NearCaster())", self.code)

    def test_the_first_impact_takes_the_corpse_nearest_the_target_first(self):
        self.assertIn("|| index != 0) return false;", self.code)
        self.assertIn("Corpses::Consume(player, target->GetPosition(), NearTarget(), CorpsesPerLance)", self.code)
        self.assertIn("Corpses::Consume(player, player->GetPosition(), NearCaster(), CorpsesPerLance)", self.code)
        self.assertIn("return taken.empty();", self.code)

    def test_blood_lance_pays_in_life_and_keeps_the_skills_number_for_the_main_lance(self):
        self.assertIn('SpendLife(player, Tune("blood_lance_life_cost_pct"));', self.code)
        self.assertIn('KeepsTheSkillsHit(RuneAt(spellId)) ? Numbers::Get(BaseId(Skill), "damage_pct") : std::nullopt', self.code)
        self.assertIn('Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct"));', self.code)

    def test_a_lance_that_ricochets_or_follows_does_not_trigger_the_runes_again(self):
        self.assertIn("if (ricocheting || !Ricochets(", self.code)
        self.assertEqual(self.code.count("ricocheting = true;"), 2)

    def test_visceral_impact_is_stretched_by_the_worn_powers_and_splinters_use_the_shared_effects(self):
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', self.code)
        self.assertIn('EnemyEffects::Weaken(target, spellId, Numbers::Num(spellId, "enemy_damage_pct"), seconds, most);', self.code)


if __name__ == "__main__":
    unittest.main()

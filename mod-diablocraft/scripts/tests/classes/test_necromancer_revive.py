"""Revive and its five runes (src/classes/necromancer/dc_necromancer_revive*.h/.cpp, the revived minion's kind in
dc_necromancer_pets.cpp, the shared minions' timedOut, the dispatch, the damage seam in dc_combat.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_revive/harness.cpp compiles the real dc_necromancer_revive_math.h
    and the shared dc_corpses_math.h with the sheets' own rune names and numbers (the corpse cap and lifetime, blank until the designer
    answers q-1021-35, are set in the harness): each rune name is its rune; Personal Army takes a share off for each minion
    standing, never below nothing; a cast revives up to the most corpses within the reach, nearest first, each with the creature
    that died there; Oblation costs a share for each corpse revived. Planted differences in a scratch copy must each make it
    fail.
  * **The code reads what the sheets and the power file state.** Every token the cast and the revived kind read by name is a row
    of necromancer_skill_values.csv for Revive (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: up to 10 corpses within 20 yards for 15 seconds, Oblation +20%, Personal Army 1%
    a minion, Recklessness +25% and 10 seconds, Horrific Return 20 yards and 3 seconds. The tunables are rows of
    data/tunables/necromancer.csv with their decoded sources (decode_pow.py power P6_Necro_Revive): the revived minion's damage
    (the Revived Monster Damage Scalar, 1), its Life (the % of the player's Life to add, 1.0) and Oblation's cost for each
    target (0.03).
  * **The wiring.** The cast refuses with no corpse in reach, takes the corpses and raises a minion for each in the look of the
    creature that died; Purgatory leaves a corpse where the minion's time is up, and only then; the engine asks the class what
    damage the Necromancer takes.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_revive.py
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
MATH = "src/classes/necromancer/dc_necromancer_revive_math.h"
CORPSES = "src/combat/dc_corpses_math.h"
HARNESS = MODULE / "tests/necromancer_revive/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_revive.cpp"
PETS = MODULE / "src/classes/necromancer/dc_necromancer_pets.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Revive"


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
    numbers = [value("", "target_count"), value("", "radius_yards"), value("Personal Army", "damage_reduction_pct"),
               float(tunables()["revive_oblation_life_cost_pct"]["d3_value"])] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (MATH, 'if (name == "Recklessness")\n            return Rune::Recklessness;', 'if (name == "Recklessness")\n            return Rune::Oblation;')),
            ("the reduction is for the army", (MATH, "reductionPerMinionPct * active / 100.0", "reductionPerMinionPct / 100.0")),
            ("the reduction is not a percent", (MATH, "reductionPerMinionPct * active / 100.0", "reductionPerMinionPct * active")),
            ("the army can heal", (MATH, "return std::max(0.0, 1.0 - reductionPerMinionPct * active / 100.0);", "return 1.0 - reductionPerMinionPct * active / 100.0;")),
            ("a negative reduction hurts", (MATH, "if (reductionPerMinionPct <= 0)\n            return 1.0;", "")),
            ("a cast revives more than it may", (MATH, "std::min(lying, std::size_t(targetCount))", "lying")),
            ("a cast revives only what it may", (MATH, "std::min(lying, std::size_t(targetCount))", "std::size_t(targetCount)")),
            ("no count allowed still revives", (MATH, "return targetCount > 0 ? std::min(lying, std::size_t(targetCount)) : 0;", "return lying;")),
            ("no corpse still casts", (MATH, "return lyingNearThePoint > 0;", "return true;")),
            ("the cost is for the cast", (MATH, "perCorpsePct * double(corpses)", "perCorpsePct")),
            ("a negative cost heals", (MATH, "return perCorpsePct > 0 ? perCorpsePct * double(corpses) : 0.0;", "return perCorpsePct * double(corpses);")),
            ("Recklessness does not raise the damage", (MATH, "return rune == Rune::Oblation || rune == Rune::Recklessness;", "return rune == Rune::Oblation;")),
            ("every rune raises the damage", (MATH, "return rune == Rune::Oblation || rune == Rune::Recklessness;", "return rune != Rune::None;")),
            ("the pile ignores the most", (CORPSES, "if (near.size() > max)", "if (false)")),
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
        self.assertEqual(runes(), ["Purgatory", "Oblation", "Personal Army", "Recklessness", "Horrific Return"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("target_count", "radius_yards", "duration_seconds")], [10, 20, 15])
        self.assertEqual(value("Oblation", "damage_bonus_pct"), 20)
        self.assertEqual(value("Personal Army", "damage_reduction_pct"), 1)
        self.assertEqual([value("Recklessness", t) for t in ("damage_bonus_pct", "duration_seconds")], [25, 10])
        self.assertEqual([value("Horrific Return", t) for t in ("radius_yards", "fear_duration_seconds")], [20, 3])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        cast = set(re.findall(call, CODE.read_text(encoding="utf-8")))
        self.assertEqual(cast - sheet_tokens, set())
        self.assertEqual(cast, {"radius_yards", "target_count", "fear_duration_seconds", "damage_reduction_pct"})
        pets = PETS.read_text(encoding="utf-8")
        kind = pets[pets.index("Minions::Kind Revived(Player* owner)"):pets.index("// Simulacrum:")]
        read_there = set(re.findall(call, kind))
        self.assertEqual(read_there - sheet_tokens, set())
        self.assertEqual(read_there, {"damage_bonus_pct", "duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "target_count"), ("", "radius_yards"), ("", "duration_seconds"), ("Oblation", "damage_bonus_pct"),
                            ("Personal Army", "damage_reduction_pct"), ("Recklessness", "damage_bonus_pct"),
                            ("Recklessness", "duration_seconds"), ("Horrific Return", "radius_yards"),
                            ("Horrific Return", "fear_duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    def test_the_decoded_rows_hold_the_power_files_numbers(self):
        rows = tunables()
        self.assertEqual((rows["revive_damage_pct"]["d3_value"], rows["revive_damage_pct"]["value"]), ("100", ""))
        self.assertIn("necromancer_revive_attacks.csv", rows["revive_damage_pct"]["notes"])
        self.assertEqual((rows["revive_life_pct"]["d3_value"], rows["revive_life_pct"]["value"]), ("100", ""))
        self.assertEqual((rows["revive_oblation_life_cost_pct"]["d3_value"], rows["revive_oblation_life_cost_pct"]["value"]), ("3", ""))
        for name in ("revive_damage_pct", "revive_life_pct", "revive_oblation_life_cost_pct"):
            with self.subTest(name):
                self.assertIn("decode_pow.py power P6_Necro_Revive", rows[name]["notes"])
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_code_reads_these(self):
        text = CODE.read_text(encoding="utf-8") + PETS.read_text(encoding="utf-8")
        read_here = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertTrue({"revive_damage_pct", "revive_life_pct", "revive_oblation_life_cost_pct", "minion_revive_cap"} <= read_here)


class Scalars(unittest.TestCase):
    """the designer's option (b), q-1021-36: each revived monster keeps its own attack, scaled by D3's Damage Scalar of it."""

    UPDATES = MODULE / "data/sql/db-world/updates"

    def attacks(self):
        return read(D3 / "necromancer_revive_attacks.csv")

    def test_the_attack_sheet_is_the_power_files_fifty_five_with_their_scalars(self):
        rows = self.attacks()
        self.assertEqual(len(rows), 55)
        self.assertTrue(all(r["power"].lower().startswith("p6_necro_revive_") for r in rows))
        counts = {}
        for r in rows:
            counts[r["damage_scalar"]] = counts.get(r["damage_scalar"], 0) + 1
        # decisions.md 2026-10-21: 1.0 on 34 of the 51 that carry one, 1.5 on 8, 0.33 on 4, 0.5 on 2, 0.85 on 2, 0.9 on 1
        self.assertEqual(counts, {"1.0": 34, "1.5": 8, "0.33": 4, "0.5": 2, "0.85": 2, "0.9": 1, "": 4})
        self.assertTrue(all("decode_pow.py power " in r["source"] for r in rows))
        scalars = {r["power"]: r["damage_scalar"] for r in rows}
        self.assertEqual(scalars["p6_Necro_Revive_Succubus_BloodStar"], "0.9")
        self.assertEqual(scalars["P6_Necro_Revive_Wraith_Melee"], "0.33")
        self.assertEqual(scalars["p6_Necro_Revive_BeastCharge"], "1.5")
        self.assertEqual(scalars["p6_Necro_Revive_deathMaiden_Spin_Attack"], "0.5")

    def test_each_monster_row_names_a_roster_monster_and_an_attack_with_a_scalar(self):
        scalars = {r["power"]: r["damage_scalar"] for r in self.attacks()}
        roster = {r["name"] for r in read(D3 / "monster_roster.csv")}
        rows = read(D3 / "necromancer_revive_monsters.csv")
        self.assertTrue(rows)
        for r in rows:
            with self.subTest(r["monster"]):
                self.assertIn(r["monster"], roster)
                self.assertTrue(scalars.get(r["power"]))
                self.assertTrue(r["why"])
        by = {r["monster"]: scalars[r["power"]] for r in rows}
        self.assertEqual((by["Sand Wasp"], by["Succubus"], by["Bogan Darter"]), ("0.33", "0.9", "0.33"))

    def test_the_migration_and_its_mirror_are_the_generators_render(self):
        sys.path.insert(0, str(MODULE / "scripts"))
        import generate_necromancer_revive_scalars as generator
        sql = (self.UPDATES / "necromancer_revive_0001_scalars.sql").read_text(encoding="utf-8")
        self.assertEqual(sql, generator.render())
        self.assertEqual(sql, (MODULE / "data/generated/necromancer_revive_0001_scalars.sql").read_text(encoding="utf-8"))
        self.assertIn("(950060, 'Succubus', 'p6_Necro_Revive_Succubus_BloodStar', 0.9)", sql)
        self.assertIn("(950041, 'Sand Wasp', 'p6_Necro_Revive_SandWasp_Projectile', 0.33)", sql)

    def test_the_generator_refuses_a_stranger_a_missing_scalar_and_a_twice(self):
        sys.path.insert(0, str(MODULE / "scripts"))
        import generate_necromancer_revive_scalars as generator
        attacks = self.attacks()
        roster = [{"monster": "Succubus", "entry": 950060}, {"monster": "Held Back", "entry": None}]
        good = {"monster": "Succubus", "power": "p6_Necro_Revive_Succubus_BloodStar", "why": "same creature"}
        self.assertEqual(len(generator.rows(roster, attacks, [good])), 1)
        for label, row in (("a stranger", dict(good, monster="Nobody")), ("held back", dict(good, monster="Held Back")),
                           ("a helper with no scalar", dict(good, power="p6_Necro_Revive_armorScavenger_buff")),
                           ("no reason", dict(good, why="")), ("an unknown attack", dict(good, power="p6_Necro_Revive_Nothing"))):
            with self.subTest(label), self.assertRaises(ValueError):
                generator.rows(roster, attacks, [row])
        with self.assertRaises(ValueError):
            generator.rows(roster, attacks, [good, good])

    def test_the_code_reads_the_table_by_the_base_entry_and_defaults_to_one(self):
        pets = re.sub(r"\s+", " ", PETS.read_text(encoding="utf-8"))
        self.assertIn('WorldDatabase.Query("SELECT entry, scalar FROM dc_revive_scalar")', pets)
        self.assertIn("scalars.find(Rifts::Family::BaseEntry(entry)); return found == scalars.end() ? 1.0 : found->second;", pets)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.pets = re.sub(r"\s+", " ", PETS.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))
        self.minions = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_minions.cpp").read_text(encoding="utf-8"))
        self.combat = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("return CorpseRevive::CanCast(player, spellId, aim);", self.dispatch)
        self.assertIn("CorpseRevive::Ground(player, spellId, center);", self.dispatch)
        self.assertIn("return Simulacrum::Reduce(victim, Passive::Reduce(victim, BoneArmor::Reduce(victim, CorpseRevive::Reduce(victim, damage))));", self.dispatch)

    def test_the_engine_asks_the_class_for_the_damage_taken_after_the_crusader(self):
        self.assertIn("result = Crusader::Redirect(victim, result); result = Necromancer::Reduce(victim, result);", self.combat)

    def test_the_cast_refuses_with_no_corpse_and_takes_them_nearest_first_up_to_the_most(self):
        self.assertIn("SPELL_CAST_OK : SPELL_FAILED_NO_VALID_TARGETS", self.code)
        self.assertIn('Revived(Corpses::Count(player, center, Reach(spellId)), Numbers::Num(spellId, "target_count"))', self.code)

    def test_each_corpse_rises_in_the_look_of_the_creature_that_died(self):
        self.assertIn("Pets::Revive(player, where, LookOf(spot.entry), spellId, spot.entry);", self.code)
        self.assertIn("GetFirstValidModel()", self.code)

    def test_oblation_pays_for_each_corpse_revived(self):
        self.assertIn('SpendLife(player, LifeCostPct(Tune("revive_oblation_life_cost_pct"), taken.size()));', self.code)

    def test_horrific_return_frightens_the_enemies_around_each_corpse(self):
        self.assertIn('Fear(player, enemy, Numbers::Num(spellId, "fear_duration_seconds"));', self.code)

    def test_personal_army_counts_the_revived_minions_standing(self):
        self.assertIn('TakenFactor(Numbers::Num(slotted, "damage_reduction_pct"), Minions::Alive(player, "revived"))', self.code)

    def test_purgatory_leaves_a_corpse_only_when_the_time_is_up(self):
        self.assertIn("Rune::Purgatory) kind.timedOut = [entry = reviveCast.corpseEntry]", self.pets)
        self.assertIn("Corpses::LeaveMade(player, at, entry);", self.pets)
        self.assertIn("kind.timedOut && player && player->IsAlive()", self.minions)
        self.assertIn("Expired(Now(), bornAt, kind.lifeMs)) kind.timedOut(player, me->GetPosition());", self.minions)

    def test_the_minion_takes_the_runes_damage_and_the_players_life(self):
        self.assertIn('kind.damagePct = Tune("revive_damage_pct") * ReviveScalar(reviveCast.corpseEntry) * (1.0 + Numbers::Num(record, "damage_bonus_pct") / 100.0);', self.pets)
        self.assertIn('kind.lifeToCopyPct = Tune("revive_life_pct");', self.pets)


if __name__ == "__main__":
    unittest.main()

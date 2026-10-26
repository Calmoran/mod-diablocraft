"""Demon Hunter Impale and its five runes (src/classes/demon_hunter/dc_demon_hunter_impale.h and .cpp, the line rule in
dc_demon_hunter_seek.h, the stun in dc_demon_hunter_effects.cpp and the burn in dc_demon_hunter_dot.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_impale/harness.cpp compiles the real dc_demon_hunter_impale.h and
    dc_demon_hunter_seek.h with the sheets' own rune names and numbers: each rune name is its rune; each bounce of Ricochet keeps
    the power file's factor of the hit before; Overpenetration's line takes an enemy on it to its end and within half the width
    either side, and not one past the end, behind or off to the side. Eight mutations planted in a scratch copy (two runes share a
    name, a bounce keeps nothing or compounds twice, the line has no end, takes enemies behind, ignores its width, is
    twice as wide, or has no width and still takes enemies) must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of demon_hunter_skill_values.csv for Impale
    (or the rune that states it), the generated value map says whose record holds it, and the numbers are the researched ones: 20
    Hatred, 750%, Impact's 100% stun for 1.5 seconds, Chemical Burn's 500% over 2 seconds, Ricochet's 2 more enemies within 20
    yards, Grievous Wounds' 330%. Every tunable it reads is a row of data/tunables/demonhunter.csv, and the sheet's and the
    tunables' numbers equal the decoded Power/DemonHunter_Impale.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch hands the skill its seams after the others', the knife's hit is the skill's 750% for every rune, the
    core's own chain to the enemies Ricochet bounces to is swallowed so only the bounces hit, the pierce and the bounces start no
    chain of their own, the extra damage of a critical hit adds nothing more, the stun is stretched by the stun duration items and
    the burn rides the class's damage over time.

What it does not prove: anything on a running server. The throw, the pierce, the bounces, the knockback and stun, the burn and the
critical bonus are docs/test-diablocraft-vawmy.12.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_impale.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/demon_hunter/dc_demon_hunter_impale.h"
SEEK = "src/classes/demon_hunter/dc_demon_hunter_seek.h"
SOURCES = [HEADER, SEEK, "tests/demon_hunter_impale/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_impale.cpp"
SKILL = "Impale"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "demon_hunter_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "demon_hunter_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "demonhunter.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_impale/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "damage_pct"), tune("impale_ricochet_damage_factor"), tune("impale_pierce_length_yards"),
                         tune("impale_pierce_width_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 13, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        line = "return width > 0 && along >= 0 && along <= length && std::fabs(across) <= width / 2;"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::ChemicalBurn;", "return Rune::Impact;")),
            ("a bounce keeps nothing", (HEADER, "return basePct * std::pow(factor, double(bounces));", "return basePct;")),
            ("a bounce compounds twice", (HEADER, "return basePct * std::pow(factor, double(bounces));", "return basePct * std::pow(factor, double(bounces * 2));")),
            ("the line has no end", (SEEK, line, "return width > 0 && along >= 0 && std::fabs(across) <= width / 2;")),
            ("the line takes enemies behind", (SEEK, line, "return width > 0 && along <= length && std::fabs(across) <= width / 2;")),
            ("the line ignores its width", (SEEK, line, "return width > 0 && along >= 0 && along <= length;")),
            ("the line is twice as wide", (SEEK, line, "return width > 0 && along >= 0 && along <= length && std::fabs(across) <= width;")),
            ("a line with no width takes enemies", (SEEK, line, "return along >= 0 && along <= length && std::fabs(across) <= width / 2;")),
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
        self.assertEqual(runes(), ["Overpenetration", "Impact", "Chemical Burn", "Ricochet", "Grievous Wounds"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [20, 750])
        self.assertEqual([value("Impact", t) for t in ("proc_chance_pct", "stun_duration_seconds")], [100, 1.5])
        self.assertEqual([value("Chemical Burn", t) for t in ("damage_pct", "dot_duration_seconds")], [500, 2])
        self.assertEqual([value("Ricochet", t) for t in ("target_count", "radius_yards")], [2, 20])
        self.assertEqual(value("Grievous Wounds", "damage_bonus_pct"), 330)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, mine, source in (("impale_pierce_length_yards", "60", "", "SF_14"), ("impale_impact_knockback_yards", "5", "", "SF_4"),
                                       ("impale_ricochet_damage_factor", "1", "", "SF_16")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, mine), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Impale.pow", rows[name]["notes"])
        # The designer's standing defaults (AGENTS.md "Numbers", 2026-10-22), set in his column: a line is 3 yards wide, a burn ticks every 0.5 s.
        for name, number in (("impale_pierce_width_yards", "3"), ("impale_chemical_burn_tick_seconds", "0.5")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), ("", number), name)
            self.assertIn("standing default", rows[name]["notes"])
        for name, row in rows.items():
            if name.startswith("impale_"):
                self.assertNotIn("PLACEHOLDER", row["notes"], name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("impale_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "radius_yards", "target_count", "damage_bonus_pct", "proc_chance_pct",
                                  "stun_duration_seconds", "dot_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("Chemical Burn", "damage_pct"), ("Chemical Burn", "dot_duration_seconds"),
                            ("Impact", "proc_chance_pct"), ("Impact", "stun_duration_seconds"), ("Ricochet", "target_count"),
                            ("Ricochet", "radius_yards"), ("Grievous Wounds", "damage_bonus_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, "")]["origin"], "own")

    def test_the_knife_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Impale.pow"))["sf"]

        def number(n):
            return float(sf[n])

        self.assertAlmostEqual(number(10) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(3), value("", "cost_resource"))
        self.assertAlmostEqual(number(5) * 100, value("Impact", "proc_chance_pct"))
        self.assertAlmostEqual(number(6), value("Impact", "stun_duration_seconds"))
        self.assertAlmostEqual(number(9) * 100, value("Chemical Burn", "damage_pct"))
        self.assertAlmostEqual(float(sf[8].split("?")[1].split(":")[0]), value("Chemical Burn", "dot_duration_seconds"))
        self.assertAlmostEqual(number(11), value("Ricochet", "target_count"))
        self.assertAlmostEqual(number(12), value("Ricochet", "radius_yards"))
        self.assertAlmostEqual(number(13) * 100, value("Grievous Wounds", "damage_bonus_pct"))
        self.assertAlmostEqual(number(14), tune("impale_pierce_length_yards"))
        self.assertAlmostEqual(number(4), tune("impale_impact_knockback_yards"))
        self.assertAlmostEqual(number(16), tune("impale_ricochet_damage_factor"))
        self.assertAlmostEqual(number(1), 1.0)  # Overpenetration pierces every time

    def test_the_hit_is_the_skills_for_every_rune(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct");', text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_skill_its_seams_after_the_others(self):
        self.assertEqual(self.dispatch.count("if (auto knife = Impale::BasePct(spellId)) return knife;"), 1)
        self.assertLess(self.dispatch.index("Grenade::BasePct(spellId)"), self.dispatch.index("Impale::BasePct(spellId)"))
        self.assertEqual(self.dispatch.count("Impale::Landed(player, target, spellId, critical);"), 1)
        self.assertIn("EvasiveFire::Impact(player, target, aimed, cone, spellId) || Impale::Impact(player, target, aimed, spellId)", self.dispatch)

    def test_only_the_enemy_thrown_at_is_left_to_the_engine_when_the_core_chains(self):
        impact = self.code[self.code.index("bool Impact("):self.code.index("void Landed(")]
        self.assertIn("target != aimed && RuneOf(row->rune) == Rune::Ricochet", impact)

    def test_the_pierce_and_the_bounces_start_no_chain_and_the_bonus_adds_nothing_more(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (chaining || adding) return;", landed)
        self.assertIn("Scope scope(chaining);", landed)
        self.assertIn("if (rune == Rune::GrievousWounds && critical && !adding)", landed)
        self.assertIn('Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_bonus_pct"));', landed)
        self.assertLess(landed.index("Scope scope(adding);"), landed.index("if (chaining || adding) return;"))

    def test_the_pierce_takes_the_line_through_the_enemy_hit_and_not_that_enemy(self):
        pierce = self.code[self.code.index("void Pierce("):self.code.index("void Ricochet(")]
        self.assertIn("heading = player->GetAngle(first)", pierce)
        self.assertIn("if (enemy != first && OnLine(", pierce)
        self.assertIn('Tune("impale_pierce_width_yards")', pierce)

    def test_the_bounces_go_to_the_nearest_not_struck_yet_and_lose_the_factor(self):
        ricochet = self.code[self.code.index("void Ricochet("):self.code.index("} // namespace\n") if "} // namespace\n" in self.code else None]
        self.assertIn("Seek(distances, bearings, flags, radius, 0.0, 360.0, 1)", ricochet)
        self.assertIn("BouncePct(base, factor, bounce)", ricochet)
        self.assertIn("flags.push_back(std::find(struck.begin(), struck.end(), enemy) != struck.end());", ricochet)

    def test_the_stun_is_stretched_and_the_burn_rides_the_classes_damage_over_time(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', landed)
        self.assertIn('Abilities::Knockback(player, target, Tune("impale_impact_knockback_yards"));', landed)
        self.assertIn('Dot::Start(player, target, spellId, Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "dot_duration_seconds"), Tune("impale_chemical_burn_tick_seconds"));', landed)


if __name__ == "__main__":
    unittest.main()

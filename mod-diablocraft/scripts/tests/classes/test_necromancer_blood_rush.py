"""Blood Rush and its five runes (src/classes/necromancer/dc_necromancer_blood_rush*.{h,cpp}); the charges are the shared
combat/dc_charge_store.h (proved in test_necromancer_bone_spirit.py).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_blood_rush/harness.cpp compiles the real dc_necromancer_blood_rush_math.h and
    dc_charge_store.h with the sheet's rune names and numbers: each name is its rune; Hemostasis costs no Life and Metabolism twice the base;
    an enemy within the collision radius of the rush is passed through, measured from the segment; each enemy heals its share; Metabolism's
    two charges. Planted mutations must each turn it red.
  * **The numbers.** The sheet rows come from the tooltip and agree with the power file (decode_pow.py power P6_Necro_BloodRush: SF_3 0.05 and
    0.1, SF_4 0.02, SF_5 8, SF_6 2, SF_8 5, SF_11 2, SF_13 1, SF_35 50); the Life costs, the charges, the recharge and the collision radius are
    tunables with their SF cited.
  * **It is wired.** The dispatch answers Casting, Cast and Ground; the Life cost, the charge, the heal, the armor and the corpse.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_blood_rush.py
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
FOLDER = MODULE / "src/classes/necromancer"
HEADER = "src/classes/necromancer/dc_necromancer_blood_rush_math.h"
STORE = "src/combat/dc_charge_store.h"
HARNESS = MODULE / "tests/necromancer_blood_rush/harness.cpp"
CODE = FOLDER / "dc_necromancer_blood_rush.cpp"
SKILL = "Blood Rush"


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


def tune(name):
    return float(tunables()[name]["d3_value"])


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (HEADER, STORE)}
    if mutate:
        old, new = mutate
        key = HEADER[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("blood_rush_life_cost_pct"), tune("metabolism_life_cost_pct"), value("Transfusion", "heal_pct"),
               tune("blood_rush_collision_yards"), tune("metabolism_charges"), tune("blood_rush_recharge_seconds")]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::Molting;\n        return Rune::None;', 'return Rune::Potency;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Hemostasis")', 'if (name == "Hemostasiss")')),
            ("Hemostasis still costs Life", ("if (rune == Rune::Hemostasis)\n            return 0.0;", "if (rune == Rune::None)\n            return 0.0;")),
            ("Metabolism costs the base", ("rune == Rune::Metabolism ? metabolismPct : basePct", "basePct")),
            ("every rune costs double", ("rune == Rune::Metabolism ? metabolismPct : basePct", "metabolismPct")),
            ("a negative cost gives Life", ("return std::max(0.0, rune == Rune::Metabolism ? metabolismPct : basePct);", "return rune == Rune::Metabolism ? metabolismPct : basePct;")),
            ("the rush is a ray", ("std::clamp((wx * vx + wy * vy) / lengthSquared, 0.0, 1.0)", "std::max((wx * vx + wy * vy) / lengthSquared, 0.0)")),
            ("the rush is a line", ("std::clamp((wx * vx + wy * vy) / lengthSquared, 0.0, 1.0)", "(wx * vx + wy * vy) / lengthSquared")),
            ("the edge of the radius is out", ("return std::sqrt(px * px + py * py) <= radius;", "return std::sqrt(px * px + py * py) < radius;")),
            ("the radius is half", ("return std::sqrt(px * px + py * py) <= radius;", "return std::sqrt(px * px + py * py) <= radius / 2;")),
            ("a rush of no length passes everything", ("lengthSquared > 0 ? std::clamp(", "lengthSquared > 0 ? std::clamp(0.5 +")),
            ("an enemy heals the whole Life", ("maxLife * healPct / 100.0 * passed : 0.0", "maxLife * passed : 0.0")),
            ("the heal ignores the enemies", ("maxLife * healPct / 100.0 * passed : 0.0", "maxLife * healPct / 100.0 : 0.0")),
            ("a negative percent drains", ("return maxLife > 0 && healPct > 0 ?", "return maxLife > 0 ?")),
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
        self.assertEqual(runes(), ["Transfusion", "Hemostasis", "Metabolism", "Potency", "Molting"])

    def test_the_sheet_numbers_agree_with_the_power_file(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "distance_yards")], [5, 50])  # SF_8, SF_35
        self.assertEqual(value("Transfusion", "heal_pct"), 2)  # SF_4 0.02
        self.assertEqual([value("Potency", t) for t in ("armor_pct", "duration_seconds")], [100, 2])  # SF_13 1, SF_11

    def test_the_path_is_3_yards_wide_by_alexs_line_default_and_the_render_follows(self):
        # the power file gives the base no width: the designer's standing default for a line attack (AGENTS.md Numbers), no placeholder left
        row = next(r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual((row["target_type"], row["range_yards"], row["width_yards"]), ("line_to_point", "50", "3"))
        self.assertNotIn("width", row["unsure"])
        self.assertNotIn("placeholder", row["source"])
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        for spell in (85119, 85216, 85217, 85218, 85219, 85220):
            self.assertIn("(%d,'line_to_point','NUMERIC',50.0,0.0,3.0);" % spell, sql, spell)
            self.assertNotIn("(%d,'line_to_point','NUMERIC',50.0,0.0,2.0);" % spell, sql, spell)

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+?, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"armor_pct", "duration_seconds", "distance_yards", "heal_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "cooldown_seconds"), ("", "distance_yards"), ("Transfusion", "heal_pct"), ("Potency", "armor_pct"),
                            ("Potency", "duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"blood_rush_life_cost_pct": "5", "metabolism_life_cost_pct": "10", "metabolism_charges": "2",
               "blood_rush_recharge_seconds": "5", "blood_rush_collision_yards": "8"}  # SF_3, SF_3, SF_6, SF_9, SF_5

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                self.assertIn("decode_pow.py power P6_Necro_BloodRush", rows[name]["notes"])

    def test_the_cost_of_metabolism_is_double_the_base_and_the_recharge_is_the_cooldown(self):
        self.assertEqual(tune("metabolism_life_cost_pct"), 2 * tune("blood_rush_life_cost_pct"))
        self.assertEqual(tune("blood_rush_recharge_seconds"), value("", "cooldown_seconds"))

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("BloodRush::Casting(player, spellId);", self.dispatch)
        self.assertIn("BloodRush::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("BloodRush::Ground(player, spellId, center);", self.dispatch)

    def test_the_cast_takes_the_life_the_rune_says(self):
        self.assertIn('SpendLife(player, LifeCostPct(RuneAt(spellId), Tune("blood_rush_life_cost_pct"), Tune("metabolism_life_cost_pct")));', self.code)

    def test_metabolism_stores_charges_and_holds_or_clears_the_button(self):
        self.assertIn('unsigned const cap = unsigned(Tune("metabolism_charges"));', self.code)
        self.assertIn("wait = charges[player->GetGUID().GetRawValue()].Spend(Now(), cap, period);", self.code)
        self.assertIn("SendSkillCooldown(player, spellId, std::uint32_t(wait));", self.code)
        self.assertIn("ReducedCooldownMilliseconds(", self.code)

    def test_transfusion_heals_for_the_enemies_passed_between_the_start_and_where_the_rush_stops(self):
        self.assertIn('Numbers::Num(spellId, "distance_yards")', self.code)
        self.assertIn('Tune("blood_rush_collision_yards")', self.code)
        self.assertIn('Heal(player, spellId, TransfusionHeal(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), passed));', self.code)

    def test_potency_raises_armor_in_percent_for_its_seconds(self):
        self.assertIn('Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1,', self.code)
        self.assertIn('Numbers::Num(spellId, "duration_seconds"));', self.code)

    def test_molting_leaves_a_corpse_where_the_rush_began(self):
        self.assertIn("Position const start = player->GetPosition();", self.code)
        self.assertIn("Corpses::LeaveMade(player, start, 0);", self.code)


if __name__ == "__main__":
    unittest.main()

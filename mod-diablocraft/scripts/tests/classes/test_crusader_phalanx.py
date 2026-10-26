"""Phalanx and its five runes (src/classes/crusader/dc_crusader_phalanx.h and .cpp, data/d3/crusader_summons.csv).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_phalanx/harness.cpp compiles the real dc_crusader_phalanx.h with
    the sheets' own rune names and numbers: each rune name is its rune; the skill and two runes charge and the other three
    keep the avatars back; the three gated runes carry the internal cooldown and cost nothing (their records, test_phalanx_free_runes.py); the runes' charge speed
    is the power file's ratio; Stampede stuns under its chance and no other rune does; a bowman shoots at the fire rate; the
    run stops at the power's reach; avatars stand side by side. Seventeen mutations planted in a scratch copy must each make
    it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_phalanx.cpp reads by name is a row of
    crusader_skill_values.csv for Phalanx (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: 490% on the line, Bowmen 185% for 5 seconds, Shield Charge 180%, Stampede 490%
    with 30% for 2 seconds, the Bodyguard 2 avatars at 560% for 10 seconds. Every tunable it reads is a row of
    data/tunables/crusader.csv with the power file's number (Power/x1_Crusader_Phalanx3.pow) as its D3 value, or a closed card's
    number in the designer's column (the avatars' 24 yards a second, the Shield Bearers' look every 0.25 seconds).
  * **The creatures.** crusader_summons.csv names two summons from donors that exist in the core (no difficulty entries, a
    model), entries no other sheet owns; the migration is the generator's render of that sheet, and the generator is the one
    function the Wizard's and the Monk's summons are made by.
  * **Phalanx deals its line on the cast and nothing else.** BasePct is the skill's 490 for the charge runes, 0 for the rest.

What it does not prove: anything on a running server, or how the client draws the avatars.

    python mod-diablocraft/scripts/tests/classes/test_crusader_phalanx.py
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
HEADER = "src/classes/crusader/dc_crusader_phalanx.h"
SOURCES = [HEADER, "src/classes/crusader/dc_crusader_consecration.h", "tests/crusader_phalanx/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_phalanx.cpp"
CORE_SQL = REPO / "azerothcore-wotlk/data/sql/base/db_world"
UPDATES = MODULE / "data/sql/db-world/updates"
MIGRATION = UPDATES / "classes_0004_crusader_summons.sql"
SKILL = "Phalanx"
POW = "Power/x1_Crusader_Phalanx3.pow"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "crusader_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "crusader_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/crusader.csv") if r["name"].startswith("phalanx_")}


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
    binary = harness_env.build([MODULE / "tests/crusader_phalanx/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    rows = tunables()
    numbers = [float(rows["phalanx_charge_speed_base"]["d3_value"]), float(rows["phalanx_shield_charge_speed_bonus"]["d3_value"]),
               float(rows["phalanx_stampede_speed_bonus"]["d3_value"]), value("Stampede", "proc_chance_pct"),
               float(rows["phalanx_bowmen_fire_seconds"]["d3_value"]),
               value("Bowmen", "internal_cooldown_seconds"), float(rows["phalanx_charge_distance_yards"]["d3_value"])] + runes() + [
               float(rows["phalanx_charge_speed_yards_per_second"]["value"])]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 35, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Bodyguard;", "return Rune::Stampede;")),
            ("Bowmen charge", (HEADER, "case Rune::Bowmen:\n                return Behavior::Follow;", "case Rune::Bowmen:\n                return Behavior::Charge;")),
            ("the Bodyguard charges", (HEADER, "return Behavior::Fight;", "return Behavior::Charge;")),
            ("the gate is for every rune", (HEADER, "return FreeButGated(rune) && internalCooldown > 0 ? internalCooldown : 0.0;",
                                            "return internalCooldown > 0 ? internalCooldown : 0.0;")),
            ("Bodyguard is not gated", (HEADER, "rune == Rune::ShieldBearers || rune == Rune::Bodyguard;", "rune == Rune::ShieldBearers;")),
            ("the speed ratio loses its base", (HEADER, "return (base + std::max(0.0, bonus)) / base;", "return base + std::max(0.0, bonus);")),
            ("the sheet's speed is ignored", (HEADER, "yardsPerSecond / creatureYardsPerSecond : 1.0) * ratio", "1.0 : 1.0) * ratio")),
            ("the speed is not a multiple of the creature's", (HEADER, "yardsPerSecond / creatureYardsPerSecond : 1.0", "yardsPerSecond : 1.0")),
            ("the ratio is lost from the run rate", (HEADER, "1.0) * ratio;\n    }\n\n    // Stampede", "1.0);\n    }\n\n    // Stampede")),
            ("a negative bonus slows", (HEADER, "std::max(0.0, bonus)", "bonus")),
            ("any rune stuns", (HEADER, "return rune == Rune::Stampede && chancePct > 0 && roll < chancePct;", "return chancePct > 0 && roll < chancePct;")),
            ("a roll at the chance stuns", (HEADER, "roll < chancePct;", "roll <= chancePct;")),
            ("a shot a moment early", (HEADER, "clockMs >= fireSeconds * 1000.0", "clockMs > fireSeconds * 500.0")),
            ("the run ignores the reach", (HEADER, "std::min(1.0, reach / distance)", "1.0")),
            ("avatars stand on each other", (HEADER, "(double(index) - (double(count) - 1.0) / 2.0) * gap", "double(index) * gap")),
            ("the skill hits no line", (HEADER, "return BehaviorOf(rune) == Behavior::Charge;", "return false;")),
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
        self.assertEqual(runes(), ["Bowmen", "Shield Charge", "Stampede", "Shield Bearers", "Bodyguard"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [30, 490])
        self.assertEqual([value("Bowmen", t) for t in ("damage_pct", "duration_seconds", "internal_cooldown_seconds")], [185, 5, 15])
        self.assertEqual(value("Shield Charge", "damage_pct"), 180)
        self.assertEqual([value("Stampede", t) for t in ("damage_pct", "proc_chance_pct", "stun_duration_seconds")], [490, 30, 2])
        self.assertEqual(value("Shield Bearers", "internal_cooldown_seconds"), 15)
        self.assertEqual([value("Bodyguard", t) for t in ("pet_count", "duration_seconds", "damage_pct", "internal_cooldown_seconds")],
                         [2, 10, 560, 30])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "duration_seconds", "internal_cooldown_seconds", "pet_count",
                                  "proc_chance_pct", "stun_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "cost_resource"), ("", "damage_pct"), ("Bowmen", "damage_pct"), ("Bowmen", "duration_seconds"),
                            ("Bowmen", "internal_cooldown_seconds"), ("Shield Charge", "damage_pct"),
                            ("Stampede", "proc_chance_pct"), ("Stampede", "stun_duration_seconds"),
                            ("Shield Bearers", "internal_cooldown_seconds"), ("Bodyguard", "pet_count"),
                            ("Bodyguard", "duration_seconds"), ("Bodyguard", "damage_pct"),
                            ("Bodyguard", "internal_cooldown_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "phalanx_charge_distance_yards": "60",           # SF_1
        "phalanx_charge_speed_base": "0.4",              # SF_13
        "phalanx_shield_charge_speed_bonus": "0.2",      # SF_12
        "phalanx_stampede_speed_bonus": "0.3",           # SF_43
        "phalanx_shield_charge_bash_radius_yards": "12", # SF_21
        "phalanx_bowmen_fire_seconds": "0.6",            # SF_7
        "phalanx_shield_bearers_seconds": "5",           # SF_28
        "phalanx_shield_bearers_radius_yards": "5",      # SF_33
    }
    # Closed cards: the plain charge's speed from the d3planner Crusader simulator (q-1021-25, 0.4 yards a frame at 60 frames a second); the Shield Bearers' look from the standing default of a check with no sourced number (q-1021-26, 0.25 seconds).
    ANSWERED = {"phalanx_charge_speed_yards_per_second": "24", "phalanx_shield_bearers_check_seconds": "0.25"}
    CARDS = {"phalanx_charge_speed_yards_per_second": "q-1021-25", "phalanx_shield_bearers_check_seconds": "q-1021-26"}

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        self.assertEqual(set(rows), set(self.NUMBERS) | set(self.ANSWERED))
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertIn(POW, rows[name]["notes"])
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_closed_cards_have_no_placeholder_left(self):
        for name, number in self.ANSWERED.items():
            row = tunables()[name]
            self.assertEqual((row["d3_value"], row["value"]), ("", number))
            self.assertNotIn("PLACEHOLDER", row["notes"])
            self.assertIn(self.CARDS[name], row["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS) | set(self.ANSWERED))

    def test_the_check_placeholder_has_a_floor_and_the_run_reads_the_speed_through_the_header(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn("constexpr double CheckFloorSeconds = 0.1;", text)
        self.assertIn('std::max(CheckFloorSeconds, Tune("phalanx_shield_bearers_check_seconds"))', text)
        self.assertIn('Tune("phalanx_charge_speed_yards_per_second")', text)
        self.assertIn("RunRate(yps, baseMoveSpeed[MOVE_RUN], ratio)", text)


class Creatures(unittest.TestCase):
    def sheet(self):
        return read(D3 / "crusader_summons.csv")

    def test_two_summons_from_real_donors(self):
        rows = self.sheet()
        self.assertEqual([r["summon"] for r in rows], ["Avatar of the Order", "Warhorse of the Order"])
        self.assertEqual({r["script"] for r in rows}, {"dc_crusader_avatar"})
        self.assertEqual({r["skill"] for r in rows}, {SKILL})
        code = CODE.read_text(encoding="utf-8")
        self.assertIn(f"AvatarEntry = {rows[0]['entry']}, HorseEntry = {rows[1]['entry']};", code)
        templates = (CORE_SQL / "creature_template.sql").read_text(encoding="utf-8")
        models = (CORE_SQL / "creature_template_model.sql").read_text(encoding="utf-8")
        for r in rows:
            with self.subTest(r["summon"]):
                row = re.search(rf"^\({r['donor_creature']},(\d+),(\d+),(\d+),", templates, re.M)
                self.assertIsNotNone(row)
                self.assertEqual(row.groups(), ("0", "0", "0"))  # difficulty_entry_1..3: the clone would claim them
                self.assertRegex(models, rf"(?m)^\({r['donor_creature']},0,\d+,")
                self.assertTrue(r["why"])

    def test_no_entry_is_another_summons(self):
        mine = {int(r["entry"]) for r in self.sheet()}
        others = ({int(r["entry"]) for r in read(D3 / "wizard_summons.csv")} | {int(r["entry"]) for r in read(D3 / "monk_summons.csv")} |
                  {int(r["entry"]) for r in read(MODULE / "data/legendary_summons.csv")} | set(range(900100, 900103)))
        self.assertEqual(len(mine), 2)
        self.assertFalse(mine & others)
        self.assertIn("'data/d3/crusader_summons.csv'",
                      (MODULE / "scripts/generate/legendaries/generate_legendary_summons.py").read_text(encoding="utf-8"))

    def test_the_migration_is_the_generators_render_of_the_sheet(self):
        sys.path.insert(0, str(MODULE / "scripts"))
        import generate_crusader_summons
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(sql, generate_crusader_summons.render())
        self.assertEqual(sql.count("ScriptName='dc_crusader_avatar'"), 2)
        for r in self.sheet():
            with self.subTest(r["summon"]):
                self.assertIn(f"SET entry={r['entry']},name='{r['summon']}',subname='',npcflag=0,unit_flags=0,", sql)
                self.assertIn(f"INSERT INTO creature_template_model SELECT {r['entry']},Idx,", sql)
        names = sorted(p.name for p in UPDATES.glob("classes_*.sql"))
        self.assertEqual(names[-1], MIGRATION.name)

    def test_the_generator_refuses_a_taken_entry(self):
        sys.path.insert(0, str(MODULE / "scripts"))
        import generate_crusader_summons
        with self.assertRaises(ValueError):
            import tempfile
            import shutil
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "data/d3").mkdir(parents=True)
                for name in ("wizard_summons.csv", "monk_summons.csv"):
                    shutil.copy(D3 / name, root / "data/d3" / name)
                shutil.copy(MODULE / "data/legendary_summons.csv", root / "data/legendary_summons.csv")
                rows = self.sheet()
                rows[0]["entry"] = "900110"  # the Wizard's Mirror Image
                with (root / "data/d3/crusader_summons.csv").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                generate_crusader_summons.rows(root)


if __name__ == "__main__":
    unittest.main()

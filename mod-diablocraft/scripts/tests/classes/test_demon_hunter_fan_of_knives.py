"""Demon Hunter Fan of Knives and its five runes (src/classes/demon_hunter/dc_demon_hunter_fan_of_knives.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_fan_of_knives/harness.cpp compiles the real
    dc_demon_hunter_fan_of_knives.h with the sheets' own rune names and numbers: each rune name is its rune; Assassin's Knives
    throws at the enemies the fan did not reach (farther than its 20 yards), within the power file's 70, nearest first and no more
    than its 5, a tie keeping the order given. Six mutations planted in a scratch copy (two runes share a name, the knives reach
    the fan's own enemies, ignore the search radius, ignore the number, go farthest first, reverse a tie) must each make it fail.
  * **The records.** The shipped render gives the skill and its runes the cost and cooldown the sheets state: no cost and 10 seconds
    for the fan, Knives Expert 30 Hatred and no cooldown, Pinpoint Accuracy 15 seconds.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Fan of Knives
    (or the rune that states it) the engine can read: the slow of 60% for a second, Fan of Daggers' 3 second stun, Assassin's
    Knives' 620% to 5 enemies, Bladed Armor's 40% armor for 6 seconds; every tunable is a row of data/tunables/demonhunter.csv, and
    the numbers equal the decoded Power/DemonHunter_FanOfKnives.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the cast and the landing, the slow is every fan hit's but not a knife's, Fan of Daggers
    knocks back then stuns (stretched by the stun factor), Assassin's Knives throws once for each enemy picked and Bladed Armor gives
    its armor for its seconds.

What it does not prove: anything on a running server. The fan, the knives, the stun and the armor are
docs/test-diablocraft-vawmy.24.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_fan_of_knives.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_fan_of_knives.h"
SOURCES = [HEADER, "tests/demon_hunter_fan_of_knives/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_fan_of_knives.cpp"
SKILL = "Fan of Knives"
SHELLS = MODULE / "data/generated/spell_shells.sql"


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
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_fan_of_knives/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "radius_yards"), tune("fan_of_knives_knife_range_yards"), value("Assassin's Knives", "target_count")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 16, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Fan of Daggers")\n            return Rune::FanOfDaggers;',
                                        'if (name == "Fan of Daggers")\n            return Rune::KnivesExpert;')),
            ("the knives reach the fan's own enemies", (HEADER, "distances[i] > fanYards &&", "distances[i] >= 0 &&")),
            ("the knives ignore the search radius", (HEADER, "&& distances[i] <= searchYards", "")),
            ("the knives ignore the number", (HEADER, "if (picked.size() > most)\n            picked.resize(most);", "")),
            ("farthest first", (HEADER, "return distances[a] < distances[b];", "return distances[a] > distances[b];")),
            ("a tie reverses the order", (HEADER, "return distances[a] < distances[b];", "return distances[a] <= distances[b];")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Records(unittest.TestCase):
    def test_cost_and_cooldown_are_the_sheets(self):
        render = SHELLS.read_text(encoding="utf-8")
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", render).group(1).split(",")]
        first_string = columns.index("Name_Lang_enUS")
        ids = {r[1]: int(r[0]) for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
               if r and r[0].isdigit() and r[4] in ("active", "rune")}

        def record(name):
            row = re.search(r"^\(%d,[^\n]*" % ids[name], render, re.M)[0][1:]
            return dict(zip(columns[:first_string], row.split(",")[:first_string]))

        base = record(SKILL)
        self.assertEqual((base["ManaCost"], base["RecoveryTime"]), ("0", str(int(value("", "cooldown_seconds") * 1000))))
        expert = record(f"{SKILL} - Knives Expert")
        self.assertEqual((expert["ManaCost"], expert["RecoveryTime"]), (str(int(value("Knives Expert", "cost_resource"))), "0"))
        pinpoint = record(f"{SKILL} - Pinpoint Accuracy")
        self.assertEqual(pinpoint["RecoveryTime"], str(int(value("Pinpoint Accuracy", "cooldown_seconds") * 1000)))
        for rune in runes():
            if rune not in ("Knives Expert", "Pinpoint Accuracy"):
                self.assertEqual(record(f"{SKILL} - {rune}")["RecoveryTime"], base["RecoveryTime"], rune)


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["Knives Expert", "Assassin's Knives", "Fan of Daggers", "Pinpoint Accuracy", "Bladed Armor"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "damage_pct", "radius_yards", "slow_pct", "slow_duration_seconds")],
                         [10, 620, 20, 60, 1])
        self.assertEqual(value("Knives Expert", "cost_resource"), 30)
        self.assertEqual([value("Assassin's Knives", "damage_pct"), value("Assassin's Knives", "target_count")], [620, 5])
        self.assertEqual(value("Fan of Daggers", "stun_duration_seconds"), 3)
        self.assertEqual([value("Pinpoint Accuracy", "damage_pct"), value("Pinpoint Accuracy", "cooldown_seconds")], [1600, 15])
        self.assertEqual([value("Bladed Armor", "armor_pct"), value("Bladed Armor", "duration_seconds")], [40, 6])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("fan_of_knives_knockback_yards", "8", "SF_11"), ("fan_of_knives_knife_range_yards", "70", "SF_17")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"], rows[name]["unit"]), (d3, "", "yards"), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_FanOfKnives.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("fan_of_knives_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"slow_pct", "slow_duration_seconds", "stun_duration_seconds", "radius_yards", "target_count",
                                  "damage_pct", "armor_pct", "duration_seconds"})
        mapped = {(r["rune"], r["token"]) for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token in (("", "slow_pct"), ("", "slow_duration_seconds"), ("Fan of Daggers", "stun_duration_seconds"),
                            ("Assassin's Knives", "radius_yards"), ("Assassin's Knives", "target_count"),
                            ("Assassin's Knives", "damage_pct"), ("Bladed Armor", "armor_pct"), ("Bladed Armor", "duration_seconds"),
                            ("Fan of Daggers", "slow_pct"), ("Fan of Daggers", "slow_duration_seconds")):
            self.assertIn((rune, token), mapped, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_FanOfKnives.pow"))["sf"]

        def number(n):
            return float(sf[n])

        self.assertAlmostEqual(number(22) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(19), value("", "radius_yards"))
        self.assertAlmostEqual(number(20) * 100, value("", "slow_pct"))
        self.assertAlmostEqual(number(5), value("", "slow_duration_seconds"))
        self.assertAlmostEqual(number(26), value("", "cooldown_seconds"))
        self.assertAlmostEqual(float(sf[8].split("?")[1].split(":")[0]), value("Knives Expert", "cost_resource"))
        self.assertAlmostEqual(number(16) * 100, value("Assassin's Knives", "damage_pct"))
        self.assertAlmostEqual(number(13), value("Assassin's Knives", "target_count"))
        self.assertAlmostEqual(number(30), value("Fan of Daggers", "stun_duration_seconds"))
        self.assertAlmostEqual(number(18) * 100, value("Pinpoint Accuracy", "damage_pct"))
        self.assertAlmostEqual(number(26) + float(sf[27].split("?")[1].split(":")[0]), value("Pinpoint Accuracy", "cooldown_seconds"))
        self.assertAlmostEqual(number(14) * 100, value("Bladed Armor", "armor_pct"))
        self.assertAlmostEqual(number(15), value("Bladed Armor", "duration_seconds"))
        self.assertAlmostEqual(number(11), tune("fan_of_knives_knockback_yards"))
        self.assertAlmostEqual(number(17), tune("fan_of_knives_knife_range_yards"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        for call in ("FanOfKnives::Landed(player, target, spellId);", "FanOfKnives::Cast(player, spellId, targets);"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_slow_is_every_fan_hits_and_not_a_knifes(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Cast(")]
        self.assertIn("if (throwing || !player || !target || !Is(spellId)) return;", landed)
        self.assertIn('Slow(player, target, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"));', landed)

    def test_fan_of_daggers_knocks_back_and_stuns(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Cast(")]
        self.assertIn("if (RuneAt(spellId) == Rune::FanOfDaggers) {", landed)
        self.assertIn('Abilities::Knockback(player, target, Tune("fan_of_knives_knockback_yards"));', landed)
        self.assertIn('Stun(player, target, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));', landed)
        self.assertLess(landed.index("Abilities::Knockback"), landed.index("Stun(player"))

    def test_assassins_knives_throw_at_the_enemies_picked_and_are_no_fan(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("case Rune::AssassinsKnives:", cast)
        self.assertIn('ExtraTargets(distances, Numbers::Num(spellId, "radius_yards"), search, unsigned(Numbers::Num(spellId, "target_count")))', cast)
        self.assertIn('Combat::Strike(player, nearby[index], spellId, Numbers::Num(spellId, "damage_pct"));', cast)
        self.assertLess(cast.index("Scope scope(throwing);"), cast.index("Combat::Strike"))

    def test_bladed_armor_gives_its_armor_for_its_seconds(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1, Numbers::Num(spellId, "duration_seconds"));', cast)


if __name__ == "__main__":
    unittest.main()

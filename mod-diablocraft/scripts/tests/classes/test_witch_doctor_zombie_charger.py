"""Witch Doctor Zombie Charger and its five runes (src/classes/witch_doctor/dc_witch_doctor_zombie_charger.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_zombie_charger/harness.cpp compiles the real
    dc_witch_doctor_zombie_charger.h with the sheets' own rune names and numbers: each rune name is its rune; a zombie's path is a
    strip of the file's length and the standing width, its ends on it and nothing past them; the bears run side by side, centred;
    Lumbering Cold's zombies run evenly round from the aim; Pile On falls on the enemy within reach or ahead by the file's distance;
    Undeath reanimates on a kill up to its most; the nearest enemy within the search range. Eleven mutations planted in a scratch copy
    (two runes share a name, the path starts behind the Witch Doctor, runs past its length, is wider than its width or has no width
    check, the bears are not centred or not spaced, the zombies are not evenly round, the tower ignores the reach, Undeath goes on
    for ever, the nearest is the farthest) must each make it fail.
  * **The records.** The shipped render costs the skill and its runes the sheet's 150 Mana and no cooldown.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Zombie Charger
    (or the rune that states it) the engine can read: 560% for the skill, 520, 280, 880, 480 and 680 for the runes, Undeath's most of
    2 and Explosive Beast's 12 yards; every tunable is a row of data/tunables/witchdoctor.csv, and the numbers equal the decoded
    Power/Witchdoctor_ZombieCharger.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the three seams; the engine's line hits nothing for the runes that strike themselves; each
    rune's cast strikes what its shape reaches; Undeath reanimates only on a kill and not on its own reanimations.

What it does not prove: anything on a running server. The zombies, the bears, the tower, the reanimation and the beast are
docs/test-diablocraft-vxrcu.23.md's, live. The number of bears is a placeholder for the PM to card.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_zombie_charger.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_zombie_charger.h"
SOURCES = [HEADER, "tests/witch_doctor_zombie_charger/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_zombie_charger.cpp"
SKILL = "Zombie Charger"
SHELLS = MODULE / "data/generated/spell_shells.sql"
POWER = "Power/Witchdoctor_ZombieCharger.pow"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "witch_doctor_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "witch_doctor_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "witchdoctor.csv")}


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_zombie_charger/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("zombie_charger_path_yards"), tune("zombie_charger_path_width_yards"), tune("zombie_charger_bear_count"),
                         tune("zombie_charger_bear_spacing_yards"), tune("zombie_charger_cold_zombies"), tune("zombie_charger_tower_reach_yards"),
                         tune("zombie_charger_tower_distance_yards"), value("Undeath", "max_count")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Pile On")\n            return Rune::PileOn;', 'if (name == "Pile On")\n            return Rune::Undeath;')),
            ("the path starts behind", (HEADER, "return width > 0 && along >= 0 && along <= length", "return width > 0 && along >= -length && along <= length")),
            ("the path runs past its length", (HEADER, "&& along <= length &&", "&& along <= length * 2 &&")),
            ("the path is twice as wide", (HEADER, "std::fabs(across) <= width / 2;", "std::fabs(across) <= width;")),
            ("a path with no width reaches", (HEADER, "return width > 0 &&", "return")),
            ("the bears are not centred", (HEADER, "(double(bear) - (double(count) - 1.0) / 2.0) * spacing", "double(bear) * spacing")),
            ("the bears are not spaced", (HEADER, "(double(bear) - (double(count) - 1.0) / 2.0) * spacing", "(double(bear) - (double(count) - 1.0) / 2.0)")),
            ("the zombies are not evenly round", (HEADER, "TwoPi * double(zombie) / double(count)", "TwoPi * double(zombie) / double(count + 1)")),
            ("the tower ignores the reach", (HEADER, "return aimedYards && *aimedYards <= reach ? *aimedYards : distance;", "return aimedYards ? *aimedYards : distance;")),
            ("Undeath goes on for ever", (HEADER, "return killed && depth < most;", "return killed;")),
            ("the nearest is the farthest", (HEADER, "(!nearest || distances[i] < distances[*nearest])", "(!nearest || distances[i] > distances[*nearest])")),
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
    def test_the_skill_and_its_runes_cost_the_sheets_mana_and_have_no_cooldown(self):
        render = SHELLS.read_text(encoding="utf-8")
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", render).group(1).split(",")]
        first_string = columns.index("Name_Lang_enUS")
        ids = {r[1]: int(r[0]) for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
               if r and r[0].isdigit() and r[4] in ("active", "rune")}
        names = [n for n in ids if n == SKILL or n.startswith(SKILL + " - ")]
        self.assertEqual(len(names), 6)
        for name in names:
            with self.subTest(name):
                row = re.search(r"^\(%d,[^\n]*" % ids[name], render, re.M)[0][1:]
                record = dict(zip(columns[:first_string], row.split(",")[:first_string]))
                self.assertEqual((record["PowerType"], record["ManaCost"]), ("0", str(int(value("", "cost_resource")))))
                self.assertEqual(record["RecoveryTime"], "0")


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["Zombie Bears", "Lumbering Cold", "Pile On", "Undeath", "Explosive Beast"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [150, 560])
        self.assertEqual([value(r, "damage_pct") for r in runes()], [520, 280, 880, 480, 680])
        self.assertEqual([value("Undeath", "max_count"), value("Explosive Beast", "radius_yards")], [2, 12])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("zombie_charger_path_yards", "22", "SF_2"), ("zombie_charger_bear_spacing_yards", "3", "SF_22"),
                                 ("zombie_charger_bear_yards", "44", "SF_20"), ("zombie_charger_cold_zombies", "7", "SF_3"),
                                 ("zombie_charger_cold_slow_pct", "60", "SF_10"), ("zombie_charger_cold_slow_seconds", "2", "SF_30"),
                                 ("zombie_charger_tower_radius_yards", "7", "SF_16"), ("zombie_charger_tower_distance_yards", "21", "SF_17"),
                                 ("zombie_charger_tower_reach_yards", "15", "SF_26"), ("zombie_charger_undeath_search_yards", "22", "SF_15"),
                                 ("zombie_charger_undeath_path_yards", "22", "SF_13"), ("zombie_charger_beast_extra_yards", "35", "SF_29")):
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""))
                self.assertIn(source, rows[name]["notes"])
                self.assertIn(POWER, rows[name]["notes"])
                self.assertNotIn("placeholder", rows[name]["notes"].lower())
        width = rows["zombie_charger_path_width_yards"]
        self.assertEqual((width["d3_value"], width["value"]), ("", "3"))
        self.assertIn("standing default", width["notes"])
        # The bears' number is in no source D3 holds: a placeholder for the PM to card.
        bears = rows["zombie_charger_bear_count"]
        self.assertEqual((bears["d3_value"], bears["value"]), ("", "3"))
        self.assertIn("placeholder", bears["notes"].lower())
        self.assertEqual({n for n in rows if n.startswith("zombie_charger_")},
                         {"zombie_charger_path_yards", "zombie_charger_path_width_yards", "zombie_charger_bear_count", "zombie_charger_bear_spacing_yards",
                          "zombie_charger_bear_yards", "zombie_charger_cold_zombies", "zombie_charger_cold_slow_pct", "zombie_charger_cold_slow_seconds",
                          "zombie_charger_tower_radius_yards", "zombie_charger_tower_distance_yards", "zombie_charger_tower_reach_yards",
                          "zombie_charger_undeath_search_yards", "zombie_charger_undeath_path_yards", "zombie_charger_beast_extra_yards"})

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {n for n in tunables() if n.startswith("zombie_charger_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "max_count", "radius_yards"})
        mapped = {(r["rune"], r["token"]) for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for key in (("", "damage_pct"), ("Zombie Bears", "damage_pct"), ("Lumbering Cold", "damage_pct"), ("Pile On", "damage_pct"),
                    ("Undeath", "damage_pct"), ("Undeath", "max_count"), ("Explosive Beast", "damage_pct"), ("Explosive Beast", "radius_yards")):
            self.assertIn(key, mapped, key)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract(POWER))["sf"]

        def number(n):
            return float(sf[n])

        self.assertAlmostEqual(number(9) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(9) * float(sf[25].split("?")[1].split(":")[0]) * 100, value("Zombie Bears", "damage_pct"), places=0)
        self.assertAlmostEqual(number(9) * float(sf[23].split("?")[1].split(":")[0]) * 100, value("Lumbering Cold", "damage_pct"))
        self.assertAlmostEqual(number(6) * 100, value("Pile On", "damage_pct"))
        self.assertAlmostEqual(number(31) * 100, value("Undeath", "damage_pct"))
        self.assertAlmostEqual(number(24), value("Undeath", "max_count"))
        self.assertAlmostEqual(number(9) * float(sf[12].split("?")[1].split(":")[0]) * 100, value("Explosive Beast", "damage_pct"), places=0)
        self.assertAlmostEqual(number(11), value("Explosive Beast", "radius_yards"))
        self.assertAlmostEqual(float(sf[2].split("+")[0]), tune("zombie_charger_path_yards"))
        self.assertAlmostEqual(number(22), tune("zombie_charger_bear_spacing_yards"))
        self.assertAlmostEqual(float(sf[20].split("+")[0]), 40.0)
        self.assertAlmostEqual(40.0 + 4.0, tune("zombie_charger_bear_yards"))
        self.assertAlmostEqual(number(3), tune("zombie_charger_cold_zombies"))
        self.assertAlmostEqual(number(10) * 100, tune("zombie_charger_cold_slow_pct"))
        self.assertAlmostEqual(number(30), tune("zombie_charger_cold_slow_seconds"))
        self.assertAlmostEqual(number(16), tune("zombie_charger_tower_radius_yards"))
        self.assertAlmostEqual(number(17), tune("zombie_charger_tower_distance_yards"))
        self.assertAlmostEqual(number(26), tune("zombie_charger_tower_reach_yards"))
        self.assertAlmostEqual(number(15), tune("zombie_charger_undeath_search_yards"))
        self.assertAlmostEqual(number(13), tune("zombie_charger_undeath_path_yards"))
        self.assertAlmostEqual(float(sf[29].split("?")[1].split(":")[0]), tune("zombie_charger_beast_extra_yards"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto charge = ZombieCharger::BasePct(spellId)) return charge;"), 1)
        self.assertLess(self.dispatch.index("ZombieCharger::BasePct(spellId)"), self.dispatch.index("PoisonDart::BasePct(spellId)"))
        for call in ("ZombieCharger::Landed(player, target, spellId);", "ZombieCharger::Cast(player, spellId, targets);"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_engines_line_hits_only_for_the_skill_and_undeaths_first_zombie(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn('RuneAt(spellId) == Rune::Undeath ? std::optional<double>(Numbers::Num(BaseId(Skill), "damage_pct"))', base)
        self.assertIn(": RuneAt(spellId) == Rune::None ? std::nullopt : std::optional<double>(0.0);", base)

    def test_each_rune_strikes_what_its_shape_reaches(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn("rune == Rune::None || rune == Rune::Undeath) return;", cast)
        self.assertIn('BearOffsets(unsigned(Tune("zombie_charger_bear_count")), Tune("zombie_charger_bear_spacing_yards"))', cast)
        self.assertIn('RunningHeadings(unsigned(Tune("zombie_charger_cold_zombies")), aim)', cast)
        self.assertIn('Slow(player, enemy, Tune("zombie_charger_cold_slow_pct"), Tune("zombie_charger_cold_slow_seconds"));', cast)
        self.assertIn('Combat::Enemies(player, spellId, where, Tune("zombie_charger_tower_radius_yards"))', cast)
        self.assertIn('Combat::Enemies(player, spellId, aimed->GetPosition(), Numbers::Num(spellId, "radius_yards"))', cast)
        self.assertIn('length + Tune("zombie_charger_beast_extra_yards")', cast)

    def test_undeath_reanimates_on_a_kill_and_not_on_its_own_reanimations(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (reanimating || !player || !target || RuneAt(spellId) != Rune::Undeath || target->IsAlive()) return;", landed)
        self.assertIn("Holding holding(reanimating);", landed)
        reanimate = self.code[self.code.index("void Reanimate("):self.code.index("} // namespace\n") if "} // namespace\n" in self.code else None]
        self.assertIn('Reanimates(true, depth, unsigned(Numbers::Num(spellId, "max_count")))', self.code)
        self.assertIn('Tune("zombie_charger_undeath_search_yards")', self.code)
        self.assertIn('Tune("zombie_charger_undeath_path_yards"), Numbers::Num(spellId, "damage_pct")', self.code)
        self.assertIn("Reanimate(player, spellId, next, depth + 1);", self.code)


if __name__ == "__main__":
    unittest.main()

"""Demon Hunter Bolas and its five runes (src/classes/demon_hunter/dc_demon_hunter_bolas.h and .cpp, and the stun in
dc_demon_hunter_effects.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_bolas/harness.cpp compiles the real dc_demon_hunter_bolas.h with the
    sheets' own rune names and numbers: each rune name is its rune; the bola of a volley explodes at the fuse plus a shot's time for
    each place after the first; Imminent Doom's fuse is the longer one. Four mutations planted in a scratch copy (two runes share a
    name, the first bola waits a shot, the later bolas leave together, the shots' time is ignored) must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of demon_hunter_skill_values.csv for Bolas
    (or the rune that states it), the generated value map says whose record holds it, and the numbers are the researched ones: 4
    Hatred (7 for Thunder Ball), 160% to the enemy and 110% to the others within 14 yards (20 for Volatile Explosives) after 1 second,
    Freezing Strike's 3 bolas of 160% with a 50% freeze for 1 second, Bitter Pill's 15% for 2 Discipline, Imminent Doom's 216% and
    148% after 2 seconds. Every tunable it reads is a row of data/tunables/demonhunter.csv, and the sheet's and the tunables' numbers
    equal the decoded Power/DemonHunter_Bolas.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The class's dispatch hands the bola its two seams after the shot's, the bola lands for the power file's next to
    nothing and the explosion carries the damage, the explosion's strikes and a volley's landings start nothing, and a freeze is a
    stun stretched by the stun duration items.

What it does not prove: anything on a running server. The shot, the fuse, the explosion, the volley and the freeze are
docs/test-diablocraft-vawmy.8.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_bolas.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_bolas.h"
SOURCES = [HEADER, "tests/demon_hunter_bolas/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_bolas.cpp"
SKILL = "Bolas"


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_bolas/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "delay_seconds"), value("Imminent Doom", "delay_seconds"),
                         tune("bolas_freezing_strike_shot_delay_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 8, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::BitterPill;", "return Rune::ThunderBall;")),
            ("the first bola waits a shot", (HEADER, "return fuseSeconds + perShot * index;", "return fuseSeconds + perShot * (index + 1);")),
            ("the later bolas leave together", (HEADER, "return fuseSeconds + perShot * index;", "return fuseSeconds;")),
            ("the shots' time is ignored", (HEADER, "return fuseSeconds + perShot * index;", "return perShot * index;")),
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
        self.assertEqual(runes(), ["Volatile Explosives", "Freezing Strike", "Thunder Ball", "Bitter Pill", "Imminent Doom"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "generated_resource"), value("", "delay_seconds"), value("", "radius_yards")], [4, 1, 14])
        self.assertEqual([value("", "damage_pct", q) for q in ("primary", "other")], [160, 110])
        self.assertEqual(value("Volatile Explosives", "radius_yards"), 20)
        self.assertEqual([value("Freezing Strike", t) for t in ("projectile_count", "damage_pct", "proc_chance_pct", "freeze_duration_seconds")],
                         [3, 160, 50, 1])
        self.assertEqual(value("Thunder Ball", "generated_resource"), 7)
        self.assertEqual([value("Bitter Pill", t) for t in ("proc_chance_pct", "gain_resource")], [15, 2])
        self.assertEqual([value("Imminent Doom", "damage_pct", q) for q in ("primary", "other")], [216, 148])
        self.assertEqual([value("Imminent Doom", t) for t in ("radius_yards", "delay_seconds")], [14, 2])

    def test_the_tunables_are_the_power_files_and_nobody_has_set_them(self):
        rows = tunables()
        for name, number, source in (("bolas_impact_damage_pct", "0.01", "SF_10"), ("bolas_travel_yards", "75", "SF_3"),
                                     ("bolas_freezing_strike_cone_degrees", "90", "SF_12"),
                                     ("bolas_freezing_strike_shot_delay_seconds", "0.1", "SF_13")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Bolas.pow", rows[name]["notes"])
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("bolas_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"proc_chance_pct", "freeze_duration_seconds", "gain_resource", "damage_pct", "radius_yards",
                                  "projectile_count", "delay_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "damage_pct", "primary"), ("", "damage_pct", "other"), ("", "delay_seconds", ""),
                                       ("", "radius_yards", ""), ("Volatile Explosives", "radius_yards", ""),
                                       ("Freezing Strike", "damage_pct", ""), ("Freezing Strike", "projectile_count", ""),
                                       ("Freezing Strike", "proc_chance_pct", ""), ("Freezing Strike", "freeze_duration_seconds", ""),
                                       ("Bitter Pill", "proc_chance_pct", ""), ("Bitter Pill", "gain_resource", ""),
                                       ("Imminent Doom", "damage_pct", "primary"), ("Imminent Doom", "damage_pct", "other"),
                                       ("Imminent Doom", "delay_seconds", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], "own")

    def test_the_bola_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Bolas.pow"))["sf"]

        def number(n):
            return float(sf[n])

        def rune_part(n):
            return float(sf[n].split("?")[1].split(":")[0].strip(" ()"))

        self.assertAlmostEqual(number(0) * 100, value("", "damage_pct", "primary"))
        self.assertAlmostEqual(number(14) * 100, value("", "damage_pct", "other"))
        self.assertAlmostEqual(number(0) * rune_part(1) * 100, value("Imminent Doom", "damage_pct", "primary"))
        # The power file computes 110% x 1.35 = 148.5%; the tooltip (the sheet) shows it as 148.
        self.assertAlmostEqual(number(14) * rune_part(1) * 100, value("Imminent Doom", "damage_pct", "other"), delta=0.5 + 1e-9)
        self.assertAlmostEqual(number(0) * 100, value("Freezing Strike", "damage_pct"))
        self.assertAlmostEqual(number(5), value("", "radius_yards"))
        self.assertAlmostEqual(number(7), value("Volatile Explosives", "radius_yards"))
        self.assertAlmostEqual(number(11), value("", "delay_seconds"))
        self.assertAlmostEqual(number(8), value("Imminent Doom", "delay_seconds"))
        self.assertAlmostEqual(number(15), value("", "generated_resource"))
        self.assertAlmostEqual(number(15) + 3, value("Thunder Ball", "generated_resource"))
        self.assertAlmostEqual(number(24), value("Freezing Strike", "projectile_count"))
        self.assertAlmostEqual(number(16) * 100, value("Freezing Strike", "proc_chance_pct"))
        self.assertAlmostEqual(number(29), value("Freezing Strike", "freeze_duration_seconds"))
        self.assertAlmostEqual(number(31) * 100, value("Bitter Pill", "proc_chance_pct"))
        self.assertAlmostEqual(number(32), value("Bitter Pill", "gain_resource"))
        self.assertAlmostEqual(number(10) * 100, tune("bolas_impact_damage_pct"))
        for n, name in ((3, "bolas_travel_yards"), (12, "bolas_freezing_strike_cone_degrees"),
                        (13, "bolas_freezing_strike_shot_delay_seconds")):
            self.assertAlmostEqual(number(n), tune(name), msg=name)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_bola_its_seams_after_the_shots(self):
        self.assertEqual(self.dispatch.count("if (auto bola = Bolas::BasePct(spellId)) return bola;"), 1)
        self.assertLess(self.dispatch.index("EntanglingShot::BasePct(spellId)"), self.dispatch.index("Bolas::BasePct(spellId)"))
        self.assertEqual(self.dispatch.count("Bolas::Landed(player, target, spellId);"), 1)

    def test_the_bola_lands_for_next_to_nothing_for_every_rune(self):
        self.assertIn('return Tune("bolas_impact_damage_pct");', self.code)

    def test_the_explosions_and_the_volleys_start_nothing(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (exploding || volley || !player || !target || !row) return;", landed)
        self.assertIn("Scope scope(volley);", landed)
        explode = self.code[self.code.index("void Explode("):self.code.index("void Wrap(")]
        self.assertIn("Scope scope(exploding);", explode)

    def test_the_explosion_strikes_the_enemy_and_the_others_with_their_own_numbers(self):
        explode = self.code[self.code.index("void Explode("):self.code.index("void Wrap(")]
        self.assertIn('Combat::Strike(player, primary, spellId, Numbers::Num(spellId, "damage_pct", "primary"));', explode)
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct", "other"));', explode)
        self.assertIn("if (enemy != primary)", explode)
        self.assertIn('Combat::Enemies(player, spellId, last, Numbers::Num(spellId, "radius_yards"))', explode)

    def test_freezing_strike_strikes_alone_and_freezes_with_a_stretched_stun(self):
        explode = self.code[self.code.index("void Explode("):self.code.index("void Wrap(")]
        freezing = explode[explode.index("if (rune == Rune::FreezingStrike)"):explode.index("else {")]
        self.assertIn('Numbers::Num(spellId, "damage_pct")', freezing)
        self.assertNotIn("Enemies", freezing)
        self.assertIn("Freeze(player, primary, spellId);", freezing)
        freeze = self.code[self.code.index("void Freeze("):self.code.index("void Bite(")]
        self.assertIn('Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player)', freeze)

    def test_the_volley_follows_the_cone_and_spaces_the_bolas(self):
        volley = self.code[self.code.index("std::vector<Unit*> Volley("):self.code.index("bool Is(")]
        self.assertIn('Tune("bolas_freezing_strike_cone_degrees")', volley)
        self.assertIn("excluded.push_back(enemy == first);", volley)
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("ExplodesAfter(fuse, perShot, index++)", landed)
        self.assertLess(landed.index("Wrap(player, spellId, rune, target, fuse);"), landed.index("if (rune != Rune::FreezingStrike) return;"))

    def test_bitter_pill_pays_discipline_once_for_each_explosion(self):
        explode = self.code[self.code.index("void Explode("):self.code.index("void Wrap(")]
        self.assertEqual(explode.count("Bite(player, spellId);"), 1)
        bite = self.code[self.code.index("void Bite("):self.code.index("void Explode(")]
        self.assertIn("Resources::Energize(player, Resources::Discipline, spellId", bite)
        self.assertIn('Numbers::Num(spellId, "gain_resource")', bite)


if __name__ == "__main__":
    unittest.main()

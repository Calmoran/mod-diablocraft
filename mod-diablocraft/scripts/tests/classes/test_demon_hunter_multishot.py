"""Demon Hunter Multishot and its five runes (src/classes/demon_hunter/dc_demon_hunter_multishot.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_multishot/harness.cpp compiles the real dc_demon_hunter_multishot.h and the
    shared random pick with the sheets' own rune names and numbers: each rune name is its rune; Wind Chill's window is open for its
    seconds, to the millisecond; Suppression Fire knocks back the first hits and no others; Arsenal's rockets leave after the warmup,
    an interval apart. Seven mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The volley is the engine's cone (a `cone_enemies` row of skill_targeting.csv, 75 yards): its Hatred
    cost, Full Broadside's damage and Fire at Will's cost are the sheet's, read by the engine.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Multishot (or the
    rune that states it); every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_Multishot.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Cast`, `Landed`, `CritBonus`); the critical hit line passes the target; Wind
    Chill chills and opens the window for every attacker; Arsenal's volley is the skill's damage and its rockets are scheduled on the
    player's own event queue; Suppression Fire reads the hit's place among the cast's enemies.

What it does not prove: anything on a running server. The volley, the chill, the rockets and the knockback are
docs/test-diablocraft-vawmy.29.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_multishot.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_multishot.h"
PICK = "src/classes/demon_hunter/dc_demon_hunter_pick.h"
SOURCES = [HEADER, PICK, "tests/demon_hunter_multishot/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_multishot.cpp"
SKILL = "Multishot"
RUNES = ["Full Broadside", "Wind Chill", "Arsenal", "Fire at Will", "Suppression Fire"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_multishot/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("Wind Chill", "duration_seconds"), value("Suppression Fire", "target_count"),
                         value("Arsenal", "projectile_count"), tune("multishot_rocket_warmup_seconds"), tune("multishot_rocket_interval_seconds")]
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
            ("two runes share a name", (HEADER, 'if (name == "Wind Chill")\n            return Rune::WindChill;',
                                        'if (name == "Wind Chill")\n            return Rune::Arsenal;')),
            ("a window ignores its seconds", (HEADER, "return nowMs + std::uint64_t(seconds > 0 ? seconds * 1000.0 : 0.0);", "return nowMs;")),
            ("a window is open in its last millisecond too", (HEADER, "return nowMs < closesMs;", "return nowMs <= closesMs;")),
            ("one enemy too few is knocked back", (HEADER, "place >= 1 && place <= count", "place >= 1 && place < count")),
            ("a hit outside the cast is knocked back", (HEADER, "place >= 1 && place <= count", "place <= count")),
            ("the rockets leave together", (HEADER, "(intervalSeconds > 0 ? intervalSeconds : 0.0) * index", "0.0")),
            ("the rockets leave without a warmup", (HEADER, "(warmupSeconds > 0 ? warmupSeconds : 0.0) +", "0.0 +")),
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
        self.assertEqual(runes(), RUNES)

    def test_the_record_is_the_engines_cone(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"]), ("cone_enemies", "75"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [25, 360])
        self.assertEqual(value("Full Broadside", "damage_pct"), 500)
        self.assertEqual([value("Wind Chill", "crit_chance_pct"), value("Wind Chill", "duration_seconds")], [8, 3])
        self.assertEqual([value("Arsenal", "projectile_count"), value("Arsenal", "damage_pct")], [3, 300])
        self.assertEqual(value("Fire at Will", "cost_resource"), 18)
        self.assertEqual(value("Suppression Fire", "target_count"), 4)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("multishot_chill_pct", "60", "SF_16"), ("multishot_knockback_yards", "8", "SF_9"),
                                 ("multishot_rocket_range_yards", "75", "SF_4"), ("multishot_rocket_interval_seconds", "0.1", "SF_5"),
                                 ("multishot_rocket_warmup_seconds", "0.7", "SF_17")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Multishot.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("multishot_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("Arsenal", "damage_pct", "own"), ("Arsenal", "projectile_count", "own"),
                                    ("Wind Chill", "crit_chance_pct", "own"), ("Wind Chill", "duration_seconds", "own"),
                                    ("Suppression Fire", "target_count", "own"), ("Fire at Will", "cost_resource", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Multishot.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        def rune_value(n):
            return float(str(sf[n]).split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(12) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(12) * rune_value(11) * 100, value("Full Broadside", "damage_pct"), delta=1.0)
        self.assertAlmostEqual(number(13), value("", "cost_resource"))
        self.assertAlmostEqual(number(13) - rune_value(15), value("Fire at Will", "cost_resource"))
        self.assertAlmostEqual(number(1) * 100, value("Wind Chill", "crit_chance_pct"))
        self.assertAlmostEqual(number(2), value("Wind Chill", "duration_seconds"))
        self.assertAlmostEqual(number(3), value("Arsenal", "projectile_count"))
        self.assertAlmostEqual(rune_value(18) * 100, value("Arsenal", "damage_pct"))
        self.assertAlmostEqual(number(10), value("Suppression Fire", "target_count"))
        self.assertAlmostEqual(number(16) * 100, tune("multishot_chill_pct"))
        self.assertAlmostEqual(number(9), tune("multishot_knockback_yards"))
        self.assertAlmostEqual(number(4), tune("multishot_rocket_range_yards"))
        self.assertAlmostEqual(number(5), tune("multishot_rocket_interval_seconds"))
        self.assertAlmostEqual(number(17), tune("multishot_rocket_warmup_seconds"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        self.combat = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto salvo = Multishot::BasePct(spellId)) return salvo;"), 1)
        self.assertLess(self.dispatch.index("ElementalArrow::BasePct(spellId)"), self.dispatch.index("Multishot::BasePct(spellId)"))
        self.assertLess(self.dispatch.index("Multishot::BasePct(spellId)"), self.dispatch.index("return Caltrops::BasePct(spellId);"))
        for call in ("Multishot::Landed(player, target, spellId);", "Multishot::Cast(player, spellId, targets);",
                     "return Vault::CritBonus(spellId) + Multishot::CritBonus(target) + Passive::CritBonus(player, target);"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_critical_hit_line_passes_the_target(self):
        self.assertEqual(self.combat.count("+Necromancer::CritBonus(player, target)+DemonHunter::CritBonus(player, target, shell.spellId)+GemPowers::CritBonus"), 1)

    def test_arsenals_volley_is_the_skills_damage_and_its_rockets_are_scheduled(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn('RuneAt(spellId) == Rune::Arsenal ? std::optional<double>(Numbers::Num(BaseId(Skill), "damage_pct")) : std::nullopt', base)
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn('unsigned(Numbers::Num(spellId, "projectile_count"))', cast)
        self.assertIn("player->m_Events.AddEventAtOffset( [player, spellId] { Rocket(player, spellId); },", cast)
        self.assertIn('RocketDelayMs(index, Tune("multishot_rocket_warmup_seconds"), Tune("multishot_rocket_interval_seconds"))', cast)
        rocket = self.code[self.code.index("void Rocket("):self.code.index("bool Is(")]
        self.assertIn('Tune("multishot_rocket_range_yards")', rocket)
        self.assertIn('Combat::Strike(player, enemies[PickAt(frand(0.0f, 1.0f), enemies.size())], spellId, Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(player));', rocket)

    def test_wind_chill_chills_and_opens_the_window_for_every_attacker(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("double CritBonus(")]
        self.assertIn('Slow(player, target, Tune("multishot_chill_pct"), seconds);', landed)
        self.assertIn('chilled[target->GetGUID().GetRawValue()] = {ClosesAt(now, seconds), Numbers::Num(spellId, "crit_chance_pct")};', landed)
        bonus = self.code[self.code.index("double CritBonus("):]
        self.assertIn("Open(found->second.closes, Now()) ? found->second.pct : 0.0", bonus)
        self.assertNotIn("player", bonus)

    def test_suppression_fire_reads_the_hits_place_among_the_casts_enemies(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("double CritBonus(")]
        self.assertIn('KnockedBack(ItemPowers::HitPlace(), unsigned(Numbers::Num(spellId, "target_count")))', landed)
        self.assertIn('Abilities::Knockback(player, target, Tune("multishot_knockback_yards"));', landed)


if __name__ == "__main__":
    unittest.main()

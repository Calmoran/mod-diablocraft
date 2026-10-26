"""Demon Hunter Entangling Shot and its five runes (src/classes/demon_hunter/dc_demon_hunter_entangling_shot.h and .cpp, the
slow in dc_demon_hunter_effects.cpp and the damage over time in dc_demon_hunter_dot.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_entangling_shot/harness.cpp compiles the real
    dc_demon_hunter_entangling_shot.h and dc_demon_hunter_dot.h with the sheets' own rune names and numbers: each rune name is its
    rune; a first shot entangles the enemy hit and the nearest others up to the sheet's count (2, Chain Gang's 4); a shot at an enemy
    still entangled keeps and refreshes everyone entangled, fills the room left from the nearest and never goes over the count; a
    shot at another enemy starts afresh; a tie that has run out is gone, the moment it runs out included; Shock Collar's 80% is
    spread over its 2 seconds in whole ticks of the tunable length. Nine mutations planted in a scratch copy (two runes share a
    name, the shot does not entangle the enemy it hit, ignores the link, keeps a tie that ran out, counts a lapsed tie as a link,
    goes over the count, entangles an enemy twice, and the ticks round up or deal the whole damage each) must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of demon_hunter_skill_values.csv for
    Entangling Shot (or the rune that states it), the generated value map says whose record holds it, and the numbers are the
    researched ones: 200%, 4 Hatred (7 for Justice is Served), 2 enemies entangled (4 for Chain Gang), a 60% slow for 2 seconds
    (4 seconds for Heavy Burden, 80% for Bounty Hunter), Shock Collar's 80% over 2 seconds. Every tunable it reads is a row of
    data/tunables/demonhunter.csv, and the sheet's and the tunables' numbers equal the decoded
    Power/X1_DemonHunter_EntanglingShot.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The class's dispatch hands the shot its two seams after the arrow's, the shot's hit is the skill's for every rune,
    and Shock Collar's damage reaches every enemy entangled.

What it does not prove: anything on a running server. The shot, the slow and its refresh and the lightning are
docs/test-diablocraft-vawmy.7.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_entangling_shot.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_entangling_shot.h"
DOT = "src/classes/demon_hunter/dc_demon_hunter_dot.h"
SOURCES = [HEADER, DOT, "tests/demon_hunter_entangling_shot/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_entangling_shot.cpp"
SKILL = "Entangling Shot"


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_entangling_shot/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "target_count"), value("Chain Gang", "target_count"), value("Shock Collar", "damage_pct"),
                         value("Shock Collar", "dot_duration_seconds"), tune("entangling_shot_shock_collar_tick_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 24, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::ChainGang;", "return Rune::ShockCollar;")),
            ("the shot does not entangle the enemy it hit", (HEADER, "group.push_back(primary);", "(void)primary;")),
            ("the shot ignores the link", (HEADER, "if (linked)", "if (false)")),
            ("a tie that ran out is kept", (HEADER, "if (tie.untilMs > nowMs && group.size() < count && !has(tie.enemy))",
                                            "if (group.size() < count && !has(tie.enemy))")),
            ("a lapsed tie is a link", (HEADER, "tie.enemy == primary && tie.untilMs > nowMs", "tie.enemy == primary")),
            ("the shot goes over the count", (HEADER, "if (group.size() < count && !has(enemy))", "if (!has(enemy))")),
            ("an enemy is entangled twice", (HEADER, "if (group.size() < count && !has(enemy))", "if (group.size() < count)")),
            ("a chained enemy takes the engine's hit", (HEADER, "return isTheEnemyShotAt;", "return true;")),
            ("the enemy shot at takes no engine hit", (HEADER, "return isTheEnemyShotAt;", "return false;")),
            ("the ticks round up", (DOT, "std::floor(seconds / tickSeconds + 1e-9)", "std::ceil(seconds / tickSeconds + 1e-9)")),
            ("each tick deals the whole damage", (DOT, "return ticks ? totalPct / ticks : 0.0;", "return ticks ? totalPct : 0.0;")),
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
        self.assertEqual(runes(), ["Heavy Burden", "Chain Gang", "Shock Collar", "Justice is Served", "Bounty Hunter"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("generated_resource", "damage_pct", "target_count", "slow_pct", "slow_duration_seconds")],
                         [4, 200, 2, 60, 2])
        self.assertEqual(value("Heavy Burden", "slow_duration_seconds"), 4)
        self.assertEqual(value("Chain Gang", "target_count"), 4)
        self.assertEqual([value("Shock Collar", t) for t in ("damage_pct", "dot_duration_seconds")], [80, 2])
        self.assertEqual(value("Justice is Served", "generated_resource"), 7)
        self.assertEqual(value("Bounty Hunter", "slow_pct"), 80)

    def test_the_tunables(self):
        rows = tunables()
        search = rows["entangling_shot_search_yards"]
        self.assertEqual((search["d3_value"], search["value"]), ("80", ""))
        self.assertIn("SF_17", search["notes"])
        self.assertIn("Power/X1_DemonHunter_EntanglingShot.pow", search["notes"])
        tick = rows["entangling_shot_shock_collar_tick_seconds"]
        # The designer's standing default for a damage over time (AGENTS.md "Numbers", 2026-10-22), set in his column.
        self.assertEqual((tick["d3_value"], tick["value"]), ("", "0.5"))
        self.assertIn("standing default", tick["notes"])
        for name in ("entangling_shot_search_yards", "entangling_shot_shock_collar_tick_seconds"):
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("entangling_shot_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "target_count", "slow_duration_seconds", "slow_pct", "dot_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("", "target_count", "own"), ("", "slow_pct", "own"),
                                    ("", "slow_duration_seconds", "own"), ("Heavy Burden", "slow_duration_seconds", "own"),
                                    ("Chain Gang", "target_count", "own"), ("Shock Collar", "damage_pct", "own"),
                                    ("Shock Collar", "dot_duration_seconds", "own"), ("Bounty Hunter", "slow_pct", "own"),
                                    ("Shock Collar", "target_count", "inherited"), ("Bounty Hunter", "slow_duration_seconds", "inherited")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, "")]["origin"], origin)

    def test_the_shot_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/X1_DemonHunter_EntanglingShot.pow"))["sf"]

        def number(n):
            return float(sf[n])

        def rune_part(n):
            return float(sf[n].split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(5) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(1), value("", "generated_resource"))
        self.assertAlmostEqual(number(1) + rune_part(10), value("Justice is Served", "generated_resource"))
        self.assertAlmostEqual(number(16) * 100, value("", "slow_pct"))
        self.assertAlmostEqual((number(16) + rune_part(11)) * 100, value("Bounty Hunter", "slow_pct"))
        self.assertAlmostEqual(number(9), value("", "slow_duration_seconds"))
        self.assertAlmostEqual(number(9) + rune_part(6), value("Heavy Burden", "slow_duration_seconds"))
        # The power file counts the enemies entangled besides the one hit; the tooltip counts that one too.
        self.assertAlmostEqual(number(14) + 1, value("", "target_count"))
        self.assertAlmostEqual(number(14) + rune_part(7) + 1, value("Chain Gang", "target_count"))
        # Shock Collar's scalar is for each second of the rune's seconds.
        self.assertAlmostEqual(rune_part(8) * 100 * value("Shock Collar", "dot_duration_seconds"), value("Shock Collar", "damage_pct"))
        self.assertAlmostEqual(number(17), tune("entangling_shot_search_yards"))

    def test_the_record_carries_the_entangle_count_in_the_cores_chain_slot(self):
        # The premise of the Impact seam below: target_count is read back from the record's chain slot, so the core chains the shot
        # to that many more enemies.
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        self.assertEqual(mapped[("", "target_count")]["source"], "chain")
        self.assertEqual(mapped[("Chain Gang", "target_count")]["source"], "chain")

    def test_the_hit_is_the_skills_for_every_rune(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct");', text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_shot_its_seams_after_the_arrows(self):
        self.assertEqual(self.dispatch.count("if (auto shot = EntanglingShot::BasePct(spellId)) return shot;"), 1)
        self.assertLess(self.dispatch.index("HungeringArrow::BasePct(spellId)"), self.dispatch.index("EntanglingShot::BasePct(spellId)"))
        self.assertEqual(self.dispatch.count("EntanglingShot::Landed(player, target, spellId);"), 1)

    def test_a_chained_enemy_is_left_to_the_entangle_and_takes_no_engine_hit(self):
        impact = self.code[self.code.index("bool Impact("):self.code.index("void Landed(")]
        self.assertIn("return player && target && aimed && RowOf(spellId, Skill) && !LeftToEngine(target == aimed);", impact)
        self.assertIn("EvasiveFire::Impact(player, target, aimed, cone, spellId) || Impale::Impact(player, target, aimed, spellId) || EntanglingShot::Impact(player, target, aimed, spellId)", self.dispatch)
        # the entangle itself is the primary's landing: it picks the others by distance, whoever the core chained to
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("Nearest(player, spellId, target, count)", landed)

    def test_the_slow_and_the_damage_reach_everyone_entangled(self):
        landed = self.code[self.code.index("void Landed("):]
        loop = landed[landed.index("for (std::uint64_t guid : group)"):]
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), seconds);', loop)
        self.assertIn("if (shock) Dot::Start(player, enemy, spellId,", loop)
        self.assertIn("RuneOf(row->rune) == Rune::ShockCollar", landed)

    def test_the_ties_are_kept_for_the_next_shot_and_cover_the_slows_seconds(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("group = Entangled(ties, now, target->GetGUID().GetRawValue(), nearest, count);", landed)
        self.assertIn("ties.push_back({enemy, now + std::uint64_t(seconds * 1000)});", landed)

    def test_the_others_are_the_nearest_of_the_search_radius_and_never_the_enemy_hit(self):
        nearest = self.code[self.code.index("Nearest(Player* player"):self.code.index("bool Is(")]
        self.assertIn('Tune("entangling_shot_search_yards")', nearest)
        self.assertIn("excluded.push_back(enemy == primary);", nearest)
        self.assertIn("Seek(distances, bearings, excluded, radius, 0.0, 360.0, count)", nearest)


if __name__ == "__main__":
    unittest.main()

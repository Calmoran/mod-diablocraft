"""Demon Hunter Cluster Arrow and its five runes (src/classes/demon_hunter/dc_demon_hunter_cluster_arrow.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_cluster_arrow/harness.cpp compiles the real dc_demon_hunter_cluster_arrow.h
    and the shared pick with the sheets' own rune names and numbers: each rune name is its rune; a grenade lands inside its ring in any
    direction; Cluster Bombs' line (the first bomb a share along it, the last at its end, strayed to either side, in any heading) and its
    spawn interval; the rockets go to the nearest enemies; Maelstrom's share of the Life; Dazzling Arrow's chance edge to edge. Eleven
    mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The cast is the engine's ground cast (a `ground_area` row of skill_targeting.csv, radius 15): the
    impact explosion, Loaded for Bear's bigger one, the cost and the schools are the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Cluster Arrow (or the
    rune that states it); every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_ClusterArrow.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Ground`, `Landed`); the impact is the skill's number and Cluster Bombs' is none;
    the grenades land round the impact and only they may stun; the rockets and bombs are scheduled on the player's own event queue.

What it does not prove: anything on a running server. The explosion, the grenades, the rockets and the bombs are
docs/test-diablocraft-vawmy.30.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_cluster_arrow.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_cluster_arrow.h"
PICK = "src/classes/demon_hunter/dc_demon_hunter_pick.h"
SOURCES = [HEADER, PICK, "tests/demon_hunter_cluster_arrow/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_cluster_arrow.cpp"
SKILL = "Cluster Arrow"
RUNES = ["Loaded for Bear", "Shooting Stars", "Cluster Bombs", "Maelstrom", "Dazzling Arrow"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_cluster_arrow/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("cluster_arrow_grenade_offset_min_yards"), tune("cluster_arrow_grenade_offset_delta_yards"),
                         tune("cluster_arrow_bombs_count"), tune("cluster_arrow_bombs_distance_yards"), tune("cluster_arrow_bomb_interval_seconds"),
                         tune("cluster_arrow_bomb_spread_yards"), value("Maelstrom", "heal_pct"), value("Dazzling Arrow", "proc_chance_pct")]
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
            ("two runes share a name", (HEADER, 'if (name == "Maelstrom")\n            return Rune::Maelstrom;',
                                        'if (name == "Maelstrom")\n            return Rune::ShootingStars;')),
            ("a grenade lands the extra only", (HEADER, "double const yards = minYards + deltaYards * distanceRoll;", "double const yards = deltaYards * distanceRoll;")),
            ("a grenade's heading is half a turn", (HEADER, "headingRoll * 2.0 * 3.14159265358979323846", "headingRoll * 3.14159265358979323846")),
            ("the first bomb lands at the start", (HEADER, "distance * double(index + 1) / double(count)", "distance * double(index) / double(count)")),
            ("the side is mirrored", (HEADER, "y + std::sin(heading) * along + std::cos(heading) * side", "y + std::sin(heading) * along - std::cos(heading) * side")),
            ("the bombs drop together", (HEADER, "* 1000.0 * index + 0.5", "* 1000.0 + 0.5")),
            ("Maelstrom heals the whole Life", (HEADER, "(maxLife > 0 ? maxLife : 0.0) * (pct > 0 ? pct : 0.0) / 100.0", "(maxLife > 0 ? maxLife : 0.0)")),
            ("a roll at the chance stuns", (HEADER, "return roll < chancePct;", "return roll <= chancePct;")),
            ("the farthest enemies are chosen", (PICK, "return distances[a] < distances[b];", "return distances[a] > distances[b];")),
            ("every enemy is chosen", (PICK, "order.resize(std::min(order.size(), count));", "")),
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

    def test_the_record_is_the_engines_ground_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("ground_area", "15"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct", "impact"), value("", "projectile_count"),
                          value("", "damage_pct", "grenade")], [40, 650, 4, 250])
        self.assertEqual(value("Loaded for Bear", "damage_pct"), 850)
        self.assertEqual([value("Shooting Stars", "max_count"), value("Shooting Stars", "damage_pct")], [2, 600])
        self.assertEqual(value("Cluster Bombs", "damage_pct"), 650)
        self.assertEqual([value("Maelstrom", n) for n in ("max_count", "damage_pct", "heal_pct")], [3, 450, 2])
        self.assertEqual([value("Dazzling Arrow", "proc_chance_pct"), value("Dazzling Arrow", "stun_duration_seconds")], [100, 1.5])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("cluster_arrow_grenade_radius_yards", "5", "SF_6"), ("cluster_arrow_grenade_offset_min_yards", "4", "SF_20"),
                                 ("cluster_arrow_grenade_offset_delta_yards", "4", "SF_21"), ("cluster_arrow_rocket_range_yards", "60", "SF_10"),
                                 ("cluster_arrow_rocket_delay_seconds", "0.8", "SF_11"), ("cluster_arrow_bombs_count", "5", "SF_2"),
                                 ("cluster_arrow_bombs_distance_yards", "35", "SF_27"), ("cluster_arrow_bomb_interval_seconds", "0.17", "SF_39"),
                                 ("cluster_arrow_bomb_spread_yards", "3", "SF_37")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_ClusterArrow.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("cluster_arrow_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, qualifier, origin in (("", "damage_pct", "impact", "own"), ("", "damage_pct", "grenade", "own"), ("", "projectile_count", "", "own"),
                                               ("Loaded for Bear", "damage_pct", "grenade", "inherited"), ("Dazzling Arrow", "damage_pct", "grenade", "inherited"),
                                               ("Shooting Stars", "max_count", "", "own"), ("Shooting Stars", "damage_pct", "", "own"),
                                               ("Maelstrom", "heal_pct", "", "own"), ("Cluster Bombs", "damage_pct", "", "own"),
                                               ("Dazzling Arrow", "proc_chance_pct", "", "own"), ("Dazzling Arrow", "stun_duration_seconds", "", "own")):
            self.assertEqual(mapped[(rune, token, qualifier)]["origin"], origin, (rune, token, qualifier))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_ClusterArrow.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        def rune_value(n):
            return float(str(sf[n]).split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(3), value("", "cost_resource"))
        self.assertAlmostEqual(number(36) * 100, value("", "damage_pct", "impact"))
        self.assertAlmostEqual(number(4), value("", "projectile_count"))
        self.assertAlmostEqual(number(5) * 100, value("", "damage_pct", "grenade"))
        self.assertAlmostEqual(number(36) * rune_value(7) * 100, value("Loaded for Bear", "damage_pct"), delta=1.0)
        self.assertAlmostEqual(number(9), value("Shooting Stars", "max_count"))
        self.assertAlmostEqual(number(14) * 100, value("Shooting Stars", "damage_pct"))
        self.assertAlmostEqual(number(8) * 100, value("Cluster Bombs", "damage_pct"))
        self.assertAlmostEqual(number(15), value("Maelstrom", "max_count"))
        self.assertAlmostEqual(number(40) * 100, value("Maelstrom", "damage_pct"))
        self.assertAlmostEqual(number(18) * 100, value("Maelstrom", "heal_pct"))
        self.assertAlmostEqual(number(12) * 100, value("Dazzling Arrow", "proc_chance_pct"))
        self.assertAlmostEqual(number(13), value("Dazzling Arrow", "stun_duration_seconds"))
        self.assertAlmostEqual(number(6), tune("cluster_arrow_grenade_radius_yards"))
        self.assertAlmostEqual(number(20), tune("cluster_arrow_grenade_offset_min_yards"))
        self.assertAlmostEqual(number(21), tune("cluster_arrow_grenade_offset_delta_yards"))
        self.assertAlmostEqual(number(10), tune("cluster_arrow_rocket_range_yards"))
        self.assertAlmostEqual(number(11), tune("cluster_arrow_rocket_delay_seconds"))
        self.assertAlmostEqual(number(2), tune("cluster_arrow_bombs_count"))
        self.assertAlmostEqual(number(27), tune("cluster_arrow_bombs_distance_yards"))
        self.assertAlmostEqual(number(39), tune("cluster_arrow_bomb_interval_seconds"))
        self.assertAlmostEqual(number(37), tune("cluster_arrow_bomb_spread_yards"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto burst = ClusterArrow::BasePct(spellId)) return burst;"), 1)
        self.assertLess(self.dispatch.index("ElementalArrow::BasePct(spellId)"), self.dispatch.index("ClusterArrow::BasePct(spellId)"))
        self.assertLess(self.dispatch.index("ClusterArrow::BasePct(spellId)"), self.dispatch.index("return Caltrops::BasePct(spellId);"))
        for call in ("ClusterArrow::Landed(player, target, spellId);", "ClusterArrow::Ground(player, spellId, center);"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_impact_is_the_skills_number_loaded_for_bears_own_and_cluster_bombs_none(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Ground(")]
        self.assertIn('case Rune::LoadedForBear: return Numbers::Num(spellId, "damage_pct");', base)
        self.assertIn("case Rune::ClusterBombs: return 0.0;", base)
        self.assertIn('Numbers::Num(spellId, "damage_pct", "impact")', base)
        self.assertIn('Numbers::Num(BaseId(Skill), "damage_pct", "impact")', base)

    def test_the_grenades_land_round_the_impact_and_only_they_may_stun(self):
        grenades = self.code[self.code.index("void Grenades("):self.code.index("void Rockets(")]
        self.assertIn("Scope scope(grenading);", grenades)
        self.assertIn('unsigned(Numbers::Num(spellId, "projectile_count"))', grenades)
        self.assertIn('Tune("cluster_arrow_grenade_offset_min_yards"), Tune("cluster_arrow_grenade_offset_delta_yards")', grenades)
        self.assertIn('Numbers::Num(spellId, "damage_pct", "grenade")', grenades)
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("!grenading || RuneAt(spellId) != Rune::DazzlingArrow", landed)
        self.assertIn('Stuns(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct"))', landed)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', landed)

    def test_the_rockets_go_to_the_nearest_enemies_after_the_delay(self):
        rockets = self.code[self.code.index("void Rockets("):self.code.index("void Bombs(")]
        self.assertIn('Tune("cluster_arrow_rocket_range_yards")', rockets)
        self.assertIn('NearestFirst(distances, std::size_t(Numbers::Num(spellId, "max_count")))', rockets)
        self.assertIn("player->m_Events.AddEventAtOffset(", rockets)
        self.assertIn('Tune("cluster_arrow_rocket_delay_seconds") * 1000.0', rockets)
        self.assertIn('Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(player)) && RuneAt(spellId) == Rune::Maelstrom', rockets)
        self.assertIn('Heal(player, spellId, Healed(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct")));', rockets)

    def test_the_bombs_are_dropped_along_the_line_every_interval(self):
        bombs = self.code[self.code.index("void Bombs("):self.code.index("} // namespace")]
        self.assertIn("start.GetAbsoluteAngle(&center)", bombs)
        self.assertIn('Tune("cluster_arrow_bombs_distance_yards")', bombs)
        self.assertIn('Tune("cluster_arrow_bomb_spread_yards")', bombs)
        self.assertIn('BombDelayMs(i, Tune("cluster_arrow_bomb_interval_seconds"))', bombs)
        self.assertIn('Explode(player, spellId, at, Numbers::Num(spellId, "damage_pct"));', bombs)
        ground = self.code[self.code.index("void Ground("):self.code.index("void Landed(")]
        self.assertIn("case Rune::ShootingStars: case Rune::Maelstrom: Rockets(player, spellId, center); break;", ground)
        self.assertIn("case Rune::ClusterBombs: Bombs(player, spellId, center); break;", ground)


if __name__ == "__main__":
    unittest.main()

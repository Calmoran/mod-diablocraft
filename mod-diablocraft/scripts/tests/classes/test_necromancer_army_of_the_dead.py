"""Army of the Dead and its five runes (src/classes/necromancer/dc_necromancer_army_of_the_dead*.{h,cpp}).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_army_of_the_dead/harness.cpp compiles the real
    dc_necromancer_army_of_the_dead_math.h with the sheet's rune names and the sheet and tunable numbers: each name is its rune; a total
    cut into blasts, hands, waves, attacks or ticks adds back to the sheet's damage; the blows are evenly spaced from the first; Frozen
    Army's line has its edge; Death Valley's pull closes in the steps the radii and the segment make. Planted mutations must each turn
    it red.
  * **The numbers.** Every number the cast reads is a sheet row (tooltip) or a tunable from the power file
    (decode_pow.py power P6_Necro_SkeleBomb, the SF cited in each note); the power's totals (SF_1 120, SF_30 140, SF_5 120, SF_15 500,
    SF_24 155) agree with the tooltip's.
  * **It is wired.** The dispatch answers BasePct, Casting and Ground; each rune's part; Dead Storm's Life cost.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_army_of_the_dead.py
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
HEADER = "src/classes/necromancer/dc_necromancer_army_of_the_dead_math.h"
HARNESS = MODULE / "tests/necromancer_army_of_the_dead/harness.cpp"
CODE = FOLDER / "dc_necromancer_army_of_the_dead.cpp"
SKILL = "Army of the Dead"


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
    key = HEADER[len("src/"):]
    files = {key: (MODULE / HEADER).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_pct"), tune("army_hits"),
               value("Blighted Grasp", "damage_pct"), tune("blighted_grasp_hits"),
               value("Frozen Army", "damage_pct"), tune("frozen_army_waves"),
               value("Unconventional Warfare", "damage_pct"), tune("unconventional_warfare_attacks"),
               value("Unconventional Warfare", "dot_duration_seconds"),
               value("Dead Storm", "damage_pct"), tune("dead_storm_ticks"), value("Dead Storm", "dot_duration_seconds"),
               tune("death_valley_start_radius_yards"), tune("death_valley_end_radius_yards"), tune("death_valley_segment_yards"),
               tune("death_valley_seconds"), 0]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::DeadStorm;\n        return Rune::None;', 'return Rune::DeathValley;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Dead Storm")', 'if (name == "Dead Storms")')),
            ("a blow is the whole total", ("return parts ? totalPct / parts : 0.0;", "return parts ? totalPct : 0.0;")),
            ("a blow with no parts is the total", ("return parts ? totalPct / parts : 0.0;", "return totalPct / std::max(parts, 1u);")),
            ("the blows come together", ("return parts && seconds > 0 ? index * seconds / parts : 0.0;", "return 0.0;")),
            ("the first blow waits", ("return parts && seconds > 0 ? index * seconds / parts : 0.0;", "return parts && seconds > 0 ? (index + 1) * seconds / parts : 0.0;")),
            ("the blows are not evenly spaced", ("index * seconds / parts", "index * index * seconds / parts / parts")),
            ("the line has no end", ("along >= 0 && along <= length &&", "along >= 0 &&")),
            ("the line is twice as wide", ("aside <= width / 2.0", "aside <= width")),
            ("the edge of the line is out", ("aside <= width / 2.0", "aside < width / 2.0")),
            ("the line runs both ways", ("return along >= 0 && along <=", "return along <=")),
            ("the sides are not told apart", ("std::fabs(rx * dy - ry * dx)", "std::fabs(rx * dx - ry * dy)")),
            ("the pull has a step too few", ("std::ceil((start - end) / size - 1e-9)", "std::floor((start - end) / size)")),
            ("the pull goes inside the end radius", ("return std::max(end, start - step * size);", "return start - step * size;")),
            ("the pull starts too close", ("return std::max(end, start - step * size);", "return std::max(end, start - (step + 1) * size);")),
            ("the edge is drawn", ("return distance > radius;", "return distance >= radius;")),
            ("the inside is drawn", ("return distance > radius;", "return distance < radius;")),
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
        self.assertEqual(runes(), ["Blighted Grasp", "Frozen Army", "Unconventional Warfare", "Death Valley", "Dead Storm"])

    def test_the_sheet_numbers_agree_with_the_power_files_totals(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "damage_pct", "radius_yards")], [120, 12000, 15])  # SF_1 120
        self.assertEqual([value("Blighted Grasp", t) for t in ("radius_yards", "damage_pct", "duration_seconds")], [15, 14000, 5])  # SF_30 140, SF_11 5
        self.assertEqual(value("Frozen Army", "damage_pct"), 12000)  # SF_5 120
        self.assertEqual([value("Unconventional Warfare", t) for t in ("damage_pct", "dot_duration_seconds")], [50000, 4])  # SF_15 500, SF_14 4
        self.assertEqual([value("Dead Storm", t) for t in ("damage_pct", "dot_duration_seconds")], [15500, 5])  # SF_24 155, SF_22 5

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"radius_yards", "damage_pct", "duration_seconds", "dot_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("", "radius_yards"), ("Blighted Grasp", "radius_yards"),
                            ("Blighted Grasp", "damage_pct"), ("Blighted Grasp", "duration_seconds"),
                            ("Frozen Army", "damage_pct"), ("Unconventional Warfare", "damage_pct"),
                            ("Unconventional Warfare", "dot_duration_seconds"), ("Dead Storm", "damage_pct"),
                            ("Dead Storm", "dot_duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "army_payload_delay_seconds": "1",            # SF_0
        "army_hits": "3",                             # SF_2
        "army_blast_gap_seconds": "0.21",             # SF_3
        "blighted_grasp_hits": "10",                  # SF_29
        "frozen_army_line_width_yards": "34",         # SF_6
        "frozen_army_line_length_yards": "45",        # the cast reach (skill_targeting.csv)
        "frozen_army_waves": "5",                     # SF_9
        "frozen_army_seconds": "5",                   # SF_8
        "unconventional_warfare_attacks": "40",       # SF_13
        "unconventional_warfare_radius_yards": "40",  # SF_16
        "unconventional_warfare_delay_seconds": "0.4",  # SF_27
        "death_valley_start_radius_yards": "40",      # SF_17
        "death_valley_end_radius_yards": "10",        # SF_18
        "death_valley_segment_yards": "5",            # SF_19
        "death_valley_seconds": "2",                  # SF_20
        "dead_storm_ticks": "10",                     # SF_23
        "dead_storm_delay_seconds": "1.5",            # SF_25
        "dead_storm_radius_yards": "16",              # SF_26
        "dead_storm_life_cost_pct": "20",             # SF_28
    }

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                self.assertIn("decode_pow.py power P6_Necro_SkeleBomb", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'(?:Tune|Count)\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))

    def test_the_line_length_is_the_cast_reach_not_a_power_number(self):
        reach = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL][0]["range_yards"]
        self.assertEqual(tunables()["frozen_army_line_length_yards"]["d3_value"], reach)
        self.assertIn("skill_targeting.csv", tunables()["frozen_army_line_length_yards"]["notes"])


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto army = ArmyOfTheDead::BasePct(spellId)) return army;", self.dispatch)
        self.assertIn("ArmyOfTheDead::Casting(player, spellId);", self.dispatch)
        self.assertIn("ArmyOfTheDead::Ground(player, spellId, center);", self.dispatch)

    def test_the_army_has_no_hit_of_its_own(self):
        self.assertIn("return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_dead_storm_takes_its_life_as_the_cast_begins_and_strikes_around_the_necromancer(self):
        self.assertIn('if (player && RuneAt(spellId) == Rune::DeadStorm) SpendLife(player, Tune("dead_storm_life_cost_pct"));', self.code)
        self.assertIn('Blast(player, spellId, player->GetPosition(), Tune("dead_storm_radius_yards"), pct);', self.code)

    def test_each_rune_has_its_part(self):
        for part in ("case Rune::BlightedGrasp: Hands(player, spellId, center);", "case Rune::FrozenArmy: Line(player, spellId, center);",
                     "case Rune::UnconventionalWarfare: Random(player, spellId, center);",
                     "case Rune::DeathValley: Pull(player, spellId, center); Blasts(player, spellId, center);",
                     "default: Blasts(player, spellId, center);"):
            self.assertIn(part, self.code)

    def test_the_blasts_wait_for_the_payload_delay(self):
        self.assertIn('After(player, Tune("army_payload_delay_seconds") + i * Tune("army_blast_gap_seconds"),', self.code)

    def test_unconventional_warfare_picks_a_random_enemy_in_its_search_radius_for_each_attack(self):
        self.assertIn('Combat::Enemies(player, spellId, center, Tune("unconventional_warfare_radius_yards"))', self.code)
        self.assertIn("std::vector<Unit*> one{enemies[urand(0, uint32(enemies.size() - 1))]};", self.code)

    def test_death_valley_draws_the_enemies_in_to_the_closing_radius(self):
        self.assertIn("double const radius = PullRadius(step, start, end, size);", self.code)
        self.assertIn("if (!Drawn(distance, radius) || distance <= 0) continue;", self.code)

    def test_a_strike_reports_the_hit_once_per_blow(self):
        self.assertEqual(self.code.count("Combat::Connected(player, spellId, hit);"), 1)


if __name__ == "__main__":
    unittest.main()

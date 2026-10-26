"""Demon Hunter Spike Trap and its five runes (src/classes/demon_hunter/dc_demon_hunter_spike_trap.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_spike_trap/harness.cpp compiles the real dc_demon_hunter_spike_trap.h with
    the sheets' own rune names and numbers: each rune name is its rune; the arming time, the blast radius, Scatter's layout, the
    pause between blasts of the chain reaction, what detonates the traps and Lightning Rod's chain are what the sheets and the
    tunables state. Mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The skill is a ground-aimed spell (a `ground_area` row of skill_targeting.csv, radius 8) that
    the engine already casts at a point, so the one new migration is the tunables'.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Spike Trap (or
    the rune that states it); every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_SpikeTrap.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams; the trap hits nothing when it is laid; it is a command device of the shared
    ground-device piece; another Hatred spender (and, with Custom Trigger, a generator) detonates every trap, never Spike Trap itself;
    the runes part as their tooltips say.

What it does not prove: anything on a running server. The laying, the chain reaction and the runes are
docs/test-diablocraft-vawmy.25.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_spike_trap.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_spike_trap.h"
SOURCES = [HEADER, "tests/demon_hunter_spike_trap/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_spike_trap.cpp"
SKILL = "Spike Trap"
RUNES = ["Impaling Spines", "Echoing Blast", "Custom Trigger", "Scatter", "Lightning Rod"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_spike_trap/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("spike_trap_arming_seconds"), tune("spike_trap_impaling_arming_seconds"),
                         tune("spike_trap_custom_trigger_arming_seconds"), value("", "radius_yards"),
                         tune("spike_trap_custom_trigger_radius_yards"), tune("spike_trap_lightning_rod_radius_yards"),
                         tune("spike_trap_scatter_spacing_yards"), value("Scatter", "spawn_count"), tune("spike_trap_explosion_gap_seconds"),
                         value("Lightning Rod", "radius_yards", "chain"), value("Lightning Rod", "target_count"),
                         value("Lightning Rod", "hit_count"), value("Lightning Rod", "damage_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Echoing Blast")\n            return Rune::EchoingBlast;',
                                        'if (name == "Echoing Blast")\n            return Rune::ImpalingSpines;')),
            ("Impaling Spines arms at once", (HEADER, "base + impalingExtra", "base")),
            ("Custom Trigger arms like the rest", (HEADER, "rune == Rune::CustomTrigger ? customTrigger : base", "base")),
            ("Custom Trigger's blast is the skill's", (HEADER, "rune == Rune::CustomTrigger ? base + customBonus", "rune == Rune::CustomTrigger ? base")),
            ("Lightning Rod's blast is the skill's", (HEADER, "rune == Rune::LightningRod ? base + rodBonus", "rune == Rune::LightningRod ? base")),
            ("Scatter's traps lie on one point", (HEADER, "* spacing)", "* 0.0)")),
            ("every trap goes at once", (HEADER, "order * gapSeconds * 1000.0 + 0.5", "0.0")),
            ("Spike Trap detonates itself", (HEADER, "return !spikeTrap && (spender", "return (spender")),
            ("a generator detonates for every rune", (HEADER, "generator && rune == Rune::CustomTrigger", "generator")),
            ("the chain takes the farthest", (HEADER, "distances[a] < distances[b]", "distances[a] > distances[b]")),
            ("the chain has no limit", (HEADER, "if (near.size() > most)", "if (false)")),
            ("the chain forgets its reach", (HEADER, "if (distances[i] <= chain)", "if (true)")),
            ("a hit is the whole damage", (HEADER, "return hits ? total / hits : 0.0;", "return total;")),
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
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("ground_area", "8"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct"), value("", "radius_yards"), value("", "max_count")],
                         [15, 1160, 8, 4])
        self.assertEqual([value("Impaling Spines", "damage_pct"), value("Impaling Spines", "immobilize_duration_seconds")], [1930, 3])
        self.assertEqual([value("Echoing Blast", "damage_pct"), value("Echoing Blast", "slow_duration_seconds")], [2020, 3])
        self.assertEqual(value("Custom Trigger", "damage_pct"), 1900)
        self.assertEqual(value("Scatter", "spawn_count"), 2)
        self.assertEqual([value("Lightning Rod", "target_count"), value("Lightning Rod", "radius_yards", "chain"),
                          value("Lightning Rod", "damage_pct"), value("Lightning Rod", "hit_count")], [3, 10, 2020, 3])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("spike_trap_arming_seconds", "1.5", "SF_20"), ("spike_trap_impaling_arming_seconds", "3", "SF_15"),
                                 ("spike_trap_custom_trigger_arming_seconds", "1", "SF_12"), ("spike_trap_armed_seconds", "30", "SF_27"),
                                 ("spike_trap_custom_trigger_radius_yards", "4", "SF_13"),
                                 ("spike_trap_lightning_rod_radius_yards", "2", "SF_24"), ("spike_trap_echoing_slow_pct", "60", "SF_40"),
                                 ("spike_trap_scatter_damage_pct", "960", "SF_56"), ("spike_trap_scatter_spacing_yards", "15", "SF_23"),
                                 ("spike_trap_explosion_gap_seconds", "0.12", "SF_57"), ("spike_trap_chain_gap_seconds", "0.035", "SF_26")):
            self.assertEqual(float(rows[name]["d3_value"] or rows[name]["value"]), float(d3), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_SpikeTrap.pow", rows[name]["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("spike_trap_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "radius_yards", "own"), ("Impaling Spines", "radius_yards", "inherited"),
                                    ("Impaling Spines", "immobilize_duration_seconds", "own"), ("Echoing Blast", "slow_duration_seconds", "own"),
                                    ("Scatter", "spawn_count", "own"), ("Lightning Rod", "target_count", "own"),
                                    ("Lightning Rod", "hit_count", "own"), ("Lightning Rod", "damage_pct", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_SpikeTrap.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        def ruled(n):
            return float(str(sf[n]).split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(7), value("", "radius_yards"))
        self.assertAlmostEqual(number(20), tune("spike_trap_arming_seconds"))
        self.assertAlmostEqual(number(15), tune("spike_trap_impaling_arming_seconds"))
        self.assertAlmostEqual(number(12), tune("spike_trap_custom_trigger_arming_seconds"))
        self.assertAlmostEqual(number(27), tune("spike_trap_armed_seconds"))
        self.assertAlmostEqual(ruled(13), tune("spike_trap_custom_trigger_radius_yards"))
        self.assertAlmostEqual(ruled(24), tune("spike_trap_lightning_rod_radius_yards"))
        self.assertAlmostEqual(number(40) * 100, tune("spike_trap_echoing_slow_pct"))
        self.assertAlmostEqual(number(56) * 100, tune("spike_trap_scatter_damage_pct"))
        self.assertAlmostEqual(number(23), tune("spike_trap_scatter_spacing_yards"))
        self.assertAlmostEqual(number(57), tune("spike_trap_explosion_gap_seconds"))
        self.assertAlmostEqual(number(26), tune("spike_trap_chain_gap_seconds"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("return laid;"), 1)
        self.assertLess(self.dispatch.index("SpikeTrap::BasePct(spellId)"), self.dispatch.index("Caltrops::BasePct(spellId)"))
        for call in ("SpikeTrap::Casting(player, spellId);", "SpikeTrap::Ground(player, spellId, center);"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_trap_hits_nothing_when_it_is_laid(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_trap_is_a_command_device_of_the_shared_piece(self):
        lay = self.code[self.code.index("void Lay("):self.code.index("bool Is(")]
        self.assertIn("setup.spec.mode = GroundDevice::Mode::Command;", lay)
        self.assertIn('setup.spec.most = std::size_t( Passive::MostStanding(player, "spike_trap", unsigned(Numbers::Num(BaseId(Skill), "max_count"))));', lay)
        self.assertIn('Tune("spike_trap_armed_seconds") * Passive::DurationFactor(player, "Spike Trap") * 1000.0', lay)
        self.assertIn("GroundDevice::Place(player, setup, at);", lay)

    def test_custom_engineering_asks_for_the_traps_time_and_cap(self):
        # The sheet side: the passive's numbers are above what the skill states, so asking the seams changes the result.
        passive = {(r["token"], r["qualifier"]): float(r["value"]) for r in read(D3 / "demon_hunter_passive_values.csv")
                   if r["skill"] == "Custom Engineering"}
        self.assertGreater(passive[("max_count", "spike_trap")], value("", "max_count"))
        self.assertEqual(tune("spike_trap_armed_seconds") * (1 + passive[("duration_bonus_pct", "")] / 100), 60)
        # The code side: the trap's life and the number standing at once go through the passive's seams, once each.
        self.assertIn('#include "dc_demon_hunter_passives.h"', CODE.read_text(encoding="utf-8"))
        lay = self.code[self.code.index("void Lay("):self.code.index("bool Is(")]
        self.assertEqual(lay.count('Passive::DurationFactor(player, "Spike Trap")'), 1)
        self.assertEqual(lay.count('Passive::MostStanding(player, "spike_trap"'), 1)

    def test_a_spender_detonates_every_trap_and_not_the_trap_itself(self):
        cast = self.code[self.code.index("void Casting("):self.code.index("void Ground(")]
        self.assertIn("Detonates(Is(spellId), CostsHatred(spellId), generator, SlottedRune(player))", cast)
        self.assertIn('Classes::CategoryOf(spellId) == "Primary"', cast)
        self.assertIn("explosionOrder = 0;", cast)
        self.assertIn("GroundDevice::Detonate(player, BaseId(Skill));", cast)

    def test_the_runes_part(self):
        explode = self.code[self.code.index("void Explode("):self.code.index("void Lay(")]
        self.assertIn('Tune("spike_trap_scatter_damage_pct")', explode)
        self.assertIn('Tune("spike_trap_explosion_gap_seconds")', explode)
        self.assertIn("rune == Rune::EchoingBlast", explode)
        self.assertIn('Slow(player, enemy, Tune("spike_trap_echoing_slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"))', explode)
        self.assertIn('Numbers::Num(spellId, "hit_count")', explode)
        self.assertIn('Numbers::Num(spellId, "radius_yards", "chain")', explode)
        lay = self.code[self.code.index("void Lay("):self.code.index("bool Is(")]
        self.assertIn("rune == Rune::ImpalingSpines", lay)
        self.assertIn('Root(player, enemy, Numbers::Num(spellId, "immobilize_duration_seconds"));', lay)
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn('Layout(unsigned(Numbers::Num(spellId, "spawn_count")), Tune("spike_trap_scatter_spacing_yards"))', ground)


if __name__ == "__main__":
    unittest.main()

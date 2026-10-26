"""Demon Hunter Preparation and its five runes (src/classes/demon_hunter/dc_demon_hunter_preparation.h and .cpp, and
src/classes/dc_resource_pool.h).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_preparation/harness.cpp compiles the real dc_demon_hunter_preparation.h,
    dc_resource_pool.h, the DoT rules and the clock with the sheets' own rune names and numbers: each rune name is its rune; what each
    rune restores at the cast (Punishment's Hatred beside the Discipline, Focused Mind's Discipline over time and none at once); the
    ticks making the Discipline; the share of Life; the chance a cooldown is skipped, edge to edge and as a share of the rolls; the
    higher maximum of the second resource (a source adds, two add up, a source set to nothing is gone, a player is apart from another).
    Nine mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** Preparation is the engine's self cast (a `self` row of skill_targeting.csv); its 45 second cooldown
    and Punishment's 20 are the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Preparation (or
    the rune that states it); the tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_Preparation.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`Cast`, `BarWritten`, `RegisterScripts`); the saved bar's write tells the Demon Hunter
    its bar; the stats add the pool's bonus to the second resource's maximum in both places; the cast restores, heals and takes the cooldown
    off as the sheet says; Focused Mind's script ends with its owner.

What it does not prove: anything on a running server. The restoring, the over-time Discipline, the Life, the cooldown and the higher
maximum are docs/test-diablocraft-vawmy.22.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_preparation.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_preparation.h"
POOL = "src/classes/dc_resource_pool.h"
DOT = "src/classes/demon_hunter/dc_demon_hunter_dot.h"
CLOCK = "src/classes/demon_hunter/dc_demon_hunter_clock.h"
SOURCES = [HEADER, POOL, DOT, CLOCK, "tests/demon_hunter_preparation/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_preparation.cpp"
SKILL = "Preparation"
RUNES = ["Punishment", "Invigoration", "Focused Mind", "Battle Scars", "Backup Plan"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_preparation/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "gain_resource"), value("Punishment", "gain_resource"), value("Focused Mind", "gain_resource"),
                         value("Focused Mind", "dot_duration_seconds"), tune("preparation_regen_tick_seconds"),
                         value("Battle Scars", "heal_pct"), value("Backup Plan", "proc_chance_pct"), value("Invigoration", "max_pool_resource")]
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
            ("two runes share a name", (HEADER, 'if (name == "Invigoration")\n            return Rune::Invigoration;',
                                        'if (name == "Invigoration")\n            return Rune::Punishment;')),
            ("Punishment gives no Hatred", (HEADER, "return {base, own, 0};", "return {base, 0, 0};")),
            ("Focused Mind restores at once as well", (HEADER, "return {0, 0, own};", "return {base, 0, own};")),
            ("a tick is the whole Discipline", (HEADER, "return Dot::TickPct(total, Dot::Ticks(seconds, tickSeconds));", "return total;")),
            ("Battle Scars heals the whole Life", (HEADER, "std::max(0.0, maxLife) * std::max(0.0, pct) / 100.0", "std::max(0.0, maxLife)")),
            ("a roll at the chance skips", (HEADER, "return roll < chancePct;", "return roll <= chancePct;")),
            ("the sources do not add", (POOL, "sum += points;", "sum = points;")),
            ("a change is always told", (POOL, "return before != (points > 0 ? points : 0.0);", "return true;")),
            ("clearing keeps the sources", (POOL, "Detail::Table().erase(guid);\n    }\n} // namespace", "(void) guid;\n    }\n} // namespace")),
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

    def test_the_record_is_the_engines_self_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual(rows[SKILL]["target_type"], "self")
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "gain_resource")], [45, 30])
        self.assertEqual([value("Punishment", "gain_resource"), value("Punishment", "cooldown_seconds")], [75, 20])
        self.assertEqual(value("Invigoration", "max_pool_resource"), 20)
        self.assertEqual([value("Focused Mind", "gain_resource"), value("Focused Mind", "dot_duration_seconds")], [45, 15])
        self.assertEqual(value("Battle Scars", "heal_pct"), 40)
        self.assertEqual(value("Backup Plan", "proc_chance_pct"), 30)

    def test_the_tick_is_alexs_standing_default(self):
        row = tunables()["preparation_regen_tick_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("", "0.5"))
        self.assertIn("standing default", row["notes"])
        self.assertIn("SF_5", row["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("preparation_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "gain_resource", "own"), ("Punishment", "gain_resource", "own"), ("Invigoration", "max_pool_resource", "own"),
                                    ("Focused Mind", "gain_resource", "own"), ("Focused Mind", "dot_duration_seconds", "own"),
                                    ("Battle Scars", "heal_pct", "own"), ("Backup Plan", "proc_chance_pct", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Preparation.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(3), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(8), value("", "gain_resource"))
        self.assertAlmostEqual(number(0), value("Punishment", "cooldown_seconds"))
        self.assertAlmostEqual(number(9), value("Punishment", "gain_resource"))
        self.assertAlmostEqual(number(1), value("Invigoration", "max_pool_resource"))
        self.assertAlmostEqual(number(4), value("Focused Mind", "gain_resource"))
        self.assertAlmostEqual(number(5), value("Focused Mind", "dot_duration_seconds"))
        self.assertAlmostEqual(number(6) * 100, value("Battle Scars", "heal_pct"))
        self.assertAlmostEqual(number(7) * 100, value("Backup Plan", "proc_chance_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        self.classes = re.sub(r"\s+", " ", (MODULE / "src/classes/dc_classes.cpp").read_text(encoding="utf-8"))
        self.stats = re.sub(r"\s+", " ", (MODULE / "src/stats/dc_stats.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        for call in ("Preparation::Cast(player, spellId, targets);", "Preparation::BarWritten(player, bar);", "Preparation::RegisterScripts();"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_saved_bars_write_tells_the_engine_and_the_engine_the_demon_hunter(self):
        self.assertIn("void WriteActionBar(Player* player) { std::vector<Slot> const bar = Bar(player); WriteActionBar(player, bar); "
                      "Combat::BarWritten(player, bar); }", self.classes)
        resolve = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.assertIn("void BarWritten(Player* player, std::vector<Classes::Slot> const& bar) { DemonHunter::BarWritten(player, bar); }", resolve)

    def test_the_stats_add_the_pools_bonus_to_the_second_resources_maximum_in_both_places(self):
        # The bonus is one term of Pool::Maximum (the pool, the bonus and the gear's Stat::MaxSecond), which both places call.
        self.assertIn("Resources::SetMax(player, *cls.second, Resources::Pool::Maximum(cls.second->pool, player->GetGUID().GetRawValue(), sheet[Stat::MaxSecond]));", self.stats)
        self.assertIn("Resources::ToUnits( *cls.second, Resources::Pool::Maximum(cls.second->pool, player->GetGUID().GetRawValue(), (*sheet)[Stat::MaxSecond])))", self.stats)

    def test_the_cast_restores_heals_and_takes_the_cooldown_off(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void BarWritten(")]
        self.assertIn('Numbers::Num(BaseId(Skill), "gain_resource"), Numbers::Num(spellId, "gain_resource")', cast)
        self.assertIn("Resources::Energize(player, Resources::Discipline, spellId, restore.disciplineNow);", cast)
        self.assertIn("Resources::Energize(player, Resources::Hatred, spellId, restore.hatredNow);", cast)
        self.assertIn('Numbers::Num(spellId, "dot_duration_seconds")', cast)
        self.assertIn('RegenTick(restore.disciplineOver, seconds, Tune("preparation_regen_tick_seconds"))', cast)
        self.assertIn('Heal(player, spellId, HealOf(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct")));', cast)
        self.assertIn('CooldownSkipped(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct"))', cast)
        self.assertIn("Combat::SendSkillCooldown(player, spellId, 0);", cast)

    def test_focused_minds_discipline_comes_every_tick_and_ends_with_its_owner(self):
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertIn('Due(regen.clock, diff, Tune("preparation_regen_tick_seconds") * 1000.0)', update)
        self.assertIn("Resources::Energize(player, Resources::Discipline, regen.spellId, regen.perTick);", update)
        self.assertIn("if (!player->IsAlive()) { Stop(player); return; }", update)
        self.assertIn("Resources::Pool::Clear(player->GetGUID().GetRawValue());", self.code)

    def test_invigorations_maximum_follows_the_rune_on_the_bar(self):
        bar = self.code[self.code.index("void BarWritten("):self.code.index("void RegisterScripts(")]
        self.assertIn("RuneAt(slot.spellId) == Rune::Invigoration", bar)
        self.assertIn('Numbers::Num(slot.spellId, "max_pool_resource")', bar)
        self.assertIn("Resources::Pool::Set(player->GetGUID().GetRawValue(), BaseId(Skill), points)", bar)
        self.assertIn("Stats::Recompute(player);", bar)


if __name__ == "__main__":
    unittest.main()

"""Witch Doctor Soul Harvest and its five runes (src/classes/witch_doctor/dc_witch_doctor_soul_harvest.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_soul_harvest/harness.cpp compiles the real dc_witch_doctor_soul_harvest.h and
    dc_witch_doctor_buffs.h with the sheets' own rune names and numbers: each rune name is its rune; a cast adds a stack for each enemy
    harvested up to the 5; Siphon's 0.06 of the Healing table is the sheet's 32185 Life for one enemy and each enemy returns it; only
    Vengeful Spirit hits; the buff's stacks add to the most and restart its 30 seconds, one that ran out starts again, its worth is the
    stacks' and none once over; Swallow Your Soul's pool rises by 5% of the pool for a stack. Ten mutations planted in a scratch copy (two
    runes share a name, the stacks have no cap, a cast adds one stack whatever the enemies, Siphon's share is lost, every rune hits, the
    time is not restarted, an ended buff still counts, a ran-out buff keeps its stacks, the pool rises by the whole pool, an enemy gives
    nothing) must each make it fail.
  * **The record needs no change.** The cast is the engine's self-centred area cast (a `self_aoe` row of skill_targeting.csv, radius 18);
    the cooldown and each rune's school are the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of witch_doctor_skill_values.csv for Soul Harvest (or
    the rune that states it): 3% Intelligence for 30 seconds, 5 stacks, Siphon's 32185 Life, Soul to Waste's 5% speed, Languish's 10% armor
    and 80% slow for 5 seconds, Swallow Your Soul's 5% pool, Vengeful Spirit's 640%; every tunable is a row of data/tunables/witchdoctor.csv,
    and the numbers equal the decoded Power/Witchdoctor_SoulHarvest.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the damage and cast seams; every cast stacks Intelligence by the enemies harvested; Languish's slow
    keeps its own seconds and the buff the skill's; the pool's base excludes the buff itself.

What it does not prove: anything on a running server. The stacks, the Life, the speed, the armor, the slow, the Mana and the hit are
docs/test-diablocraft-vxrcu.20.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_soul_harvest.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_soul_harvest.h"
BUFFS = "src/classes/witch_doctor/dc_witch_doctor_buffs.h"
SOURCES = [HEADER, BUFFS, "tests/witch_doctor_soul_harvest/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_soul_harvest.cpp"
SKILL = "Soul Harvest"
RUNES = ["Siphon", "Soul to Waste", "Languish", "Swallow Your Soul", "Vengeful Spirit"]


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


def healing_table_70():
    text = (MODULE / "src/combat/dc_healing_table.h").read_text(encoding="utf-8")
    numbers = re.findall(r"\d+", text[text.index("Table[71] = {"):text.index("};")])
    return float(numbers[1:][70])


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_soul_harvest/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "max_stacks_count"), value("", "duration_seconds"), tune("soul_harvest_healing_share"), healing_table_70(),
                         value("Siphon", "heal_life"), value("Vengeful Spirit", "damage_pct"), value("Swallow Your Soul", "max_pool_pct")]
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
            ("two runes share a name", (HEADER, 'if (name == "Languish")\n            return Rune::Languish;', 'if (name == "Languish")\n            return Rune::Siphon;')),
            ("the stacks have no cap", (HEADER, "return std::min(enemies, std::max(1u, most));", "return enemies;")),
            ("a cast adds one stack whatever the enemies", (HEADER, "return std::min(enemies, std::max(1u, most));", "return enemies ? 1u : 0u;")),
            ("Siphon's share is lost", (HEADER, "return share > 0 && table > 0 ? share * table * enemies : 0.0;", "return share > 0 && table > 0 ? table * enemies : 0.0;")),
            ("every rune hits", (HEADER, "return rune == Rune::VengefulSpirit ? runePct : 0.0;", "return runePct;")),
            ("the time is not restarted", (BUFFS, "held.until = now + ms;", "held.until = held.until ? held.until : now + ms;")),
            ("an ended buff still counts", (BUFFS, "return Over(held, now) ? 0.0 : perStack * held.stacks;", "return perStack * held.stacks;")),
            ("a buff that ran out keeps its stacks", (BUFFS, "if (held.until <= now)\n            held.stacks = 0;", "if (false)\n            held.stacks = 0;")),
            ("the pool rises by the whole pool", (BUFFS, "return basePoints > 0 && pct > 0 ? basePoints * pct / 100.0 : 0.0;", "return basePoints > 0 && pct > 0 ? basePoints : 0.0;")),
            ("an enemy gives nothing", (BUFFS, "return perEnemy > 0 ? perEnemy * enemies : 0.0;", "return perEnemy > 0 ? perEnemy : 0.0;")),
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

    def test_the_record_is_the_engines_self_area_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("self_aoe", "18"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", n) for n in ("cooldown_seconds", "radius_yards", "primary_stat_pct", "duration_seconds", "max_stacks_count")],
                         [12, 18, 3, 30, 5])
        self.assertEqual(value("Siphon", "heal_life"), 32185)
        self.assertEqual(value("Soul to Waste", "movement_speed_pct"), 5)
        self.assertEqual([value("Languish", n) for n in ("armor_pct", "slow_pct", "duration_seconds")], [10, 80, 5])
        self.assertEqual(value("Swallow Your Soul", "max_pool_pct"), 5)
        self.assertEqual(value("Vengeful Spirit", "damage_pct"), 640)

    def test_the_tunable(self):
        row = tunables()["soul_harvest_healing_share"]
        self.assertEqual((row["d3_value"], row["value"]), ("0.06", ""))
        self.assertIn("SF_9", row["notes"])
        self.assertIn("Power/Witchdoctor_SoulHarvest.pow", row["notes"])
        self.assertNotIn("placeholder", row["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("soul_harvest_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "max_stacks_count", "duration_seconds", "primary_stat_pct", "movement_speed_pct", "armor_pct",
                                  "slow_pct", "max_pool_pct"})
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "primary_stat_pct", "own"), ("", "duration_seconds", "own"), ("", "max_stacks_count", "own"),
                                    ("Siphon", "primary_stat_pct", "inherited"), ("Languish", "duration_seconds", "own"),
                                    ("Vengeful Spirit", "damage_pct", "own"), ("Soul to Waste", "movement_speed_pct", "own"),
                                    ("Languish", "armor_pct", "own"), ("Languish", "slow_pct", "own"), ("Swallow Your Soul", "max_pool_pct", "own")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token)]["origin"], origin)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_SoulHarvest.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(14), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(3), value("", "radius_yards"))
        self.assertAlmostEqual(number(8) * 100, value("", "primary_stat_pct"))
        self.assertAlmostEqual(number(5), value("", "duration_seconds"))
        self.assertAlmostEqual(number(13), value("", "max_stacks_count"))
        self.assertIn("(0.06)", str(sf[9]))
        self.assertAlmostEqual(0.06 * healing_table_70(), value("Siphon", "heal_life"), delta=1.0)
        self.assertAlmostEqual(number(6) * 100, value("Soul to Waste", "movement_speed_pct"))
        self.assertAlmostEqual(number(15) * 100, value("Languish", "armor_pct"))
        self.assertAlmostEqual(number(10) * 100, value("Languish", "slow_pct"))
        self.assertAlmostEqual(number(11), value("Languish", "duration_seconds"))
        self.assertAlmostEqual(number(1) * 100, value("Swallow Your Soul", "max_pool_pct"))
        self.assertAlmostEqual(number(0) * 100, value("Vengeful Spirit", "damage_pct"))
        self.assertAlmostEqual(tune("soul_harvest_healing_share"), 0.06)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("SoulHarvest::BasePct(spellId)"), 1)
        self.assertEqual(self.dispatch.count("SoulHarvest::Cast(player, spellId, targets);"), 1)

    def test_every_cast_stacks_intelligence_by_the_enemies_harvested(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("unsigned const adds = StacksAdded(enemies, most);", cast)
        self.assertIn('SheetBuffs::Stack(player, spellId, Stat::Intelligence, Bucket::Percent, Numbers::Num(spellId, "primary_stat_pct"), most, seconds, adds);', cast)
        self.assertIn('Numbers::Num(BaseId(Skill), "duration_seconds")', cast)
        self.assertIn("Combat::ModifiedDurationSeconds(player, spellId,", cast)

    def test_each_rune_does_its_one_thing(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('SiphonHeal(Tune("soul_harvest_healing_share"), Healing::At(player->GetLevel()), enemies)', cast)
        self.assertIn('SheetBuffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Flat, Numbers::Num(spellId, "movement_speed_pct"), most, seconds, adds);', cast)
        self.assertIn('SheetBuffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), most, seconds, adds);', cast)
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "duration_seconds"));', cast)
        self.assertIn('Buffs::PoolPerStack(BasePool(player, spellId), Numbers::Num(spellId, "max_pool_pct"))', cast)
        self.assertIn("SheetBuffs::Stack(player, spellId, Stat::MaxFury, Bucket::Flat, rise, most, seconds, adds);", cast)
        self.assertIn("Gain(player, Classes::ClassIdOf(player), spellId, Buffs::PerEnemy(adds, rise), 1);", cast)
        pool = self.code[self.code.index("double BasePool("):self.code.index("} // namespace")]
        self.assertIn("(*sheet)[Stat::MaxFury] - SheetBuffs::Current(player, spellId, Stat::MaxFury)", pool)
        self.assertIn('return HitPct(RuneAt(spellId), Numbers::Get(spellId, "damage_pct").value_or(0.0));', self.code)


if __name__ == "__main__":
    unittest.main()

"""Demon Hunter Marked for Death and its five runes (src/classes/demon_hunter/dc_demon_hunter_marked_for_death.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_marked_for_death/harness.cpp compiles the real
    dc_demon_hunter_marked_for_death.h and the clock with the sheets' own rune names and numbers: each rune name is its rune; a mark runs
    its seconds from when it was made, to the millisecond; Grim Reaper's share is divided evenly and the parts make the share; Contagion
    picks the nearest enemies nearest first with a tie in its order; the area holds its edge and ticks at its cadence; Death Toll's heal
    is the share of the maximum Life. Nine mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The cast is the engine's single-enemy spell (a `single_enemy` row of skill_targeting.csv, 70 yards);
    the Discipline cost is the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Marked for Death
    (or the rune that states it); every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_MarkedForDeath.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Cast`, `Landed`, `RegisterScripts`); the mark is the shared enemy effect
    "takes more damage from all attacks"; the damage and death hooks are the unit script; the area marks every tick; Mortal Enemy pays
    the Demon Hunter only and Death Toll any attacker.

What it does not prove: anything on a running server. The mark, the share, the spread, the area, the Hatred and the heal are
docs/test-diablocraft-vawmy.23.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_marked_for_death.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_marked_for_death.h"
CLOCK = "src/classes/demon_hunter/dc_demon_hunter_clock.h"
SOURCES = [HEADER, CLOCK, "tests/demon_hunter_marked_for_death/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_marked_for_death.cpp"
SKILL = "Marked for Death"
RUNES = ["Grim Reaper", "Contagion", "Valley of Death", "Mortal Enemy", "Death Toll"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_marked_for_death/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "duration_seconds"), value("Grim Reaper", "damage_share_pct"), value("Contagion", "target_count"),
                         value("Valley of Death", "radius_yards"), tune("marked_for_death_area_tick_seconds"),
                         value("Valley of Death", "duration_seconds"), value("Death Toll", "heal_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Contagion")\n            return Rune::Contagion;',
                                        'if (name == "Contagion")\n            return Rune::GrimReaper;')),
            ("a mark never ends", (HEADER, "return nowMs + std::uint64_t(seconds > 0 ? seconds * 1000.0 : 0.0);", "return nowMs;")),
            ("a mark is on in its last millisecond too", (HEADER, "return nowMs < endsMs;", "return nowMs <= endsMs;")),
            ("the share is not divided", (HEADER, "damage * sharePct / 100.0 / double(others)", "damage * sharePct / 100.0")),
            ("the share is the whole hit", (HEADER, "damage * sharePct / 100.0 / double(others)", "damage / double(others)")),
            ("the farthest are chosen", (HEADER, "return distances[a] < distances[b];", "return distances[a] > distances[b];")),
            ("every enemy is chosen", (HEADER, "order.resize(std::min(order.size(), count));", "")),
            ("the edge of the area is out", (HEADER, "return radius > 0 && distance <= radius;", "return radius > 0 && distance < radius;")),
            ("Death Toll heals nothing of the share", (HEADER, "std::max(0.0, maxLife) * std::max(0.0, pct) / 100.0", "std::max(0.0, maxLife)")),
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

    def test_the_record_is_the_engines_single_enemy_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"]), ("single_enemy", "70"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_bonus_pct"), value("", "duration_seconds")], [3, 15, 30])
        self.assertEqual([value("Grim Reaper", "damage_share_pct"), value("Grim Reaper", "radius_yards")], [15, 20])
        self.assertEqual([value("Contagion", "target_count"), value("Contagion", "radius_yards")], [3, 30])
        self.assertEqual([value("Valley of Death", n) for n in ("radius_yards", "duration_seconds", "damage_bonus_pct")], [15, 15, 15])
        self.assertEqual(value("Mortal Enemy", "gain_resource"), 4)
        self.assertEqual(value("Death Toll", "heal_pct"), 3)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("marked_for_death_area_tick_seconds", "0.5", "SF_8"), ("marked_for_death_area_buff_seconds", "1", "SF_10")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_MarkedForDeath.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("marked_for_death_")})
        # the landing attack's proc coefficient is read off that attack's spell, not the mark's (test_proc_scaling.py)
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text)) - {"proc_coefficient"}
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_bonus_pct", "own"), ("", "duration_seconds", "own"), ("Grim Reaper", "damage_share_pct", "own"),
                                    ("Grim Reaper", "radius_yards", "own"), ("Contagion", "target_count", "own"), ("Contagion", "radius_yards", "own"),
                                    ("Valley of Death", "duration_seconds", "own"), ("Valley of Death", "damage_bonus_pct", "own"),
                                    ("Valley of Death", "radius_yards", "own"), ("Mortal Enemy", "gain_resource", "own"),
                                    ("Death Toll", "heal_pct", "own"), ("Contagion", "damage_bonus_pct", "inherited"),
                                    ("Contagion", "duration_seconds", "inherited")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_MarkedForDeath.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(1) * 100, value("", "damage_bonus_pct"))
        self.assertAlmostEqual(number(16), value("", "duration_seconds"))
        self.assertAlmostEqual(number(2) * 100, value("Grim Reaper", "damage_share_pct"))
        self.assertAlmostEqual(number(3), value("Grim Reaper", "radius_yards"))
        self.assertAlmostEqual(float(sf[6].split("?")[1].split(":")[0]), value("Contagion", "target_count"))
        self.assertAlmostEqual(number(5), value("Contagion", "radius_yards"))
        self.assertAlmostEqual(number(7), value("Valley of Death", "radius_yards"))
        self.assertAlmostEqual(number(9), value("Valley of Death", "duration_seconds"))
        self.assertAlmostEqual(number(12) * 100, value("Valley of Death", "damage_bonus_pct"))
        self.assertAlmostEqual(number(11), value("Mortal Enemy", "gain_resource"))
        self.assertAlmostEqual(number(13), 1.0)
        self.assertAlmostEqual(number(14) * 100, value("Death Toll", "heal_pct"))
        self.assertAlmostEqual(number(8), tune("marked_for_death_area_tick_seconds"))
        self.assertAlmostEqual(number(10), tune("marked_for_death_area_buff_seconds"))

    def test_custom_engineering_lengthens_the_mark_and_the_valley_and_nothing_else_here(self):
        # The power file's own list: the mark's seconds (SF_17) and Valley of Death's area (SF_18) are the passive's SF_0 times the base;
        # the buff the area re-applies every tick (SF_10) and the tick (SF_8) are not.
        passive = {(r["token"], r["qualifier"]): float(r["value"]) for r in read(D3 / "demon_hunter_passive_values.csv")
                   if r["skill"] == "Custom Engineering"}
        longer = 1 + passive[("duration_bonus_pct", "")] / 100
        self.assertEqual(value("", "duration_seconds") * longer, 60)
        self.assertEqual(value("Valley of Death", "duration_seconds") * longer, 30)
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_MarkedForDeath.pow"))["sf"]
        engineering = "DemonHunter_Passive_CustomEngineering"
        self.assertRegex(str(sf[17]), rf"^30\s*\*\s*PowerTag\.{engineering}\.\"Script Formula 0\"$")
        self.assertRegex(str(sf[18]), rf"^15\s*\*\s*PowerTag\.{engineering}\.\"Script Formula 0\"$")
        self.assertAlmostEqual(float(str(sf[16])), value("", "duration_seconds"))
        self.assertAlmostEqual(float(str(sf[9])), value("Valley of Death", "duration_seconds"))
        for n in (8, 10):
            self.assertNotIn("CustomEngineering", str(sf[n]), n)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto mark = MarkedForDeath::BasePct(spellId)) return mark;"), 1)
        self.assertLess(self.dispatch.index("ElementalArrow::BasePct(spellId)"), self.dispatch.index("MarkedForDeath::BasePct(spellId)"))
        self.assertLess(self.dispatch.index("MarkedForDeath::BasePct(spellId)"), self.dispatch.index("return Caltrops::BasePct(spellId);"))
        for call in ("MarkedForDeath::Landed(player, target, spellId);", "MarkedForDeath::Cast(player, spellId, targets);", "MarkedForDeath::RegisterScripts();"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_cast_hits_nothing_and_marks_the_enemy_for_every_attacker(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        mark = self.code[self.code.index("void MarkEnemy("):self.code.index("void Spread(")]
        self.assertIn('Numbers::Num(spellId, "duration_seconds")', mark)
        self.assertIn("marks[enemy->GetGUID().GetRawValue()] = {owner->GetGUID(), spellId, EndsAt(now, seconds)};", mark)
        self.assertIn('EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_bonus_pct"), seconds);', mark)
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn("for (Unit* enemy : targets) MarkEnemy(player, enemy, spellId);", cast)

    def test_custom_engineering_asks_for_the_marks_and_the_areas_seconds(self):
        # Asked once where the mark is made (a Contagion spread goes through the same call) and once where the area is laid, by the
        # skill's own name in the passive's list; the buff the area re-applies is not lengthened.
        self.assertIn('#include "dc_demon_hunter_passives.h"', CODE.read_text(encoding="utf-8"))
        mark = self.code[self.code.index("void MarkEnemy("):self.code.index("void Spread(")]
        self.assertEqual(mark.count('Passive::DurationFactor(owner, "Marked for Death")'), 1)
        self.assertIn('double const seconds = Numbers::Num(spellId, "duration_seconds") * Passive::DurationFactor(owner, "Marked for Death");', mark)
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertEqual(cast.count('Passive::DurationFactor(player, "Marked for Death")'), 1)
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertNotIn("DurationFactor", update)
        self.assertEqual(self.code.count("DurationFactor("), 2)
        # The name asked is the sheet's name for the skill.
        self.assertEqual({r["skill"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == "Marked for Death"}, {"Marked for Death"})

    def test_grim_reaper_shares_what_the_marked_enemy_takes_and_never_shares_a_share(self):
        hook = self.code[self.code.index("void OnDamage("):self.code.index("void OnUnitDeath(")]
        self.assertIn("if (sharing || !damage) return;", hook)
        self.assertIn("RuneAt(mark->spellId) != Rune::GrimReaper", hook)
        self.assertIn("if (enemy != victim) others.push_back(enemy);", hook)
        self.assertIn('SharePerEnemy(damage, Numbers::Num(mark->spellId, "damage_share_pct"), others.size())', hook)
        self.assertIn("Scope scope(sharing);", hook)
        self.assertIn("Combat::DealHit(owner, enemy, mark->spellId, hit, true);", hook)

    def test_contagion_spreads_when_the_enemy_dies_and_a_death_ends_the_mark(self):
        death = self.code[self.code.index("void OnUnitDeath("):self.code.index("class Areas")]
        self.assertIn("marks.erase(found);", death)
        self.assertIn("RuneAt(mark->spellId) != Rune::Contagion", death)
        self.assertIn("Spread(owner, unit, *mark);", death)
        spread = self.code[self.code.index("void Spread("):self.code.index("class Marks")]
        self.assertIn('Numbers::Num(mark.spellId, "radius_yards")', spread)
        self.assertIn('Nearest(distances, std::size_t(Numbers::Num(mark.spellId, "target_count")))', spread)
        self.assertIn("MarkEnemy(owner, near[place], mark.spellId);", spread)

    def test_the_area_marks_every_tick_and_ends_with_its_owner(self):
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertIn('Due(area.clock, diff, Tune("marked_for_death_area_tick_seconds") * 1000.0)', update)
        self.assertIn('Numbers::Num(area.spellId, "radius_yards")', update)
        self.assertIn('EnemyEffects::Taken(enemy, area.spellId, Numbers::Num(area.spellId, "damage_bonus_pct"), Tune("marked_for_death_area_buff_seconds"));', update)
        self.assertIn("area.left -= diff;", update)
        self.assertIn("if (!player->IsAlive()) { Stop(player); return; }", update)
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn("if (RuneAt(spellId) == Rune::ValleyOfDeath)", cast)
        self.assertIn('area.left = Numbers::Num(spellId, "duration_seconds") * Passive::DurationFactor(player, "Marked for Death") * 1000.0;', cast)
        self.assertIn("OnPlayerMapChanged", self.code)
        self.assertIn("OnPlayerLogout", self.code)

    def test_mortal_enemy_pays_the_demon_hunter_and_death_toll_heals_any_attacker(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void RegisterScripts(")]
        self.assertIn("if (player->GetGUID() == mark->owner)", landed)
        self.assertIn('Proc::Scaled(coefficient, Numbers::Num(mark->spellId, "gain_resource"))', landed)
        self.assertIn("Resources::Energize(player, Resources::Hatred, mark->spellId, gain);", landed)
        self.assertIn('Proc::Scaled(coefficient, LifeBack(player->GetMaxHealth(), Numbers::Num(mark->spellId, "heal_pct")))', landed)
        self.assertIn("Heal(player, mark->spellId, heal);", landed)


if __name__ == "__main__":
    unittest.main()

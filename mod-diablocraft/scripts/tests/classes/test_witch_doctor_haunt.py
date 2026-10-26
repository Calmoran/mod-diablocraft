"""Witch Doctor Haunt and its five runes (src/classes/witch_doctor/dc_witch_doctor_haunt.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_haunt/harness.cpp compiles the real dc_witch_doctor_haunt.h and the shared
    damage-over-time arithmetic with the sheets' own rune names and numbers: each rune name is its rune; only Resentful Spirits releases two
    spirits; the haunt's ticks make the 4000% and the last falls when the 12 seconds end; a cast passes over an enemy freshly haunted; the
    sixth spirit displaces the oldest; Consuming Spirit's 0.008 of the Healing table is the sheet's 4291 Life a second; Draining Spirit's
    150 Mana over the haunt is the sheet's 12 a second rounded down; a spirit jumps to the nearest enemy and a lingering one looks for
    the sheet's 10 seconds; the clock gives a search every 1.25 seconds. Eleven mutations planted in a scratch copy (two runes share a
    name, every rune releases two, a cast never passes over a haunted enemy, the sixth spirit never displaces, the newest is displaced, the
    share of the table is lost, a tick returns the whole second, the jump goes to the farthest enemy, the lingering never ends, the
    clock loses its rest, the haunt never ends) must each make it fail.
  * **The record needs no change.** The cast is the engine's single-enemy cast (a `single_enemy` row of skill_targeting.csv, an
    `instant_dot`); the Mana cost and each rune's school are the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of witch_doctor_skill_values.csv for Haunt (or the
    rune that states it): 50 Mana, 4000% over 12 seconds, Lingering Spirit's 10 seconds, Poisoned Spirit's 20%; every tunable is a row of
    data/tunables/witchdoctor.csv, and the numbers equal the decoded Power/Witchdoctor_Haunt.pow (skipped where the game archives are
    not on this machine).
  * **The wiring.** The dispatch answers the damage and cast seams; the spirit's ticks run on the player's own queue; a fallen host sends
    the spirit to the nearest free enemy, a lingering rune looks on; Poisoned Spirit weakens the host and the new host through the shared
    enemy effects; Consuming Spirit and Draining Spirit pay through the core's heal and the class's Mana.

What it does not prove: anything on a running server. The spirit, its jump, the five at most, the Life, the Mana and the second spirit are
docs/test-diablocraft-vxrcu.14.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_haunt.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_haunt.h"
CLOCK = "src/classes/witch_doctor/dc_witch_doctor_clock.h"
PICK = "src/classes/witch_doctor/dc_witch_doctor_pick.h"
PERIODIC = "src/combat/dc_periodic_strike.h"
SOURCES = [HEADER, CLOCK, PICK, PERIODIC, "tests/witch_doctor_haunt/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_haunt.cpp"
SKILL = "Haunt"
RUNES = ["Consuming Spirit", "Lingering Spirit", "Poisoned Spirit", "Draining Spirit", "Resentful Spirits"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_haunt/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("haunt_resentful_spirit_count"), tune("haunt_max_spirits"), value("", "damage_pct"),
                         value("", "dot_duration_seconds"), tune("haunt_tick_seconds"), value("Lingering Spirit", "duration_seconds"),
                         tune("haunt_consuming_healing_share"), healing_table_70(), value("Consuming Spirit", "heal_per_second_life"),
                         tune("haunt_draining_total_mana"), value("Draining Spirit", "regen_per_second_resource"),
                         tune("haunt_skip_below_seconds"), tune("haunt_jump_check_seconds")]
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
            ("two runes share a name", (HEADER, 'if (name == "Poisoned Spirit")\n            return Rune::PoisonedSpirit;',
                                        'if (name == "Poisoned Spirit")\n            return Rune::ConsumingSpirit;')),
            ("every rune releases two", (HEADER, "return rune == Rune::ResentfulSpirits ? std::max(1u, static_cast<unsigned>(resentful + 0.5)) : 1u;",
                                         "return std::max(1u, static_cast<unsigned>(resentful + 0.5));")),
            ("a cast never passes over a haunted enemy", (HEADER, "return leftSeconds > minLeft;", "return false;")),
            ("the sixth spirit never displaces", (HEADER, "if (startedAt.size() < most || startedAt.empty())", "if (true)")),
            ("the newest is displaced", (HEADER, "std::min_element(startedAt.begin(), startedAt.end())", "std::max_element(startedAt.begin(), startedAt.end())")),
            ("the table's share is lost", (HEADER, "return share > 0 && table > 0 ? share * table : 0.0;", "return share > 0 && table > 0 ? table : 0.0;")),
            ("a tick returns the whole second", (CLOCK, "return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;",
                                                 "return perSecond > 0 && tickSeconds > 0 ? perSecond : 0.0;")),
            ("the jump goes to the farthest enemy", (PICK, "std::min_element(distances.begin(), distances.end())", "std::max_element(distances.begin(), distances.end())")),
            ("the lingering never ends", (HEADER, "return lingerSeconds > 0 && waitedSeconds < lingerSeconds;", "return lingerSeconds > 0;")),
            ("the clock loses its rest", (CLOCK, "clock -= interval;", "clock = 0;")),
            ("the haunt never ends", (CLOCK, "return std::max(0.0, leftSeconds - std::max(0.0, tickSeconds));", "return leftSeconds;")),
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
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["cast_type"]), ("single_enemy", "instant_dot"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", n) for n in ("cost_resource", "damage_pct", "dot_duration_seconds")], [50, 4000, 12])
        self.assertEqual(value("Lingering Spirit", "duration_seconds"), 10)
        self.assertEqual(value("Poisoned Spirit", "damage_taken_pct"), 20)
        self.assertEqual(value("Consuming Spirit", "heal_per_second_life"), 4291)
        self.assertEqual(value("Draining Spirit", "regen_per_second_resource"), 12)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("haunt_max_spirits", "5", "SF_8"), ("haunt_spread_yards", "80", "SF_10"),
                                 ("haunt_jump_check_seconds", "1.25", "SF_11"), ("haunt_cursor_yards", "15", "SF_18"),
                                 ("haunt_skip_below_seconds", "1", "SF_17"), ("haunt_consuming_healing_share", "0.008", "SF_2"),
                                 ("haunt_draining_total_mana", "150", "SF_3")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/Witchdoctor_Haunt.pow", rows[name]["notes"])
        self.assertEqual((rows["haunt_resentful_spirit_count"]["d3_value"], rows["haunt_resentful_spirit_count"]["value"]), ("2", ""))
        # The designer's standing default (AGENTS.md "Numbers", 2026-10-22), set in his column: a burn or bleed ticks every 0.5 seconds.
        self.assertEqual((rows["haunt_tick_seconds"]["d3_value"], rows["haunt_tick_seconds"]["value"]), ("", "0.5"))
        self.assertIn("standing default", rows["haunt_tick_seconds"]["notes"])
        for name, row in rows.items():
            if name.startswith("haunt_"):
                self.assertNotIn("placeholder", row["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("haunt_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "dot_duration_seconds", "duration_seconds", "damage_taken_pct"})
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("", "dot_duration_seconds", "own"), ("Lingering Spirit", "damage_pct", "inherited"),
                                    ("Lingering Spirit", "duration_seconds", "own"), ("Poisoned Spirit", "damage_taken_pct", "own")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token)]["origin"], origin)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_Haunt.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(12) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(13), value("", "dot_duration_seconds"))
        self.assertAlmostEqual(number(4), value("Lingering Spirit", "duration_seconds"))
        self.assertAlmostEqual(number(5) * 100, value("Poisoned Spirit", "damage_taken_pct"))
        self.assertIn("0.008", str(sf[2]))
        self.assertAlmostEqual(0.008 * healing_table_70(), value("Consuming Spirit", "heal_per_second_life"), delta=1.0)
        self.assertIn("150 / SF_13", str(sf[3]))
        self.assertAlmostEqual(150 / number(13), value("Draining Spirit", "regen_per_second_resource"), delta=1.0)
        for name, n in (("haunt_max_spirits", 8), ("haunt_spread_yards", 10), ("haunt_jump_check_seconds", 11), ("haunt_cursor_yards", 18),
                        ("haunt_skip_below_seconds", 17), ("haunt_consuming_healing_share", None), ("haunt_draining_total_mana", None)):
            if n:
                self.assertAlmostEqual(number(n), tune(name), msg=name)
        self.assertAlmostEqual(tune("haunt_consuming_healing_share"), 0.008)
        self.assertAlmostEqual(tune("haunt_draining_total_mana"), 150)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("Haunt::BasePct(spellId)"), 1)
        self.assertEqual(self.dispatch.count("Haunt::Cast(player, spellId, targets);"), 1)

    def test_the_cast_hits_nothing_and_the_spirit_ticks_on_the_players_queue(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        schedule = self.code[self.code.index("void Schedule("):self.code.index("// The spirit's tick")]
        self.assertIn("player->m_Events.AddEventAtOffset(", schedule)
        tick = self.code[self.code.index("void Tick(Player* player, std::uint64_t stamp) {"):self.code.index("// One spirit on")]
        self.assertIn("Combat::Strike(player, host, spellId,", tick)
        self.assertIn('PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), ticks), true);', tick)
        self.assertIn("if (!player->IsAlive() || !player->IsInWorld()) { Drop(player, stamp); return; }", tick)

    def test_a_fallen_host_sends_the_spirit_on_and_only_lingering_looks_on(self):
        tick = self.code[self.code.index("void Tick(Player* player, std::uint64_t stamp) {"):self.code.index("// One spirit on")]
        fallen = tick[tick.index("// \"If the enemy dies"):]
        self.assertIn('NearestFree(player, spellId, spirit.lastSeen, Tune("haunt_spread_yards"), host)', fallen)
        self.assertIn("else if (rune == Rune::LingeringSpirit) { spirit.lingering = true;", fallen)
        self.assertIn('Due(spirit.checkClock, tick * 1000.0, Tune("haunt_jump_check_seconds") * 1000.0)', tick)
        self.assertIn('StillLooking(spirit.waited, Numbers::Num(spellId, "duration_seconds"))', tick)

    def test_each_rune_does_its_one_thing(self):
        self.assertIn("if (RuneAt(spellId) == Rune::PoisonedSpirit) EnemyEffects::Taken(host, spellId, Numbers::Num(spellId, \"damage_taken_pct\"), seconds);", self.code)
        self.assertEqual(self.code.count("Weaken(next, spellId, spirit.leftSeconds);"), 2)
        self.assertIn("Weaken(host, spellId, spirit.leftSeconds);", self.code)
        self.assertIn("EnemyEffects::Remove(displaced, displacedSpell);", self.code)
        self.assertIn('LifePerSecond(Tune("haunt_consuming_healing_share"), Healing::At(player->GetLevel()))', self.code)
        self.assertIn('ManaPerSecond(Tune("haunt_draining_total_mana"), Duration())', self.code)
        self.assertIn("Gain(player, Classes::ClassIdOf(player), spellId,", self.code)
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Spirits(RuneAt(spellId), Tune("haunt_resentful_spirit_count"))', cast)
        self.assertIn('PassesOver(found->second, Tune("haunt_skip_below_seconds"))', cast)
        self.assertIn('Tune("haunt_cursor_yards")', cast)
        release = self.code[self.code.index("void Release("):self.code.index("} // namespace")]
        self.assertIn('Displaced(orders, unsigned(Tune("haunt_max_spirits")))', release)


if __name__ == "__main__":
    unittest.main()

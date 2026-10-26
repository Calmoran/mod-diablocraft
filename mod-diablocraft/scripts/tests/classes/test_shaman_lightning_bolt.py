"""Shaman Lightning Bolt and its five runes (src/classes/shaman/dc_shaman_lightning_bolt.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_lightning_bolt/harness.cpp compiles the real dc_shaman_lightning_bolt.h with the
    sheets' own rune names and numbers: each rune name is its rune; an Overload comes up below its chance; Hailstone adds Maelstrom
    against a chilled enemy only and Stormcaller on a critical hit only; the Earthen Spike mark raises a Physical hit on the marked
    enemy and holds for its seconds. Mutations planted in a scratch copy must each make it fail.
  * **The records.** Lava Beam is a beam through every enemy in a line: the migration combat_0132 gives its record the line shape
    (a `line_pierce` row, 30 yards and 3 wide) where the base bolt and the other runes keep one enemy.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Lightning Bolt (or the
    rune that states it); the draft's numbers are the sheet's, the code types none.
  * **The wiring.** The class dispatch answers the seams (`Landed` and the target-aware `Multipliers`) and the engine calls them at
    both places a hit lands and where its multipliers are computed; Overload's second strike starts nothing; Hailstone reads the chill
    before it gives its own; the mark belongs to the Shaman who made it.

What it does not prove: anything on a running server. The bolt, the beam, the chill, the mark and the Maelstrom are
docs/test-diablocraft-xnrvn.12.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_lightning_bolt.py
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
HEADER = "src/classes/shaman/dc_shaman_lightning_bolt.h"
BUCKETS = "src/combat/dc_damage_buckets.h"
HARNESS = MODULE / "tests/shaman_lightning_bolt/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_lightning_bolt.cpp"
SKILL = "Lightning Bolt"
RUNES = ["Overload", "Lava Beam", "Hailstone", "Earthen Spike", "Stormcaller"]
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0132_shaman_lightning_bolt_lava_beam_pierces.sql"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def waiting_runes():
    """The runes whose record the loader would give no hit (dc_combat_internal.h DamageWaits): the record or its skill states a duration."""
    waits = {"dot_duration_seconds", "duration_seconds", "duration_minutes"}
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL]
    base = any(r["rune"] == "" and (r["token"] in waits or (r["token"], r["qualifier"]) == ("damage_pct", "ramp")) for r in rows)
    names = []
    for rune in [""] + RUNES:
        own = any(r["rune"] == rune and (r["token"] in waits or (r["token"], r["qualifier"]) == ("damage_pct", "ramp")) for r in rows)
        if base or own:
            names.append(rune)
    return names


def runes():
    rows = sorted((r for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (HEADER, BUCKETS)}
    if mutate:
        old, new = mutate
        key = HEADER[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = RUNES + [value("Overload", "proc_chance_pct"), value("Hailstone", "gain_resource"), value("Earthen Spike", "damage_taken_pct"),
                       value("Earthen Spike", "duration_seconds"), value("Stormcaller", "gain_resource"), ",".join(waiting_runes())]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 7, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Lava Beam")\n            return Rune::LavaBeam;', 'if (name == "Lava Beam")\n            return Rune::Overload;')),
            ("an Overload always comes up", ("return chancePct > 0 && roll * 100.0 < chancePct;", "return chancePct > 0;")),
            ("an Overload comes up at the chance", ("roll * 100.0 < chancePct", "roll * 100.0 <= chancePct")),
            ("Hailstone adds against any enemy", ("return chilled && gain > 0 ? gain : 0.0;", "return gain > 0 ? gain : 0.0;")),
            ("Hailstone adds nothing", ("return chilled && gain > 0 ? gain : 0.0;", "return 0.0;")),
            ("Stormcaller adds on any hit", ("return critical && gain > 0 ? gain : 0.0;", "return gain > 0 ? gain : 0.0;")),
            ("the mark raises a hit of another element", ("return marked && physical && pct > 0 ? pct : 0.0;", "return marked && pct > 0 ? pct : 0.0;")),
            ("the mark raises an unmarked enemy's hit", ("return marked && physical && pct > 0 ? pct : 0.0;", "return physical && pct > 0 ? pct : 0.0;")),
            ("the skill leaves Earthen Spike's hit to the loader", ("inline bool ClaimsHit(Rune)\n    {\n        return true;", "inline bool ClaimsHit(Rune rune)\n    {\n        return rune != Rune::EarthenSpike;")),
            ("the mark holds a millisecond long", ("return nowMs < untilMs;", "return nowMs <= untilMs;")),
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
    def test_earthen_spikes_record_is_one_the_loader_would_give_no_hit(self):
        # The case this test guards: the rune states the mark's seconds, which DamageWaits reads as a damage that waits.
        self.assertEqual(waiting_runes(), ["Earthen Spike"])

    def test_the_five_runes(self):
        self.assertEqual(runes(), RUNES)

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\(spellId, "([a-z_]+)"\)', code))
        self.assertGreaterEqual(len(reads), 7, reads)
        rows = {(r["rune"], r["token"]) for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        held = {token for _rune, token in rows}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("Overload", "proc_chance_pct"), value("Overload", "damage_pct"), value("Lava Beam", "damage_pct"),
                          value("Hailstone", "damage_pct"), value("Hailstone", "chill_pct"), value("Hailstone", "chill_duration_seconds"),
                          value("Hailstone", "gain_resource"), value("Earthen Spike", "damage_pct"), value("Earthen Spike", "damage_taken_pct"),
                          value("Earthen Spike", "duration_seconds"), value("Stormcaller", "generated_resource", "new"),
                          value("Stormcaller", "gain_resource")],
                         [20, 285, 270, 300, 30, 2, 4, 320, 10, 4, 16, 4])
        self.assertEqual(value("", "damage_pct"), 285)
        self.assertEqual(value("", "generated_resource"), 12)

    def test_lava_beam_is_a_line_through_every_enemy(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        beam = rows["Lightning Bolt - Lava Beam"]
        self.assertEqual((beam["target_type"], beam["range_yards"], beam["width_yards"]), ("line_pierce", "30", "3"))
        # The bolt and the other runes keep the one enemy.
        self.assertEqual(rows[SKILL]["target_type"], "single_enemy")
        for rune in RUNES:
            if rune != "Lava Beam":
                self.assertNotIn(f"{SKILL} - {rune}", rows, rune)

    def test_the_migration_gives_lava_beams_record_the_line(self):
        text = MIGRATION.read_text(encoding="utf-8")
        shells = {r["name"]: r for r in read(MODULE / "data/generated/spell_shells.csv")}
        beam = shells[f"{SKILL} - Lava Beam"]["spell_id"]
        self.assertIn(f"INSERT INTO dc_spell_targeting VALUES ({beam},'line_pierce','NUMERIC',30.0,0.0,3.0);", text)
        self.assertNotIn(f"VALUES ({shells[SKILL]['spell_id']},'line_pierce'", text)
        self.assertEqual((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8").count(f"VALUES ({beam},'line_pierce'"), 1)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))
        self.resolve = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.combat = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (!IsShaman(player)) return; LightningBolt::Landed(player, target, spellId, critical);", self.dispatch)
        self.assertIn("if (IsShaman(player)) { LightningBolt::Multipliers(player, target, spellId, out);", self.dispatch)

    def test_the_engine_calls_the_seams_where_a_hit_lands_and_is_computed(self):
        self.assertEqual(self.resolve.count("Shaman::Landed(player, target, shell.spellId, hit.critical);"), 1)
        self.assertEqual(self.resolve.count("Shaman::Landed(player, target, spellId, hit.critical);"), 1)
        self.assertEqual(self.combat.count("Shaman::Multipliers(player, target, shell.spellId, hit.factors);"), 1)
        # Beside the other classes' calls, inside the same blocks.
        self.assertLess(self.resolve.index("WitchDoctor::Landed(player, target, shell.spellId);"), self.resolve.index("Shaman::Landed(player, target, shell.spellId, hit.critical);"))
        self.assertLess(self.resolve.index("Shaman::Landed(player, target, shell.spellId, hit.critical);"), self.resolve.index("WitchDoctor::Pets::Landed(player, target, shell.spellId);"))

    def test_overloads_second_strike_starts_nothing(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Multipliers(")]
        self.assertIn("if (striking || !player || !target) return;", landed)
        self.assertIn("Overloads(frand(0.0f, 1.0f), Numbers::Num(spellId, \"proc_chance_pct\"))", landed)
        self.assertIn('striking = true; Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct")); striking = false;', landed)

    def test_hailstone_reads_the_chill_before_it_gives_its_own(self):
        landed = self.code[self.code.index("case Rune::Hailstone:"):self.code.index("case Rune::EarthenSpike:")]
        self.assertLess(landed.index("Chilled(player, target)"), landed.index("Chill(player, target,"))
        self.assertIn('Chill(player, target, Numbers::Num(spellId, "chill_pct"), Numbers::Num(spellId, "chill_duration_seconds"));', landed)
        self.assertIn('Gain(player, spellId, ChilledGain(chilled, Numbers::Num(spellId, "gain_resource")));', landed)

    def test_the_mark_is_the_shamans_who_made_it_and_raises_physical_hits(self):
        landed = self.code[self.code.index("case Rune::EarthenSpike:"):self.code.index("case Rune::Stormcaller:")]
        self.assertIn('Numbers::Num(spellId, "duration_seconds") * 1000.0', landed)
        self.assertIn('mark.pct = Numbers::Num(spellId, "damage_taken_pct");', landed)
        self.assertIn("marks[target->GetGUID().GetRawValue()] = mark;", landed)
        multipliers = self.code[self.code.index("void Multipliers("):]
        self.assertIn("if (found->second.owner == player->GetGUID()) pct = found->second.pct;", multipliers)
        self.assertIn("MarkBonus(pct > 0, PhysicalHit(spellId), pct)", multipliers)
        self.assertIn('AddFactor(out, "Earthen Spike", bonus);', multipliers)
        self.assertIn("info->GetSchoolMask() == SPELL_SCHOOL_MASK_NORMAL", self.code)
        self.assertIn("if (!Holds(Now(), found->second.until)) { marks.erase(found); return; }", multipliers)

    def test_the_skill_hands_the_loader_every_records_hit(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Landed(")]
        self.assertIn("if (!Is(spellId) || !ClaimsHit(RuneAt(spellId))) return std::nullopt;", base)
        self.assertIn('return Numbers::Num(spellId, "damage_pct");', base)
        self.assertIn("std::optional<double> PrimaryBasePct(std::uint32_t spellId) { if (auto lightningBolt = LightningBolt::BasePct(spellId)) return lightningBolt;", self.dispatch)
        loader = "else if (auto shamanPrimary = Shaman::PrimaryBasePct(ability.id)) shell.damagePct = *shamanPrimary;"
        self.assertEqual(self.combat.count(loader), 1)
        # Ahead of the rule that reads a duration as a wait, and beside the other classes' claims.
        self.assertLess(self.combat.index("DemonHunter::BasePct(ability.id)"), self.combat.index(loader))
        self.assertLess(self.combat.index(loader), self.combat.index("!DamageWaits(ability.id)"))

    def test_stormcaller_adds_on_a_critical_hit(self):
        landed = self.code[self.code.index("case Rune::Stormcaller:"):]
        self.assertIn('Gain(player, spellId, CriticalGain(critical, Numbers::Num(spellId, "gain_resource")));', landed)

    def test_the_chill_is_the_effects_slow_and_the_stock_hold_is_the_look(self):
        chill = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_chill.cpp").read_text(encoding="utf-8"))
        effects = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_effects.cpp").read_text(encoding="utf-8"))
        self.assertIn("constexpr std::uint32_t SlowHold = 50259;", effects)
        self.assertIn("constexpr std::uint32_t SlowHold = 50259;", chill)
        self.assertIn("Slow(player, target, pct, seconds);", chill)
        self.assertIn("target->HasAura(SlowHold, player->GetGUID())", chill)


if __name__ == "__main__":
    unittest.main()

"""Shaman Earth Elemental and its five runes (src/classes/shaman/dc_shaman_earth_elemental.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_earth_elemental/harness.cpp compiles the real dc_shaman_earth_elemental.h with the
    sheets' and tunables' own names and numbers: each rune name is its rune; only Bedrock reads the new damage reduction; as many stomps
    fit the seconds as the interval allows; a tick of a zone deals above 0 and the ticks of a second add up; an arc goes to an enemy
    outside the stomp's reach; it stands until its seconds are over. Mutations planted in a scratch copy must each make it fail.
  * **Every damage it deals passes its own percent.** Every record states a duration, so the loader gives the cast's own hit none
    (DamageWaits) and the stomps, zones and arcs are strikes with their percent; the test reads the sheet for each (stomp, Primal Earth
    Elemental, Magma Colossus, the arcs) and pins that each is above 0 and passed.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Earth Elemental (or the
    rune that states it); the four numbers the draft does not give are rows of data/tunables/combat.csv, rendered into the tunables
    migration current_migration.txt names.
  * **The wiring.** The class dispatch answers the ground seam beside the Earthquake's; one elemental per Shaman at a time (a new cast
    takes a new stamp) and apart from the Fire Elemental's state; the elemental is skill damage with no creature and no taunt.

What it does not prove: anything on a running server. The stomps, the reduction and each rune's effect are
docs/test-diablocraft-xnrvn.35.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_earth_elemental.py
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
HEADERS = ["src/classes/shaman/dc_shaman_earth_elemental.h", "src/combat/dc_periodic_strike.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_earth_elemental/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_earth_elemental.cpp"
SKILL = "Earth Elemental"
RUNES = ["Bedrock", "Primal Earth Elemental", "Magma Colossus", "Thunder Colossus", "Glacial Colossus"]
TUNABLES = {
    "earth_elemental_zone_tick_seconds": "1",
    "earth_elemental_arc_radius_yards": "30",
    "earth_elemental_arc_damage_pct": "250",
    "earth_elemental_glacial_mark_seconds": "3",
}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunable(name):
    return float({r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}[name]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in HEADERS}
    if mutate:
        old, new = mutate
        key = HEADER[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = RUNES + [value("", "duration_seconds"), value("", "interval_seconds"), value("Primal Earth Elemental", "damage_pct"),
                       tunable("earth_elemental_zone_tick_seconds"), value("", "radius_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 8, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Magma Colossus")\n            return Rune::MagmaColossus;', 'if (name == "Magma Colossus")\n            return Rune::GlacialColossus;')),
            ("every rune reads the new reduction", ('return rune == Rune::Bedrock ? "new" : "";', 'return "new";')),
            ("Bedrock reads the old reduction", ('return rune == Rune::Bedrock ? "new" : "";', 'return "";')),
            ("a stomp fits a second too many", ("return DC::Combat::PeriodicStrike::Ticks(seconds, intervalSeconds);", "return DC::Combat::PeriodicStrike::Ticks(seconds + intervalSeconds, intervalSeconds);")),
            ("no stomp ever", ("return DC::Combat::PeriodicStrike::Ticks(seconds, intervalSeconds);", "return 0;")),
            ("a zone tick deals nothing", ("return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;", "return 0.0;")),
            ("a zone tick deals the whole second", ("return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;", "return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct : 0.0;")),
            ("an arc may go inside the reach", ("return std::hypot(ex - cx, ey - cy) > radius;", "return true;")),
            ("an arc cannot go outside the reach", ("return std::hypot(ex - cx, ey - cy) > radius;", "return false;")),
            ("an arc goes at the reach's edge", ("return std::hypot(ex - cx, ey - cy) > radius;", "return std::hypot(ex - cx, ey - cy) >= radius;")),
            ("it stands a millisecond long", ("return nowMs < untilMs;", "return nowMs <= untilMs;")),
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

    def test_every_damage_it_deals_is_above_0(self):
        # Every record states a duration, so the cast's own hit loads at 0 by design; these are what the strikes pass.
        self.assertGreater(value("", "damage_pct"), 0)
        self.assertGreater(value("Primal Earth Elemental", "damage_pct"), 0)
        self.assertGreater(value("Magma Colossus", "damage_pct"), 0)
        self.assertGreater(tunable("earth_elemental_arc_damage_pct"), 0)
        self.assertGreater(value("", "interval_seconds"), 0)
        self.assertGreater(value("", "duration_seconds"), value("", "interval_seconds"))

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|BaseId\(\)), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 9, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "interval_seconds"), value("", "damage_pct"), value("", "radius_yards"),
                          value("", "damage_reduction_pct"), value("", "duration_seconds"), value("Bedrock", "damage_reduction_pct", "new"),
                          value("Bedrock", "damage_reduction_pct", "base"), value("Primal Earth Elemental", "duration_seconds"),
                          value("Primal Earth Elemental", "damage_pct"), value("Magma Colossus", "damage_pct"), value("Magma Colossus", "duration_seconds"),
                          value("Thunder Colossus", "stun_duration_seconds"), value("Thunder Colossus", "target_count"),
                          value("Glacial Colossus", "freeze_duration_seconds"), value("Glacial Colossus", "damage_taken_pct")],
                         [90, 2, 500, 15, 20, 15, 35, 20, 2, 300, 250, 3, 1, 3, 1, 10])

    def test_the_tunables_are_rows_of_the_combat_sheet_and_of_the_migration(self):
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / name).read_text(encoding="utf-8")
        self.assertEqual(migration, (MODULE / "data/generated" / name).read_text(encoding="utf-8"))
        for tunable_name, number in TUNABLES.items():
            with self.subTest(tunable_name):
                self.assertEqual(rows[tunable_name]["value"], number)
                self.assertTrue(rows[tunable_name]["notes"].strip())
                self.assertIn(f"('combat', '{tunable_name}', NULL, {float(number)},", migration)

    def test_the_code_reads_only_tunables_the_sheet_has(self):
        used = set(re.findall(r'Tune\("([a-z_]+)"\)', CODE.read_text(encoding="utf-8")))
        self.assertEqual(used, set(TUNABLES))

    def test_it_rises_at_a_place_the_caster_aims_at(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        row = rows[SKILL]
        self.assertEqual((row["target_type"], row["range_yards"], row["radius_yards"]), ("ground_area", "30", "15"))
        self.assertEqual(float(row["radius_yards"]), value("", "radius_yards"))


class Creature(unittest.TestCase):
    """The look: an untargetable creature with a stock Earth Elemental model that stands where it rose, in minions_0007."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(MODULE / "scripts/generate/classes"))
        import generate_shaman_elemental_summons as generator
        cls.generator = generator
        cls.rows = {r["summon"]: r for r in generator.rows(MODULE)}  # also checks the entries are not taken

    def test_the_sheet_row_is_the_stock_greater_earth_elemental_for_the_skill(self):
        row = self.rows["Earth Elemental"]
        self.assertEqual((row["skill"], row["rune"], row["entry"], row["donor_creature"], row["script"]), (SKILL, "", "900191", "15352", "dc_minion"))

    def test_the_code_raises_the_sheets_entry(self):
        self.assertIn(f"constexpr std::uint32_t Entry = {self.rows['Earth Elemental']['entry']};", CODE.read_text(encoding="utf-8"))

    def test_the_migration_is_the_generators_render_and_the_creature_cannot_be_selected(self):
        migration = (MODULE / "data/sql/db-world/updates/minions_0007_shaman_elemental_summons.sql").read_text(encoding="utf-8")
        self.assertEqual(migration, self.generator.render(MODULE))
        self.assertEqual(migration.count("unit_flags=33554432,unit_flags2=0,"), 2)
        self.assertIn("WHERE entry=15352;", migration)
        self.assertIn("INSERT INTO creature_template_model SELECT 900191,", migration)

    def test_the_two_elementals_have_their_own_entries(self):
        self.assertNotEqual(self.rows["Earth Elemental"]["entry"], self.rows["Fire Elemental"]["entry"])


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_ground_seam_beside_the_earthquake(self):
        self.assertIn("if (IsShaman(player)) { Earthquake::Ground(player, spellId, center); EarthElemental::Ground(player, spellId, center); }", self.dispatch)

    def test_the_skill_claims_no_hit_and_every_strike_passes_its_percent(self):
        self.assertNotIn("BasePct", self.code)
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Num(BaseId(), "damage_pct"));', self.code)
        self.assertIn("Combat::Strike(player, enemy, spellId, pct, true);", self.code)
        self.assertIn('Combat::Strike(player, enemy, spellId, Tune("earth_elemental_arc_damage_pct"));', self.code)
        self.assertIn("if (!ticks || pct <= 0) return;", self.code)
        self.assertIn("if (!stomps) return;", self.code)

    def test_the_creature_rises_with_the_elemental_stands_where_it_rose_and_leaves_with_it(self):
        ground = self.code[self.code.index("void Ground("):self.code.index("void RegisterScripts()")]
        self.assertIn("Minions::Dismiss(player, Group); Minions::Raise(player, Group, center);", ground)
        end = self.code[self.code.index("void End("):self.code.index("void Zone(")]
        self.assertIn("PutReduction(player, 0); Minions::Dismiss(player, Group);", end)
        define = self.code[self.code.index("void RegisterScripts()"):]
        self.assertIn("Minions::Define(Group,", define)
        self.assertIn("kind.entry = Entry;", define)
        self.assertIn("kind.cap = 1;", define)
        self.assertIn("kind.staysPut = true;", define)
        self.assertNotIn("damagePct", define)
        self.assertNotIn("auraPct", define)
        self.assertIn("FireElemental::RegisterScripts(); EarthElemental::RegisterScripts();", self.dispatch)

    def test_one_at_a_time_apart_from_the_fire_elemental_and_no_taunt(self):
        ground = self.code[self.code.index("void Ground("):self.code.index("void RegisterScripts()")]
        self.assertIn("Standing& elemental = standing[key]; stamp = elemental.stamp = ++stamps;", ground)
        stomp = self.code[self.code.index("void Stomp("):self.code.index("} // namespace bool Is(")]
        self.assertIn("found == standing.end() || found->second.stamp != stamp", stomp)
        self.assertIn("!player->IsInWorld() || !player->IsAlive() || player->GetMap() != elemental.map", stomp)
        for forbidden in ("SummonCreature", "TempSummon", "ScriptedAI", "Taunt(", "FireElemental", "damagePct"):
            self.assertNotIn(forbidden, self.code)

    def test_the_reduction_is_worn_while_it_stands_and_taken_off_at_the_end(self):
        ground = self.code[self.code.index("void Ground("):self.code.index("void RegisterScripts()")]
        self.assertIn('PutReduction(player, Numbers::Num(spellId, "damage_reduction_pct", ReductionQualifier(rune)));', ground)
        end = self.code[self.code.index("void End("):self.code.index("void Zone(")]
        self.assertIn("standing.erase(found); } PutReduction(player, 0);", end)
        put = self.code[self.code.index("void PutReduction("):self.code.index("void End(")]
        self.assertIn("{Source::Temporary, Stat::SpecificReduction, BaseId(), pct, Bucket::Flat}", put)

    def test_each_runes_stomp_effect(self):
        stomp = self.code[self.code.index("void Stomp("):self.code.index("} // namespace bool Is(")]
        self.assertIn('Combat::Enemies(player, spellId, elemental.center, Numbers::Num(spellId, "radius_yards"))', stomp)
        self.assertIn('Stun(player, enemy, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));', stomp)
        self.assertIn('Freeze(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds"));', stomp)
        self.assertIn('DamageMark::Set(player, enemy, Numbers::Num(spellId, "damage_taken_pct"), Tune("earth_elemental_glacial_mark_seconds"));', stomp)
        self.assertIn("if (elemental.rune == Rune::ThunderColossus) Arcs(player, elemental);", stomp)
        self.assertIn('StartZone(player, elemental, Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "duration_seconds"));', stomp)
        self.assertIn("if (elemental.rune == Rune::PrimalEarthElemental || elemental.rune == Rune::MagmaColossus)", stomp)

    def test_the_arcs_go_to_the_nearest_enemies_outside_the_reach(self):
        arcs = self.code[self.code.index("void Arcs("):self.code.index("void Stomp(")]
        self.assertIn('Tune("earth_elemental_arc_radius_yards")', arcs)
        self.assertIn("!Outside(elemental.center.GetPositionX(), elemental.center.GetPositionY(), enemy->GetPositionX(), enemy->GetPositionY(), radius)", arcs)
        self.assertIn('auto const count = std::size_t(Numbers::Num(spellId, "target_count"));', arcs)
        self.assertIn("if (far.size() > count) far.resize(count);", arcs)


if __name__ == "__main__":
    unittest.main()

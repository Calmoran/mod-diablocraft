"""Shaman Earthquake (Shaman) and its five runes (src/classes/shaman/dc_shaman_earthquake.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_earthquake/harness.cpp compiles the real dc_shaman_earthquake.h with the sheets'
    and tunables' own names and numbers: each rune name is its rune; only Thundering Earth states the ticks' damage; only Rolling Quake
    follows the Shaman; a tick strikes all that stand inside or, for Thundering Earth, a few; **the hit of a tick is above 0 for every
    rune** (the sheet's damage over its seconds, the ticks adding up to it); the area is round; Frozen Tundra's chill lasts through the
    next tick and its freeze comes every interval; Magma Chamber raises Lava Burst for an enemy inside; Earth Shock adds Maelstrom for a
    target inside. Mutations planted in a scratch copy must each make it fail.
  * **The cast deals nothing at once.** Every record states a duration, so the loader gives the cast's own hit none (DamageWaits); the
    ticks deal the damage with their own percent, and the test pins that the skill claims no hit and that every tick strike passes its
    percent.
  * **The records.** Rolling Quake is centred on the Shaman: a `self_aoe` row of skill_targeting.csv (12 yards), rendered into the newest
    combat migration, the generated spell shells and the client Spell.dbc, where the skill and the other runes stay a ground area.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Earthquake (Shaman) (or
    the rune that states it); the two numbers the draft does not give are rows of data/tunables/combat.csv, rendered into the tunables
    migration current_migration.txt names.
  * **The wiring.** The class dispatch answers the seams and the engine calls the Ground seam beside the other classes'; one Earthquake
    per Shaman, a new cast taking a new stamp; Flame Shock's Earth Shock asks the Earthquake whether the target stands inside.

What it does not prove: anything on a running server. The area, the knock down, the eruption, the following, the bonus, the chill, the
freeze and the strikes are docs/test-diablocraft-xnrvn.27.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_earthquake.py
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
HEADERS = ["src/classes/shaman/dc_shaman_earthquake.h", "src/combat/dc_damage_buckets.h", "src/combat/dc_periodic_strike.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_earthquake/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_earthquake.cpp"
SKILL = "Earthquake (Shaman)"
RUNES = ["Aftershock", "Rolling Quake", "Magma Chamber", "Frozen Tundra", "Thundering Earth"]
TUNABLES = {"earthquake_tick_seconds": "1", "earthquake_thundering_strikes_per_tick": "2"}
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0136_shaman_rolling_quake_is_centred_on_the_shaman.sql"


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
    numbers = RUNES + [value("", "damage_pct"), value("Thundering Earth", "damage_pct"), value("", "dot_duration_seconds"),
                       tunable("earthquake_tick_seconds"), value("", "radius_yards"), value("Rolling Quake", "radius_yards"),
                       value("Magma Chamber", "damage_taken_pct"), flame_gain(), value("Frozen Tundra", "interval_seconds"),
                       tunable("earthquake_thundering_strikes_per_tick")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


def flame_gain():
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"]) == ("Flame Shock", "Earth Shock", "gain_resource")]
    assert len(rows) == 1
    return float(rows[0]["value"])


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 14, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Frozen Tundra")\n            return Rune::FrozenTundra;', 'if (name == "Frozen Tundra")\n            return Rune::MagmaChamber;')),
            ("every rune states the ticks' damage", ("return rune == Rune::ThunderingEarth;\n    }\n\n    // Rolling", "return rune != Rune::None;\n    }\n\n    // Rolling")),
            ("Thundering Earth leaves the ticks to the skill", ("return rune == Rune::ThunderingEarth;\n    }\n\n    // Rolling", "return false;\n    }\n\n    // Rolling")),
            ("every Earthquake follows the Shaman", ("return rune == Rune::RollingQuake;", "return true;")),
            ("Rolling Quake stays where it was cast", ("return rune == Rune::RollingQuake;", "return false;")),
            ("Thundering Earth strikes all", ("return rune != Rune::ThunderingEarth;", "return true;")),
            ("Thundering Earth strikes too many", ("return StrikesAll(rune) ? inside : std::min(inside, most);", "return inside;")),
            ("Thundering Earth strikes too few", ("return StrikesAll(rune) ? inside : std::min(inside, most);", "return StrikesAll(rune) ? inside : std::min(inside, std::size_t(1));")),
            ("the area is a square", ("return radius > 0 && std::hypot(ex - cx, ey - cy) <= radius;", "return radius > 0 && std::fabs(ex - cx) <= radius && std::fabs(ey - cy) <= radius;")),
            ("the area has no edge", ("return radius > 0 && std::hypot(ex - cx, ey - cy) <= radius;", "return true;")),
            ("the chill ends before the next tick", ("return tickSeconds > 0 ? tickSeconds * 2.0 : 0.0;", "return tickSeconds > 0 ? tickSeconds * 0.5 : 0.0;")),
            ("a freeze comes every tick", ("return intervalSeconds > 0 && (lastMs == 0 || nowMs >= lastMs + std::uint64_t(intervalSeconds * 1000.0));", "return intervalSeconds > 0;")),
            ("a freeze waits a millisecond too long", ("nowMs >= lastMs + std::uint64_t", "nowMs > lastMs + std::uint64_t")),
            ("every rune raises Lava Burst", ("return rune == Rune::MagmaChamber && inside && pct > 0 ? pct : 0.0;", "return inside && pct > 0 ? pct : 0.0;")),
            ("Magma Chamber raises it outside the area", ("return rune == Rune::MagmaChamber && inside && pct > 0 ? pct : 0.0;", "return rune == Rune::MagmaChamber && pct > 0 ? pct : 0.0;")),
            ("Earth Shock adds outside the area", ("return inside && gain > 0 ? gain : 0.0;", "return gain > 0 ? gain : 0.0;")),
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

    def test_every_record_states_a_duration_so_the_casts_own_hit_is_none_and_the_ticks_deal_the_damage(self):
        # DamageWaits reads the duration as a damage that waits: every Earthquake record loads with no hit, by design.
        rows = [r for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL]
        self.assertTrue(any(r["rune"] == "" and r["token"] == "dot_duration_seconds" for r in rows))

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|quake\.spellId|id|BaseId\(\)|OwnsTickDamage\(rune\) \? spellId : BaseId\(\)), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 9, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "cost_resource"), value("", "radius_yards"), value("", "damage_pct"), value("", "dot_duration_seconds"),
                          value("", "proc_chance_pct"), value("", "duration_seconds"), value("Aftershock", "damage_pct"), value("Rolling Quake", "radius_yards"),
                          value("Magma Chamber", "damage_taken_pct"), value("Frozen Tundra", "chill_pct"), value("Frozen Tundra", "freeze_duration_seconds"),
                          value("Frozen Tundra", "interval_seconds"), value("Thundering Earth", "damage_pct"), value("Thundering Earth", "dot_duration_seconds"),
                          flame_gain()],
                         [50, 15, 2600, 8, 10, 1, 800, 12, 10, 50, 1, 3, 3000, 8, 6])

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

    def test_rolling_quake_is_centred_on_the_shaman(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"], rows[SKILL]["radius_yards"]), ("ground_area", "30", "15"))
        rolling = rows[f"{SKILL} - Rolling Quake"]
        self.assertEqual((rolling["target_type"], rolling["range_yards"], rolling["radius_yards"]), ("self_aoe", "SELF", "12"))
        self.assertEqual(float(rolling["radius_yards"]), value("Rolling Quake", "radius_yards"))
        for rune in RUNES:
            if rune != "Rolling Quake":
                self.assertNotIn(f"{SKILL} - {rune}", rows, rune)

    def test_the_newest_combat_migration_and_the_shells_give_the_record_its_shape(self):
        shells = {r["name"]: r["spell_id"] for r in read(MODULE / "data/generated/spell_shells.csv")}
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        migration = MIGRATION.read_text(encoding="utf-8")
        rolling = f"VALUES ({shells[f'{SKILL} - Rolling Quake']},'self_aoe','SELF',0,12.0,0.0);"
        self.assertEqual(sql.count(rolling), 1)
        self.assertIn(rolling, migration)
        for rune in ("", " - Aftershock", " - Magma Chamber", " - Frozen Tundra", " - Thundering Earth"):
            line = f"VALUES ({shells[SKILL + rune]},'ground_area','NUMERIC',30.0,15.0,0.0);"
            self.assertEqual(sql.count(line), 1, rune)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))
        self.resolve = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.flame = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_flame_shock.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_and_the_engine_answer_the_seams(self):
        self.assertIn("LavaBurst::Multipliers(player, target, spellId, out); Earthquake::Multipliers(player, target, spellId, out);", self.dispatch)
        self.assertIn("void Ground(Player* player, std::uint32_t spellId, Position const& center) { if (IsShaman(player)) { Earthquake::Ground(player, spellId, center);", self.dispatch)
        self.assertEqual(self.resolve.count("Shaman::Ground(player, shell.spellId, center);"), 1)
        self.assertLess(self.resolve.index("WitchDoctor::Ground(player, shell.spellId, center);"), self.resolve.index("Shaman::Ground(player, shell.spellId, center);"))
        self.assertLess(self.resolve.index("Shaman::Ground(player, shell.spellId, center);"), self.resolve.index("if (connected) Connected(player, shell.spellId, connected);"))

    def test_the_skill_claims_no_hit_and_every_tick_passes_its_percent(self):
        self.assertNotIn("BasePct", self.code)
        self.assertIn("Combat::Strike(player, enemy, quake.spellId, pct, true);", self.code)
        self.assertIn('double const pct = PeriodicStrike::TickPct(Numbers::Num(OwnsTickDamage(rune) ? spellId : BaseId(), "damage_pct"), ticks);', self.code)
        self.assertIn('unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);', self.code)
        self.assertIn("if (!ticks) return;", self.code)

    def test_one_earthquake_per_shaman_and_a_new_cast_takes_a_new_stamp(self):
        ground = self.code[self.code.index("void Ground("):self.code.index("bool Inside(Player* player")]
        self.assertIn("Quake& quake = quakes[key]; stamp = quake.stamp = ++stamps;", ground)
        tick = self.code[self.code.index("void Tick("):self.code.index("bool Is(")]
        self.assertIn("found == quakes.end() || found->second.stamp != stamp", tick)
        self.assertIn("!player->IsInWorld() || !player->IsAlive() || player->GetMap() != quake.map", tick)

    def test_aftershock_erupts_when_it_ends(self):
        tick = self.code[self.code.index("void Tick("):self.code.index("bool Is(")]
        self.assertIn("if (quake.rune == Rune::Aftershock) Erupt(player, quake);", tick)
        self.assertLess(tick.index("if (left > 1)"), tick.index("Erupt(player, quake)"))
        erupt = self.code[self.code.index("void Erupt("):self.code.index("void Tick(")]
        self.assertIn('Combat::Strike(player, enemy, quake.spellId, Numbers::Num(quake.spellId, "damage_pct"));', erupt)

    def test_the_ticks_knock_down_and_frozen_tundra_chills_and_freezes(self):
        tick = self.code[self.code.index("void Tick("):self.code.index("bool Is(")]
        self.assertIn('frand(0.0f, 100.0f) < Numbers::Num(quake.spellId, "proc_chance_pct")', tick)
        self.assertIn('Stun(player, enemy, Numbers::Num(quake.spellId, "duration_seconds"));', tick)
        self.assertIn('Chill(player, enemy, Numbers::Num(quake.spellId, "chill_pct"), ChillSeconds(intervalMs / 1000.0));', tick)
        self.assertIn('Freeze(player, enemy, Numbers::Num(quake.spellId, "freeze_duration_seconds"));', tick)
        self.assertIn('FreezeDue(Now(), quake.lastFreeze, Numbers::Num(quake.spellId, "interval_seconds"))', tick)

    def test_rolling_quake_follows_and_thundering_earth_strikes_a_few(self):
        centre = self.code[self.code.index("void Centre("):self.code.index("void Erupt(")]
        self.assertIn("if (Follows(quake.rune)) { x = player->GetPositionX(); y = player->GetPositionY(); return; }", centre)
        tick = self.code[self.code.index("void Tick("):self.code.index("bool Is(")]
        self.assertIn('Struck(quake.rune, inside.size(), std::size_t(Tune("earthquake_thundering_strikes_per_tick")))', tick)
        self.assertIn("inside.resize(struck);", tick)

    def test_magma_chamber_and_earth_shock_ask_whether_the_target_is_inside(self):
        multipliers = self.code[self.code.index("void Multipliers("):]
        self.assertIn('std::string_view(row->skill) != "Lava Burst"', multipliers)
        self.assertIn('MagmaBonus(rune, Inside(player, target), Numbers::Num(id, "damage_taken_pct"))', multipliers)
        self.assertIn('AddFactor(out, "Magma Chamber", bonus);', multipliers)
        self.assertIn('Gain(player, spellId, Earthquake::EarthShockGain(Earthquake::Inside(player, target), Numbers::Num(spellId, "gain_resource")));', self.flame)


if __name__ == "__main__":
    unittest.main()

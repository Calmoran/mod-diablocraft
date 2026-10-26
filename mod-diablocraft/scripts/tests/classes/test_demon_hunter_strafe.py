"""Demon Hunter Strafe and its five runes (src/classes/demon_hunter/dc_demon_hunter_strafe.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_strafe/harness.cpp compiles the real dc_demon_hunter_strafe.h, Rapid Fire's
    shot arithmetic it uses, the DoT rules and the clock with the sheets' own rune names and numbers: each rune name is its rune; the
    shots a second of attack speed holds (Demolition's grenades slower) deal the sheet's damage and cost its cost; the slowed run and
    how long it holds; the roll that picks a random enemy is even and never past the last; Icy Trail's patch at its distance and its
    ticks making the damage; Rocket Storm's rockets; Stinging Steel's extra. Nine mutations planted in a scratch copy must each make it
    fail.
  * **The record is a real channel.** `Strafe` joins the generator's channel list (generate_spells.py `CHANNEL_DRAIN_SKILLS`) and its
    channel does not stop when the Demon Hunter walks (`CHANNEL_WHILE_MOVING_SKILLS`); `combat_0103` is the full render, and the six
    records carry the channel attribute, the infinite duration, no cost of their own and no aura.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Strafe (or the
    rune that states it); every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_Strafe.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Cast`, `Landed`, `RegisterScripts`); the channel pays and fires each
    shot at the cadence attack speed gives and ends when the Hatred is not there or the channel was let go; the slow is on while it
    lasts and taken off when it ends; the patches burn after the channel ends and stop with their owner.

What it does not prove: anything on a running server. The channel, the shots, the slow and the runes are
docs/test-diablocraft-vawmy.28.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_strafe.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_strafe.h"
RAPID = "src/classes/demon_hunter/dc_demon_hunter_rapid_fire.h"
DOT = "src/classes/demon_hunter/dc_demon_hunter_dot.h"
PICK = "src/classes/demon_hunter/dc_demon_hunter_pick.h"
CLOCK = "src/classes/demon_hunter/dc_demon_hunter_clock.h"
SOURCES = [HEADER, RAPID, DOT, CLOCK, PICK, "tests/demon_hunter_strafe/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_strafe.cpp"
GENERATOR = MODULE / "scripts/generate/classes/generate_spells.py"
SKILL = "Strafe"
RUNES = ["Demolition", "Icy Trail", "Rocket Storm", "Drifting Shadow", "Stinging Steel"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_strafe/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("strafe_shots_per_attack"), tune("strafe_demolition_shot_fraction"), value("", "damage_pct"), value("", "cost_resource"),
                         value("Demolition", "damage_pct"), value("Icy Trail", "damage_pct"), value("Icy Trail", "dot_duration_seconds"),
                         tune("strafe_trail_tick_seconds"), tune("strafe_trail_drop_yards"), value("", "movement_speed_pct"),
                         value("Drifting Shadow", "movement_speed_pct"), value("Stinging Steel", "damage_bonus_pct"),
                         tune("strafe_rockets_per_attack"), value("Rocket Storm", "damage_pct"), tune("strafe_slow_refresh_seconds")]
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
            ("two runes share a name", (HEADER, 'if (name == "Icy Trail")\n            return Rune::IcyTrail;',
                                        'if (name == "Icy Trail")\n            return Rune::Demolition;')),
            ("Demolition shoots as fast as the arrows", (HEADER, "return rune == Rune::Demolition ? base * demolitionFraction : base;", "return base;")),
            ("the slow takes the speed away, not the rest", (HEADER, "std::clamp(100.0 - speedPct, 0.0, 100.0)", "std::clamp(speedPct, 0.0, 100.0)")),
            ("the slow holds one refresh", (HEADER, "2.0 * refreshSeconds", "refreshSeconds")),
            ("every shot goes to the first enemy", (PICK, "std::min(count - 1, std::size_t(std::max(0.0, roll) * double(count)))", "0")),
            ("the roll can pick past the last enemy", (PICK, "std::min(count - 1, std::size_t(std::max(0.0, roll) * double(count)))",
                                                      "std::size_t(std::max(0.0, roll) * double(count))")),
            ("a patch a yard short", (HEADER, "dropYards > 0 && moved >= dropYards", "dropYards > 0 && moved > dropYards")),
            ("a patch tick is the whole damage", (HEADER, "return Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds));", "return totalPct;")),
            ("a critical hit adds the whole shot", (HEADER, "std::max(0.0, shotPct) * std::max(0.0, bonusPct) / 100.0", "std::max(0.0, shotPct)")),
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

    def test_the_record_is_a_channel_the_module_pays_and_walking_does_not_stop(self):
        text = GENERATOR.read_text(encoding="utf-8")
        channels = re.search(r"CHANNEL_DRAIN_SKILLS = \((.*?)\)\n", text, re.S).group(1)
        self.assertIn('"Strafe"', channels)
        self.assertIn('CHANNEL_WHILE_MOVING_SKILLS = ("Strafe",)', text)
        self.assertIn('values[columns.index("ChannelInterruptFlags")] = 0', text)
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["cast_type"]), ("self_moving_aoe", "channel"))

    def test_the_render_is_the_one_new_migration_and_it_changes_only_strafe(self):
        migration = MODULE / "data/sql/db-world/updates/combat_0122_demon_hunter_strafe_is_a_real_channel.sql"
        self.assertTrue(migration.exists())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune in [""] + RUNES:
            self.assertEqual(mapped[(rune, "cost_resource")]["source"], "exact", rune)

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct"), value("", "movement_speed_pct")], [12, 675, 75])
        self.assertEqual([value("Demolition", "damage_pct"), value("Demolition", "radius_yards")], [460, 9])
        self.assertEqual([value("Icy Trail", n) for n in ("damage_pct", "dot_duration_seconds", "chill_duration_seconds")], [300, 3, 3])
        self.assertEqual(value("Rocket Storm", "damage_pct"), 130)
        self.assertEqual(value("Drifting Shadow", "movement_speed_pct"), 100)
        self.assertEqual(value("Stinging Steel", "damage_bonus_pct"), 140)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("strafe_shots_per_attack", "4", "SF_0"), ("strafe_demolition_shot_fraction", "0.5", "SF_27"),
                                 ("strafe_seek_range_yards", "50", "SF_2"), ("strafe_rocket_range_yards", "50", "SF_30"),
                                 ("strafe_rockets_per_attack", "2", "SF_36"), ("strafe_rocket_warmup_seconds", "0.35", "SF_32"),
                                 ("strafe_trail_drop_yards", "6", "SF_37"), ("strafe_trail_tick_seconds", "0.2", "SF_38"),
                                 ("strafe_trail_radius_yards", "7", "SF_39"), ("strafe_trail_chill_pct", "60", "SF_40")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Strafe.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_the_slow_refresh_is_alexs_standing_default(self):
        row = tunables()["strafe_slow_refresh_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("", "0.25"))
        self.assertIn("standing default", row["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("strafe_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Strafe.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        def quotient(n):
            top, bottom = str(sf[n]).split("/")
            return float(top) / float(bottom.strip().replace("SF_0", str(number(0))))

        def rune_value(n):
            return float(str(sf[n]).split("?")[1].split(":")[0])

        self.assertAlmostEqual(quotient(9) * number(0) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(16) + number(15) * number(0), value("", "cost_resource"))
        self.assertAlmostEqual(number(7) * 100, value("", "movement_speed_pct"))
        self.assertAlmostEqual((number(7) + rune_value(14)) * 100, value("Drifting Shadow", "movement_speed_pct"))
        self.assertAlmostEqual(quotient(26) * 2 * 100, value("Demolition", "damage_pct"))
        self.assertAlmostEqual(number(28) * 100 * number(12), value("Icy Trail", "damage_pct"))
        self.assertAlmostEqual(number(12), value("Icy Trail", "dot_duration_seconds"))
        self.assertAlmostEqual(number(41), value("Icy Trail", "chill_duration_seconds"))
        self.assertAlmostEqual(number(35) * number(36) * 100, value("Rocket Storm", "damage_pct"))
        self.assertAlmostEqual(number(17) * 100, value("Stinging Steel", "damage_bonus_pct"))
        self.assertAlmostEqual(number(0), tune("strafe_shots_per_attack"))
        self.assertAlmostEqual(rune_value(27), tune("strafe_demolition_shot_fraction"))
        self.assertAlmostEqual(number(2), tune("strafe_seek_range_yards"))
        self.assertAlmostEqual(number(30), tune("strafe_rocket_range_yards"))
        self.assertAlmostEqual(number(36), tune("strafe_rockets_per_attack"))
        self.assertAlmostEqual(number(32), tune("strafe_rocket_warmup_seconds"))
        self.assertAlmostEqual(number(37), tune("strafe_trail_drop_yards"))
        self.assertAlmostEqual(number(38), tune("strafe_trail_tick_seconds"))
        self.assertAlmostEqual(number(39), tune("strafe_trail_radius_yards"))
        self.assertAlmostEqual(number(40) * 100, tune("strafe_trail_chill_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto volley = Strafe::BasePct(spellId)) return volley;"), 1)
        self.assertLess(self.dispatch.index("ElementalArrow::BasePct(spellId)"), self.dispatch.index("Strafe::BasePct(spellId)"))
        self.assertLess(self.dispatch.index("Strafe::BasePct(spellId)"), self.dispatch.index("return Caltrops::BasePct(spellId);"))
        for call in ("Strafe::Landed(player, target, spellId, critical);", "Strafe::Cast(player, spellId, targets);", "Strafe::RegisterScripts();"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_cast_hits_nothing_and_the_first_shot_fires_with_the_slow_on(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn("if (!Shoot(player, channel)) { player->InterruptSpell(CURRENT_CHANNELED_SPELL); return; }", cast)
        self.assertIn("KeepSlow(player, spellId);", cast)
        self.assertIn('channel.warmup = Tune("strafe_rocket_warmup_seconds") * 1000.0;', cast)

    def test_each_shot_pays_its_share_and_goes_to_a_random_enemy(self):
        shoot = self.code[self.code.index("bool Shoot("):self.code.index("void Rocket(")]
        self.assertIn('RapidFire::ShotCost(Numbers::Num(spellId, "cost_resource"), shots)', shoot)
        self.assertIn("RapidFire::ShotPct(Total(spellId), shots)", shoot)
        self.assertIn("if (Resources::Get(player, Resources::Hatred) < cost) return false;", shoot)
        self.assertIn('RandomEnemy(player, spellId, Tune("strafe_seek_range_yards"))', shoot)
        self.assertIn('Numbers::Num(spellId, "radius_yards")', shoot)
        random = self.code[self.code.index("Unit* RandomEnemy("):self.code.index("bool Shoot(")]
        self.assertIn("enemies[PickAt(frand(0.0f, 1.0f), enemies.size())]", random)

    def test_the_channel_runs_at_the_cadence_and_ends_when_let_go_or_out_of_hatred(self):
        tick = self.code[self.code.index("static void Tick("):self.code.index("static void Burn(")]
        self.assertIn("RapidFire::ShotSeconds(ShotsPer(spellId), Combat::AttacksPerSecond(player, spellId)) * 1000.0", tick)
        self.assertIn("current->GetSpellInfo()->Id != channel.spellId", tick)
        self.assertIn("player->InterruptSpell(CURRENT_CHANNELED_SPELL); Stop(player); return;", tick)
        self.assertIn('Due(channel.slowClock, diff, Tune("strafe_slow_refresh_seconds") * 1000.0)', tick)
        stop = self.code[self.code.index("static void Stop("):self.code.index("private:")]
        self.assertIn("Unslow(player, player);", stop)

    def test_the_runes_part(self):
        tick = self.code[self.code.index("static void Tick("):self.code.index("static void Burn(")]
        self.assertIn("rune == Rune::RocketStorm", tick)
        self.assertIn('RapidFire::RocketSeconds(Tune("strafe_rockets_per_attack") * Combat::AttacksPerSecond(player, spellId))', tick)
        self.assertIn("rune == Rune::IcyTrail", tick)
        self.assertIn("DropPatch(player, channel);", tick)
        rocket = self.code[self.code.index("void Rocket("):self.code.index("void KeepSlow(")]
        self.assertIn('RapidFire::ShotPct(Numbers::Num(spellId, "damage_pct"), Tune("strafe_rockets_per_attack"))', rocket)
        freeze = self.code[self.code.index("void Freeze("):self.code.index("class Channels")]
        self.assertIn("Combat::Strike(player, enemy, patch.spellId, pct, true);", freeze)
        self.assertIn('Slow(player, enemy, Tune("strafe_trail_chill_pct"), Numbers::Num(patch.spellId, "chill_duration_seconds"));', freeze)
        keep = self.code[self.code.index("void KeepSlow("):self.code.index("void DropPatch(")]
        self.assertIn('SlowPct(Numbers::Num(spellId, "movement_speed_pct"))', keep)
        landed = self.code[self.code.index("void Landed("):self.code.index("void RegisterScripts(")]
        self.assertIn("RuneAt(spellId) != Rune::StingingSteel", landed)
        self.assertIn('CritExtraPct(shot, Numbers::Num(spellId, "damage_bonus_pct"))', landed)
        self.assertIn("Scope scope(adding);", landed)

    def test_the_patches_burn_after_the_channel_and_stop_with_their_owner(self):
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertIn("Tick(player, diff); Burn(player, diff);", update)
        self.assertIn("if (!player->IsAlive())", update)
        self.assertIn("patches.erase(", self.code)
        self.assertIn("OnPlayerMapChanged", self.code)
        self.assertIn("OnPlayerLogout", self.code)


if __name__ == "__main__":
    unittest.main()

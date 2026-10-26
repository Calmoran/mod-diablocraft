"""Demon Hunter Rapid Fire and its five runes (src/classes/demon_hunter/dc_demon_hunter_rapid_fire.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_rapid_fire/harness.cpp compiles the real
    dc_demon_hunter_rapid_fire.h with the sheets' own rune names and numbers: each rune name is its rune; a second of attack
    speed holds 6 shots (3 grenades for Bombardment) so a shot is a sixth of the 685% and of the 6 Hatred a second; the clock
    gives whole shots and keeps the rest; and held for ten seconds of server updates at one and at one and a half attacks a second the
    channel keeps shooting at the cadence and spends the Hatred a second the sheet says. Eight mutations planted in a scratch copy (two
    runes share a name, attack speed slows the shots, a shot is the whole second's damage or cost, the rockets are not spaced, the
    clock loses its rest, never fires on the moment, has no cap) must each make it fail.
  * **The record is the channel.** The migration combat_0099 (and the render it carries) gives the skill and its five runes
    SPELL_ATTR1_IS_CHANNELED, the Wizard channels' duration, no cost of their own (the module pays the start and each shot) and no aura.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of demon_hunter_skill_values.csv for Rapid
    Fire (or the rune that states it): 20 Hatred to start (10 for Withering Fire) and 6 a second, 685% a second, Bombardment's 545%
    in 8 yards, High Velocity's 50%, Fire Support's 2 rockets of 145%, Frost Shots' 80% chill for 2 seconds; every tunable is a row of
    data/tunables/demonhunter.csv, and the numbers equal the decoded Power/DemonHunter_RapidFire.pow (skipped where the game archives
    are not on this machine).
  * **The wiring.** The dispatch answers the cast, the register and the can-cast seams, the engine calls them, the cast arrives once
    at the channel's start and pays it, a shot that cannot be paid ends the channel, and the channel ends with the core's.

What it does not prove: anything on a running server. The held channel, the shots, the grenades, the pierce, the rockets and the chill
are docs/test-diablocraft-vawmy.13.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_rapid_fire.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_rapid_fire.h"
CLOCK = "src/classes/demon_hunter/dc_demon_hunter_clock.h"
SOURCES = [HEADER, CLOCK, "tests/demon_hunter_rapid_fire/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_rapid_fire.cpp"
SKILL = "Rapid Fire"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0099_demon_hunter_rapid_fire_and_siphon_blood_channels.sql"


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_rapid_fire/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("rapid_fire_shots_per_attack"), tune("rapid_fire_bombardment_shots_per_attack"),
                         value("", "cost_resource", "channel"), value("", "damage_pct"), value("Bombardment", "damage_pct"),
                         value("Fire Support", "projectile_count")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 24, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Fire Support")\n            return Rune::FireSupport;', 'if (name == "Fire Support")\n            return Rune::FrostShots;')),
            ("attack speed slows the shots", (HEADER, "1.0 / (attacksPerSecond * shotsPerAttack)", "1.0 * attacksPerSecond / shotsPerAttack")),
            ("a shot is the whole second's damage", (HEADER, "damagePct / shotsPerAttack : 0.0", "damagePct : 0.0")),
            ("a shot is the whole second's cost", (HEADER, "channelCost / shotsPerAttack : 0.0", "channelCost : 0.0")),
            ("the rockets are not spaced", (HEADER, "1.0 / rocketsPerSecond", "1.0")),
            ("the clock loses its rest", (CLOCK, "clock -= interval;", "clock = 0;")),
            ("a shot is never due on the moment", (CLOCK, "while (clock >= interval && due < cap)", "while (clock > interval && due < cap)")),
            ("the clock has no cap", (CLOCK, "due < cap)", "true)")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Records(unittest.TestCase):
    def test_the_skill_and_its_runes_are_the_channel_with_no_cost_of_their_own(self):
        migration = MIGRATION.read_text(encoding="utf-8")
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", migration).group(1).split(",")]
        ids = {r[1]: int(r[0]) for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
               if r and r[0].isdigit() and r[4] in ("active", "rune")}
        names = [n for n in ids if n == SKILL or n.startswith(SKILL + " - ")]
        self.assertEqual(len(names), 6)

        def record(spell):
            row = re.search(r"\(%d,([^\n]*)\)[,;]?\n" % spell, migration)
            return dict(zip(columns, ("%d," % spell + row.group(1)).split(",")))

        ray = record(83104)
        for name in names:
            with self.subTest(name):
                r = record(ids[name])
                self.assertEqual(int(r["AttributesEx"]) & 0x4, 0x4)
                self.assertEqual(r["DurationIndex"], ray["DurationIndex"])
                self.assertEqual((r["ManaCost"], r["PowerType"], r["EffectAura_1"]), ("0", "0", "0"))


CORE_AURA_DEFINES = REPO / "azerothcore-wotlk/src/server/game/Spells/SpellDefines.h"
SHELLS = MODULE / "data/generated/spell_shells.sql"
UPDATES = MODULE / "data/sql/db-world/updates"
SIPHON_BLOOD = "Siphon Blood"


def core_flag(name):
    return int(re.search(r"\b%s\s*=\s*(0x[0-9A-Fa-f]+)" % name, CORE_AURA_DEFINES.read_text(encoding="utf-8"))[1], 16)


def render_records():
    """{spell id: {column: value}} of every spell_dbc row in the generated render (the numeric columns before the first string)."""
    render = SHELLS.read_text(encoding="utf-8")
    columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", render).group(1).split(",")]
    numeric = columns.index("Name_Lang_enUS")
    return {int(m[1]): dict(zip(columns[:numeric], m[0].split(",")[:numeric]))
            for m in re.finditer(r"^\((\d+),[^\n]*", render, re.M) for m in [(m[0][1:], m[1])]}


def names_to_ids(skill):
    ids = {r[1]: int(r[0]) for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
           if r and r[0].isdigit() and r[4] in ("active", "rune")}
    return {n: i for n, i in ids.items() if n == skill or n.startswith(skill + " - ")}


class Walking(unittest.TestCase):
    """Rapid Fire stops when the Demon Hunter walks, and keeps channelling while she stands, turns or is hit.

    The core ends a channel through the record's ChannelInterruptFlags (Unit::RemoveAurasWithInterruptFlags on a step), and the
    module's loop ends with the core's channel (Wiring), so the flag on the six records is the whole rule."""

    def test_the_skill_and_each_rune_end_when_the_demon_hunter_moves(self):
        records, move = render_records(), core_flag("AURA_INTERRUPT_FLAG_MOVE")
        names = names_to_ids(SKILL)
        self.assertEqual(len(names), 6)
        for name, spell in names.items():
            with self.subTest(name):
                self.assertTrue(int(records[spell]["ChannelInterruptFlags"]) & move)

    def test_standing_keeps_it_channelling(self):
        # Only movement interrupts: turning to aim, being hit or hit by a spell, jumping and casting through it stay out.
        records, move = render_records(), core_flag("AURA_INTERRUPT_FLAG_MOVE")
        for name, spell in names_to_ids(SKILL).items():
            with self.subTest(name):
                self.assertEqual(int(records[spell]["ChannelInterruptFlags"]), move)
                for other in ("AURA_INTERRUPT_FLAG_TURNING", "AURA_INTERRUPT_FLAG_TAKE_DAMAGE", "AURA_INTERRUPT_FLAG_HITBYSPELL"):
                    self.assertFalse(int(records[spell]["ChannelInterruptFlags"]) & core_flag(other), other)

    def test_siphon_blood_keeps_the_channel_flags_it_had(self):
        # The Necromancer's channel is the Wizard channels' (combat_0099 gave it Ray of Frost's); this change does not touch it.
        records = render_records()
        ray = records[83104]["ChannelInterruptFlags"]
        self.assertNotEqual(ray, "0")
        for name, spell in names_to_ids(SIPHON_BLOOD).items():
            with self.subTest(name):
                self.assertEqual(records[spell]["ChannelInterruptFlags"], ray)

    def test_a_migration_ships_the_render(self):
        # The render reaches dev as one numbered migration whose bytes are the generated file's.
        shipped = [p for p in UPDATES.glob("combat_*.sql") if p.read_bytes() == SHELLS.read_bytes()]
        self.assertEqual(len(shipped), 1, [p.name for p in shipped])


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["Bombardment", "High Velocity", "Fire Support", "Withering Fire", "Frost Shots"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource", q) for q in ("initial", "channel")], [20, 6])
        self.assertEqual(value("", "damage_pct"), 685)
        self.assertEqual([value("Bombardment", t) for t in ("damage_pct", "radius_yards")], [545, 8])
        self.assertEqual(value("High Velocity", "proc_chance_pct"), 50)
        self.assertEqual([value("Fire Support", t) for t in ("projectile_count", "damage_pct")], [2, 145])
        self.assertEqual(value("Withering Fire", "cost_resource", "initial"), 10)
        self.assertEqual([value("Frost Shots", t) for t in ("chill_pct", "chill_duration_seconds")], [80, 2])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("rapid_fire_shots_per_attack", "6", "SF_20"), ("rapid_fire_bombardment_shots_per_attack", "3", "SF_21"),
                                 ("rapid_fire_rocket_warmup_seconds", "0.7", "SF_12"), ("rapid_fire_rocket_range_yards", "50", "SF_25"),
                                 ("rapid_fire_grenade_range_yards", "50", "SF_15")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_RapidFire.pow", rows[name]["notes"])
        self.assertEqual((rows["rapid_fire_pierce_length_yards"]["d3_value"], rows["rapid_fire_pierce_length_yards"]["value"]), ("60", ""))
        # The designer's standing default (AGENTS.md "Numbers", 2026-10-22), set in his column: a line is 3 yards wide.
        self.assertEqual((rows["rapid_fire_pierce_width_yards"]["d3_value"], rows["rapid_fire_pierce_width_yards"]["value"]), ("", "3"))
        self.assertIn("standing default", rows["rapid_fire_pierce_width_yards"]["notes"])
        for name, row in rows.items():
            if name.startswith("rapid_fire_"):
                self.assertNotIn("PLACEHOLDER", row["notes"], name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("rapid_fire_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "cost_resource", "radius_yards", "proc_chance_pct", "chill_pct", "chill_duration_seconds",
                                  "projectile_count"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "cost_resource", "initial"), ("", "cost_resource", "channel"), ("", "damage_pct", ""),
                                       ("Bombardment", "damage_pct", ""), ("Bombardment", "radius_yards", ""),
                                       ("High Velocity", "proc_chance_pct", ""), ("Fire Support", "projectile_count", ""),
                                       ("Fire Support", "damage_pct", ""), ("Withering Fire", "cost_resource", "initial"),
                                       ("Frost Shots", "chill_pct", ""), ("Frost Shots", "chill_duration_seconds", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], "own")

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_RapidFire.pow"))["sf"]

        def number(n):
            return float(sf[n])

        def rune_part(n):
            return float(sf[n].split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(0) * number(20) * 100, value("", "damage_pct"), delta=0.01)
        self.assertAlmostEqual(number(4), value("", "cost_resource", "initial"))
        self.assertAlmostEqual(number(4) - rune_part(3), value("Withering Fire", "cost_resource", "initial"))
        self.assertAlmostEqual(number(17), value("", "cost_resource", "channel"))
        # SF_6 is "1.81667 * SF_27": a grenade's damage before the Grenadier passive, three of them in a second.
        self.assertAlmostEqual(float(sf[6].split("*")[0]) * number(21) * 100, value("Bombardment", "damage_pct"), delta=0.01)
        self.assertAlmostEqual(8, value("Bombardment", "radius_yards"))
        self.assertAlmostEqual(number(7) * 100, value("High Velocity", "proc_chance_pct"))
        self.assertAlmostEqual(number(16), value("Fire Support", "projectile_count"))
        self.assertAlmostEqual(number(23) * 100, value("Fire Support", "damage_pct"))
        self.assertAlmostEqual(number(8) * 100, value("Frost Shots", "chill_pct"))
        self.assertAlmostEqual(number(9), value("Frost Shots", "chill_duration_seconds"))
        self.assertAlmostEqual(number(20), tune("rapid_fire_shots_per_attack"))
        self.assertAlmostEqual(number(21), tune("rapid_fire_bombardment_shots_per_attack"))
        self.assertAlmostEqual(number(12), tune("rapid_fire_rocket_warmup_seconds"))
        self.assertAlmostEqual(number(25), tune("rapid_fire_rocket_range_yards"))
        self.assertAlmostEqual(number(15), tune("rapid_fire_grenade_range_yards"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        engine = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat/dc_combat_internal.h",
                                                                 *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.engine = re.sub(r"\s+", " ", engine)

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto disc = RapidFire::BasePct(spellId)) return disc;"), 1)
        self.assertLess(self.dispatch.index("Impale::BasePct(spellId)"), self.dispatch.index("RapidFire::BasePct(spellId)"))
        self.assertIn("RapidFire::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("RapidFire::RegisterScripts();", self.dispatch)
        self.assertIn("RapidFire::Affordable(player, spellId) ? SPELL_CAST_OK : SPELL_FAILED_NO_POWER", self.dispatch)

    def test_the_engine_calls_them(self):
        self.assertEqual(self.engine.count("DemonHunter::Cast(player, shell.spellId, targets);"), 1)
        self.assertLess(self.engine.index("Necromancer::Cast(player, shell.spellId, targets);"), self.engine.index("DemonHunter::Cast(player, shell.spellId, targets);"))
        self.assertEqual(self.engine.count("DemonHunter::RegisterScripts();"), 1)

    def test_the_start_is_paid_once_at_the_cast_and_a_shot_that_cannot_be_paid_ends_the_channel(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void RegisterScripts(")]
        self.assertIn('Numbers::Num(spellId, "cost_resource", "initial")', self.code)
        self.assertIn("Resources::SpendUnits(player, Resources::Hatred,", cast)
        self.assertLess(cast.index("Resources::SpendUnits"), cast.index("channels[player->GetGUID().GetRawValue()] = channel;"))
        shoot = self.code[self.code.index("bool Shoot("):self.code.index("void Rocket(")]
        self.assertIn("if (Resources::Get(player, Resources::Hatred) < cost) return false;", shoot)
        self.assertLess(shoot.index("return false;"), shoot.index("Resources::SpendUnits"))
        self.assertIn("if (!Shoot(player, target, channel)) {", self.code)
        self.assertIn("player->InterruptSpell(CURRENT_CHANNELED_SPELL);", self.code)

    def test_the_channel_ends_with_the_cores_and_the_skill_has_no_engine_hit(self):
        update = self.code[self.code.index("void OnPlayerUpdate("):]
        self.assertIn("!current || current->GetSpellInfo()->Id != channel.spellId", update)
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_each_rune_does_its_one_thing(self):
        shoot = self.code[self.code.index("bool Shoot("):self.code.index("void Rocket(")]
        self.assertIn('Numbers::Num(spellId, "radius_yards")', shoot)
        self.assertIn('Tune("rapid_fire_grenade_range_yards")', shoot)
        self.assertIn("Pierce(player, spellId, target, pct);", shoot)
        self.assertIn('Slow(player, target, Numbers::Num(spellId, "chill_pct"), Numbers::Num(spellId, "chill_duration_seconds"));', shoot)
        pierce = self.code[self.code.index("void Pierce("):self.code.index("bool Shoot(")]
        self.assertIn('roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct")))', pierce)
        self.assertIn("OnLine(", pierce)
        total = self.code[self.code.index("double Total("):self.code.index("double Initial(")]
        self.assertIn('Numbers::Num(BaseId(Skill), "damage_pct")', total)


if __name__ == "__main__":
    unittest.main()

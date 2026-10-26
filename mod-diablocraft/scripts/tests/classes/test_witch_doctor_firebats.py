"""Witch Doctor Firebats and its five runes (src/classes/witch_doctor/dc_witch_doctor_firebats.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_firebats/harness.cpp compiles the real dc_witch_doctor_firebats.h with the
    sheets' own rune names and numbers: each rune name is its rune; a second of attack speed holds 2 ticks (1 for Dire Bats) so a tick is
    half of the 475% and of the 125 Mana a second; the cone takes an enemy at its edge and not past it; Plague Bats' stacks rise by one a
    tick, stop at the most and start again once they lapse; Cloud of Bats' damage rises by a third each whole second to the sheet's 850%;
    the clock gives whole ticks and keeps the rest. Eleven mutations planted in a scratch copy (two runes share a name, attack speed slows
    the ticks, a tick is the whole second's damage or cost, the cone is twice as wide, the plague's stacks have no end or never lapse, its
    damage ignores the stacks, the cloud's bonus is not capped, the clock loses its rest, has no cap) must each make it fail.
  * **The record is the channel.** The migration combat_0123 (and the render it carries) gives the skill and its five runes
    SPELL_ATTR1_IS_CHANNELED, the Wizard channels' duration, no cost of their own (the module pays each tick, and Vampire Bats' start) and
    no aura.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of witch_doctor_skill_values.csv for Firebats
    (or the rune that states it): 125 Mana a second, 475% a second, Dire Bats' 500%, Hungry Bats' 750%, Plague Bats' 720%, Vampire Bats'
    250 Mana to start, Cloud of Bats' 425% rising to 850%; every tunable is a row of data/tunables/witchdoctor.csv, and the numbers equal
    the decoded Power/Witchdoctor_Firebats.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the cast, the register and the damage seams, the engine registers the class's scripts, the cast
    arrives once at the channel's start, Vampire Bats pays its start there, a tick that cannot be paid ends the channel, and the channel
    ends with the core's.

What it does not prove: anything on a running server. The held channel, the cone, the seeking bats, the stacks and the swirl are
docs/test-diablocraft-vxrcu.13.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_firebats.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_firebats.h"
CLOCK = "src/classes/witch_doctor/dc_witch_doctor_clock.h"
SOURCES = [HEADER, CLOCK, "tests/witch_doctor_firebats/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_firebats.cpp"
SKILL = "Firebats"
RUNES = ["Dire Bats", "Hungry Bats", "Plague Bats", "Vampire Bats", "Cloud of Bats"]
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0123_witch_doctor_firebats_is_a_real_channel.sql"


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_firebats/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("firebats_ticks_per_attack"), tune("firebats_dire_ticks_per_attack"), tune("firebats_hungry_ticks_per_attack"),
                         tune("firebats_cloud_ticks_per_attack"), value("", "cost_resource"), value("", "damage_pct"),
                         tune("firebats_cone_degrees"), tune("firebats_plague_max_stacks"), value("Plague Bats", "damage_pct"),
                         tune("firebats_cloud_stack_bonus"), tune("firebats_cloud_max_stacks"), value("Cloud of Bats", "damage_pct", "base"),
                         value("Cloud of Bats", "damage_pct", "maximum")]
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
            ("two runes share a name", (HEADER, 'if (name == "Hungry Bats")\n            return Rune::HungryBats;',
                                        'if (name == "Hungry Bats")\n            return Rune::DireBats;')),
            ("attack speed slows the ticks", (HEADER, "1.0 / (attacksPerSecond * ticksPerAttack)", "1.0 * attacksPerSecond / ticksPerAttack")),
            ("a tick is the whole second's damage or cost", (HEADER, "perAttack / ticksPerAttack : 0.0", "perAttack : 0.0")),
            ("the cone is twice as wide", (HEADER, "coneDegrees * 3.14159265358979323846 / 360.0", "coneDegrees * 3.14159265358979323846 / 180.0")),
            ("the plague's stacks have no end", (HEADER, "return std::min(held + 1u, most > 0 ? most : 1u);", "return held + 1u;")),
            ("the plague's stacks never lapse", (HEADER, "sinceMs <= lastsMs ? stacks : 0u", "stacks")),
            ("the plague's damage ignores its stacks", (HEADER, "mostPct * double(std::min(stacks, most)) / double(most)", "mostPct")),
            ("the cloud's bonus has no end", (HEADER, "std::min(std::floor(channelSeconds > 0 ? channelSeconds : 0.0), double(most))",
                                              "std::floor(channelSeconds > 0 ? channelSeconds : 0.0)")),
            ("the cloud's bonus grows between the seconds", (HEADER, "std::min(std::floor(channelSeconds > 0 ? channelSeconds : 0.0), double(most))",
                                                             "std::min(channelSeconds > 0 ? channelSeconds : 0.0, double(most))")),
            ("the clock loses its rest", (CLOCK, "clock -= interval;", "clock = 0;")),
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
                self.assertEqual((r["ManaCost"], r["EffectAura_1"]), ("0", "0"))

    def test_the_cast_is_the_cone_of_enemies(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"], rows[SKILL]["cast_type"]), ("cone_enemies", "28", "channel"))


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), RUNES)

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [125, 475])
        self.assertEqual([value("Dire Bats", "damage_pct"), value("Hungry Bats", "damage_pct"), value("Plague Bats", "damage_pct")], [500, 750, 720])
        self.assertEqual(value("Vampire Bats", "cost_resource"), 250)
        self.assertEqual([value("Cloud of Bats", "damage_pct", q) for q in ("base", "maximum")], [425, 850])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("firebats_ticks_per_attack", "2", "SF_25"), ("firebats_dire_ticks_per_attack", "1", "SF_26"),
                                 ("firebats_hungry_ticks_per_attack", "2", "SF_27"), ("firebats_cloud_ticks_per_attack", "2", "SF_28"),
                                 ("firebats_cone_yards", "28", "SF_3"), ("firebats_cone_degrees", "50", "SF_4"),
                                 ("firebats_hungry_range_yards", "60", "SF_10"), ("firebats_cloud_area_yards", "15", "SF_21"),
                                 ("firebats_plague_max_stacks", "3", "SF_22"), ("firebats_plague_stack_ticks", "2", "SF_11"),
                                 ("firebats_cloud_stack_bonus", "0.333", "SF_23"), ("firebats_cloud_max_stacks", "3", "SF_24")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/Witchdoctor_Firebats.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("firebats_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"cost_resource", "damage_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, qualifier, origin in (("", "cost_resource", "", "own"), ("", "damage_pct", "", "own"), ("Dire Bats", "damage_pct", "", "own"),
                                               ("Hungry Bats", "damage_pct", "", "own"), ("Plague Bats", "damage_pct", "", "own"),
                                               ("Vampire Bats", "cost_resource", "", "own"), ("Vampire Bats", "damage_pct", "", "inherited"),
                                               ("Cloud of Bats", "damage_pct", "base", "own"), ("Cloud of Bats", "damage_pct", "maximum", "own")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], origin)
        for rune in ("", *RUNES):
            self.assertEqual(mapped[(rune, "cost_resource", "")]["source"], "exact", rune)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_Firebats.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(2), value("", "cost_resource"))
        self.assertAlmostEqual(number(13) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(15) * 100, value("Dire Bats", "damage_pct"))
        self.assertAlmostEqual(number(18) * 100, value("Hungry Bats", "damage_pct"))
        self.assertAlmostEqual(number(13) * 1.515 * 100, value("Plague Bats", "damage_pct"), delta=0.5)
        self.assertIn("250", str(sf[31]))
        self.assertAlmostEqual(250, value("Vampire Bats", "cost_resource"))
        self.assertAlmostEqual(number(13) * 0.895 * 100, value("Cloud of Bats", "damage_pct", "base"), delta=0.5)
        self.assertAlmostEqual(value("Cloud of Bats", "damage_pct", "base") * (1 + number(23) * number(24)), value("Cloud of Bats", "damage_pct", "maximum"),
                               delta=1.0)
        for name, n in (("firebats_ticks_per_attack", 25), ("firebats_dire_ticks_per_attack", 26), ("firebats_hungry_ticks_per_attack", 27),
                        ("firebats_cloud_ticks_per_attack", 28), ("firebats_cone_yards", 3), ("firebats_cone_degrees", 4),
                        ("firebats_hungry_range_yards", 10), ("firebats_cloud_area_yards", 21), ("firebats_plague_max_stacks", 22),
                        ("firebats_cloud_stack_bonus", 23), ("firebats_cloud_max_stacks", 24)):
            self.assertAlmostEqual(number(n), tune(name), msg=name)
        # SF_11 is "(SF_22 * 2) * SF_7": the file's 2 ticks to a stack.
        self.assertIn("(SF_22 * 2)", str(sf[11]))
        self.assertAlmostEqual(tune("firebats_plague_stack_ticks"), 2)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))
        engine = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat/dc_combat_internal.h",
                                                                 *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.engine = re.sub(r"\s+", " ", engine)

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("Firebats::BasePct(spellId)"), 1)
        self.assertEqual(self.dispatch.count("Firebats::Cast(player, spellId, targets);"), 1)
        self.assertEqual(self.dispatch.count("Firebats::RegisterScripts();"), 1)

    def test_the_engine_registers_the_classes_scripts(self):
        self.assertEqual(self.engine.count("WitchDoctor::RegisterScripts();"), 1)

    def test_the_start_is_paid_once_at_the_cast_and_a_tick_that_cannot_be_paid_ends_the_channel(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void RegisterScripts(")]
        self.assertIn("if (RuneAt(spellId) == Rune::VampireBats)", cast)
        self.assertIn('Numbers::Num(spellId, "cost_resource")', cast)
        self.assertIn("Resources::SpendUnits(player, Resources::Mana,", cast)
        self.assertLess(cast.index("Resources::SpendUnits"), cast.index("channels[player->GetGUID().GetRawValue()] = channel;"))
        tick = self.code[self.code.index("bool Tick("):self.code.index("class Channels")]
        self.assertIn("rune == Rune::VampireBats ? 0.0 : TickShare(Numbers::Num(BaseId(Skill), \"cost_resource\"), ticks);", tick)
        self.assertIn("if (Resources::Get(player, Resources::Mana) < cost) return false;", tick)
        self.assertLess(tick.index("return false;"), tick.index("Resources::SpendUnits"))
        self.assertIn("if (!Tick(player, channel)) {", self.code)
        self.assertIn("player->InterruptSpell(CURRENT_CHANNELED_SPELL);", self.code)

    def test_the_channel_ends_with_the_cores_and_the_skill_has_no_engine_hit(self):
        update = self.code[self.code.index("void OnPlayerUpdate("):]
        self.assertIn("!current || current->GetSpellInfo()->Id != channel.spellId", update)
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        self.assertIn("// The first tick falls with the cast.", self.code)

    def test_each_rune_does_its_one_thing(self):
        tick = self.code[self.code.index("bool Tick("):self.code.index("class Channels")]
        self.assertIn('Tune("firebats_hungry_range_yards")', tick)
        self.assertIn("enemies[PickAt(frand(0.0f, 1.0f), enemies.size())]", tick)
        self.assertIn('Tune("firebats_cloud_area_yards")', tick)
        self.assertIn('Numbers::Num(spellId, "damage_pct", "base")', tick)
        self.assertIn("CloudFactor(channel.seconds / 1000.0,", tick)
        self.assertIn("PlagueStacks(plague.stacks,", tick)
        self.assertIn("PlaguePct(Numbers::Num(spellId, \"damage_pct\"), plague.stacks,", tick)
        self.assertIn("InCone(offset, Tune(\"firebats_cone_degrees\"))", self.code)
        ticks = self.code[self.code.index("double TicksPerAttack("):self.code.index("bool InFront(")]
        for rune, name in (("DireBats", "dire"), ("HungryBats", "hungry"), ("CloudOfBats", "cloud")):
            self.assertIn(f'case Rune::{rune}: return Tune("firebats_{name}_ticks_per_attack");', ticks)


if __name__ == "__main__":
    unittest.main()

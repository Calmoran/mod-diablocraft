"""diablocraft-plgq2 (pylons and shrines P1, docs/proposals/pylons.md 4.3 and 7): the eleven buffs.

  * data/pylon_buffs.csv against everything the generator made of it (the records' names, texts, $s numbers, the death
    flag on the pylons only, Shield's immunities, Empowered's regeneration auras, the header, the manifest, the
    migration), and every number against data/d3/pylons.csv, which is the D3 source and not the sheet under test;
  * src/combat/dc_pylon_math.h compiled with the module's real dc_common.cpp (Calculate) and dc_paragon_math.h and
    driven with the tunable rows: each kind's number reaches its stat or factor while it is in force and leaves when the
    buff ends, nothing works while dead, a saved sheet is cleaned at login; single-rule mutants fail the same driver;
  * Channeling's free Whirlwind tick: the sheet's Resource Cost Reduction with Channeling in force, through the core's
    own spell-modifier arithmetic (tests/cost_math's core harness, extracted from the pin), charges nothing;
  * the core pin: the death flag keeps a pylon's aura at death and only it, and a friendly heal passes Shield's school
    immunity; source guards that the module calls each piece where the plan puts it (they prove the call is there, not
    that it runs; syntax_check.sh compiles the C++, and the in-game steps are in docs/test-diablocraft-plgq2.md).
"""
import csv
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import affixes_text  # noqa: E402
import harness_env
import test_cost_math as cost
import test_spell_records as records

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_pylon_math.h"
HARNESS = MODULE / "tests/pylons/harness.cpp"
SHEET = MODULE / "data/pylon_buffs.csv"
TUNABLES = MODULE / "data/tunables/combat.csv"
D3 = MODULE / "data/d3/pylons.csv"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0053_pylon_buff_shells.sql"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch/pylons"

KINDS = ["power", "conduit", "channeling", "shield", "speed",
         "blessed", "empowered", "enlightened", "fleeting", "fortune", "frenzied"]
BIT = {kind: 1 << i for i, kind in enumerate(KINDS)}
# Each kind: its data/d3/pylons.csv row, and each number row with where D3's number is in that row's effect text (the
# n-th 'N%'), or a literal for what the text says in words. 'seconds' is the row's duration_seconds.
D3_ROWS = {
    "power": ("Power Pylon", {"damage_pct": 0}),
    "conduit": ("Conduit Pylon", {}),
    "channeling": ("Channeling Pylon", {"cooldown_reduction_pct": 0, "cost_reduction_pct": ("reduced to zero", 100)}),
    "shield": ("Shielding Pylon", {}),
    "speed": ("Speed Pylon", {"movement_pct": 0, "attack_speed_pct": 1}),
    "blessed": ("Blessed Shrine", {"damage_taken_pct": 0}),
    "empowered": ("Empowered Shrine", {"regeneration_pct": 0, "cooldown_reduction_pct": 1}),
    "enlightened": ("Enlightened Shrine", {"xp_pct": 0}),
    "fleeting": ("Fleeting Shrine", {"movement_pct": 0, "pickup_radius_yards": ("pickup radius by 20 yards", 20)}),
    "fortune": ("Fortune Shrine", {"magic_find_pct": 0, "gold_find_pct": 0}),
    "frenzied": ("Frenzied Shrine", {"attack_speed_pct": 0}),
}
# The harness prints: modifiers flag, then these stats in this order.
STATS = ["attack_speed", "cdr", "rcr", "specific", "movement", "magic_find", "gold_find"]
# What each kind puts on the sheet, by the row that carries it.
ON_SHEET = {
    "channeling": {"cdr": "cooldown_reduction_pct", "rcr": "cost_reduction_pct"},
    "speed": {"movement": "movement_pct", "attack_speed": "attack_speed_pct"},
    "blessed": {"specific": "damage_taken_pct"},
    "empowered": {"cdr": "cooldown_reduction_pct"},
    "fleeting": {"movement": "movement_pct"},
    "fortune": {"magic_find": "magic_find_pct", "gold_find": "gold_find_pct"},
    "frenzied": {"attack_speed": "attack_speed_pct"},
}


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def row_name(kind, what):
    return ("pylon_" if KINDS.index(kind) < 5 else "shrine_") + kind + "_" + what


def tunables():
    """{row name: the number the server reads}: the designer's value when set, D3's otherwise (generate_tunables.py)."""
    return {r["name"]: float(r["value"] or r["d3_value"]) for r in read(TUNABLES)
            if r["name"].startswith(("pylon_", "shrine_")) and (r["value"] or r["d3_value"])}


def d3_number(kind, what):
    name, numbers = D3_ROWS[kind]
    row = next(r for r in read(D3) if r["name"] == name)
    if what == "seconds":
        return float(row["duration_seconds"])
    where = numbers[what]
    if isinstance(where, tuple):
        assert where[0] in row["effect_text"], (kind, what)
        return float(where[1])
    return float(re.findall(r"(\d+(?:\.\d+)?)%", row["effect_text"])[where])


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = read(SHEET)
        cls.rows = tunables()
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"),
                                              every_class=True)

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def test_the_sheet_is_the_eleven_kinds_in_order(self):
        self.assertEqual(KINDS, [r["kind"] for r in self.sheet])
        self.assertEqual(list(range(83500, 83511)), [int(r["spell_id"]) for r in self.sheet])
        self.assertEqual(["pylon"] * 5 + ["shrine"] * 6, [r["group"] for r in self.sheet])
        header = (SRC / "combat/dc_pylon_math.h").read_text(encoding="utf-8")
        names = re.search(r"Names\[KindCount\] = \{(.*?)\};", header, re.S).group(1)
        self.assertEqual(KINDS, re.findall(r'"(\w+)"', names), "the C++ kinds are the sheet's, in its order")

    def test_every_row_seeds_from_d3_and_alex_has_set_none(self):
        expected = {}
        for kind, (_name, numbers) in D3_ROWS.items():
            expected[row_name(kind, "seconds")] = d3_number(kind, "seconds")
            for what in numbers:
                expected[row_name(kind, what)] = d3_number(kind, what)
        # The objects' rows (P3, diablocraft-7h5tr: looks, the shrine radius, the list budget) are test_pylon_objects.py's;
        # Conduit's strikes and Speed's knock-up (P2, diablocraft-eok78) are test_pylon_conduit_speed.py's.
        p2 = ("pylon_conduit_", "pylon_speed_knockup_")
        by_name = {r["name"]: r for r in read(TUNABLES) if r["name"].startswith(("pylon_", "shrine_"))
                   and not r["name"].endswith("_display_id") and r["name"] != "shrine_share_radius_yards"
                   and not r["name"].startswith("pylon_list_")
                   and not (r["name"].startswith(p2) and r["name"] != "pylon_conduit_seconds")}
        self.assertEqual(sorted(expected), sorted(by_name), "one row per number of 6.3, and no other")
        for name, number in expected.items():
            self.assertEqual(number, float(by_name[name]["d3_value"]), name)
            self.assertEqual("", by_name[name]["value"], "%s: the value column is the designer's" % name)

    def test_each_record_is_the_buff_its_row_names(self):
        infinite = self.field(83411, "DurationIndex")  # a legendary gem buff: the module sets the seconds
        for r in self.sheet:
            spell, kind = int(r["spell_id"]), r["kind"]
            self.assertEqual(r["name"], records.unquote(self.field(spell, "Name_Lang_enUS")))
            text = records.unquote(self.field(spell, "AuraDescription_Lang_enUS"))
            self.assertEqual(r["text"], text)
            self.assertEqual(infinite, self.field(spell, "DurationIndex"), spell)
            self.assertEqual("0", self.field(spell, "ProcTypeMask"), spell)
            self.assertFalse(int(self.field(spell, "Attributes")) & 0x40, "%d: not passive, so death can take it" % spell)
            self.assertFalse(int(self.field(spell, "Attributes")) & 0x04000000, "%d: a buff, not a debuff" % spell)
            # $sN is the row the column names, as the server reads it
            for slot, column in ((1, "amount_1"), (2, "amount_2")):
                if "$s%d" % slot not in text:
                    continue
                stated = int(self.field(spell, "EffectBasePoints_%d" % slot)) + int(self.field(spell, "EffectDieSides_%d" % slot))
                self.assertEqual(self.rows[r[column]], stated, "%s $s%d" % (kind, slot))
            self.assertNotRegex(text, r"(?i)per stack")
            self.assertEqual("", self.field(spell, "CumulativeAura").strip("0"), spell)

    def test_only_a_pylon_survives_death(self):
        for r in self.sheet:
            ex3 = int(self.field(int(r["spell_id"]), "AttributesEx3"))
            self.assertEqual(r["group"] == "pylon", bool(ex3 & 0x00100000), r["kind"])  # SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD

    def test_shield_is_the_stock_immunities_and_a_friendly_heal_still_lands(self):
        spell = 83503
        self.assertEqual(("6", "39", "127"), tuple(self.field(spell, c) for c in ("Effect_1", "EffectAura_1", "EffectMiscValue_1")),
                         "SPELL_AURA_SCHOOL_IMMUNITY over every school")
        self.assertEqual(("6", "147", "96"), tuple(self.field(spell, c) for c in ("Effect_2", "EffectAura_2", "EffectMiscValue_2")),
                         "SPELL_AURA_MECHANIC_IMMUNITY_MASK, the all-controls set Ignore Pain carries")
        self.assertGreater(int(self.field(spell, "EffectBasePoints_2")) + int(self.field(spell, "EffectDieSides_2")), 0)
        ex1 = int(self.field(spell, "AttributesEx"))
        self.assertTrue(ex1 & 0x8000, "SPELL_ATTR1_IMMUNITY_PURGES_EFFECT: taking it frees a held player")
        self.assertFalse(ex1 & 0x00010000, "SPELL_ATTR1_IMMUNITY_TO_HOSTILE_AND_FRIENDLY_EFFECTS would stop heals")
        # The three holds the elites throw are stock auras with these mechanics; the all-controls set holds each.
        defines = cost.at_pin("src/server/shared/SharedDefines.h")
        controls = defines[defines.index("IMMUNE_TO_MOVEMENT_IMPAIRMENT_AND_LOSS_CONTROL_MASK ="):]
        controls = controls[:controls.index(";")]
        for mechanic in ("MECHANIC_FEAR", "MECHANIC_STUN", "MECHANIC_ROOT"):
            self.assertIn(mechanic, controls)

    def test_empowered_regenerates_energy_and_mana_from_its_row(self):
        spell = 83506
        want = self.rows["shrine_empowered_regeneration_pct"]
        for slot, power in ((1, "3"), (3, "0")):
            self.assertEqual(("110", power), (self.field(spell, "EffectAura_%d" % slot), self.field(spell, "EffectMiscValue_%d" % slot)))
            self.assertEqual(want, int(self.field(spell, "EffectBasePoints_%d" % slot)) + int(self.field(spell, "EffectDieSides_%d" % slot)))

    def test_the_header_manifest_migration_and_client_carry_them(self):
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        listed = re.findall(r'\{(835\d\d), "(\w+)", (true|false)\}', header)
        self.assertEqual([(r["spell_id"], r["kind"], "true" if r["group"] == "pylon" else "false") for r in self.sheet], listed)
        table = re.findall(r"\d+", re.search(r"ShellIds\[\] = \{(.*?)\};", header, re.S).group(1))
        manifest = {int(r["spell_id"]): r for r in read(MODULE / "data/generated/spell_shells.csv")}
        sql = MIGRATION.read_text(encoding="utf-8")
        for r in self.sheet:
            self.assertIn(r["spell_id"], table)
            self.assertEqual("pylon_buff", manifest[int(r["spell_id"])]["kind"])
            self.assertRegex(sql, r"(?m)^\(%s," % r["spell_id"])
            self.assertIn("(%s,'dc_pylon_buff')" % r["spell_id"], sql)
        self.assertIn("BETWEEN 81000 AND 83510", sql)
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if dbc.is_file():
            ids = set(records.dbc_ids(dbc))
            for r in self.sheet:
                self.assertIn(int(r["spell_id"]), ids)


def build(header_text, name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="pylons-%s-" % name, dir=str(SCRATCH)))   # the cases file only; the binary is the cache's
    # The harness includes the module's headers by relative path, so the module's headers are staged with it; a mutant replaces only
    # dc_pylon_math.h, and the same text is the same staged tree and the same binary (the green run repeats once per mutant).
    files = {"src/" + path.relative_to(SRC).as_posix(): path.read_bytes() for path in SRC.rglob("*") if path.is_file() and path.suffix != ".cpp"}
    files["src/common/dc_common.cpp"] = (SRC / "common/dc_common.cpp").read_bytes()
    files["src/combat/dc_pylon_math.h"] = header_text
    files["tests/pylons/harness.cpp"] = HARNESS.read_bytes()
    tree = harness_env.stage_files(files)
    try:
        binary = harness_env.build([tree / "tests/pylons/harness.cpp", tree / "src/common/dc_common.cpp"], flags=["-std=c++17", "-O1"])
    except harness_env.BuildError as error:
        shutil.rmtree(work, ignore_errors=True)
        raise AssertionError("harness did not compile:\n" + error.stderr[-3000:])
    return work, binary


def drive(lines, header_text=None, name="real", rows=None):
    """One answer line per wear/power/xp line; None when the harness fails (a mutant may make it throw)."""
    work, binary = build(header_text or MATH.read_text(encoding="utf-8"), name)
    try:
        preamble = ["row %s %r" % (k, v) for k, v in sorted((rows or tunables()).items())]
        (work / "cases.txt").write_text("\n".join(preamble + lines) + "\n")
        done = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if done.returncode:
        return None
    return done.stdout.splitlines()


def sheet_line(line):
    cells = line.split()
    return int(cells[0]), dict(zip(STATS, (float(c) for c in cells[1:])))


def reduction(*pcts):
    product = 1.0
    for pct in pcts:
        product *= 1 - pct / 100
    return (1 - product) * 100


class Sheet(unittest.TestCase):
    """The rows reach the real sheet while a kind is in force and leave it when it ends."""

    def expected(self, kind):
        rows = tunables()
        want = dict.fromkeys(STATS, 0.0)
        for stat, what in ON_SHEET.get(kind, {}).items():
            want[stat] = rows[row_name(kind, what)]
        return want

    def test_each_kind_reaches_its_stats_and_leaves_with_the_buff(self):
        lines = ["wear 0 1"]
        for kind in KINDS:
            lines += ["wear %d 1" % BIT[kind], "wear 0 1"]
        out = drive(lines)
        self.assertIsNotNone(out)
        zero = dict.fromkeys(STATS, 0.0)
        self.assertEqual((1, zero), sheet_line(out[0]), "the first settle after login touches every kind")
        for i, kind in enumerate(KINDS):
            on_flag, on = sheet_line(out[1 + 2 * i])
            off_flag, off = sheet_line(out[2 + 2 * i])
            for stat in STATS:
                self.assertAlmostEqual(self.expected(kind)[stat], on[stat], places=6, msg="%s %s" % (kind, stat))
            self.assertEqual(zero, off, "%s leaves the sheet when it ends" % kind)
            touches = kind in ("channeling", "empowered")
            self.assertEqual((touches, touches), (bool(on_flag), bool(off_flag)),
                             "%s: the cost and cooldown auras are rebuilt exactly when a reduction moves" % kind)

    def test_kinds_run_together_and_reductions_multiply(self):
        rows = tunables()
        out = drive(["wear %d 1" % (BIT["channeling"] | BIT["empowered"] | BIT["speed"] | BIT["fleeting"] | BIT["frenzied"]),
                     "wear %d 1" % (BIT["empowered"] | BIT["fleeting"])])
        _, both = sheet_line(out[0])
        self.assertAlmostEqual(reduction(rows["pylon_channeling_cooldown_reduction_pct"],
                                         rows["shrine_empowered_cooldown_reduction_pct"]), both["cdr"], places=6)
        self.assertAlmostEqual(rows["pylon_speed_movement_pct"] + rows["shrine_fleeting_movement_pct"], both["movement"], places=6,
                               msg="temporary speed is not capped (the sheet's cap is 25)")
        self.assertAlmostEqual(rows["pylon_speed_attack_speed_pct"] + rows["shrine_frenzied_attack_speed_pct"], both["attack_speed"], places=6)
        _, left = sheet_line(out[1])
        self.assertAlmostEqual(rows["shrine_empowered_cooldown_reduction_pct"], left["cdr"], places=6)
        self.assertAlmostEqual(rows["shrine_fleeting_movement_pct"], left["movement"], places=6)
        self.assertEqual(0.0, left["rcr"])
        self.assertEqual(0.0, left["attack_speed"])

    def test_nothing_works_while_dead_and_a_pylon_works_again_after(self):
        rows = tunables()
        # a pylon's record stays on a dead player (the death flag); it does nothing until the player lives
        out = drive(["wear %d 1" % BIT["speed"], "wear %d 0" % BIT["speed"], "wear %d 1" % BIT["speed"],
                     "power 1 1", "power 1 0", "power 0 1"])
        self.assertEqual(rows["pylon_speed_movement_pct"], sheet_line(out[0])[1]["movement"])
        self.assertEqual(0.0, sheet_line(out[1])[1]["movement"])
        self.assertEqual(rows["pylon_speed_movement_pct"], sheet_line(out[2])[1]["movement"])
        self.assertAlmostEqual(1 + rows["pylon_power_damage_pct"] / 100, float(out[3]), places=6)
        self.assertAlmostEqual(5.0, float(out[3]), places=6, msg="D3: x5")
        self.assertEqual([1.0, 1.0], [float(out[4]), float(out[5])])

    def test_a_saved_sheet_keeps_nothing_after_login(self):
        rows = tunables()
        # the sheet was saved with Fortune on; after the login the player no longer wears it
        out = drive(["wear %d 1" % BIT["fortune"], "login", "wear 0 1"])
        self.assertEqual(rows["shrine_fortune_magic_find_pct"], sheet_line(out[0])[1]["magic_find"])
        self.assertEqual(dict.fromkeys(STATS, 0.0), sheet_line(out[1])[1])

    def test_enlightened_multiplies_the_finished_award(self):
        rows = tunables()
        out = drive(["xp 1000 50 10 1 1", "xp 1000 50 10 0 1", "xp 1000 50 10 1 0", "xp 0 50 10 1 1"])
        paid = 1000 * 1.5 + 10
        self.assertEqual([int(paid * (1 + rows["shrine_enlightened_xp_pct"] / 100)), int(paid), int(paid), int(10 * 1.25)],
                         [int(x) for x in out])

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "dead_still_counts": ("return alive && wearing;", "return wearing;"),
            "login_settles_nothing": ("known ? (now ^ before) : ((1u << KindCount) - 1)", "(now ^ before)"),
            "an_ended_kind_stays": ("                    remove(row.stat, id);", "                    ;"),
            "modifiers_never_rebuilt": ("modifiers = modifiers || TouchesModifiers(kind);", ";"),
            "speed_is_a_shrine": ("<= static_cast<unsigned>(Kind::Speed)", "< static_cast<unsigned>(Kind::Speed)"),
            "power_while_dead": ("        if (active)\n            AddFactor", "        if (true)\n            AddFactor"),
            "frenzied_gives_nothing": ('{Kind::Frenzied, Stat::AttackSpeed, Bucket::Flat, "attack_speed_pct"},', ""),
        }
        lines = ["wear 0 1"]
        for kind in KINDS:
            lines += ["wear %d 1" % BIT[kind], "wear %d 0" % BIT[kind], "wear 0 1"]
        lines += ["wear %d 1" % BIT["fortune"], "login", "wear 0 1", "power 1 1", "power 1 0"]
        want = drive(lines)
        self.assertIsNotNone(want)
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            self.assertNotEqual(want, drive(lines, real.replace(old, new), name), "mutant %s passed" % name)


class ChannelingIsFree(unittest.TestCase):
    """The sheet's Resource Cost Reduction with Channeling in force, through the core's spell-modifier arithmetic."""

    def test_whirlwinds_tick_costs_nothing_under_channeling(self):
        _, sheet = sheet_line(drive(["wear %d 1" % BIT["channeling"]])[0])
        runner = cost.CostMathTests("test_a_full_reduction_is_free_and_none_is_the_whole_cost")
        runner.setUpClass()
        try:
            terms = runner.terms
            tick = ("tick", terms["channel_cost_speed_term_resource"], terms["channel_cost_flat_resource"], 1.0,
                    terms["channel_tick_frames_count"], terms["channel_frames_per_second_count"])
            charged, without = runner.drive([tick + (sheet["rcr"],), tick + (0,)])
        finally:
            runner.tearDownClass()
        self.assertEqual(0.0, charged, "a Whirlwind tick under Channeling is free")
        self.assertGreater(without, 0.0, "and the same tick without it is not")


class Core(unittest.TestCase):
    """What the plan leans on in the core pin (read with git show, never written)."""

    def test_the_death_flag_keeps_an_aura_at_death_and_nothing_else_does(self):
        info = cost.at_pin("src/server/game/Spells/SpellInfo.cpp")
        self.assertRegex(info, r"bool SpellInfo::IsDeathPersistent\(\) const\s*\{\s*return AttributesEx3 & SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD;")
        unit = cost.at_pin("src/server/game/Entities/Unit/Unit.cpp")
        body = unit[unit.index("void Unit::RemoveAllAurasOnDeath()"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("!aura->IsDeathPersistent()", body)

    def test_a_friendly_heal_passes_school_immunity(self):
        unit = cost.at_pin("src/server/game/Entities/Unit/Unit.cpp")
        body = unit[unit.index("bool Unit::IgnoresSchoolImmunityFromFriendlyCaster("):]
        body = body[:body.index("\n}\n")]
        self.assertIn("caster->IsFriendlyTo(this)", body)
        self.assertIn("!immunitySpellInfo->HasAttribute(SPELL_ATTR1_IMMUNITY_TO_HOSTILE_AND_FRIENDLY_EFFECTS)", body)


class Source(unittest.TestCase):
    """The module calls each piece where the plan puts it."""

    @staticmethod
    def text(path):
        return (SRC / path).read_text(encoding="utf-8")

    def body(self, text, signature, end):
        start = text.index(signature)
        return text[start:text.index(end, start)]

    def test_power_is_a_factor_of_step_8_and_shield_stops_every_monster_hit(self):
        combat = self.text("combat/dc_combat.cpp")
        step8 = combat[combat.index("Abilities::Multipliers(player, hit.factors);"):]
        self.assertTrue(step8.startswith("Abilities::Multipliers(player, hit.factors);\n        Pylons::Multipliers(player, hit.factors);"))
        hit = self.body(combat, "void DealMonsterHit(", "SpellInfo const* info")
        self.assertIn("if (Pylons::Shielded(victim))\n            return;", hit)
        self.assertIn("Pylons::RegisterScripts();", combat)

    def test_shield_stops_the_knockback_and_the_vortex_and_the_holds_meet_the_immunity(self):
        elites = affixes_text()
        vortex = elites[elites.index("float const travel = elite->GetDistance(victim) - elite->GetMeleeRange(victim);"):]
        self.assertLess(vortex.index("if (DC::Combat::Pylons::Shielded(victim))\n        return;"),
                        vortex.index("if (travel > 0.0f && n.knockbackSpeedZ > 0.0f)"))
        self.assertIn('if (affix.behaviour == "knockback" && Roll() * 100.0 < chance)\n                KnockbackHit(', elites)
        knock = elites[elites.index("void KnockbackHit(Creature* elite, EliteState* state, Player* player"):]
        self.assertLess(knock.index("if (DC::Combat::Pylons::Shielded(player))\n        return;"),
                        knock.index("PackStateOf(elite, state)"))
        hold = self.body(elites, "bool ApplyHold(Unit* source, Player* player", "\n}\n")
        self.assertIn("source->AddAura(donor, player)", hold, "AddAura asks the core's immunity")

    def test_enlightened_wraps_every_own_kill_award(self):
        award = self.body(self.text("paragon/dc_paragon.cpp"), "XP SheetAward(Player* player", "\n}\n")
        self.assertIn("Combat::Pylons::ExperiencePct(player)", award)
        returns = re.findall(r"return ([^;]+);", award)
        self.assertEqual(["amount", "pct > 0.0 ? Enlightened(paid, Hundredths(pct)) : paid",
                          "enlightened(amount)", "enlightened(AwardXP(amount, percent, flat > 0.0 ? XP(flat) : XP(0)))"],
                         returns, "the early return is the not-a-kill one; both kill returns pay Enlightened")

    def test_the_module_settles_on_every_change_and_channeling_resets(self):
        pylons = self.text("combat/dc_pylons.cpp")
        self.assertIn("Active(player->IsAlive(), player->HasAura(record))", pylons)
        self.assertIn("PowerFactor(Wearing(player, Kind::Power), Tune(Row(Kind::Power, \"damage_pct\")), out);", pylons)
        reconcile = self.body(pylons, "void Reconcile(Player* player)", "\n    }\n")
        self.assertIn("Settle(", reconcile)
        self.assertIn("Passives::RefreshModifiers(player);", reconcile)
        give = self.body(pylons, "bool Give(Player* target, Kind kind)", "\n    }\n")
        self.assertIn("if (kind == Kind::Channeling)\n            target->RemoveAllSpellCooldown();", give)
        self.assertIn("target->RemoveAurasDueToSpell(record);", give, "the same kind again restarts its time")
        self.assertIn("if (!IsPylon(kind) && !target->IsAlive())\n            return false;", give, "no shrine to the dead")
        for hook in ("PLAYERHOOK_ON_UPDATE", "PLAYERHOOK_ON_PLAYER_JUST_DIED", "PLAYERHOOK_ON_PLAYER_RESURRECT"):
            self.assertIn(hook, pylons)
        self.assertIn('Tunables::Get("combat", row)', pylons)


if __name__ == "__main__":
    unittest.main()

"""diablocraft-eok78 (pylons and shrines P2, docs/proposals/pylons.md 6.9, 6.10 and 7): Conduit and Speed's knock-up.

  * src/combat/dc_pylon_math.h compiled into tests/pylon_p2/harness.cpp and driven with the tunable rows: a pulse
    never strikes more than the row's count, never a monster this wearer struck inside the rehit window; a Greater
    Rift strike is the rows' share of the monster's normal Life (past 2.1 billion too), with no gear input; in a
    Nephalem and a Greater Rift alike a Guardian or a boss takes the strike times its row; the knock-up throws a monster run into, never a rooted one or a Guardian, and none while
    the wearer stands; single-rule mutants fail the same driver;
  * the records in the generated spell SQL, combat_0056 and the header: Conduit's buff ticks at its row's period,
    the strike is Lightning, the knock-up aura is hidden, kept through death and ticks at its row, the throw is the
    stock knockback at the rows' speeds; both tick records carry dc_pylon_tick;
  * the core pin's own knockback spares bosses and the rooted (SpellEffects.cpp), which the throw relies on;
  * source guards that dc_pylons.cpp and dc_combat.cpp call each piece where the plan puts it (they prove the call is
    there, not that it runs; syntax_check.sh compiles the C++, and the in-game steps are docs/test-diablocraft-eok78.md).
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
import harness_env
import test_spell_records as records

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_pylon_math.h"
CPP = SRC / "combat/dc_pylons.cpp"
COMBAT = SRC / "combat/dc_combat.cpp"
HARNESS = MODULE / "tests/pylon_p2/harness.cpp"
TUNABLES = MODULE / "data/tunables/combat.csv"
SHEET = MODULE / "data/pylon_buffs.csv"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0056_pylon_conduit_speed_shells.sql"
GENERATED = MODULE / "data/generated/spell_shells.sql"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch/pylons"
CORE_EFFECTS = REPO / "azerothcore-wotlk/src/server/game/Spells/SpellEffects.cpp"
STRIKE, KNOCKUP, THROW = 83511, 83512, 83513


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def row(name):
    return next(r for r in read(TUNABLES) if r["name"] == name)


def tunable(name):
    r = row(name)
    return float(r["value"] or r["d3_value"])


def drive(lines, header_text=None, name="real"):
    """One answer line per input line; None when a mutant does not build or run."""
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="pylon-p2-%s-" % name, dir=str(SCRATCH)))
    try:
        tree = work / "mod"
        shutil.copytree(SRC, tree / "src", ignore=shutil.ignore_patterns("*.cpp"))
        (tree / "tests/pylon_p2").mkdir(parents=True)
        shutil.copy(HARNESS, tree / "tests/pylon_p2/harness.cpp")
        (tree / "src/combat/dc_pylon_math.h").write_text(header_text or MATH.read_text(encoding="utf-8"), encoding="utf-8")
        binary = work / "harness"
        built = subprocess.run([compiler, "-std=c++17", "-O1", str(tree / "tests/pylon_p2/harness.cpp"), "-o",
                                str(binary)], capture_output=True, text=True)
        if built.returncode:
            if header_text is None:
                raise AssertionError("harness did not compile:\n" + built.stderr[-3000:])
            return None
        (work / "cases.txt").write_text("\n".join(lines) + "\n")
        done = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return None if done.returncode else done.stdout.splitlines()


def conduit_cases():
    """Pulses a second apart over the same eight monsters, then the Greater Rift strikes, then the knock-up table."""
    rehit, cap = tunable("pylon_conduit_rehit_seconds") * 1000, tunable("pylon_conduit_targets")
    monsters = " ".join(str(i) for i in range(1, 9))
    pulses = ["pulse %d %r %r %s" % (t, rehit, cap, monsters) for t in (0, 1000, 2000, 3000)]
    # the ms clock wraps (getMSTime): a monster struck just before the wrap is still inside the window after it
    pulses += ["pulse %d %r %r 20" % (4294967000, rehit, cap), "pulse %d %r %r 20" % (500, rehit, cap),
               "pulse %d %r %r 20" % ((4294967000 + int(rehit)) % 2**32, rehit, cap)]
    low, high = tunable("pylon_conduit_greater_life_min_pct"), tunable("pylon_conduit_greater_life_max_pct")
    greater = ["greater %r %r %r %r %r" % args for args in (
        (10e9, 1, low, high, 0),      # past 2.1 billion, the bottom of the share
        (10e9, 1, low, high, 1),      # the top
        (10e9, 2.5, low, high, 0),    # an elite's Life factor is taken out: the normal monster's Life
    )]
    # a skill hit of 1000 (Nephalem) or a share of 3000 (Greater), on a monster or a Guardian/boss, the row at 0.5
    strike = ["strike %d 1000 3000 %d 0.5" % (g, b) for g in (0, 1) for b in (0, 1)]
    knock = ["knock %d %d %d" % (m, g, r) for m in (0, 1) for g in (0, 1) for r in (0, 1)]
    return pulses + greater + strike + knock


def expected_conduit():
    cap = int(tunable("pylon_conduit_targets"))
    low, high = tunable("pylon_conduit_greater_life_min_pct"), tunable("pylon_conduit_greater_life_max_pct")
    first = list(range(1, cap + 1))
    rest = [i for i in range(1, 9) if i not in first][:cap]
    lines = [" ".join(map(str, first)),           # t=0: the first `cap` found
             " ".join(map(str, rest)),            # t=1000: those struck at 0 are inside the window
             " ".join(map(str, first)),           # t=2000: the window has passed for the first ones
             " ".join(map(str, rest)),            # t=3000: and for the rest
             "20", "", "20"]
    lines += ["%.6f" % v for v in (10e9 * low / 100, 10e9 * high / 100, 10e9 / 2.5 * low / 100)]
    lines += ["%.6f" % ((3000 if g else 1000) * (0.5 if b else 1)) for g in (0, 1) for b in (0, 1)]
    lines += [str(int(m and not g and not r)) for m in (0, 1) for g in (0, 1) for r in (0, 1)]
    return lines


class Rows(unittest.TestCase):
    """The numbers of 6.9 and 6.10: D3's where it published one, the plan's placeholder start otherwise."""

    def test_d3_numbers_and_starts(self):
        published = {"pylon_conduit_rehit_seconds": "2", "pylon_conduit_weapon_damage_pct": "4000",
                     "pylon_conduit_greater_life_min_pct": "40", "pylon_conduit_greater_life_max_pct": "50"}
        starts = {"pylon_conduit_pulse_ms": "1000", "pylon_conduit_targets": "5", "pylon_conduit_radius_yards": "50",
                  "pylon_conduit_boss_factor": "1", "pylon_speed_knockup_tick_ms": "1000",
                  "pylon_speed_knockup_reach_yards": "5", "pylon_speed_knockup_speed_xy": "16",
                  "pylon_speed_knockup_speed_z": "6"}
        for name, value in published.items():
            self.assertEqual((value, ""), (row(name)["d3_value"], row(name)["value"]), name)
        for name, value in starts.items():
            self.assertEqual(("", value), (row(name)["d3_value"], row(name)["value"]), name)
            self.assertIn("PLACEHOLDER", row(name)["notes"], name)
        # the knock-up's damage starts empty (6.9: none until the designer sets one)
        damage = row("pylon_speed_knockup_weapon_damage_pct")
        self.assertEqual(("", ""), (damage["d3_value"], damage["value"]))
        # the knock speeds are seeded at our skills' knock, as 6.9 says
        skills = {r["name"]: r for r in read(MODULE / "data/tunables/ability_tunables.csv")}
        self.assertEqual(skills["ability_knockback_speed_xy"]["value"], row("pylon_speed_knockup_speed_xy")["value"])
        self.assertEqual(skills["ability_knockback_speed_z"]["value"], row("pylon_speed_knockup_speed_z")["value"])

    def test_the_current_tunables_migration_carries_them(self):
        sql = (MODULE / "data/sql/db-world/updates/tunables_0011.sql").read_text(encoding="utf-8")
        for name in ("pylon_conduit_targets", "pylon_conduit_boss_factor", "pylon_speed_knockup_weapon_damage_pct"):
            self.assertIn("('combat', '%s'," % name, sql)


class Rules(unittest.TestCase):
    def test_conduit_pick_greater_strike_and_knock_up(self):
        self.assertEqual(expected_conduit(), drive(conduit_cases()))

    def test_the_mutants_fail_the_same_driver(self):
        text = MATH.read_text(encoding="utf-8")
        mutants = {
            "cap": ("double(picked.size()) < cap", "double(picked.size()) <= cap"),
            "window": (">= rehitMs ? last.erase", "> rehitMs + 1000 ? last.erase"),
            "no window": ("if (last.emplace(near[i], now).second)", "if (last.insert_or_assign(near[i], now).second || true)"),
            "elite": ("trueLife / eliteFactor", "trueLife"),
            "boss": ("(boss ? bossFactor : 1.0)", "bossFactor"),
            # the return's bug (fr6p7): the cut only in a Greater Rift
            "nephalem boss": ("(greater ? greaterShare : skillHit) * (boss ? bossFactor : 1.0)",
                              "(greater ? greaterShare * (boss ? bossFactor : 1.0) : skillHit)"),
            "share": ("roll * (maxPct - minPct)", "(maxPct - minPct)"),
            "guardian": ("moving && !guardian && !rooted", "moving && !rooted"),
            "rooted": ("moving && !guardian && !rooted", "moving && !guardian"),
            "standing": ("moving && !guardian && !rooted", "!guardian && !rooted"),
        }
        cases, expected = conduit_cases(), expected_conduit()
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, text.count(old), old)
                self.assertNotEqual(expected, drive(cases, text.replace(old, new), name))


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names, cls.spells = records.parse(GENERATED.read_text(encoding="utf-8"), every_class=True)
        cls.conduit = int(next(r for r in read(SHEET) if r["kind"] == "conduit")["spell_id"])
        cls.speed = next(r for r in read(SHEET) if r["kind"] == "speed")

    def field(self, spell, column):
        return int(self.spells[spell][self.names.index(column)])

    def test_conduits_buff_ticks_at_its_row(self):
        self.assertEqual(226, self.field(self.conduit, "EffectAura_1"))  # SPELL_AURA_PERIODIC_DUMMY
        self.assertEqual(tunable("pylon_conduit_pulse_ms"), self.field(self.conduit, "EffectAuraPeriod_1"))

    def test_the_strike_is_lightning(self):
        self.assertEqual(8, self.field(STRIKE, "SchoolMask"))
        self.assertEqual(0, self.field(STRIKE, "Effect_1"))

    def test_the_knock_up_aura_is_hidden_kept_through_death_and_ticks_at_its_row(self):
        self.assertEqual((6, 226, 1), (self.field(KNOCKUP, "Effect_1"), self.field(KNOCKUP, "EffectAura_1"),
                                       self.field(KNOCKUP, "ImplicitTargetA_1")))
        self.assertEqual(tunable("pylon_speed_knockup_tick_ms"), self.field(KNOCKUP, "EffectAuraPeriod_1"))
        self.assertTrue(self.field(KNOCKUP, "AttributesEx") & 0x10000000)   # SPELL_ATTR1_NO_AURA_ICON
        self.assertTrue(self.field(KNOCKUP, "AttributesEx3") & 0x00100000)  # SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD

    def test_the_throw_is_the_stock_knockback_at_the_rows_speeds(self):
        self.assertEqual((98, 6, 13), (self.field(THROW, "Effect_1"), self.field(THROW, "ImplicitTargetA_1"),
                                       self.field(THROW, "RangeIndex")))
        # EffectKnockBack: speedxy = MiscValue * 0.1, speedz = value * 0.1 (base + die)
        self.assertEqual(tunable("pylon_speed_knockup_speed_xy") * 10, self.field(THROW, "EffectMiscValue_1"))
        self.assertEqual(tunable("pylon_speed_knockup_speed_z") * 10,
                         self.field(THROW, "EffectBasePoints_1") + self.field(THROW, "EffectDieSides_1"))

    def test_speeds_text_states_the_knock_up_and_promises_no_damage(self):
        self.assertIn("knocking them up into the air", self.speed["text"])
        self.assertNotIn("damag", self.speed["text"].lower())

    def test_migration_header_and_script_names(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        # A later spell migration rerenders the whole range (combat_0057, diablocraft-pl8fc; combat_0058 changed Whirlwind's
        # visual, diablocraft-vz49.3), so the bytes move on; the three records 0056 brought are still the render's, field for
        # field (as test_combat_fixes_xecwl's 0055 pin keeps only what 0055 was about).
        names, carried = records.parse(sql, every_class=True)
        render_names, render = records.parse(GENERATED.read_text(encoding="utf-8"), every_class=True)
        self.assertEqual(names, render_names)
        self.assertEqual({i: carried[i] for i in (STRIKE, KNOCKUP, THROW)}, {i: render[i] for i in (STRIKE, KNOCKUP, THROW)})
        self.assertIn("BETWEEN 81000 AND 83513", sql)
        self.assertIn("(%d,'dc_pylon_tick'),(%d,'dc_pylon_tick');" % (self.conduit, KNOCKUP), sql)
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn("PylonConduitStrike = %d, PylonSpeedKnockup = %d, PylonSpeedThrow = %d;" % (STRIKE, KNOCKUP, THROW),
                      header)
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if dbc.is_file():
            self.assertTrue({STRIKE, KNOCKUP, THROW} <= set(records.dbc_ids(dbc)))


class Core(unittest.TestCase):
    def test_the_stock_knockback_spares_bosses_and_the_rooted(self):
        text = CORE_EFFECTS.read_text(encoding="utf-8")
        body = text[text.index("void Spell::EffectKnockBack"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("creatureTarget->isWorldBoss() || creatureTarget->IsDungeonBoss() || creatureTarget->IsImmuneToKnockback()", body)
        self.assertIn("if (unitTarget->HasUnitState(UNIT_STATE_ROOT))", body)
        self.assertIn("float speedxy = float(m_spellInfo->Effects[effIndex].MiscValue) * ratio;", body)
        self.assertIn("float speedz = float(damage) * ratio;", body)


class Wiring(unittest.TestCase):
    """Where dc_pylons.cpp and dc_combat.cpp call each piece."""

    @classmethod
    def setUpClass(cls):
        cls.cpp = CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])

    def section(self, start, end):
        return self.cpp[self.cpp.index(start):self.cpp.index(end)]

    def test_the_tick_does_nothing_while_dead(self):
        tick = self.section("class dc_pylon_tick", "class Update")
        self.assertRegex(tick, r"if \(!player \|\| !player->IsAlive\(\)\)\s+return;\s+if \(GetId\(\) == Shells::PylonSpeedKnockup\)")
        self.assertIn("OnEffectPeriodic += AuraEffectPeriodicFn(dc_pylon_tick::Tick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);", tick)
        self.assertIn("RegisterSpellScript(dc_pylon_tick);", self.cpp)

    def test_the_pulse_reads_its_rows_and_splits_by_rift_kind(self):
        pulse = self.section("void ConduitPulse", "void KnockUp")
        for name in ("pylon_conduit_radius_yards", "pylon_conduit_rehit_seconds", "pylon_conduit_targets",
                     "pylon_conduit_weapon_damage_pct", "pylon_conduit_greater_life_min_pct",
                     "pylon_conduit_greater_life_max_pct", "pylon_conduit_boss_factor"):
            self.assertIn('Tune("%s")' % name, pulse)
        boss = pulse[:pulse.index("if (greater)")]
        self.assertIn("DC::Rifts::IsGuardianEntry(creature->GetEntry())", boss)
        greater, nephalem = pulse[pulse.index("if (greater)"):].split("else if (!ComputeHit(")
        self.assertNotIn("ComputeHit", greater)  # whatever the gear
        self.assertIn("double(target->GetMaxHealth()), DC::Rifts::EliteLifeFactor(creature)", greater)
        # both kinds reach the one cut and the one hit: the Nephalem branch leaves only when ComputeHit fails
        self.assertRegex(nephalem, r"^player, target, Shells::PylonConduitStrike, hit,\s+"
                                   r"Tune\(\"pylon_conduit_weapon_damage_pct\"\)\)\)\s+continue;\s+"
                                   r"hit\.total = ConduitDamage\(greater, hit\.total, share, boss, "
                                   r"Tune\(\"pylon_conduit_boss_factor\"\)\);\s+"
                                   r"DealHit\(player, target, Shells::PylonConduitStrike, hit, greater\);")

    def test_the_knock_up_casts_the_stock_throw_on_what_it_may(self):
        knock = self.section("void KnockUp", "class dc_pylon_tick")
        self.assertIn("player->isMoving()", knock)
        self.assertIn('Tune("pylon_speed_knockup_reach_yards")', knock)
        self.assertIn("KnocksUp(moving, creature && DC::Rifts::IsGuardianEntry(creature->GetEntry()),", knock)
        self.assertIn("target->HasUnitState(UNIT_STATE_ROOT)", knock)
        self.assertIn("player->CastSpell(target, Shells::PylonSpeedThrow, true);", knock)
        self.assertIn('DC::Tunables::Has("combat", "pylon_speed_knockup_weapon_damage_pct")', knock)

    def test_speed_brings_and_takes_its_knock_up(self):
        give = self.cpp[self.cpp.index("bool Give(Player* target, Kind kind)"):]
        self.assertIn("if (kind == Kind::Speed)\n            if (Aura* knockUp = target->AddAura(Shells::PylonSpeedKnockup, target))", give)
        gone = self.section("void Gone(", "void Register() override")
        self.assertIn("if (GetId() == RecordOf(Kind::Speed))", gone)
        self.assertIn("owner->RemoveAurasDueToSpell(Shells::PylonSpeedKnockup);", gone)
        self.assertIn("AfterEffectRemove += AuraEffectApplyFn(dc_pylon_buff::Gone,", self.cpp)

    def test_combat_loads_the_strike_and_deals_a_fixed_hit_as_it_is(self):
        self.assertIn("sSpellMgr->GetSpellInfo(Shells::PylonConduitStrike)", self.combat)
        self.assertIn("fixed ? hit.total : VictimAdjustedTotal(player, target, hit)", self.combat)


if __name__ == "__main__":
    unittest.main()

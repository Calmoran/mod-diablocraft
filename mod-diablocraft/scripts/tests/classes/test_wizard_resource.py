"""diablocraft-wizard-resource (Wizard part B1): the stats sheet and Arcane Power.

What this proves, and how:

  * **The class-keyed base sheet.** generate_sql.py's dc_class_base_stats rows
    are read back against both classes' CSVs, the Barbarian-only render is the
    full render with the Wizard's section taken out (the Barbarian did not move
    when the Wizard arrived), and the applied dc_barbarian_base_stats
    migration is unchanged.
  * **The sheet arithmetic.** tests/wizard_resource/harness.cpp compiles the
    module's real dc_common.cpp: the Barbarian with its class rules passed in
    serialises byte-identical to the Barbarian on the old fallback at all 70
    levels, and the Wizard at 70 gets its own Life, Armor, class DR 0, Thorns
    on Intelligence and a resource maximum of 100.
  * **The records.** The regeneration aura, the channel records and the
    sourced frame and interval rows, read out of the generated SQL and value
    map; the regeneration amount is recomputed from wizard_resource.csv.
  * **The ground damage over time.** Blizzard, Meteor and their runes are the
    stock ground-DoT shape - a persistent area aura (effect 27) with a
    PERIODIC_DUMMY effect whose period is interval_seconds and whose life is
    dot_duration_seconds - so the stock tick count is the simulator's (24 for
    Blizzard, 32 for Unrelenting Storm, 3 for Meteor), every one is bound to
    the dc_wizard_ground AuraScript, Meteor Shower is not, and no module tick
    scheduler is left in dc_combat.cpp.
  * **The channel arithmetic.** The same harness compiles dc_cost_math.h, the
    functions dc_combat.cpp calls, and prints the cadence, cost, ramp and tick
    share at two attack speeds for the script to hold to the simulator's rules.
  * **B3's generator side** (diablocraft-wizard-b3). Every proc_coefficient
    row reaches the exact table. Ice Blades' freeze and chill stay exact
    values, so the blade keeps B2's DurationIndex (dropping the freeze from
    SIDE_EFFECT_DURATIONS fails this). Conflagrate's burn and Scorch's wall
    are scripted PERIODIC_DUMMY helpers with the simulator's periods.

What it does not prove: anything about the running server. Nobody logged in;
the regeneration rate a player sees, the channel stopping at 0 and the hits
landing are docs/test-wizard-resource.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_wizard_resource.py
"""

import csv
import io
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
GENERATED = MODULE / "data" / "generated"
UPDATES = MODULE / "data" / "sql" / "db-world" / "updates"
SCRATCH = REPO / "azerothcore-wotlk" / "build" / "_agent-scratch" / "wizard_resource"
sys.path.insert(0, str(MODULE / "scripts"))

import generate_sql  # noqa: E402
from class_names import sheet_stem  # noqa: E402

SPELL_ATTR0_PASSIVE = 0x40
SPELL_EFFECT_PERSISTENT_AREA_AURA = 27
SPELL_AURA_PERIODIC_DUMMY = 226
GROUNDS = ("Blizzard", "Meteor")
STOCK_DBC = REPO / "azerothcore-wotlk" / "build" / "server" / "data" / "dbc"
SPELL_ATTR1_IS_CHANNELED = 0x4
CHANNELS = ("Ray of Frost", "Arcane Torrent", "Disintegrate")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def spell_records(path=GENERATED / "spell_shells.sql"):
    text = path.read_text(encoding="utf-8")
    columns = [c.strip("` ") for c in re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\)", text).group(1).split(",")]
    records = {}
    for match in re.finditer(r"(?<=\n)\((8[1-3]\d{3},[^\n]*)\)[,;](?=\n)", text):
        row = next(csv.reader(io.StringIO(match.group(1)), quotechar="'", escapechar="\\", skipinitialspace=True))
        if len(row) == len(columns):
            records[int(row[0])] = dict(zip(columns, row))
    return records


def shells_by_name():
    # Archon form's abilities are named for themselves ("Slow Time",
    # "Teleport") and would shadow the skills of the same name, so they are
    # kept apart (diablocraft-wizard-mechanics).
    return {row["name"]: int(row["spell_id"]) for row in read(GENERATED / "spell_shells.csv")
            if row["kind"] != "archon"}


def archon_by_name():
    return {row["name"]: int(row["spell_id"]) for row in read(GENERATED / "spell_shells.csv")
            if row["kind"] == "archon"}


class ClassBaseStats(unittest.TestCase):
    def test_each_class_is_its_own_csv(self):
        rows = {name: (class_id, rules, levels)
                for class_id, name, rules, levels in generate_sql.class_base_rows()}
        self.assertEqual(sorted(rows), ["Barbarian", "Crusader", "Demon Hunter", "Monk", "Necromancer", "Shaman", "Witch Doctor", "Wizard"])
        for name, resource in (("Barbarian", "fury_max"), ("Wizard", "resource_max"), ("Monk", "resource_max"),
                               ("Crusader", "resource_max"), ("Necromancer", "resource_max"), ("Demon Hunter", "resource_max"),
                               ("Witch Doctor", "resource_max"), ("Shaman", "resource_max")):
            sheet = read(D3 / f"{sheet_stem(name)}_base_stats.csv")
            expected = [[int(row[c]) for c in generate_sql.CLASS_BASE_COLUMNS + (resource,)] for row in sheet]
            self.assertEqual(rows[name][2], expected, name)
            self.assertEqual(len(expected), 70)
        self.assertEqual(rows["Barbarian"][0], 1)
        self.assertEqual(rows["Wizard"][0], 2)
        self.assertEqual(rows["Monk"][0], 3)
        self.assertEqual(rows["Necromancer"][0], 5)
        # class_primary_stats.csv's transcriptions, the same cells the
        # Barbarian's numeric rules read.
        self.assertEqual([float(v) for v in rows["Barbarian"][1]], [30.0, 0.1])
        self.assertEqual([float(v) for v in rows["Wizard"][1]], [0.0, 0.1])
        self.assertEqual([float(v) for v in rows["Monk"][1]], [30.0, 0.1])
        self.assertEqual({row[-1] for row in rows["Wizard"][2]}, {100})
        self.assertEqual({row[-1] for row in rows["Monk"][2]}, {250})
        self.assertEqual([float(v) for v in rows["Necromancer"][1]], [0.0, 0.1])
        self.assertEqual({row[-1] for row in rows["Necromancer"][2]}, {200})
        # The Demon Hunter's sheet has two pools; the table's resource is Hatred's resource_max, not the second pool's discipline_max.
        self.assertEqual(rows["Demon Hunter"][0], 6)
        self.assertEqual([float(v) for v in rows["Demon Hunter"][1]], [0.0, 0.1])
        self.assertEqual({row[-1] for row in rows["Demon Hunter"][2]}, {125})
        self.assertEqual({int(r["discipline_max"]) for r in read(D3 / "demon_hunter_base_stats.csv")}, {30})
        # The Shaman's rows are the Wizard's base stats with Maelstrom's pool of 100 in resource_max.
        self.assertEqual(rows["Shaman"][0], 8)
        self.assertEqual([float(v) for v in rows["Shaman"][1]], [0.0, 0.1])
        self.assertEqual({row[-1] for row in rows["Shaman"][2]}, {100})

    def test_the_barbarian_did_not_move_when_the_wizard_arrived(self):
        alone, _ = generate_sql.render_class_base_stats(classes={"Barbarian"})
        both, _ = generate_sql.render_class_base_stats()
        wizard_start = both.index("-- Wizard\n")
        self.assertEqual(both[:wizard_start], alone)

    def test_the_migration_is_the_generated_file_and_the_old_table_is_untouched(self):
        sql, count = generate_sql.render_class_base_stats()
        self.assertEqual(count, 560)   # eight classes x 70 levels
        self.assertEqual((UPDATES / generate_sql.CLASS_BASE_MIGRATION).read_text(encoding="utf-8"), sql)
        self.assertEqual((GENERATED / "class_base_stats.sql").read_text(encoding="utf-8"), sql)
        applied = "mod-diablocraft/data/sql/db-world/updates/0001_dc_barbarian_base_stats.sql"
        head = subprocess.run(["git", "show", "HEAD:" + applied], cwd=REPO, capture_output=True).stdout
        self.assertEqual((REPO / applied).read_bytes(), head)

    def test_the_loader_reads_the_class_table_and_no_class_is_named(self):
        stats = (MODULE / "src" / "stats" / "dc_stats.cpp").read_text(encoding="utf-8")
        self.assertIn("FROM dc_class_base_stats b", stats)
        self.assertNotIn("FROM dc_barbarian_base_stats", stats)
        self.assertNotIn("SetMaxPower(POWER_RAGE", stats)
        # No class is named in the Rage reward gate: it reads the registry's Rage rows (the Barbarian's Fury, the Shaman's Maelstrom).
        self.assertEqual(len(re.findall(r"\bBarbarian\(", stats)), 0)
        self.assertEqual(len(re.findall(r"\bRageResource\(", stats)), 2)


class Harness(unittest.TestCase):
    """Builds and runs tests/wizard_resource/harness.cpp once per class."""

    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("no C++ compiler")
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = SCRATCH / "harness"
        subprocess.run([compiler, "-std=c++20", "-O1", "-o", str(binary),
                        str(MODULE / "tests" / "wizard_resource" / "harness.cpp"),
                        str(MODULE / "src" / "common" / "dc_common.cpp")], check=True)
        out = harness_env.run([str(binary), str(D3 / "barbarian_base_stats.csv"), str(D3 / "wizard_base_stats.csv")],
                             check=True, capture_output=True, text=True).stdout
        cls.values = dict(line.split(" ", 1) for line in out.splitlines())

    def number(self, key):
        return float(self.values[key])


class SheetArithmetic(Harness):
    def test_the_barbarian_is_byte_identical_at_every_level(self):
        self.assertEqual(self.values["barbarian_levels"], "70")
        self.assertEqual(self.values["barbarian_identical"], "70")

    def test_the_wizard_at_seventy_is_its_own_sheet(self):
        row = read(D3 / "wizard_base_stats.csv")[-1]
        self.assertEqual(self.number("wizard_levels"), 70)
        self.assertEqual(self.number("wizard_max_life"), float(row["total_life"]))
        self.assertEqual(self.number("wizard_armor"), float(row["base_armor"]))
        self.assertEqual(self.number("wizard_int"), float(row["int"]))
        self.assertAlmostEqual(self.number("wizard_all_res"), float(row["int"]) * 0.1, places=6)
        self.assertEqual(self.number("wizard_class_dr"), 0)
        self.assertEqual(self.number("wizard_resource_max"), 100)
        # stats.csv Thorns: Sheet_Thorns x (1 + Primary_Stat / 100).
        self.assertAlmostEqual(self.number("wizard_thorns"), 1000 * (1 + float(row["int"]) / 100), places=4)
        self.assertAlmostEqual(self.number("wizard_taken_physical"), self.number("wizard_expected_taken"), places=9)


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = spell_records()
        cls.ids = shells_by_name()

    def test_arcane_power_regenerates_as_native_energy(self):
        # diablocraft-resource-rollout-a item 4: Arcane Power lives in Energy,
        # whose native 10/s (Player::Regenerate) is the sheet's rate, so no
        # regeneration aura is written and 83319 is a retired identity.
        rate = [float(row["regen_per_second"]) for row in read(D3 / "wizard_resource.csv")
                if row["regen_per_second"]]
        self.assertEqual(rate, [10.0])
        self.assertNotIn("Wizard - resource regeneration", self.ids)
        self.assertNotIn(83319, self.records)
        header = (MODULE / "src" / "combat" / "dc_spell_shells.h").read_text(encoding="utf-8")
        # The regeneration aura's lookup only: RegenerationMaskFor (diablocraft-dupme) names the Rage class.
        header = header.split("inline uint32_t ResourceRegenerationFor(uint32_t classId)")[1].split("\n}\n")[0]
        self.assertNotIn("if (classId == 2)", header)
        self.assertNotIn("classId == 1", header)
        costed = [r for r in self.records.values() if int(r["ID"]) in range(83100, 83300) and r["ManaCost"] != "0"]
        self.assertTrue(costed)
        self.assertEqual({r["PowerType"] for r in costed}, {"3"})

    def test_the_three_channels_and_their_runes_are_channels_and_nothing_else_is(self):
        channels = {name: spell for name, spell in self.ids.items() if name.split(" - ")[0] in CHANNELS
                    and "token storage" not in name}
        self.assertEqual(len(channels), 18)
        # The never-expiring SpellDuration row, as generate_spells.py picks it.
        raw = (MODULE.parent / "azerothcore-wotlk/build/server/data/dbc/SpellDuration.dbc").read_bytes()
        count, size = struct.unpack_from("<I", raw, 4)[0], struct.unpack_from("<I", raw, 12)[0]
        infinite = str(min(struct.unpack_from("<I", raw, 20 + i * size)[0] for i in range(count)
                           if struct.unpack_from("<i", raw, 20 + i * size + 4)[0] == -1))
        for name, spell in channels.items():
            record = self.records[spell]
            with self.subTest(name=name):
                self.assertTrue(int(record["AttributesEx"]) & SPELL_ATTR1_IS_CHANNELED)
                self.assertEqual(record["DurationIndex"], infinite)
                self.assertEqual(record["ManaCost"], "0")
                self.assertNotEqual(record["ChannelInterruptFlags"], "0")
        # Archon form's Disintegration Wave is a channel of the same shape
        # (wizard_archon_values.csv) and the only other one.
        wave = archon_by_name()["Disintegration Wave"]
        others = [spell for spell, record in self.records.items()
                  if 83100 <= spell <= 83399 and spell not in channels.values()
                  and int(record["AttributesEx"]) & SPELL_ATTR1_IS_CHANNELED]
        self.assertEqual(others, [wave])
        self.assertEqual(self.records[wave]["DurationIndex"], infinite)
        self.assertEqual(self.records[wave]["ManaCost"], "0")
        self.assertNotEqual(self.records[wave]["ChannelInterruptFlags"], "0")

    def test_the_sourced_rows_reach_every_record_that_needs_them(self):
        value_map = read(GENERATED / "spell_value_map.csv")

        def value(spell, token):
            rows = [r for r in value_map if int(r["spell_id"]) == spell and r["token"] == token]
            return rows[0] if rows else None
        frames = {"Ray of Frost": 30, "Arcane Torrent": 20, "Disintegrate": 20,
                  "Arcane Torrent - Arcane Mines": 40, "Arcane Torrent - Death Blossom": 30}
        sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        for name, spell in self.ids.items():
            if name.split(" - ")[0] not in CHANNELS or "token storage" in name:
                continue
            with self.subTest(name=name):
                self.assertIsNotNone(value(spell, "channel_tick_frames_count"))
                self.assertIsNotNone(value(spell, "channel_frames_per_second_count"))
                expected = frames.get(name, frames[name.split(" - ")[0]])
                found = re.search(r"\(%d,'channel_tick_frames_count','',([0-9.]+)\)" % spell, sql)
                self.assertEqual(float(found.group(1)), expected)
        for skill, seconds in (("Blizzard", 0.25), ("Meteor", 1.0)):
            row = value(self.ids[skill], "interval_seconds")
            self.assertEqual(row["source"], "period")
            self.assertEqual(int(self.records[self.ids[skill]]["EffectAuraPeriod_1"]), int(seconds * 1000))


class Grounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = spell_records()
        cls.ids = shells_by_name()
        cls.value_map = read(GENERATED / "spell_value_map.csv")
        data = (STOCK_DBC / "SpellDuration.dbc").read_bytes()
        count, _, size = struct.unpack_from("<III", data, 4)
        cls.durations = {}
        for index in range(count):
            ident, milliseconds = struct.unpack_from("<ii", data, 20 + index * size)
            cls.durations[ident] = milliseconds
        # diablocraft-wizard-mechanics: a Meteor's ground is its own helper
        # record ("<Meteor record> - molten ground"), cast where the meteor
        # lands after delay_seconds, so the Meteor records themselves are no
        # longer grounds; Black Hole and Energy Twister - Wicked Wind are.
        cls.grounds = {name: spell for name, spell in cls.ids.items()
                       if (name.split(" - ")[0] in GROUNDS + ("Black Hole",) and "token storage" not in name
                           and not name.startswith("Meteor")) or name.endswith(" - molten ground")
                       or name == "Energy Twister - Wicked Wind"}
        cls.owner = {spell: cls.ids[name[:-len(" - molten ground")]] for name, spell in cls.ids.items()
                     if name.endswith(" - molten ground")}
        cls.bubbles = {name: spell for name, spell in cls.ids.items() if name.endswith(" - bubble")}

    def row(self, spell, token, qualifier=""):
        rows = [r for r in self.value_map if int(r["spell_id"]) == spell and r["token"] == token
                and r["qualifier"] == qualifier]
        self.assertEqual(len(rows), 1, (spell, token))
        return rows[0]

    def test_every_ground_is_a_stock_persistent_area_aura_over_its_sheet_life(self):
        # Blizzard and its five runes, Black Hole and its five, Wicked Wind,
        # and the six Meteor records' molten grounds.
        self.assertEqual(len(self.grounds), 19)
        ticks = {}
        for name, spell in self.grounds.items():
            record = self.records[spell]
            with self.subTest(name=name):
                self.assertEqual(int(record["Effect_1"]), SPELL_EFFECT_PERSISTENT_AREA_AURA)
                self.assertEqual(int(record["EffectAura_1"]), SPELL_AURA_PERIODIC_DUMMY)
                self.assertEqual(int(record["ImplicitTargetA_1"]), 87)  # TARGET_DEST_DEST, the cast point
                self.assertEqual(int(record["ImplicitTargetB_1"]), 0)   # enemies only
                period = int(record["EffectAuraPeriod_1"])
                milliseconds = self.durations[int(record["DurationIndex"])]
                ticks[name] = milliseconds // period
                if spell in self.owner:
                    # A helper carries its Meteor record's numbers, which
                    # stay on that record: the helper's period and life are
                    # the same sheet numbers (Meteor Shower's molten ones).
                    owner = self.records[self.owner[spell]]
                    self.assertEqual(period, int(owner["EffectAuraPeriod_1"]))
                    if name.startswith("Meteor - Meteor Shower"):
                        # dot_duration_seconds:molten, 2 s (wizard.js:692).
                        self.assertEqual(milliseconds, 2000)
                    else:
                        self.assertEqual(milliseconds, self.durations[int(owner["DurationIndex"])])
                    continue
                interval = self.row(spell, "interval_seconds")
                life = self.row(spell, "dot_duration_seconds")
                # Black Hole's 8 frames (0.1333 s) is no whole millisecond:
                # the number is exact and the period its nearest millisecond.
                self.assertEqual(interval["source"], "exact" if name.startswith("Black Hole") else "period")
                self.assertEqual(life["source"], "duration")
        # AuraEffect::GetTotalTicks: max duration / amplitude, no initial tick.
        # The simulator's: 360/15, 480/15, 180/60 frames (wizard.js:744-756, :678-694).
        self.assertEqual(ticks["Blizzard"], 24)
        self.assertEqual(ticks["Blizzard - Unrelenting Storm"], 32)
        self.assertEqual(ticks["Meteor - molten ground"], 3)
        # Black Hole: 120 frames at a tick every 8 (wizard.js:1190).
        self.assertEqual(int(self.records[self.ids["Black Hole"]]["EffectAuraPeriod_1"]), 133)
        self.assertEqual(ticks["Black Hole"], 15)
        # Meteor Shower's molten fire: 0.7 a meteor over 2 seconds
        # (wizard.js:681, :692), ticking on the base's second.
        self.assertEqual(ticks["Meteor - Meteor Shower - molten ground"], 2)
        for name in ("Blizzard - Frozen Solid",):
            self.assertEqual(ticks[name], ticks[name.split(" - ")[0]], name)
        self.assertEqual(ticks["Meteor - Comet - molten ground"], ticks["Meteor - molten ground"])

    def test_molten_impact_is_eighteen_yards_for_the_impact_and_the_ground(self):
        # d3planner simulator/wizard.js:680 and :724 (pinned 898918b): rune a
        # is range 18 for the molten ground and for the impact; the base is 12.
        data = (STOCK_DBC / "SpellRadius.dbc").read_bytes()
        count, _, size = struct.unpack_from("<III", data, 4)
        radii = dict(struct.unpack_from("<if", data, 20 + index * size) for index in range(count))
        sql = (UPDATES / "combat_0027_wizard_resource.sql").read_text(encoding="utf-8")
        header = (MODULE / "src" / "combat" / "dc_spell_shells.h").read_text(encoding="utf-8")
        for name, yards in (("Meteor - Molten Impact", 18.0), ("Meteor", 12.0)):
            spell = self.ids[name]
            with self.subTest(name=name):
                # The ground: the dynamic object's radius is the record's
                # (Spell::EffectPersistentAA, Effects[i].CalcRadius).
                self.assertEqual(radii[int(self.records[spell]["EffectRadiusIndex_1"])], yards)
                # The impact: GroundImpact's AreaList reads the shell's
                # targeting radius, which the header and dc_spell_targeting carry.
                found = re.search(r"dc_spell_targeting VALUES \(%d,'ground_area','NUMERIC',[0-9.]+,([0-9.]+)," % spell,
                                  sql)
                self.assertEqual(float(found.group(1)), yards)
                self.assertRegex(header, r"\{%d, \"%s\", \"%s\", %s\}" % (
                    spell, *(name.split(" - ") + [""])[:2], re.escape("%.1f" % yards)))

    def test_no_meteor_record_is_its_own_ground_and_the_bubbles_are_the_only_other_areas(self):
        # The fall is the module's (Wizard::Delayed): a Meteor record that
        # were still a ground would burn at the cast point from the cast,
        # before the meteor lands.
        for name, spell in self.ids.items():
            if name.split(" - ")[0] == "Meteor" and spell not in self.grounds.values() \
                    and "token storage" not in name:
                with self.subTest(name=name):
                    self.assertNotEqual(int(self.records[spell]["Effect_1"]), SPELL_EFFECT_PERSISTENT_AREA_AURA)
        others = [spell for spell, record in self.records.items()
                  if 83100 <= spell <= 83399 and spell not in self.grounds.values()
                  and int(record["Effect_1"]) == SPELL_EFFECT_PERSISTENT_AREA_AURA]
        self.assertEqual(sorted(others), sorted(self.bubbles.values()))

    def test_each_ground_is_bound_to_the_aura_script_and_no_scheduler_is_left(self):
        sql = (UPDATES / "combat_0028_wizard_mechanics.sql").read_text(encoding="utf-8")
        bound = {int(s) for s in re.findall(r"\((\d+),'dc_wizard_ground'\)", sql)}
        self.assertEqual(bound, set(self.grounds.values()))
        source = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src" / "combat" / "dc_combat_internal.h", *sorted((MODULE / "src" / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("RegisterSpellScript(dc_wizard_ground);", source)
        self.assertIn("AuraEffectPeriodicFn(dc_wizard_ground::Tick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY)", source)
        for gone in ("dc_wizard_grounds", "groundMutex", "StartGround", "GroundTick"):
            self.assertNotIn(gone, source)


class ChannelArithmetic(Harness):
    def test_cadence_follows_attack_speed_and_the_cost_does_not(self):
        # floor(30 / aps) frames of 60 (cast.js:491-495).
        self.assertAlmostEqual(self.number("rof_interval_1"), 0.5)
        self.assertAlmostEqual(self.number("rof_interval_1_5"), 20 / 60)
        # cost x (1 - RCR) x channeling / 60 (cast.js:136-147).
        self.assertAlmostEqual(self.number("rof_tick_cost"), 8)
        self.assertAlmostEqual(self.number("rof_tick_cost_rcr"), 5.6)
        self.assertAlmostEqual(self.number("dis_tick_cost"), 6)

    def test_the_ramp_steps_each_whole_second_and_stops_at_the_max(self):
        for seconds, pct in (("0", 430), ("0.99", 430), ("1", 835), ("1.99", 835), ("2", 1240), ("7.5", 1240)):
            self.assertAlmostEqual(self.number("rof_ramp_" + seconds), pct)

    def test_a_tick_carries_its_share(self):
        # Ray of Frost: x aps x floor(30 / aps) / 60 (wizard.js:174).
        self.assertAlmostEqual(self.number("rof_share_1"), 430 * 1.0 * 30 / 60)
        self.assertAlmostEqual(self.number("rof_share_1_5"), 430 * 1.5 * 20 / 60)
        # Arcane Torrent: x channeling / 60 whatever the speed (wizard.js:323-325).
        self.assertAlmostEqual(self.number("at_share_1_5"), 400 * 20 / 60)

    def test_whole_mana_carries_the_fraction_and_a_short_pool_stops(self):
        self.assertEqual(self.values["debits"], "56566")
        self.assertAlmostEqual(self.number("pool_after"), 72)
        self.assertEqual(self.values["short_pool_paid"], "0")
        self.assertEqual(self.values["exact_pool_paid"], "1")


class B3(unittest.TestCase):
    """diablocraft-wizard-b3: what the generator must carry for the C++."""

    @classmethod
    def setUpClass(cls):
        cls.records = spell_records()
        cls.ids = shells_by_name()
        cls.archon = archon_by_name()
        cls.value_map = read(GENERATED / "spell_value_map.csv")
        cls.sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")

    def exact(self, spell, token, qualifier=""):
        found = re.search(r"\(%d,'%s','%s',([0-9.eE+-]+)\)" % (spell, token, qualifier), self.sql)
        return float(found.group(1)) if found else None

    def test_every_proc_coefficient_reaches_the_exact_table(self):
        # The C++ reads proc_coefficient through Numbers::Get; a row the
        # generator dropped would read 0 and silently switch a proc off.
        seen = 0
        for sheet, ids in (("wizard_skill_values.csv", self.ids), ("wizard_archon_values.csv", self.archon)):
            for row in read(D3 / sheet):
                if row["token"] != "proc_coefficient":
                    continue
                name = row.get("skill") or row["ability"]
                rune = row.get("rune") or ""
                spell = ids[" - ".join(part for part in (name, rune) if part)]
                with self.subTest(spell=spell, qualifier=row["qualifier"]):
                    self.assertEqual(self.exact(spell, "proc_coefficient", row["qualifier"]), float(row["value"]))
                    seen += 1
        # 111 skill and rune rows (99 d3planner rows rewritten to the client data, 12 added by
        # diablocraft-proc-coefficients-wiring) plus the three qualified ones, and Archon's three.
        self.assertEqual(seen, 117)

    def test_ice_blades_side_effects_do_not_move_the_blade_duration(self):
        blade = self.ids["Spectral Blade - Ice Blades"]
        for token, value in (("freeze_duration_seconds", 1.0), ("chill_duration_seconds", 0.6)):
            with self.subTest(token=token):
                rows = [r for r in self.value_map if int(r["spell_id"]) == blade and r["token"] == token]
                self.assertEqual([r["source"] for r in rows], ["exact"])
                self.assertEqual(self.exact(blade, token), value)
        # B2's record (the applied, frozen combat_0028) had the blade's own.
        b2 = spell_records(UPDATES / "combat_0028_wizard_mechanics.sql")
        self.assertEqual(self.records[blade]["DurationIndex"], b2[blade]["DurationIndex"])

    def test_the_burn_and_the_wall_are_scripted_periodic_helpers(self):
        for name, owner, period, stacks in (("Magic Missile - Conflagrate - burn", "Magic Missile - Conflagrate", 250, "3"),
                                            ("Arcane Orb - Scorch - wall", "Arcane Orb - Scorch", 100, "0")):
            spell = self.ids[name]
            record = self.records[spell]
            with self.subTest(name=name):
                self.assertEqual(int(record["EffectAura_1"]), SPELL_AURA_PERIODIC_DUMMY)
                self.assertEqual(int(record["EffectAuraPeriod_1"]), period)
                self.assertEqual(record["CumulativeAura"], stacks)
                self.assertIn("(%d,'dc_wizard_buff')" % spell, self.sql)
                self.assertTrue(re.search(r"\{%d, [^}]*%d\}" % (spell, self.ids[owner]),
                                          (MODULE / "src" / "combat" / "dc_spell_shells.h").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main(verbosity=1)

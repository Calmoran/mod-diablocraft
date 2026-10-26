"""diablocraft-y75r (Legendary gems part 10b-3): group C, the spell-driven procs.

  * the eight gem ids the code names are the sheet's gems;
  * data/legendary_gem_spells.csv (the eight spell shells) against what the generator wrote: spell_shells.csv, the
    generated header's GemShells, the spell_dbc rows (effect, aura, target, period, school, no number in the record)
    and the spell_script_names rows of the two periodic effects;
  * the production math (src/combat/dc_gem_power_math.h: Resolve, the damage-over-time tick split, Moratorium's split
    and pool; src/combat/dc_proc_math.h: the chance on hit) is compiled and driven with the generated number rows.
    Every expected value comes from d3planner (value/delta/maxlevel and the numbers of its effect texts), never from
    the code under test;
  * mutants of the math fail the same driver;
  * source-text guards that the hooks call it, and that every tunable the code reads is a row of combat.csv (they
    prove the call is there, not that it runs; the C++ is compile-checked by syntax_check.sh and the in-game steps
    are in docs/test-legendary-gem-group-c.md).
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import barbarian_source  # noqa: E402
import harness_env
import test_legendary_gems as numbers
import test_spell_records as records

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_gem_power_math.h"
PROC = SRC / "combat/dc_proc_math.h"
HARNESS = MODULE / "tests/legendary_gem_group_c/harness.cpp"
SHELLS_CSV = MODULE / "data/legendary_gem_spells.csv"
SCRATCH = numbers.SCRATCH
RANKS = numbers.RANKS
SCHOOL = {"physical": 1, "holy": 2, "fire": 4, "lightning": 8, "cold": 16, "poison": 32, "arcane": 64}

IDS = {  # constant name in the header -> the gem the sheet names
    "Wreath": "Wreath of Lightning",
    "Toxin": "Gem of Efficacious Toxin",
    "Pain": "Pain Enhancer",
    "Mirinae": "Mirinae, Teardrop of the Starweaver",
    "Moratorium": "Moratorium",
    "Iceblink": "Iceblink",
    "Zei": "Zei's Stone of Vengeance",
    "Boyarsky": "Boyarsky's Chip",
}
# The eight gems with a shell, and what each shell does (data/legendary_gem_spells.csv `effect`).
EFFECTS = {
    "Wreath of Lightning": "pulse", "Gem of Efficacious Toxin": "dot", "Pain Enhancer": "dot",
    "Mirinae, Teardrop of the Starweaver": "hit", "Moratorium": "stagger", "Zei's Stone of Vengeance": "stun",
    "Boyarsky's Chip": "taunt", "Iceblink": "slow",
    # part 10b-4 (diablocraft-apkq): the three shells of the rank-25 bonuses
    "Bane of the Trapped": "slow", "Molten Wildebeest's Gizzard": "absorb", "Simplicity's Strength": "heal",
}


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def constant(const):
    return re.search(r'%s = "(Unique_Gem_\d+_x1)"' % const, MATH.read_text(encoding="utf-8")).group(1)


def rows():
    """gem_id -> the eleven columns of the generated INSERT (base, per_rank, base2, per2, max, r25a, r25b, f1..f3)."""
    sql = numbers.GENERATED.read_text(encoding="utf-8")
    out = {}
    for gem_id, cells in re.findall(r"^\('(Unique_Gem_\d+_x1)'," + ",".join([r"'(?:[^'\\]|''|\\.)*'"] * 3) + r",(.*)\)[,;]$", sql, re.M):
        out[gem_id] = [None if x == "NULL" else float(x) for x in cells.split(",")]
    return out


def row_line(gem_id, c):
    f = lambda v: "none" if v is None else repr(v)
    return "row %s %r %r %s %s %s %s %s %s %s %s" % (gem_id, c[0], c[1], f(c[4]), f(c[2]), f(c[3]),
                                                    f(c[7]), f(c[8]), f(c[9]), f(c[5]), f(c[6]))


def planner_texts():
    """gem name -> every effect's format string of d3planner, `%%` read as `%`."""
    text = numbers.PLANNER.read_text(encoding="utf-8")
    text = text[text.index("DiabloCalc.legendaryGems = {"):]
    out = {}
    for block in re.split(r"\n  \w+: \{\n    id:", text)[1:]:
        name = re.search(r'\n    name: "(.*?)"', block).group(1)
        out[name] = [f.replace("%%", "%") for f in re.findall(r'format: "(.*?)",', block)]
    return out


def build(header_text, proc_text, name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    files = {**{rel: (SRC / rel).read_text(encoding="utf-8") for rel in ("common/dc_legendary_gem.h", "items/dc_legendary_gem_item.h")}, "combat/dc_gem_power_math.h": header_text, "combat/dc_proc_math.h": proc_text}
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
    work = Path(tempfile.mkdtemp(prefix="gemgroupc-%s-" % name, dir=str(SCRATCH)))
    return work, binary


def run(lines, header_text=None, proc_text=None, name="real"):
    work, binary = build(header_text or MATH.read_text(encoding="utf-8"),
                         proc_text or PROC.read_text(encoding="utf-8"), name)
    try:
        (work / "cases.txt").write_text("\n".join(lines) + "\n")
        return harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def agrees(got, want):
    return len(got) == len(want) and all(
        abs(a - b) <= 1e-6 * max(1.0, abs(b)) for g, w in zip(got, want) for a, b in zip(g, w))


class Ids(unittest.TestCase):
    def test_every_named_gem_is_the_one_the_sheet_calls_that(self):
        sheet = {r["gem_id"]: r["gem_name"] for r in numbers.read(numbers.CSV) if r["gem_id"]}
        for const, name in IDS.items():
            self.assertEqual(name, sheet[constant(const)], const)

    def test_rank_25_is_the_tooltips_rank(self):
        self.assertRegex(MATH.read_text(encoding="utf-8"), r"Rank25 = 25;")


class Shells(unittest.TestCase):
    """The sheet of the eight spells against everything the generator made of it."""

    @classmethod
    def setUpClass(cls):
        cls.sheet = {r["gem_id"]: r["gem_name"] for r in numbers.read(numbers.CSV) if r["gem_id"]}
        cls.csv = read(SHELLS_CSV)
        cls.manifest = {int(r["spell_id"]): r for r in read(MODULE / "data/generated/spell_shells.csv")}
        names, spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)
        cls.names, cls.spells = names, spells

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def test_the_sheet_is_the_eleven_gems_with_one_shell_each(self):
        self.assertEqual(sorted(EFFECTS), sorted(self.sheet[r["gem_id"]] for r in self.csv))
        self.assertEqual(11, len({r["spell_id"] for r in self.csv}))
        for r in self.csv:
            self.assertEqual(EFFECTS[self.sheet[r["gem_id"]]], r["effect"], r["gem_id"])
            self.assertTrue(83400 <= int(r["spell_id"]) <= 83499, "outside the gem block")
            if r["effect"] in ("dot", "pulse"):
                self.assertTrue(int(r["period_ms"]) > 0, r["gem_id"])
            if r["effect"] == "stagger":
                self.assertEqual("", r["period_ms"], "Moratorium's cadence is combat.csv's, not a column here")

    def test_the_manifest_has_a_gem_row_per_shell_named_as_the_gem(self):
        gem_rows = {i: r for i, r in self.manifest.items() if r["kind"].startswith("gem_") and r["kind"] != "gem_buff"}
        self.assertEqual({int(r["spell_id"]) for r in self.csv}, set(gem_rows))
        for r in self.csv:
            row = gem_rows[int(r["spell_id"])]
            self.assertEqual(self.sheet[r["gem_id"]], row["name"])
            self.assertEqual("gem_" + r["effect"], row["kind"])
            self.assertEqual(r["element"], row["element"])
            self.assertEqual(r["base_spell"], row["base_spell"])

    def test_the_header_lists_the_same_shells(self):
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        listed = re.findall(r'\{(\d+), "(Unique_Gem_\d+_x1)", "(\w+)"\}', header)
        self.assertEqual([(r["spell_id"], r["gem_id"], r["effect"]) for r in self.csv], listed)
        table = re.search(r"ShellIds\[\] = \{(.*?)\};", header, re.S).group(1)
        for r in self.csv:
            self.assertIn(r["spell_id"], re.findall(r"\d+", table), "the own-shell guard must know %s" % r["spell_id"])

    def test_each_record_has_the_effect_its_sheet_row_names(self):
        for r in self.csv:
            spell = int(r["spell_id"])
            effect = r["effect"]
            self.assertEqual(self.sheet[r["gem_id"]], records.unquote(self.field(spell, "Name_Lang_enUS")))
            self.assertEqual(str(SCHOOL[r["element"]]), self.field(spell, "SchoolMask"))
            self.assertEqual("0", self.field(spell, "EffectBasePoints_1"), "%s: a number lives in the gem, not the record" % effect)
            self.assertEqual("0", self.field(spell, "EffectDieSides_1"))
            if effect in ("hit", "heal", "stagger"):
                self.assertEqual("3", self.field(spell, "Effect_1"))  # SPELL_EFFECT_DUMMY, as every shell's
                continue
            aura = {"pulse": "226", "dot": "226", "stun": "12", "taunt": "11", "slow": "33", "absorb": "69"}[effect]
            self.assertEqual("6", self.field(spell, "Effect_1"))      # SPELL_EFFECT_APPLY_AURA
            self.assertEqual(aura, self.field(spell, "EffectAura_1"))
            self.assertEqual("1" if effect in ("pulse", "absorb") else "6", self.field(spell, "ImplicitTargetA_1"))
            # the shield takes every school (SPELL_SCHOOL_MASK_ALL); no other aura has a misc value
            self.assertEqual("127" if effect == "absorb" else "0", self.field(spell, "EffectMiscValue_1"))
            self.assertEqual({"stun": "12", "slow": "11"}.get(effect, "0"), self.field(spell, "Mechanic"))
            self.assertEqual("0", self.field(spell, "ProcTypeMask"), "a donor's proc must not come with the shell")
            # The module applies it with the gem's own seconds: the record's duration is the stock infinite one
            # (the one the Wizard's own control helper, 83337, carries)
            self.assertEqual(self.field(83337, "DurationIndex"), self.field(spell, "DurationIndex"))
            debuff = bool(int(self.field(spell, "Attributes")) & 0x04000000)  # SPELL_ATTR0_AURA_IS_DEBUFF
            self.assertEqual(effect not in ("pulse", "absorb"), debuff, effect)
            for slot in (2, 3):
                self.assertEqual("0", self.field(spell, "Effect_%d" % slot))
        pay = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}["gem_moratorium_pay_period_ms"]
        for r in self.csv:
            period = pay["value"] if r["effect"] == "stagger" else r["period_ms"]
            if period:
                self.assertEqual(period, self.field(int(r["spell_id"]), "EffectAuraPeriod_1"))

    def test_only_the_two_periodic_shells_are_scripted(self):
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        found = re.search(r"INSERT INTO spell_script_names \(spell_id,ScriptName\) VALUES ((?:\(\d+,'dc_gem_tick'\),?)+);", sql)
        scripted = sorted(int(i) for i in re.findall(r"\((\d+),'dc_gem_tick'\)", found.group(1)))
        self.assertEqual(sorted(int(r["spell_id"]) for r in self.csv if r["effect"] in ("dot", "pulse")), scripted)
        self.assertIn("DELETE FROM spell_script_names WHERE ScriptName='dc_gem_tick';", sql)
        # the shared span ends at the highest id below the wings; class blocks above them are deleted block by block
        shared = max(i for i in self.manifest if i <= 83999)
        self.assertIn("DELETE FROM `spell_dbc` WHERE `ID` BETWEEN 81000 AND %d;" % shared, sql)

    def test_the_client_record_exists_for_every_shell(self):
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if not dbc.is_file():
            self.skipTest("client Spell.dbc is generated, not tracked")
        ids = records.dbc_ids(dbc)
        for r in self.csv:
            self.assertIn(int(r["spell_id"]), ids)

    def test_the_migration_carries_the_shells(self):
        migration = MODULE / "data/sql/db-world/updates/combat_0050_legendary_gem_shells.sql"
        sql = migration.read_text(encoding="utf-8")
        for r in self.csv:
            self.assertRegex(sql, r"(?m)^\(%s," % r["spell_id"], r["spell_id"])
        self.assertIn("BETWEEN 81000 AND 83410", sql)


class Math(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d3p = numbers.planner()
        cls.text = numbers.planner_fixed()
        cls.effects = planner_texts()

    def val(self, key, rank, slot=0):
        gem = self.d3p[IDS[key]]
        top = rank if gem[3] is None else min(rank, gem[3])
        return gem[1][slot] + gem[2][slot] * top

    def rank25(self, key):
        """The numbers of the second effect's text (Zei's stun, Boyarsky's taunt)."""
        return numbers.numbers(re.sub(r"%[-+0-9.]*[a-z]", "", self.effects[IDS[key]][1]))

    def cases(self):
        ids = {c: constant(c) for c in IDS}
        out = []
        for const, gem_id in ids.items():
            for rank in RANKS:
                out.append([(gem_id, rank)])
        out.append([(g, 40) for g in ids.values()])
        out.append([(g, 25) for g in ids.values()])
        out.append([(g, 24) for g in ids.values()])
        # Unique Equipped: two of a kind, the highest rank counts, whatever the order
        out.append([(ids["Mirinae"], 5), (ids["Mirinae"], 60), (ids["Zei"], 3)])
        out.append([(ids["Mirinae"], 60), (ids["Mirinae"], 5)])
        out.append([(ids["Zei"], 24), (ids["Zei"], 25)])
        # a gem that is not one of these eight adds nothing
        out.append([("Unique_Gem_016_x1", 50)])
        out.append([])
        return out

    def want(self, worn):
        ids = {constant(c): c for c in IDS}
        best = {}
        for gem_id, rank in worn:
            best[gem_id] = max(best.get(gem_id, 0), rank)
        w = {ids[g]: r for g, r in best.items() if g in ids}
        fx = lambda k, i: self.text[IDS[k]][i]
        z = lambda: 0.0
        mir = [self.val("Mirinae", w["Mirinae"]), fx("Mirinae", 0), fx("Mirinae", 1)] if "Mirinae" in w else [0, 0, 0]
        wre = [self.val("Wreath", w["Wreath"]), fx("Wreath", 0), fx("Wreath", 1)] if "Wreath" in w else [0, 0, 0]
        pain = [self.val("Pain", w["Pain"]), fx("Pain", 0)] if "Pain" in w else [0, 0]
        tox = [self.val("Toxin", w["Toxin"]), fx("Toxin", 0)] if "Toxin" in w else [0, 0]
        stag = [fx("Moratorium", 0), self.val("Moratorium", w["Moratorium"])] if "Moratorium" in w else [0, 0]
        stun = self.rank25("Zei") if "Zei" in w and w["Zei"] >= 25 else [0, 0]
        taunt = self.rank25("Boyarsky")[0] if "Boyarsky" in w and w["Boyarsky"] >= 25 else 0
        ice = self.val("Iceblink", w["Iceblink"]) if "Iceblink" in w else 0
        return mir + wre + pain + tox + stag + stun + [taunt, ice]

    def drive(self, header_text, name, proc_text=None):
        lines = [row_line(g, c) for g, c in rows().items()]
        cases = self.cases()
        for worn in cases:
            lines.append("case %d %s" % (len(worn), " ".join("%s %d" % w for w in worn)))
        done = run(lines, header_text, proc_text, name)
        self.assertEqual(0, done.returncode, done.stderr)
        got = [[float(x) for x in line.split()] for line in done.stdout.splitlines()]
        return got, [self.want(c) for c in cases]

    def test_every_power_at_every_rank_is_d3planners(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 120)
        self.assertTrue(agrees(got, want))
        by = lambda worn: got[next(n for n, c in enumerate(self.cases()) if c == worn)]
        # the sheets' own text at rank 0 and the rank gate
        mirinae = by([(constant("Mirinae"), 0)])
        self.assertEqual([3000.0, 15.0, 3.0], mirinae[:3])      # "15% chance ... 3000% ... heal ... 3%"
        self.assertEqual([2500.0, 3.0], by([(constant("Pain"), 0)])[6:8])    # "2500% ... over 3 seconds"
        self.assertEqual([2000.0, 10.0], by([(constant("Toxin"), 0)])[8:10])  # "2000% ... over 10 seconds"
        self.assertEqual([35.0, 3.0], by([(constant("Moratorium"), 0)])[10:12])
        self.assertEqual([0.0, 0.0], by([(constant("Zei"), 24)])[12:14])      # "(Requires Rank 25)"
        self.assertEqual([20.0, 1.0], by([(constant("Zei"), 25)])[12:14])
        self.assertEqual(0.0, by([(constant("Boyarsky"), 24)])[14])
        self.assertEqual(2.0, by([(constant("Boyarsky"), 25)])[14])
        self.assertEqual(25.0, by([(constant("Iceblink"), 50)])[15])          # caps at 25.0% at rank 50
        self.assertEqual(25.0, by([(constant("Iceblink"), 300)])[15])
        self.assertEqual(25.0 + 0, by([(constant("Iceblink"), 51)])[15])

    def test_a_gem_with_no_fixed_number_is_an_error_not_a_zero(self):
        for gem, columns in ((constant("Mirinae"), "none none none none none none none"),
                             (constant("Moratorium"), "none none none none none none none")):
            lines = ["row %s 3000 60 none %s" % (gem, columns), "case 1 %s 5" % gem]
            self.assertNotEqual(0, run(lines).returncode, gem)

    def test_a_rank_25_gem_with_no_rank_25_number_is_an_error_not_a_zero(self):
        gem = constant("Zei")
        lines = ["row %s 4 0.08 none 20 0.4 10 50 none none none" % gem, "case 1 %s 30" % gem]
        self.assertNotEqual(0, run(lines).returncode)
        self.assertEqual(0, run(lines[:1] + ["case 1 %s 24" % gem]).returncode)  # below rank 25 it is not asked

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "zei_stun_without_the_rank_gate": ("if (rank25)\n                {\n                    powers.zeiStunChancePct",
                                               "if (true)\n                {\n                    powers.zeiStunChancePct"),
            "zei_stun_numbers_swapped": ("powers.zeiStunChancePct = Rank25Number(*row, 0);\n                    powers.zeiStunSeconds = Rank25Number(*row, 1);",
                                         "powers.zeiStunChancePct = Rank25Number(*row, 1);\n                    powers.zeiStunSeconds = Rank25Number(*row, 0);"),
            "boyarsky_gate_is_26": ("if (rank25)\n                    powers.boyarskyTauntSeconds",
                                    "if (gem.rank >= Rank25 + 1)\n                    powers.boyarskyTauntSeconds"),
            "mirinae_chance_is_the_heal": ("powers.mirinaeChancePct = Fixed(*row, 0);\n                powers.mirinaeHealPct = Fixed(*row, 1);",
                                           "powers.mirinaeChancePct = Fixed(*row, 1);\n                powers.mirinaeHealPct = Fixed(*row, 0);"),
            "wreath_seconds_is_the_chance": ("powers.wreathChancePct = Fixed(*row, 0);\n                powers.wreathSeconds = Fixed(*row, 1);",
                                             "powers.wreathChancePct = Fixed(*row, 1);\n                powers.wreathSeconds = Fixed(*row, 0);"),
            "pain_seconds_is_scaled_value": ("powers.painSeconds = Fixed(*row, 0);", "powers.painSeconds = value;"),
            "toxin_pct_unscaled": ("powers.toxinPct = value;", "powers.toxinPct = row->base;"),
            "stagger_pct_is_the_scaled_number": ("powers.staggerPct = Fixed(*row, 0);\n                powers.staggerSeconds = value;",
                                                 "powers.staggerPct = value;\n                powers.staggerSeconds = Fixed(*row, 0);"),
            "iceblink_slow_unscaled": ("powers.iceblinkSlowPct = value;", "powers.iceblinkSlowPct = row->base;"),
            "iceblink_is_not_capped": ("powers.iceblinkSlowPct = value;", "powers.iceblinkSlowPct = row->base + row->perRank * gem.rank;"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            got, want = self.drive(real.replace(old, new), name)
            self.assertFalse(agrees(got, want), "mutant %s passed" % name)


class Ticks(unittest.TestCase):
    SCENES = [(2500.0, 3.0, 1000), (2000.0, 10.0, 1000), (1250.0, 3.0, 1000), (2500.0, 3.0, 500), (100.0, 0.4, 1000),
              (100.0, 3.0, 0), (3000.0, 10.0, 750), (700.0, 2.7, 1000)]

    @staticmethod
    def model(total, seconds, period):
        ticks = 1 if period <= 0 else max(1, round(seconds * 1000 / period))
        return [ticks, total / ticks]

    def drive(self, header_text, name):
        lines = ["ticks %r %r %d" % scene for scene in self.SCENES]
        done = run(lines, header_text, None, name)
        self.assertEqual(0, done.returncode, done.stderr)
        return [[float(x) for x in line.split()] for line in done.stdout.splitlines()], [self.model(*s) for s in self.SCENES]

    def test_a_damage_over_time_pays_its_total_over_its_seconds(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "ticks")
        self.assertTrue(agrees(got, want))
        self.assertEqual(3.0, got[0][0])
        self.assertAlmostEqual(2500.0 / 3, got[0][1], places=6)
        for scene, row in zip(self.SCENES, got):
            self.assertAlmostEqual(scene[0], row[0] * row[1], places=3)  # the ticks add back to the total

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "tick_is_the_whole_total": ("return totalPct / Ticks(seconds, periodMs);", "return totalPct;"),
            "ticks_round_down": ("std::llround(seconds * 1000.0 / periodMs)", "static_cast<long long>(seconds * 1000.0 / periodMs)"),
            "no_floor_of_one_tick": ("std::max<long long>(1, std::llround", "std::max<long long>(0, std::llround"),
            "period_in_seconds": ("seconds * 1000.0 / periodMs", "seconds / periodMs"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            got, want = self.drive(real.replace(old, new), name)
            self.assertFalse(agrees(got, want), "mutant %s passed" % name)


class Stagger(unittest.TestCase):
    """Moratorium: the share put off, and a pool that pays each debt evenly over its own seconds."""

    SPLITS = [(35.0, 1000.0), (35.0, 1.0), (0.0, 500.0), (100.0, 80.0), (35.0, 0.0)]
    # (debts as (amount, seconds, startMs), pay times in ms). The clock wraps at 2^32.
    POOLS = [
        ([(350.0, 3.0, 1000)], [1000, 1500, 2000, 2500, 4000, 4001, 9000]),
        ([(350.0, 3.0, 1000), (700.0, 3.5, 2000)], [1000, 2000, 2500, 4000, 5500, 6000]),
        ([(100.0, 0.0, 500)], [500, 501]),
        ([(90.0, 3.0, 4294966000)], [4294966000, 4294967000, 1000, 1704, 1705, 3000]),
        ([(60.0, 2.0, 0)], [0, 0, 0, 1999, 2000]),
    ]

    @staticmethod
    def model(debts, times):
        """Independent model on an unwrapped clock: each debt linear over its window, paid as time passes."""
        start0 = debts[0][2]
        paid = [0.0] * len(debts)
        out = []
        for t in times:
            t = t if t >= start0 else t + 2 ** 32
            due = 0.0
            for i, (amount, seconds, start) in enumerate(debts):
                if t - start >= seconds * 1000:
                    share = 1.0
                else:
                    share = max(0, t - start) / (seconds * 1000)
                owe = amount * share - paid[i]
                if owe > 0:
                    paid[i] += owe
                    due += owe
            out.append(due)
        out.append(sum(a - p for (a, _s, _st), p in zip(debts, paid)))
        return out

    def drive(self, header_text, name):
        lines, want = [], []
        for pct, damage in self.SPLITS:
            lines.append("split %r %r" % (pct, damage))
        for debts, times in self.POOLS:
            lines.append("pool %d %s %d %s" % (len(debts), " ".join("%r %r %d" % d for d in debts), len(times),
                                               " ".join(str(t) for t in times)))
        done = run(lines, header_text, None, name)
        self.assertEqual(0, done.returncode, done.stderr)
        got = [[float(x) for x in line.split()] for line in done.stdout.splitlines()]
        want = [[damage * (1 - pct / 100), damage * pct / 100] for pct, damage in self.SPLITS]
        want += [self.model(debts, times) for debts, times in self.POOLS]
        return got, want

    def test_the_split_and_the_pool_are_the_independent_model(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "stagger")
        self.assertTrue(agrees(got, want), (got, want))
        # 35% of 1000 is put off and 650 dealt now; a debt is never paid more than once (it adds back to 350)
        self.assertEqual([650.0, 350.0], got[0])
        self.assertAlmostEqual(350.0, sum(got[len(self.SPLITS)][:-1]), places=6)
        self.assertEqual(0.0, got[len(self.SPLITS)][-1])

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "share_dealt_is_the_share_put_off": ("return damage - owed;", "return owed;"),
            "pct_not_percent": ("damage * powers.staggerPct / 100.0", "damage * powers.staggerPct"),
            "paid_all_at_once": ("std::max(0, elapsed) / static_cast<double>(entry.durationMs)", "1.0"),
            "paid_twice": ("entry.paid = finished ? entry.total : entry.paid + paidNow;",
                           "entry.paid = finished ? entry.total : entry.paid;"),
            "never_finished_on_a_zero_duration": ("entry.durationMs == 0 || elapsed", "entry.durationMs != 0 && elapsed"),
            "unsigned_clock_breaks_the_wrap": ("static_cast<std::int32_t>(nowMs - entry.startMs)",
                                               "static_cast<std::int32_t>(nowMs > entry.startMs ? nowMs - entry.startMs : 0)"),
            "seconds_not_milliseconds": ("std::max(0.0, seconds) * 1000.0", "std::max(0.0, seconds)"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            got, want = self.drive(real.replace(old, new), name)
            self.assertFalse(agrees(got, want), "mutant %s passed" % name)


class Chance(unittest.TestCase):
    """A gem's N% chance on hit is N% of the coefficient of the skill that landed it; no coefficient, no chance."""

    SCENES = [("1.0", 15.0), ("0.13", 15.0), ("0.5", 20.0), ("none", 15.0), ("0", 15.0), ("1.0", 0.0), ("0.1667", 20.0)]

    def drive(self, proc_text, name):
        done = run(["chance %s %r" % s for s in self.SCENES], None, proc_text, name)
        self.assertEqual(0, done.returncode, done.stderr)
        return [[float(x) for x in line.split()] for line in done.stdout.splitlines()]

    @staticmethod
    def model(scene):
        coefficient = None if scene[0] == "none" else float(scene[0])
        return 0.0 if not coefficient or coefficient <= 0 or scene[1] <= 0 else coefficient * scene[1]

    def agrees(self, got):
        for scene, (pct, hits) in zip(self.SCENES, got):
            want = self.model(scene)
            if abs(pct - want) > 1e-4:
                return False
            if abs(hits / 200000.0 * 100 - want) > 0.25:  # the rate of 200000 rolls, within a quarter of a point
                return False
        return len(got) == len(self.SCENES)

    def test_the_chance_is_the_coefficient_times_the_gems_chance(self):
        got = self.drive(PROC.read_text(encoding="utf-8"), "chance")
        self.assertTrue(self.agrees(got))
        self.assertAlmostEqual(15.0, got[0][0], places=4)                 # Bash 1.0: the gem's own 15%
        self.assertAlmostEqual(0.13 * 15.0, got[1][0], places=4)           # Whirlwind 0.13: about 2%
        self.assertEqual(0.0, got[3][0])                                   # a hit that states none never procs
        self.assertEqual(0, got[3][1])

    def test_the_mutants_fail_the_same_driver(self):
        real = PROC.read_text(encoding="utf-8")
        old_body = "return float(*coefficient * basePct);"
        mutants = {
            "coefficient_ignored": (old_body, "return float(basePct);"),
            "coefficient_only": (old_body, "return float(*coefficient * 100.0);"),
            "missing_coefficient_is_one": ("if (!coefficient || *coefficient <= 0 || basePct <= 0)\n            return 0.0f;\n        return float(*coefficient * basePct);",
                                           "double const c = coefficient ? *coefficient : 1.0;\n        return float(c * basePct);"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            self.assertFalse(self.agrees(self.drive(real.replace(old, new), name)), "mutant %s passed" % name)


class Tunables(unittest.TestCase):
    """The numbers the sheet and d3planner do not give are the designer's rows, and the code reads no other."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        cls.powers = (SRC / "combat/dc_gem_powers.cpp").read_text(encoding="utf-8")

    def test_every_tunable_the_gem_code_reads_is_a_combat_row(self):
        read_names = set(re.findall(r'Tune\("(gem_\w+)"\)', self.powers))
        self.assertEqual({"gem_mirinae_smite_range_yards", "gem_wreath_radius_yards", "gem_iceblink_chill_seconds",
                          "gem_iceblink_chill_slow_pct", "gem_aura_refresh_ms"}, read_names)
        for name in read_names:
            self.assertIn(name, self.rows)

    def test_the_rows_Alex_sets_are_blank_and_the_one_published_number_is_cited(self):
        for name in ("gem_mirinae_smite_range_yards", "gem_wreath_radius_yards", "gem_iceblink_chill_seconds"):
            self.assertEqual(("", ""), (self.rows[name]["d3_value"], self.rows[name]["value"]), name)
            self.assertIn("Blank =", self.rows[name]["notes"])
        slow = self.rows["gem_iceblink_chill_slow_pct"]
        self.assertEqual(("60", ""), (slow["d3_value"], slow["value"]))
        wizard = {r["name"]: r for r in read(MODULE / "data/tunables/ability_tunables.csv")}["wizard_chill_slow_pct"]
        self.assertEqual("60", wizard["value"], "Iceblink's 60 is the one the Wizard's chill uses")
        self.assertIn("maxroll", slow["notes"])

    def test_moratoriums_cadence_is_a_marked_placeholder_row_the_generator_bakes(self):
        # No source gives it (AGENTS.md Numbers), so it is the designer's row; the generator reads it into record 83404 and
        # the module reads the record, so the C++ never names the row.
        row = self.rows["gem_moratorium_pay_period_ms"]
        self.assertEqual(("", "250"), (row["d3_value"], row["value"]))
        self.assertIn("PLACEHOLDER", row["notes"])
        self.assertIn("the designer sets it", row["notes"])
        self.assertNotIn('Tune("gem_moratorium', self.powers)
        generator = (MODULE / "scripts/generate/classes/generate_spells.py").read_text(encoding="utf-8")
        self.assertIn('GEM_PAY_PERIOD_TUNABLE = "gem_moratorium_pay_period_ms"', generator)
        self.assertRegex(generator, r'if gem\["effect"\] == "stagger":\n[^\n]*\n\s*period = int\(float\(gem_pay_period\[')

    def test_the_gem_sheet_is_engineering_data_beside_its_sibling_not_verified_d3_data(self):
        self.assertTrue((MODULE / "data/legendary_gem_spells.csv").is_file())
        self.assertTrue((MODULE / "data/legendary_gem_items.csv").is_file())
        self.assertFalse((MODULE / "data/d3/legendary_gem_spells.csv").exists())
        for path in (REPO / "docs/contracts/legendary-gems.md", MODULE / "scripts/generate/classes/generate_spells.py",
                     SRC / "combat/dc_spell_shells.h", SRC / "combat/dc_gem_powers.cpp"):
            self.assertNotIn("d3/legendary_gem_spells", path.read_text(encoding="utf-8"), path.name)

    def test_the_generated_migration_carries_the_rows(self):
        sql = (MODULE / "data/sql/db-world/updates/tunables_0008.sql").read_text(encoding="utf-8")
        for name in ("gem_mirinae_smite_range_yards", "gem_wreath_radius_yards", "gem_iceblink_chill_seconds",
                     "gem_iceblink_chill_slow_pct", "gem_moratorium_pay_period_ms", "gem_aura_refresh_ms"):
            self.assertIn("'%s'" % name, sql)


if __name__ == "__main__":
    unittest.main()

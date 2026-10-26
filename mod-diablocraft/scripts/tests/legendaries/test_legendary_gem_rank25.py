"""diablocraft-apkq (Legendary gems part 10b-4): group D, the rank-25 bonuses.

  * every legendary gem with a rank-25 text is accounted for exactly once: built here, built in 10b-3 (Zei, Boyarsky),
    or built later (Enforcer, diablocraft-ml7y: test_legendary_gem_enforcer.py), or waiting, with the reason
    (Mutilation Guard: needs no code; Legacy of Dreams: set bonuses; Gem of Ease: levelling);
  * the rank-25 numbers of the sheet (the `rank25_value_*` columns) equal the numbers of d3planner's own text for
    the gem, so a number cannot be typed in by hand;
  * the production math (src/combat/dc_gem_power_math.h: Resolve at and below rank 25, Wanted, the factors, the shield
    and the chance on a kill) is compiled and driven with the generated number rows. Every expected value comes from
    d3planner's text and the sheet, never from the code under test;
  * mutants of the math fail the same driver;
  * source-text guards that the hooks call it and that every tunable the code reads is a row of combat.csv (they
    prove the call is there, not that it runs; the C++ is compile-checked by syntax_check.sh and the in-game steps
    are in docs/test-legendary-gem-rank25.md).
"""
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env
import test_legendary_gem_group_c as groupc
import test_legendary_gems as numbers

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_gem_power_math.h"
HARNESS = MODULE / "tests/legendary_gem_rank25/harness.cpp"
SCRATCH = numbers.SCRATCH

# The gems this part builds, and which planner number (index into the numbers of its rank-25 text) each Resolve field
# holds. The field order is the harness's `case` line.
FIELDS = ["powerfulEliteDamagePct", "powerfulEliteDefencePct", "strickenBossPct", "trappedYards", "trappedSlowPct",
          "esotericBelowLifePct", "esotericResistPct", "toxinTakenPct", "toxinDealtPct", "gogokCooldownPerStack",
          "iceblinkCritPct", "controlImmune", "mirinaeEverySeconds", "wildebeestQuietSeconds", "wildebeestShieldPct",
          "moratoriumClearChancePct", "painFrenzyPct", "painFrenzyYards", "simplicityHealPct",
          "taegukArmorPctPerStack", "wreathMovePct"]
BUILT = {
    "Bane of the Powerful": {"powerfulEliteDamagePct": 0, "powerfulEliteDefencePct": 1},
    "Bane of the Stricken": {"strickenBossPct": 0},
    "Bane of the Trapped": {"trappedYards": 0, "trappedSlowPct": 1},
    "Esoteric Alteration": {"esotericBelowLifePct": 0, "esotericResistPct": 1},
    "Gem of Efficacious Toxin": {"toxinTakenPct": 0, "toxinDealtPct": 1},
    "Gogok of Swiftness": {"gogokCooldownPerStack": 0},
    "Iceblink": {"iceblinkCritPct": 0},
    "Invigorating Gemstone": {"controlImmune": None},  # its text has no number: the rank is the gate
    "Mirinae, Teardrop of the Starweaver": {"mirinaeEverySeconds": 0},
    "Molten Wildebeest's Gizzard": {"wildebeestQuietSeconds": 0, "wildebeestShieldPct": 1},
    "Moratorium": {"moratoriumClearChancePct": 0},
    "Pain Enhancer": {"painFrenzyPct": 0, "painFrenzyYards": 1},
    "Simplicity's Strength": {"simplicityHealPct": 0},
    "Taeguk": {"taegukArmorPctPerStack": 0},
    "Wreath of Lightning": {"wreathMovePct": 0},
}
EARLIER = {"Zei's Stone of Vengeance", "Boyarsky's Chip"}  # their rank-25 power was part 10b-3's
LATER = {"Enforcer"}  # wired from the sourced pet list (diablocraft-ml7y); test_legendary_gem_enforcer.py
WAITS = {
    "Mutilation Guard": "moving through enemies needs no code: the 3.3.5 client has no unit collision",
    "Legacy of Dreams": "set bonuses do not exist yet",
    "Gem of Ease": "levelling does not exist yet",
}
# the planner format string that is the rank-25 power (the other is the base power); Wildebeest lists only it
R25_FORMAT = {"Molten Wildebeest's Gizzard": 0}
# part 10b-3 / 10b-2 constants the tests of those parts own; the ones this part reads
GEMS = {"Bane of the Powerful": "Powerful", "Bane of the Stricken": "Stricken", "Bane of the Trapped": "Trapped",
        "Esoteric Alteration": "Esoteric", "Gem of Efficacious Toxin": "Toxin", "Gogok of Swiftness": "Gogok",
        "Iceblink": "Iceblink", "Invigorating Gemstone": "Invigorating", "Mirinae, Teardrop of the Starweaver": "Mirinae",
        "Molten Wildebeest's Gizzard": "Wildebeest", "Moratorium": "Moratorium", "Pain Enhancer": "Pain",
        "Simplicity's Strength": "Simplicity", "Taeguk": "Taeguk", "Wreath of Lightning": "Wreath",
        "Zei's Stone of Vengeance": "Zei"}
RANKS = (0, 1, 24, 25, 26, 50, 99, 100, 150, 300)


def build(header_text, name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    files = {**{rel: (SRC / rel).read_text(encoding="utf-8") for rel in ("common/dc_legendary_gem.h", "items/dc_legendary_gem_item.h")}, "combat/dc_gem_power_math.h": header_text}
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O0"], files=files)
    work = Path(tempfile.mkdtemp(prefix="gemrank25-%s-" % name, dir=str(SCRATCH)))
    return work, binary


def run(lines, header_text=None, name="real"):
    work, binary = build(header_text or MATH.read_text(encoding="utf-8"), name)
    try:
        (work / "cases.txt").write_text("\n".join(lines) + "\n")
        return harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def agrees(got, want):
    return len(got) == len(want) and all(
        len(g) == len(w) and all(abs(a - b) <= 1e-6 * max(1.0, abs(b)) for a, b in zip(g, w)) for g, w in zip(got, want))


def unquote_numbers(text):
    return numbers.numbers(re.sub(r"%[-+0-9.]*[a-z]", "", text))


def distinct(rows, ids, numbers_by_name):
    """The generated rows with the rank-25 numbers of some gems replaced, so a mutant that reads one number for the
    other cannot hide behind a gem whose two numbers are equal (Bane of the Powerful 15 and 15, Toxin 10 and 10)."""
    out = {g: list(c) for g, c in rows.items()}
    for name, (first, second) in numbers_by_name.items():
        out[ids[name]][5], out[ids[name]][6] = first, second
    return out


class Model:
    """The expectations, from the sheet and d3planner's text and nothing of the code under test."""

    def __init__(self):
        self.d3p = numbers.planner()
        self.formats = groupc.planner_texts()
        self.fixed = numbers.planner_fixed()
        self.ids = {name: groupc.constant(const) for name, const in GEMS.items()}
        self.by_id = {gem_id: name for name, gem_id in self.ids.items()}

    def r25(self, name):
        """The numbers of the gem's rank-25 text in d3planner."""
        formats = self.formats[name]
        return unquote_numbers(formats[R25_FORMAT.get(name, 1)])

    def value(self, name, rank, slot=0):
        gem = self.d3p[name]
        top = rank if gem[3] is None else min(rank, gem[3])
        return gem[1][slot] + gem[2][slot] * top

    def best(self, worn):
        best = {}
        for gem_id, rank in worn:
            best[gem_id] = max(best.get(gem_id, 0), rank)
        return {self.by_id[g]: r for g, r in best.items() if g in self.by_id}

    def resolve(self, worn):
        out = dict.fromkeys(FIELDS, 0.0)
        for name, rank in self.best(worn).items():
            if rank < 25 or name not in BUILT:
                continue
            for field, index in BUILT[name].items():
                out[field] = 1.0 if index is None else self.r25(name)[index]
        return [out[f] for f in FIELDS]

    def wanted(self, worn, gogok, taeguk, bleeding, wreath, below, base):
        w = self.best(worn)
        at25 = lambda name: w.get(name, -1) >= 25
        out = [0.0] * 11
        if "Gogok of Swiftness" in w:
            out[0] = self.fixed["Gogok of Swiftness"][0] * gogok   # "Attack Speed by 1%" a stack, from the base text
        if at25("Gogok of Swiftness"):
            out[1] = min(100.0, self.r25("Gogok of Swiftness")[0] * gogok)
        if at25("Taeguk"):
            out[2] = self.r25("Taeguk")[0] * taeguk
        if at25("Pain Enhancer"):
            out[3] = self.r25("Pain Enhancer")[0] * bleeding
        if at25("Wreath of Lightning") and wreath:
            out[4] = self.r25("Wreath of Lightning")[0]
        if at25("Bane of the Powerful"):
            out[5] = self.r25("Bane of the Powerful")[0]
        if at25("Esoteric Alteration") and below:
            for i in range(5):
                out[6 + i] = base[i] * self.r25("Esoteric Alteration")[1] / 100.0
        return out


class Accounting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = [r for r in numbers.read(numbers.CSV) if r["gem_id"]]

    def test_every_gem_with_a_rank_25_text_is_built_earlier_or_waits_for_a_reason(self):
        names = {r["gem_name"] for r in self.live}
        accounted = set(BUILT) | EARLIER | LATER | set(WAITS)
        self.assertEqual(21, len(names))
        self.assertEqual(names, accounted)
        self.assertEqual(set(), set(BUILT) & EARLIER | set(BUILT) & set(WAITS) | EARLIER & set(WAITS) |
                         LATER & (set(BUILT) | EARLIER | set(WAITS)))
        self.assertEqual(21, len(BUILT) + len(EARLIER) + len(LATER) + len(WAITS))

    def test_the_waits_and_the_gems_built_are_named_in_the_contract(self):
        contract = (REPO / "docs/contracts/legendary-gems.md").read_text(encoding="utf-8")
        section = contract[contract.index("## Group D"):]
        for name in list(BUILT) + list(WAITS):
            self.assertIn(name, section, name)

    def test_the_numbers_of_each_built_gem_are_d3planners_own_text(self):
        model = Model()
        sheet = {r["gem_name"]: r for r in self.live}
        for name, fields in BUILT.items():
            cells = [float(sheet[name][c]) for c in ("rank25_value_1", "rank25_value_2") if sheet[name][c]]
            planner = model.r25(name)
            self.assertEqual(planner, cells, name)
            for field, index in fields.items():
                if index is not None:
                    self.assertLess(index, len(cells), "%s: %s has no number %d" % (name, field, index))

    def test_esoteric_alterations_half_is_a_number_of_the_sheet(self):
        row = {r["gem_name"]: r for r in self.live}["Esoteric Alteration"]
        self.assertEqual(("50", "75"), (row["rank25_value_1"], row["rank25_value_2"]))
        self.assertIn("below half Life", row["rank_25_bonus"])

    def test_the_gems_that_wait_are_not_read_by_the_code(self):
        # Mutilation Guard's 50 is in the sheet, and no code reads it: nothing for it to do
        resolve = MATH.read_text(encoding="utf-8")
        for const in ("Mutilation", "Simplicity"):
            self.assertIn("char const* %s =" % const, resolve)
        body = resolve[resolve.index("else if (gem.gemId == Mutilation)"):resolve.index("else if (gem.gemId == Simplicity)")]
        self.assertNotIn("Rank25Number", body)


class Resolving(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = Model()
        cls.rows = groupc.rows()

    def cases(self):
        ids = self.model.ids
        out = []
        for name, gem_id in ids.items():
            for rank in RANKS:
                out.append([(gem_id, rank)])
        out.append([(g, 25) for g in ids.values()])
        out.append([(g, 24) for g in ids.values()])
        out.append([(g, 300) for g in ids.values()])
        # Unique Equipped: two of a kind, the highest rank counts, whatever the order
        t = ids["Taeguk"]
        out.append([(t, 5), (t, 60)])
        out.append([(t, 60), (t, 5)])
        out.append([(t, 24), (t, 25)])
        # a gem with no rank-25 field here (Mutilation Guard; Enforcer's is its own test) adds nothing to these
        out.append([("Unique_Gem_019_x1", 50), ("Unique_Gem_010_x1", 50)])
        out.append([])
        return out

    def drive(self, header_text, name):
        lines = [groupc.row_line(g, c) for g, c in self.rows.items()]
        cases = self.cases()
        lines += ["case %d %s" % (len(w), " ".join("%s %d" % g for g in w)) for w in cases]
        done = run(lines, header_text, name)
        self.assertEqual(0, done.returncode, done.stderr)
        return [[float(x) for x in line.split()] for line in done.stdout.splitlines()], [self.model.resolve(w) for w in cases]

    def test_every_rank_25_number_at_every_rank_is_the_sheets_and_none_applies_below_25(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 150)
        self.assertTrue(agrees(got, want))
        by = lambda worn: dict(zip(FIELDS, got[self.cases().index(worn)]))
        taeguk = self.model.ids["Taeguk"]
        self.assertEqual(0.0, by([(taeguk, 24)])["taegukArmorPctPerStack"])  # "(Requires Rank 25)"
        self.assertEqual(2.0, by([(taeguk, 25)])["taegukArmorPctPerStack"])  # "Gain 2% increased Armor for every stack"
        self.assertEqual(2.0, by([(taeguk, 300)])["taegukArmorPctPerStack"])  # no cap of its own: still 2
        esoteric = self.model.ids["Esoteric Alteration"]
        self.assertEqual((50.0, 75.0), (by([(esoteric, 25)])["esotericBelowLifePct"], by([(esoteric, 25)])["esotericResistPct"]))
        invigorating = self.model.ids["Invigorating Gemstone"]
        self.assertEqual((0.0, 1.0), (by([(invigorating, 24)])["controlImmune"], by([(invigorating, 25)])["controlImmune"]))
        # Unique Equipped: the higher rank counts, so rank 60's bonus applies whichever order they are worn in
        self.assertEqual(2.0, by([(taeguk, 5), (taeguk, 60)])["taegukArmorPctPerStack"])
        self.assertEqual(2.0, by([(taeguk, 24), (taeguk, 25)])["taegukArmorPctPerStack"])
        # Mutilation Guard has its rank-25 power in the sheet and none in the code; Enforcer's fields are not these
        self.assertEqual([0.0] * len(FIELDS), got[self.cases().index([("Unique_Gem_019_x1", 50), ("Unique_Gem_010_x1", 50)])])

    def test_a_built_gem_with_no_rank_25_number_is_an_error_not_a_zero(self):
        gem = self.model.ids["Esoteric Alteration"]
        lines = ["row %s 10 0.5 100 none none none none none none none" % gem, "case 1 %s 30" % gem]
        self.assertNotEqual(0, run(lines).returncode)
        self.assertEqual(0, run(lines[:1] + ["case 1 %s 24" % gem]).returncode)  # below rank 25 it is not asked
        # Invigorating's text has no number: it must not ask for one
        gem = self.model.ids["Invigorating Gemstone"]
        lines = ["row %s 1 0.02 none none none 5 10 none none none" % gem, "case 1 %s 30" % gem]
        self.assertEqual(0, run(lines).returncode)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "gate_is_26": ("bool const rank25 = gem.rank >= Rank25;", "bool const rank25 = gem.rank > Rank25;"),
            "gate_is_24": ("bool const rank25 = gem.rank >= Rank25;", "bool const rank25 = gem.rank >= Rank25 - 1;"),
            "no_gate": ("bool const rank25 = gem.rank >= Rank25;", "bool const rank25 = true;"),
            "immune_always": ("powers.controlImmune = rank25;", "powers.controlImmune = true;"),
            "immune_never": ("powers.controlImmune = rank25;", "powers.controlImmune = false;"),
            "gogok_cooldown_is_unscaled": ("powers.gogokCooldownPerStack = Rank25Number(*row, 0);", "powers.gogokCooldownPerStack = value;"),
            "taeguk_armor_is_the_stack_value": ("powers.taegukArmorPctPerStack = Rank25Number(*row, 0);", "powers.taegukArmorPctPerStack = value;"),
            "mirinae_clock_is_the_chance": ("powers.mirinaeEverySeconds = Rank25Number(*row, 0);", "powers.mirinaeEverySeconds = Fixed(*row, 0);"),
            "wreath_speed_is_its_chance": ("powers.wreathMovePct = Rank25Number(*row, 0);", "powers.wreathMovePct = Fixed(*row, 0);"),
            "simplicity_heal_is_the_damage": ("powers.simplicityHealPct = Rank25Number(*row, 0);", "powers.simplicityHealPct = value;"),
            "stricken_boss_is_the_stack": ("powers.strickenBossPct = Rank25Number(*row, 0);", "powers.strickenBossPct = value;"),
            "iceblink_crit_is_the_slow": ("powers.iceblinkCritPct = Rank25Number(*row, 0);", "powers.iceblinkCritPct = value;"),
            "moratorium_clear_is_the_share": ("powers.moratoriumClearChancePct = Rank25Number(*row, 0);", "powers.moratoriumClearChancePct = Fixed(*row, 0);"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            got, want = self.drive(real.replace(old, new), name)
            self.assertFalse(agrees(got, want), "mutant %s passed" % name)

    def test_a_gem_with_two_rank_25_numbers_reads_each_in_its_own_place(self):
        """Six gems have two numbers; two of them are equal in the sheet, so the real rows cannot tell the first from the
        second. The same rows with the two numbers made 11 and 13, real header against mutant header."""
        two = {"Bane of the Powerful": "powerfulEliteDamagePct", "Bane of the Trapped": "trappedYards",
               "Esoteric Alteration": "esotericBelowLifePct", "Gem of Efficacious Toxin": "toxinTakenPct",
               "Molten Wildebeest's Gizzard": "wildebeestQuietSeconds", "Pain Enhancer": "painFrenzyPct"}
        rows = distinct(self.rows, self.model.ids, {name: (11.0, 13.0) for name in two})
        lines = [groupc.row_line(g, c) for g, c in rows.items()]
        lines += ["case 1 %s 25" % self.model.ids[name] for name in two]

        def read(header, name):
            done = run(lines, header, name)
            self.assertEqual(0, done.returncode, done.stderr)
            return [[float(x) for x in line.split()] for line in done.stdout.splitlines()]

        real = MATH.read_text(encoding="utf-8")
        got = read(real, "real")
        for (name, field), line in zip(two.items(), got):
            self.assertEqual(11.0, dict(zip(FIELDS, line))[field], name)
            self.assertEqual(13.0, dict(zip(FIELDS, line))[FIELDS[FIELDS.index(field) + 1]], name)
        for field in two.values():
            old = "powers.%s = Rank25Number(*row, 0);" % field
            self.assertEqual(1, real.count(old), field)
            self.assertNotEqual(got, read(real.replace(old, old.replace("(*row, 0)", "(*row, 1)")), field), field)


class Wanting(unittest.TestCase):
    """What the gems put on the sheet, as the state moves (stacks, Life, the Wreath, bleeding enemies)."""

    @classmethod
    def setUpClass(cls):
        cls.model = Model()
        cls.rows = groupc.rows()

    def scenes(self):
        ids = self.model.ids
        g, t, p, w, e, pw = (ids["Gogok of Swiftness"], ids["Taeguk"], ids["Pain Enhancer"], ids["Wreath of Lightning"],
                             ids["Esoteric Alteration"], ids["Bane of the Powerful"])
        base = [10, 20, 30, 40, 50]
        zero = [0] * 5
        every = [(g, 25), (t, 25), (p, 25), (w, 25), (e, 25), (pw, 25)]
        return [
            ([(g, 25)], 15, 0, 0, 0, 0, zero),
            ([(g, 24)], 15, 0, 0, 0, 0, zero),     # base Attack Speed, no Cooldown Reduction below 25
            ([(g, 25)], 0, 0, 0, 0, 0, zero),
            ([(g, 25)], 500, 0, 0, 0, 0, zero),    # a Cooldown Reduction cannot pass 100 (the sheet refuses it)
            ([(t, 25)], 0, 10, 0, 0, 0, zero),
            ([(t, 24)], 0, 10, 0, 0, 0, zero),
            ([(p, 25)], 0, 0, 4, 0, 0, zero),
            ([(p, 25)], 0, 0, 0, 0, 0, zero),
            ([(p, 24)], 0, 0, 4, 0, 0, zero),
            ([(w, 25)], 0, 0, 0, 1, 0, zero),
            ([(w, 25)], 0, 0, 0, 0, 0, zero),
            ([(w, 24)], 0, 0, 0, 1, 0, zero),
            ([(pw, 25)], 0, 0, 0, 0, 0, zero),
            ([(pw, 24)], 0, 0, 0, 0, 0, zero),
            ([(e, 25)], 0, 0, 0, 0, 1, base),
            ([(e, 25)], 0, 0, 0, 0, 0, base),      # not below half Life
            ([(e, 24)], 0, 0, 0, 0, 1, base),
            ([(e, 25)], 0, 0, 0, 0, 1, zero),
            (every, 7, 3, 2, 1, 1, base),
            (every, 0, 0, 0, 0, 0, base),
            ([], 15, 10, 4, 1, 1, base),
        ]

    def drive(self, header_text, name):
        lines = [groupc.row_line(g, c) for g, c in self.rows.items()]
        want = []
        for worn, gogok, taeguk, bleeding, wreath, below, base in self.scenes():
            lines.append("wanted %d %s %d %d %d %d %d %s" % (
                len(worn), " ".join("%s %d" % x for x in worn), gogok, taeguk, bleeding, wreath, below,
                " ".join(repr(float(b)) for b in base)))
            want.append(self.model.wanted(worn, gogok, taeguk, bleeding, wreath, below, base))
        done = run(lines, header_text, name)
        self.assertEqual(0, done.returncode, done.stderr)
        return [[float(x) for x in line.split()] for line in done.stdout.splitlines()], want

    def test_the_sheet_follows_the_state(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertTrue(agrees(got, want), (got, want))
        # the readable ones
        self.assertEqual([15.0, 15.0], got[0][:2])         # Gogok: 1% Attack Speed and 1% Cooldown Reduction a stack
        self.assertEqual([15.0, 0.0], got[1][:2])
        self.assertEqual(100.0, got[3][1])
        self.assertEqual(20.0, got[4][2])                  # Taeguk: 2% Armor a stack
        self.assertEqual(12.0, got[6][3])                  # Blood Frenzy: 3% per bleeding enemy
        self.assertEqual(25.0, got[9][4])                  # the Wreath: 25% Movement Speed
        self.assertEqual(15.0, got[12][5])                 # Bane of the Powerful: 15% elite damage
        self.assertEqual([7.5, 15.0, 22.5, 30.0, 37.5], got[14][6:])   # resistances x 1.75: +75% of what they were
        self.assertEqual([0.0] * 5, got[15][6:])

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        for name, (old, new) in MUTANTS_WANTED.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            got, want = self.drive(real.replace(old, new), name)
            self.assertFalse(agrees(got, want), "mutant %s passed" % name)

    def test_the_elite_damage_is_the_first_number_not_the_defence(self):
        # 15 and 15 in the sheet: with 11 and 13 the sheet's elite damage is 11, and a mutant that reads the 13 shows
        gem = self.model.ids["Bane of the Powerful"]
        rows = distinct(self.rows, self.model.ids, {"Bane of the Powerful": (11.0, 13.0)})
        lines = [groupc.row_line(g, c) for g, c in rows.items()] + ["wanted 1 %s 25 0 0 0 0 0 0 0 0 0 0" % gem]
        real = MATH.read_text(encoding="utf-8")
        self.assertEqual(11.0, float(run(lines).stdout.split()[5]))
        old = "out.eliteDamage = powers.powerfulEliteDamagePct;"
        self.assertEqual(1, real.count(old))
        mutant = run(lines, real.replace(old, "out.eliteDamage = powers.powerfulEliteDefencePct;"), "elite")
        self.assertEqual(13.0, float(mutant.stdout.split()[5]))

    def test_two_sheets_equal_within_a_millionth_of_a_percent(self):
        # the resistances are read back from a sheet that already holds the last ones: (a + b) - b is not always a
        lines = ["same 5 5.0000001", "same 5 5.001", "same 0.3 0.30000000000000004"]
        self.assertEqual(["1", "0", "1"], run(lines).stdout.split())
        real = MATH.read_text(encoding="utf-8")
        exact = real.replace("std::fabs(a - b) < 1e-6", "a == b")
        self.assertNotEqual(real, exact)
        self.assertNotEqual(["1", "0", "1"], run(lines, exact, "exact").stdout.split())


MUTANTS_WANTED = {
    "cooldown_unclamped": ("std::min(100.0, powers.gogokCooldownPerStack * now.gogok)", "powers.gogokCooldownPerStack * now.gogok"),
    "cooldown_not_per_stack": ("std::min(100.0, powers.gogokCooldownPerStack * now.gogok)", "std::min(100.0, powers.gogokCooldownPerStack)"),
    "armor_not_per_stack": ("powers.taegukArmorPctPerStack * now.taeguk", "powers.taegukArmorPctPerStack"),
    "frenzy_not_per_enemy": ("powers.painFrenzyPct * now.bleeding", "powers.painFrenzyPct"),
    "wreath_speed_without_the_wreath": ("now.wreath ? powers.wreathMovePct : 0.0", "powers.wreathMovePct"),
    "resistance_absolute": ("now.resistBase[i] * powers.esotericResistPct / 100.0", "powers.esotericResistPct"),
    "resistance_at_full_life": ("if (now.belowLife && powers.esotericResistPct > 0)", "if (powers.esotericResistPct > 0)"),
    "attack_speed_per_stack_is_dodge": ("out.gogokAttackSpeed = AttackSpeedPct(powers, now.gogok);", "out.gogokAttackSpeed = DodgePct(powers, now.gogok);"),
}


class Factoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = Model()
        cls.rows = groupc.rows()

    def lines(self, worn, extra):
        lines = [groupc.row_line(g, c) for g, c in self.rows.items()]
        lines.append(extra % (len(worn), " ".join("%s %d" % x for x in worn)))
        return lines

    def factors(self, worn, header_text=None, name="real", rows=None):
        lines = [groupc.row_line(g, c) for g, c in (rows or self.rows).items()]
        lines.append("factors %d %s" % (len(worn), " ".join("%s %d" % x for x in worn)))
        done = run(lines, header_text, name)
        self.assertEqual(0, done.returncode, done.stderr)
        return [float(x) for x in done.stdout.split()]

    def test_the_elite_and_poison_and_boss_factors(self):
        ids = self.model.ids
        # Bane of the Powerful: "take 15% reduced damage from elites"
        got = self.factors([(ids["Bane of the Powerful"], 25)])
        self.assertAlmostEqual(0.85, got[0])
        self.assertAlmostEqual(1.0, got[1])
        self.assertAlmostEqual(1.0, self.factors([(ids["Bane of the Powerful"], 24)])[0])
        # Gem of Efficacious Toxin: "take 10% increased damage ... and deal 10% less damage"
        got = self.factors([(ids["Gem of Efficacious Toxin"], 25)])
        self.assertAlmostEqual(0.9, got[2])
        self.assertAlmostEqual(10.0, got[3])
        got = self.factors([(ids["Gem of Efficacious Toxin"], 24)])
        self.assertEqual((1.0, 0.0), (got[2], got[3]))
        # Bane of the Stricken: "25% increased damage against bosses and Rift Guardians", on top of the stacks
        rank = 40
        stacks = 1.0 + 3 * self.model.value("Bane of the Stricken", rank) / 100.0
        got = self.factors([(ids["Bane of the Stricken"], rank)])
        self.assertAlmostEqual(stacks, got[5])
        self.assertAlmostEqual(stacks * 1.25, got[4])
        got = self.factors([(ids["Bane of the Stricken"], 24)])
        self.assertAlmostEqual(got[5], got[4])

    def test_the_shield_waits_for_the_quiet_and_is_a_share_of_the_life_per_second(self):
        gem = self.model.ids["Molten Wildebeest's Gizzard"]

        def shield(rank, armed, quiet, lps, header=None, name="real"):
            done = run(self.lines([(gem, rank)], "shield %d %s " + "%d %d %r" % (armed, quiet, lps)), header, name)
            self.assertEqual(0, done.returncode, done.stderr)
            return [float(x) for x in done.stdout.split()]

        self.assertEqual([1.0, 24690.0], shield(25, 1, 4000, 12345))   # 4 seconds, 200% of the Life per Second
        self.assertEqual(0.0, shield(25, 1, 3999, 12345)[0])
        self.assertEqual(1.0, shield(25, 1, 400000, 12345)[0])
        self.assertEqual(0.0, shield(25, 0, 4000, 12345)[0])           # nothing hurt it: one quiet spell, one shield
        self.assertEqual(0.0, shield(24, 1, 4000, 12345)[0])           # "(Requires Rank 25)"
        real = MATH.read_text(encoding="utf-8")
        for name, (old, new) in {
            "no_arming": ("return armed && powers.wildebeestShieldPct > 0", "return powers.wildebeestShieldPct > 0"),
            "quiet_boundary_exclusive": ("quietMs >= powers.wildebeestQuietSeconds * 1000.0", "quietMs > powers.wildebeestQuietSeconds * 1000.0"),
            "quiet_in_seconds": ("quietMs >= powers.wildebeestQuietSeconds * 1000.0", "quietMs >= powers.wildebeestQuietSeconds"),
            "shield_unscaled": ("return lifePerSecond * powers.wildebeestShieldPct / 100.0;", "return lifePerSecond;"),
        }.items():
            self.assertEqual(1, real.count(old), name)
            variant = real.replace(old, new)
            got = [shield(25, 1, 4000, 12345, variant, name), shield(25, 1, 3999, 12345, variant, name),
                   shield(25, 0, 4000, 12345, variant, name), shield(25, 1, 100, 12345, variant, name)]
            want = [[1.0, 24690.0], [0.0, 24690.0], [0.0, 24690.0], [0.0, 24690.0]]
            self.assertNotEqual(want, got, "mutant %s passed" % name)

    def test_a_chance_on_a_kill_hits_below_its_percentage_and_never_at_zero(self):
        lines = ["chance 20 19.999", "chance 20 20", "chance 20 0", "chance 0 -0.5", "chance 0 0", "chance 100 99.9"]
        done = run(lines)
        self.assertEqual(["1", "0", "1", "0", "0", "1"], done.stdout.split())
        real = MATH.read_text(encoding="utf-8")
        for name, (old, new) in {
            "inclusive": ("return pct > 0 && roll < pct;", "return pct > 0 && roll <= pct;"),
            "zero_hits": ("return pct > 0 && roll < pct;", "return roll < pct;"),
            "inverted": ("return pct > 0 && roll < pct;", "return pct > 0 && roll > pct;"),
        }.items():
            self.assertEqual(1, real.count(old), name)
            self.assertNotEqual(["1", "0", "1", "0", "0", "1"], run(lines, real.replace(old, new), name).stdout.split(), name)

    def test_the_factor_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        ids = self.model.ids
        worn = [(ids["Bane of the Powerful"], 25), (ids["Gem of Efficacious Toxin"], 25), (ids["Bane of the Stricken"], 40)]
        # Bane of the Powerful's two numbers and the Toxin's are equal in the sheet: give them distinct ones
        rows = distinct(self.rows, ids, {"Bane of the Powerful": (11.0, 13.0), "Gem of Efficacious Toxin": (12.0, 7.0)})
        want = self.factors(worn, rows=rows)
        self.assertEqual([0.87, 1.0, 0.93, 12.0], [round(x, 6) for x in want[:4]])
        for name, (old, new) in {
            "elite_defence_for_everyone": ("return attackerIsElite ? 1.0 - powers.powerfulEliteDefencePct / 100.0 : 1.0;",
                                           "return 1.0 - powers.powerfulEliteDefencePct / 100.0;"),
            "elite_defence_for_no_one": ("return attackerIsElite ? 1.0 - powers.powerfulEliteDefencePct / 100.0 : 1.0;",
                                         "return 1.0;"),
            "weakened_adds": ("return 1.0 - powers.toxinDealtPct / 100.0;", "return 1.0 + powers.toxinDealtPct / 100.0;"),
            "victim_takes_what_it_deals": ("return powers.toxinTakenPct;", "return powers.toxinDealtPct;"),
            "boss_ignored": ("if (boss)\n            factor *= 1.0 + powers.strickenBossPct / 100.0;",
                             "if (!boss)\n            factor *= 1.0 + powers.strickenBossPct / 100.0;"),
            "boss_bonus_off": ("factor *= 1.0 + powers.strickenBossPct / 100.0;", "factor *= 1.0;"),
        }.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            self.assertNotEqual(want, self.factors(worn, real.replace(old, new), name, rows), "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

"""Legendary powers P4, the K4 patterns the Wastes build needs (diablocraft-j86ni): a rune given without choosing it, every rune at once, a
skill another skill's hit applies, a bleed that stacks and a bleed paid out in one second.

  * data/legendary_powers.csv gains eight rows: the Wastes 6-piece (Whirlwind gains Dust Devils; all Whirlwind and Rend damage x101), Mortick's
    Brace (every rune of Wrath of the Berserker), Ambo's Pride (a Whirlwind hit applies Rend; Rend's whole damage dealt over 1 second) and
    Lamentation (Rend stacks up to 2; its damage +[100-150]%). Every number is read from its source text and compared (the planner's
    wording, the sets and legendaries sheets, the rune sheet, and the Power files through decode_pow.py where the client data is on this machine);
  * the generator refuses a row it cannot stand behind (a rune that is not the skill's, a granted rune that is not simply on, an apply_skill the code
    cannot apply, a hit with no skill, a stack count that is not a whole number above 1, ...);
  * the production rules (src/combat/dc_item_power_math.h: GrantsRune, SkillLowest, Ticks and the bleed stacks, with Fire and SkillFactor on the
    rows) are compiled and driven with the generated rows: the sets' counts, the worn item, the stored roll, the bleed to the tick;
  * mutants of those rules fail the same driver;
  * source-text guards that every rune effect reads the rune through the one lookup, the Rend bleed carries its stacks, and the apply path keeps a running
    bleed (they prove the call is there, not that it runs; the C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-j86ni.md).
"""
import csv
import math
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_k4/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
WASTES, MORTICK, AMBO, LAMENTATION = "Wrath of the Wastes", "P2_Unique_Bracer_003", "P67_Unique_Mighty_1H_012", "P67_Unique_BarbBelt_005"
OWNERS = {(WASTES, 6), (MORTICK, 0), (AMBO, 0), (LAMENTATION, 0)}


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def generated_rows():
    """The rows of this bead, sixteen columns, in table order."""
    text = GENERATED.read_text(encoding="utf-8")
    rows = [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16]))
            for m in re.finditer(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)", text)]
    return [r for r in rows if (r[0], r[1]) in OWNERS]


def all_rows():
    text = GENERATED.read_text(encoding="utf-8")
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16]))
            for m in re.finditer(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)", text)]


def six_piece():
    """(rune, [skills], percent) from the Wastes 6-piece text of the sets sheet."""
    texts = {r["bonus_6pc"] for r in read_csv("data/d3/barbarian_sets.csv") if r["set_name"] == WASTES}
    assert len(texts) == 1, texts
    m = re.fullmatch(r"(\w+) gains the effect of the ([\w' ]+) rune and all (\w+) and (\w+) damage is increased by (\d+)%\.", texts.pop())
    assert m, "the 6-piece text changed"
    return m[2], (m[1], m[3], m[4]), float(m[5])


def legendary_text(name):
    return next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == name)


def ambo_numbers():
    """(skill that hits, skill applied, seconds) from the planner's wording of Ambo's Pride."""
    text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
    start = text.index('id: "P67_Unique_Mighty_1H_012"')
    block = text[start:text.index("},\n\n", start)]
    m = re.search(r"Attacking with (\w+) also applies (\w+), and the total damage of \w+ is dealt over (\d+) second", block)
    assert m, block
    return m[1], m[2], float(m[3])


def lamentation_numbers():
    """(stacks, low %, high %) from the legendaries sheet's wording of Lamentation."""
    m = re.search(r"Rend can now stack up to (\d+) times on an enemy, and the damage of Rend is increased by \[(\d+) - (\d+)\]%", legendary_text("Lamentation"))
    assert m
    return float(m[1]), float(m[2]), float(m[3])


def wrath_runes():
    return [r["rune_name"] for r in read_csv("data/d3/barbarian_runes.csv") if r["skill_name"] == "Wrath of the Berserker"]


class Table(unittest.TestCase):
    def test_rows_are_their_sources_numbers(self):
        rune, (skill, first, second), pct = six_piece()
        stacks, low, high = lamentation_numbers()
        hitter, applied, seconds = ambo_numbers()
        self.assertEqual(("Dust Devils", ("Whirlwind", "Whirlwind", "Rend"), 10000.0), (rune, (skill, first, second), pct))
        self.assertIn("Dust Devils", [r["rune_name"] for r in read_csv("data/d3/barbarian_runes.csv") if r["skill_name"] == "Whirlwind"])
        self.assertEqual("Wrath of the Berserker gains the effect of every rune.", legendary_text("Mortick's Brace"))
        self.assertEqual(5, len(wrath_runes()))
        want = {
            (WASTES, 6, "rune", skill, rune, 1.0, 1.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (WASTES, 6, "skill", first, "damage_increase_pct", pct, pct, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (WASTES, 6, "skill", second, "damage_increase_pct", pct, pct, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (MORTICK, 0, "rune", "Wrath of the Berserker", "all", 1.0, 1.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (AMBO, 0, "effect", applied, "apply_skill", 1.0, 1.0, "", 0.0, "", 0.0, 0, "hit", hitter, 100.0, 0.0),
            (AMBO, 0, "skill", applied, "dot_payout_seconds", seconds, seconds, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (LAMENTATION, 0, "skill", "Rend", "dot_max_stacks", stacks, stacks, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (LAMENTATION, 0, "skill", "Rend", "damage_increase_pct", low, high, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
        }
        self.assertEqual(want, set(generated_rows()))
        self.assertEqual(8, len(generated_rows()))
        self.assertEqual((2.0, 100.0, 150.0), (stacks, low, high))
        self.assertEqual(("Whirlwind", "Rend", 1.0), (hitter, applied, seconds))

    def test_the_power_files_agree_where_the_client_data_is_here(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the client data is not on this machine")
        attrs = decode_pow.items()
        _, low, high = lamentation_numbers()
        value = lambda item: decode_pow.evaluate(next(f for i, sno, f in attrs[item] if i == decode_pow.ATTR_ITEM_POWER_PASSIVE))  # noqa: E731
        self.assertEqual((low / 100, high / 100), tuple(round(v, 6) for v in value(LAMENTATION)))   # the item's own number is the range
        self.assertEqual((1.0, 1.0), tuple(round(v, 6) for v in value(MORTICK)))                    # Mortick's: simply on
        self.assertEqual((0.2, 0.3), tuple(round(v, 6) for v in value(AMBO)))                       # Ambo's: a number the text does not use

    def test_every_row_has_a_source_and_a_note(self):
        sheet = {(r["owner"], r["pieces"] or "0", r["skill"], r["stat"]): r for r in read_csv("data/legendary_powers.csv")}
        for owner, pieces, _, skill, stat, *_ in generated_rows():
            row = sheet[(owner, str(pieces), skill, stat)]
            self.assertTrue(row["source"].strip() and row["note"].strip(), (owner, stat))

    def test_generator_refuses_a_row_it_cannot_stand_behind(self):
        base = {"owner": MORTICK, "pieces": "", "kind": "rune", "skill": "Wrath of the Berserker", "stat": "all", "value_min": "1", "value_max": "1",
                "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                "icd_seconds": "", "source": "x", "note": ""}
        apply = dict(base, owner=AMBO, kind="effect", skill="Rend", stat="apply_skill", fire_on="hit", fire_skills="Whirlwind")
        stack = dict(base, owner=LAMENTATION, kind="skill", skill="Rend", stat="dot_max_stacks", value_min="2", value_max="2")
        payout = dict(base, owner=AMBO, kind="skill", skill="Rend", stat="dot_payout_seconds")
        bad = {
            "a rune of another skill": dict(base, stat="Dust Devils"),
            "a rune that does not exist": dict(base, stat="Not A Rune"),
            "a rune of a skill that does not exist": dict(base, skill="Not A Skill", stat="all"),
            "a rune with no skill": dict(base, skill=""),
            "a granted rune that is not 1": dict(base, value_min="2", value_max="2"),
            "a granted rune that rolls": dict(base, value_max="2"),
            "a granted rune with a condition": dict(base, cond="triggered", cond_arg="3", fire_on="kill"),
            "a granted rune that fires": dict(base, fire_on="kill"),
            "a skill named by a stat row": dict(base, kind="stat", stat="edmg"),
            "an apply the code cannot do": dict(apply, skill="Whirlwind"),
            "an apply that names no skill": dict(apply, skill=""),
            "an apply with no event": dict(apply, fire_on="", fire_skills=""),
            "a hit with no skill": dict(apply, fire_skills=""),
            "a hit of a skill that does not exist": dict(apply, fire_skills="Not A Skill"),
            "skills on a kill": dict(apply, fire_on="kill"),
            "a cooldown cut that names a skill": dict(apply, stat="cooldown_cut_seconds"),
            "a stack count of 1": dict(stack, value_min="1", value_max="1"),
            "a fractional stack count": dict(stack, value_min="2.5", value_max="2.5"),
            "a stack count that rolls": dict(stack, value_max="3"),
            "stacks on a skill with no bleed": dict(stack, skill="Frenzy"),
            "a payout on a skill with no bleed": dict(payout, skill="Frenzy"),
            "a payout that rolls": dict(payout, value_max="2"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        self.assertEqual([(MORTICK, 0, "rune", "Wrath of the Berserker", "all", 1.0, 1.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)], self.rows_of([base]))
        self.assertEqual(1, len(self.rows_of([dict(base, stat="Insanity")])))           # a rune of the skill, by name
        self.assertEqual(2, len(self.rows_of([base, dict(base, stat="Insanity")])))     # all and one: two rows, one grant
        self.assertEqual(1, len(self.rows_of([apply])))
        self.assertEqual(1, len(self.rows_of([stack])))
        self.assertEqual(1, len(self.rows_of([payout])))
        self.assertEqual(1, len(self.rows_of([dict(base, owner=WASTES, pieces="6", skill="Whirlwind", stat="Dust Devils")])))
        with self.subTest("listed twice"), self.assertRaises(ValueError):
            self.rows_of([base, base])

    @staticmethod
    def rows_of(sheet_rows):
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as folder:
            module = Path(folder)
            (module / "data/d3").mkdir(parents=True)
            for name in ("base_items.csv", "affix_pools.csv", "legendary_potions.csv", *sorted(p.name for p in (MODULE / "data/d3").glob("*_skills.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skill_values.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_runes.csv"))):
                shutil.copy(MODULE / "data/d3" / name, module / "data/d3" / name)
            with (module / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
                writer.writeheader()
                writer.writerows(sheet_rows)
            return [row for row in generator.rows(module) if row[2] != "potion"]  # the potions' own rows (87qlt)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemk4-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    @staticmethod
    def sets(**worn):
        return ["%d" % len(worn)] + [x for name, n in worn.items() for x in (name.replace("_", " "), str(n))]

    def cases(self):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in all_rows()]
        assert all(len(c[0].split("\t")) == 17 for c in out), "row width"
        none = self.sets()
        rune_, (_, first, second), pct = six_piece()
        two_piece = next(r for r in all_rows() if r[0] == WASTES and r[1] == 2 and r[4] == "damage_increase_pct")[5]
        big = 1 + pct / 100                      # 101: its own multiplier
        rend2 = 1 + two_piece / 100              # 6
        grant = lambda skill, rune, *sets, wears=(): [(T("clear"), None)] + [(T("wears", w, 0), None) for w in wears] + [  # noqa: E731
            (T("rune", skill, rune, *(sets or none)), None)]
        want_rune = lambda skill, rune, expect, *sets, wears=(): grant(skill, rune, *sets, wears=wears)[:-1] + [  # noqa: E731
            (T("rune", skill, rune, *(sets or none)), "1" if expect else "0")]

        # the Wastes 6-piece: Dust Devils for Whirlwind from the sixth piece, no other rune and no other skill's
        for worn in range(0, 7):
            out += want_rune("Whirlwind", rune_, worn >= 6, *self.sets(Wrath_of_the_Wastes=worn))
        out += want_rune("Whirlwind", rune_, True, *self.sets(Wrath_of_the_Wastes=6, Other_Set=1))
        out += want_rune("Whirlwind", rune_, False, *self.sets(Other_Set=6))
        for other in ("Hurricane", "Wind Shear", "Blood Funnel", "Volcanic Eruption"):
            out += want_rune("Whirlwind", other, False, *self.sets(Wrath_of_the_Wastes=6))
        out += want_rune("Rend", rune_, False, *self.sets(Wrath_of_the_Wastes=6))
        out += want_rune("Wrath of the Berserker", rune_, False, *self.sets(Wrath_of_the_Wastes=6))
        # all Whirlwind and Rend damage x101 at six pieces, with the 2-piece's 500% beside it as a multiplier of its own
        for worn in range(0, 7):
            s = self.sets(Wrath_of_the_Wastes=worn)
            out += [(T("clear"), None), (T("factor", "Whirlwind", "damage_increase_pct", *s), "%g" % (big if worn >= 6 else 1)),
                    (T("factor", "Rend", "damage_increase_pct", *s), "%g" % ((rend2 if worn >= 2 else 1) * (big if worn >= 6 else 1))),
                    (T("factor", "Frenzy", "damage_increase_pct", *s), "1")]

        # Mortick's Brace: all five runes of Wrath of the Berserker while it is worn, none of another skill's, nothing when not worn
        for rune in wrath_runes():
            out += want_rune("Wrath of the Berserker", rune, True, wears=(MORTICK,))
            out += want_rune("Wrath of the Berserker", rune, False)
        out += want_rune("Whirlwind", rune_, False, wears=(MORTICK,))
        out += want_rune("Rend", "Mutilate", False, wears=(MORTICK,))
        out += want_rune("Wrath of the Berserker", "Not A Rune", True, wears=(MORTICK,))     # `all` means every name the caller asks for
        out += want_rune("Wrath of the Berserker", "Insanity", True, *self.sets(Other_Set=2), wears=(MORTICK, "Someone_Else"))
        out += want_rune("Wrath of the Berserker", "Insanity", False, wears=("Someone_Else", AMBO, LAMENTATION))

        # Ambo's Pride: the whole damage in the time it says, never longer than the skill's own; every Rend, not only the applied one
        for base in (15, 5, 3, 1, 0.5):
            out += [(T("clear"), None), (T("lowest", "Rend", "dot_payout_seconds", base, *none), "%g" % base),
                    (T("wears", AMBO, 0), None), (T("lowest", "Rend", "dot_payout_seconds", base, *none), "%g" % min(base, 1.0))]
        out += [(T("clear"), None), (T("wears", AMBO, 0), None), (T("lowest", "Whirlwind", "dot_payout_seconds", 5, *none), "5"),
                (T("lowest", "Rend", "dot_duration_seconds", 5, *none), "5"), (T("setto", "Rend", "dot_payout_seconds", 0.5, *none), "1")]   # another skill, another stat
        # the hit event: a hit of Whirlwind applies Rend; a hit of another skill, another event or an item not worn does not
        apply_ = "apply_skill(Rend)=1;"
        out += [(T("clear"), None), (T("now", 10), None), (T("fire", "hit", "Whirlwind", 0.13, 99, *none), ""),
                (T("wears", AMBO, 0), None), (T("fire", "hit", "Whirlwind", 0.13, 99, *none), apply_),
                (T("fire", "hit", "Whirlwind", 0, 99, *none), apply_),                      # a certain effect needs no proc coefficient
                (T("fire", "hit", "Whirlwind", 1, 0, *none), apply_),                       # and fires on every hit: no internal cooldown
                (T("fire", "hit", "Rend", 1, 0, *none), ""), (T("fire", "hit", "Frenzy", 1, 0, *none), ""),
                (T("fire", "hit_spender", "Whirlwind", 1, 0, *none), ""), (T("fire", "cast", "Whirlwind", 1, 0, *none), ""),
                (T("fire", "kill", "", 1, 0, *none), "")]

        # Lamentation: 2 stacks, and +[100-150]% on Rend at the item's stored roll
        out += [(T("clear"), None), (T("setto", "Rend", "dot_max_stacks", 1, *none), "1"),
                (T("wears", LAMENTATION, 0), None), (T("setto", "Rend", "dot_max_stacks", 1, *none), "2"),
                (T("setto", "Whirlwind", "dot_max_stacks", 1, *none), "1")]
        for roll in (100, 123, 150):
            out += [(T("clear"), None), (T("wears", LAMENTATION, 0), None), (T("value", LAMENTATION, "Rend", "damage_increase_pct", roll), None),
                    (T("factor", "Rend", "damage_increase_pct", *none), "%g" % (1 + roll / 100))]
        out += [(T("clear"), None), (T("wears", LAMENTATION, 0), None), (T("factor", "Rend", "damage_increase_pct", *none), "1"),     # no stored roll, no power
                (T("value", LAMENTATION, "Rend", "damage_increase_pct", 150), None),
                (T("factor", "Rend", "damage_increase_pct", *self.sets(Wrath_of_the_Wastes=6)), "%g" % (2.5 * rend2 * big)),        # the multipliers multiply
                (T("factor", "Whirlwind", "damage_increase_pct", *self.sets(Wrath_of_the_Wastes=6)), "%g" % big)]

        # Ticks: whole seconds, at least one
        out += [(T("ticks", s), "%d" % want) for s, want in ((0.2, 1), (1, 1), (4.5, 5), (5, 5), (14.6, 15), (15, 15), (15.4, 15))]

        # a bleed alone pays what the 5-tick bleed paid before: floor(total n / 5) minus floor(total (n-1) / 5)
        legacy = lambda total, base, n: math.floor(total * n / base) - math.floor(total * (n - 1) / base)  # noqa: E731
        for total, length in ((1003, 5), (1003, 15), (7, 15), (123456.5, 15), (1003, 3)):
            out += [(T("stacks", "clear"), None), (T("stacks", "add", total, 5, length, length, 0, 1), None), (T("stacks", "end"), "%d" % length)]
            out += [(T("stacks", "tick", n), "%g" % (legacy(total, 5, n) if 1 <= n <= length else 0)) for n in range(0, length + 3)]
        # dealt over one tick: all the damage of its length at once, then nothing
        for total, length in ((1003, 5), (1003, 15), (7, 15), (123456.5, 15)):
            whole = math.floor(total * length / 5)
            out += [(T("stacks", "clear"), None), (T("stacks", "add", total, 5, length, 1, 0, 1), None), (T("stacks", "end"), "1"),
                    (T("stacks", "tick", 0), "0"), (T("stacks", "tick", 1), "%g" % whole), (T("stacks", "tick", 2), "0"), (T("stacks", "tick", 15), "0")]
        # dealt over three ticks of fifteen: the whole of the fifteen, in thirds
        total, whole = 1003, math.floor(1003 * 15 / 5)
        out += [(T("stacks", "clear"), None), (T("stacks", "add", total, 5, 15, 3, 0, 1), None), (T("stacks", "end"), "3")]
        out += [(T("stacks", "tick", n), "%g" % ((math.floor(whole * n / 3) - math.floor(whole * (n - 1) / 3)) if n <= 3 else 0)) for n in (1, 2, 3, 4)]

        # two bleeds on one aura (cap 2): the second begins after the aura's tick it was applied on; both tick; the aura lasts for both
        out += [(T("stacks", "clear"), None), (T("stacks", "add", 1000, 5, 5, 5, 0, 2), None), (T("stacks", "add", 500, 5, 5, 5, 2, 2), None),
                (T("stacks", "count"), "2"), (T("stacks", "end"), "7"), (T("stacks", "starts"), "0;2;")]
        out += [(T("stacks", "tick", n), "%g" % (legacy(1000, 5, n) * (1 <= n <= 5) + legacy(500, 5, n - 2) * (3 <= n <= 7))) for n in range(0, 9)]
        # a third replaces the oldest (the cap is 2)
        out += [(T("stacks", "add", 2000, 5, 5, 5, 4, 2), None), (T("stacks", "count"), "2"), (T("stacks", "starts"), "2;4;"), (T("stacks", "end"), "9")]
        out += [(T("stacks", "tick", 3), "%g" % legacy(500, 5, 1)), (T("stacks", "tick", 5), "%g" % (legacy(500, 5, 3) + legacy(2000, 5, 1)))]
        # with no stacking power the cap is 1: a new bleed replaces the one that runs
        out += [(T("stacks", "clear"), None), (T("stacks", "add", 1000, 5, 5, 5, 0, 1), None), (T("stacks", "add", 500, 5, 5, 5, 2, 1), None),
                (T("stacks", "count"), "1"), (T("stacks", "starts"), "2;"), (T("stacks", "tick", 1), "0"), (T("stacks", "tick", 3), "%g" % legacy(500, 5, 1))]
        # a compressed bleed beside a long one (Ambo's with the 2-piece, then a plain one): each is paid by its own rule
        out += [(T("stacks", "clear"), None), (T("stacks", "add", 1000, 5, 15, 1, 0, 2), None), (T("stacks", "add", 1000, 5, 5, 5, 0, 2), None),
                (T("stacks", "tick", 1), "%g" % (3000 + legacy(1000, 5, 1))), (T("stacks", "tick", 2), "%g" % legacy(1000, 5, 2)), (T("stacks", "end"), "5")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_sources(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 150)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "lowest_takes_the_highest": real.replace("            if (value < base)\n                base = value;\n        return base;\n    }\n\n    // Whether a rune",
                                                     "            if (value > base)\n                base = value;\n        return base;\n    }\n\n    // Whether a rune"),
            "lowest_ignores_the_base": real.replace("            if (value < base)\n                base = value;\n        return base;\n    }\n\n    // Whether a rune",
                                                    "            base = value;\n        return base;\n    }\n\n    // Whether a rune"),
            "all_is_not_a_grant": real.replace(' ||\n               !ActiveValues(rows, counts, "rune", skill, "all", situation).empty();', ";"),
            "a_named_rune_is_not_a_grant": real.replace('return !ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||', "return false ||"),
            "a_grant_of_any_skill": real.replace('ActiveValues(rows, counts, "rune", skill, "all", situation)', 'ActiveValues(rows, counts, "rune", "Wrath of the Berserker", "all", situation)'),
            "a_grant_ignores_the_set_count": real.replace("if (worn == counts.end() || worn->second < row.pieces)\n                return false;", ""),
            "ticks_round_down": real.replace("static_cast<unsigned>(std::lround(seconds))", "static_cast<unsigned>(seconds)"),
            "ticks_can_be_none": real.replace("return seconds < 1.0 ? 1u :", "return seconds < 0.0 ? 1u :"),
            "a_bleed_starts_with_its_own_tick": real.replace("if (tick <= stack.start || tick > stack.start + stack.payTicks)", "if (tick < stack.start || tick > stack.start + stack.payTicks)"),
            "a_bleed_runs_one_tick_long": real.replace("tick > stack.start + stack.payTicks)", "tick > stack.start + stack.payTicks + 1)"),
            "a_bleed_ends_a_tick_early": real.replace("tick > stack.start + stack.payTicks)", "tick >= stack.start + stack.payTicks)"),
            "a_compressed_bleed_pays_its_own_length_only": real.replace("stack.total * stack.lengthTicks / stack.baseTicks, stack.payTicks, n", "stack.total, stack.payTicks, n"),
            "a_compressed_bleed_is_paid_in_full_ticks": real.replace("if (stack.payTicks == stack.lengthTicks)", "if (true)"),
            "only_the_first_bleed_ticks": real.replace("for (BleedStack const& stack : stacks)\n            sum += StackTick(stack, tick);", "for (BleedStack const& stack : stacks)\n        {\n            sum += StackTick(stack, tick);\n            break;\n        }"),
            "the_aura_ends_with_the_first_bleed": real.replace("end = std::max(end, stack.start + stack.payTicks);", "end = end ? end : stack.start + stack.payTicks;"),
            "the_aura_ends_with_the_shortest": real.replace("end = std::max(end, stack.start + stack.payTicks);", "end = end ? std::min(end, stack.start + stack.payTicks) : stack.start + stack.payTicks;"),
            "the_cap_is_not_held": real.replace("while (!stacks.empty() && stacks.size() >= (cap ? cap : 1))", "while (false)"),
            "the_newest_is_dropped": real.replace("return a.start < b.start;", "return a.start > b.start;"),
            "a_cap_of_one_stacks": real.replace("(cap ? cap : 1)", "(cap + 1)"),
            "the_hit_event_ignores_the_skill": real.replace("!row.fireSkills.empty() && std::find", "false && std::find"),
            "the_applied_skill_is_not_returned": real.replace("out.push_back({row.stat, number, row.skill, &row});", "out.push_back({row.stat, number, \"\", &row});"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

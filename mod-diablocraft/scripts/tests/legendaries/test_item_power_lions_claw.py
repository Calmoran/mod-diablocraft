"""Legendary rest, bead diablocraft-xureo: Lion's Claw (Monk fist weapon, list row 240, K1).

  "Seven-Sided Strike performs an additional 7 strikes."
  * the text and number are read from d3planner (item_onehand.js, leg_lionsclaw, args 0: the 7 is in the text) and the catalogue row; the table
    (data/legendary_powers.csv) holds ONE `skill` row for the pool item P1_fistWeapon_norm_unique_01: Seven-Sided Strike, `extra_strikes` 7 (fixed);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses
    a bad `extra_strikes` row;
  * the production rules are compiled and driven with the generated row: SkillSetTo (dc_item_power_math.h) gives the 7 only while the item is
    worn, and SevenSided::Strikes (dc_monk_seven_sided_strike.h) then lands 14 strikes instead of 7, each still the skill's total over its sheet
    count of 7, so a cast deals twice the damage;
  * mutants of the row, the rules and the header fail the same driver; source-text guards that Start reads the extra once, through SkillSetTo, and
    that nothing else changes the strike's size (BasePct) or the series' length. The C++ is compile-checked by syntax_check.sh and the in-game steps
    are in docs/test-diablocraft-xureo.md.
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
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
STRIKE_H = SRC / "classes/monk/dc_monk_seven_sided_strike.h"
STRIKE_CPP = SRC / "classes/monk/dc_monk_seven_sided_strike.cpp"
HARNESS = MODULE / "tests/item_power_lions_claw/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P1_fistWeapon_norm_unique_01"
SKILL = "Seven-Sided Strike"
STAT = "extra_strikes"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
TEXT = re.compile(r'custom: \{id: "leg_lionsclaw", name: "Extra Seven-Sided Strike Attacks", format: "Seven-Sided Strike performs an additional (\d+) strikes\.", args: 0\}')
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def words():
    """The strikes the item adds, from d3planner's item."""
    found = TEXT.findall((REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8"))
    assert len(found) == 1, found
    return float(found[0])


def sheet(token):
    found = {r["value"] for r in read_csv("data/d3/monk_skill_values.csv") if r["skill"] == SKILL and r["rune"] == "" and r["token"] == token}
    assert len(found) == 1, found
    return float(found.pop())


class Table(unittest.TestCase):
    def test_the_sources_say_seven_more_strikes(self):
        self.assertEqual(7.0, words())
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Seven-Sided Strike performs an additional 7 strikes.", catalogue[0]["power_text"])
        self.assertEqual((7.0, 5677.0), (sheet("hit_count"), sheet("damage_pct")))

    def test_one_row_on_seven_sided_strike(self):
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, words(), words(), *BLANK)], mine())

    def test_the_tooltip_says_it(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertEqual("Seven-Sided Strike performs an additional 7 strikes.", m[1])

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0064_table.sql")


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "7", "value_max": "7", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="lionsclaw-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if not (r["owner"] == OWNER and r["stat"] == STAT)]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        refused = {
            "a range": ({"value_min": "6", "value_max": "7"}, "extra_strikes is one whole number"),
            "a part strike": ({"value_min": "1.5", "value_max": "1.5"}, "extra_strikes is one whole number"),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min|extra_strikes is one whole number"),
            "another skill": ({"skill": "Fists of Thunder"}, "extra_strikes is one whole number"),
            "not a skill": ({"skill": "Seven-Sided Strikes"}, "is not a skill"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, "extra_strikes is one whole number"),
            "an event": ({"fire_on": "cast", "fire_skills": SKILL}, "an event fires|extra_strikes is one whole number"),
            "a set bonus": ({"pieces": "2"}, "not a set|extra_strikes is one whole number"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, strike_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text, "classes/monk/dc_monk_seven_sided_strike.h": strike_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemlionsclaw-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        count, total, extra = sheet("hit_count"), sheet("damage_pct"), words()
        each = "%.10g" % (total / count)
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: the sheet's 7 strikes of a seventh of the total
        out += clear + [(T("setto", SKILL, STAT, 0), "0"), (T("strikes", count, total), "%d %s" % (count, each))]
        # worn: 7 more, 14 in all, each the same size
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 0), "%g" % extra), (T("strikes", count, total), "%d %s" % (count + extra, each))]
        out += [(T("strikes", 1, 100), "%d 100" % (1 + extra)), (T("strikes", 0, 100), "%d 0" % extra)]
        # only Seven-Sided Strike's `extra_strikes`
        for other in ("Fists of Thunder", "Seven-Sided Strikes", "seven-sided strike", ""):
            out += [(T("setto", other, STAT, 0), "0")]
        for other in ("hit_count", "damage_increase_pct", "extra_strike", ""):
            out += [(T("setto", SKILL, other, 0), "0")]
        # another owner's item does nothing
        out += clear + [(T("wears", "Other Fist"), None), (T("setto", SKILL, STAT, 0), "0"), (T("strikes", count, total), "%d %s" % (count, each))]
        return out

    def drive(self, math_text, strike_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(math_text, strike_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), STRIKE_H.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 10)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real, strike = MATH.read_text(encoding="utf-8"), STRIKE_H.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, strike, rows, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Fists of Thunder",) + r[4:] for r in rows],
            "six_strikes": [r[:5] + (6.0, 6.0) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("hit_count",) + r[5:] for r in rows],
            "no_row": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, strike, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double SkillSetTo("):]
        body = body[:body.index("\n    }\n") + 7]
        for name, (old, new) in {"never_raises": ("if (value > base)", "if (value < base)"),
                                 "reads_the_player_rows": ('"skill", skill, stat', '"player", skill, stat')}.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), strike, rows, name)
                self.assertNotEqual(want, got, name + " survived")
        count = strike[strike.index("inline unsigned Strikes("):]
        count = count[:count.index("\n    }\n") + 7]
        sums = "static_cast<unsigned>(std::floor(std::max(0.0, sheetCount))) + static_cast<unsigned>(std::floor(std::max(0.0, extra)))"
        for name, new in {"the_extra_ignored": "static_cast<unsigned>(std::floor(std::max(0.0, sheetCount)))",
                          "the_extra_replaces": "static_cast<unsigned>(std::floor(std::max(std::max(0.0, sheetCount), extra)))",
                          "the_extra_doubles_the_sheet": "static_cast<unsigned>(std::floor(std::max(0.0, sheetCount))) * 2",
                          "one_short": sums + " - 1"}.items():
            with self.subTest(mutant=name):
                self.assertIn(sums, count, name + " does not apply")
                _, got = self.drive(real, strike.replace(count, count.replace(sums, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        pct = strike[strike.index("inline double StrikePct("):]
        pct = pct[:pct.index("\n    }\n") + 7]
        with self.subTest(mutant="the_strike_shrinks_with_the_extra"):
            mutated = strike.replace(pct, pct.replace("totalPct / std::floor(strikes)", "totalPct / (std::floor(strikes) + 7)", 1))
            self.assertNotEqual(strike, mutated)
            _, got = self.drive(real, mutated, rows, "shrinks")
            self.assertNotEqual(want, got, "the_strike_shrinks_with_the_extra survived")


def reader_failures(text):
    """What is wrong with Start's reading of the extra strikes in `text` ([] when it is right)."""
    wrong = []
    start = text[text.index("bool Start("):]

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the item powers are included", '#include "../../combat/dc_item_powers.h"' in text)
    need("the series' length is the sheet's count plus the item's extra",
         'series->count = Strikes(Numbers::Num(spellId, "hit_count"),\n                                ItemPowers::SkillSetTo(player, std::string(Skill), "extra_strikes", 0));' in start)
    need("the strikes are queued from the series' count", "for (unsigned i = 0; i < series->count; ++i)" in start)
    need("a strike's size does not read the extra", 'return StrikePct(Numbers::Num(source, "damage_pct"), Numbers::Num(spellId, "hit_count"));' in text)
    need("the extra is read in one place", text.count("extra_strikes") == 1)
    return wrong


class Hooks(unittest.TestCase):
    def test_start_reads_the_extra_strikes(self):
        self.assertEqual([], reader_failures(STRIKE_CPP.read_text(encoding="utf-8")))

    def test_the_monk_name_stays_in_the_monks_folder(self):
        for path in (SRC / "combat").rglob("*"):
            if path.suffix in (".cpp", ".h") and path.name != "dc_spell_shells.h":
                self.assertNotIn("extra_strikes", path.read_text(encoding="utf-8", errors="replace"), path)

    def test_the_source_guards_fail_their_mutants(self):
        real = STRIKE_CPP.read_text(encoding="utf-8")
        mutants = {
            "no_extra": ('ItemPowers::SkillSetTo(player, std::string(Skill), "extra_strikes", 0)', "0.0"),
            "wrong_base": ('"extra_strikes", 0)', '"extra_strikes", 7)'),
            "another_stat": ('"extra_strikes"', '"hit_count"'),
            "no_include": ('#include "../../combat/dc_item_powers.h"\n', ""),
            "the_size_reads_it": ('return StrikePct(Numbers::Num(source, "damage_pct"), Numbers::Num(spellId, "hit_count"));',
                                  'return StrikePct(Numbers::Num(source, "damage_pct"), Numbers::Num(spellId, "hit_count") + 7);'),
            "the_loop_ignores_the_count": ("for (unsigned i = 0; i < series->count; ++i)", "for (unsigned i = 0; i < 7; ++i)"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], reader_failures(real.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()

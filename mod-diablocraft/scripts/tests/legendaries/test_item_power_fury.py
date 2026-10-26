"""Fury of the Ancients (diablocraft-tab0h, legendary build 2 bead 4): Call of the Ancients gains the effect of the Ancients' Fury rune, and
the Ancients attack 100% faster.

  * data/legendary_powers.csv gains its two rows: `rune` Call of the Ancients / Ancients' Fury (given without choosing it, as Mortick's
    Brace) and `skill` Call of the Ancients `summon_attack_speed_pct` 100, a stat only the Ancients read; the words and the 100 are read from
    d3planner's item file and set against the tooltip; the generator refuses the summon stat on a skill whose summons do not read it;
  * the production rules (dc_item_power_math.h GrantsRune and SkillFactor) are driven with the generated rows through the k4 harness, and
    their mutants fail the same driver;
  * source-text guards that the Ancients take Ancients' Fury's own Fury number whatever rune summoned them, swing at the owner's attacks per
    second times the summon factor, and that the player's own cast reads the other stat (they prove the calls are there, not that they run;
    the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-tab0h.md).
"""
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import test_item_power_math as power_math  # noqa: E402  (modules, so their test classes are not run twice)
import test_item_power_k4 as k4  # noqa: E402
from test_item_power_math import GENERATED, generator, planner, read_csv  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
FURY, MORTICK = "P67_Unique_Shoulder_102", "P2_Unique_Bracer_003"
COTA, RUNE = "Call of the Ancients", "Ancients' Fury"
RUNES = ("The Council Rises", "Duty to the Clan", "Ancients' Fury", "Together as One", "Ancients' Blessing")


Q = r"'((?:[^']|'')*)'"   # a quoted SQL string: "Ancients'' Fury" is one (power_math's pattern stops at the doubled quote)
ROW = re.compile(r"\(%s,(\d+),%s,%s,%s,(-?[\d.]+),(-?[\d.]+),%s,([\d.]+),%s,([\d.]+),(\d+),%s,%s,([\d.]+),([\d.]+)\)" % ((Q,) * 4 + (Q,) * 2 + (Q,) * 2))


def all_rows():
    u = lambda text: text.replace("''", "'")  # noqa: E731
    return [(u(m[1]), int(m[2]), u(m[3]), u(m[4]), u(m[5]), float(m[6]), float(m[7]), u(m[8]), float(m[9]), u(m[10]), float(m[11]), int(m[12]),
             u(m[13]), u(m[14]), float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def tooltip(d3_id):
    """The power text the players see (dc_item_tooltip, generate_crafting.py), its doubled quotes read as one."""
    m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s',%s,%s" % (re.escape(d3_id), Q, Q),
                  (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
    assert m, d3_id
    return m[2].replace("''", "'")


def source():
    text = planner("item_shoulders.js", FURY)
    found = re.search(r"format: \"Call of the Ancients gains the effect of the Ancients' Fury rune, and your Ancients attack (\d+)%% faster.\", "
                      r"args: 0\}", text)
    assert found, text
    return float(found[1])


class Table(unittest.TestCase):
    def test_the_rows_are_the_sources(self):
        faster = source()
        self.assertEqual(100, faster)
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(FURY, 0, "rune", COTA, RUNE, 1.0, 1.0, *blank),
                          (FURY, 0, "skill", COTA, "summon_attack_speed_pct", faster, faster, *blank)},
                         {r for r in all_rows() if r[0] == FURY})
        self.assertIn("your Ancients attack %g%% faster." % faster, tooltip(FURY))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == FURY)
        self.assertEqual(("Fury of the Ancients", "yes", "barbarian"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))
        # the rune and its number exist: the Fury each Ancient's damage gives
        self.assertEqual(set(RUNES), {r["rune_name"] for r in read_csv("data/d3/barbarian_runes.csv") if r["skill_name"] == COTA})
        gain = [r for r in read_csv("data/d3/barbarian_skill_values.csv") if (r["skill"], r["rune"], r["token"]) == (COTA, RUNE, "gain_resource")]
        self.assertEqual(1, len(gain))
        self.assertGreater(float(gain[0]["value"]), 0)

    def test_the_generator_refuses_a_summon_speed_nothing_reads(self):
        base = {"owner": FURY, "pieces": "", "kind": "skill", "skill": COTA, "stat": "summon_attack_speed_pct", "value_min": "100", "value_max": "100",
                "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                "icd_seconds": "", "source": "x", "note": ""}
        for name, row in {"a skill with no summons": dict(base, skill="Hammer of the Ancients"),
                          "on the player": dict(base, kind="player", skill=""),
                          "a rune that is not one": dict(base, kind="rune", stat="Not A Rune", value_min="1", value_max="1")}.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([base])))
        self.assertEqual(("Call of the Ancients",), generator.SUMMON_SKILLS)


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        faster = 1 + source() / 100
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        # not worn: nothing given, the Ancients at the owner's speed
        out += clear + [(T("rune", COTA, rune, 0), "0") for rune in RUNES]
        out += [(T("factor", COTA, "summon_attack_speed_pct", 0), "1")]
        # worn: Ancients' Fury given and no other rune; the Ancients twice as fast; the player's own cast of the skill is not
        out += clear + [(T("wears", FURY, 0), None)]
        out += [(T("rune", COTA, rune, 0), "1" if rune == RUNE else "0") for rune in RUNES]
        out += [(T("rune", "Wrath of the Berserker", RUNE, 0), "0"),
                (T("factor", COTA, "summon_attack_speed_pct", 0), "%g" % faster),
                (T("factor", COTA, "attack_speed_pct", 0), "1"),
                (T("factor", "Hammer of the Ancients", "summon_attack_speed_pct", 0), "1")]
        # with Mortick's Brace (every rune of Wrath of the Berserker): each gives its own skill's runes only
        out += clear + [(T("wears", FURY, 0), None), (T("wears", MORTICK, 0), None),
                        (T("rune", "Wrath of the Berserker", "Insanity", 0), "1"), (T("rune", COTA, "The Council Rises", 0), "0"),
                        (T("rune", COTA, RUNE, 0), "1")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k4.Rules.build(header_text, "fury-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 15)
        self.assertEqual(GENERATED.read_text(encoding="utf-8").count("\n("), len(all_rows()))     # every generated row parsed
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        factor = 'for (double pct : ActiveValues(rows, counts, "skill", skill, stat, situation))\n            factor *= 1.0 + pct / 100.0;'
        mutants = {
            "every_rune_is_given": real.replace('!ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||',
                                                '!ActiveValues(rows, counts, "rune", skill, "Ancients\' Fury", situation).empty() ||'),
            "the_stat_is_ignored": real.replace(factor, factor.replace("skill, stat, situation", 'skill, "summon_attack_speed_pct", situation')),
            "the_skill_is_ignored": real.replace(factor, factor.replace("skill, stat, situation", '"Call of the Ancients", stat, situation')),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

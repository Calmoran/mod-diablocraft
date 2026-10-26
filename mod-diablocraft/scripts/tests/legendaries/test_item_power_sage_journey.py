"""Legendary rest, bead diablocraft-xlpqw: the Sage's Journey 3-piece bonus, "Double the amount of Death's Breath that drop."

  * the table (data/legendary_powers.csv) holds one `player` `deaths_breath_pct` row at pieces 3, its number read apart from the table
    out of the set text (reference/d3planner/data_itemsets.js: "Double" is +100%, a factor of 2); the owner is a four-piece set whose
    pieces are craft-only (they never drop, the Blacksmith makes them);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: PlayerFactor, BonusActive) are compiled and driven with the generated row:
    x1 with 0, 1 and 2 pieces, x2 from the 3rd piece, no other stat moves, another set's count does not switch it on;
  * mutants of each rule fail the same driver;
  * source-text guards that the loot roll grants Death's Breath through the one reader ItemPowers::DeathsBreathFactor, the count it
    grants is that factor (never fewer than the one), and the reader is the player factor of the table's stat (the C++ is
    compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-xlpqw.md).
"""
import re
import shutil
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import harness_env
import test_item_power_might_of_the_earth as mote  # a module, so its test classes are not run twice
from test_item_power_might_of_the_earth import GENERATED, SRC, MATH, REPO, generator, read_csv

MODULE = Path(__file__).resolve().parents[3]
SET = "Sage's Journey"
STAT = "deaths_breath_pct"
LOOT = SRC / "loot/dc_loot.cpp"
POWERS_CPP = item_powers_source.CPP
POWERS_H = SRC / "combat/dc_item_powers.h"
TEXT = "Double the amount of Death's Breath that drop."
# the generated row, the owner read with its doubled quote (the set's name has an apostrophe)
ROW = re.compile(mote.ROW.pattern.replace("\\('([^']*)'", "\\('((?:[^']|'')*)'", 1))


def source():
    """The percent the set text gives: 'Double' is +100%. Read from d3planner's set data, the catalogue's source rule for set bonuses."""
    planner = (REPO / "reference/d3planner/data_itemsets.js").read_text(encoding="utf-8")
    assert planner.count('{format: "%s"}' % TEXT) == 1, "the 3-piece text is not in d3planner's set data once"
    return 100.0


def mine():
    text = GENERATED.read_text(encoding="utf-8")
    return [(m[1].replace("''", "'"), int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7])) for m in ROW.finditer(text)
            if m[1].replace("''", "'") == SET and m[2] == "3"]


def row_problems(rows, pct):
    want = [(SET, 3, "player", "", STAT, pct, pct)]
    return [] if rows == want else ["rows %r are not %r" % (rows, want)]


class Table(unittest.TestCase):
    def test_the_row_is_the_set_texts_double(self):
        self.assertEqual([], row_problems(mine(), source()))
        for name, rows in {"half": [(SET, 3, "player", "", STAT, 50.0, 50.0)], "another stat": [(SET, 3, "player", "", "damage_dealt_pct", 100.0, 100.0)],
                           "another level": [(SET, 2, "player", "", STAT, 100.0, 100.0)], "another kind": [(SET, 3, "skill", "", STAT, 100.0, 100.0)],
                           "no row": []}.items():
            self.assertTrue(row_problems(rows, source()), name)

    def test_the_owner_is_the_four_piece_craft_only_set(self):
        pieces = [r for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET]
        self.assertEqual(4, len(pieces))
        self.assertEqual({"yes"}, {r["craft_only"] for r in pieces})

    def test_the_row_has_its_source(self):
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == SET and r["pieces"] == "3")
        self.assertIn("data_itemsets.js:271", row["source"])
        self.assertIn(TEXT, row["source"])
        self.assertTrue(row["note"])

    def test_the_sql_row_and_the_stat_vocabulary(self):
        sql = generator.render()
        self.assertIn("('%s',3,'player','','%s',100,100,'',0,'',0,0,'','',100,0)" % (SET, STAT), sql.replace("Journey''s", "Journey's").replace("Sage''s", "Sage's"))
        self.assertIn(STAT, generator.PLAYER_STATS)
        self.assertIn(STAT, generator.POSITIVE_PLAYER_STATS)     # a factor below the one would shrink the drop: the generator refuses it


class Rules(unittest.TestCase):
    def cases(self, rows):
        pct = source()
        out = [("\t".join(["row", *map(str, (r[0], r[1], r[2], r[3], r[4], "%g" % r[5], "%g" % r[6]))]), None) for r in mine()]
        if rows is not None:
            out = [("\t".join(["row", *map(str, (r[0], r[1], r[2], r[3], r[4], "%g" % r[5], "%g" % r[6]))]), None) for r in rows]
        for n in range(0, 6):      # the four pieces (and past them: a fifth cannot exist, the count must not break)
            out.append(("player\t%s\t1\t%s\t%d" % (STAT, SET, n), "%g" % (1 + pct / 100 if n >= 3 else 1)))
            out.append(("active\t%s\t3\t%d" % (SET, n), "1" if n >= 3 else "0"))
            out.append(("active\t%s\t2\t%d" % (SET, n), "0"))       # the 2-piece (all four stats) is a sheet stat, no row here
            out.append(("player\tdamage_dealt_pct\t1\t%s\t%d" % (SET, n), "1"))     # no other stat moves
        out.append(("player\t%s\t1\tOther Set\t4" % STAT, "1"))     # another set's count does not switch it on
        out.append(("player\t%s\t0" % STAT, "1"))                   # nothing worn
        out.append(("player\t%s\t2\t%s\t3\tOther Set\t6" % (STAT, SET), "2"))
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = mote.Rules.build(header_text, "sage-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_set_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), None, "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        factor = "factor *= 1.0 + pct / 100.0;"
        level = "if (worn < pieces || !pieces)"
        self.assertIn(level, real)
        start = real.index("inline double PlayerFactor(")
        end = real.index("}", real.index("return factor;", start))
        player = real[start:end]
        self.assertIn(factor, player)
        base = [(SET, 3, "player", "", STAT, 100.0, 100.0)]
        mutants = {
            "factor_is_not_one_plus_n": (real[:start] + player.replace(factor, "factor *= pct / 100.0;") + real[end:], base),
            "level_needs_one_more": (real.replace(level, "if (worn <= pieces || !pieces)"), base),
            "the_number_halved": (real, [(SET, 3, "player", "", STAT, 50.0, 50.0)]),
            "the_level_is_two": (real, [(SET, 2, "player", "", STAT, 100.0, 100.0)]),
            "the_stat_is_damage": (real, [(SET, 3, "player", "", "damage_dealt_pct", 100.0, 100.0)]),
            "no_row": (real, []),
        }
        for name, (header, rows) in mutants.items():
            if header is not real:
                self.assertNotEqual(real, header, name + " did not apply")
            with self.subTest(mutant=name):
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


READ = 'double DeathsBreathFactor(Player const* player)\n    {\n        return PlayerFactor(player, "%s");' % STAT
GRANT = "std::max(1u, static_cast<unsigned>(std::lround(DC::Combat::ItemPowers::DeathsBreathFactor(player))))"


def loot_problems(loot, powers, header):
    """What is wrong with the places the factor is read: the guards a mutant of the source must trigger."""
    bad = []
    if "double DeathsBreathFactor(Player const*);" not in header:
        bad.append("the header does not declare DeathsBreathFactor")
    if READ not in powers:
        bad.append("DeathsBreathFactor does not read " + STAT)
    if '#include "../combat/dc_item_powers.h"' not in loot:
        bad.append("the loot roll does not include the item powers")
    if "unsigned const deathsBreathCount = deathsBreath\n        ? " + GRANT + " : 0;" not in loot:
        bad.append("the count is not the factor, at least one, and none when nothing dropped")
    if "GrantMaterial(player, Currencies[DeathsBreath].entry, deathsBreathCount)" not in loot:
        bad.append("the grant does not pay the count")
    if "result.deathsBreath = deathsBreathCount;" not in loot:
        bad.append("the result does not report the count")
    if loot.count("DeathsBreathFactor(") != 1:
        bad.append("the loot file calls the one reader not exactly once")
    if re.search(r"Currencies\[DeathsBreath\]\.entry,\s*1\b", loot):
        bad.append("a Death's Breath grant of a literal 1 is left")
    return bad


class Places(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loot = LOOT.read_text(encoding="utf-8")
        cls.powers = POWERS_CPP.read_text(encoding="utf-8")
        cls.header = POWERS_H.read_text(encoding="utf-8")

    def problems(self, **swap):
        return loot_problems(swap.get("loot", self.loot), swap.get("powers", self.powers), swap.get("header", self.header))

    def test_the_loot_roll_grants_through_the_one_reader(self):
        self.assertEqual([], self.problems())

    def test_nothing_in_the_reader_is_hardcoded(self):
        reader = self.powers[self.powers.index("double DeathsBreathFactor(Player const* player)"):]
        self.assertNotRegex(reader[:reader.index("}") + 1], r"\b(2|2\.0|100)\b")

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "the grant stays one": dict(loot=self.loot.replace("Currencies[DeathsBreath].entry, deathsBreathCount)", "Currencies[DeathsBreath].entry, 1)")),
            "the count skips the factor": dict(loot=self.loot.replace(GRANT, "1u")),
            "the count can be zero": dict(loot=self.loot.replace(GRANT, "static_cast<unsigned>(std::lround(DC::Combat::ItemPowers::DeathsBreathFactor(player)))")),
            "a count when nothing dropped": dict(loot=self.loot.replace("deathsBreath\n        ? " + GRANT + " : 0;", "true\n        ? " + GRANT + " : 0;")),
            "the result still says one": dict(loot=self.loot.replace("result.deathsBreath = deathsBreathCount;", "result.deathsBreath = 1;")),
            "the reader reads another stat": dict(powers=self.powers.replace('PlayerFactor(player, "%s")' % STAT, 'PlayerFactor(player, "damage_dealt_pct")')),
            "the reader is not declared": dict(header=self.header.replace("double DeathsBreathFactor(Player const*);", "")),
        }
        for name, swap in mutants.items():
            key = next(iter(swap))
            self.assertNotEqual({"loot": self.loot, "powers": self.powers, "header": self.header}[key], swap[key], "the %s mutation no longer applies" % name)
            self.assertTrue(self.problems(**swap), "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()

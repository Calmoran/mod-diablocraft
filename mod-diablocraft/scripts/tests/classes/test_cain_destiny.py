"""diablocraft-y3z8a: Cain's Destiny 3-piece, "when a Greater Rift Keystone drops, there is a 25% chance for an extra one to drop".

1. The row: data/legendary_powers.csv holds one `player` extra_keystone_pct row for the set's 3-piece, its number read back from
   d3planner's itemSets text (never typed in the test), and the generator renders it into the migration. The generator refuses the
   stat at zero or below, and the set name is the one the four craft-only pieces carry in base_items.csv.
2. The chance: the production power-table rule (dc_item_power_math.h PlayerFactor) is compiled and driven with the generated rows
   for 0 to 6 worn pieces, and dc_keystone_rule.h turns that factor into the extra keystone with a roll at, just under and just over
   the chance. Each rule runs again on a mutant that breaks it, and the harness must go red.
3. The wiring, pinned as text (not run: it needs a Player and a Guardian kill): one reader of the stat, one caller of the roll, after
   the Guardian's own keystone grant and under its own receipt; the Greater Rift refund path is not the caller.
"""
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import test_item_power_events as events
import test_item_power_math as power_math
from test_class_parity import SRC, mutate, run
from test_item_power_math import GENERATED, MIGRATION, generator, read_csv

MODULE = SRC.parent
REPO = MODULE.parent
SET = "Cain's Destiny"
STAT = "extra_keystone_pct"
RULE = (SRC / "loot/dc_keystone_rule.h").read_text(encoding="utf-8")
LOOT = (SRC / "loot/dc_loot.cpp").read_text(encoding="utf-8")
LOOT_H = (SRC / "loot/dc_loot.h").read_text(encoding="utf-8")
RIFT_AI = (SRC / "monsters/dc_monster_ai.cpp").read_text(encoding="utf-8")
GR_OPEN = (SRC / "rifts/dc_gr_open.cpp").read_text(encoding="utf-8")
POWERS = item_powers_source.CPP.read_text(encoding="utf-8")
POWERS_H = (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")
MATH = (SRC / "combat/dc_item_power_math.h").read_text(encoding="utf-8")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
# test_item_power_math.ROW stops at an escaped quote in the owner ("Cain''s Destiny"), so it drops every apostrophe set: the owner group takes ''.
ROW = re.compile(power_math.ROW.pattern.replace("\\('([^']*)'", "\\('((?:[^']|'')*)'", 1))


def all_rows():
    return [(m[1].replace("''", "'"), int(m[2]), *m.group(3, 4, 5), float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]),
             m[13], m[14], float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def source_pct():
    """The percent in d3planner's itemSets text for the set's 3-piece."""
    text = (REPO / "reference/d3planner/data_itemsets.js").read_text(encoding="utf-8")
    found = re.findall(r'format: "When a Greater Rift Keystone drops, there is a (\d+)%% chance for an extra one to drop\."', text)
    assert len(found) == 1, found
    return float(found[0])


class Table(unittest.TestCase):
    def test_the_row_is_the_sources_chance(self):
        n = source_pct()
        self.assertEqual(25, n)
        # The 3-piece is the keystone row; the 2-piece's stat rows are N-SETSTAT's (diablocraft-a13xy).
        rows = [r for r in all_rows() if r[0] == SET and r[1] == 3]
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual([(SET, 3, "player", "", STAT, n, n, *blank)], rows)

    def test_the_set_is_the_four_craft_only_pieces(self):
        pieces = [r for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET and r["pool_version"] == "yes"]
        self.assertEqual(4, len(pieces), pieces)
        self.assertEqual({"Cain's Travelers", "Cain's Scrivener", "Cain's Insight", "Cain's Habit"}, {p["d3_name"] for p in pieces})

    def test_generated_and_migration_are_what_the_generator_renders(self):
        self.assertEqual(generator.render(MODULE), GENERATED.read_text(encoding="utf-8"))
        self.assertEqual(generator.render(MODULE), MIGRATION.read_text(encoding="utf-8"))
        self.assertIn("('Cain''s Destiny',3,'player','','%s',25,25,'',0,'',0,0,'','',100,0)" % STAT, MIGRATION.read_text(encoding="utf-8"))
        self.assertIn(STAT, generator.PLAYER_STATS)
        self.assertIn(STAT, generator.POSITIVE_PLAYER_STATS)

    def test_the_generator_refuses_a_chance_it_cannot_read(self):
        base = {"owner": SET, "pieces": "3", "kind": "player", "skill": "", "stat": STAT, "value_min": "25", "value_max": "25", "cond": "",
                "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                "icd_seconds": "", "source": "x", "note": ""}
        for name, row in {"zero": dict(base, value_min="0", value_max="0"), "negative": dict(base, value_min="-25", value_max="-25")}.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([base])))


class Rules(unittest.TestCase):
    def factor_cases(self):
        """[(command line, expected output)] for the events harness: the keystone factor for 0 to 6 worn pieces of the set and of another."""
        out = [(T("row", *r), None) for r in all_rows()]
        for worn in range(7):
            out += [(T("player", STAT, "1", SET, worn), "1.25" if worn >= 3 else "1")]
        out += [(T("player", STAT, "1", "Crimson", 6), "1"), (T("player", STAT, "0"), "1")]
        out += [(T("player", "shield_potency_pct", "1", SET, 4), "1")]    # no other stat moves
        return out

    def drive_factor(self, header_text, name):
        work, binary = events.Rules.build(header_text, "cain-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in self.factor_cases()) + "\n")
            done = events.harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, done.returncode, done.stderr)
            return [w for _, w in self.factor_cases() if w is not None], done.stdout.split("\n")[:-1]
        finally:
            events.shutil.rmtree(work, ignore_errors=True)

    def test_three_pieces_give_the_sources_factor(self):
        want, got = self.drive_factor(MATH, "real")
        self.assertEqual(10, len(want))
        self.assertEqual(want, got)

    def test_the_power_table_mutants_fail_the_same_driver(self):
        start = MATH.index("inline double PlayerFactor(")
        end = MATH.index("}", MATH.index("return factor;", start))
        player = MATH[start:end]
        factor = "factor *= 1.0 + pct / 100.0;"
        self.assertIn(factor, player)
        worn = "if (worn == counts.end() || worn->second < row.pieces)"
        self.assertEqual(1, MATH.count(worn))
        mutants = {"factor_is_not_one_plus_n": MATH[:start] + player.replace(factor, "factor *= pct / 100.0;") + MATH[end:],
                   "two_pieces_are_enough": MATH.replace(worn, "if (worn == counts.end() || worn->second + 1 < row.pieces)"),
                   "any_count_is_enough": MATH.replace(worn, "if (worn == counts.end())")}
        for name, mutant in mutants.items():
            self.assertNotEqual(MATH, mutant, name)
            want, got = self.drive_factor(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)

    @staticmethod
    def harness(rule, body):
        return ("#include <cassert>\n" + rule + "\nusing namespace DC::Loot::Keystone;\nint main() {\n" + body + "\n    return 0;\n}\n")

    def both(self, body, old, new):
        ok, out = run(self.harness(RULE, body))
        self.assertTrue(ok, out)
        ok, out = run(self.harness(mutate(RULE, old, new), body))
        self.assertFalse(ok, "mutation survived: " + new)

    def test_one_extra_inside_the_chance_and_none_outside(self):
        n = source_pct()
        f = 1 + n / 100
        self.both("    double f = %r;\n    assert(Extra(f, 0.0) == 1);\n    assert(Extra(f, %r) == 1);\n    assert(Extra(f, %r) == 0);\n    assert(Extra(f, 0.999) == 0);"
                  % (f, n / 100 - 0.0001, n / 100 + 0.0001), "roll * 100.0 < (factor - 1.0) * 100.0 ? 1u : 0u",
                  "roll * 100.0 < (factor - 1.0) * 100.0 ? 2u : 0u")

    def test_the_chance_edge_is_exclusive(self):
        # a roll in [0, 1) lands on the edge with probability 0, but 25.0 must not read as inside: 25 of every 100 rolls win, not 26
        n = source_pct()
        self.both("    assert(Extra(%r, %r) == 0);" % (1 + n / 100, n / 100),
                  "roll * 100.0 < (factor - 1.0)", "roll * 100.0 <= (factor - 1.0)")

    def test_no_bonus_never_pays(self):
        self.both("    for (int i = 0; i < 100; ++i) assert(Extra(1.0, i / 100.0) == 0);",
                  "(factor - 1.0) * 100.0 ? 1u", "(factor) * 100.0 ? 1u")


class Wiring(unittest.TestCase):
    def test_one_reader_of_the_stat_and_the_roll_reads_it(self):
        self.assertIn('double KeystoneFactor(Player const* player)\n    {\n        return PlayerFactor(player, "%s");' % STAT, POWERS)
        self.assertIn("double KeystoneFactor(Player const*);", POWERS_H)
        self.assertEqual(1, POWERS.count(STAT))
        self.assertIn("return Keystone::Extra(DC::Combat::ItemPowers::KeystoneFactor(player), Roll());", LOOT)
        self.assertIn("unsigned ExtraKeystones(Player const* player);", LOOT_H)
        self.assertIn('#include "dc_keystone_rule.h"', LOOT)

    def test_the_guardian_payout_grants_the_extra_under_its_own_receipt(self):
        pay = RIFT_AI[RIFT_AI.index("bool PayGuardianMember("):RIFT_AI.index("bool RewardGuardian(")]
        first = pay.index("DC::Loot::GrantMaterial(member, KEYSTONE_ITEM, 1,")
        extra = pay.index("DC::Loot::ExtraKeystones(member)")
        shards = pay.index("GuardianShards(rift)")
        self.assertTrue(first < extra < shards, (first, extra, shards))
        grant = pay[extra:shards]
        self.assertIn("DC::Loot::GrantMaterial(member, KEYSTONE_ITEM, extra,", grant)
        self.assertIn('run + "keystone-extra:" + std::to_string(member->GetGUID().GetCounter())', grant)
        self.assertIn("PlayerEconomy::Fail();", grant)
        self.assertNotIn("keystone-extra", pay[:extra])

    def test_only_the_guardian_payout_rolls_it(self):
        callers = [p for p in (SRC.rglob("*.cpp")) if "ExtraKeystones(" in p.read_text(encoding="utf-8")]
        self.assertEqual(["dc_loot.cpp", "dc_monster_ai.cpp"], sorted(p.name for p in callers))
        self.assertNotIn("ExtraKeystones", GR_OPEN)   # the opening's refund gives back the Keystone it took, never an extra


if __name__ == "__main__":
    unittest.main()

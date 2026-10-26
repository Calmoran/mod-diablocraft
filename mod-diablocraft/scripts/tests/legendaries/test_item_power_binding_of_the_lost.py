"""Binding of the Lost (diablocraft-9ao0o, on Orb of Infinite Depth's N-STACKBUFF): each hit with Seven-Sided Strike grants [4-5]% damage
reduction for 7 seconds; the PM's D3 reading (decisions 1099218ab): one stack per hit, capped at 7 (a tunable), one 7 s timer refreshed by every hit.

  * data/legendary_powers.csv gains its rows: an `effect` stack_buff 1 fired on `hit` of Seven-Sided Strike (7 s, at most 7) and a `buff`
    damage_reduction_pct 4-5 rolled once per item; the numbers are d3planner's and the power file's, the cap the PM's;
  * the tunable monk.binding_of_the_lost_max_stacks (7) is the cap when set (ItemPowers StackCap), the row's stack_max otherwise;
  * the record 83556 of data/legendary_power_buffs.csv: a dummy that states no number (the roll is the item's), stacking to 7;
    generate_spells.py lets a rolled dummy go without its $s1 and nothing else;
  * the production rules (StackedFactor, now never under 0, and the stack fire) are driven with the generated rows through the events
    harness, and their mutants fail the same driver;
  * source-text guards that the cap is read where the stacks are added (the C++ is compile-checked by syntax_check.sh and the in-game
    steps are in docs/test-diablocraft-9ao0o.md).
"""
import csv
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_spells  # noqa: E402
import test_item_power_events as events  # noqa: E402  (modules, so their test classes are not run twice)
import test_spell_records as records  # noqa: E402
from test_item_power_math import planner, read_csv, tooltip, all_rows  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
BELT, ORB = "P61_Unique_Belt_03", "P61_Unique_Orb_004"
BUFF = 83556
SKILL = "Seven-Sided Strike"


def source():
    text = planner("item_waist.js", BELT)
    found = re.search(r'format: "Each hit with Seven-Sided Strike grants %\.1f%% damage reduction for (\d+) seconds\.", min: (\d+), max: (\d+), '
                      r'step: 0\.1\}', text)
    assert found, text
    return {"seconds": float(found[1]), "low": float(found[2]), "high": float(found[3])}


def tunable():
    with (MODULE / "data/tunables/monk.csv").open(encoding="utf-8", newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if r["name"] == "binding_of_the_lost_max_stacks")
    return int(row["value"])


class Table(unittest.TestCase):
    def test_the_rows_are_the_sources(self):
        n, most = source(), tunable()
        self.assertEqual((7, 4, 5, 7), (n["seconds"], n["low"], n["high"], most))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(BELT, 0, "effect", "", "stack_buff", 1.0, 1.0, "", 0.0, "", n["seconds"], most, "hit", SKILL, 100.0, 0.0),
                          (BELT, 0, "buff", "", "damage_reduction_pct", n["low"], n["high"], *blank)},
                         {row for row in all_rows() if row[0] == BELT})
        for row in read_csv("data/legendary_powers.csv"):
            if row["owner"] == BELT:
                self.assertIn("P3_ItemPassive_Unique_Ring_027.pow", row["source"])
                self.assertIn("leg_bindingofthelost_p6", row["source"])
        self.assertIn("1099218ab", next(r["source"] for r in read_csv("data/legendary_powers.csv") if r["owner"] == BELT and r["kind"] == "effect"))
        self.assertEqual("Each hit with Seven-Sided Strike grants 4–5% damage reduction for 7 seconds.", tooltip(BELT))
        pool = next(row for row in read_csv("data/d3/base_items.csv") if row["d3_id"] == BELT)
        self.assertEqual(("Binding of the Lost", "yes", "monk"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))

    def test_the_tunables_migration_carries_the_cap(self):
        current = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        sql = (MODULE / "data/sql/db-world/updates" / current).read_text(encoding="utf-8")
        self.assertIn("'monk','binding_of_the_lost_max_stacks'", sql.replace(", ", ","))


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)
        cls.sheet = {int(r["spell_id"]): r for r in read_csv("data/legendary_power_buffs.csv")}

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def test_the_buff_states_no_number(self):
        self.assertEqual({BUFF: (BELT, "damage_reduction_pct", "dummy")},
                         {s: (r["owner"], r["stat"], r["aura"]) for s, r in self.sheet.items() if r["owner"] == BELT})
        self.assertEqual(("0", "0"), (self.field(BUFF, "EffectBasePoints_1"), self.field(BUFF, "EffectDieSides_1")))
        self.assertEqual(("6", "4", "1"), tuple(self.field(BUFF, c) for c in ("Effect_1", "EffectAura_1", "ImplicitTargetA_1")))
        self.assertEqual(str(tunable()), self.field(BUFF, "CumulativeAura"))
        self.assertEqual(self.field(83411, "DurationIndex"), self.field(BUFF, "DurationIndex"))   # infinite: the module sets 7 s
        self.assertFalse(int(self.field(BUFF, "Attributes")) & 0x04000000)
        self.assertEqual("Damage taken reduced.", records.unquote(self.field(BUFF, "AuraDescription_Lang_enUS")))
        self.assertIn('{83556, "P61_Unique_Belt_03", "damage_reduction_pct"},', (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"))
        render = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        # the 0082 render is the one that brought the record; later renders (the newest full one is the generated file) carry the same row
        migration = (MODULE / "data/sql/db-world/updates/combat_0082_binding_of_the_lost_buff.sql").read_text(encoding="utf-8")
        # a row's last character is the INSERT batch's comma or semicolon, which moves when records are added before it
        row = next(line for line in render.splitlines() if line.startswith("(%d," % BUFF)).rstrip(",;")
        self.assertIn(row, [line.rstrip(",;") for line in migration.splitlines()])

    def test_only_a_rolled_dummy_goes_without_its_number(self):
        self.assertIsNone(generate_spells.power_buff_number({"owner": BELT, "stat": "damage_reduction_pct", "aura": "dummy"}))
        self.assertEqual(20, generate_spells.power_buff_number({"owner": ORB, "stat": "damage_reduction_pct", "aura": "dummy"}))
        with self.assertRaises(SystemExit):   # a slow states its number, rolled or not
            generate_spells.power_buff_number({"owner": BELT, "stat": "damage_reduction_pct", "aura": "slow"})
        with self.assertRaises(SystemExit):   # a rolled number the Orb's damage is named only by its own record's text, never as a record stat
            generate_spells.power_buff_number({"owner": ORB, "stat": "damage_dealt_pct", "aura": "slow"})
        body = Path(generate_spells.__file__).read_text(encoding="utf-8")
        self.assertIn('!= ([] if mark or number is None else ["$s1"])', body)


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        n, most = source(), tunable()
        out = [(T("row", *row), None) for row in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        stacked = "stack_buff=1;@%s/%g/%d;" % (BELT, n["seconds"], most)
        # worn: every Seven-Sided Strike hit adds a stack, whatever its proc coefficient, no cooldown; another skill, a cast, not worn: nothing
        out += clear + [(T("wears", BELT, 0), None)] + [(T("fire", "hit", SKILL, 1, 50, 0), stacked)] * 7
        out += [(T("fire", "hit", SKILL, 0.25, 99, 0), stacked), (T("fire", "hit", "Fists of Thunder", 1, 50, 0), "")]
        out += [(T("fire", "cast", SKILL, 1, 50, 0), "")]
        out += clear + [(T("fire", "hit", SKILL, 1, 50, 0), "")]
        # the reduction: the item's roll per stack, 1 - stacks x N/100; seven stacks of a 4-5 roll are 28-35%
        for roll in (n["low"], 4.5, n["high"]):
            out += clear + [(T("wears", BELT, 0), None), (T("value", BELT, "", "damage_reduction_pct", roll), None)]
            for stacks in range(0, most + 1):
                out += [(T("stackfactor", "damage_reduction_pct", -1, 1, BELT, stacks), "%g" % (1 - stacks * roll / 100))]
            # a cap raised past 100%: all of the damage, never past it
            out += [(T("stackfactor", "damage_reduction_pct", -1, 1, BELT, 30), "0")]
        # no stored roll, or not worn: nothing
        out += clear + [(T("wears", BELT, 0), None), (T("stackfactor", "damage_reduction_pct", -1, 1, BELT, 7), "1")]
        out += clear + [(T("stackfactor", "damage_reduction_pct", -1, 1, BELT, 7), "1")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = events.Rules.build(header_text, "binding-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        line = "factor *= std::max(0.0, 1.0 + sign * held->second * number / 100.0);"
        mutants = {
            "no_floor": real.replace(line, "factor *= 1.0 + sign * held->second * number / 100.0;"),
            "not_per_stack": real.replace(line, "factor *= std::max(0.0, 1.0 + sign * number / 100.0);"),
            "not_the_roll": real.replace(line, "factor *= std::max(0.0, 1.0 + sign * held->second * row.max / 100.0);"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

"""Orb of Infinite Depth (diablocraft-anpkx, N-STACKBUFF): each time you hit an enemy with Explosive Blast your damage is increased by
[8-10]% and your damage reduction is increased by 20% for 6 seconds; the effect stacks up to 4 times.

  * data/legendary_powers.csv gains its rows: an `effect` stack_buff 1 fired on `hit` of Explosive Blast (6 s, at most 4) and the kind
    `buff` rows damage_dealt_pct 8-10 (rolled once per item) and damage_reduction_pct 20; the numbers are d3planner's and the power
    file's; the generator refuses the new buff stats anywhere they cannot be read;
  * the record 83553 of data/legendary_power_buffs.csv: a dummy stating one stack's reduction, stacking to 4;
  * the production rule (dc_item_power_math.h StackedFactor: 1 + sign x stacks x N/100 per owner, N the item's roll) is driven with the
    generated rows through the events harness, and its mutants fail the same driver;
  * source-text guards that the damage dealt and taken read the record's stacks (they prove the calls are there, not that they run;
    the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-anpkx.md).
"""
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import test_item_power_events as events  # noqa: E402  (modules, so their test classes are not run twice)
import test_item_power_math as k0k2  # noqa: E402
from test_control_immunity_gap import insert_rows, newest_spell_render  # noqa: E402
import test_spell_records as records  # noqa: E402
from test_item_power_math import generator, planner, read_csv, tooltip, all_rows  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
ORB, GLOVES, MIGHT = "P61_Unique_Orb_004", "P66_Unique_Gloves_007", "P61_Unique_Ring_05"
BUFF = 83553


def source():
    text = planner("item_offhand.js", ORB)
    found = re.search(r'format: "Each time you hit an enemy with Explosive Blast your damage is increased by %d%% and your damage reduction is '
                      r'increased by (\d+)%% for (\d+) seconds. This effect can stack up to (\d+) times.", min: (\d+), max: (\d+)\}', text)
    assert found, text
    return {"reduction": float(found[1]), "seconds": float(found[2]), "most": int(found[3]), "low": float(found[4]), "high": float(found[5])}


class Table(unittest.TestCase):
    def test_the_rows_are_the_sources(self):
        n = source()
        self.assertEqual((20, 6, 4, 8, 10), (n["reduction"], n["seconds"], n["most"], n["low"], n["high"]))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(ORB, 0, "effect", "", "stack_buff", 1.0, 1.0, "", 0.0, "", n["seconds"], n["most"], "hit", "Explosive Blast", 100.0, 0.0),
                          (ORB, 0, "buff", "", "damage_dealt_pct", n["low"], n["high"], *blank),
                          (ORB, 0, "buff", "", "damage_reduction_pct", n["reduction"], n["reduction"], *blank)},
                         {row for row in all_rows() if row[0] == ORB})
        for row in read_csv("data/legendary_powers.csv"):
            if row["owner"] == ORB:   # the power file agrees: SF_0 6 s, SF_1 0.2, SF_2 4 stacks, the item's 0.08-0.1
                self.assertIn("SF_0 Buff Duration = 6, SF_1 Damage Reduction = 0.2, SF_2 Max Stacks = 4", row["source"])
                self.assertIn("the item's own number 0.08-0.1", row["source"])
        self.assertIn("your damage is increased by 8–10% and your damage reduction is increased by 20% for 6 seconds", tooltip(ORB))
        pool = next(row for row in read_csv("data/d3/base_items.csv") if row["d3_id"] == ORB)
        self.assertEqual(("Orb of Infinite Depth", "yes"), (pool["d3_name"], pool["pool_version"]))

    def test_the_generator_refuses_a_buff_it_cannot_read(self):
        def row(kind, stat, low, high=None, **cells):
            base = {"owner": ORB, "pieces": "", "kind": kind, "skill": "", "stat": stat, "value_min": low, "value_max": high or low, "cond": "",
                    "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                    "icd_seconds": "", "source": "x", "note": ""}
            base.update(cells)
            return base
        stack = row("effect", "stack_buff", "1", stack_seconds="6", stack_max="4", fire_on="hit", fire_skills="Explosive Blast")
        good = [stack, row("buff", "damage_dealt_pct", "8", "10"), row("buff", "damage_reduction_pct", "20")]
        self.assertEqual(3, len(k0k2.Table.rows_of(good)))
        bad = {
            "a damage that lowers": [stack, row("buff", "damage_dealt_pct", "-8")],
            "a reduction that adds damage": [stack, row("buff", "damage_reduction_pct", "-20")],
            "a reduction of 100% at the most stacks": [stack, row("buff", "damage_reduction_pct", "25")],
            "a stacked stat with no record": [dict(r, owner=k0k2.MAGEFIST) for r in good],
            "a rolled armor": [dict(stack, owner=GLOVES), row("buff", "armor_pct", "40", "50", owner=GLOVES)],
        }
        for name, sheet in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                k0k2.Table.rows_of(sheet)
        self.assertEqual(("damage_dealt_pct", "damage_reduction_pct", "skill_damage_pct"), generator.STACKED_BUFF_STATS)


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)
        cls.sheet = {int(r["spell_id"]): r for r in read_csv("data/legendary_power_buffs.csv")}

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def test_the_buff(self):
        n = source()
        self.assertEqual({BUFF: (ORB, "damage_reduction_pct", "dummy")},
                         {s: (r["owner"], r["stat"], r["aura"]) for s, r in self.sheet.items() if r["owner"] == ORB})
        self.assertEqual(n["reduction"], int(self.field(BUFF, "EffectBasePoints_1")) + int(self.field(BUFF, "EffectDieSides_1")))   # one stack
        self.assertEqual(("6", "4", "1"), tuple(self.field(BUFF, c) for c in ("Effect_1", "EffectAura_1", "ImplicitTargetA_1")))
        self.assertEqual(str(n["most"]), self.field(BUFF, "CumulativeAura"))           # the client shows the total of the stacks
        self.assertEqual(self.field(83411, "DurationIndex"), self.field(BUFF, "DurationIndex"))   # infinite: the module sets 6 s
        self.assertEqual(("0", "0", "0"), (self.field(BUFF, "Effect_2"), self.field(BUFF, "Effect_3"), self.field(BUFF, "Mechanic")))
        self.assertFalse(int(self.field(BUFF, "Attributes")) & 0x04000000)            # a buff, not a debuff
        self.assertEqual("Damage taken reduced by $s1% and damage dealt increased.", records.unquote(self.field(BUFF, "AuraDescription_Lang_enUS")))
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn('{83553, "P61_Unique_Orb_004", "damage_reduction_pct"},', header)
        # The newest full spell render carries the record 0071 brought unchanged, field for field; nothing is asserted about its other
        # records, so a later render of another record leaves this green.
        render = newest_spell_render(MODULE / "data/sql/db-world/updates").read_text(encoding="utf-8")
        migration = MODULE / "data/sql/db-world/updates/combat_0071_orb_of_infinite_depth_buff.sql"
        rendered = {int(r["ID"]): r for r in insert_rows(render, "spell_dbc")}
        brought = {int(r["ID"]): r for r in insert_rows(migration.read_text(encoding="utf-8"), "spell_dbc")}
        self.assertIn(BUFF, brought)
        self.assertEqual(brought[BUFF], rendered.get(BUFF))


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        n = source()
        out = [(T("row", *row), None) for row in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        stacked = "stack_buff=1;@%s/%g/%d;" % (ORB, n["seconds"], n["most"])
        # worn: every Explosive Blast hit fires the stack, a proc coefficient does not scale it, no cooldown; another skill or not worn: nothing
        out += clear + [(T("wears", ORB, 0), None)] + [(T("fire", "hit", "Explosive Blast", 1, 50, 0), stacked)] * 3
        out += [(T("fire", "hit", "Explosive Blast", 0.25, 99, 0), stacked), (T("fire", "hit", "Arcane Orb", 1, 50, 0), "")]
        out += [(T("fire", "cast", "Explosive Blast", 1, 50, 0), "")]
        out += clear + [(T("fire", "hit", "Explosive Blast", 1, 50, 0), "")]
        # the damage: the item's roll per stack, 1 + stacks x N/100; the reduction 1 - stacks x 20/100
        roll = 9.0
        out += clear + [(T("wears", ORB, 0), None), (T("value", ORB, "", "damage_dealt_pct", roll), None)]
        for stacks in range(0, n["most"] + 1):
            out += [(T("stackfactor", "damage_dealt_pct", 1, 1, ORB, stacks), "%g" % (1 + stacks * roll / 100)),
                    (T("stackfactor", "damage_reduction_pct", -1, 1, ORB, stacks), "%g" % (1 - stacks * n["reduction"] / 100))]
        out += [(T("stackfactor", "damage_dealt_pct", 1, 0), "1"),                          # no record on the player
                (T("stackfactor", "damage_dealt_pct", 1, 1, GLOVES, 4), "1"),               # another owner's stacks
                (T("stackfactor", "armor_pct", 1, 1, GLOVES, 4), "1")]                      # Stone Gauntlets' armor is the sheet's
        # a `player` row of the stat is not a stack's (Band of Might's reduction is its `triggered` window's, ReductionFactor)
        out += [(T("wears", MIGHT, 0), None), (T("value", MIGHT, "", "damage_reduction_pct", 70), None),
                (T("stackfactor", "damage_reduction_pct", -1, 1, MIGHT, 4), "1")]
        # no stored roll: no damage, the reduction still its fixed number; not worn: nothing
        out += clear + [(T("wears", ORB, 0), None), (T("stackfactor", "damage_dealt_pct", 1, 1, ORB, 4), "1"),
                        (T("stackfactor", "damage_reduction_pct", -1, 1, ORB, 4), "%g" % (1 - 4 * n["reduction"] / 100))]
        out += clear + [(T("stackfactor", "damage_reduction_pct", -1, 1, ORB, 4), "1")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = events.Rules.build(header_text, "orb-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        line = "factor *= std::max(0.0, 1.0 + sign * held->second * number / 100.0);"
        mutants = {
            "not_per_stack": real.replace(line, "factor *= 1.0 + sign * number / 100.0;"),
            "no_sign": real.replace(line, "factor *= 1.0 + held->second * number / 100.0;"),
            "not_the_roll": real.replace(line, "factor *= 1.0 + sign * held->second * row.min / 100.0;"),
            "any_owner": real.replace("auto held = stacks.find(row.owner);", "auto held = stacks.begin();"),
            "any_kind": real.replace('held != stacks.end() && row.kind == "buff" && row.stat == stat', "held != stacks.end() && row.stat == stat"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

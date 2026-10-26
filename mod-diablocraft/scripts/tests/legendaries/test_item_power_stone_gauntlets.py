"""Stone Gauntlets (diablocraft-ghb4o, PM 2026-10-12): getting hit increases your armor by 50%, but reduces your movement speed by 15% and
attack speed by 20%; the effect stacks up to 5 times.

  * data/legendary_powers.csv gains its rows: an `effect` stack_buff 1 fired on `taken` (6 s, at most 5) and the kind `buff` rows
    armor_pct 50, movement_speed_pct -15, attack_speed_pct -20 and attack_speed_floor_pct 10; the 50/15/20/5 are read from d3planner's
    item file and set against the tooltip, the 6 s and the 0.1 floor from docs/research/stone-gauntlets.md; the generator refuses the
    kind anywhere it cannot be read;
  * the two records of data/legendary_power_buffs.csv: 83551 the buff (a dummy stating one stack's armor, stacking to 5) and 83552 its
    slow (a stock SPELL_AURA_MOD_DECREASE_SPEED of -15 per stack with the Snare mechanic, so control immunity removes it);
  * the production rules (dc_item_power_math.h Fire's stack_buff, Stacked, StackedSpeedFactor, BuffValue) are driven with the generated
    rows through the events harness, and their mutants fail the same driver;
  * source-text guards that a hit taken stacks both records on one timer, the armor reaches the sheet and leaves it, the attack speed is
    read where the attacks per second are, the stacks end with the gloves and Juggernaut leaves them alone (they prove the calls are
    there, not that they run; the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-ghb4o.md).
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
import test_item_power_math as power_math  # noqa: E402
import test_spell_records as records  # noqa: E402
from test_item_power_math import generator, planner, read_csv, tooltip, all_rows  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
GLOVES, GAVEL = "P66_Unique_Gloves_007", "P61_Unique_Mighty_2H_001"
BUFF, SLOW = 83551, 83552


def source():
    text = planner("item_hands.js", GLOVES)
    found = re.search(r'format: "Getting hit increases your armor by (\d+)%%, but reduces your movement speed by (\d+)%% and attack speed by '
                      r'(\d+)%%. This effect stacks up to (\d+) times.", args: 0\}', text)
    assert found, text
    return {"armor": float(found[1]), "movement": float(found[2]), "speed": float(found[3]), "most": int(found[4])}


def research():
    """The two numbers d3planner does not state: the seconds and the attack speed floor (docs/research/stone-gauntlets.md)."""
    text = (REPO / "docs/research/stone-gauntlets.md").read_text(encoding="utf-8")
    assert "a *single* buff timer, **about 6 s**" in text
    assert "0.1 attacks/sec (0.1× base/weapon APS)" in text
    return {"seconds": 6.0, "floor": 10.0}


class Table(unittest.TestCase):
    def test_the_rows_are_the_sources(self):
        n, r = source(), research()
        self.assertEqual((50, 15, 20, 5), (n["armor"], n["movement"], n["speed"], n["most"]))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        buff = lambda stat, v: (GLOVES, 0, "buff", "", stat, v, v, *blank)  # noqa: E731
        self.assertEqual({(GLOVES, 0, "effect", "", "stack_buff", 1.0, 1.0, "", 0.0, "", r["seconds"], n["most"], "taken", "", 100.0, 0.0),
                          buff("armor_pct", n["armor"]), buff("movement_speed_pct", -n["movement"]),
                          buff("attack_speed_pct", -n["speed"]), buff("attack_speed_floor_pct", r["floor"])},
                         {row for row in all_rows() if row[0] == GLOVES})
        self.assertIn("increases your armor by %g%%, but reduces your movement speed by %g%% and attack speed by %g%%" %
                      (n["armor"], n["movement"], n["speed"]), tooltip(GLOVES))
        pool = next(row for row in read_csv("data/d3/base_items.csv") if row["d3_id"] == GLOVES)
        self.assertEqual(("Stone Gauntlets", "yes", ""), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))

    def test_the_generator_refuses_a_buff_it_cannot_read(self):
        def row(kind, stat, value, **cells):
            base = {"owner": GLOVES, "pieces": "", "kind": kind, "skill": "", "stat": stat, "value_min": value, "value_max": value, "cond": "",
                    "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                    "icd_seconds": "", "source": "x", "note": ""}
            base.update(cells)
            return base
        stack = row("effect", "stack_buff", "1", stack_seconds="6", stack_max="5", fire_on="taken")
        good = [stack, row("buff", "armor_pct", "50"), row("buff", "movement_speed_pct", "-15"), row("buff", "attack_speed_pct", "-20"),
                row("buff", "attack_speed_floor_pct", "10")]
        self.assertEqual(5, len(power_math.Table.rows_of(good)))
        bad = {
            "a stack with no buff rows": [stack],
            "buff rows with no stack": good[1:],
            "no seconds": [dict(stack, stack_seconds=""), *good[1:]],
            "no stack limit": [dict(stack, stack_max=""), *good[1:]],
            "a part of a stack": [dict(stack, value_min="0.5", value_max="0.5"), *good[1:]],
            "a stack on a set": [dict(stack, pieces="2"), *good[1:]],
            "a buff stat nothing reads": [*good, row("buff", "damage_pct", "10")],
            "a slow that speeds up": [stack, row("buff", "movement_speed_pct", "15")],
            "an armor that rolls": [stack, row("buff", "armor_pct", "40", value_max="50")],
            "a buff with a condition": [stack, row("buff", "armor_pct", "50", cond="triggered", cond_arg="4", fire_on="taken")],
            "a floor above 100": [*good[:4], row("buff", "attack_speed_floor_pct", "110")],
            "an attack speed with no slow": [stack, row("buff", "armor_pct", "50"), row("buff", "attack_speed_pct", "-20")],
            "a buff with no record": [dict(r, owner=GAVEL) for r in good],
        }
        for name, sheet in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of(sheet)
        self.assertIn("stack_buff", generator.EFFECT_STATS)
        self.assertIn("buff", generator.KINDS)


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)
        cls.sheet = {int(r["spell_id"]): r for r in read_csv("data/legendary_power_buffs.csv")}

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def test_the_buff_and_its_slow(self):
        n = source()
        self.assertEqual({BUFF: (GLOVES, "armor_pct", "dummy"), SLOW: (GLOVES, "movement_speed_pct", "slow")},
                         {s: (r["owner"], r["stat"], r["aura"]) for s, r in self.sheet.items() if r["owner"] == GLOVES})
        for spell, number, aura in ((BUFF, n["armor"], "4"), (SLOW, -n["movement"], "33")):
            self.assertEqual(number, int(self.field(spell, "EffectBasePoints_1")) + int(self.field(spell, "EffectDieSides_1")))   # one stack
            self.assertEqual(("6", aura, "1"), tuple(self.field(spell, c) for c in ("Effect_1", "EffectAura_1", "ImplicitTargetA_1")))
            self.assertEqual(str(n["most"]), self.field(spell, "CumulativeAura"))           # the client shows the total of the stacks
            self.assertEqual(self.field(83411, "DurationIndex"), self.field(spell, "DurationIndex"))   # infinite: the module sets 6 s
            self.assertEqual(("0", "0"), (self.field(spell, "Effect_2"), self.field(spell, "Effect_3")))
        self.assertEqual("11", self.field(SLOW, "Mechanic"))     # MECHANIC_SNARE: RemoveAurasWithMechanic(ControlImpairing) takes it off
        self.assertEqual("0", self.field(BUFF, "Mechanic"))      # and leaves the armor
        self.assertTrue(int(self.field(SLOW, "Attributes")) & 0x04000000)
        self.assertFalse(int(self.field(BUFF, "Attributes")) & 0x04000000)
        self.assertEqual("Armor increased by $s1%.", records.unquote(self.field(BUFF, "AuraDescription_Lang_enUS")))
        self.assertEqual("Movement speed reduced by $s1%.", records.unquote(self.field(SLOW, "AuraDescription_Lang_enUS")))
        self.assertEqual("0", self.field(83550, "CumulativeAura"))   # The Burning Axe of Sankis's window does not stack
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn('{83551, "P66_Unique_Gloves_007", "armor_pct"},\n    {83552, "P66_Unique_Gloves_007", "movement_speed_pct"},', header)


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        n, r = source(), research()
        out = [(T("row", *row), None) for row in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        stacked = "stack_buff=1;@%s/%g/%d;" % (GLOVES, r["seconds"], n["most"])
        # worn: every hit taken fires the stack, no cooldown; not worn: nothing
        out += clear + [(T("wears", GLOVES, 0), None)] + [(T("fire", "taken", "", 1, 50, 0), stacked)] * 3
        out += [(T("fire", "kill", "", 1, 50, 0), ""), (T("fire", "hit_spender", "Hammer of the Ancients", 1, 50, 0), "")]
        out += clear + [(T("fire", "taken", "", 1, 50, 0), "")]
        # the stacks: one more each hit, never past 5
        out += [(T("stacked", held, 1, n["most"]), str(min(held + 1, n["most"]))) for held in range(0, 7)]
        # the attack speed: 1.0, 0.8, 0.6, 0.4, 0.2, then the floor 0.1 (Blizzard forum t/45055)
        for stacks, want in zip(range(0, 7), ("1", "0.8", "0.6", "0.4", "0.2", "0.1", "0.1")):
            out += [(T("speed", GLOVES, stacks), want)]
        out += [(T("speed", GAVEL, 5), "1")]                                       # an item with no slow
        out += [(T("buff", GLOVES, "armor_pct"), "%g" % n["armor"]), (T("buff", GLOVES, "movement_speed_pct"), "%g" % -n["movement"]),
                (T("buff", GLOVES, "stack_buff"), "0"), (T("buff", GAVEL, "armor_pct"), "0")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = events.Rules.build(header_text, "stone-" + name)
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
        mutants = {
            "no_cap": real.replace("return std::min(held + static_cast<unsigned>(add), most);", "return held + static_cast<unsigned>(add);"),
            "no_floor": real.replace('BuffValue(rows, owner, "attack_speed_floor_pct") / 100.0,', "0.0,"),
            "not_per_stack": real.replace('1.0 + stacks * BuffValue(rows, owner, "attack_speed_pct")', '1.0 + BuffValue(rows, owner, "attack_speed_pct")'),
            "no_row_handed_over": real.replace("out.push_back({row.stat, number, row.skill, &row});", "out.push_back({row.stat, number, row.skill});"),
            "any_kind_is_a_buff": real.replace('row.owner == owner && !row.pieces && row.kind == "buff" && row.stat == stat',
                                               "row.owner == owner && !row.pieces && row.stat == stat"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

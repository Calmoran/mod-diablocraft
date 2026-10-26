"""Halo of Karini (diablocraft-g8clb, legendary rest bead 017): "You take [60-80]% less damage for 5 seconds after your Storm Armor
electrocutes an enemy more than 15 yards away."

  * data/legendary_powers.csv gains its two rows: a `player` damage_reduction_pct [60-80] under `triggered` 5 s fired on the new event
    `storm_armor_shock`, and the item's fixed companion `event_distance_yards` 15 (the way `resource_threshold_pct` rides beside
    `resource_above`). The numbers and words are read from d3planner's item file and set against the tooltip;
  * the generator refuses a companion it cannot read (a condition, an event, a set, a range, no event row of the item to read it);
  * the production rules (dc_item_power_math.h Fire with the event's distance, MinYards) are compiled and driven with the generated rows
    through the events harness: strictly more than 15 yards, the 5 s window to the millisecond, the owner, the event, an item with no
    companion; their mutants fail the same driver;
  * source-text guards that Storm Armor's two electrocutes (its tick and Shocking Aspect's crit shock) call ItemPowers::StormArmorShock,
    which reads the yards to the enemy the way DistanceFactor does and hands them to Fire (they prove the calls are there, not that they run;
    the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-g8clb.md).
"""
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_events as events  # noqa: E402  (a module, so its test classes are not run twice)
import test_item_power_math as power_math  # noqa: E402
from test_item_power_math import generator, planner, read_csv, tooltip, all_rows  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HALO, BAND = "P61_Unique_Ring_03", "P61_Unique_Ring_05"
EVENT = "storm_armor_shock"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def source():
    text = planner("item_finger.js", HALO)
    found = re.search(r'format: "You take %d%% less damage for (\d+) seconds after your Storm Armor electrocutes an enemy more than (\d+) '
                      r'yards away.", min: (\d+), max: (\d+)\}', text)
    assert found, text
    return {"seconds": float(found[1]), "yards": float(found[2]), "reduction": (float(found[3]), float(found[4]))}


class Table(unittest.TestCase):
    def test_the_rows_are_the_sources(self):
        n = source()
        self.assertEqual((5, 15, (60, 80)), (n["seconds"], n["yards"], n["reduction"]))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(HALO, 0, "player", "", "damage_reduction_pct", *n["reduction"], "triggered", n["seconds"], "", 0.0, 0, EVENT, "", 100.0, 0.0),
                          (HALO, 0, "player", "", "event_distance_yards", n["yards"], n["yards"], *blank)},
                         {r for r in all_rows() if r[0] == HALO})
        self.assertIn("%g–%g%%" % n["reduction"], tooltip(HALO))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == HALO)
        self.assertEqual(("Halo of Karini", "yes", "wizard"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))
        self.assertIn(EVENT, generator.EVENTS)

    def test_the_generator_refuses_a_distance_it_cannot_read(self):
        event = {"owner": HALO, "pieces": "", "kind": "player", "skill": "", "stat": "damage_reduction_pct", "value_min": "60", "value_max": "80",
                 "cond": "triggered", "cond_arg": "5", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": EVENT,
                 "fire_skills": "", "chance_pct": "", "icd_seconds": "", "source": "x", "note": ""}
        far = dict(event, stat="event_distance_yards", value_min="15", value_max="15", cond="", cond_arg="", fire_on="")
        bad = {
            "a range": dict(far, value_max="20"),
            "zero": dict(far, value_min="0", value_max="0"),
            "negative": dict(far, value_min="-15", value_max="-15"),
            "under a condition": dict(far, cond="triggered", cond_arg="5", fire_on=EVENT),
            "fired by an event": dict(far, fire_on="taken"),
            "a set's": dict(far, pieces="2"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([event, row])
        with self.assertRaises(ValueError):   # a distance with no event row of its item to read it
            power_math.Table.rows_of([far])
        with self.assertRaises(ValueError):   # the event names no skills
            power_math.Table.rows_of([dict(event, fire_skills="Storm Armor"), far])
        self.assertEqual(2, len(power_math.Table.rows_of([event, far])))
        self.assertEqual(1, len(power_math.Table.rows_of([event])))   # an event with no distance is any distance
        self.assertIn("event_distance_yards", generator.PLAYER_STATS)


class Rules(unittest.TestCase):
    def cases(self):
        n = source()
        taken = lambda p: "%g" % (1 - p / 100)  # noqa: E731
        none = events.Rules.sets()
        fire = lambda event, skill, draw=50: T("fire", event, skill, 1, draw, *none)  # noqa: E731
        reduction = T("reduction", *none)
        out = [(T("row", *r), None) for r in all_rows()]
        start = [(T("clear"), None), (T("now", 1000), None), (T("wears", HALO, 0), None), (T("value", HALO, "", "damage_reduction_pct", 70), None)]
        # strictly more than the item's yards opens the window; the stored roll is the amount
        for yards, on in ((0, False), (10, False), (n["yards"] - 0.01, False), (n["yards"], False), (n["yards"] + 0.01, True), (40, True)):
            out += start + [(T("yards", yards), None), (fire(EVENT, ""), ""), (reduction, taken(70) if on else "1"),
                            (T("opened", EVENT), "%s/damage_reduction_pct/5;" % HALO if on else "")]
        # the window: 5 s to the millisecond, a Primal's roll
        out += start + [(T("yards", 30), None), (fire(EVENT, ""), ""), (T("now", 5999), None), (reduction, taken(70)),
                        (T("now", 6000), None), (reduction, taken(70)), (T("now", 6001), None), (reduction, "1")]
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", HALO, 0), None), (T("value", HALO, "", "damage_reduction_pct", 80), None),
                (T("yards", 30), None), (fire(EVENT, ""), ""), (reduction, taken(80))]
        # a near shock after a far one does not shorten the window; a far one renews it
        out += start + [(T("yards", 30), None), (fire(EVENT, ""), ""), (T("now", 4000), None), (T("yards", 5), None), (fire(EVENT, ""), ""),
                        (T("now", 6001), None), (reduction, "1"), (T("yards", 30), None), (fire(EVENT, ""), ""), (reduction, taken(70))]
        # not worn; no roll stored; another event; the Storm Armor skill name changes nothing (the row names no skills)
        out += [(T("clear"), None), (T("now", 1000), None), (T("yards", 30), None), (fire(EVENT, ""), ""), (reduction, "1")]
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", HALO, 0), None), (T("yards", 30), None), (fire(EVENT, ""), ""), (reduction, "1")]
        out += start + [(T("yards", 30), None), (fire("cast", "Storm Armor"), ""), (fire("taken", ""), ""), (fire("kill", ""), ""), (reduction, "1")]
        out += start + [(T("yards", 30), None), (fire(EVENT, "Storm Armor"), ""), (reduction, taken(70))]
        # an item with no distance row keeps its event at any distance (Band of Might has none), and Halo's row is read only for Halo
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", BAND, 0), None), (T("value", BAND, "", "damage_reduction_pct", 70), None),
                (T("yards", 0), None), (fire("cast", "Leap"), ""), (reduction, taken(70))]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = events.Rules.build(header_text, "halo-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        gate = "if (farther > 0 && !(situation.eventYards > farther))"
        mutants = {
            "no_distance_gate": real.replace(gate, "if (false)"),
            "exactly_enough": real.replace(gate, gate.replace("situation.eventYards > farther", "situation.eventYards >= farther")),
            "the_wrong_way": real.replace(gate, gate.replace("situation.eventYards > farther", "situation.eventYards < farther")),
            "the_zero_is_a_distance": real.replace(gate, "if (!(situation.eventYards > farther))"),
            "any_items_distance": real.replace("if (row.owner == owner && !row.pieces && row.kind == \"player\" && row.stat == \"event_distance_yards\")",
                                               "if (!row.pieces && row.kind == \"player\" && row.stat == \"event_distance_yards\")"),
            "any_stat_is_the_distance": real.replace("&& row.stat == \"event_distance_yards\"", ""),
            "the_yards_not_read": real.replace("situation.eventYards > farther", "true"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

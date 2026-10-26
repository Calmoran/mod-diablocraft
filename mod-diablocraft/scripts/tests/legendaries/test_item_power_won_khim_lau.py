"""Won Khim Lau (diablocraft-vbm0q, Monk legendary list row 238, on Dark Mage's Shade's N-CAST): "Hitting with Tempest Rush will activate Cyclone
Strike, and both skills deal [500-600]% increased damage."

  * data/legendary_powers.csv gains two rows for the fist weapon P67_Unique_Fist_006: `skill` Tempest Rush;Cyclone Strike `damage_increase_pct` 500-600
    (one roll for both), and `effect` `cast_skill` Cyclone Strike fired on `hit_spender` of Tempest Rush, its number 0: the cooldown is the designer's tunable
    monk.won_khim_lau_cooldown_seconds, 0 (q-1014-14 (a): the text states none, so every Tempest Rush tick that hits casts one);
  * the production rules (dc_item_power_math.h Fire with Situation::castCooldownSeconds, SkillFactor, RollPowers) are driven with the generated rows
    through tests/item_power_won_khim_lau/harness.cpp, and their mutants fail the same driver;
  * the generator refuses a cast on a hit that it cannot stand behind (a number, no skill to fire on, the per-enemy `hit`);
  * source-text guards that Tempest Rush's tick reports one spender hit per tick that struck (Combat::Connected with the count, as Crippling Wave),
    that Connected reaches the `hit_spender` event for a skill that states a cost, that the caller reads the tunable before the lock and that the
    effect casts the bar's skill (they prove the calls are there, not that they run; the C++ is compile-checked by syntax_check.sh and the in-game
    steps are in docs/test-diablocraft-vbm0q.md).
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import test_item_power_k4 as k4  # noqa: E402
from test_item_power_k4 import GENERATED, all_rows, read_csv  # noqa: E402
from test_item_power_math import planner, tooltip  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_won_khim_lau/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
OWNER = "P67_Unique_Fist_006"
RUSH, CYCLONE = "Tempest Rush", "Cyclone Strike"
BOTH = RUSH + ";" + CYCLONE
DMG, CAST = "damage_increase_pct", "cast_skill"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def source():
    """(text, low, high) as d3planner words the power."""
    item = planner("item_onehand.js", OWNER)
    m = re.search(r'format: "(Hitting with Tempest Rush will activate Cyclone Strike, and both skills deal %d%% increased damage.)", min: (\d+), max: (\d+)', item)
    assert m, item
    return m[1].replace("%d%%", "%s%%"), float(m[2]), float(m[3])


def mine():
    return [r for r in all_rows() if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_rows_are_the_source(self):
        text, low, high = source()
        self.assertEqual((500.0, 600.0), (low, high))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(OWNER, 0, "skill", BOTH, DMG, low, high, *blank),
                          (OWNER, 0, "effect", CYCLONE, CAST, 0.0, 0.0, "", 0.0, "", 0.0, 0, "hit_spender", RUSH, 100.0, 0.0)}, set(mine()))
        self.assertEqual(text % "500–600", tooltip(OWNER))
        item = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Won Khim Lau", "legendary", "yes", "no"), (item["d3_name"], item["rarity"], item["pool_version"], item["craft_only"]))
        for r in read_csv("data/legendary_powers.csv"):
            if r["owner"] == OWNER:
                self.assertIn("leg_wonkhimlau", r["source"])
                self.assertTrue(r["note"])

    def test_the_cooldown_is_alexs_tunable_at_zero(self):
        row = next(r for r in read_csv("data/tunables/monk.csv") if r["name"] == "won_khim_lau_cooldown_seconds")
        self.assertEqual(("", "0", "seconds"), (row["d3_value"], row["value"], row["unit"]))
        self.assertIn("q-1014-14", row["notes"])
        current = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        for sql in (MODULE / "data/generated" / current, MODULE / "data/sql/db-world/updates" / current):
            self.assertIn("('monk', 'won_khim_lau_cooldown_seconds', NULL, 0.0, 'seconds',", sql.read_text(encoding="utf-8"))

    def test_tempest_rush_states_a_cost_so_its_hit_is_a_spenders(self):
        costs = [r for r in read_csv("data/d3/monk_skill_values.csv") if r["skill"] == RUSH and r["token"] == "cost_resource"]
        self.assertTrue(costs and all(float(r["value"]) > 0 for r in costs), costs)

    def test_the_generator_refuses_a_cast_on_a_hit_it_cannot_stand_behind(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == CAST)
        self.assertEqual(1, len(k4.Table.rows_of([base])))
        bad = {
            "a number on the hit cast": dict(base, value_min="5", value_max="5"),
            "a range on the hit cast": dict(base, value_min="0", value_max="5"),
            "no skill whose hit casts it": dict(base, fire_skills=""),
            "every enemy hit": dict(base, fire_on="hit"),
            "a generator's hit": dict(base, fire_on="hit_generator"),
            "a chance": dict(base, chance_pct="50"),
            "a cooldown column": dict(base, icd_seconds="1"),
            "another effect on the event of the life": dict(base, stat="resource_refund", skill="", fire_on="life_below", fire_skills="",
                                                            value_min="5", value_max="5"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                k4.Table.rows_of([row])


class Rules(unittest.TestCase):
    @staticmethod
    def build(header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="wonkhimlau-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        _, low, high = source()
        key = "power:%s:%s" % (RUSH, DMG)
        cast = "%s=0@%s;" % (CAST, CYCLONE)
        out = [(T("row", *r), None) for r in rows]
        wear = lambda roll: [(T("clear"), None), (T("stored", key, roll), None), (T("wears", OWNER), None)]  # noqa: E731
        # not worn, or in the bag: nothing
        out += [(T("clear"), None), (T("now", 1000), None), (T("fire", "hit_spender", RUSH, 1), "")]
        out += [(T("clear"), None), (T("stored", key, 550), None), (T("bag", OWNER), None), (T("fire", "hit_spender", RUSH, 1), ""),
                (T("factor", RUSH, DMG), "1")]
        for roll in (low, 550, high):
            out += wear(roll)
            # the damage: one roll on both skills, nothing on another
            out += [(T("factor", RUSH, DMG), "%.10g" % (1 + roll / 100)), (T("factor", CYCLONE, DMG), "%.10g" % (1 + roll / 100)),
                    (T("factor", "Lashing Tail Kick", DMG), "1"), (T("factor", "Wave of Light", DMG), "1")]
            # cooldown 0 (the designer's number): every tick that hits casts, 0.2 s apart and even in the same millisecond; a certain row ignores the proc coefficient
            for ms in (1000, 1000, 1200, 1400, 1600):
                out += [(T("now", ms), None), (T("fire", "hit_spender", RUSH, 1), cast)]
            out += [(T("fire", "hit_spender", RUSH, 0), cast), (T("fire", "hit_spender", RUSH, 0.25), cast)]
            # only Tempest Rush's spender hit: not Cyclone Strike's own (no loop), another skill, another event
            out += [(T("fire", "hit_spender", CYCLONE, 1), ""), (T("fire", "hit_spender", "Lashing Tail Kick", 1), ""),
                    (T("fire", "hit", RUSH, 1), ""), (T("fire", "hit_generator", RUSH, 1), ""), (T("fire", "cast", RUSH, 1), ""),
                    (T("fire", "life_below", RUSH, 1), "")]
        # a cooldown the designer sets is kept from the last cast, the end exact
        out += wear(550) + [(T("cooldown", 1.5), None)]
        for ms, fires in ((1000, True), (1200, False), (2499, False), (2500, True), (2700, False), (4000, True)):
            out += [(T("now", ms), None), (T("fire", "hit_spender", RUSH, 1), cast if fires else "")]
        # one stored roll, under the first skill's key; the fixed cast row stores nothing; a Primal takes the top
        out += [(T("roll", OWNER, 1), "%s=%g;" % (key, high)), (T("roll", OWNER, 0), "%s=%g;" % (key, (low + high) / 2))]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        dmg = next(r for r in rows if r[2] == "skill")
        cast = next(r for r in rows if r[2] == "effect")
        header = {
            "the_tunable_is_ignored": ('row.stat == "cast_skill" ? (number > 0 ? number : situation.castCooldownSeconds) : row.icdSeconds',
                                       'row.stat == "cast_skill" ? number : row.icdSeconds'),
            "the_column_is_the_cooldown": ('row.stat == "cast_skill" ? (number > 0 ? number : situation.castCooldownSeconds) : row.icdSeconds',
                                           "row.icdSeconds"),
            "any_skill_fires_it": ("if (!row.fireSkills.empty() && std::find(row.fireSkills.begin(), row.fireSkills.end(), skill) == row.fireSkills.end())\n"
                                   "                continue;", ""),
            "any_event_fires_it": ("if (row.fireOn != fireOn || !Owned(row, counts, situation, number))", "if (!Owned(row, counts, situation, number))"),
        }
        for name, (old, new) in header.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name)
                want, got = self.drive(real.replace(old, new), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        swap = lambda old, new: [new if r is old else r for r in rows]  # noqa: E731
        data = {
            "rush_only": swap(dmg, dmg[:3] + (RUSH,) + dmg[4:]),
            "cyclone_casts_cyclone": swap(cast, cast[:13] + (CYCLONE,) + cast[14:]),
            "per_enemy_hit": swap(cast, cast[:12] + ("hit",) + cast[13:]),
            "a_one_second_cooldown": swap(cast, cast[:5] + (1.0, 1.0) + cast[7:]),
            "no_cast_row": [dmg],
        }
        for name, mutant in data.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

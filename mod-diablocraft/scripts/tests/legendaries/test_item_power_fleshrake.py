"""Fleshrake (diablocraft-k2yzl, on N-STACKBUFF): Dashing Strike increases the damage of Dashing Strike by [75-100]% for 1 second, stacking up
to 5 times.

  * data/legendary_powers.csv gains its rows: an `effect` stack_buff 1 fired on the `cast` of Dashing Strike (1 s, at most 5) and the kind
    `buff` row skill_damage_pct 75-100 (rolled once per item) that names Dashing Strike; the numbers are d3planner's and the power file's;
    the generator refuses the new buff stat where it cannot be read;
  * the record 83564 of data/legendary_power_buffs.csv: a dummy that states no number (the roll differs per item), stacking to 5;
  * the production rule (dc_item_power_math.h StackedFactor with a skill: 1 + stacks x N/100 per owner, N the item's roll, only for the
    skill the row names) is driven with the generated rows through the events harness, and its mutants fail the same driver;
  * source-text guards that the hit reads the stacks of the record (they prove the calls are there, not that they run; the C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-k2yzl.md).
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
FLESHRAKE, ORB = "P41_Unique_Fist_007", "P61_Unique_Orb_004"
DASH, OTHER = "Dashing Strike", "Way of the Falling Star"
BUFF = 83564


def source():
    text = planner("item_onehand.js", FLESHRAKE)
    found = re.search(r'format: "Dashing Strike increases the damage of Dashing Strike by %d%% for (\d+) second, stacking up to (\d+) times.", '
                      r'min: (\d+), max: (\d+)\}', text)
    assert found, text
    return {"seconds": float(found[1]), "most": int(found[2]), "low": float(found[3]), "high": float(found[4])}


class Table(unittest.TestCase):
    def test_the_rows_are_the_sources(self):
        n = source()
        self.assertEqual((1, 5, 75, 100), (n["seconds"], n["most"], n["low"], n["high"]))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(FLESHRAKE, 0, "effect", "", "stack_buff", 1.0, 1.0, "", 0.0, "", n["seconds"], n["most"], "cast", DASH, 100.0, 0.0),
                          (FLESHRAKE, 0, "buff", DASH, "skill_damage_pct", n["low"], n["high"], *blank)},
                         {row for row in all_rows() if row[0] == FLESHRAKE})
        for row in read_csv("data/legendary_powers.csv"):
            if row["owner"] == FLESHRAKE:   # the power file agrees: SF_0 1 s, SF_1 5 stacks, the item's 0.75-1
                self.assertIn("SF_0 Buff Duration = 1, SF_1 Max Stacks = 5", row["source"])
                self.assertIn("the item's own number 0.75-1", row["source"])
        self.assertIn("Dashing Strike increases the damage of Dashing Strike by 75–100% for 1 second, stacking up to 5 times", tooltip(FLESHRAKE))
        pool = next(row for row in read_csv("data/d3/base_items.csv") if row["d3_id"] == FLESHRAKE)
        self.assertEqual(("Fleshrake", "yes"), (pool["d3_name"], pool["pool_version"]))

    def test_the_generator_refuses_a_skill_buff_it_cannot_read(self):
        def row(kind, stat, low, high=None, **cells):
            base = {"owner": FLESHRAKE, "pieces": "", "kind": kind, "skill": "", "stat": stat, "value_min": low, "value_max": high or low,
                    "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "",
                    "chance_pct": "", "icd_seconds": "", "source": "x", "note": ""}
            base.update(cells)
            return base
        stack = row("effect", "stack_buff", "1", stack_seconds="1", stack_max="5", fire_on="cast", fire_skills=DASH)
        good = [stack, row("buff", "skill_damage_pct", "75", "100", skill=DASH)]
        self.assertEqual(2, len(k0k2.Table.rows_of(good)))
        bad = {
            "no skill named": [stack, row("buff", "skill_damage_pct", "75", "100")],
            "not a skill": [stack, row("buff", "skill_damage_pct", "75", "100", skill="Dashing Stroke")],
            "two skills": [stack, row("buff", "skill_damage_pct", "75", "100", skill=DASH + ";Cyclone Strike")],
            "a damage that lowers": [stack, row("buff", "skill_damage_pct", "-75", skill=DASH)],
            "a skill on a buff that names none": [stack, row("buff", "damage_dealt_pct", "8", skill=DASH)],
            "no stack_buff row": [row("buff", "skill_damage_pct", "75", "100", skill=DASH)],
            "no record of the owner": [dict(r, owner=k0k2.MAGEFIST) for r in good],
        }
        for name, sheet in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                k0k2.Table.rows_of(sheet)
        self.assertIn("skill_damage_pct", generator.STACKED_BUFF_STATS)


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)
        cls.sheet = {int(r["spell_id"]): r for r in read_csv("data/legendary_power_buffs.csv")}

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def test_the_buff(self):
        n = source()
        self.assertEqual({BUFF: (FLESHRAKE, "skill_damage_pct", "dummy")},
                         {s: (r["owner"], r["stat"], r["aura"]) for s, r in self.sheet.items() if r["owner"] == FLESHRAKE})
        self.assertEqual(("6", "4", "1"), tuple(self.field(BUFF, c) for c in ("Effect_1", "EffectAura_1", "ImplicitTargetA_1")))
        self.assertEqual(("0", "0"), (self.field(BUFF, "EffectBasePoints_1"), self.field(BUFF, "EffectDieSides_1")))   # the roll is not in the record
        self.assertEqual(str(n["most"]), self.field(BUFF, "CumulativeAura"))           # the client shows the total of the stacks
        self.assertEqual(self.field(83411, "DurationIndex"), self.field(BUFF, "DurationIndex"))   # infinite: the module sets the 1 s
        self.assertEqual(("0", "0", "0"), (self.field(BUFF, "Effect_2"), self.field(BUFF, "Effect_3"), self.field(BUFF, "Mechanic")))
        self.assertFalse(int(self.field(BUFF, "Attributes")) & 0x04000000)            # a buff, not a debuff
        self.assertEqual("Dashing Strike damage increased.", records.unquote(self.field(BUFF, "AuraDescription_Lang_enUS")))
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn('{83564, "P41_Unique_Fist_007", "skill_damage_pct"},', header)
        # The newest full spell render carries the record combat_0103 brought unchanged, field for field; nothing is asserted about its other
        # records, so a later render of another record leaves this green.
        render = newest_spell_render(MODULE / "data/sql/db-world/updates").read_text(encoding="utf-8")
        migration = MODULE / "data/sql/db-world/updates/combat_0106_fleshrake_dashing_strike_buff.sql"
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
        stacked = "stack_buff=1;@%s/%g/%d;" % (FLESHRAKE, n["seconds"], n["most"])
        # worn: every cast of Dashing Strike fires one stack, a proc coefficient does not scale it, no cooldown; a hit of it, another
        # skill, or not worn: nothing
        out += clear + [(T("wears", FLESHRAKE, 0), None)] + [(T("fire", "cast", DASH, 1, 50, 0), stacked)] * 3
        out += [(T("fire", "cast", DASH, 0.25, 99, 0), stacked), (T("fire", "cast", "Cyclone Strike", 1, 50, 0), "")]
        out += [(T("fire", "hit", DASH, 1, 50, 0), "")]
        out += clear + [(T("fire", "cast", DASH, 1, 50, 0), "")]
        # the damage: the item's roll per stack, 1 + stacks x N/100, for Dashing Strike alone
        roll = 90.0
        out += clear + [(T("wears", FLESHRAKE, 0), None), (T("value", FLESHRAKE, DASH, "skill_damage_pct", roll), None)]
        for stacks in range(0, n["most"] + 1):
            out += [(T("stackskill", DASH, "skill_damage_pct", 1, 1, FLESHRAKE, stacks), "%g" % (1 + stacks * roll / 100)),
                    (T("stackskill", OTHER, "skill_damage_pct", 1, 1, FLESHRAKE, stacks), "1"),         # another skill's hit
                    (T("stackfactor", "skill_damage_pct", 1, 1, FLESHRAKE, stacks), "1")]               # the unnamed-skill reader: not a skill's
        out += [(T("stackskill", DASH, "skill_damage_pct", 1, 0), "1"),                                 # no record on the player
                (T("stackskill", DASH, "skill_damage_pct", 1, 1, ORB, 4), "1"),                         # another owner's stacks
                (T("stackskill", DASH, "damage_dealt_pct", 1, 1, FLESHRAKE, 4), "1")]                   # another stat
        # Orb of Infinite Depth's buff names no skill: the skill reader leaves it alone and the plain reader still reads it
        out += clear + [(T("wears", ORB, 0), None), (T("value", ORB, "", "damage_dealt_pct", 9.0), None),
                        (T("stackskill", DASH, "damage_dealt_pct", 1, 1, ORB, 4), "1"),
                        (T("stackfactor", "damage_dealt_pct", 1, 1, ORB, 4), "%g" % (1 + 4 * 9.0 / 100))]
        # no stored roll: no damage; not worn: nothing
        out += clear + [(T("wears", FLESHRAKE, 0), None), (T("stackskill", DASH, "skill_damage_pct", 1, 1, FLESHRAKE, 5), "1")]
        out += clear + [(T("stackskill", DASH, "skill_damage_pct", 1, 1, FLESHRAKE, 5), "1")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = events.Rules.build(header_text, "fleshrake-" + name)
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
            "any_skill": real.replace("row.stat == stat && row.skill == skill &&", "row.stat == stat &&"),
            "only_named_skills": real.replace("row.stat == stat && row.skill == skill &&", "row.stat == stat && !row.skill.empty() &&"),
            "not_per_stack": real.replace(line, "factor *= 1.0 + sign * number / 100.0;"),
            "not_the_roll": real.replace(line, "factor *= 1.0 + sign * held->second * row.min / 100.0;"),
            "any_owner": real.replace("auto held = stacks.find(row.owner);", "auto held = stacks.begin();"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


class Hooks(unittest.TestCase):
    """Source-text guards: what the server .cpp files must call, in what order."""

    @classmethod
    def setUpClass(cls):
        cls.readers = (SRC / "combat/dc_item_powers_readers.cpp").read_text(encoding="utf-8")
        cls.combat = (SRC / "combat/dc_combat.cpp").read_text(encoding="utf-8")

    def test_the_skill_reader_reads_the_stacks_of_the_record(self):
        start = self.readers.index("double StackedSkillFactor(Player const* player, std::string const& skill)")
        body = self.readers[start:self.readers.index("double PetSpeedFactor(", start)]
        self.assertLess(body.index("BuffStacks(player);"), body.index("std::lock_guard<std::mutex> lock(mutex);"))   # auras before the lock
        self.assertIn('ItemPower::StackedFactor(Data().rows, CountsOf(guid), stacks, "skill_damage_pct", 1.0, SituationOf(guid, std::move(seen)), skill)', body)

    def test_the_hit_multiplies_by_it_for_its_skill(self):
        self.assertIn('hit.legendary *= ItemPowers::StackedSkillFactor(player, petName);', self.combat)
        # the plain reader leaves a skill buff alone (its rows name a skill, DealtFactor's name none)
        self.assertIn('"damage_dealt_pct", 1.0, situation)', self.readers)


if __name__ == "__main__":
    unittest.main()

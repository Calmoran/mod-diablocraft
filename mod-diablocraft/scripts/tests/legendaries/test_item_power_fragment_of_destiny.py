"""Legendary rest, bead diablocraft-d1lq1: Fragment of Destiny (wand, Wizard), N-STACKBUFF (Orb of Infinite Depth's) and N-COUNTREAD (a skill's damage read from another skill's stacks).

  "Your Signature Spells attack 50% faster and deal triple damage. You gain a Spectral buff whenever you land an attack with a Signature Spell. Hydras deal [20-30]% increased damage for
  each Spectral stack. Max 10 stacks."
  * the text and numbers are the catalogue row's; the roll 0.2-0.3 is the item's own (decode_pow.py item P610_Unique_Wand_010; the power file is not in the archives); the table
    (data/legendary_powers.csv) holds FOUR rows for the pool item: `attack_speed_pct` 50 and `damage_increase_pct` 200 on the four Signature Spells, the `stack_buff` effect
    (1 stack, at most 10, fired once per cast that hit) and the `buff` row `skill_damage_pct` 20-30 on Hydra; the record 83565 "Spectral" is in data/legendary_power_buffs.csv, in the
    generated spell shells, in the combat_0110 render and in the client Spell.dbc of the committed patch-4.MPQ (test_spell_records and test_combat_fixes_xecwl);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses the stack buff without its buff row
    and the skill buff on no skill, on two, or on a skill the sheets do not know;
  * the production rules (src/combat/dc_item_power_math.h: SkillFactor, StackedFactor with a skill, Fire's hit_generator) are compiled and driven with the generated rows: the four spells
    swing 1.5 times as fast and hit x3, Hydra neither; a Signature attack that hit adds a stack, Hydra's, a Cleave's and a hit event's do not; Hydra's damage is
    1 + stacks x N/100 with the item's stored roll, only while worn; mutants fail the same driver. The in-game steps are in docs/test-diablocraft-d1lq1.md.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import item_power_mark_and_stack_support as support  # noqa: E402
from item_power_mark_and_stack_support import (BLANK, MATH, MODULE, REPO, T, function_body, g, mine, read_csv, render_rows, sheet_row)  # noqa: E402


def drive(cases, header_text, name):
    return support.drive(cases, header_text, name, lambda *args, **kwargs: harness_env.run(*args, **kwargs))


OWNER = "P610_Unique_Wand_010"
SIGNATURE = "Magic Missile;Shock Pulse;Spectral Blade;Electrocute"
FOUR = SIGNATURE.split(";")
HYDRA = "Hydra"
BUFF = 83565


class Table(unittest.TestCase):
    def test_the_catalogue_says_the_numbers(self):
        catalogue = [r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual("Your Signature Spells attack 50% faster and deal triple damage. You gain a Spectral buff whenever you land an attack with a Signature Spell. "
                         "Hydras deal [20-30]% increased damage for each Spectral stack. Max 10 stacks.", catalogue[0]["power_text"])
        for skill in FOUR + [HYDRA]:
            self.assertIn(skill, [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")])

    def test_four_rows_hold_them(self):
        self.assertEqual(sorted([(OWNER, 0, "skill", SIGNATURE, "attack_speed_pct", 50.0, 50.0, *BLANK),
                                 (OWNER, 0, "skill", SIGNATURE, "damage_increase_pct", 200.0, 200.0, *BLANK),
                                 (OWNER, 0, "effect", "", "stack_buff", 1.0, 1.0, "", 0.0, "", 3.0, 10, "hit_generator", SIGNATURE, 100.0, 0.0),
                                 (OWNER, 0, "buff", HYDRA, "skill_damage_pct", 20.0, 30.0, *BLANK)]), sorted(mine(OWNER)))

    def test_the_stack_seconds_are_a_marked_placeholder(self):
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == "stack_buff")
        self.assertIn("PLACEHOLDER", row["note"])

    def test_the_record_is_in_every_place_it_must_be(self):
        record = next(r for r in read_csv("data/legendary_power_buffs.csv") if r["spell_id"] == str(BUFF))
        self.assertEqual((OWNER, "skill_damage_pct", "dummy", "Spectral"), (record["owner"], record["stat"], record["aura"], record["name"]))
        shells = read_csv("data/generated/spell_shells.csv")
        self.assertEqual("power_buff", next(r for r in shells if r["spell_id"] == str(BUFF))["kind"])
        migration = max((MODULE / "data/sql/db-world/updates").glob("combat_*fragment_of_destiny*.sql"))
        self.assertIn("83565", migration.read_text(encoding="utf-8"))


class Generator(unittest.TestCase):
    STACK = sheet_row(OWNER, "effect", "stack_buff", "1", stack_seconds="3", stack_max="10", fire_on="hit_generator", fire_skills=SIGNATURE)
    BUFF = sheet_row(OWNER, "buff", "skill_damage_pct", "20", "30", skill=HYDRA)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len(mine(OWNER, render_rows(OWNER, self.STACK, self.BUFF))))

    def test_it_refuses_what_it_cannot_carry(self):
        stack, buff = self.STACK, self.BUFF
        refused = {
            "no stack buff": ([buff], "needs the stack_buff effect row"),
            "no skill named": ([stack, {**buff, "skill": ""}], "(a skill is named|skill_damage_pct names one skill)"),
            "not a skill": ([stack, {**buff, "skill": "Hydrah"}], "(skill_damage_pct names one skill|not a skill)"),
            "two skills": ([stack, {**buff, "skill": "Hydra;Meteor"}], "(skill_damage_pct names one skill|listed twice|only a skill row)"),
            "a loss": ([stack, {**buff, "value_min": "-20", "value_max": "-20"}], "needs 0|a buff row"),
            "a stack with no seconds": ([{**stack, "stack_seconds": ""}, buff], "stack_buff is an item"),
            "a stack with no maximum": ([{**stack, "stack_max": ""}, buff], "stack_buff is an item"),
        }
        for name, (rows, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    render_rows(OWNER, *rows)


class Rules(unittest.TestCase):
    OTHER = ("Other Wand", 0, "buff", HYDRA, "skill_damage_pct", 1.0, 100.0, *BLANK)
    ODD = ("Odd Wand", 0, "buff", "Meteor", "skill_damage_pct", 50.0, 50.0, *BLANK)

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows + [self.OTHER, self.ODD]]
        clear = (T("clear"), None)
        worn = [clear, (T("wears", OWNER), None)]
        # not worn: nothing
        out += [clear, (T("skillfactor", "Magic Missile", "damage_increase_pct"), "1"), (T("skillfactor", "Magic Missile", "attack_speed_pct"), "1"),
                (T("stacked", OWNER, 10, "skill_damage_pct", 1, HYDRA), "1"), (T("fire", "hit_generator", "Magic Missile", 0, 1), "-")]
        # worn: the four Signature Spells hit x3 and swing x1.5, nothing else does
        for skill in FOUR:
            out += worn + [(T("skillfactor", skill, "damage_increase_pct"), "3"), (T("skillfactor", skill, "attack_speed_pct"), "1.5")]
        for skill in (HYDRA, "Meteor", "Arcane Orb", "Archon", ""):
            out += worn + [(T("skillfactor", skill, "damage_increase_pct"), "1"), (T("skillfactor", skill, "attack_speed_pct"), "1")]
        # an attack of a Signature Spell that hit adds a stack, once; Hydra's, another skill's and another event's do not
        for skill in FOUR:
            out += worn + [(T("fire", "hit_generator", skill, 0, 1), "stack_buff:1")]
        for event, skill in (("hit_generator", HYDRA), ("hit_generator", "Meteor"), ("hit_spender", "Magic Missile"), ("hit", "Magic Missile"), ("cast", "Magic Missile"), ("kill", "")):
            out += worn + [(T("fire", event, skill, 0, 1), "-")]
        # Hydra's damage: 1 + stacks x N/100 with the item's roll, for each end of the roll; none without stacks
        for roll in (20, 25, 30):
            out += worn + [(T("stacked", OWNER, 0, "skill_damage_pct", 1, HYDRA), "1")]
            for stacks in (1, 5, 10):
                out += [clear, (T("wears", OWNER), None), (T("stored", OWNER, HYDRA, "skill_damage_pct", roll), None),
                        (T("stacked", OWNER, stacks, "skill_damage_pct", 1, HYDRA), g(1 + stacks * roll / 100))]
        # only Hydra reads them; only the owner's stacks
        out += [clear, (T("wears", OWNER), None), (T("stored", OWNER, HYDRA, "skill_damage_pct", 30), None),
                (T("stacked", OWNER, 10, "skill_damage_pct", 1, "Meteor"), "1"), (T("stacked", OWNER, 10, "skill_damage_pct", 1, "Magic Missile"), "1"),
                (T("stacked", "Other Wand", 10, "skill_damage_pct", 1, HYDRA), "1")]
        # the Wizard's other item's buff on Hydra is a multiplier of its own
        out += [clear, (T("wears", OWNER), None), (T("stored", OWNER, HYDRA, "skill_damage_pct", 30), None), (T("wears", "Other Wand"), None), (T("stored", "Other Wand", HYDRA, "skill_damage_pct", 10), None),
                (T("stacked", "Other Wand", 5, "skill_damage_pct", 1, HYDRA), g(1.5))]
        return out

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = drive(self.cases(mine(OWNER)), MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine(OWNER)
        self.assertEqual(4, len(rows))
        want, _ = drive(self.cases(rows), real, "want")
        by = lambda stat: [r for r in rows if r[4] == stat]  # noqa: E731
        speed, damage, stack, buff = by("attack_speed_pct"), by("damage_increase_pct"), by("stack_buff"), by("skill_damage_pct")
        row_mutants = {
            "no_speed": damage + stack + buff,
            "speed_100": [r[:5] + (100.0, 100.0) + r[7:] for r in speed] + damage + stack + buff,
            "no_triple": speed + stack + buff,
            "double_not_triple": speed + [r[:5] + (100.0, 100.0) + r[7:] for r in damage] + stack + buff,
            "hydra_as_signature": [r[:3] + (SIGNATURE + ";Hydra",) + r[4:] for r in speed + damage] + stack + buff,
            "three_signatures": [r[:3] + ("Magic Missile;Shock Pulse;Spectral Blade",) + r[4:] for r in speed + damage] + stack + buff,
            "no_stack": speed + damage + buff,
            "stack_on_hydra": speed + damage + [r[:13] + ("Hydra",) + r[14:] for r in stack] + buff,
            "stack_per_hit": speed + damage + [r[:12] + ("hit",) + r[13:] for r in stack] + buff,
            "no_buff": speed + damage + stack,
            "buff_on_meteor": speed + damage + stack + [r[:3] + ("Meteor",) + r[4:] for r in buff],
            "buff_range_fixed": speed + damage + stack + [r[:6] + (r[5],) + r[7:] for r in buff],
            "the_wrong_owner": [("Other Wand",) + r[1:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = drive(self.cases(mutant_rows), real, name)
                self.assertNotEqual(want, got, name + " survived")
        stacked = function_body(real, "inline double StackedFactor(")
        rules = {
            "stacks_added_once": (stacked, "held->second * number / 100.0", "number / 100.0"),
            "percent_as_a_fraction": (stacked, "held->second * number / 100.0", "held->second * number"),
            "any_skill": (stacked, "row.skill == skill &&", ""),
            "any_owner": (stacked, "auto held = stacks.find(row.owner);", "auto held = stacks.begin();"),
            "a_loss": (stacked, "1.0 + sign *", "1.0 - sign *"),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                try:
                    _, got = drive(self.cases(rows), real.replace(where, where.replace(old, new, 1)), name)
                except AssertionError:
                    continue   # a mutant that does not compile is caught too
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()

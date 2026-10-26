"""Legendary rest, bead diablocraft-ggvdt: Madawc's Sorrow (two-hand mighty weapon, Barbarian), builds N-MARK (a per-enemy mark of the players who have hit it) on N-STUN.

  "Stun enemies for 2 seconds the first time you hit them."
  * the text is d3planner's (item_twohand.js, leg_madawcssorrow, no number) and the catalogue row's; the numbers are the power file's (decode_pow.py power ItemPassive_Unique_Ring_562_x1:
    SF_0 'Stun Proc Chance' 1, SF_1 'Stun Duration' 2); the table (data/legendary_powers.csv) holds ONE `effect` row for the pool item: `stun_seconds` 2 fired on a `hit` of any
    skill under the new condition `first_hit_on_target`;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses the condition on anything but
    a stun effect, with a set level, an event other than a hit, a cond_arg or a skill, and refuses a stun with another condition;
  * the production rules (src/combat/dc_item_power_math.h: Fire's `first_hit_on_target` test, FirstHit, MarksFirstHits, ControlSpell) are compiled and driven with the generated row:
    the stun fires on the first hit of an enemy and on no later one, only on a hit event, only while the item is worn, one mark per creature and player; mutants of the rules and of the
    row fail the same driver; source guards on the marking (dc_item_powers_effects.cpp Fire) and the executor follow. The in-game steps are in docs/test-diablocraft-ggvdt.md.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import item_powers_source  # noqa: E402
import item_power_mark_and_stack_support as support  # noqa: E402
from item_power_mark_and_stack_support import (BLANK, MATH, T, function_body, mine, read_csv, render_rows, sheet_row)  # noqa: E402


def drive(cases, header_text, name):
    return support.drive(cases, header_text, name, lambda *args, **kwargs: harness_env.run(*args, **kwargs))


OWNER = "Unique_Mighty_2H_101_x1"
STAT, COND = "stun_seconds", "first_hit_on_target"
ROOT_HOLD, STUN_HOLD, FREEZE_HOLD = 64695, 853, 15878


class Table(unittest.TestCase):
    def test_the_sources_say_stun_two_seconds_the_first_time(self):
        catalogue = [r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual("Stun enemies for 2 seconds the first time you hit them.", catalogue[0]["power_text"])
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        for cited in ("SF_0 'Stun Proc Chance' = 1", "SF_1 'Stun Duration' = 2"):
            self.assertIn(cited, row["source"])

    def test_one_effect_row_holds_them(self):
        self.assertEqual([(OWNER, 0, "effect", "", STAT, 2.0, 2.0, COND, 0.0, "", 0.0, 0, "hit", "", 100.0, 0.0)], mine(OWNER))


class Generator(unittest.TestCase):
    BASE = sheet_row(OWNER, "effect", STAT, "2", cond=COND, fire_on="hit")

    def test_the_real_row_passes(self):
        self.assertEqual(1, len(mine(OWNER, render_rows(OWNER, self.BASE))))

    def test_it_refuses_what_it_cannot_carry(self):
        base = self.BASE
        refused = {
            "the condition on a root": ({**base, "stat": "root_seconds"}, "first_hit_on_target is an item"),
            "the condition on a player row": (sheet_row(OWNER, "player", "damage_dealt_pct", "5", cond=COND), "first_hit_on_target is an item"),
            "a set level": ({**base, "owner": "Immortal King's Call", "pieces": "4"}, "first_hit_on_target is an item|stun_seconds is an item"),
            "another event": ({**base, "fire_on": "kill"}, "first_hit_on_target is an item|stun_seconds is an item"),
            "a cond_arg": ({**base, "cond_arg": "2"}, "takes no cond_arg"),
            "a stun under another condition": ({**base, "cond": "enemies_hit_at_most", "cond_arg": "3"}, "enemies_hit_at_most is an effect row"),
            "a range": ({**base, "value_max": "3"}, "stun_seconds is an item"),
            "no seconds": ({**base, "value_min": "0", "value_max": "0"}, "needs 0 < value_min|stun_seconds is an item"),
        }
        for name, (row, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    render_rows(OWNER, row)

    def test_a_stun_with_no_condition_is_every_hit(self):
        # the stun effect is not the Madawc's alone: without the condition it fires on every hit, like the root of Hellrack
        self.assertEqual(1, len(mine(OWNER, render_rows(OWNER, {**self.BASE, "cond": ""}))))


class Rules(unittest.TestCase):
    OTHER = ("Other Axe", 0, "effect", "", STAT, 2.0, 2.0, "", 0.0, "", 0.0, 0, "hit", "", 100.0, 0.0)   # a stun on every hit: not a first hit

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows + [self.OTHER]]
        clear = (T("clear"), None)
        worn = [clear, (T("wears", OWNER), None)]
        # not worn: nothing, first hit or not
        out += [clear, (T("fire", "hit", "Bash", 1, 1), "-"), (T("marks"), "0")]
        # worn: the first hit of an enemy, of any skill, stuns for the item's 2 seconds; a later hit does not
        for skill in ("Bash", "Cleave", "Earthquake", ""):
            out += worn + [(T("fire", "hit", skill, 1, 1), "stun_seconds:2"), (T("fire", "hit", skill, 0, 1), "-")]
        # only the hit event (a kill, a cast, a hit taken are not hits)
        for event in ("kill", "cast", "taken", "hit_spender", "hit_generator", "tick"):
            out += worn + [(T("fire", event, "Bash", 1, 1), "-")]
        # the item marks while worn; another stat does not
        out += worn + [(T("marks"), "1")]
        out += [clear, (T("wears", "Other Axe"), None), (T("marks"), "0")]
        # the other axe's stun (no condition) fires on a later hit as well, the Madawc's does not: both worn, a later hit gives one stun
        out += worn + [(T("wears", "Other Axe"), None), (T("fire", "hit", "Bash", 0, 1), "stun_seconds:2"), (T("fire", "hit", "Bash", 1, 1), "stun_seconds:2,stun_seconds:2")]
        # one mark per creature and player
        out += [(T("first", "wolf", 1), "1"), (T("first", "wolf", 1), "0"), (T("first", "wolf", 2), "1"), (T("first", "boar", 1), "1"), (T("first", "boar", 1), "0"), (T("first", "wolf", 2), "0")]
        # the stun is a stun hold of its own, not the root's nor Torment's freeze hold
        out += [(T("control", "stun_seconds"), str(STUN_HOLD)), (T("control", "root_seconds"), str(ROOT_HOLD)), (T("control", "charm_seconds"), "0")]
        return out

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = drive(self.cases(mine(OWNER)), MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)
        self.assertNotIn(str(FREEZE_HOLD), want)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine(OWNER)
        want, _ = drive(self.cases(rows), real, "want")
        row_mutants = {
            "no_condition": [r[:7] + ("",) + r[8:] for r in rows],
            "four_seconds": [r[:5] + (4.0, 4.0) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("root_seconds",) + r[5:] for r in rows],
            "another_event": [r[:12] + ("kill",) + r[13:] for r in rows],
            "the_wrong_owner": [("Other Axe",) + r[1:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = drive(self.cases(mutant_rows), real, name)
                self.assertNotEqual(want, got, name + " survived")
        first = function_body(real, "inline bool FirstHit(")
        marks = function_body(real, "inline bool MarksFirstHits(")
        rules = {
            "every_hit_is_first": (first, "return hitBy.insert(player).second;", "return true;"),
            "never_first": (first, "return hitBy.insert(player).second;", "return false;"),
            "not_marked": (first, "return hitBy.insert(player).second;", "return hitBy.count(player) == 0;"),
            "marks_unworn": (marks, "Owned(row, counts, situation, number)", "true"),
            "marks_any_condition": (marks, 'row.cond == "first_hit_on_target" &&', ""),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                _, got = drive(self.cases(rows), real.replace(where, where.replace(old, new, 1)), name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "first_hit_test_lost": real.replace('            if (row.cond == "first_hit_on_target" && !situation.firstHit)\n                continue;\n', ""),
            "first_hit_inverted": real.replace('row.cond == "first_hit_on_target" && !situation.firstHit', 'row.cond == "first_hit_on_target" && situation.firstHit'),
            "stun_is_the_root": real.replace('stat == "stun_seconds" ? StunHold : ', 'stat == "stun_seconds" ? RootHold : '),
            "stun_is_the_freeze_hold": real.replace('stat == "stun_seconds" ? StunHold : ', 'stat == "stun_seconds" ? FreezeHold : ') if False else real.replace("constexpr std::uint32_t StunHold = 853;", "constexpr std::uint32_t StunHold = 15878;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                try:
                    _, got = drive(self.cases(rows), header, name)
                except AssertionError:
                    continue   # a mutant that does not compile is caught too
                self.assertNotEqual(want, got, name + " survived")


class Server(unittest.TestCase):
    """Text guards on the marking and the executor. Nothing here runs the worldserver; the in-game steps are in the test sheet."""

    def failures(self, effects, powers):
        wrong = []

        def need(why, ok):
            if not ok:
                wrong.append(why)

        need("the mark is a list of the players on the creature, in its own data", "struct HitBy : DataMap::Base\n        {\n            std::set<std::uint64_t> players;\n        };" in effects)
        need("only a hit event of a worn item that stuns first hits marks, on a creature (never a player)",
             'if (markable && std::string_view(event) == "hit" && Data().marks && ItemPower::MarksFirstHits(Data().rows, CountsOf(guid), situation))' in effects
             and "Creature* const markable = target ? target->ToCreature() : nullptr;" in effects)
        need("the first hit is the production rule over the creature's list, handed to the rows through the situation",
             'situation.firstHit = ItemPower::FirstHit(markable->CustomData.GetDefault<HitBy>("DCItemHitBy")->players, guid);' in effects)
        need("the marking is under the lock with the situation it fills", effects.find("situation.firstHit =") > effects.find("ItemPower::Situation situation = SituationOf(guid, std::move(seen));") > 0)
        need("the stun is the executor's Control with the stock stun hold, stretched by the stun-duration powers",
             'else if (one.stat == "stun_seconds" && target)\n                    Control(player, target, ItemPower::ControlSpell(one.stat), one.value * StunFactor(player));' in effects)
        need("a row that stuns first hits turns the marking on", 'loaded.marks = loaded.marks || row.cond == "first_hit_on_target";' in powers)
        return wrong

    def parts(self):
        return [(item_powers_source.FOLDER / "dc_item_powers_effects.cpp").read_text(encoding="utf-8"), item_powers_source.CPP.read_text(encoding="utf-8")]

    def test_the_server_marks_and_stuns_as_the_rules_say(self):
        self.assertEqual([], self.failures(*self.parts()))

    def test_the_text_mutants_are_caught(self):
        parts = self.parts()
        mutants = {
            "not_in_its_own_data": (0, 'GetDefault<HitBy>("DCItemHitBy")->players', 'GetDefault<HitBy>("DCItemHitBy")->players'.replace("HitBy", "HitBy2")),
            "marks_every_event": (0, 'std::string_view(event) == "hit" && Data().marks', 'Data().marks'),
            "marks_when_nothing_wants_it": (0, " && Data().marks && ItemPower::MarksFirstHits(", " && ItemPower::MarksFirstHits("),
            "marks_without_the_item": (0, " && ItemPower::MarksFirstHits(Data().rows, CountsOf(guid), situation))", ")"),
            "marks_players": (0, "Creature* const markable = target ? target->ToCreature() : nullptr;", "Creature* const markable = nullptr;"),
            "first_not_handed_on": (0, "situation.firstHit = ItemPower::FirstHit(", "ItemPower::FirstHit("),
            "stun_not_stretched": (0, "ItemPower::ControlSpell(one.stat), one.value * StunFactor(player)", "ItemPower::ControlSpell(one.stat), one.value"),
            "stun_not_executed": (0, 'else if (one.stat == "stun_seconds" && target)', 'else if (one.stat == "stun_seconds" && !target)'),
            "flag_never_set": (1, 'loaded.marks = loaded.marks || row.cond == "first_hit_on_target";', ""),
        }
        for name, (which, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, parts[which], name + " does not apply")
                mutated = list(parts)
                mutated[which] = parts[which].replace(old, new, 1)
                self.assertNotEqual(parts, mutated)
                self.assertTrue(self.failures(*mutated), name + " survived")


if __name__ == "__main__":
    unittest.main()

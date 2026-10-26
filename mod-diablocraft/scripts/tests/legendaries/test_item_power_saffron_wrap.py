"""Legendary rest, bead diablocraft-5o0j5: Saffron Wrap (belt, Barbarian), builds N-NEXT (a stack one cast leaves and the next cast of the skill spends).

  "The damage of your next Overpower is increased by [40-50]% for each enemy hit. Max 20 enemies."
  * the text and range are d3planner's (item_waist.js, P43_Unique_Belt_001_x1, leg_saffronwrap, min 40 max 50) and the catalogue row's; the buff's 3 seconds are the power file's
    (decode_pow.py power P43_ItemPassive_Unique_Ring_001: SF_1 'Buff Duration' 3); the table (data/legendary_powers.csv) holds THREE `skill` rows on Overpower for the pool item:
    `damage_per_enemy_hit_pct` 40-50 (rolled once per item) and the fixed `enemy_hit_stacks_max` 20 and `enemy_hit_stack_seconds` 3;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses each stat on another skill, with a
    condition, an event or a set level, and any of the three without the others;
  * the production rules (src/combat/dc_item_power_math.h: EnemyPress, EnemyConnect, PerStackFactor) are compiled and driven with the generated rows: the factor is 1 + N/100 x the
    stacks with the item's stored roll, only while worn and only on Overpower; the enemies a cast hit ride on the next cast pressed within 3 s and are spent by it, at most 20, and a cast
    that hit nothing leaves the stack as it was; mutants of the rules and of the rows fail the same driver; source guards on the three calls (the press, the connect, the hit) follow.
    The in-game steps are in docs/test-diablocraft-5o0j5.md.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import item_powers_source  # noqa: E402
import item_power_mark_and_stack_support as support  # noqa: E402
from item_power_mark_and_stack_support import (BLANK, MATH, MODULE, REPO, T, function_body, g, mine, read_csv, render_rows, sheet_row)  # noqa: E402


def drive(cases, header_text, name):
    return support.drive(cases, header_text, name, lambda *args, **kwargs: harness_env.run(*args, **kwargs))


OWNER = "P43_Unique_Belt_001_x1"
SKILL = "Overpower"
PER, MOST, SECONDS = "damage_per_enemy_hit_pct", "enemy_hit_stacks_max", "enemy_hit_stack_seconds"


def planner():
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_sources_say_40_to_50_per_enemy_max_20(self):
        text, low, high = planner()
        self.assertEqual("The damage of your next Overpower is increased by %d%% for each enemy hit. Max 20 enemies.", text)
        self.assertEqual((40.0, 50.0), (low, high))
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == SECONDS)
        self.assertIn("SF_1 'Buff Duration' = 3", row["source"])
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])

    def test_three_skill_rows_hold_them(self):
        _, low, high = planner()
        self.assertEqual(sorted([(OWNER, 0, "skill", SKILL, PER, low, high, *BLANK), (OWNER, 0, "skill", SKILL, MOST, 20.0, 20.0, *BLANK),
                                 (OWNER, 0, "skill", SKILL, SECONDS, 3.0, 3.0, *BLANK)]), sorted(mine(OWNER)))


class Generator(unittest.TestCase):
    PER_ROW = sheet_row(OWNER, "skill", PER, "40", "50", skill=SKILL)
    MOST_ROW = sheet_row(OWNER, "skill", MOST, "20", skill=SKILL)
    SECONDS_ROW = sheet_row(OWNER, "skill", SECONDS, "3", skill=SKILL)

    def test_the_real_rows_pass(self):
        self.assertEqual(3, len(mine(OWNER, render_rows(OWNER, self.PER_ROW, self.MOST_ROW, self.SECONDS_ROW))))

    def test_it_refuses_what_it_cannot_carry(self):
        per, most, seconds = self.PER_ROW, self.MOST_ROW, self.SECONDS_ROW
        refused = {
            "another skill": ([{**per, "skill": "Frenzy"}, {**most, "skill": "Frenzy"}, {**seconds, "skill": "Frenzy"}], "for \\('Overpower',\\) only"),
            "a condition": ([{**per, "cond": "quiet_stacks", "cond_arg": "2", "stack_seconds": "1", "stack_max": "2"}, most, seconds], "simply on"),
            "an event": ([{**per, "fire_on": "kill"}, most, seconds], "simply on|an event fires"),
            "a set level": ([{**per, "owner": "Immortal King's Call", "pieces": "4", "value_max": "40"}, most, seconds], "simply on"),
            "a rolled maximum": ([per, {**most, "value_max": "30"}, seconds], "one fixed number"),
            "a fractional maximum": ([per, {**most, "value_min": "2.5", "value_max": "2.5"}, seconds], "whole number"),
            "no maximum": ([per, seconds], "go together"),
            "no seconds": ([per, most], "go together"),
            "the maximum alone": ([most], "go together"),
        }
        for name, (rows, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    render_rows(OWNER, *rows)


class Rules(unittest.TestCase):
    OTHER = ("Other Belt", 0, "skill", SKILL, PER, 1.0, 100.0, *BLANK)    # a second source, ranged: the driver sets its stored roll
    ODD = ("Odd Belt", 0, "skill", SKILL, "damage_increase_pct", 90.0, 90.0, *BLANK)

    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows + [self.OTHER, self.ODD]]
        clear = (T("clear"), None)
        wear = lambda roll: [clear, (T("wears", OWNER), None), (T("stored", OWNER, SKILL, PER, roll), None)]  # noqa: E731
        # not worn: nothing, however many stacks
        out += [clear, (T("perstack", SKILL, PER, 5), "1"), (T("stored", OWNER, SKILL, PER, high), None), (T("perstack", SKILL, PER, 5), "1")]
        # worn, each end of the roll: 1 + N/100 x the stacks, 1 with none
        for roll in (low, 45, high):
            out += wear(roll)
            for stacks in (0, 1, 5, 20):
                out += [(T("perstack", SKILL, PER, stacks), g(1 + roll / 100 * stacks))]
        # only Overpower; only this stat
        out += wear(high) + [(T("perstack", "Cleave", PER, 5), "1"), (T("perstack", "", PER, 5), "1"), (T("perstack", SKILL, "damage_increase_pct", 5), "1")]
        # two sources multiply: 50% and 20% a stack, 4 stacks
        out += wear(high) + [(T("wears", "Other Belt"), None), (T("stored", "Other Belt", SKILL, PER, 20), None), (T("perstack", SKILL, PER, 4), g((1 + high / 100 * 4) * (1 + 0.2 * 4)))]
        # another stat of another item is not this one
        out += [clear, (T("wears", "Odd Belt"), None), (T("perstack", SKILL, PER, 5), "1")]
        # the stack: a cast leaves the enemies it hit; the next cast pressed within 3 s rides on them and leaves none
        out += [(T("reset"), None), (T("connect", 5, 20, 1000), None), (T("riding"), "0 5 1000"),
                (T("press", 3999, 3), None), (T("riding"), "5 0 0"),
                (T("connect", 3, 20, 4100), None), (T("riding"), "5 3 4100"),    # this cast's own enemies are carried, the ones it rode on stay until the next press
                (T("press", 4200, 3), None), (T("riding"), "3 0 0")]
        # a press just late is empty: 3001 ms after the last hit
        out += [(T("reset"), None), (T("connect", 5, 20, 1000), None), (T("press", 4000, 3), None), (T("riding"), "5 0 0"),
                (T("reset"), None), (T("connect", 5, 20, 1000), None), (T("press", 4001, 3), None), (T("riding"), "0 0 0")]
        # the most that count; a cast that hit nothing changes nothing; a press with nothing carried rides on nothing
        out += [(T("reset"), None), (T("connect", 30, 20, 500), None), (T("riding"), "0 20 500"), (T("connect", 0, 20, 900), None), (T("riding"), "0 20 500"),
                (T("reset"), None), (T("press", 500, 3), None), (T("riding"), "0 0 0")]
        # a later cast's enemies replace the carried ones, they do not add
        out += [(T("reset"), None), (T("connect", 4, 20, 100), None), (T("connect", 3, 20, 200), None), (T("riding"), "0 3 200")]
        # spent: pressed twice with no cast between, the second rides on nothing
        out += [(T("reset"), None), (T("connect", 4, 20, 100), None), (T("press", 200, 3), None), (T("press", 300, 3), None), (T("riding"), "0 0 0")]
        # the clock wrapping past 2^32 is no break
        out += [(T("reset"), None), (T("connect", 6, 20, 4294966000), None), (T("press", 1000, 3), None), (T("riding"), "6 0 0"),
                (T("reset"), None), (T("connect", 6, 20, 4294966000), None), (T("press", 2000, 3), None), (T("riding"), "0 0 0")]
        # no seconds, no promise
        out += [(T("reset"), None), (T("connect", 5, 20, 100), None), (T("press", 100, 0), None), (T("riding"), "0 0 0")]
        return out

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = drive(self.cases(mine(OWNER)), MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine(OWNER)
        self.assertEqual(3, len(rows))
        want, _ = drive(self.cases(rows), real, "want")
        per = [r for r in rows if r[4] == PER]
        row_mutants = {
            "the_wrong_skill": [r[:3] + ("Cleave",) + r[4:] for r in per],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in per],
            "the_wrong_owner": [("Other Belt",) + r[1:] for r in per],
            "the_range_fixed_at_the_bottom": [r[:6] + (r[5],) + r[7:] for r in per],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = drive(self.cases(mutant_rows), real, name)
                self.assertNotEqual(want, got, name + " survived")
        press = function_body(real, "inline EnemyStack EnemyPress(")
        connect = function_body(real, "inline EnemyStack EnemyConnect(")
        rules = {
            "press_ignores_the_age": (press, "stack.carried > 0 && seconds > 0 && static_cast<std::int32_t>(now - stack.carriedAt) <= static_cast<std::int32_t>(seconds * 1000.0)", "stack.carried > 0"),
            "press_age_exclusive": (press, "<= static_cast<std::int32_t>(seconds * 1000.0)", "< static_cast<std::int32_t>(seconds * 1000.0)"),
            "press_seconds_a_tenth": (press, "seconds * 1000.0", "seconds * 100.0"),
            "press_no_seconds_rides": (press, "seconds > 0 &&", ""),
            "press_keeps_the_carry": (press, "return {fresh ? stack.carried : 0u, 0u, 0u};", "return {fresh ? stack.carried : 0u, stack.carried, stack.carriedAt};"),
            "press_never_rides": (press, "fresh ? stack.carried : 0u", "0u"),
            "connect_unlimited": (connect, "std::min(enemies, most)", "enemies"),
            "connect_empty_resets": (connect, "if (enemies == 0)\n            return stack;", ""),
            "connect_adds": (connect, "stack.carried = std::min(enemies, most);", "stack.carried = std::min(stack.carried + enemies, most);"),
            "connect_time_kept": (connect, "stack.carriedAt = now;", ""),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                _, got = drive(self.cases(rows), real.replace(where, where.replace(old, new, 1)), name)
                self.assertNotEqual(want, got, name + " survived")


class Server(unittest.TestCase):
    """Text guards on the three calls and the table flag. Nothing here runs the worldserver; the in-game steps are in the test sheet."""

    FOLDER = item_powers_source.FOLDER

    def parts(self):
        return [(self.FOLDER / "dc_item_powers_events.cpp").read_text(encoding="utf-8"), (self.FOLDER / "dc_item_powers_clocks.cpp").read_text(encoding="utf-8"),
                (self.FOLDER / "dc_item_powers_readers.cpp").read_text(encoding="utf-8"), (self.FOLDER / "dc_combat.cpp").read_text(encoding="utf-8"),
                item_powers_source.CPP.read_text(encoding="utf-8")]

    def failures(self, events, clocks, readers, combat, powers):
        wrong = []

        def need(why, ok):
            if not ok:
                wrong.append(why)

        need("a pressed skill hands the last cast's enemies to the cast, before the cast's own events", "EnemyStackPress(player, skill->skill);\n        NextAttackPressed(player);\n        Fire(player, \"cast\", skill->skill, 1.0);" in events)
        need("a cast that hit hands its enemies to the next (Combat::Connected, ItemPowers::Attack)", "EnemyStackConnect(player, spellId, enemies);" in events)
        press = clocks[clocks.find("void EnemyStackPress("):] if "void EnemyStackPress(" in clocks else ""
        press = press[:press.find("\n        }\n")] if press else ""
        need("the press is watched only when a row counts enemies, takes the item's seconds and the production rule",
             "if (!Data().enemyStacks)\n                return;" in press and 'SkillSetTo(player, skill, "enemy_hit_stack_seconds", 0.0)' in press
             and "stack = ItemPower::EnemyPress(stack, getMSTime(), seconds);" in press)
        connect = clocks[clocks.find("void EnemyStackConnect("):] if "void EnemyStackConnect(" in clocks else ""
        connect = connect[:connect.find("\n        }\n")] if connect else ""
        need("the connect counts enemies of a skill a row names, at most the item's maximum, by the production rule",
             "if (!Data().enemyStacks || !enemies)\n                return;" in connect and 'SkillSetTo(player, shell->skill, "enemy_hit_stacks_max", 0.0)' in connect
             and "if (most < 1)\n                return;" in connect
             and "stack = ItemPower::EnemyConnect(stack, enemies, static_cast<unsigned>(most), getMSTime());" in connect)
        reader = readers[readers.find("double EnemyStacks("):] if "double EnemyStacks(" in readers else ""
        reader = reader[:reader.find("\n    }\n")] if reader else ""
        need("the reader answers the cast in progress's stacks (riding), 0 when no row counts", "if (!player || !Data().enemyStacks)\n            return 0.0;" in reader
             and "static_cast<double>(found->second.riding)" in reader)
        need("the hit multiplies its legendary term by the per-stack rows over those stacks, once",
             'hit.legendary *= ItemPowers::PerStackFactor(player, petName, "damage_per_enemy_hit_pct", ItemPowers::EnemyStacks(player, petName));' in combat
             and combat.count('"damage_per_enemy_hit_pct"') == 1)
        need("a row that counts enemies turns the counting on", 'loaded.enemyStacks = loaded.enemyStacks || row.stat == "damage_per_enemy_hit_pct";' in powers)
        return wrong

    def test_the_calls_are_where_the_rules_say(self):
        self.assertEqual([], self.failures(*self.parts()))

    def test_the_text_mutants_are_caught(self):
        parts = self.parts()
        mutants = {
            "no_press": (0, "        EnemyStackPress(player, skill->skill);\n", ""),
            "press_after_the_cast_event": (0, "EnemyStackPress(player, skill->skill);\n        NextAttackPressed(player);\n        Fire(player, \"cast\", skill->skill, 1.0);", "NextAttackPressed(player);\n        Fire(player, \"cast\", skill->skill, 1.0);\n        EnemyStackPress(player, skill->skill);"),
            "no_connect": (0, "            EnemyStackConnect(player, spellId, enemies);\n", ""),
            "press_always_watched": (1, "if (!Data().enemyStacks)\n                return;\n            double const seconds", "double const seconds"),
            "press_wrong_seconds": (1, '"enemy_hit_stack_seconds", 0.0', '"enemy_hit_stacks_max", 0.0'),
            "press_not_the_rule": (1, "stack = ItemPower::EnemyPress(stack, getMSTime(), seconds);", "stack.riding = stack.carried;"),
            "connect_no_enemies_test": (1, "if (!Data().enemyStacks || !enemies)", "if (!Data().enemyStacks)"),
            "connect_wrong_maximum": (1, '"enemy_hit_stacks_max", 0.0', '"enemy_hit_stack_seconds", 0.0'),
            "connect_no_skill_test": (1, "if (most < 1)\n                return;", ""),
            "connect_not_the_rule": (1, "stack = ItemPower::EnemyConnect(stack, enemies, static_cast<unsigned>(most), getMSTime());", "stack.carried = enemies;"),
            "reader_answers_the_carry": (2, "static_cast<double>(found->second.riding)", "static_cast<double>(found->second.carried)"),
            "reader_always_asks": (2, "if (!player || !Data().enemyStacks)", "if (!player)"),
            "hit_not_multiplied": (3, "        hit.legendary *= ItemPowers::PerStackFactor(player, petName, \"damage_per_enemy_hit_pct\"", "        (void)ItemPowers::PerStackFactor(player, petName, \"damage_per_enemy_hit_pct\""),
            "hit_wrong_stacks": (3, "ItemPowers::EnemyStacks(player, petName));", "1.0);"),
            "flag_never_set": (4, 'loaded.enemyStacks = loaded.enemyStacks || row.stat == "damage_per_enemy_hit_pct";', ""),
        }
        for name, (which, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, parts[which], name + " does not apply")
                at = parts[which].index(old, parts[which].index("void EnemyStackConnect(") if (which == 1 and name.startswith("connect")) else 0)
                mutated = list(parts)
                mutated[which] = parts[which][:at] + new + parts[which][at + len(old):]
                self.assertTrue(self.failures(*mutated), name + " survived")


if __name__ == "__main__":
    unittest.main()

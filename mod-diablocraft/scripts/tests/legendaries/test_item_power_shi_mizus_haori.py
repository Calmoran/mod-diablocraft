"""Legendary rest, bead diablocraft-tudh9: Shi Mizu's Haori (chest armor, any class), N-CRIT on N-PLIFE (a critical hit chance that the player's own Life switches).

  "While below [20-25]% Life, all attacks are guaranteed Critical Hits."
  * the text and range are read from d3planner (data.json items Unique_Chest_101_x1, leg_shimizushaori, min 20 max 25) and the catalogue row; the power file
    (decode_pow.py power ItemPassive_Unique_Ring_597_x1) holds the old fixed threshold (SF_2 0.3, DEPRECATED) the roll replaced; the table (data/legendary_powers.csv)
    holds TWO `player` rows for the pool item: `own_life_threshold_pct` 20-25 (rolled once per item, the higher the better: a Primal takes 25) and `crit_chance_pct` 100
    under the new condition `own_life_below`;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses `own_life_below` without
    the item's threshold row, on a skill row, with a set level, an event or a cond_arg, and the threshold with a condition or without the condition;
  * the production rules (src/combat/dc_item_power_math.h: Holds' `own_life_below`, OwnLifeThreshold, PlayerSum of `crit_chance_pct`) are compiled and driven with the generated
    rows: +100 critical hit chance strictly below the item's stored threshold, none at it or above, none when the item is off or has no stored roll; mutants of the rules and the
    rows fail the same driver; source guards on the Life read (Seen) follow. The in-game steps are in docs/test-diablocraft-tudh9.md.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_prides_fall import (BLANK, MATH, MODULE, REPO, T, drive, function_body, g, mine, read_csv, render_rows)  # noqa: E402

OWNER = "Unique_Chest_101_x1"
THRESHOLD, CRIT, COND = "own_life_threshold_pct", "crit_chance_pct", "own_life_below"


def planner():
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_sources_say_below_20_to_25_percent_life(self):
        text, low, high = planner()
        self.assertEqual("While below %d%% Life, all attacks are guaranteed Critical Hits.", text)
        self.assertEqual((20.0, 25.0), (low, high))
        catalogue = [r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual("While below [20-25]% Life, all attacks are guaranteed Critical Hits.", catalogue[0]["power_text"])

    def test_two_player_rows_hold_them(self):
        _, low, high = planner()
        self.assertEqual(sorted([(OWNER, 0, "player", "", THRESHOLD, low, high, *BLANK),
                                 (OWNER, 0, "player", "", CRIT, 100.0, 100.0, COND, *BLANK[1:])]), sorted(mine(OWNER)))


class Generator(unittest.TestCase):
    THRESHOLD_ROW = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": THRESHOLD, "value_min": "20", "value_max": "25", "cond": "",
                     "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                     "icd_seconds": "", "source": "s", "note": "n"}
    CRIT_ROW = {**THRESHOLD_ROW, "stat": CRIT, "value_min": "100", "value_max": "100", "cond": COND}

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len(mine(OWNER, render_rows(OWNER, self.THRESHOLD_ROW, self.CRIT_ROW))))

    def test_it_refuses_what_it_cannot_carry(self):
        threshold, crit = self.THRESHOLD_ROW, self.CRIT_ROW
        refused = {
            "no threshold": ([crit], "own_life_below is an item"),
            "the threshold alone": ([threshold], "own_life_threshold_pct is an item"),
            "a threshold under a condition": ([{**threshold, "cond": "quiet_stacks", "cond_arg": "2", "stack_seconds": "1", "stack_max": "2"}, crit],
                                              "own_life_threshold_pct is an item"),
            "a threshold of more than a bar": ([{**threshold, "value_min": "90", "value_max": "120"}, crit], "up to 100"),
            "a set level": ([threshold, {**crit, "owner": "Immortal King's Call", "pieces": "4"}], "is an item"),
            "an event": ([threshold, {**crit, "fire_on": "kill"}], "own_life_below is an item|an event fires"),
            "a cond_arg": ([threshold, {**crit, "cond_arg": "2"}], "takes no cond_arg"),
            "cond skills": ([threshold, {**crit, "cond_skills": "Sprint"}], "own_life_below is an item"),
            "a skill row": ([threshold, {**crit, "kind": "skill", "skill": "Frenzy", "stat": "damage_increase_pct"}], "is an item"),
        }
        for name, (rows, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    render_rows(OWNER, *rows)


class Rules(unittest.TestCase):
    ODD = ("Odd Chest", 0, "player", "", "damage_dealt_pct", 100.0, 100.0, COND, *BLANK[1:])   # another stat under the condition: not a crit chance
    OTHERTH = ("Other Chest", 0, "player", "", THRESHOLD, 1.0, 100.0, *BLANK)

    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows + [self.ODD, self.OTHERTH]]
        clear = (T("clear"), None)
        wear = lambda roll, life: [clear, (T("wears", OWNER, 0), None), (T("stored", OWNER, THRESHOLD, roll), None), (T("life", life), None)]  # noqa: E731
        # not worn: nothing, at any Life, even with the roll known
        out += [clear, (T("life", 1), None), (T("crit"), "0"), (T("stored", OWNER, THRESHOLD, high), None), (T("crit"), "0")]
        # worn, each end of the roll: strictly below the threshold, +100; at it or above, nothing
        for roll in (low, 22.5, high):
            for life, on in ((0, 1), (roll - 0.01, 1), (roll, 0), (roll + 0.01, 0), (50, 0), (100, 0)):
                out += wear(roll, life) + [(T("crit"), "100" if on else "0"), (T("holds", 1), "1" if on else "0")]
        # worn with no stored roll for the threshold: the condition never holds (the crit row still needs its own item)
        out += [clear, (T("wears", OWNER, 0), None), (T("life", 1), None), (T("crit"), "0"), (T("holds", 1), "0")]
        # the threshold is this item's own: another item's roll does not open this one
        out += [clear, (T("wears", OWNER, 0), None), (T("wears", "Other Chest", 0), None), (T("stored", "Other Chest", THRESHOLD, 90), None), (T("life", 50), None), (T("crit"), "0")]
        # another stat under the condition is not a crit chance
        out += wear(high, 1) + [(T("wears", "Odd Chest", 0), None), (T("crit"), "100")]
        out += [clear, (T("wears", "Odd Chest", 0), None), (T("stored", "Odd Chest", THRESHOLD, 90), None), (T("life", 1), None), (T("crit"), "0")]
        # a Primal stores the top of the range (the higher is the better)
        out += [(T("best", 0), g(high))]
        return out

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = drive(self.cases(mine(OWNER)), MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 35)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine(OWNER)
        self.assertEqual(2, len(rows))
        want, _ = drive(self.cases(rows), real, "want")
        threshold = [r for r in rows if r[4] == THRESHOLD]
        crit = [r for r in rows if r[4] == CRIT]
        row_mutants = {
            "no_condition": threshold + [r[:7] + ("",) + r[8:] for r in crit],
            "the_wrong_stat": threshold + [r[:4] + ("damage_reduction_pct",) + r[5:] for r in crit],
            "fifty_points": threshold + [r[:5] + (50.0, 50.0) + r[7:] for r in crit],
            "the_wrong_owner": [("Other Chest",) + r[1:] for r in rows],
            "the_range_fixed_at_the_bottom": [r[:6] + (r[5],) + r[7:] for r in threshold] + crit,
            "no_threshold": crit,
            "no_crit": threshold,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = drive(self.cases(mutant_rows), real, name)
                self.assertNotEqual(want, got, name + " survived")
        lookup = function_body(real, "inline bool OwnLifeThreshold(")
        rules = {
            "other_threshold_stat": (lookup, '"own_life_threshold_pct"', '"resource_threshold_pct"'),
            "the_roll_ignored": (lookup, "pct = value.value;", "pct = 100.0;"),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                _, got = drive(self.cases(rows), real.replace(where, where.replace(old, new, 1)), name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "at_or_below": real.replace("situation.lifePct < pct;", "situation.lifePct <= pct;"),
            "above": real.replace("situation.lifePct < pct;", "situation.lifePct > pct;"),
            "the_condition_dispatch_lost": real.replace('        if (row.cond == "own_life_below")\n        {', '        if (row.cond == "own_life_below_x")\n        {'),
            "the_best_is_the_bottom": real.replace('row.stat == "resource_threshold_pct" ? row.min : row.max', "row.min"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = drive(self.cases(rows), header, name)
                self.assertNotEqual(want, got, name + " survived")


class Server(unittest.TestCase):
    """The Life is read when the number is read; the crit reader hands the situation over (Envious Blade's CritBonus). Text guards, nothing here runs the worldserver."""

    def failures(self, powers, readers):
        wrong = []

        def need(why, ok):
            if not ok:
                wrong.append(why)

        need("a row under the condition turns the Life read on", '|| row.cond == "own_life_below";' in powers)
        need("Seen reads the Life when a row wants it, at the moment the number is read",
             "if (Data().life && player->GetMaxHealth())\n                situation.lifePct = 100.0 * player->GetHealth() / player->GetMaxHealth();" in powers)
        reader = readers[readers.index("double CritBonus("):]
        reader = reader[:reader.index("\n    }\n")]
        need("the crit reader reads the situation Seen took (the Life) and sums the crit chance rows",
             "ItemPower::Situation seen = Seen(player);" in reader and 'ItemPower::PlayerSum(Data().rows, CountsOf(guid), "crit_chance_pct", SituationOf(guid, std::move(seen)))' in reader)
        return wrong

    def parts(self):
        return [item_powers_source.CPP.read_text(encoding="utf-8"), (item_powers_source.FOLDER / "dc_item_powers_readers.cpp").read_text(encoding="utf-8")]

    def test_the_life_reaches_the_crit_rule(self):
        self.assertEqual([], self.failures(*self.parts()))

    def test_the_text_mutants_are_caught(self):
        parts = self.parts()
        mutants = {
            "flag_never_set": (0, '|| row.cond == "own_life_below";', ";"),
            "life_not_read": (0, "situation.lifePct = 100.0 * player->GetHealth() / player->GetMaxHealth();", ""),
            "life_not_a_percent": (0, "situation.lifePct = 100.0 * player->GetHealth()", "situation.lifePct = 1.0 * player->GetHealth()"),
            "crit_without_the_situation": (1, 'ItemPower::PlayerSum(Data().rows, CountsOf(guid), "crit_chance_pct", SituationOf(guid, std::move(seen)))',
                                           'ItemPower::PlayerSum(Data().rows, CountsOf(guid), "crit_chance_pct", SituationOf(guid))'),
        }
        for name, (which, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, parts[which], name + " does not apply")
                mutated = list(parts)
                mutated[which] = parts[which].replace(old, new, 1)
                self.assertTrue(self.failures(*mutated), name + " survived")


if __name__ == "__main__":
    unittest.main()

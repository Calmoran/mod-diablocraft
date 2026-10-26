"""Legendary rest, bead diablocraft-sifvi: Rogar's Huge Stone (ring, any class), N-PLIFE (a player number scaled by the Life missing).

  "Increase your Life per Second by up to [75-100]% based on your missing Life."
  * the text and range are read from d3planner (data.json items Unique_Ring_103_x1, leg_rogarshugestone, min 75 max 100) and the catalogue row; the power file (decode_pow.py power
    ItemPassive_Unique_Ring_665_x1) gives SF_1 'Per % Life Missing' 1 and SF_2 'Tick Rate' 0.5; the table (data/legendary_powers.csv) holds TWO `player` rows for the pool item:
    `life_regen_by_missing_pct` 75-100 (rolled once per item, a Primal takes 100) and the fixed `life_regen_tick_seconds` 0.5;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses each stat with a set level,
    a condition or an event, the tick with a range or without the bonus, and the bonus without the tick;
  * the production rules (src/combat/dc_item_power_math.h: RegenByMissing through PlayerSum, LifeLookDue) are compiled and driven with the generated rows: the bonus is
    N x the Life missing / 100 with the item's stored roll (nothing at full Life, N with none left, the sources adding, rounded to 0.1), none when the item is off; a look is due
    after the tick; mutants of the rules and the rows fail the same driver; source guards on the server reader (dc_item_powers_clocks.cpp MissingLifeRegen) follow.
    The in-game steps are in docs/test-diablocraft-sifvi.md.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_prides_fall import (BLANK, MATH, MODULE, REPO, T, drive, function_body, g, mine, read_csv, render_rows)  # noqa: E402

OWNER = "Unique_Ring_103_x1"
STAT, TICK = "life_regen_by_missing_pct", "life_regen_tick_seconds"


def planner():
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_sources_say_up_to_75_to_100_percent_by_missing_life(self):
        text, low, high = planner()
        self.assertEqual("Increase your Life per Second by up to %d%% based on your missing Life.", text)
        self.assertEqual((75.0, 100.0), (low, high))
        catalogue = [r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual("Increase your Life per Second by up to [75-100]% based on your missing Life.", catalogue[0]["power_text"])
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == STAT)
        self.assertIn("SF_1 'Per % Life Missing' = 1, SF_2 'Tick Rate' = 0.5", row["source"])

    def test_two_player_rows_hold_them(self):
        _, low, high = planner()
        self.assertEqual(sorted([(OWNER, 0, "player", "", STAT, low, high, *BLANK), (OWNER, 0, "player", "", TICK, 0.5, 0.5, *BLANK)]), sorted(mine(OWNER)))


class Generator(unittest.TestCase):
    BONUS = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "75", "value_max": "100", "cond": "",
             "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
             "icd_seconds": "", "source": "s", "note": "n"}
    TICKROW = {**BONUS, "stat": TICK, "value_min": "0.5", "value_max": "0.5"}

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len(mine(OWNER, render_rows(OWNER, self.BONUS, self.TICKROW))))

    def test_it_refuses_what_it_cannot_carry(self):
        bonus, tick = self.BONUS, self.TICKROW
        refused = {
            "a set level": ([{**bonus, "owner": "Immortal King's Call", "pieces": "4", "value_min": "75", "value_max": "75"}, tick], "simply on"),
            "a condition": ([{**bonus, "cond": "quiet_stacks", "cond_arg": "2", "stack_seconds": "1", "stack_max": "2"}, tick], "simply on"),
            "an event": ([{**bonus, "fire_on": "kill"}, tick], "simply on|an event fires"),
            "a negative number": ([{**bonus, "value_min": "-75", "value_max": "-75"}, tick], "non-zero, one sign|needs 0"),
            "no tick": ([bonus], "needs the item's fixed life_regen_tick_seconds"),
            "a rolled tick": ([bonus, {**tick, "value_min": "0.4"}], "one fixed number"),
            "a tick alone": ([tick], "one fixed number beside the life_regen_by_missing_pct"),
            "a tick under a condition": ([bonus, {**tick, "cond": "standing_still", "stack_seconds": "1", "stack_max": "1"}], "simply on|only"),
        }
        for name, (rows, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    render_rows(OWNER, *rows)


class Rules(unittest.TestCase):
    OTHER = ("Other Ring", 0, "player", "", STAT, 1.0, 100.0, *BLANK)     # a second source, ranged: the driver sets its stored roll
    ODD = ("Odd Ring", 0, "player", "", "damage_dealt_pct", 90.0, 90.0, *BLANK)

    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows + [self.OTHER, self.ODD]]
        clear = (T("clear"), None)
        wear = lambda roll, life: [clear, (T("wears", OWNER, 0), None), (T("stored", OWNER, STAT, roll), None), (T("life", life), None)]  # noqa: E731
        # not worn: nothing, however much Life is missing, even with the roll known
        out += [clear, (T("life", 0), None), (T("regen"), "0"), (T("stored", OWNER, STAT, high), None), (T("regen"), "0")]
        # worn, each end of the roll, at every Life: N x missing / 100, rounded to 0.1
        for roll in (low, 87, high):
            for life in (100, 99, 75, 50, 33.3, 10, 0):
                missing = 100 - life
                out += wear(roll, life) + [(T("regen"), g(round(roll * missing / 100 * 10) / 10))]
        # more Life than the bar (a stale read) and a negative one are clamped
        out += wear(high, 150) + [(T("regen"), "0")] + wear(high, -20) + [(T("regen"), g(high))]
        # two sources add: 100 and 40 at half Life
        out += wear(high, 50) + [(T("wears", "Other Ring", 0), None), (T("stored", "Other Ring", STAT, 40), None), (T("regen"), g((high + 40) / 2))]
        # another stat of another item is not this bonus
        out += [clear, (T("wears", "Odd Ring", 0), None), (T("life", 0), None), (T("regen"), "0")]
        # the tick: a look is due at the cadence; a wrapped clock is no break; no cadence never waits
        out += [(T("due", 0, 499, 0.5), "0"), (T("due", 0, 500, 0.5), "1"), (T("due", 1000, 1499, 0.5), "0"), (T("due", 4294967200, 100, 0.5), "0"),
                (T("due", 4294967200, 500, 0.5), "1"), (T("due", 0, 1, 0), "1"), (T("due", 0, 1, -1), "1")]
        # a Primal stores the top of the range
        out += [(T("best", 0), g(high))]
        return out

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = drive(self.cases(mine(OWNER)), MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine(OWNER)
        self.assertEqual(2, len(rows))
        want, _ = drive(self.cases(rows), real, "want")
        bonus = [r for r in rows if r[4] == STAT]
        row_mutants = {
            "the_wrong_stat": [r[:4] + ("damage_dealt_pct",) + r[5:] for r in bonus],
            "the_wrong_owner": [("Other Ring",) + r[1:] for r in bonus],
            "the_range_fixed_at_the_bottom": [r[:6] + (r[5],) + r[7:] for r in bonus],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = drive(self.cases(mutant_rows), real, name)
                self.assertNotEqual(want, got, name + " survived")
        regen = function_body(real, "inline double RegenByMissing(")
        due = function_body(real, "inline bool LifeLookDue(")
        rules = {
            "present_not_missing": (regen, "100.0 - lifePct", "lifePct"),
            "no_clamp": (regen, "std::clamp(100.0 - lifePct, 0.0, 100.0)", "100.0 - lifePct"),
            "percent_as_a_fraction": (regen, "* missing / 100.0 * 10.0", "* missing * 10.0"),
            "no_rounding": (regen, "/ 10.0;", "/ 1.0;"),
            "wrong_stat": (regen, '"life_regen_by_missing_pct"', '"damage_dealt_pct"'),
            "tick_exclusive": (due, ">= static_cast<std::uint32_t>(seconds * 1000.0)", "> static_cast<std::uint32_t>(seconds * 1000.0)"),
            "tick_a_tenth": (due, "seconds * 1000.0", "seconds * 100.0"),
            "no_cadence_waits": (due, "seconds <= 0 ||", ""),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                _, got = drive(self.cases(rows), real.replace(where, where.replace(old, new, 1)), name)
                self.assertNotEqual(want, got, name + " survived")
        for name, header in {"the_bottom_not_the_roll": real.replace("number = found->value;", "number = row.min;")}.items():
            with self.subTest(mutant=name):
                _, got = drive(self.cases(rows), header, name)
                self.assertNotEqual(want, got, name + " survived")


class Server(unittest.TestCase):
    """Text guards on the one server reader. Nothing here runs the worldserver; the in-game steps are in the test sheet."""

    CLOCKS = item_powers_source.FOLDER / "dc_item_powers_clocks.cpp"

    def failures(self, clocks, powers, header):
        wrong = []

        def need(why, ok):
            if not ok:
                wrong.append(why)

        start = clocks.find("void MissingLifeRegen(Player* player)")
        body = clocks[start:clocks.index("\n        }\n", start)] if start >= 0 else ""
        need("watched only when some row holds the stat", "if (!Data().missingRegen)\n                return;" in body)
        need("only for a player who wears something that owns a power", "if (mine == clocks.end())\n                    return;" in body)
        need("the Life is the player's now, read before the lock",
             "double const life = player->GetMaxHealth() ? 100.0 * player->GetHealth() / player->GetMaxHealth() : 100.0;" in body
             and "std::lock_guard" in body and body.index("double const life") < body.index("std::lock_guard"))
        need("the tick is the item's fixed row and a look waits for it",
             'every = ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), "life_regen_tick_seconds", 0.0, situation);' in body
             and "if (!ItemPower::LifeLookDue(clock.missingRegenAt, now, every))\n                    return;" in body and "clock.missingRegenAt = now;" in body)
        need("the bonus is the production rule", "pct = ItemPower::RegenByMissing(Data().rows, CountsOf(guid), life, situation);" in body)
        need("redone only when it changed", "changed = pct != clock.missingRegen;" in body and "if (!changed)\n                return;" in body)
        need("the sheet gets a Temporary Percent Life Regen of the item powers' own id, the old one taken off first",
             "Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, MissingRegenId);" in body
             and "if (pct > 0)\n                Stats::AddContribution(guid, {Source::Temporary, Stat::LifeRegen, MissingRegenId, pct, Bucket::Percent});" in body)
        need("the sheet is recomputed and pushed", "Stats::Recompute(player);\n            Inventory::PushSheet(player);" in body)
        need("a row that raises the regeneration turns the watch on", 'loaded.missingRegen = loaded.missingRegen || row.stat == "life_regen_by_missing_pct";' in powers)
        need("the update hook reads it", powers.count("MissingLifeRegen(player);") == 1)
        need("the id is not another contribution's", "constexpr std::uint64_t MissingRegenId = OverCapId + 5;" in header and "constexpr std::uint64_t RegenId = OverCapId + 2;" in header)
        return wrong

    def parts(self):
        return [self.CLOCKS.read_text(encoding="utf-8"), item_powers_source.CPP.read_text(encoding="utf-8"),
                (item_powers_source.FOLDER / item_powers_source.HEADER).read_text(encoding="utf-8")]

    def test_the_server_reader_is_what_the_rules_say(self):
        self.assertEqual([], self.failures(*self.parts()))

    def test_the_text_mutants_are_caught(self):
        parts = self.parts()
        mutants = {
            "always_watched": (0, "if (!Data().missingRegen)", "if (false)"),
            "no_player_check": (0, "if (mine == clocks.end())\n                    return;", ""),
            "life_not_a_percent": (0, "100.0 * player->GetHealth()", "1.0 * player->GetHealth()"),
            "wrong_tick": (0, '"life_regen_tick_seconds", 0.0, situation', '"life_regen_by_missing_pct", 0.0, situation'),
            "no_wait": (0, "if (!ItemPower::LifeLookDue(clock.missingRegenAt, now, every))", "if (false)"),
            "look_not_recorded": (0, "clock.missingRegenAt = now;", ""),
            "not_the_production_rule": (0, "ItemPower::RegenByMissing(Data().rows, CountsOf(guid), life, situation)", "50.0"),
            "always_redone": (0, "changed = pct != clock.missingRegen;", "changed = true;"),
            "never_redone": (0, "changed = pct != clock.missingRegen;", "changed = false;"),
            "wrong_sheet_stat": (0, "Stat::LifeRegen, MissingRegenId, pct,", "Stat::Thorns, MissingRegenId, pct,"),
            "wrong_bucket": (0, "pct, Bucket::Percent}", "pct, Bucket::Flat}"),
            "old_one_not_removed": (0, "Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, MissingRegenId);", ""),
            "no_recompute": (0, "Stats::Recompute(player);\n            Inventory::PushSheet(player);", ""),
            "flag_never_set": (1, 'loaded.missingRegen = loaded.missingRegen || row.stat == "life_regen_by_missing_pct";', ""),
            "not_called": (1, "                MissingLifeRegen(player);\n", ""),
            "shared_id": (2, "MissingRegenId = OverCapId + 5;", "MissingRegenId = OverCapId + 2;"),
        }
        for name, (which, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, parts[which], name + " does not apply")
                at = parts[which].index(old, parts[which].index("void MissingLifeRegen(") if which == 0 else 0)
                mutated = list(parts)
                mutated[which] = parts[which][:at] + new + parts[which][at + len(old):]
                self.assertTrue(self.failures(*mutated), name + " survived")


if __name__ == "__main__":
    unittest.main()

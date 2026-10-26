"""Legendary rest, bead diablocraft-odu01: Boots of Disregard (boots, any class), N-MOVE.

  "Gain 10000 Life regeneration per Second for each second you stand still. This effect stacks up to 4 times."
  * the numbers (10000 a stack, 4 stacks, a second a stack) are read from the catalogue row's text (docs/research/legendary-catalogue.csv) and from the item's
    tooltip (data/generated/crafting.sql); the table (data/legendary_powers.csv) holds ONE `player` row for the pool item Unique_Boots_102_x1: `life_regen`
    10000 under the new condition `standing_still` with stack_seconds 1 and stack_max 4;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts
    `standing_still` only as an item's player row with stacks, and `life_regen` only under it;
  * the production rules (src/combat/dc_item_power_math.h: StillSince, StillStacks through Stacks / Holds / PlayerSum) are compiled and driven with the generated
    row: a stack a second stood still while the item is worn, at most 4, none when the item is off or the timer has not started, the later of "went on" and
    "stopped moving" starts the count, a moving player restarts the timer, the clock wrapping is no break;
  * mutants of the rules and of the row fail the same driver;
  * source-text guards for the server side (dc_item_powers.cpp StandStill): the player's movement is `Unit::isMoving`, the timer is StillSince, the number is
    PlayerSum of `life_regen`, put on the sheet's Life Regen as a Temporary flat contribution, redone only when it changed, from the update hook, and only
    watched when some row holds `standing_still`; mutants of that text are caught.
    The in-game steps are in docs/test-diablocraft-odu01.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
POWERS = item_powers_source.CPP
HARNESS = MODULE / "tests/item_power_boots_of_disregard/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Boots_102_x1"
STAT, COND = "life_regen", "standing_still"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (REPO / name if name.startswith("docs/") else MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(Life Regen a stack, stacks, seconds a stack) as the catalogue words them."""
    row = next(r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
    m = re.fullmatch(r"Gain (\d+) Life regeneration per Second for each second you stand still\. This effect stacks up to (\d+) times\.", row["power_text"])
    assert m, row["power_text"]
    return float(m[1]), int(m[2]), 1.0


class Table(unittest.TestCase):
    def test_the_source_gives_the_numbers(self):
        self.assertEqual((10000.0, 4, 1.0), numbers())

    def test_one_player_row_holds_them(self):
        per_stack, most, every = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, per_stack, per_stack, COND, 0.0, "", every, most, "", "", 100.0, 0.0)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Gain 10000 Life regeneration per Second for each second you stand still. This effect stacks up to 4 times.", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "10000", "value_max": "10000", "cond": COND,
            "cond_arg": "", "cond_skills": "", "stack_seconds": "1", "stack_max": "4", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="boots-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "no stack seconds": ({"stack_seconds": ""}, "stack_seconds > 0"),
            "no stack maximum": ({"stack_max": ""}, "stack_max >= 1"),
            "a fractional stack maximum": ({"stack_max": "2.5"}, "stack_max >= 1"),
            "a cond_arg": ({"cond_arg": "2"}, "takes no cond_arg"),
            "cond skills": ({"cond_skills": "Sprint"}, "no cond_skills"),
            "a set bonus": ({"owner": "Immortal King's Call", "pieces": "4"}, "standing_still"),
            "an event": ({"fire_on": "kill"}, "standing_still"),
            "a skill row": ({"kind": "skill", "skill": "Frenzy", "stat": "damage_increase_pct"}, "standing_still is an item"),
            "the number without the condition": ({"cond": "", "stack_seconds": "", "stack_max": ""}, "life_regen is an item"),
            "the number under another condition": ({"cond": "quiet_stacks", "cond_arg": "2"}, "life_regen is an item"),
            "a negative number": ({"value_min": "-5", "value_max": "-5"}, "needs 0 < value_min <= value_max"),
            "a zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)

    def test_another_player_number_may_stand_still_too(self):
        # the condition is not the boots': a later bead's damage number under it is one row of the same kind
        rows = self.render_with({}, {"stat": "damage_dealt_pct", "value_min": "25", "value_max": "25"})
        self.assertEqual(2, len([r for r in rows if r[0] == OWNER]))


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemboots-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        per_stack, most, _ = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = T("clear")

        def at(now, since, worn=0, tracked=1):
            return [(clear, None), (T("wears", OWNER, worn), None), (T("now", now), None), (T("still", tracked, since), None)]

        regen = lambda stacks: g(per_stack * stacks)  # noqa: E731
        # not worn: nothing, whatever the timer says
        out += [(clear, None), (T("now", 9000), None), (T("still", 1, 0), None), (T("sum", STAT), "0"), (T("holds", 0), "0")]
        # worn, timer not started: nothing
        out += at(9000, 0, tracked=0) + [(T("sum", STAT), "0"), (T("holds", 0), "0")]
        # a stack a whole second: none under one, one at the second, two just under three seconds, three, four
        for now, stacks in ((0, 0), (999, 0), (1000, 1), (1999, 1), (2000, 2), (2999, 2), (3000, 3), (4000, 4)):
            out += at(now, 0) + [(T("sum", STAT), regen(stacks)), (T("holds", 0), "1" if stacks else "0")]
        # the cap: seconds past the fourth add nothing
        out += at(9000, 0) + [(T("sum", STAT), regen(most))]
        # the count starts at the later of "went on" and "stopped": worn after the player stopped
        out += at(6000, 0, worn=5000) + [(T("sum", STAT), regen(1))]
        out += at(5999, 0, worn=5000) + [(T("sum", STAT), "0")]
        # ... and stopped after the item went on
        out += at(8000, 7000, worn=0) + [(T("sum", STAT), regen(1))]
        out += at(7999, 7000, worn=0) + [(T("sum", STAT), "0")]
        # the clock wrapping past 2^32 is no break
        out += at(1100, 4294966300, worn=4294966300) + [(T("sum", STAT), regen(2))]
        # the timer: moving restarts it at now, the first look starts it at now, standing keeps it
        out += [(T("since", 1, 1, 100, 5000), "5000"), (T("since", 0, 0, 100, 5000), "5000"), (T("since", 0, 1, 100, 5000), "100"),
                (T("since", 1, 0, 100, 5000), "5000")]
        # a stopped, started and stopped again player: the timer set by StillSince feeds the count
        out += at(5000, 5000) + [(T("sum", STAT), "0")]
        out += at(7000, 5000) + [(T("sum", STAT), regen(2))]
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

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row_mutants = {
            "the_condition_lost": [r[:7] + ("",) + r[8:] for r in rows],
            "the_stack_cap_raised": [r[:11] + (r[11] + 1,) + r[12:] for r in rows],
            "the_stack_cap_lowered": [r[:11] + (r[11] - 1,) + r[12:] for r in rows],
            "a_stack_every_two_seconds": [r[:10] + (2.0,) + r[11:] for r in rows],
            "the_number_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_reduction_pct",) + r[5:] for r in rows],
            "the_wrong_owner": [("Other Boots",) + r[1:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        still = real[real.index("inline unsigned StillStacks("):]
        still = still[:still.index("\n    }\n") + 7]
        timer = real[real.index("inline std::uint32_t StillSince("):]
        timer = timer[:timer.index("\n    }\n") + 7]
        rules = {
            "an_unstarted_timer_counts": (still, "|| !situation.stillTracked", ""),
            "the_item_going_on_is_ignored": (still, "if (static_cast<std::int32_t>(worn->second - start) > 0)", "if (false)"),
            "the_item_going_on_always_wins": (still, "if (static_cast<std::int32_t>(worn->second - start) > 0)", "if (true)"),
            "no_cap": (still, "return built < row.stackMax ? built : row.stackMax;", "return built;"),
            "a_stack_a_half_second": (still, "elapsed / (row.stackSeconds * 1000.0)", "elapsed / (row.stackSeconds * 500.0)"),
            "moving_does_not_restart": (timer, "moving || !tracked ? now : since", "!tracked ? now : since"),
            "standing_restarts": (timer, "moving || !tracked ? now : since", "now"),
            "the_first_look_keeps_zero": (timer, "moving || !tracked ? now : since", "moving ? now : since"),
        }
        for name, (body, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_dispatch_lost": ('if (row.cond == "standing_still")\n            return StillStacks(row, situation);', ""),
            "holds_ignores_it": ('row.cond == "quiet_stacks" || row.cond == "standing_still"', 'row.cond == "quiet_stacks"'),
        }
        for name, (old, new) in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, real, name + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


class Server(unittest.TestCase):
    """Text guards on the one server reader. Nothing here runs the worldserver; the in-game steps are in the test sheet."""

    def text(self):
        return POWERS.read_text(encoding="utf-8")

    def body(self, text=None):
        text = self.text() if text is None else text
        start = text.index("void StandStill(Player* player)")
        return text[start:text.index("\n        }\n", start)]

    def check(self, text):
        body = self.body(text)
        # watched only when a row holds the condition, and only for a player who wears something that owns a power
        self.assertRegex(body, r"if \(!Data\(\)\.still\)\s+return;")
        self.assertRegex(body, r"if \(mine == clocks\.end\(\)\)\s+return;")
        self.assertIn("loaded.still = loaded.still || row.cond == \"standing_still\";", text)
        # the timer is the production rule, fed by the core's own movement test
        self.assertIn("clock.stillSince = ItemPower::StillSince(player->isMoving(), clock.stillTracked, clock.stillSince, getMSTime());", body)
        self.assertIn("clock.stillTracked = true;", body)
        # the number is PlayerSum of life_regen, read with the situation the hit path reads, under the lock
        self.assertIn('regen = ItemPower::PlayerSum(Data().rows, CountsOf(guid), "life_regen", SituationOf(guid));', body)
        self.assertLess(body.index("std::lock_guard"), body.index("PlayerSum"))
        # the sheet gets it as a Temporary flat Life Regen of the item powers' own id, redone only when it changed
        self.assertIn("changed = regen != clock.lifeRegen;", body)
        self.assertRegex(body, r"if \(!changed\)\s+return;")
        self.assertIn("Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, RegenId);", body)
        self.assertRegex(body, r"if \(regen > 0\)\s+Stats::AddContribution\(guid, \{Source::Temporary, Stat::LifeRegen, RegenId, regen, Bucket::Flat\}\);")
        self.assertIn("Stats::Recompute(player);", body)
        # the situation carries the timer to the conditions
        self.assertIn("situation.stillTracked = mine->second.stillTracked;", text)
        self.assertIn("situation.stillSince = mine->second.stillSince;", text)
        # called from the update hook
        self.assertIn("PLAYERHOOK_ON_UPDATE", text)
        # the one update hook also fires the `tick` event (the clock) and then reads the timer
        self.assertRegex(text, r'void OnPlayerUpdate\(Player\* player, std::uint32_t\) override\s+\{\s+Fire\(player, "tick", "", 1\.0\);\s+StandStill\(player\);(\s+\w+\(player\);)*\s+\}')
        self.assertEqual(1, text.count("void OnPlayerUpdate("))

    def test_the_server_reader_is_what_the_rules_say(self):
        self.check(self.text())

    def test_the_regen_id_is_not_another_contributions(self):
        text = (item_powers_source.FOLDER / item_powers_source.HEADER).read_text(encoding="utf-8")   # the ids are declared in the shared header
        self.assertIn("constexpr std::uint64_t OverCapId = 1ULL << 62;", text)
        self.assertIn("constexpr std::uint64_t RegenId = OverCapId + 2;", text)

    def test_the_text_mutants_are_caught(self):
        text = self.text()
        mutants = {
            "always_watched": ("if (!Data().still)", "if (false)"),
            "movement_ignored": ("ItemPower::StillSince(player->isMoving(), clock.stillTracked", "ItemPower::StillSince(false, clock.stillTracked"),
            "not_the_production_timer": ("ItemPower::StillSince(player->isMoving(),", "ItemPower::StillSince(!player->isMoving(),"),
            "timer_never_started": ("clock.stillTracked = true;", "clock.stillTracked = false;"),
            "wrong_stat_read": ('"life_regen", SituationOf(guid)', '"damage_dealt_pct", SituationOf(guid)'),
            "always_redone": ("changed = regen != clock.lifeRegen;", "changed = true;"),
            "never_redone": ("changed = regen != clock.lifeRegen;", "changed = false;"),
            "wrong_sheet_stat": ("Stat::LifeRegen, RegenId, regen,", "Stat::Thorns, RegenId, regen,"),
            "wrong_bucket": ("regen, Bucket::Flat}", "regen, Bucket::Percent}"),
            "old_one_not_removed": ("Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, RegenId);", ""),
            "not_called": ("StandStill(player);\n                StunScan(player);", "StunScan(player);"),
            "not_called": ("StandStill(player);\n                NoDamageCost(player);", "NoDamageCost(player);"),
            "hook_not_registered": ("PLAYERHOOK_ON_CREATURE_KILL, PLAYERHOOK_ON_UPDATE", "PLAYERHOOK_ON_CREATURE_KILL"),
            "timer_not_in_the_situation": ("situation.stillSince = mine->second.stillSince;", ""),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, text, name + " does not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    self.check(text.replace(old, new, 1))


if __name__ == "__main__":
    unittest.main()

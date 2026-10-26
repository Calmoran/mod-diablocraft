"""Legendary rest, bead diablocraft-c32yt: Irontoe Mudsputters (boots, any class). Builds N-PSPD (a player's movement speed from an item power).

  "Gain up to [25-30]% increased movement speed based on amount of Life missing."
  * the numbers (25 to 30) are read from d3planner (item_feet.js, leg_irontoemudsputters); the table (data/legendary_powers.csv) holds ONE `player` row for
    the pool item Unique_Boots_104_x1: `movement_speed_pct`, 0.25-0.30, under the condition `life_missing` (Lornelle's Sunstone's: the number is per 1% of
    Life missing, so it is the "up to N%" at no Life), which the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat
    as a player row only, positive only;
  * the production rules (src/combat/dc_item_power_math.h: LifeMissing / Counted / Holds read by PlayerSum, and LookDue) are compiled and driven with the
    generated row: N x M/100 of the item's stored roll, M the percent of Life missing, nothing at full Life or with the item unworn or unrolled, a second
    source adds, the look is due at once and then once a period; mutants of the rules and of the row fail the same driver;
  * source-text guards for the server side (dc_item_powers_clocks.cpp MovementSpeed): the number is PlayerSum of `movement_speed_pct` read with a fresh
    Seen, put on the sheet's movement speed as a Temporary Uncapped contribution, redone only when it changed, from the update hook, looked at every
    combat.item_power_speed_look_seconds, and only when some row gives it; mutants of that text are caught.
    The in-game steps are in docs/test-diablocraft-c32yt.md.
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
import harness_env  # noqa: E402
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_irontoe_mudsputters/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Boots_104_x1"
STAT, COND = "movement_speed_pct", "life_missing"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
AFTER = (COND, 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(low, high) of the item's number as the planner words it: percent at no Life."""
    text = (REPO / "reference/d3planner/item_feet.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},", start)]
    m = re.search(r'Gain up to %d%% increased movement speed based on amount of Life missing\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_source_gives_the_range(self):
        self.assertEqual((25.0, 30.0), numbers())

    def test_one_player_row_holds_the_range_per_percent_missing(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low / 100, high / 100, *AFTER)], mine())

    def test_the_row_has_its_source_and_says_how_it_is_put_on(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_feet.js", rows[0]["source"])
        self.assertIn("leg_irontoemudsputters", rows[0]["source"])
        self.assertIn("per 1% of Life missing", rows[0]["note"])
        self.assertIn("Temporary Uncapped", rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Gain up to 25–30% increased movement speed based on amount of Life missing.", m[1])

    def test_the_look_period_is_the_standing_default(self):
        row = next(r for r in read_csv("data/tunables/combat.csv") if r["name"] == "item_power_speed_look_seconds")
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("", "0.25", "seconds"))
        self.assertIn("standing default", row["notes"])
        self.assertNotIn("PLACEHOLDER", row["notes"])

    def test_the_power_is_in_the_contract(self):
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertIn("### Irontoe Mudsputters (`diablocraft-c32yt`", text)


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "0.25", "value_max": "0.3", "cond": COND,
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="irontoe-gen-", dir=str(SCRATCH)))
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

    def test_the_stat_is_a_player_row_with_or_without_the_condition(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))
        self.assertEqual(1, len([r for r in self.render_with({"cond": ""}) if r[0] == OWNER]))

    def test_it_refuses_what_the_code_does_not_read(self):
        refused = {
            "a skill row": {"kind": "skill", "skill": "Leap", "stat": STAT},
            "a negative number": {"value_min": "-0.3", "value_max": "-0.25"},
            "an unknown stat": {"stat": "movement_speed"},
            "a cond_arg": {"cond_arg": "50"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="irontoe-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        low, high = (v / 100 for v in numbers())
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = lambda roll, life: clear + [(T("wears", OWNER), None), (T("value", OWNER, "", STAT, roll), None), (T("life", life), None)]  # noqa: E731
        speed = lambda roll, life: g(roll * (100 - life))  # noqa: E731
        # not worn, worn with no roll, a roll in the bag, the Life never read: nothing
        out += clear + [(T("life", 10), None), (T("sum", STAT), "0")]
        out += clear + [(T("wears", OWNER), None), (T("life", 10), None), (T("sum", STAT), "0")]
        out += clear + [(T("value", OWNER, "", STAT, high), None), (T("life", 10), None), (T("sum", STAT), "0")]
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, "", STAT, high), None), (T("sum", STAT), "0")]
        # worn and rolled: N x M at both ends of the range and between, at every Life from full to none; at no Life it is the "up to N%"
        for roll in (low, 0.28, high):
            for life in (100, 99, 90, 75, 50, 25, 10, 1, 0):
                out += worn(roll, life) + [(T("sum", STAT), speed(roll, life))]
        out += worn(high, 0) + [(T("sum", STAT), "30")]
        out += worn(low, 0) + [(T("sum", STAT), "25")]
        # a Life past the ends is clamped, and nothing is kept from the earlier read
        out += worn(high, 130) + [(T("sum", STAT), "0")]
        out += worn(high, -20) + [(T("sum", STAT), "30")]
        out += worn(0.28, 100) + [(T("sum", STAT), "0"), (T("life", 40), None), (T("sum", STAT), speed(0.28, 40)), (T("life", 100), None), (T("sum", STAT), "0")]
        # a second source of movement speed adds, a fixed one too
        out += worn(high, 50) + [(T("wears", "Other Boots"), None), (T("sum", STAT), g(high * 50 + 10))]
        out += worn(high, 100) + [(T("wears", "Other Boots"), None), (T("sum", STAT), "10")]
        # the speed is a player stat, not a multiplier read as damage
        out += worn(high, 50) + [(T("factor", "damage_dealt_pct"), "1")]
        # the range rolls once per item (a Primal stores the top)
        out += [(T("roll", OWNER, 1), "power::%s=%g;" % (STAT, high)), (T("roll", OWNER, 0), "power::%s=%g;" % (STAT, (low + high) / 2))]
        # the look: due at once, then once a period, across a wrapped clock
        out += [(T("look", 0, 0, 0, 250), "1"), (T("look", 1, 1000, 1249, 250), "0"), (T("look", 1, 1000, 1250, 250), "1"), (T("look", 1, 1000, 5000, 250), "1"),
                (T("look", 1, 4294967200, 200, 250), "1"), (T("look", 1, 4294967200, 100, 250), "0"), (T("look", 1, 4294967200, 4294967210, 250), "0"), (T("look", 1, 1000, 1000, 0), "1")]
        return out

    def other(self):
        return [("Other Boots", 0, "player", "", STAT, 10.0, 10.0, *BLANK)]

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
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + self.other(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows + self.other(), "want")
        row_mutants = {
            "the_row_lost": [],
            "the_condition_dropped": [r[:7] + BLANK[:1] + r[8:] for r in rows],
            "the_number_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_stat_changed": [r[:4] + ("damage_dealt_pct",) + r[5:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + self.other(), name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "life_taken_for_missing": real.replace("std::clamp(100.0 - situation.lifePct, 0.0, 100.0)", "std::clamp(situation.lifePct, 0.0, 100.0)"),
            "missing_not_clamped": real.replace("std::clamp(100.0 - situation.lifePct, 0.0, 100.0)", "(100.0 - situation.lifePct)"),
            "counted_once": real.replace('return row.cond == "life_missing" ? LifeMissing(situation) :', 'return row.cond == "life_missing" ? 1.0 :'),
            "holds_at_full_life": real.replace("return LifeMissing(situation) > 0;", "return LifeMissing(situation) < 0;"),
            "number_not_counted": real.replace("out.push_back(number * Counted(row, situation));", "out.push_back(number);"),
            "the_first_look_waits": real.replace("return !looked || static_cast<std::uint32_t>(nowMs - lastMs) >= periodMs;", "return looked && static_cast<std::uint32_t>(nowMs - lastMs) >= periodMs;"),
            "the_look_comes_a_tick_late": real.replace("static_cast<std::uint32_t>(nowMs - lastMs) >= periodMs", "static_cast<std::uint32_t>(nowMs - lastMs) > periodMs"),
            "the_look_ignores_a_wrapped_clock": real.replace("return !looked || static_cast<std::uint32_t>(nowMs - lastMs) >= periodMs;", "return !looked || nowMs >= lastMs + periodMs;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows + self.other(), name)
                self.assertNotEqual(want, got, name + " survived")


class Wiring(unittest.TestCase):
    POWERS = item_powers_source.CPP_WITH_HEADER

    def check(self, powers):
        """The guards on how the speed reaches the sheet; raises AssertionError on a mutant."""
        clocks = item_powers_source.named("dc_item_powers_clocks.cpp") if powers is None else powers
        body = clocks[clocks.index("void MovementSpeed(Player* player)"):]
        body = body[:body.index("\n        }\n") + 11]
        assert "if (!Data().speed)" in body, "the player is looked at only when some row gives speed"
        assert 'DC::Tunables::Get("combat", "item_power_speed_look_seconds")' in body, "the look period is the tunable"
        assert "ItemPower::LookDue(clock.speedLooked, clock.speedAt, now," in body, "the look is due by the rule"
        assert body.index("ItemPower::LookDue(") < body.index("ItemPower::Situation seen = Seen(player);"), "the Life is read after the look is due"
        assert 'ItemPower::PlayerSum(Data().rows, CountsOf(guid), "movement_speed_pct", SituationOf(guid, std::move(seen)))' in body, "the number is the rows' sum with a fresh read"
        assert "changed = speed != mine->second.movementSpeed;" in body and "if (!changed)\n                return;" in body, "redone only when it changed"
        assert "Stats::RemoveContribution(guid, Source::Temporary, Stat::MovementSpeed, SpeedId);" in body, "the old number comes off"
        assert "Stats::AddContribution(guid, {Source::Temporary, Stat::MovementSpeed, SpeedId, speed, Bucket::Uncapped});" in body, "the new one goes on the sheet's movement speed"
        assert "Stats::Recompute(player);" in body and "Inventory::PushSheet(player);" in body, "the sheet is recomputed and sent"

    def test_the_speed_reaches_the_sheet(self):
        self.check(None)
        update = item_powers_source.named("dc_item_powers.cpp")
        assert re.search(r"StandStill\(player\);(\s+\w+\(player\);)*\s+MovementSpeed\(player\);", update), "the update hook looks at it"
        assert 'loaded.speed = loaded.speed || (row.kind == "player" && row.stat == "movement_speed_pct");' in update, "the table notes that a row gives speed"
        internal = item_powers_source.named("dc_item_powers_internal.h")
        assert "constexpr std::uint64_t SpeedId = OverCapId + 3;" in internal, "its contribution has an id of its own"

    def test_the_guards_fail_their_mutants(self):
        clocks = item_powers_source.named("dc_item_powers_clocks.cpp")
        mutants = {
            "no_flag_gate": clocks.replace("if (!Data().speed)\n                return;", "", 1),
            "a_fixed_period": clocks.replace('DC::Tunables::Get("combat", "item_power_speed_look_seconds") * 1000.0', "250.0", 1),
            "no_look_rule": clocks.replace("ItemPower::LookDue(clock.speedLooked, clock.speedAt, now,", "(true || clock.speedLooked) && (clock.speedAt, now,", 1),
            "stale_life": clocks.replace('"movement_speed_pct", SituationOf(guid, std::move(seen)))', '"movement_speed_pct", SituationOf(guid))', 1),
            "always_redone": clocks.replace("changed = speed != mine->second.movementSpeed;", "changed = true;", 1),
            "old_number_stays": clocks.replace("Stats::RemoveContribution(guid, Source::Temporary, Stat::MovementSpeed, SpeedId);", "", 1),
            "capped_bucket": clocks.replace("speed, Bucket::Uncapped}", "speed, Bucket::Flat}", 1),
            "wrong_stat": clocks.replace("{Source::Temporary, Stat::MovementSpeed, SpeedId, speed", "{Source::Temporary, Stat::AttackSpeed, SpeedId, speed", 1),
            "not_sent": (lambda at: clocks[:at] + clocks[at + len("Inventory::PushSheet(player);"):])(
                clocks.index("Inventory::PushSheet(player);", clocks.index("void MovementSpeed(Player* player)"))),
        }
        for name, edit in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(clocks, edit, name + " did not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    self.check(edit)


if __name__ == "__main__":
    unittest.main()

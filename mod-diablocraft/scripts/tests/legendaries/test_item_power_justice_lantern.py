"""Legendary rest, bead diablocraft-snng3: Justice Lantern (ring, any class). N-DERIVED (a damage figure derived from the Block Chance).

  "Gain damage reduction equal to [45-55]% of your Block Chance."
  * the numbers (45 to 55) are read from d3planner (item_finger.js, leg_justicelantern; stats_full.js adds block x N x 0.01 to the damage reduction); the table
    (data/legendary_powers.csv) holds ONE `player` row for the pool item P4_Unique_Ring_03: `damage_reduction_of_block_pct`, 45-55, always on, which the roller
    rolls once per item (the ring's fixed Block Chance and control-duration cut are the item side's, not this bead);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat
    as an always-on player row of at most 100, and refuses a condition, an event, a skill row, a number above 100;
  * the production rule (src/combat/dc_item_power_math.h: BlockReductionFactor) is compiled and driven with the generated row: 1 - N x B/10000 of the item's
    stored roll, B the Block Chance in percent, nothing with no Block Chance or the item unworn or unrolled, a second source multiplies, the cut is held to 0-100;
    mutants of the rule and of the row fail the same driver;
  * source-text guards for the server side (dc_item_powers_readers.cpp IncomingFactor and BlockChanceNow): the Block Chance is the sheet's with what the worn
    items add under the cap Mitigate rolls with, worked out only when some row cuts by it and before the lock, and the factor is one of the factors of the
    damage taken; mutants of that text are caught. The in-game steps are in docs/test-diablocraft-snng3.md.
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
COMBAT = SRC / "combat/dc_combat.cpp"
HARNESS = MODULE / "tests/item_power_justice_lantern/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P4_Unique_Ring_03"
STAT = "damage_reduction_of_block_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
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
    """(low, high) of the share, in percent of the Block Chance, as the planner words it."""
    text = (REPO / "reference/d3planner/item_finger.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("\n  },", start)]
    m = re.search(r'Gain damage reduction equal to %d%% of your Block Chance\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_source_gives_the_range(self):
        self.assertEqual((45.0, 55.0), numbers())
        stats = (REPO / "reference/d3planner/stats_full.js").read_text(encoding="utf-8")
        self.assertIn('this.add("dmgred", this.block * this.leg_justicelantern * 0.01, 1, "P4_Unique_Ring_03");', stats)

    def test_one_player_row_holds_the_range(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, *BLANK)], mine())

    def test_the_row_has_its_source_and_says_how_it_combines(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_finger.js", rows[0]["source"])
        self.assertIn("leg_justicelantern", rows[0]["source"])
        self.assertIn("1 - N x B/10000", rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Gain damage reduction equal to 45–55% of your Block Chance.", m[1])

    def test_the_power_is_in_the_contract(self):
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertIn("### Justice Lantern (`diablocraft-snng3`", text)


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "45", "value_max": "55", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="lantern-gen-", dir=str(SCRATCH)))
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

    def test_the_row_is_accepted_at_a_hundred(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))
        self.assertEqual(1, len([r for r in self.render_with({"value_min": "100", "value_max": "100"}) if r[0] == OWNER]))

    def test_it_refuses_what_the_code_does_not_read(self):
        refused = {
            "a condition": {"cond": "life_missing"},
            "an event": {"fire_on": "hit_generator"},
            "a skill row": {"kind": "skill", "skill": "Leap"},
            "above a hundred": {"value_min": "45", "value_max": "101"},
            "a skill list": {"cond_skills": "Leap"},
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
        return Path(tempfile.mkdtemp(prefix="lantern-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = lambda roll: clear + [(T("wears", OWNER), None), (T("value", OWNER, "", STAT, roll), None)]  # noqa: E731
        cut = lambda roll, block: g(1 - roll * block / 10000)  # noqa: E731
        # not worn, worn with no roll, a roll in the bag: nothing, whatever the Block Chance
        out += clear + [(T("blockred", 50), "1")]
        out += clear + [(T("wears", OWNER), None), (T("blockred", 50), "1")]
        out += clear + [(T("value", OWNER, "", STAT, high), None), (T("blockred", 50), "1")]
        # worn and rolled: 1 - N x B/10000 at both ends of the range and between, at every Block Chance from none to the cap
        for roll in (low, 50, high):
            for block in (0, 1, 12, 25, 40, 75):
                out += worn(roll) + [(T("blockred", block), cut(roll, block))]
        # a negative Block Chance is none; a share of 100 at the cap of 100 is the whole cut, held
        out += worn(high) + [(T("blockred", -5), "1")]
        out += worn(100) + [(T("blockred", 100), "0")]
        out += worn(100) + [(T("blockred", 250), "0")]
        # a second source is a multiplier of its own
        out += worn(high) + [(T("wears", "Other Ring"), None), (T("blockred", 20), g((1 - high * 20 / 10000) * (1 - 10 * 20 / 10000)))]
        # the stat is a player stat, not another figure
        out += worn(high) + [(T("reduction"), "1"), (T("factor", "damage_dealt_pct"), "1"), (T("sum", "damage_reduction_pct"), "0")]
        # the range rolls once per item (a Primal stores the top)
        out += [(T("roll", OWNER, 1), "power::%s=%g;" % (STAT, high)), (T("roll", OWNER, 0), "power::%s=%g;" % (STAT, (low + high) / 2))]
        return out

    def other(self):
        return [("Other Ring", 0, "player", "", STAT, 10.0, 10.0, *BLANK)]

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
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows + self.other(), "want")
        row_mutants = {
            "the_row_lost": [],
            "the_number_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_stat_changed": [r[:4] + ("damage_reduction_pct",) + r[5:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + self.other(), name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "block_not_a_share": real.replace("share * std::max(0.0, blockChancePct) / 100.0", "share / 100.0"),
            "share_not_a_share": real.replace("share * std::max(0.0, blockChancePct) / 100.0", "blockChancePct / 100.0"),
            "the_cut_not_held": real.replace("std::clamp(share * std::max(0.0, blockChancePct) / 100.0, 0.0, 100.0) / 100.0", "(share * std::max(0.0, blockChancePct) / 100.0) / 100.0"),
            "the_cut_added_not_multiplied": real.replace("factor *= 1.0 - std::clamp(share * std::max(0.0, blockChancePct)", "factor = 1.0 - std::clamp(share * std::max(0.0, blockChancePct)"),
            "the_cut_is_a_gain": real.replace("factor *= 1.0 - std::clamp(share * std::max(0.0, blockChancePct)", "factor *= 1.0 + std::clamp(share * std::max(0.0, blockChancePct)"),
            "the_stat_read_is_another": real.replace('"damage_reduction_of_block_pct", situation))\n            factor', '"damage_reduction_pct", situation))\n            factor'),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows + self.other(), name)
                self.assertNotEqual(want, got, name + " survived")


class Wiring(unittest.TestCase):
    def check(self, readers, powers, combat):
        """The guards on how the Block Chance reaches the rule; raises AssertionError on a mutant."""
        chance = readers[readers.index("double BlockChanceNow(Player const* player)"):]
        chance = chance[:chance.index("\n    }\n") + 7]
        assert "Stats::Get(player->GetGUID().GetRawValue())" in chance, "the sheet's Block Chance"
        assert "(*sheet)[Stat::BlockChance]" in chance, "the sheet's own stat"
        assert "double const bonus = BlockBonus(player);" in chance, "what the worn items add"
        assert "ItemBlock::Chance((*sheet)[Stat::BlockChance], bonus, bonus > 0 ? NumericData::Block().totalChanceCap : 0.0)" in chance, "under the cap Mitigate uses"
        mitigate_chance = "ItemBlock::Chance(s[Stat::BlockChance], bonus, bonus > 0 ? NumericData::Block().totalChanceCap : 0.0)"
        assert mitigate_chance in combat, "Mitigate rolls the block with the same cap"
        incoming = readers[readers.index("double IncomingFactor(Player const* player)"):]
        incoming = incoming[:incoming.index("\n    }\n") + 7]
        assert "double const block = Data().blockReduction ? BlockChanceNow(player) : 0.0;" in incoming, "worked out only when a row cuts by it"
        assert incoming.index("BlockChanceNow(player)") < incoming.index("std::lock_guard<std::mutex> lock(mutex);"), "before the lock"
        assert "ItemPower::BlockReductionFactor(Data().rows, CountsOf(guid), situation, block)" in incoming, "one of the factors of the damage taken"
        assert 'loaded.blockReduction = loaded.blockReduction || (row.kind == "player" && row.stat == "damage_reduction_of_block_pct");' in powers, "the table notes that a row cuts by it"
        assert readers.count("BlockChanceNow(") == 2, "one definition, one use"

    def test_the_block_chance_reaches_the_rule(self):
        self.check(item_powers_source.named("dc_item_powers_readers.cpp"), item_powers_source.named("dc_item_powers.cpp"), COMBAT.read_text(encoding="utf-8"))

    def test_the_guards_fail_their_mutants(self):
        readers = item_powers_source.named("dc_item_powers_readers.cpp")
        powers = item_powers_source.named("dc_item_powers.cpp")
        combat = COMBAT.read_text(encoding="utf-8")
        mutants = {
            "no_sheet": dict(readers=readers.replace("Stats::Get(player->GetGUID().GetRawValue())", "Stats::Get(0)", 1)),
            "no_item_bonus": dict(readers=readers.replace("double const bonus = BlockBonus(player);", "double const bonus = 0.0;", 1)),
            "another_cap": dict(readers=readers.replace("bonus > 0 ? NumericData::Block().totalChanceCap : 0.0);\n    }", "bonus > 0 ? 100.0 : 0.0);\n    }", 1)),
            "always_worked_out": dict(readers=readers.replace("Data().blockReduction ? BlockChanceNow(player) : 0.0", "BlockChanceNow(player)", 1)),
            "not_in_the_damage_taken": dict(readers=readers.replace("ItemPower::BlockReductionFactor(Data().rows, CountsOf(guid), situation, block)", "1.0", 1)),
            "flag_not_set": dict(powers=powers.replace('loaded.blockReduction = loaded.blockReduction ||', 'loaded.blockReduction = false ||', 1)),
            "worked_out_under_the_lock": dict(readers=readers.replace("        double const block = Data().blockReduction ? BlockChanceNow(player) : 0.0;\n        std::map<std::string, unsigned> const stacks = BuffStacks(player);\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);",
                                                                      "        std::map<std::string, unsigned> const stacks = BuffStacks(player);\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        double const block = Data().blockReduction ? BlockChanceNow(player) : 0.0;", 1)),
        }
        for name, edit in mutants.items():
            with self.subTest(mutant=name):
                before = dict(readers=readers, powers=powers, combat=combat)
                self.assertNotEqual(before, {**before, **edit}, name + " did not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    self.check(**{**before, **edit})


if __name__ == "__main__":
    unittest.main()

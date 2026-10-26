"""Legendary rest, bead diablocraft-tgiih: Heart of Iron (chest armor, any class), N-DERIVED (a sheet number that is a share of another sheet stat).

  "Gain Thorns equal to [250-300]% of your Vitality."
  * the text and range are read from d3planner (data.json items P4_Unique_Chest_018, leg_heartofiron, min 250 max 300) and the catalogue row; the power file
    (decode_pow.py item P4_Unique_Chest_018 -> P4_ItemPassive_Unique_Ring_036.pow, 2.5-3) holds no other number; the table (data/legendary_powers.csv) holds ONE `player` row
    for the pool item: `thorns_per_vitality_pct` 250-300, rolled once per item (a Primal takes 300);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses the stat with a set
    level, a condition or an event;
  * the production rule (src/combat/dc_item_power_math.h: ThornsOfVitality through PlayerSum) is compiled and driven with the generated row: the Thorns are N/100 x the
    sheet's Vitality with the item's stored roll, only while worn, none for a Vitality of 0 or less, two sources add; a Primal stores 300 (Best);
  * mutants of the rule and of the row fail the same driver; source-text guards on the server reader (dc_item_powers_clocks.cpp VitalityThorns) follow, with their own mutants.
    The in-game steps are in docs/test-diablocraft-tgiih.md.
"""
import csv
import json
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
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_heart_of_iron/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P4_Unique_Chest_018"
STAT = "thorns_per_vitality_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
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


def planner():
    """(text, min, max) of the pool item's power in d3planner's data.json."""
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_sources_say_250_to_300_percent_of_vitality(self):
        text, low, high = planner()
        self.assertEqual("Gain Thorns equal to %d%% of your Vitality.", text)
        self.assertEqual((250.0, 300.0), (low, high))
        catalogue = [r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Gain Thorns equal to [250-300]% of your Vitality.", catalogue[0]["power_text"])

    def test_one_player_row_holds_them(self):
        _, low, high = planner()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, *BLANK)], mine())

    def test_the_item_rolls_thorns_and_vitality_beside_it(self):
        # the chest's own affixes (base_items.csv) include thorns and vit; the power is the third Thorns source, not a replacement
        item = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertIn("thorns", item["preset_affixes"].split(";"))
        self.assertIn("vit", item["preset_affixes"].split(";"))


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "250", "value_max": "300", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="hoi-gen-", dir=str(SCRATCH)))
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

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a set level": ({"owner": "Immortal King's Call", "pieces": "4", "value_min": "250", "value_max": "250"}, "no set level"),
            "a condition": ({"cond": "quiet_stacks", "cond_arg": "2", "stack_seconds": "1", "stack_max": "2"}, "simply on"),
            "an event": ({"fire_on": "kill"}, "simply on|an event fires"),
            "a negative number": ({"value_min": "-250", "value_max": "-250"}, "needs 0 < value_min <= value_max"),
            "a zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)


def _player_sum():
    text = MATH.read_text(encoding="utf-8")
    body = text[text.index("inline double PlayerSum("):]
    return body[:body.index("\n    }\n") + 7]


PLAYER_SUM = _player_sum()


class Rules(unittest.TestCase):
    OTHER = ("Other Chest", 0, "player", "", STAT, 1.0, 500.0, *BLANK)     # a ranged row: the driver sets its stored roll
    ODD = ("Odd Chest", 0, "player", "", "damage_dealt_pct", 300.0, 300.0, *BLANK)   # another stat: not Thorns

    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemhoi-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows + [self.OTHER, self.ODD]]
        clear = (T("clear"), None)
        wear = lambda roll: [clear, (T("wears", OWNER), None), (T("stored", OWNER, STAT, roll), None)]  # noqa: E731
        # not worn: nothing, whatever the Vitality, even with the roll known
        out += [clear, (T("thorns", 1000), "0"), (T("stored", OWNER, STAT, low), None), (T("thorns", 1000), "0")]
        # worn, each end of the roll: N/100 x Vitality
        for roll in (low, high):
            out += wear(roll)
            for vitality in (1, 1000, 1234.5, 40000):
                out += [(T("thorns", vitality), g(roll / 100 * vitality))]
        # a Vitality of nothing or below gives nothing
        out += wear(high) + [(T("thorns", 0), "0"), (T("thorns", -50), "0")]
        # two sources add (a flat Thorns source each): 250% and 100% of 100 Vitality
        out += wear(low) + [(T("wears", "Other Chest"), None), (T("stored", "Other Chest", STAT, 100), None), (T("thorns", 100), g((low + 100) / 100 * 100))]
        # another stat of another item is not Thorns
        out += [clear, (T("wears", "Odd Chest"), None), (T("thorns", 1000), "0")]
        # a Primal stores the top of the range
        out += [(T("best", 0), g(high))]
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
        self.assertGreater(len(want), 12)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row_mutants = {
            "the_wrong_stat": [r[:4] + ("damage_dealt_pct",) + r[5:] for r in rows],
            "the_wrong_owner": [("Other Chest",) + r[1:] for r in rows],
            "the_range_fixed_at_the_bottom": [r[:6] + (r[5],) + r[7:] for r in rows],
            "the_range_fixed_at_the_top": [r[:5] + (r[6],) + r[6:7] + r[7:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double ThornsOfVitality("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "percent_as_a_fraction": ("* std::max(0.0, vitality) / 100.0", "* std::max(0.0, vitality)"),
            "a_tenth": ("* std::max(0.0, vitality) / 100.0", "* std::max(0.0, vitality) / 1000.0"),
            "negative_vitality_counts": ("std::max(0.0, vitality)", "vitality"),
            "another_stat": ('"thorns_per_vitality_pct"', '"damage_dealt_pct"'),
            "vitality_ignored": ("* std::max(0.0, vitality) / 100.0", "/ 100.0"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_bottom_not_the_roll": real.replace("number = found->value;", "number = row.min;"),
            "sources_do_not_add": real.replace(PLAYER_SUM, PLAYER_SUM.replace("sum += value;", "sum = value;")),
            "a_primal_stores_the_bottom": real.replace('return row.stat == "resource_threshold_pct" || row.stat == "damage_generation_cut_pct" ? row.min : row.max;', "return row.min;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


class Server(unittest.TestCase):
    """Text guards on the one server reader. Nothing here runs the worldserver; the in-game steps are in the test sheet."""

    CLOCKS = item_powers_source.FOLDER / "dc_item_powers_clocks.cpp"

    def failures(self, clocks, powers, header):
        wrong = []

        def need(why, ok):
            if not ok:
                wrong.append(why)

        body = clocks[clocks.index("void VitalityThorns(Player* player)"):]
        body = body[:body.index("\n        }\n")]
        need("watched only when some row holds the stat", "if (!Data().vitalityThorns)\n                return;" in body)
        need("only for a player who wears something that owns a power", "if (mine == clocks.end())\n                    return;" in body)
        need("the Vitality is the sheet's, read before the lock", "double const vitality = sheet ? (*sheet)[Stat::Vitality] : 0.0;" in body
             and "Stats::Get(guid)" in body and body.index("Stats::Get(guid)") < body.index("std::lock_guard<std::mutex> lock(mutex);"))
        need("the number is the production rule over the rows in play, under the lock",
             "thorns = ItemPower::ThornsOfVitality(Data().rows, CountsOf(guid), vitality, SituationOf(guid));" in body
             and body.index("std::lock_guard") < body.index("ThornsOfVitality"))
        need("redone only when it changed", "changed = thorns != clock.vitalityThorns;" in body and "if (!changed)\n                return;" in body)
        need("the sheet gets a Temporary flat Thorns contribution of the item powers' own id, the old one taken off first",
             "Stats::RemoveContribution(guid, Source::Temporary, Stat::Thorns, VitalityThornsId);" in body
             and "if (thorns > 0)\n                Stats::AddContribution(guid, {Source::Temporary, Stat::Thorns, VitalityThornsId, thorns, Bucket::Flat});" in body)
        need("the sheet is recomputed and pushed", "Stats::Recompute(player);\n            Inventory::PushSheet(player);" in body)
        need("a row that gives Thorns by Vitality turns the watch on",
             'loaded.vitalityThorns = loaded.vitalityThorns || row.stat == "thorns_per_vitality_pct";' in powers)
        need("the update hook reads it", "VitalityThorns(player);" in powers and powers.count("VitalityThorns(player);") == 1)
        need("the id is not another contribution's", "constexpr std::uint64_t VitalityThornsId = OverCapId + 4;" in header
             and "constexpr std::uint64_t SpeedId = OverCapId + 3;" in header
             and "constexpr std::uint64_t RegenId = OverCapId + 2;" in header and "constexpr std::uint64_t CostFreeId = OverCapId + 1;" in header)
        return wrong

    def test_the_server_reader_is_what_the_rules_say(self):
        header = (item_powers_source.FOLDER / item_powers_source.HEADER).read_text(encoding="utf-8")
        self.assertEqual([], self.failures(self.CLOCKS.read_text(encoding="utf-8"), item_powers_source.CPP.read_text(encoding="utf-8"), header))

    def test_the_text_mutants_are_caught(self):
        clocks = self.CLOCKS.read_text(encoding="utf-8")
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        header = (item_powers_source.FOLDER / item_powers_source.HEADER).read_text(encoding="utf-8")
        mutants = {
            "always_watched": (clocks, "if (!Data().vitalityThorns)", "if (false)"),
            "no_player_check": (clocks, "if (mine == clocks.end())\n                    return;", ""),
            "not_the_sheets_vitality": (clocks, "(*sheet)[Stat::Vitality]", "(*sheet)[Stat::Strength]"),
            "vitality_read_under_the_lock": (clocks, "auto const sheet = Stats::Get(guid);", ""),
            "not_the_production_rule": (clocks, "ItemPower::ThornsOfVitality(Data().rows, CountsOf(guid), vitality, SituationOf(guid))", "vitality"),
            "always_redone": (clocks, "changed = thorns != clock.vitalityThorns;", "changed = true;"),
            "never_redone": (clocks, "changed = thorns != clock.vitalityThorns;", "changed = false;"),
            "wrong_sheet_stat": (clocks, "Stat::Thorns, VitalityThornsId, thorns,", "Stat::LifeRegen, VitalityThornsId, thorns,"),
            "wrong_bucket": (clocks, "thorns, Bucket::Flat}", "thorns, Bucket::Percent}"),
            "old_one_not_removed": (clocks, "Stats::RemoveContribution(guid, Source::Temporary, Stat::Thorns, VitalityThornsId);", ""),
            "no_recompute": (clocks, "Stats::Recompute(player);\n            Inventory::PushSheet(player);", ""),
            "flag_never_set": (powers, 'loaded.vitalityThorns = loaded.vitalityThorns || row.stat == "thorns_per_vitality_pct";', ""),
            "not_called": (powers, "                VitalityThorns(player);\n", ""),
            "shared_id": (header, "VitalityThornsId = OverCapId + 4;", "VitalityThornsId = OverCapId + 3;"),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                at = where.rindex(old)   # VitalityThorns is the last function of the clocks file; StandStill above it has the same lines
                mutated = where[:at] + new + where[at + len(old):]
                args = [clocks, powers, header]
                args[[clocks, powers, header].index(where)] = mutated
                self.assertTrue(self.failures(*args), name + " survived")


if __name__ == "__main__":
    unittest.main()

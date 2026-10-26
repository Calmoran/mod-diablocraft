"""Legendary rest, bead diablocraft-pruc8: Pride's Fall (helm, any class), N-COST (a resource cost cut that a condition switches).

  "Your resource costs are reduced by 30% after not taking damage for 5 seconds."
  * the numbers are the power file's (decode_pow.py power ItemPassive_Unique_Helm_017_x1: SF_0 'Seconds of No Damage' 5, SF_1 'Resource Cost Reduction %' 0.3) and the catalogue
    row's text; the table (data/legendary_powers.csv) holds ONE `player` row for the pool item: `resource_cost_reduction_pct` 30 under the new condition `no_damage_for` with
    cond_arg 5 (seconds);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses the stat with a set level, an
    event or 100 or more, `no_damage_for` without seconds, with cond_skills or on a skill row;
  * the production rules (src/combat/dc_item_power_math.h: QuietFor through Holds, CostCutPct) are compiled and driven with the generated row: the cut is 30 once 5 s have passed
    since the later of the item going on and the last damage taken, 0 before, 0 when the item is off, a hit starts the count again, a wrapped clock is no break;
  * mutants of the rules and of the row fail the same driver; source guards on the server reader (dc_item_powers_clocks.cpp NoDamageCost) follow.
    The in-game steps are in docs/test-diablocraft-pruc8.md.
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
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_life_and_cost/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Helm_103_x1"
STAT, COND = "resource_cost_reduction_pct", "no_damage_for"
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


def mine(owner, rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == owner]


def render_rows(owner, *sheet_rows):
    """generator.rows over the real module with `owner`'s rows replaced by the given ones (dicts of csv columns)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="life-gen-", dir=str(SCRATCH)))
    try:
        shutil.copytree(MODULE / "data/d3", work / "data/d3")
        shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
        sheet = read_csv("data/legendary_powers.csv")
        kept = [r for r in sheet if r["owner"] != owner]
        with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, list(sheet[0].keys()))
            writer.writeheader()
            writer.writerows(kept + list(sheet_rows))
        return generator.rows(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def build(header_text, name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
    work = Path(tempfile.mkdtemp(prefix="itemlife-%s-" % name, dir=str(SCRATCH)))
    return work, binary


def drive(cases, header_text, name):
    """(wanted, got) of the cases (lines, wanted-or-None) run through the harness built on `header_text`."""
    work, binary = build(header_text, name)
    try:
        (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def function_body(text, signature):
    body = text[text.index(signature):]
    return body[:body.index("\n    }\n") + 7]


class Table(unittest.TestCase):
    def test_the_sources_say_30_percent_after_5_seconds(self):
        catalogue = [r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Your resource costs are reduced by 30% after not taking damage for 5 seconds.", catalogue[0]["power_text"])
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        for cited in ("SF_0 'Seconds of No Damage' = 5", "SF_1 'Resource Cost Reduction %' = 0.3"):
            self.assertIn(cited, row["source"])

    def test_one_player_row_holds_them(self):
        self.assertEqual([(OWNER, 0, "player", "", STAT, 30.0, 30.0, COND, 5.0, "", 0.0, 0, "", "", 100.0, 0.0)], mine(OWNER))


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "30", "value_max": "30", "cond": COND,
            "cond_arg": "5", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def test_the_real_row_passes(self):
        self.assertEqual(1, len(mine(OWNER, render_rows(OWNER, self.BASE))))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a set level": ({"owner": "Immortal King's Call", "pieces": "4"}, "no_damage_for is an item"),
            "an event": ({"fire_on": "kill"}, "no_damage_for is an item|an event fires"),
            "no seconds": ({"cond_arg": ""}, "needs cond_arg > 0 seconds"),
            "cond skills": ({"cond_skills": "Sprint"}, "no_damage_for is an item"),
            "a skill row": ({"kind": "skill", "skill": "Frenzy", "stat": "damage_increase_pct"}, "no_damage_for is an item"),
            "a hundred percent": ({"value_min": "100", "value_max": "100"}, "percent below 100"),
            "a negative number": ({"value_min": "-30", "value_max": "-30"}, "needs 0 < value_min <= value_max"),
            "stack numbers": ({"stack_seconds": "1", "stack_max": "1"}, "only"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    render_rows(OWNER, {**self.BASE, **edit})


class Rules(unittest.TestCase):
    ZERO = ("Zero Helm", 0, "player", "", STAT, 30.0, 30.0, COND, 0.0, *BLANK[2:])   # no seconds: a row the generator refuses, which the rule must never hold
    ODD = ("Odd Helm", 0, "player", "", "damage_dealt_pct", 30.0, 30.0, COND, 5.0, *BLANK[2:])   # another stat under the condition: not a cost cut

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows + [self.ODD, self.ZERO]]
        clear = (T("clear"), None)

        def at(now, worn=0, hurt=None):
            lines = [clear, (T("wears", OWNER, worn), None), (T("now", now), None)]
            return lines + ([(T("hurt", 1, hurt), None)] if hurt is not None else [])
        # not worn: nothing, however long ago
        out += [clear, (T("now", 99999), None), (T("cost"), "0"), (T("holds", 0), "0")]
        # worn and never hit: 5 s after it went on, not a millisecond before
        for now, cut in ((0, 0), (4999, 0), (5000, 30), (60000, 30)):
            out += at(now) + [(T("cost"), g(cut)), (T("holds", 0), "1" if cut else "0")]
        # hit at 10000: the count starts again from the hit
        for now, cut in ((10000, 0), (14999, 0), (15000, 30), (20000, 30)):
            out += at(now, hurt=10000) + [(T("cost"), g(cut))]
        # a hit before the item went on is no break: the count runs from the item
        out += at(24999, worn=20000, hurt=15000) + [(T("cost"), "0")] + at(25000, worn=20000, hurt=15000) + [(T("cost"), "30")]
        # a hit taken, then again: the later hit wins
        out += at(16000, hurt=12000) + [(T("cost"), "0")] + at(17000, hurt=12000) + [(T("cost"), "30")]
        # hurt flag off: the last-hurt number is ignored
        out += [clear, (T("wears", OWNER, 0), None), (T("now", 5000), None), (T("hurt", 0, 4000), None), (T("cost"), "30")]
        # the clock wrapping past 2^32 is no break
        out += at(4000, worn=4294966000) + [(T("cost"), "30")] + at(3000, worn=4294966000) + [(T("cost"), "0")]
        out += at(6000, worn=4294966000, hurt=4294967000) + [(T("cost"), "30")] + at(4000, worn=4294966000, hurt=4294967000) + [(T("cost"), "0")]
        # no seconds is no promise: a row of 0 seconds never holds
        out += [clear, (T("wears", "Zero Helm", 0), None), (T("now", 9000), None), (T("cost"), "0")]
        # another stat under the condition is not a cost cut
        out += [clear, (T("wears", "Odd Helm", 0), None), (T("now", 9000), None), (T("cost"), "0")]
        return out

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = drive(self.cases(mine(OWNER)), MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine(OWNER)
        want, _ = drive(self.cases(rows), real, "want")
        row_mutants = {
            "ten_seconds": [r[:8] + (10.0,) + r[9:] for r in rows],
            "one_second": [r[:8] + (1.0,) + r[9:] for r in rows],
            "no_condition": [r[:7] + ("",) + r[8:] for r in rows],
            "the_number_halved": [r[:5] + (15.0, 15.0) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_reduction_pct",) + r[5:] for r in rows],
            "the_wrong_owner": [("Other Helm",) + r[1:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = drive(self.cases(mutant_rows), real, name)
                self.assertNotEqual(want, got, name + " survived")
        quiet = function_body(real, "inline bool QuietFor(")
        cost = function_body(real, "inline double CostCutPct(")
        rules = {
            "hit_ignored": (quiet, "if (situation.hurt && static_cast<std::int32_t>(situation.lastHurt - start) > 0)", "if (false)"),
            "item_going_on_ignored": (quiet, "std::uint32_t start = worn->second;", "std::uint32_t start = 0;"),
            "always_the_hit": (quiet, "if (situation.hurt && static_cast<std::int32_t>(situation.lastHurt - start) > 0)", "if (situation.hurt)"),
            "the_flag_ignored": (quiet, "situation.hurt &&", ""),
            "exclusive": (quiet, ">= static_cast<std::int32_t>(seconds * 1000.0)", "> static_cast<std::int32_t>(seconds * 1000.0)"),
            "a_tenth_of_the_seconds": (quiet, "seconds * 1000.0", "seconds * 100.0"),
            "no_seconds_always": (quiet, "|| seconds <= 0", ""),
            "wrong_stat": (cost, '"resource_cost_reduction_pct"', '"damage_dealt_pct"'),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                mutated = real.replace(where, where.replace(old, new, 1))
                try:
                    _, got = drive(self.cases(rows), mutated, name)
                except AssertionError:   # a mutant that does not compile is caught too
                    continue
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "dispatch_lost": real.replace('        if (row.cond == "no_damage_for")\n            return QuietFor(row.owner, row.arg, situation);\n', ""),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = drive(self.cases(rows), header, name)
                self.assertNotEqual(want, got, name + " survived")
        # a rule that ignores the row's seconds fails once the row holds other seconds
        fixed = real.replace("return QuietFor(row.owner, row.arg, situation);", "return QuietFor(row.owner, 5.0, situation);")
        self.assertNotEqual(real, fixed)
        other = [r[:8] + (7.0,) + r[9:] for r in rows]
        self.assertNotEqual(drive(self.cases(other), real, "seven")[1], drive(self.cases(other), fixed, "seven_fixed")[1])


class Server(unittest.TestCase):
    """Text guards on the one server reader. Nothing here runs the worldserver; the in-game steps are in the test sheet."""

    CLOCKS = item_powers_source.FOLDER / "dc_item_powers_clocks.cpp"

    def failures(self, clocks, powers, header):
        wrong = []

        def need(why, ok):
            if not ok:
                wrong.append(why)

        body = clocks[clocks.index("void NoDamageCost(Player* player)"):]
        body = body[:body.index("\n        }\n")]
        need("watched only when some row holds the stat", "if (!Data().quietCost)\n                return;" in body)
        need("only for a player who wears something that owns a power", "if (mine == clocks.end())\n                    return;" in body)
        need("the cut is the production rule over the rows in play, under the lock",
             "cut = ItemPower::CostCutPct(Data().rows, CountsOf(guid), SituationOf(guid));" in body and body.index("std::lock_guard") < body.index("CostCutPct"))
        need("redone only when it changed", "changed = cut != clock.quietCost;" in body and "if (!changed)\n                return;" in body)
        need("the sheet gets a Temporary flat Resource Cost Reduction of the item powers' own id, the old one taken off first",
             "Stats::RemoveContribution(guid, Source::Temporary, Stat::ResourceCostReduction, QuietCostId);" in body
             and "if (cut > 0)\n                Stats::AddContribution(guid, {Source::Temporary, Stat::ResourceCostReduction, QuietCostId, cut, Bucket::Flat});" in body)
        need("the class's gear cost aura is rebuilt from it", "Passives::RefreshModifiers(player);" in body)
        need("a row that cuts the costs turns the watch on", 'loaded.quietCost = loaded.quietCost || row.stat == "resource_cost_reduction_pct";' in powers)
        need("the update hook reads it", "NoDamageCost(player);" in powers and powers.count("NoDamageCost(player);") == 1)
        need("the id is not another contribution's", "constexpr std::uint64_t QuietCostId = OverCapId + 4;" in header
             and "constexpr std::uint64_t CostFreeId = OverCapId + 1;" in header and "constexpr std::uint64_t RegenId = OverCapId + 2;" in header)
        return wrong

    def parts(self):
        return [self.CLOCKS.read_text(encoding="utf-8"), item_powers_source.CPP.read_text(encoding="utf-8"),
                (item_powers_source.FOLDER / item_powers_source.HEADER).read_text(encoding="utf-8")]

    def test_the_server_reader_is_what_the_rules_say(self):
        self.assertEqual([], self.failures(*self.parts()))

    def test_the_text_mutants_are_caught(self):
        parts = self.parts()
        mutants = {
            "always_watched": (0, "if (!Data().quietCost)", "if (false)"),
            "no_player_check": (0, "if (mine == clocks.end())\n                    return;", ""),
            "not_the_production_rule": (0, "ItemPower::CostCutPct(Data().rows, CountsOf(guid), SituationOf(guid))", "30.0"),
            "always_redone": (0, "changed = cut != clock.quietCost;", "changed = true;"),
            "never_redone": (0, "changed = cut != clock.quietCost;", "changed = false;"),
            "wrong_sheet_stat": (0, "Stat::ResourceCostReduction, QuietCostId, cut,", "Stat::CooldownReduction, QuietCostId, cut,"),
            "wrong_bucket": (0, "cut, Bucket::Flat}", "cut, Bucket::Percent}"),
            "old_one_not_removed": (0, "Stats::RemoveContribution(guid, Source::Temporary, Stat::ResourceCostReduction, QuietCostId);", ""),
            "aura_not_rebuilt": (0, "Passives::RefreshModifiers(player);", ""),
            "flag_never_set": (1, 'loaded.quietCost = loaded.quietCost || row.stat == "resource_cost_reduction_pct";', ""),
            "not_called": (1, "                NoDamageCost(player);\n", ""),
            "shared_id": (2, "QuietCostId = OverCapId + 4;", "QuietCostId = OverCapId + 1;"),
        }
        for name, (which, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, parts[which], name + " does not apply")
                at = parts[which].index(old, parts[which].index("void NoDamageCost(") if which == 0 else 0)   # the lines of StandStill above it have the same text
                mutated = list(parts)
                mutated[which] = parts[which][:at] + new + parts[which][at + len(old):]
                self.assertTrue(self.failures(*mutated), name + " survived")


if __name__ == "__main__":
    unittest.main()

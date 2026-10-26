"""Legendary rest, set bead diablocraft-wn9q7: N-SETSTAT (a set level whose bonus is a plain sheet stat) and Asheara's Vestments 2-piece
(4 Blacksmith-crafted pieces). The designer's fold (docs/decisions.md 2026-10-12): this bead is the reader plus the 2-piece; diablocraft-a13xy adds the
other 13 stat-only set levels as rows; Asheara's 3-piece is a13xy's, the 4-piece (followers) is held.

  2-piece: +100 Resistance to All Elements.
  * the number and its affix id are read from d3planner (data_itemsets.js, asheara 2: resall 100), apart from the table; the table
    (data/legendary_powers.csv) holds ONE `stat` row at pieces 2, `resall` 100, a fixed number; the set's four pieces are craft-only;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    refuses a set stat the sheet cannot map (SET_STATS), a range, a skill, a condition or an event;
  * every SET_STATS id is a key of the item affix map (dc_items_data.cpp Mappings), so a set row reaches the sheet as an item's affix does;
  * the production rule (src/combat/dc_item_power_math.h: SetStats, SetStatContributionId) is compiled and driven with the generated rows: the
    row is on from the 2nd distinct piece of its own set, never for an item-owned stat row; its contribution id is its place among the set
    `stat` rows, in 3..255, apart from the weapon's 1-2, the Cube's 256+ and an item's 65536+;
  * mutants of the rule and of the row fail the same driver;
  * source-text guards: Items::RefreshCubedStats (run by Apply after ItemPowers::Refresh, on every equip and unequip) puts the rows on the sheet
    through Mappings() under Source::Items and takes them off with the rest of its list; ItemPowers::SetStats copies the counts under the lock
    and reads the table outside it. The C++ is compile-checked by syntax_check.sh and the in-game step is in docs/test-diablocraft-wn9q7.md.
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import item_powers_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_ashearas_vestments/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SET = "Asheara's Vestments"
ROW = re.compile(r"\('((?:[^']|'')*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1].replace("''", "'"), int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13],
             m[14], float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    """The 2-piece's rows (the 3-piece is a13xy's, test_item_power_stat_set_levels.py)."""
    return [r for r in (all_rows() if rows is None else rows) if r[0] == SET and r[1] == 2]


def planner():
    """The set's 2-piece stats as d3planner lists them: [(affix id, value)]."""
    text = (REPO / "reference/d3planner/data_itemsets.js").read_text(encoding="utf-8")
    start = text.index('name: "%s"' % SET)
    block = text[start:text.index("\n  },", start)]
    two = re.search(r'"2": \[(.*?)\]\s*,\s*"3"', block, re.S)[1]
    return [(s, float(v)) for s, v in re.findall(r'stat: "(\w+)", value: \[(\d+)\]', two)]


def mappings():
    """The item affix map's keys (dc_items_data.cpp Mappings) and their stats."""
    text = items_source.read("dc_items_data.cpp")
    body = text[text.index("std::unordered_map<std::string, StatMapping> const& Mappings()"):]
    body = body[:body.index("return mappings;")]
    return dict(re.findall(r'\{"(\w+)", \{Stat::(\w+)', body))


class Table(unittest.TestCase):
    def test_the_planner_gives_the_two_piece_one_stat(self):
        self.assertEqual([("resall", 100.0)], planner())

    def test_the_one_row_is_the_two_piece(self):
        (stat, value), = planner()
        self.assertEqual([(SET, 2, "stat", "", stat, value, value, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)], mine())

    def test_the_held_and_folded_levels_are_not_here(self):
        # the 3-piece (Life) is a13xy's (test_item_power_stat_set_levels.py), the 4-piece (followers) is held
        self.assertEqual([2, 3], sorted(r[1] for r in all_rows() if r[0] == SET))

    def test_the_owner_is_the_crafted_set(self):
        pieces = [r for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET]
        self.assertEqual(4, len(pieces))
        self.assertTrue(all(r["craft_only"] == "yes" for r in pieces))

    def test_the_row_has_its_source_and_note(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == SET and r["pieces"] == "2"]
        self.assertEqual(1, len(rows))
        self.assertIn("data_itemsets.js:144", rows[0]["source"])
        self.assertIn("N-SETSTAT", rows[0]["note"])

    def test_every_set_stat_is_one_the_sheet_maps(self):
        mapped = mappings()
        self.assertEqual("AllResistance", mapped["resall"])
        self.assertEqual(set(), set(generator.SET_STATS) - set(mapped))


class Generator(unittest.TestCase):
    TWO = {"owner": SET, "pieces": "2", "kind": "stat", "skill": "", "stat": "resall", "value_min": "100", "value_max": "100", "cond": "",
           "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
           "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, two):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="asheara-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != SET]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.TWO, **two}])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == SET]))

    def test_every_set_stat_passes(self):
        for stat in generator.SET_STATS:
            with self.subTest(stat=stat):
                self.assertEqual(1, len([r for r in self.render_with({"stat": stat}) if r[0] == SET]))

    def test_it_refuses_what_the_sheet_cannot_carry(self):
        refused = {
            "a stat the sheet does not map": ({"stat": "meleedef"}, "set level's stat"),
            "a range": ({"value_max": "120"}, "set level's stat|one number"),
            "a skill": ({"skill": "Bash"}, "set level's stat|skill"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Bash"}, "carries no condition"),
            "an event": ({"fire_on": "kill"}, "is not fired"),
            "no number": ({"value_min": "0", "value_max": "0"}, "value_min"),
        }
        for name, (two, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(two)


class Rules(unittest.TestCase):
    def build(self, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="asheara-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """`rows` is the whole generated table: the Asheara row's index is its place among the set stat rows."""
        out = [(T("row", *r), None) for r in rows]
        stats = [r for r in all_rows() if r[1] and r[2] == "stat"]
        on = "%d:%s:resall=100;" % (stats.index(mine()[0]), SET)
        # from the 3rd piece the 3-piece's +20% Life (diablocraft-a13xy) is on beside it
        three, = [r for r in stats if r[0] == SET and r[1] == 3]
        on3 = on + "%d:%s:%s=%g;" % (stats.index(three), SET, three[4], three[5])
        for n, want in ((0, ""), (1, ""), (2, on), (3, on3), (4, on3)):
            out += [(T("clear"), None), (T("set", SET, n), None), (T("stats"), want)]
        # another set's pieces do not count, and an item-owned stat row (pieces 0) is never a set stat
        out += [(T("clear"), None), (T("set", "Immortal King's Call", 6), None), (T("set", "Unique_Mace_1H_011_x1", 6), None), (T("stats"), "")]
        # the ids: 3 for the first, 255 for the 253rd, none past it; the Cube's first is 256 (CubeContributionId(1, 0))
        out += [(T("id", 0), "3"), (T("id", 1), "4"), (T("id", 252), "255"), (T("id", 253), "0")]
        return out

    def apart(self):
        """Two set stat rows: the index is the row's place among them whether or not the earlier one is worn."""
        rows = [("Other Set", 2, "stat", "", "vit", 250.0, 250.0), ("Item_X", 0, "stat", "", "edmg", 5.0, 9.0), (SET, 2, "stat", "", "resall", 100.0, 100.0),
                (SET, 3, "skill", "Bash", "damage_increase_pct", 5.0, 5.0)]
        out = [(T("row", *r), None) for r in rows]
        out += [(T("clear"), None), (T("set", SET, 3), None), (T("stats"), "1:%s:resall=100;" % SET)]
        out += [(T("clear"), None), (T("set", SET, 2), None), (T("set", "Other Set", 2), None), (T("stats"), "0:Other Set:vit=250;1:%s:resall=100;" % SET)]
        out += [(T("clear"), None), (T("set", "Other Set", 1), None), (T("stats"), "")]
        return out

    def drive(self, header_text, cases, name):
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rule_agrees_with_the_set(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), self.cases(all_rows()), "real")
        self.assertEqual(want, got)
        want, got = self.drive(MATH.read_text(encoding="utf-8"), self.apart(), "apart")
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = all_rows()
        row = mine()[0]
        at = rows.index(row)
        row_mutants = {
            "the_row_removed": rows[:at] + rows[at + 1:],
            "a_three_piece": rows[:at] + [(row[0], 3) + row[2:]] + rows[at + 1:],
            "fifty_resistance": rows[:at] + [row[:5] + (50.0, 50.0) + row[7:]] + rows[at + 1:],
            "another_stat": rows[:at] + [row[:4] + ("vit",) + row[5:]] + rows[at + 1:],
        }
        cases = self.cases(rows)
        want = [w for _, w in cases if w is not None]
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                mutant_cases = [(T("row", *r), None) for r in mutant_rows] + [c for c in cases if not c[0].startswith("row\t")]
                _, got = self.drive(real, mutant_cases, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("// N-SETSTAT: the set rows"):]
        body = body[:body.index("// A set's first bonus")]
        rules = {
            "one_piece_short": ("found->second >= row.pieces", "found->second > row.pieces"),
            "item_rows_count": ("if (!row.pieces || row.kind != \"stat\")", "if (row.kind != \"stat\")"),
            "any_kind_counts": ("if (!row.pieces || row.kind != \"stat\")", "if (!row.pieces)"),
            "index_only_when_on": ("            ++index;\n", ""),
            "ids_from_two": ("3 + index", "2 + index"),
            "no_upper_bound": ("index < 253 ? 3 + index : 0", "3 + index"),
            "another_set_counts": ("worn.find(row.owner)", "worn.begin()"),
        }
        apart = self.apart()
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                mutant = real.replace(body, body.replace(old, new, 1))
                if name == "index_only_when_on":
                    mutant = mutant.replace("out.push_back({index, row});", "out.push_back({index++, row});", 1)
                w1, g1 = self.drive(mutant, cases, name)
                w2, g2 = self.drive(mutant, apart, name + "-apart")
                self.assertTrue(w1 != g1 or w2 != g2, name + " survived")


class Guards(unittest.TestCase):
    def setUp(self):
        self.items = items_source.source()
        self.powers = item_powers_source.CPP.read_text(encoding="utf-8")

    def refresh(self):
        body = self.items[self.items.index("void RefreshCubedStats(Player* player)"):]
        return body[:body.index("\n}\n")]

    def test_the_sheet_gets_the_rows_through_the_affix_map(self):
        body = self.refresh()
        loop = body[body.index("for (auto const& [index, row] : DC::Combat::ItemPowers::SetStats(player))"):]
        loop = loop[:loop.index("std::vector<std::pair<Stat, std::uint64_t>> had;")]
        self.assertIn("auto mapping = Mappings().find(row.stat);", loop)
        self.assertIn("DC::Combat::ItemPower::SetStatContributionId(index)", loop)
        self.assertIn("wanted.push_back({Source::Items, mapping->second.stat, id, row.min, mapping->second.bucket, mapping->second.element});", loop)
        # the rows join the same list the Cube's use, so the next refresh takes them off
        self.assertLess(body.index("SetStats(player)"), body.index("RemoveContribution(playerGuid, Source::Items, stat, id)"))

    def test_apply_refreshes_after_the_set_counts(self):
        apply = self.items[self.items.index("DC::Combat::ItemPowers::Refresh(player, item, equipping, *instance);"):]
        self.assertIn("RefreshCubedStats(player);", apply[:apply.index("\n}\n")])

    def test_the_counts_are_copied_under_the_lock_and_read_outside(self):
        body = self.powers[self.powers.index("std::vector<std::pair<unsigned, ItemPower::Row>> SetStats(Player const* player)"):]
        body = body[:body.index("\n    }\n")]
        self.assertLess(body.index("std::lock_guard<std::mutex> lock(mutex);"), body.index("worn = mine->second;"))
        self.assertLess(body.index("worn = mine->second;\n        }"), body.index("return ItemPower::SetStats(Data().rows, worn);"))

    def test_the_source_mutants_fail_the_guards(self):
        mutants = {
            "the_cube_id": ("DC::Combat::ItemPower::SetStatContributionId(index)", "DC::Combat::ItemPower::CubeContributionId(1, index)"),
            "a_gem_source": ("wanted.push_back({Source::Items, mapping->second.stat", "wanted.push_back({Source::Gems, mapping->second.stat"),
            "the_flat_bucket_forced": ("row.min, mapping->second.bucket", "row.min, Bucket::Flat"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, self.items)
                self.items = self.items.replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    self.test_the_sheet_gets_the_rows_through_the_affix_map()
                self.setUp()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""diablocraft-6pmeb: a legendary's fixed stat outside its slot's pool rolls in the item's own range.

The module's own `PlanRoll` is cut out of dc_items_roll.cpp (the cut is test_blacksmith_tooltips.py's), compiled, and run
over The Witching Hour as StageRoll hands it over: the waist pool parsed out of data/generated/affix_pools.sql and the
item's rows parsed out of the generated items_0024_item_preset_ranges.sql. Before the fix both presets were skipped
(the pool has no ias or chd on a belt) and the fill took four random lines. The generator's refusals run on copies of
the sheets in a temp dir; the committed migration must be its render.
"""
from __future__ import annotations

import csv
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import harness_env

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ITEMS_CPP = MODULE / "src/items/dc_items_roll.cpp"
POOLS_SQL = MODULE / "data/generated/affix_pools.sql"
SCRATCH = MODULE.parent / "azerothcore-wotlk/build/_agent-scratch/item-preset-ranges"
WITCHING_HOUR = 100536  # base_item_ids.csv Unique_Belt_009_x1
sys.path.insert(0, str(HERE))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tooltips = load("test_blacksmith_tooltips", HERE / "tests/crafting/test_blacksmith_tooltips.py")
generator = load("generate_item_presets", HERE / "generate/items/generate_item_presets.py")
CXX = shutil.which("c++") or shutil.which("g++")
VALUE = re.compile(r"'((?:[^']|'')*)'|(NULL)|(-?\d+(?:\.\d+)?)")


def tuples(sql: str, table: str) -> list[list]:
    """The value tuples of every INSERT INTO `table`, one list per row, NULL as None."""
    out = []
    for block in re.findall(rf"INSERT INTO `{table}` \([^)]*\) VALUES\n(.*?);\n", sql, re.S):
        for line in block.split("\n"):
            out.append([s.replace("''", "'") if s or not (n or d) else (None if n else float(d))
                        for s, n, d in VALUE.findall(line)])
    return out


def entry(affix_id, name, kind, low, high, step, percent, order):
    return (f'PoolEntry{{"{affix_id}", "{name}", "{kind}", "", {low}, {high}, 0, 0, "", {step or 0}, '
            f'{"true" if percent else "false"}, {int(order)}}}')


def waist_pool(bracket: str) -> list[str]:
    """`in.primary`/`in.secondary` pushes for the waist pool at `bracket`, from the generated SQL."""
    lines = []
    for slot, affix_id, name, kind, low, high, step, b, percent, _src, order, *_ in tuples(
            POOLS_SQL.read_text(encoding="utf-8"), "dc_affix_pool"):
        if slot == "waist" and b == bracket:
            target = "secondary" if kind == "secondary" else "primary"
            lines.append(f"    in.{target}.push_back({entry(affix_id, name, kind, low, high, step, percent, order)});")
    assert lines, f"no waist {bracket} rows in {POOLS_SQL.name}"
    return lines


def item_rows(sql: str, bracket: str) -> list[str]:
    lines = []
    for item, affix_id, name, kind, low, high, step, b, percent, order in tuples(sql, "dc_item_preset_range"):
        if int(item) == WITCHING_HOUR and b == bracket:
            lines.append(f"    in.itemPresets.push_back({entry(affix_id, name, kind, low, high, step, percent, order)});")
    return lines


def plan(bracket: str, counts=(4, 2), sql: str | None = None, items_cpp: Path = ITEMS_CPP) -> dict:
    """Run the compiled PlanRoll for The Witching Hour at `bracket`; fixed lines and the random counts."""
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    sql = generator.sql(generator.rows()) if sql is None else sql
    body = ["    RollPlanInput in;", f"    in.counts = Counts{{{counts[0]}, {counts[1]}}};",
            '    in.presets.push_back("ias");', '    in.presets.push_back("chd");']
    body += waist_pool(bracket) + item_rows(sql, bracket)
    code = f"""#include <algorithm>
#include <iostream>
#include <string>
#include <vector>
namespace DC::Items
{{
{tooltips.cuts(items_cpp)}
}}
using namespace DC::Items;
int main()
{{
{chr(10).join(body)}
    RollPlan const plan = PlanRoll(in);
    for (auto const& f : plan.fixed)
        std::cout << "FIXED " << f.entry.affixId << " " << f.entry.kind << " " << f.entry.min << " " << f.entry.max
                  << " " << f.counted << "\\n";
    std::cout << "RANDOM " << plan.randomPrimary << " " << plan.randomSecondary << "\\n";
}}
"""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=bracket + "-", dir=SCRATCH))
    (folder / "plan.cpp").write_text(code, encoding="utf-8")
    built = subprocess.run([CXX, "-std=c++17", "-o", str(folder / "plan"), str(folder / "plan.cpp")],
                           capture_output=True, text=True)
    assert built.returncode == 0, "PlanRoll did not compile:\n" + built.stderr[-4000:]
    out = harness_env.run([str(folder / "plan")], capture_output=True, text=True, check=True).stdout
    shutil.rmtree(folder)
    fixed = [(a, k, float(lo), float(hi), c == "1") for a, k, lo, hi, c in re.findall(r"^FIXED (\S+) (\S+) (\S+) (\S+) (\d)$", out, re.M)]
    random = tuple(int(n) for n in re.search(r"^RANDOM (\d+) (\d+)$", out, re.M).groups())
    return {"fixed": fixed, "random": random}


class WitchingHourRoll(unittest.TestCase):
    def test_both_lines_fixed_in_their_source_range_at_every_bracket(self):
        for bracket in ("legendary", "ancient", "primal"):
            with self.subTest(bracket=bracket):
                got = plan(bracket)
                self.assertEqual(got["fixed"], [("ias", "primary", 5, 7, True), ("chd", "primary", 26, 50, True)])
                # Both are counted primaries: the fill takes the other two of four, the two secondaries untouched.
                self.assertEqual(got["random"], (2, 2))

    def test_item_rows_never_feed_the_fill(self):
        # A budget larger than the pool: the fill takes every waist primary and no more; the item's two rows
        # would make it primaries + 2.
        primaries = len([l for l in waist_pool("legendary") if "in.primary" in l])
        self.assertEqual(plan("legendary", counts=(primaries + 10, 0))["random"], (primaries, 0))

    def test_without_item_rows_the_presets_are_skipped_as_before(self):
        empty = generator.sql([])
        self.assertEqual(plan("legendary", sql=empty), {"fixed": [], "random": (4, 2)})

    def test_stage_roll_hands_the_item_its_rows_for_its_bracket(self):
        source = ITEMS_CPP.read_text(encoding="utf-8")
        stage = source[source.index("std::unique_ptr<StagedRoll> StageRoll("):]
        self.assertRegex(stage, r"itemPresetRanges\.find\(baseItemId\).*\n.*find\(BracketFor\(base\.rarity, qualityTier\)\)")
        self.assertIn("planning.itemPresets = itemPresets;", stage)
        # Only PlanRoll's preset step reads them: neither fill pool is ever handed an item row.
        self.assertNotRegex(stage, r"(primaryPool|secondaryPool)\.push_back\([^)]*itemPreset")
        self.assertIn("FROM dc_item_preset_range", items_source.source())
        self.assertIn("itemPresetRanges = std::move(loadedPresets);", items_source.source())


class Generator(unittest.TestCase):
    def test_committed_migration_is_the_render(self):
        self.assertEqual(generator.MIGRATION.read_text(encoding="utf-8"), generator.sql(generator.rows()))

    def test_the_sheet_still_carries_the_witching_hours_two_lines(self):
        got = sorted((r[1], r[4], r[5], r[7]) for r in generator.rows() if r[0] == WITCHING_HOUR)
        want = sorted((a, lo, hi, b) for a, lo, hi in (("ias", 5, 7), ("chd", 26, 50))
                      for b in ("legendary", "ancient", "primal"))
        self.assertEqual(got, want)

    @staticmethod
    def witching(rows):
        """The sheet's row these tests mutate: The Witching Hour's attack speed at legendary (the first one 6pmeb wrote)."""
        return next(r for r in rows if r["d3_id"] == "Unique_Belt_009_x1" and r["affix_id"] == "ias"
                    and r["item_level_bracket"] == "legendary")

    def refuse(self, edit, message):
        with tempfile.TemporaryDirectory() as folder:
            d3 = Path(folder)
            for name in ("base_items.csv", "base_item_ids.csv", "affix_pools.csv", "item_preset_ranges.csv",
                         "affix_metadata.csv", "class_resources.csv"):
                shutil.copy(generator.D3 / name, d3 / name)
            path = d3 / "item_preset_ranges.csv"
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            edit(rows)
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, message):
                generator.rows(d3)

    def test_refuses_a_stat_the_slot_pool_already_holds(self):
        # The Sash of Knives-style case: a stat the waist pool rolls belongs to the pool's own row.
        self.refuse(lambda rows: rows.append({**self.witching(rows), "d3_id": "Unique_Gloves_011_x1", "affix_id": "ias"}),
                    "pool already holds it|not one of")
        self.refuse(lambda rows: self.witching(rows).update(affix_id="vit"), "not one of the item's preset_affixes")
        # diablocraft-4ruv4: a Maximum <class resource> row stands for the `resource` preset only on an item that lists
        # it; on The Witching Hour (no `resource`) it is refused.
        self.refuse(lambda rows: self.witching(rows).update(affix_id="maxfury", affix_name="Maximum Fury"),
                    "not one of the item's preset_affixes")

    def test_refuses_a_hands_stat_already_in_the_hands_pool(self):
        def edit(rows):
            gloves = next(r for r in generator.read(generator.D3 / "base_items.csv")
                          if r["slot"] == "hands" and r["rarity"] == "legendary" and r["pool_version"] == "yes"
                          and "ias" in r["preset_affixes"].split(";"))
            rows.append({**Generator.witching(rows), "d3_id": gloves["d3_id"]})
        self.refuse(edit, "pool already holds it")

    def test_refuses_bad_rows(self):
        self.refuse(lambda rows: self.witching(rows).update(d3_id="No_Such_Item"), "no base_items.csv")
        bases = generator.read(generator.D3 / "base_items.csv")
        # diablocraft-jh08v: the guard now mirrors dc_quality_rule.h, so a magic item (the rare bracket) and an
        # ethereal at ancient are what it refuses - a set or a plain legendary is legal data now.
        magic = next(r["d3_id"] for r in bases if r["rarity"] == "magic" and r["pool_version"] == "yes")
        self.refuse(lambda rows: self.witching(rows).update(d3_id=magic), "reads no bracket this sheet models")
        ethereal = next(r["d3_id"] for r in bases if r["rarity"] == "ethereal" and r["pool_version"] == "yes")
        self.refuse(lambda rows: self.witching(rows).update(d3_id=ethereal, item_level_bracket="ancient"), "never ancient")
        self.refuse(lambda rows: self.witching(rows).update(item_level_bracket="rare"), "bracket must be")
        self.refuse(lambda rows: self.witching(rows).update(value_min="9"), "value_min above value_max")
        self.refuse(lambda rows: self.witching(rows).update(source=""), "no source")
        self.refuse(lambda rows: rows.append(dict(self.witching(rows))), "listed twice")


# diablocraft-jh08v: the preset lines the sheet cannot carry, each with the reason it cannot. A line here is a
# known gap, not a silent drop: the preset is skipped by the roller exactly as it was before the sheet existed.
# Empty since diablocraft-dw6gz: the designer's q-1016-14 gave its last two (Holy Beacon dmghol, Bombardier's Rucksack dex).
NO_RANGE: set[tuple[str, str]] = set()  # d3planner has no range for the affix on this item: not its item block, data.json or its type's slots.js list


class Coverage(unittest.TestCase):
    """No preset names an affix the roller would drop, and every line it does drop has one of the three reasons."""

    def test_every_preset_the_sheet_could_carry_has_its_row(self):
        bases = generator.read(generator.D3 / "base_items.csv")
        pools = generator.read(generator.D3 / "affix_pools.csv")
        pool = {(r["slot"], r["affix_id"]) for r in pools}
        have = {(r["d3_id"], r["affix_id"]) for r in generator.read(generator.D3 / "item_preset_ranges.csv")}
        source = items_source.read("dc_items_data.cpp")
        # dc_items_data.cpp Mappings(): the affix -> stat sheet table. An affix absent from it and from the deliberate
        # no-effect list (sockets, durability, chance-on-hit, pickup - the comment above Mappings) cannot be
        # applied, so a row for it would roll a number that does nothing.
        mappable = set(re.findall(r'\{"(\w+)",\s*\{Stat::', source))
        elemental = items_source.table("ElementalAffixes")
        mappable |= set(re.findall(r'\{"(\w+)"', elemental))
        no_effect = {"sockets", "dura", "lvlreq", "onhit", "pickup", "bleed", "ccr", "damage", "edef", "healbonus",
                     "hitblind", "hitchill", "hitfear", "hitfreeze", "hitimmobilize", "hitknockback", "hitslow",
                     "hitstun", "meleedef", "rangedef", "wpnarc", "wpncol", "wpnfir", "wpnhol", "wpnlit", "wpnpsn"}
        skills = set(re.findall(r"\('skill_\w+',\s*'\d+',\s*'(\w+)',",
                                (MODULE / "data/generated/skill_affixes.sql").read_text(encoding="utf-8")))
        dropped = []
        for base in bases:
            if base["pool_version"] != "yes":
                continue
            for affix in (base["preset_affixes"] or "").split(";"):
                affix = affix.strip()
                if (not affix or affix == "custom" or (base["slot"], affix) in pool
                        or (base["d3_id"], affix) in have):
                    continue
                if base["rarity"] not in generator.LEGENDARY_BRACKET:
                    continue  # the rare bracket: the sheet models no row for it (dc_quality_rule.h Bracket)
                if (base["d3_id"], affix) in NO_RANGE:
                    continue
                if affix.startswith("skill_"):
                    # A skill id is never in Mappings() (dc_items_equip.cpp applies it from dc_skill_affix), so a built
                    # one is judged by that table alone; an unbuilt class's skill has nothing to apply it to.
                    if affix not in skills:
                        continue
                elif affix not in mappable and affix not in no_effect:
                    continue  # no Stat in dc_items_data.cpp Mappings() to apply it to
                dropped.append((base["d3_id"], affix))
        self.assertEqual(dropped, [], "a preset the roller could serve has no item_preset_ranges.csv row")


class Sources(unittest.TestCase):
    """Every row's source names a place that says what the row says (diablocraft-651eg)."""

    REF = MODULE.parent / "reference/d3planner"

    @classmethod
    def setUpClass(cls):
        cls.rows = generator.read(generator.D3 / "item_preset_ranges.csv")
        cls.slots = (cls.REF / "slots.js").read_text(encoding="utf-8").splitlines()

    def test_every_slots_cite_holds_the_named_entry_with_the_rows_numbers(self):
        cite = re.compile(r"slots\.js:(\d+) (legendary|ancient|rare) (\w+) (-?[\d.]+)-(-?[\d.]+)")
        seen = 0
        for r in self.rows:
            for line, bracket, var, low, high in cite.findall(r["source"]):
                seen += 1
                text = self.slots[int(line) - 1]
                m = re.match(rf"\s+{var}: \{{min: (-?[\d.]+), max: (-?[\d.]+)", text)
                self.assertTrue(m, f"{r['d3_id']} {r['affix_id']}: slots.js:{line} is {text.strip()!r}, not {var}")
                self.assertEqual((float(m[1]), float(m[2])), (float(low), float(high)), f"slots.js:{line}")
                self.assertEqual((float(r["value_min"]), float(r["value_max"])), (float(low), float(high)),
                                 f"{r['d3_id']} {r['affix_id']} {r['item_level_bracket']}: the cite is not the row's range")
                # the line sits inside the bracket's own block of statLimits
                start = next(i for i, l in enumerate(self.slots) if l == f"  {bracket}: {{")
                self.assertGreater(int(line) - 1, start, f"slots.js:{line} is above the {bracket} block")
        self.assertGreater(seen, 100)

    def test_every_item_cite_names_the_affix_it_is_cited_for(self):
        cite = re.compile(r"reference/d3planner/(item_\w+\.js):(\d+)(?:-(\d+))?")
        for r in self.rows:
            m = cite.search(r["source"])
            if not m:
                self.assertIn("data.json", r["source"], f"{r['d3_id']}: neither an item_*.js line nor data.json")
                continue
            lines = (self.REF / m[1]).read_text(encoding="utf-8").splitlines()
            span = "\n".join(lines[int(m[2]) - 1:int(m[3] or m[2])])
            self.assertRegex(span, rf"\b{re.escape(r['affix_id'])}\b|\bdmg\w+:", f"{r['d3_id']} {m[0]}: {span!r}")

    def test_an_own_fixed_stat_row_says_where_its_name_kind_percent_and_order_came_from(self):
        own = [r for r in self.rows if "the item's own fixed stat" in r["source"]]
        self.assertGreater(len(own), 100)
        for r in own:
            self.assertRegex(r["source"], r"fixed stat \((name[^)]*(pool|data_stats\.js|dc_skill_affix))",
                             f"{r['d3_id']} {r['affix_id']}")


if __name__ == "__main__":
    unittest.main()

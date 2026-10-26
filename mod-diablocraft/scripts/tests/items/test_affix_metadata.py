#!/usr/bin/env python3
"""The preset stats item_preset_ranges.csv could not carry.

(a) Five set shoulders named their All Resistance preset `allres`, an id d3planner defines nowhere (its stat is
`resall`, data_stats.js:46, the id the shoulders pool rolls); base_items.csv respells it and items_0030 carries it.
(b) data/d3/affix_metadata.csv names the stats no slot's pool holds, so a sheet row for one has a name, kind, percent and
order to agree with, and nothing rolls them at random. The metadata is recomputed here from data_stats.js on its own;
the generator's refusals run on copies of the sheets in a temp dir; the committed migrations must be the renders.
"""
from __future__ import annotations

import csv
import importlib.util
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
D3 = MODULE / "data/d3"
STATS = MODULE.parent / "reference/d3planner/data_stats.js"
UPDATES = MODULE / "data/sql/db-world/updates"
SHOULDERS = {"Unique_Shoulder_Set_10_x1", "Unique_Shoulder_Set_05_x1", "Unique_Shoulder_Set_01_p1",
             "Unique_Shoulder_Set_15_x1", "Unique_Shoulder_Set_11_x1"}
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = load("generate_item_presets", HERE / "generate/items/generate_item_presets.py")
gensql = load("generate_sql", HERE / "generate/tooling/generate_sql.py")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class Metadata(unittest.TestCase):
    def test_every_row_is_data_stats_js(self):
        lines = STATS.read_text(encoding="utf-8").splitlines()
        rows = read(D3 / "affix_metadata.csv")
        self.assertEqual(sorted(r["affix_id"] for r in rows),
                         sorted("dmgphy dmgfir dmgcol dmgpsn dmgarc dmglit dmghol expmul mf colddef dex maxfury "
                                "basearmor firetaken apoc manaregen spiritregen lifefury respsn reslit maxap maxdisc "
                                "maxmana damage_demons damage_beasts damage_humans damage_undead maxspirit maxessence maxwrath".split()))
        for r in rows:
            with self.subTest(affix=r["affix_id"]):
                number = next(n for n, line in enumerate(lines, 1) if line.strip().startswith(r["affix_id"] + ": {"))
                line = lines[number - 1]
                self.assertIn(f"data_stats.js:{number} ", r["source"])
                self.assertEqual(r["affix_name"], re.search(r'name: "([^"]+)"', line).group(1))
                self.assertEqual(r["kind"], "secondary" if "secondary: true" in line else "primary")
                self.assertEqual(r["is_percent"], "1" if "percent: true" in line else "0")
                self.assertEqual(r["display_order"], "999")   # after the pool's lines: dc_tooltip.lua's default

    def test_no_metadata_stat_has_a_pool_row(self):
        pooled = {r["affix_id"] for r in read(D3 / "affix_pools.csv")}
        self.assertFalse(pooled & set(generator.metadata()))

    def test_committed_migration_is_the_render(self):
        self.assertEqual(generator.METADATA_MIGRATION.read_text(encoding="utf-8"),
                         generator.metadata_sql(generator.metadata()))
        self.assertEqual(generator.METADATA_MIGRATION.name, "items_0048_affix_metadata_wrath.sql")

    def sheets(self, folder):
        d3 = Path(folder)
        for name in ("base_items.csv", "base_item_ids.csv", "affix_pools.csv", "item_preset_ranges.csv",
                     "affix_metadata.csv", "class_resources.csv"):
            shutil.copy(D3 / name, d3 / name)
        return d3

    def rewrite(self, path, edit):
        rows = read(path)
        edit(rows)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def refuse(self, sheet, edit, message):
        with tempfile.TemporaryDirectory() as folder:
            d3 = self.sheets(folder)
            self.rewrite(d3 / sheet, edit)
            with self.assertRaisesRegex(ValueError, message):
                generator.rows(d3)

    def cindercoat(self, **change):
        # Cindercoat's fixed Fire Damage Increase: no slot's pool holds dmgfir, the metadata does. Its sheet rows are
        # replaced by one that is not an own-stat row, so the metadata is what the row is held to.
        def edit(rows):
            rows[:] = [r for r in rows if r["d3_id"] != "Unique_Chest_006_x1"]
            rows.append({**rows[0], "d3_id": "Unique_Chest_006_x1", "affix_id": "dmgfir",
                         "affix_name": "Fire Damage Increase", "kind": "primary", "is_percent": "1",
                         "display_order": "999", "source": "reference/d3planner/slots.js:147 (the item's range)",
                         **change})
        return edit

    def test_a_sheet_row_that_says_what_the_metadata_says_is_taken(self):
        with tempfile.TemporaryDirectory() as folder:
            d3 = self.sheets(folder)
            self.rewrite(d3 / "item_preset_ranges.csv", self.cindercoat())
            self.assertIn("dmgfir", [r[1] for r in generator.rows(d3)])

    def test_refuses_a_sheet_row_that_disagrees_with_the_metadata(self):
        for change in ({"affix_name": "Fire Damage"}, {"kind": "secondary"}, {"is_percent": "0"}):
            with self.subTest(change=change):
                self.refuse("item_preset_ranges.csv", self.cindercoat(**change), "is not affix_metadata.csv's")

    def test_refuses_a_stat_with_neither_a_pool_row_nor_metadata(self):
        # Stone of Jordan's Maximum Resource: one range per class in d3planner, so no pool, sheet or metadata row
        # names `resource`.
        self.refuse("item_preset_ranges.csv",
                    lambda rows: rows.append({**rows[0], "d3_id": "P69_Unique_Ring_019", "affix_id": "resource",
                                              "source": "reference/d3planner/data.json (not an own-stat row)"}),
                    "no pool row in any slot and no affix_metadata.csv row")

    def test_refuses_bad_metadata(self):
        self.refuse("affix_metadata.csv", lambda rows: rows.append(dict(rows[0])), "listed twice")
        self.refuse("affix_metadata.csv", lambda rows: rows[0].update(affix_id="resall"), "a pool row holds it")
        self.refuse("affix_metadata.csv", lambda rows: rows[0].update(kind="utility"), "kind must be")
        self.refuse("affix_metadata.csv", lambda rows: rows[0].update(is_percent="2"), "is_percent 0 or 1")
        self.refuse("affix_metadata.csv", lambda rows: rows[0].update(display_order="last"), "display_order a number")
        self.refuse("affix_metadata.csv", lambda rows: rows[0].update(affix_name=" "), "no name")
        self.refuse("affix_metadata.csv", lambda rows: rows[0].update(source=""), "no source")


class Respelling(unittest.TestCase):
    def test_the_set_shoulders_preset_resall_the_pool_rolls(self):
        bases = {r["d3_id"]: r for r in read(D3 / "base_items.csv")}
        self.assertEqual([d for d, r in bases.items() if "allres" in r["preset_affixes"].split(";")], [])
        pool = {(r["slot"], r["affix_id"]) for r in read(D3 / "affix_pools.csv")}
        for d3_id in SHOULDERS:
            self.assertEqual(bases[d3_id]["preset_affixes"], "mainstat;resall")
            self.assertIn(("shoulders", "resall"), pool)

    def test_a_new_unapplied_migration_carries_it(self):
        self.assertEqual(gensql.BASE_PRESET_MIGRATION, "items_0030_base_item_presets.sql")
        applied = (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertNotIn(gensql.BASE_PRESET_MIGRATION, applied)
        base_sql, _, _ = gensql.render_base_items(D3 / "base_items.csv")
        with tempfile.TemporaryDirectory() as folder:
            target = gensql.emit_base_item_preset_delta(MODULE, base_sql, Path(folder))
            self.assertEqual(target.read_text(encoding="utf-8"),
                             (UPDATES / gensql.BASE_PRESET_MIGRATION).read_text(encoding="utf-8"))
        committed = (UPDATES / gensql.BASE_PRESET_MIGRATION).read_text(encoding="utf-8")
        ids = {r["d3_id"]: r["item_entry"] for r in read(D3 / "base_item_ids.csv")}
        for d3_id in SHOULDERS:
            self.assertIn(f"SET `preset_affixes`='mainstat;resall' WHERE `entry`={ids[d3_id]};", committed)


if __name__ == "__main__":
    unittest.main()

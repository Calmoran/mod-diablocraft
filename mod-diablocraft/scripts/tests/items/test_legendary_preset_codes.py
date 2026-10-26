#!/usr/bin/env python3
"""Every preset code a pool-rolled legendary or set item carries is one Torment knows.

A code is known when the item's slot pool has a row for it (affix_pools.csv), the item has its own range for it
(item_preset_ranges.csv), or affix_metadata.csv names it. A code none of the three knows is never rolled, and the
tooltip prints the bare code (Tal Rasha's Relentless Pursuit read '+% ias'). The codes below are served by other
parts of the roller and are left out: `custom` (the legendary power), `mainstat` and `elemental` (pool groups the
roller resolves), `sockets`, `damage` (the weapon's own damage), `dura`, `extra_passive`, and every `skill_*` code
(dc_skill_affix serves it through the slot's skill group). `resource` is known when the item has its own Maximum
<resource> rows, one per class (diablocraft-4ruv4; test_resource_affix.py checks each class takes its own).

The check runs on the committed sheets, and again on copies with one row taken out, so the check itself is shown to
catch a missing row.
"""
from __future__ import annotations

import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
D3 = HERE.parent / "data/d3"
SHEETS = ("base_items.csv", "affix_pools.csv", "item_preset_ranges.csv", "affix_metadata.csv", "class_resources.csv")
HANDLED = {"custom", "mainstat", "sockets", "damage", "dura", "extra_passive", "elemental"}
# `resource` is D3's "Maximum <the wearer's resource>": the item's rows named "Maximum <a class resource>"
# (item_preset_ranges.csv, one per class) serve it, as dc_resource_affix_rule.h reads them.
RESOURCE = "resource"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def unknown(d3: Path = D3) -> list[tuple[str, str]]:
    """(d3_id, code) of every pool-rolled legendary or set preset code no pool, sheet or metadata row knows."""
    pool = {(r["slot"], r["affix_id"]) for r in read(d3 / "affix_pools.csv")}
    ranges = {(r["d3_id"], r["affix_id"]) for r in read(d3 / "item_preset_ranges.csv")}
    named = {r["affix_id"] for r in read(d3 / "affix_metadata.csv")}
    maximums = {f"Maximum {r['d3_name']}" for r in read(d3 / "class_resources.csv")}
    resource = {r["d3_id"] for r in read(d3 / "item_preset_ranges.csv") if r["affix_name"] in maximums}
    out = []
    for base in read(d3 / "base_items.csv"):
        if base["rarity"] not in ("legendary", "set") or base["pool_version"] != "yes":
            continue
        for code in filter(None, (c.strip() for c in base["preset_affixes"].split(";"))):
            if code in HANDLED or code.startswith("skill_"):
                continue
            if (base["slot"], code) in pool or (base["d3_id"], code) in ranges or code in named:
                continue
            if code == RESOURCE and base["d3_id"] in resource:
                continue
            out.append((base["d3_id"], code))
    return out


class PresetCodes(unittest.TestCase):
    def test_every_code_is_known(self):
        self.assertEqual(sorted(unknown()), [],
                         "a legendary or set preset code has no pool row for its slot, no item_preset_ranges.csv "
                         "row and no affix_metadata.csv name")

    def without(self, **drops) -> list[tuple[str, str]]:
        """unknown() over copies of the sheets, each sheet named in `drops` with the rows its test picks taken out."""
        with tempfile.TemporaryDirectory() as folder:
            d3 = Path(folder)
            for name in SHEETS:
                shutil.copy(D3 / name, d3 / name)
            for sheet, drop in drops.items():
                rows = read(d3 / f"{sheet}.csv")
                kept = [r for r in rows if not drop(r)]
                self.assertLess(len(kept), len(rows), f"nothing to drop from {sheet}.csv")
                with (d3 / f"{sheet}.csv").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(kept)
            return unknown(d3)

    def test_a_missing_range_row_and_name_are_caught(self):
        # Split Tusk's Maximum Mana: no head pool row; its sheet rows and its metadata name each know it.
        line = ("Unique_VoodooMask_006_x1", "maxmana")
        sheet = lambda r: (r["d3_id"], r["affix_id"]) == line
        name = lambda r: r["affix_id"] == "maxmana"
        self.assertNotIn(line, self.without(item_preset_ranges=sheet))
        self.assertNotIn(line, self.without(affix_metadata=name))
        self.assertIn(line, self.without(item_preset_ranges=sheet, affix_metadata=name))

    def test_a_pooled_code_is_caught_without_its_range_row(self):
        # Jesseth Skullshield's Cooldown Reduction: the shoulders pool rolls cdr, the offhand pool does not, so the
        # item's own sheet row is all that knows it.
        got = self.without(item_preset_ranges=lambda r: (r["d3_id"], r["affix_id"]) == ("P6_Unique_Shield_01", "cdr"))
        self.assertIn(("P6_Unique_Shield_01", "cdr"), got)

    def test_a_resource_preset_without_its_class_rows_is_caught(self):
        # Stone of Jordan's `resource`: only its Maximum <resource> rows know it.
        got = self.without(item_preset_ranges=lambda r: r["d3_id"] == "P69_Unique_Ring_019"
                           and r["affix_name"].startswith("Maximum "))
        self.assertIn(("P69_Unique_Ring_019", RESOURCE), got)
        self.assertNotIn(("Unique_Shield_008_x1", RESOURCE), got)

    def test_a_missing_metadata_name_is_caught(self):
        # Holy Beacon's Holy Damage: the neck pool rolls `elemental`, never `dmghol`, so the item's own sheet row
        # (ruling q-1016-14) and the metadata name are what know it; take both away and the line comes back.
        line = ("Unique_Amulet_013_x1", "dmghol")
        sheet = lambda r: (r["d3_id"], r["affix_id"]) == line
        name = lambda r: r["affix_id"] == "dmghol"
        self.assertNotIn(line, self.without(affix_metadata=name))
        self.assertIn(line, self.without(item_preset_ranges=sheet, affix_metadata=name))


if __name__ == "__main__":
    unittest.main()

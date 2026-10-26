#!/usr/bin/env python3
"""Checks for client-extension/wowdecomp/patches/0007-nameplate-class-colours-past-the-druid.patch, three sources
against the table it writes (NamePlateFrame.cpp's s_classColors, read as s_classColors[class id]):

  * client-patch/dbc/ChrClasses.dbc: every class id the client knows (so every id the server can send) has an
    entry, and each class's file token (field 55) names its id;
  * the class colour sheet, mod-diablocraft/data/class_colours.csv (diablocraft-wc9v3): a class it lists takes its
    hex. The sheet is not on nightly yet; until it is, the copy below (w/diablocraft-wc9v3 c1a1f318) stands in,
    and once it is the file is read and must agree with the copy;
  * the stock table, the patch's own removed lines: every other class keeps its stock bytes.

Also checks the read is held to the table's size, so a class id past it never reads the bytes after it.
Nothing here builds or runs the client; the nameplate colour on screen is the designer's check.

Run: python3 client-extension/tests/test_nameplate_class_colours.py
"""

from __future__ import annotations

import csv
import re
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PATCH = HERE.parent / "wowdecomp" / "patches" / "0007-nameplate-class-colours-past-the-druid.patch"
CHR_CLASSES = REPO / "client-patch" / "dbc" / "ChrClasses.dbc"
SHEET = REPO / "mod-diablocraft" / "data" / "class_colours.csv"

# class_colours.csv at w/diablocraft-wc9v3 c1a1f318, verbatim (token -> hex).
SHEET_COPY = {
    "WARRIOR": "FF3B2F",
    "PALADIN": "FFE135",
    "HUNTER": "B061FF",
    "MONK": "FF7D0A",
    "NECROMANCER": "1FD8C8",
    "WITCHDOCTOR": "4CDB3E",
    "MAGE": "3D8DFF",
    "SHAMAN": "0070DE",
}

# The Necromancer's class id (diablocraft-im7mr.1's contract); its ChrClasses row lands with 1a-1d, not on this base.
NECROMANCER_ID = 13
CHR_CLASSES_TOKEN_FIELD = 55

ROW = re.compile(r"CImVector\(0x([0-9A-F]{2}), 0x([0-9A-F]{2}), 0x([0-9A-F]{2}), 0x([0-9A-F]{2})\)")


def table(sign: str) -> list[tuple[int, int, int, int]]:
    """s_classColors as the patch leaves it ('+') or as stock had it ('-'), rows as (b, g, r, a)."""
    lines = PATCH.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l[:1] in (sign, " ") and "s_classColors[" in l and "= {" in l)
    rows = []
    for line in lines[start + 1:]:
        if line[1:].startswith("};"):
            break
        if line[:1] in (sign, " "):
            match = ROW.search(line)
            if match:
                rows.append(tuple(int(x, 16) for x in match.groups()))
    return rows


def declared_size() -> int:
    match = re.search(r"^\+static CImVector s_classColors\[(\d+)\] = \{", PATCH.read_text(), re.M)
    assert match, "the patch declares no s_classColors size"
    return int(match.group(1))


def class_tokens() -> dict[str, int]:
    """ChrClasses.dbc: file token -> class id."""
    data = CHR_CLASSES.read_bytes()
    magic, count, fields, size, _ = struct.unpack("<4s4I", data[:20])
    assert magic == b"WDBC"
    strings = data[20 + count * size:]
    out = {}
    for i in range(count):
        record = data[20 + i * size:20 + (i + 1) * size]
        class_id = struct.unpack_from("<I", record, 0)[0]
        offset = struct.unpack_from("<I", record, CHR_CLASSES_TOKEN_FIELD * 4)[0]
        out[strings[offset:strings.index(b"\0", offset)].decode()] = class_id
    return out


def sheet() -> dict[str, str]:
    if not SHEET.exists():
        return SHEET_COPY
    with SHEET.open(newline="") as f:
        return {row["token"]: row["hex"].upper() for row in csv.DictReader(f)}


def bgra(hex_rgb: str) -> tuple[int, int, int, int]:
    r, g, b = (int(hex_rgb[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r, 0xFF)


class NamePlateClassColours(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.new = table("+")
        cls.stock = table("-")
        cls.ids = class_tokens()
        cls.ids.setdefault("NECROMANCER", NECROMANCER_ID)

    def test_the_stock_table_was_twelve(self):
        self.assertEqual(len(self.stock), 12)

    def test_declared_size_is_the_rows(self):
        self.assertEqual(declared_size(), len(self.new))

    def test_every_class_id_has_an_entry(self):
        for token, class_id in self.ids.items():
            self.assertLess(class_id, len(self.new), f"{token} ({class_id}) has no s_classColors entry")

    def test_sheet_copy_agrees_with_the_sheet(self):
        if SHEET.exists():
            self.assertEqual(sheet(), SHEET_COPY, "class_colours.csv changed: update SHEET_COPY and the patch")

    def test_sheet_classes_take_the_sheet_hex(self):
        colours = sheet()
        for token, hex_rgb in colours.items():
            if token not in self.ids:
                continue  # a class the client's ChrClasses.dbc does not hold has no entry to colour
            self.assertEqual(self.new[self.ids[token]], bgra(hex_rgb), f"{token} ({self.ids[token]})")

    def test_other_classes_keep_stock_bytes(self):
        sheet_ids = {self.ids[t] for t in sheet() if t in self.ids}
        for class_id, stock in enumerate(self.stock):
            if class_id not in sheet_ids:
                self.assertEqual(self.new[class_id], stock, f"class id {class_id} changed but is not on the sheet")

    def test_monk_necromancer_and_witch_doctor_are_named(self):
        self.assertEqual(self.ids["MONK"], 12)
        self.assertEqual(self.new[12], bgra("FF7D0A"))
        self.assertEqual(self.new[13], bgra("1FD8C8"))
        self.assertEqual(self.ids["WITCHDOCTOR"], 14)
        self.assertEqual(self.new[14], bgra("4CDB3E"))

    def test_the_read_is_held_to_the_table(self):
        text = PATCH.read_text()
        guard = text.index("+        && unit->m_unit->m_unitFieldBytes0[1] < sizeof(s_classColors) / sizeof(s_classColors[0])) {")
        read = text.index("         this->m_healthBarColor = s_classColors[unit->m_unit->m_unitFieldBytes0[1]];")
        self.assertLess(guard, read)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)

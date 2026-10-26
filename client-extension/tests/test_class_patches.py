#!/usr/bin/env python3
"""Checks for client-extension/torment/ClassPatches.hpp (Monk 1c, diablocraft-3oetm), three sources against it:

  * tswow's class patches, copied below as literals from reference/tswow 00608832
    tswow-scripts/util/ClientPatches.ts:48-73 (FILE offsets): every site is that offset + 0x400C00 and writes
    exactly tswow's bytes, and no site of tswow's three sets is missing (the PE-header bit at 0x126 excepted);
  * wxl-core's own glue-unlock script, client-extension/wxl-core/src/patcher/GlueUnlock.cpp (VAs): the glue
    sites are exactly its edits, which is what fixes the 0x400C00 shift on Wow.exe's code section;
  * the core's Warden memory checks, azerothcore-wotlk/data/sql/base/db_world/warden_checks.sql: no Wow.exe
    MEM_CHECK reads a byte the module writes.

Nothing here runs the module or reads a Wow.exe; the run-time write is the designer's check on his PC.

Run: python3 client-extension/tests/test_class_patches.py
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HEADER = HERE.parent / "torment" / "ClassPatches.hpp"
WXL_GLUE = HERE.parent / "wxl-core" / "src" / "patcher" / "GlueUnlock.cpp"
WARDEN = REPO / "azerothcore-wotlk" / "data" / "sql" / "base" / "db_world" / "warden_checks.sql"

TEXT_FILE_TO_VA = 0x400C00

# ClientPatches.ts:48-73 at tswow 00608832, file offsets, verbatim.
TSWOW_GLUE = [
    (0x1F41BF, [0xEB]),
    (0x415A25, [0xEB]),
    (0x415A3F, [0x03]),
    (0x415A95, [0x03]),
    (0x415B46, [0xEB]),
    (0x415B5F, [0xB8, 0x03]),
    (0x415B61, [0x00, 0x00, 0x00, 0xEB, 0xED]),
]  # and (0x126, [0x23]): the large-address-aware bit in the PE header, left out (ClassPatches.hpp says why)
TSWOW_RACE_CLASS = [(0xE0355, [0x78]), (0xE038E, [0x88]), (0xE03A3, [0x88]), (0xE03C3, [0x88])]
TSWOW_ROLE_XREFS = [0x151D48, 0x152F7D, 0x152F94, 0x1531E7, 0x153D22]
TSWOW_ROLE_TABLE_BYTES = 1 + 32  # [0, ...rolemask], rolemask = new Array(32)

MEM_CHECK = 243  # Warden.h WardenCheckType


def header() -> str:
    return HEADER.read_text()


def edits(name: str) -> list[tuple[int, bytes]]:
    """The { va, len, { bytes } } rows of the named array in ClassPatches.hpp."""
    body = re.search(rf"\b{name}\[\]\s*=\s*\{{(.*?)\n\s*\}};", header(), re.S)
    assert body, f"{name} not found in {HEADER}"
    out = []
    for va, n, raw in re.findall(r"\{\s*(0x[0-9A-Fa-f]+),\s*(\d+),\s*\{([^}]*)\}\s*\}", body.group(1)):
        data = bytes(int(b, 16) for b in raw.split(","))
        assert len(data) == int(n), f"{name} {va}: len {n} but {len(data)} bytes"
        out.append((int(va, 16), data))
    return out


def addresses(name: str) -> list[int]:
    body = re.search(rf"\b{name}\[\]\s*=\s*\{{(.*?)\}};", header(), re.S)
    assert body, f"{name} not found in {HEADER}"
    return [int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", re.sub(r"//[^\n]*", "", body.group(1)))]


def constant(name: str) -> int:
    m = re.search(rf"\b{name}\s*=\s*(0x[0-9A-Fa-f]+|\d+)", header())
    assert m, f"{name} not found in {HEADER}"
    return int(m.group(1), 0)


def merged(patches: list[tuple[int, list[int]]]) -> list[tuple[int, bytes]]:
    """tswow splits one write over adjacent entries (0x415B5F + 0x415B61); join runs that touch."""
    out: list[tuple[int, bytearray]] = []
    for off, data in sorted(patches):
        if out and out[-1][0] + len(out[-1][1]) == off:
            out[-1][1].extend(data)
        else:
            out.append((off, bytearray(data)))
    return [(off, bytes(data)) for off, data in out]


def as_va(patches) -> list[tuple[int, bytes]]:
    return [(off + TEXT_FILE_TO_VA, data) for off, data in merged(patches)]


class TswowTests(unittest.TestCase):
    def test_glue_sites_are_tswows(self):
        self.assertEqual(edits("kGlueXml"), as_va(TSWOW_GLUE))

    def test_race_class_sites_are_tswows(self):
        self.assertEqual(edits("kRaceClassPairs"), as_va(TSWOW_RACE_CLASS))

    def test_role_xrefs_are_tswows(self):
        self.assertEqual(addresses("kRoleTableSites"), [x + TEXT_FILE_TO_VA for x in TSWOW_ROLE_XREFS])

    def test_role_table_is_tswows_size_and_keeps_the_stock_classes(self):
        self.assertEqual(constant("kRoleEntries"), TSWOW_ROLE_TABLE_BYTES)
        # Stock 3.3.5's classes are ids 1..11 (Druid 11); the table is indexed by class id, so 0..11 are copied.
        self.assertEqual(constant("kStockRoleEntries"), 12)

    def test_the_shift_is_the_one_constant(self):
        self.assertEqual(constant("kTextFileToVa"), TEXT_FILE_TO_VA)


class WxlTests(unittest.TestCase):
    def test_glue_sites_are_wxls(self):
        src = WXL_GLUE.read_text()
        wxl = [
            (int(va, 16), bytes(int(b, 16) for b in raw.split(",")))
            for va, raw, _ in re.findall(r"\{\s*(0x[0-9A-Fa-f]+),\s*\{([^}]*)\},\s*(\d+)\s*\}", src)
        ]
        self.assertEqual(len(wxl), 6)
        self.assertEqual(edits("kGlueXml"), wxl)


class WardenTests(unittest.TestCase):
    def test_no_wow_exe_memory_check_reads_a_written_byte(self):
        rows = re.findall(
            r"\((\d+),(\d+),'[^']*','([^']*)',(\d+),(\d+),'[^']*',(?:NULL|'[^']*')\)", WARDEN.read_text()
        )
        checks = [(int(a), int(n)) for _, t, module, a, n in rows if int(t) == MEM_CHECK and module == ""]
        self.assertEqual(len(checks), 34, "the base data's Wow.exe memory checks changed: re-read them")
        written = [(va, len(d)) for va, d in edits("kGlueXml") + edits("kRaceClassPairs")]
        written += [(va, 4) for va in addresses("kRoleTableSites")]
        for va, n in written:
            for a, m in checks:
                self.assertFalse(a < va + n and va < a + m, f"Warden MEM_CHECK {a:#x}+{m} reads {va:#x}+{n}")


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)

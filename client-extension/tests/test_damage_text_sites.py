#!/usr/bin/env python3
"""Checks for client-extension/torment/DamageTextSites.hpp (docs/contracts/damage-text.md), two sources against it:

  * reference/wowdecomp (SatyPardus/wowdecomp 5d0aafad, read only, never copied): every function address is
    the OFFSET tag on that function, every global the STATIC tag on that global, every field offset the
    offset the struct names, the text drop the one CreateWorldText applies, and CreateWorldText has exactly
    one caller, PlayerNameCreateText, so a hit is queued only past its checks;
  * the core's Warden memory checks, azerothcore-wotlk/data/sql/base/db_world/warden_checks.sql: no Wow.exe
    MEM_CHECK reads the start of a function the module detours.

reference/ is gitignored and lives in the main checkout; WOWDECOMP names another copy. Nothing here runs the
module or reads a Wow.exe; the calling conventions were read off the stock exe once and are written in the
header, and the run in the client is the designer's check on his PC.

Run: python3 client-extension/tests/test_damage_text_sites.py
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HEADER = HERE.parent / "torment" / "DamageTextSites.hpp"
WARDEN = REPO / "azerothcore-wotlk" / "data" / "sql" / "base" / "db_world" / "warden_checks.sql"


def find_decomp() -> Path:
    for candidate in (os.environ.get("WOWDECOMP"), REPO / "reference" / "wowdecomp",
                      Path.home() / "diablocraft" / "reference" / "wowdecomp"):
        if candidate and (Path(candidate) / "WoW" / "Source").is_dir():
            return Path(candidate) / "WoW" / "Source"
    raise SystemExit("reference/wowdecomp not found: set WOWDECOMP to its folder")


SOURCE = find_decomp()
MEM_CHECK = 243  # Warden.h WardenCheckType
# A detour writes a 5-byte jump at the function's start; any Warden read within this many bytes is refused.
DETOUR_BYTES = 16

FUNCTIONS = {
    "kAddWorldDamageText": ("Object/ObjectClient/Unit_C.cpp", "CGUnit_C::AddWorldDamageText("),
    "kAddWorldText": ("Object/ObjectClient/Unit_C.cpp", "CGUnit_C::AddWorldText("),
    "kAddWorldHealingText": ("Object/ObjectClient/Unit_C.cpp", "CGUnit_C::AddWorldHealingText("),
    "kCreateWorldText": ("Game/GameClient/PlayerName.cpp", "PLAYERNAMEDESC::CreateWorldText("),
    "kGetScreenCoordinates": ("Ui/WorldFrame.cpp", "CGWorldFrame::GetScreenCoordinates("),
}
GLOBALS = {
    "kCurrentWorldFrame": ("Ui/WorldFrame.cpp", "CGWorldFrame::s_currentWorldFrame;"),
    "kDdcWidthScale": ("../../Engine/Source/Base/Coordinate.cpp", "static float s_ddcWidthScale ="),
    "kAspectCompensation": ("../../Engine/Source/Base/Coordinate.cpp", "static float s_aspectCompensation ="),
}
FIELDS = {
    "kSpellSchoolMask": ("DB/Rec/SpellRec.h", "m_schoolMask;"),
    "kWorldFrameCamera": ("Ui/WorldFrame.h", "CGCamera* m_camera;"),
}
DETOURED = ["kAddWorldDamageText", "kAddWorldText", "kAddWorldHealingText", "kCreateWorldText"]


def header() -> str:
    return HEADER.read_text()


def constant(name: str) -> int:
    m = re.search(rf"\b{name}\s*=\s*(0x[0-9A-Fa-f]+)\s*;", header())
    assert m, f"{name} not found in {HEADER}"
    return int(m.group(1), 16)


def tag_before(path: str, line_text: str, tag: str) -> int:
    """The `// <tag>: 0x...` value in the comment block right above the one line holding line_text."""
    lines = (SOURCE / path).read_text().splitlines()
    found = []
    for n, line in enumerate(lines):
        if line_text not in line or line.lstrip().startswith("//"):
            continue
        i = n - 1
        while i >= 0 and lines[i].lstrip().startswith("//"):
            m = re.match(rf"\s*// {tag}: (0x[0-9A-Fa-f]+)", lines[i])
            if m:
                found.append(int(m.group(1), 16))
                break
            i -= 1
    assert len(found) == 1, f"{line_text!r} in {path}: {len(found)} lines tagged {tag}"
    return found[0]


class DecompTests(unittest.TestCase):
    def test_each_function_is_at_its_offset_tag(self):
        for name, (path, text) in FUNCTIONS.items():
            with self.subTest(name):
                self.assertEqual(constant(name), tag_before(path, text, "OFFSET"))

    def test_each_global_is_at_its_static_tag(self):
        for name, (path, text) in GLOBALS.items():
            with self.subTest(name):
                self.assertEqual(constant(name), tag_before(path, text, "STATIC"))

    def test_each_field_is_at_its_struct_offset(self):
        for name, (path, text) in FIELDS.items():
            with self.subTest(name):
                rows = [l for l in (SOURCE / path).read_text().splitlines() if l.strip().endswith(text)]
                self.assertEqual(len(rows), 1, f"{text!r} in {path}")
                m = re.search(r"/\* ([0-9A-Fa-f]{4}) \*/", rows[0])
                self.assertTrue(m, rows[0])
                self.assertEqual(constant(name), int(m.group(1), 16))

    def test_the_text_drop_is_the_engines(self):
        body = (SOURCE / "Game/GameClient/PlayerName.cpp").read_text()
        create = body[body.index("void PLAYERNAMEDESC::CreateWorldText("):]
        create = create[: create.index("\n}\n")]
        drop = re.findall(r"position\.z = position\.z - ([0-9.]+)f;", create)
        self.assertEqual(drop, [re.search(r"kTextStartDrop = ([0-9.]+)f;", header()).group(1)])

    def test_create_world_text_has_one_caller_past_the_engines_checks(self):
        callers = []
        for path in SOURCE.rglob("*.cpp"):
            for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if "CreateWorldText(" in line and "::CreateWorldText(" not in line and "//" not in line.split("CreateWorldText(")[0]:
                    callers.append((path.relative_to(SOURCE).as_posix(), line.strip()))
        self.assertEqual(callers, [("Game/GameClient/PlayerName.cpp", "desc->CreateWorldText(type, text, color, pvpRank);")])

    def test_the_three_world_text_functions_end_in_create_world_text(self):
        body = (SOURCE / "Object/ObjectClient/Unit_C.cpp").read_text()
        for text in ("void CGUnit_C::AddWorldDamageText(", "void CGUnit_C::AddWorldText(",
                     "void CGUnit_C::AddWorldHealingText("):
            with self.subTest(text):
                fn = body[body.index(text):]
                fn = fn[: fn.index("\n}\n")]
                self.assertEqual(fn.count("PlayerNameCreateText(this->m_nameDesc"), 1)


class WardenTests(unittest.TestCase):
    def test_no_wow_exe_memory_check_reads_a_detoured_function(self):
        rows = re.findall(
            r"\((\d+),(\d+),'[^']*','([^']*)',(\d+),(\d+),'[^']*',(?:NULL|'[^']*')\)", WARDEN.read_text()
        )
        checks = [(int(a), int(n)) for _, t, module, a, n in rows if int(t) == MEM_CHECK and module == ""]
        self.assertEqual(len(checks), 34, "the base data's Wow.exe memory checks changed: re-read them")
        for name in DETOURED:
            va = constant(name)
            for a, m in checks:
                self.assertFalse(a < va + DETOUR_BYTES and va < a + m,
                                 f"Warden MEM_CHECK {a:#x}+{m} reads {name} {va:#x}")


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)

#!/usr/bin/env python3
"""Checks for client-extension/wowdecomp/patches/0010-life-in-64-bits.patch (diablocraft-p22re, K3 of the client 64-bit numbers).

The rebuilt client reads a unit's Life and max Life as two update-field dwords (the server's core patch 0027, wire contract
docs/contracts/life-64bit-wire.md): the stock low dword in place, a new high dword each at the end of the unit block. Four
sources have to agree, and none of them is built here (the build is the client-rebuild workflow):

  * the server's layout, from the contract and core patch 0027 when they are in the tree (they arrive with Part 1,
    diablocraft-sbxl) and from the frozen copy below until then; the copy must equal them once they are;
  * the numbers the patch writes: Unit.h's offsets and size, the descriptor rows, the object manager's block counts and
    byte base for the player's fields, the saved-field list and the handler-list sizes;
  * the C++ of `UnitWideField` and `UnitLifeAsPower`, cut out of the patch and compiled on Linux (g++), fed whole numbers
    through the two dwords, with the reads a site does (`> 0`, float, int64);
  * the patched tree itself (the series applied to reference/wowdecomp in a throwaway index): every registration on a Life
    dword has one on its high dword, and no site stores Life in 32 bits again, which a compile cannot see through an
    explicit cast or a `%d`.

Run: python3 client-extension/tests/test_life_64bit_fields.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PATCHES = HERE.parent / "wowdecomp" / "patches"
PATCH = PATCHES / "0010-life-in-64-bits.patch"
CONTRACT = REPO / "docs" / "contracts" / "life-64bit-wire.md"
CORE_PATCH = REPO / "core-patches" / "0027-life-64bit.patch"

# The server's layout at core patch 0027 (docs/contracts/life-64bit-wire.md, diablocraft-sbxl bcfa7e638), in dwords from the
# start of the object's values; the unit data starts after the 6 object dwords.
OBJECT_END = 6
SERVER = {
    "UNIT_FIELD_HEALTH": OBJECT_END + 0x12,
    "UNIT_FIELD_MAXHEALTH": OBJECT_END + 0x1A,
    "UNIT_FIELD_PADDING": OBJECT_END + 0x8D,
    "UNIT_FIELD_HEALTH_HI": OBJECT_END + 0x8E,
    "UNIT_FIELD_MAXHEALTH_HI": OBJECT_END + 0x8F,
    "UNIT_END": OBJECT_END + 0x90,
}
STOCK_UNIT_END = OBJECT_END + 0x8E  # 148, the stock unit block
STOCK_PLAYER_DWORDS = (324, 1326)  # a remote player's block and the active player's, in dwords from the object's start


def patch_text() -> str:
    return PATCH.read_text()


def added(path: str) -> str:
    """The lines the patch adds to `path` (without the leading plus), in order."""
    text = patch_text()
    start = text.index(f"diff --git a/{path} b/{path}")
    end = text.find("\ndiff --git ", start + 1)
    body = text[start:end if end != -1 else len(text)]
    return "\n".join(line[1:] for line in body.splitlines() if line.startswith("+") and not line.startswith("+++"))


def removed(path: str) -> str:
    text = patch_text()
    start = text.index(f"diff --git a/{path} b/{path}")
    end = text.find("\ndiff --git ", start + 1)
    body = text[start:end if end != -1 else len(text)]
    return "\n".join(line[1:] for line in body.splitlines() if line.startswith("-") and not line.startswith("---"))


class ServerLayout(unittest.TestCase):
    def test_the_frozen_copy_is_the_stock_layout_plus_two_dwords(self):
        self.assertEqual(SERVER["UNIT_FIELD_HEALTH_HI"], STOCK_UNIT_END)
        self.assertEqual(SERVER["UNIT_FIELD_MAXHEALTH_HI"], STOCK_UNIT_END + 1)
        self.assertEqual(SERVER["UNIT_END"], STOCK_UNIT_END + 2)
        self.assertEqual(SERVER["UNIT_FIELD_PADDING"] + 1, STOCK_UNIT_END)

    def test_the_contract_agrees_with_the_copy(self):
        if not CONTRACT.exists():
            self.skipTest("docs/contracts/life-64bit-wire.md is not in this tree yet (diablocraft-sbxl)")
        text = CONTRACT.read_text()
        for name in ("UNIT_FIELD_HEALTH", "UNIT_FIELD_MAXHEALTH", "UNIT_FIELD_HEALTH_HI", "UNIT_FIELD_MAXHEALTH_HI"):
            match = re.search(rf"`{name}`(?: \(new\))? \| `[^`]*` = (\d+)", text)
            self.assertIsNotNone(match, f"the contract has no row for {name}")
            self.assertEqual(int(match.group(1)), SERVER[name], name)
        self.assertRegex(text, rf"`UNIT_END` was {STOCK_UNIT_END} and is \*\*{SERVER['UNIT_END']}\*\*")

    def test_core_patch_0027_agrees_with_the_copy(self):
        if not CORE_PATCH.exists():
            self.skipTest("core-patches/0027-life-64bit.patch is not in this tree yet (diablocraft-sbxl)")
        text = CORE_PATCH.read_text()
        for name in ("UNIT_FIELD_HEALTH_HI", "UNIT_FIELD_MAXHEALTH_HI", "UNIT_END"):
            match = re.search(rf"^\+\s+{name}\s+= OBJECT_END \+ (0x[0-9A-Fa-f]+),", text, re.M)
            self.assertIsNotNone(match, f"core patch 0027 does not define {name}")
            self.assertEqual(OBJECT_END + int(match.group(1), 16), SERVER[name], name)


class PatchNumbers(unittest.TestCase):
    def test_unit_data_layout(self):
        unit_h = added("WoW/Source/Object/Unit.h")
        high = SERVER["UNIT_FIELD_HEALTH_HI"] - OBJECT_END  # dwords into the unit data
        self.assertIn(f"/* {high * 4:04X} */ uint32_t m_unitFieldHealthHigh;", unit_h)
        self.assertIn(f"/* {(high + 1) * 4:04X} */ uint32_t m_unitFieldMaxhealthHigh;", unit_h)
        self.assertIn(f"offsetof(CGUnitData, m_unitFieldHealthHigh) == 0x{high * 4:X}", unit_h)
        self.assertIn(f"offsetof(CGUnitData, m_unitFieldMaxhealthHigh) == 0x{(high + 1) * 4:X}", unit_h)
        unit_dwords = SERVER["UNIT_END"] - OBJECT_END
        self.assertIn(f"sizeof(CGUnitData) == 0x{unit_dwords * 4:X}", unit_h)
        # The members that read the whole value sit on the stock offsets and find the high dword at the distance given.
        low_health, low_max = (SERVER["UNIT_FIELD_HEALTH"] - OBJECT_END) * 4, (SERVER["UNIT_FIELD_MAXHEALTH"] - OBJECT_END) * 4
        self.assertIn(f"UnitWideField<int64_t, 0x{low_health:X}, 0x{high * 4:X}> m_unitFieldHealth;", unit_h)
        self.assertIn(f"UnitWideField<uint64_t, 0x{low_max:X}, 0x{(high + 1) * 4:X}> m_unitFieldMaxhealth;", unit_h)

    def test_descriptor_rows(self):
        rows = added("WoW/Source/ObjectMgrClient/Mirror.cpp")
        self.assertIn("UNIT_DESCRIPTORS[91]", rows)
        self.assertIn(f'{{ "UNIT_FIELD_HEALTH_HI", {SERVER["UNIT_FIELD_HEALTH_HI"] - OBJECT_END}, 1, 1, 0x1 }}', rows)
        self.assertIn(f'{{ "UNIT_FIELD_MAXHEALTH_HI", {SERVER["UNIT_FIELD_MAXHEALTH_HI"] - OBJECT_END}, 1, 1, 0x1 }}', rows)
        self.assertIn("UNIT_DESCRIPTORS[91]", added("WoW/Source/ObjectMgrClient/Mirror.h"))

    def test_object_manager_block_counts(self):
        text = added("WoW/Source/ObjectMgrClient/ObjectMgrClient.cpp")
        unit_end = SERVER["UNIT_END"]
        self.assertIn(f"{{ 0x6, 0x40, 0x8A, 0x{unit_end:X}, 0x{STOCK_PLAYER_DWORDS[1] + 2:X}, 0x12, 0xC, 0x24 }}", text)
        self.assertRegex(text, rf"return {unit_end};")
        self.assertIn(f"{STOCK_PLAYER_DWORDS[1] + 2} : {STOCK_PLAYER_DWORDS[0] + 2}", text)
        # The player's fields start at byte 4 * UNIT_END: both the type's byte offset and the mapping's base.
        base = f"0x{unit_end * 4:X}"
        self.assertEqual(len(re.findall(rf"return {base};", text)), 1)
        self.assertIn(f"offset >= {base}", text)
        self.assertIn(f"DescriptorToMirrorOffset(offset, size, local, {base})", text)
        old = f"0x{STOCK_UNIT_END * 4:X}"
        self.assertEqual(len(re.findall(rf"{old}\b", removed("WoW/Source/ObjectMgrClient/ObjectMgrClient.cpp"))), 3)
        self.assertNotIn(old, text)

    def test_handler_lists_and_saved_fields(self):
        units = SERVER["UNIT_END"] - OBJECT_END
        self.assertIn(f"m_unitMirrorLists [{units}]", added("WoW/Source/Object/ObjectClient/Unit_C.h"))
        self.assertIn(f"m_unitMirrorLists, {units});", added("WoW/Source/ObjectMgrClient/ObjectMgrClient.cpp"))
        unit_cpp = added("WoW/Source/Object/Unit.cpp")
        # 123 saved fields (the last one is the spare slot of field 142, the Life high dword) and field 143 after it.
        self.assertIn("s_mirrorFieldIndices[124]", unit_cpp)
        self.assertIn(f"0x{SERVER['UNIT_FIELD_MAXHEALTH_HI'] - OBJECT_END:X},", unit_cpp)
        self.assertIn("CGObject::TotalFieldsSaved() + 124", unit_cpp)
        self.assertIn("s_mirrorFieldIndices[124]", added("WoW/Source/Object/Unit.h"))


WIDE_FIELD_HARNESS = r"""
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cmath>

%(code)s

// CGUnitData's relevant layout: Life at 0x48, max Life at 0x68, the high dwords at 0x238 and 0x23C.
struct Data {
    uint8_t before[0x48];
    UnitWideField<int64_t, 0x48, 0x238> health;
    uint8_t between[0x68 - 0x4C];
    UnitWideField<uint64_t, 0x68, 0x23C> maxhealth;
    uint8_t rest[0x238 - 0x6C];
    uint32_t healthHigh;
    uint32_t maxhealthHigh;
};
static_assert(offsetof(Data, health) == 0x48 && offsetof(Data, maxhealth) == 0x68, "layout");
static_assert(offsetof(Data, healthHigh) == 0x238 && offsetof(Data, maxhealthHigh) == 0x23C && sizeof(Data) == 0x240, "layout");

int main() {
    // Each line of stdin: low high, as hex; prints the member reads a site does.
    unsigned low, high;

    while (std::scanf("%%x %%x", &low, &high) == 2) {
        Data data;
        std::memset(static_cast<void*>(&data), 0, sizeof(data));
        std::memcpy(reinterpret_cast<uint8_t*>(static_cast<void*>(&data)) + 0x48, &low, 4);
        std::memcpy(reinterpret_cast<uint8_t*>(static_cast<void*>(&data)) + 0x238, &high, 4);
        std::memcpy(reinterpret_cast<uint8_t*>(static_cast<void*>(&data)) + 0x68, &low, 4);
        std::memcpy(reinterpret_cast<uint8_t*>(static_cast<void*>(&data)) + 0x23C, &high, 4);
        const Data& d = data;
        int64_t life = d.health;
        uint64_t max = d.maxhealth;
        std::printf("%%lld %%llu %%d %%d %%.0f %%u %%d\n", static_cast<long long>(life), static_cast<unsigned long long>(max),
                    d.health > 0 ? 1 : 0, d.health <= 0 ? 1 : 0, static_cast<double>(static_cast<float>(d.maxhealth)),
                    static_cast<unsigned>(d.health.GetLow()), UnitLifeAsPower(d.health));
    }

    return 0;
}
"""


def cut_code() -> str:
    unit_h = added("WoW/Source/Object/Unit.h")
    start = unit_h.index("template <typename T, size_t LowOffset, size_t HighOffset>")
    end = unit_h.index("};", start) + 2
    power = unit_h.index("inline int32_t UnitLifeAsPower(int64_t life) {")
    power_end = unit_h.index("\n}\n", power) + 3
    return unit_h[start:end] + "\n\n" + unit_h[power:power_end]


def build_and_run(code: str, rows: list[tuple[int, int]]) -> list[list[str]]:
    gxx = shutil.which("g++")
    if not gxx:
        raise unittest.SkipTest("no g++")
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "wide.cpp"
        source.write_text(WIDE_FIELD_HARNESS % {"code": code})
        exe = Path(folder) / "wide"
        built = subprocess.run([gxx, "-std=c++17", "-O1", "-Wall", "-Werror", "-fsanitize=address,undefined", str(source), "-o", str(exe)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            raise AssertionError(f"the cut-out code does not compile:\n{built.stderr}")
        run = subprocess.run([str(exe)], input="".join(f"{low:x} {high:x}\n" for low, high in rows), capture_output=True, text=True)
        if run.returncode != 0:
            raise AssertionError(f"the harness failed:\n{run.stderr}")
        return [line.split() for line in run.stdout.splitlines()]


# (low dword, high dword) -> the Life the two dwords hold.
CASES = [
    (0, 0), (1, 0), (0x7FFFFFFF, 0), (0x80000000, 0), (0xFFFFFFFF, 0),
    (0, 1),                      # 4,294,967,296: the low dword is 0, and a unit holding this is alive
    (0xFFFFFFFF, 1),             # 8,589,934,591
    (0x540BE400, 0xB),           # 50,000,000,000
    (0xA7640000, 0x918),         # 10,000,000,000,000
    (0xFFFFFFFB, 0xFFFFFFFF),    # -5 as a signed 64-bit Life
]


class WideField(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = build_and_run(cut_code(), CASES)

    def test_each_read_is_the_whole_number(self):
        for (low, high), row in zip(CASES, self.rows):
            life = (high << 32) | low
            signed = life - (1 << 64) if life >= 1 << 63 else life
            with self.subTest(low=hex(low), high=hex(high)):
                self.assertEqual(int(row[0]), signed)
                self.assertEqual(int(row[1]), life)
                self.assertEqual(int(row[2]), 1 if signed > 0 else 0)  # `Life > 0`, the "alive" test of 90 lines
                self.assertEqual(int(row[3]), 1 if signed <= 0 else 0)
                self.assertEqual(int(row[5]), low)
                saturated = max(-(1 << 31), min((1 << 31) - 1, signed))
                self.assertEqual(int(row[6]), saturated)

    def test_the_view_cannot_be_copied_or_passed_through_varargs(self):
        # A copy of the low dword alone would read its high dword from beyond itself, and a %d argument is a copy.
        gxx = shutil.which("g++")
        if not gxx:
            self.skipTest("no g++")
        for name, body in (("copy", "auto copy = d.health; (void)copy;"), ("varargs", 'std::printf("%d", d.health);')):
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "wide.cpp"
                source.write_text(WIDE_FIELD_HARNESS.replace("int main() {", "int main() {\n    Data data{};\n    const Data& d = data;\n    " + body.replace("%", "%%") + "\n    return 0;\n}\nint unused_main() {") % {"code": cut_code()})
                built = subprocess.run([gxx, "-std=c++17", "-fsyntax-only", str(source)], capture_output=True, text=True)
                self.assertNotEqual(built.returncode, 0, f"a {name} of the view compiled")

    def test_a_unit_at_exactly_two_to_the_32_is_alive(self):
        # The whole point of the high dword being read: the low dword alone says 0, which the stock client takes for dead.
        index = CASES.index((0, 1))
        self.assertEqual(int(self.rows[index][2]), 1)
        self.assertEqual(int(self.rows[index][5]), 0)

    def test_broken_copies_are_caught(self):
        code = cut_code()
        mutants = {
            "the high dword is ignored": code.replace("(static_cast<uint64_t>(high) << 32) | m_low", "m_low"),
            "the high dword is read from the low dword's neighbour": code.replace("- LowOffset + HighOffset", "+ 4"),
            "Life is read unsigned": code.replace("static_cast<T>((static_cast<uint64_t>(high) << 32) | m_low)",
                                                  "static_cast<T>(static_cast<uint64_t>(high) << 32 | m_low) & 0x7FFFFFFFFFFFFFFFLL"),
            "the power saturation is dropped": code.replace("return life > INT32_MAX", "return static_cast<int32_t>(life); return life > INT32_MAX"),
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(mutant, code, "the text to break is not in the patch")
                try:
                    rows = build_and_run(mutant, CASES)
                except AssertionError:
                    continue  # does not compile: noticed
                self.assertNotEqual(rows, self.rows, f"{name} was not noticed")


def reference_checkout() -> Path | None:
    for root in (REPO, Path.home() / "diablocraft"):
        candidate = root / "reference" / "wowdecomp"
        if (candidate / ".git").exists():
            return candidate
    return None


class PatchedTree(unittest.TestCase):
    """The series applied at the pin in a throwaway index, searched with git grep --cached."""

    @classmethod
    def setUpClass(cls):
        cls.reference = reference_checkout()
        if cls.reference is None:
            raise unittest.SkipTest("reference/wowdecomp is not checked out")
        pin = re.search(r"WOWDECOMP_COMMIT:\s*([0-9a-f]{40})", (REPO / ".github/workflows/client-rebuild.yml").read_text()).group(1)
        cls.scratch = tempfile.mkdtemp()
        cls.index = os.path.join(cls.scratch, "index")
        env = dict(os.environ, GIT_INDEX_FILE=cls.index)
        for argv in (["read-tree", pin],) + tuple(["apply", "--cached", str(p)] for p in sorted(PATCHES.glob("*.patch"))):
            done = subprocess.run(["git", "-C", str(cls.reference), *argv], env=env, capture_output=True, text=True)
            if done.returncode != 0:
                raise AssertionError(f"git {' '.join(argv)}: {done.stderr}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def grep(self, pattern: str) -> list[str]:
        env = dict(os.environ, GIT_INDEX_FILE=self.index)
        done = subprocess.run(["git", "-C", str(self.reference), "grep", "--cached", "-n", "-E", pattern, "--", "WoW", "Engine"],
                              env=env, capture_output=True, text=True)
        return [line for line in done.stdout.splitlines() if line]

    def test_every_registration_on_a_low_dword_has_one_on_its_high_dword(self):
        for low, high in (("m_unitFieldHealth", "m_unitFieldHealthHigh"), ("m_unitFieldMaxhealth", "m_unitFieldMaxhealthHigh")):
            for verb in ("ClntObjMgrSetObjMirrorHandler", "ClntObjMgrUnsetObjMirrorHandler",
                         "ClntObjMgrSetTypeMirrorHandler", "ClntObjMgrUnsetTypeMirrorHandler"):
                with self.subTest(low=low, verb=verb):
                    lows = self.grep(rf"{verb}\(.*offsetof\(CGUnitData, {low}\)")
                    highs = self.grep(rf"{verb}\(.*offsetof\(CGUnitData, {high}\)")
                    self.assertEqual(len(lows), len(highs), f"{lows}\n{highs}")

    def test_a_low_dword_registration_covers_four_bytes(self):
        for line in self.grep(r"offsetof\(CGUnitData, m_unitField(Max)?health(High)?\), sizeof\("):
            self.assertIn("sizeof(uint32_t)", line, line)

    def test_no_site_stores_life_in_32_bits(self):
        # What the compiler cannot see: a cast to 32 bits, a 32-bit local or parameter, a varargs argument.
        for line in self.grep(r"m_unitField(Health|Maxhealth)\b"):
            code = line.split(":", 2)[2]
            if "offsetof(" in code or "UnitLifeAsPower(" in code or "GetLow()" in code:
                continue
            if re.search(r"state->m_(health|maxHealth) = static_cast<uint32_t>\(", code):
                continue  # the party member and pet states stay 32 bits (the wire's SMSG_PARTY_MEMBER_STATS does), said in a comment
            with self.subTest(line=line):
                self.assertNotRegex(code, r"static_cast<(u?int(8|16|32)_t|int|unsigned)>\([^;]*m_unitField(Health|Maxhealth)\b")
                # A 32-bit variable initialised from Life (a comparison or && on the right is a bool, not Life).
                assignment = re.search(r"\b(u?int(8|16|32)_t|int|unsigned)\s+\w+\s*=\s*([^;]*m_unitField(Health|Maxhealth)\b[^;]*)", code)
                if assignment:
                    self.assertRegex(assignment.group(3), r"&&|\|\||[<>]=?|==|!=", "a 32-bit variable takes Life")
                self.assertNotRegex(code, r"(Printf|printf|Log)\(.*m_unitField(Health|Maxhealth)\b")


if __name__ == "__main__":
    sys.exit(unittest.main())

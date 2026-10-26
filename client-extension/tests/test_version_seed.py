#!/usr/bin/env python3
"""version_seed.py: the authserver seed from a client exe, on synthetic PE images (no Blizzard binary).

Each test changes one thing the client's checksum ignores or hashes and checks the seed follows:
relocations put back, the import address table read from the name table, the descriptor time stamp
and the header checksum zeroed, writable sections hashed as zeros, unicows.dll and DivxDecoder.dll
appended. The challenge is read from the core's AuthSession.cpp, so a core that changes it fails here.

The cross-source check: with TORMENT_STOCK_CLIENT naming a stock 3.3.5a (12340) folder, the stock
Wow.exe, DivxDecoder.dll and unicows.dll must give the seed AzerothCore ships in build_info for 12340.
It reads the player's files in place and skips without them.

    python3 client-extension/tests/test_version_seed.py
    TORMENT_STOCK_CLIENT=/mnt/c/<folder> python3 client-extension/tests/test_version_seed.py
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "wowdecomp"))
import version_seed as vs  # noqa: E402

REPO = HERE.parents[1]
AUTH_SESSION = Path("azerothcore-wotlk/src/server/apps/authserver/Server/AuthSession.cpp")
BUILD_INFO = Path("azerothcore-wotlk/data/sql/base/db_auth/build_info.sql")
# The stock 12340 files the cross-source check expects, by sha256 (Wow.exe is tswow's clean client).
STOCK = {"wow.exe": "aa63a5750d60ef16746c686b3d5e26876d98953eab08b1c026cd0faf78e88cb8",
         "divxdecoder.dll": "ed34d37b575c91a56704218eb9f6abbefda8b7de0e2ed44c96191abd0f9915a5",
         "unicows.dll": "22f23cc65698741184ec34f46e6f69717644e0b5aabf5d5bd015101f2d72e56e"}


def core_file(rel: Path) -> Path | None:
    for root in (REPO, Path("/home/user/diablocraft")):
        if (root / rel).is_file():
            return root / rel
    return None

FILE_ALIGN, SECTION_ALIGN = 0x200, 0x1000
TEXT_RVA, RDATA_RVA, DATA_RVA, RELOC_RVA = 0x1000, 0x2000, 0x3000, 0x4000
POINTER_AT = TEXT_RVA + 0x10        # a pointer in .text that a DIR64/HIGHLOW fixup relocates
IAT_RVA, INT_RVA, NAME_RVA, DLL_RVA = RDATA_RVA + 0x100, RDATA_RVA + 0x140, RDATA_RVA + 0x180, RDATA_RVA + 0x1A0
DESC_RVA = RDATA_RVA


def build_pe(*, is32: bool = False, image_base: int | None = None, text: bytes = b"\xC3" * 8,
             data: bytes = b"\x11" * 16, iat: int | None = None, desc_stamp: int = 0, e_csum: int = 0,
             with_reloc: bool = True) -> bytes:
    """A small PE image: .text with one relocated pointer, .rdata with one import (descriptor, name
    table, address table), writable .data, .reloc. `iat` writes a bound address into the IAT."""
    width = 4 if is32 else 8
    base = image_base if image_base is not None else (0x400000 if is32 else 0x140000000)
    opt_size = 224 if is32 else 240
    sections = [(b".text", TEXT_RVA, 0x60000020), (b".rdata", RDATA_RVA, 0x40000040),
                (b".data", DATA_RVA, 0xC0000040)]
    if with_reloc:
        sections.append((b".reloc", RELOC_RVA, 0x42000040))
    lfanew = 0x40
    headers_size = FILE_ALIGN
    size_of_image = RELOC_RVA + SECTION_ALIGN

    txt = bytearray(0x200)
    txt[: len(text)] = text
    struct.pack_into("<I" if is32 else "<Q", txt, POINTER_AT - TEXT_RVA, base + DATA_RVA)

    rd = bytearray(0x200)
    hint_name = INT_RVA - RDATA_RVA
    struct.pack_into("<IIIII", rd, 0, INT_RVA, desc_stamp, 0, DLL_RVA, IAT_RVA)  # descriptor; the next is zeros
    thunk = struct.pack("<I" if is32 else "<Q", NAME_RVA)
    rd[hint_name:hint_name + width] = thunk
    bound = struct.pack("<I" if is32 else "<Q", iat) if iat is not None else thunk
    rd[IAT_RVA - RDATA_RVA:IAT_RVA - RDATA_RVA + width] = bound
    rd[NAME_RVA - RDATA_RVA:NAME_RVA - RDATA_RVA + 8] = b"\0\0Beep\0\0"
    rd[DLL_RVA - RDATA_RVA:DLL_RVA - RDATA_RVA + 13] = b"KERNEL32.dll\0"

    dat = bytearray(0x200)
    dat[: len(data)] = data

    rel = bytearray(0x200)
    kind = vs.REL_HIGHLOW if is32 else vs.REL_DIR64
    struct.pack_into("<IIHH", rel, 0, TEXT_RVA, 12, (kind << 12) | (POINTER_AT - TEXT_RVA), 0)

    bodies = [txt, rd, dat] + ([rel] if with_reloc else [])
    pe = bytearray(headers_size)
    pe[:2] = b"MZ"
    struct.pack_into("<H", pe, vs.E_CSUM_OFFSET, e_csum)
    struct.pack_into("<I", pe, 0x3C, lfanew)
    pe[lfanew:lfanew + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", pe, lfanew + 4, 0x14C if is32 else 0x8664, len(sections), 0, 0, 0, opt_size,
                     0x0102 if is32 else 0x0022)
    opt = lfanew + 24
    struct.pack_into("<H", pe, opt, 0x10B if is32 else 0x20B)
    if is32:
        struct.pack_into("<I", pe, opt + 28, base)
    else:
        struct.pack_into("<Q", pe, opt + 24, base)
    struct.pack_into("<II", pe, opt + 32, SECTION_ALIGN, FILE_ALIGN)
    struct.pack_into("<II", pe, opt + 56, size_of_image, headers_size)
    struct.pack_into("<H", pe, opt + 70, 0x0160 if not is32 else 0)
    dirs = opt + (96 if is32 else 112)
    struct.pack_into("<I", pe, dirs - 4, 16)
    struct.pack_into("<II", pe, dirs + 8 * vs.IMAGE_DIRECTORY_ENTRY_IMPORT, DESC_RVA, 40)
    if with_reloc:
        struct.pack_into("<II", pe, dirs + 8 * vs.IMAGE_DIRECTORY_ENTRY_BASERELOC, RELOC_RVA, 12)
    sec = opt + opt_size
    raw = headers_size
    for i, ((name, rva, chars), body) in enumerate(zip(sections, bodies)):
        s = sec + 40 * i
        pe[s:s + 8] = name.ljust(8, b"\0")
        struct.pack_into("<IIII", pe, s + 8, len(body) - 0x10, rva, len(body), raw)
        struct.pack_into("<I", pe, s + 36, chars)
        raw += len(body)
    for body in bodies:
        pe += body
    return bytes(pe)


class VersionSeed(unittest.TestCase):
    def test_the_challenge_is_the_cores(self):
        src = core_file(AUTH_SESSION)
        if not src:
            self.skipTest(f"{AUTH_SESSION} not found")
        m = re.search(r"VersionChallenge\s*=\s*\{\s*\{([^}]*)\}", src.read_text())
        self.assertIsNotNone(m, "VersionChallenge not found in AuthSession.cpp")
        core = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", m.group(1)))
        self.assertEqual(core, vs.VERSION_CHALLENGE)

    def test_the_stock_client_gives_the_cores_stock_seed(self):
        folder = os.environ.get("TORMENT_STOCK_CLIENT")
        sql = core_file(BUILD_INFO)
        if not folder or not sql:
            self.skipTest("TORMENT_STOCK_CLIENT not set or build_info.sql not found")
        files = {p.name.lower(): p for p in Path(folder).iterdir() if p.name.lower() in STOCK}
        for name, sha in STOCK.items():
            self.assertIn(name, files, f"{name} not in {folder}")
            self.assertEqual(hashlib.sha256(files[name].read_bytes()).hexdigest(), sha, f"{name} is not the stock file")
        row = re.search(r"\(12340,[^)]*'([0-9A-F]{40})','[0-9A-F]{40}'\)", sql.read_text())
        self.assertIsNotNone(row, "no 12340 row with a Windows seed in build_info.sql")
        got = vs.seed(files["wow.exe"].read_bytes(), files["divxdecoder.dll"].read_bytes(),
                      files["unicows.dll"].read_bytes())
        self.assertEqual(got, row.group(1))

    def test_the_seed_is_an_hmac_sha1_keyed_by_the_challenge(self):
        pe = build_pe()
        stream = vs.image_stream(vs.Image(pe))
        want = hmac.new(vs.VERSION_CHALLENGE, stream + b"unicows", hashlib.sha1).hexdigest().upper()
        self.assertEqual(vs.seed(pe, None, b"unicows"), want)
        self.assertRegex(want, r"^[0-9A-F]{40}$")

    def test_a_relocated_load_hashes_as_the_file(self):
        for is32 in (False, True):
            pe = build_pe(is32=is32)
            at_base = vs.seed(pe)
            for delta in (0x10000, 0x7FF600000000 if not is32 else 0x30000000):
                moved = vs.Image(pe, delta)
                self.assertNotEqual(bytes(moved.mem), bytes(vs.Image(pe).mem), "the load did relocate")
                self.assertEqual(vs.seed(pe, load_delta=delta), at_base, (is32, hex(delta)))

    def test_read_only_bytes_count(self):
        self.assertNotEqual(vs.seed(build_pe(text=b"\xC3" * 8)), vs.seed(build_pe(text=b"\x90" * 8)))

    def test_writable_sections_hash_as_zeros(self):
        self.assertEqual(vs.seed(build_pe(data=b"\x11" * 16)), vs.seed(build_pe(data=b"\x22" * 16)))

    def test_the_import_address_table_is_read_from_the_name_table(self):
        self.assertEqual(vs.seed(build_pe()), vs.seed(build_pe(iat=0x7FFA12345678)))

    def test_the_descriptor_time_stamp_and_header_checksum_are_zeroed(self):
        self.assertEqual(vs.seed(build_pe()), vs.seed(build_pe(desc_stamp=0xFFFFFFFF)))
        self.assertEqual(vs.seed(build_pe()), vs.seed(build_pe(e_csum=0xBEEF)))

    def test_unicows_and_divx_are_appended(self):
        pe = build_pe()
        base = vs.seed(pe)
        self.assertNotEqual(vs.seed(pe, unicows=b"u"), base)
        self.assertNotEqual(vs.seed(pe, divx=build_pe(is32=True)), base)
        mac = hmac.new(vs.VERSION_CHALLENGE, digestmod=hashlib.sha1)
        mac.update(vs.image_stream(vs.Image(pe)))
        mac.update(vs.image_stream(vs.Image(build_pe(is32=True))))
        mac.update(b"u")
        self.assertEqual(vs.seed(pe, build_pe(is32=True), b"u"), mac.hexdigest().upper())

    def test_the_stream_covers_every_section_padded_to_alignment(self):
        pe = build_pe()
        img = vs.Image(pe)
        sections = 1 + len(img.sections)  # the headers count as one
        self.assertEqual(len(vs.image_stream(img)), sections * SECTION_ALIGN)

    def test_not_a_pe_is_refused(self):
        with self.assertRaises(vs.PeError):
            vs.seed(b"MZ" + bytes(0x40))
        with self.assertRaises(vs.PeError):
            vs.seed(b"not an exe")

    def test_the_command_line_prints_the_seed(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            exe, uni = Path(d) / "WowClient64.exe", Path(d) / "unicows.dll"
            exe.write_bytes(build_pe())
            uni.write_bytes(b"unicows")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(vs.main(["--exe", str(exe), "--unicows", str(uni)]), 0)
            self.assertEqual(out.getvalue().strip(), vs.seed(build_pe(), None, b"unicows"))

    def test_check_proof_tells_the_file_walk_from_a_moved_load(self):
        # seed-probe/check_proof.py on the runner: the probe's stream (the client's code on its loaded
        # self) must be the walk over its file. The stock walk under ASLR, where Windows wrote the load
        # address into the in-memory ImageBase, hashes moved bytes and is told apart.
        import contextlib
        import io
        import tempfile
        sys.path.insert(0, str(HERE.parent / "wowdecomp" / "seed-probe"))
        import check_proof
        pe = build_pe()
        moved = vs.Image(pe, 0x7FF600000000)
        struct.pack_into("<Q", moved.mem, moved.opt + 24, moved.address)
        moved.image_base = moved.address
        with tempfile.TemporaryDirectory() as d:
            exe, good, bad = Path(d) / "probe.exe", Path(d) / "good.bin", Path(d) / "bad.bin"
            exe.write_bytes(pe)
            good.write_bytes(vs.image_stream(vs.Image(pe)))
            bad.write_bytes(vs.image_stream(moved))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(check_proof.main([str(exe), str(good), str(good)]), 0)
                self.assertEqual(check_proof.main([str(exe), str(good), str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()

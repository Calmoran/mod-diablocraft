#!/usr/bin/env python3
"""build_id.py and patch 0009: the crash log's first line names the build, and the build's PDB is kept.

Synthetic PE images and PDBs carry the format cases (a GUID's mixed endianness, a PDB that is not the one the exe
was linked with, a missing CodeView entry, a debug directory pointing outside the image, the store's rules).
Two cross-source checks:

  * the C++ BuildLine function of patch 0009 is cut out of the patch, compiled on Linux against a header that
    lays out the Windows PE structs (under AddressSanitizer, on an image allocated at exactly SizeOfImage) and
    must print the same line as build_id.py, on the synthetic images and on a real client-rebuild artefact;
  * on a real artefact (the shared scratch folder, or $TORMENT_REBUILD_ARTEFACT) the exe's TimeDateStamp,
    SizeOfImage, GUID and age must equal what binutils' objdump reads from it.

The C++ is not compiled by MSVC here (that is the client-rebuild workflow); the header's layouts are asserted
against the PE format's own offsets. The checks skip without g++, objdump or an artefact.

Run: python3 client-extension/tests/test_build_id.py
"""

from __future__ import annotations

import calendar
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WOWDECOMP = HERE.parent / "wowdecomp"
sys.path.insert(0, str(WOWDECOMP))
import build_id as B  # noqa: E402

PATCH = WOWDECOMP / "patches" / "0009-crash-log-names-the-build.patch"
WORKFLOW = REPO / ".github" / "workflows" / "client-rebuild.yml"
SCRATCH = Path.home() / "diablocraft" / "azerothcore-wotlk" / "build" / "_agent-scratch"

GUID = "F01213CA-F806-43A8-B663-2EE47C894B9D"


def pe(stamp=0x6AD97161, size_of_image=0x3000, pdb="D:\\a\\build\\bin\\Win\\WowClient64.pdb", guid=GUID, age=1,
       dir_rva=0x1000, dir_size=28, cv_rva=0x1040, cv_size=None, nul=True, magic=0x20B, machine=0x8664) -> bytes:
    """A small PE image: one section at 0x1000 holding a debug directory with one CodeView entry. The knobs move
    the directory or the entry out of range, or drop the entry's terminator."""
    name = pdb.encode() + (b"\0" if nul else b"")
    cv = b"RSDS" + uuid.UUID(guid).bytes_le + struct.pack("<I", age) + name
    cv_size = len(cv) if cv_size is None else cv_size
    opt_size = 240 if magic == 0x20B else 224
    opt = bytearray(opt_size)
    struct.pack_into("<H", opt, 0, magic)
    struct.pack_into("<I", opt, 56, size_of_image)
    struct.pack_into("<I", opt, 60, 0x200)
    dirs = 112 if magic == 0x20B else 96
    struct.pack_into("<II", opt, dirs + 8 * B.IMAGE_DIRECTORY_ENTRY_DEBUG, dir_rva, dir_size)
    headers = bytearray(0x200)
    headers[:2] = b"MZ"
    struct.pack_into("<I", headers, 0x3C, 0x80)
    headers[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHI", headers, 0x84, machine, 1, stamp)
    struct.pack_into("<H", headers, 0x80 + 20, opt_size)
    headers[0x80 + 24:0x80 + 24 + opt_size] = opt
    sect = 0x80 + 24 + opt_size
    headers[sect:sect + 8] = b".rdata\0\0"
    struct.pack_into("<IIII", headers, sect + 8, 0x1000, 0x1000, 0x200, 0x200)
    body = bytearray(0x200)
    entry = struct.pack("<IIHHIIII", 0, stamp, 0, 0, B.IMAGE_DEBUG_TYPE_CODEVIEW, cv_size, cv_rva, 0)
    body[0:28] = entry
    if cv_rva - 0x1000 + len(cv) <= 0x200:  # else the entry points past the section's data
        body[cv_rva - 0x1000:cv_rva - 0x1000 + len(cv)] = cv
    return bytes(headers + body)


def msf(guid=GUID, age=1, block=512) -> bytes:
    """A minimal MSF 7.00 PDB: stream 0 empty, stream 1 the PDB info stream."""
    info = struct.pack("<III", 20000404, 0x5E000000, age) + uuid.UUID(guid).bytes_le
    directory = struct.pack("<I", 2) + struct.pack("<II", 0, len(info)) + struct.pack("<I", 3)
    blocks = [bytearray(block) for _ in range(6)]
    super_ = b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0" + struct.pack("<6I", block, 1, 6, len(directory), 0, 5)
    blocks[0][:len(super_)] = super_
    blocks[3][:len(info)] = info
    blocks[4][:len(directory)] = directory
    struct.pack_into("<I", blocks[5], 0, 4)
    return b"".join(blocks)


def sums_for(folder: Path, names) -> None:
    import hashlib
    (folder / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256((folder / n).read_bytes()).hexdigest().upper()}  {n}\n" for n in names))


def artefact(folder: Path, exe_guid=GUID, pdb_guid=GUID, pdb_age=1, exe_age=1, **kw) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "WowClient64.exe").write_bytes(pe(guid=exe_guid, age=exe_age, **kw))
    (folder / "WowClient64.pdb").write_bytes(msf(pdb_guid, pdb_age))
    other = "9722E9FE-2D5E-4919-98CD-4B1FB5C44EE1"
    (folder / "XvidDecoder.dll").write_bytes(pe(stamp=0x6AD96F9F, guid=other, pdb="XvidDecoder.pdb"))
    (folder / "XvidDecoder.pdb").write_bytes(msf(other))
    (folder / "wowdecomp-commit.txt").write_text("SatyPardus/wowdecomp 5d0aafad\n")
    sums_for(folder, ["WowClient64.exe", "WowClient64.pdb", "XvidDecoder.dll", "XvidDecoder.pdb",
                      "wowdecomp-commit.txt"])
    return folder


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.old = os.environ.get("TORMENT_PDB_STORE")
        os.environ["TORMENT_PDB_STORE"] = str(self.tmp / "store")
        self.addCleanup(self.restore)

    def restore(self):
        if self.old is None:
            os.environ.pop("TORMENT_PDB_STORE", None)
        else:
            os.environ["TORMENT_PDB_STORE"] = self.old

    def run_main(self, *argv):
        with tempfile.TemporaryFile("w+") as out, tempfile.TemporaryFile("w+") as err:
            old = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = out, err
            try:
                code = B.main([str(a) for a in argv])
            finally:
                sys.stdout, sys.stderr = old
            out.seek(0), err.seek(0)
            return code, out.read(), err.read()


class Identity(Tmp):
    def test_the_line_names_stamp_size_pdb_guid_and_age(self):
        ident = B.read_image(pe())
        self.assertEqual(
            ident.line("WowClient64.exe"),
            f"BUILD WowClient64.exe timedatestamp=6AD97161 sizeofimage=3000 pdb=WowClient64.pdb guid={GUID} age=1")
        self.assertEqual(ident.key, "6AD97161-3000")

    def test_the_guid_is_the_symbol_tools_mixed_endian_text(self):
        raw = bytes.fromhex("ca1312f006f8a843b6632ee47c894b9d")  # the bytes in the exe's CodeView entry
        self.assertEqual(B.guid_text(raw), GUID)

    def test_age_and_size_are_not_padded_the_way_the_c_format_writes_them(self):
        line = B.read_image(pe(size_of_image=0xBF9000, age=12)).line("X.exe")
        self.assertIn("sizeofimage=BF9000 ", line)
        self.assertTrue(line.endswith("age=12"))

    def test_no_codeview_entry_is_pdb_none(self):
        self.assertTrue(B.read_image(pe(dir_size=0)).line("X.exe").endswith("sizeofimage=3000 pdb=none"))

    def test_a_debug_directory_outside_the_image_is_pdb_none_not_a_crash(self):
        self.assertIsNone(B.read_image(pe(dir_rva=0x2FF0)).pdb)

    def test_a_codeview_entry_outside_the_image_or_without_a_terminator_is_skipped(self):
        self.assertIsNone(B.read_image(pe(cv_rva=0x2FF8)).pdb)
        self.assertIsNone(B.read_image(pe(nul=False, cv_size=None)).pdb)

    def test_the_pdb_identity_is_its_info_stream(self):
        self.assertEqual(B.read_pdb(msf(age=7)), (GUID, 7))

    def test_not_a_pdb_is_refused(self):
        with self.assertRaises(B.BuildIdError):
            B.read_pdb(b"x" * 4096)


class Check(Tmp):
    def test_a_matching_pair_passes_and_prints_both_lines(self):
        code, out, err = self.run_main("check", artefact(self.tmp / "a"))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual([l.split()[1] for l in out.splitlines()], ["WowClient64.exe", "XvidDecoder.dll"])

    def test_a_pdb_from_another_link_fails(self):
        a = artefact(self.tmp / "a", pdb_guid="11111111-2222-3333-4444-555555555555")
        code, _, err = self.run_main("check", a)
        self.assertEqual(code, 1)
        self.assertIn("WowClient64.pdb is 11111111", err)

    def test_the_same_guid_with_another_age_fails(self):
        code, _, err = self.run_main("check", artefact(self.tmp / "a", pdb_age=2))
        self.assertEqual(code, 1)
        self.assertIn("age 2", err)

    def test_an_exe_without_debug_info_fails(self):
        code, _, err = self.run_main("check", artefact(self.tmp / "a", dir_size=0))
        self.assertEqual(code, 1)
        self.assertIn("RelWithDebInfo", err)

    def test_an_exe_that_names_another_pdb_fails(self):
        code, _, err = self.run_main("check", artefact(self.tmp / "a", pdb="D:\\x\\Other.pdb"))
        self.assertEqual(code, 1)
        self.assertIn("names Other.pdb", err)

    def test_a_file_that_is_not_what_sha256sums_says_fails(self):
        a = artefact(self.tmp / "a")
        (a / "XvidDecoder.pdb").write_bytes(msf("9722E9FE-2D5E-4919-98CD-4B1FB5C44EE1", 1) + b"\0")
        code, _, err = self.run_main("check", a)
        self.assertEqual(code, 1)
        self.assertIn("XvidDecoder.pdb does not match SHA256SUMS.txt", err)

    def test_a_missing_pdb_fails(self):
        a = artefact(self.tmp / "a")
        (a / "WowClient64.pdb").unlink()
        self.assertEqual(self.run_main("check", a)[0], 1)


class Store(Tmp):
    def test_add_keeps_the_build_under_its_key_and_find_returns_its_pdb(self):
        a = artefact(self.tmp / "a")
        self.assertEqual(self.run_main("add", a, "--run", "39709396181")[0], 0)
        dest = self.tmp / "store" / "6AD97161-3000"
        self.assertEqual(sorted(p.name for p in dest.iterdir()),
                         sorted(["WowClient64.exe", "WowClient64.pdb", "XvidDecoder.dll", "XvidDecoder.pdb",
                                 "SHA256SUMS.txt", "wowdecomp-commit.txt", "build.txt"]))
        self.assertIn("run 39709396181", (dest / "build.txt").read_text())
        self.assertEqual((dest / "WowClient64.pdb").read_bytes(), (a / "WowClient64.pdb").read_bytes())
        self.assertEqual(oct(dest.stat().st_mode & 0o777), "0o700")
        self.assertEqual(oct((dest / "WowClient64.pdb").stat().st_mode & 0o777), "0o600")
        log = self.tmp / "WowClient_crash.log"
        log.write_text(B.read_image((a / "WowClient64.exe").read_bytes()).line("WowClient64.exe") +
                       "\nCRASH 0xC0000005 at WowClient64.exe+0x1234 (read 0x0)\n")
        code, out, _ = self.run_main("find", log)
        self.assertEqual((code, out.strip()), (0, str(dest / "WowClient64.pdb")))

    def test_the_same_build_again_is_a_no_op_and_leaves_no_staging_folder(self):
        a = artefact(self.tmp / "a")
        self.run_main("add", a)
        code, out, _ = self.run_main("add", a)
        self.assertEqual(code, 0)
        self.assertIn("already stored", out)
        self.assertEqual([p.name for p in (self.tmp / "store").iterdir()], ["6AD97161-3000"])

    def test_a_different_pdb_at_a_stored_key_is_refused_never_replaced(self):
        self.run_main("add", artefact(self.tmp / "a"))
        b = artefact(self.tmp / "b", exe_guid="11111111-2222-3333-4444-555555555555",
                     pdb_guid="11111111-2222-3333-4444-555555555555")
        code, _, err = self.run_main("add", b)
        self.assertEqual(code, 1)
        self.assertIn("never replaced", err)
        stored = B.read_pdb((self.tmp / "store" / "6AD97161-3000" / "WowClient64.pdb").read_bytes())
        self.assertEqual(stored[0], GUID)

    def test_a_pair_that_does_not_check_is_not_stored(self):
        a = artefact(self.tmp / "a", pdb_age=9)
        self.assertEqual(self.run_main("add", a)[0], 1)
        self.assertFalse((self.tmp / "store" / "6AD97161-3000").exists())

    def test_find_refuses_a_log_whose_guid_is_not_the_stored_pdbs(self):
        a = artefact(self.tmp / "a")
        self.run_main("add", a)
        line = B.read_image((a / "WowClient64.exe").read_bytes()).line("WowClient64.exe")
        code, _, err = self.run_main("find", line.replace("age=1", "age=2"))
        self.assertEqual(code, 1)
        self.assertIn("the log says", err)

    def test_find_on_an_unknown_build_says_so(self):
        code, _, err = self.run_main("find", f"BUILD WowClient64.exe timedatestamp=00000001 sizeofimage=10 "
                                             f"pdb=WowClient64.pdb guid={GUID} age=1")
        self.assertEqual(code, 1)
        self.assertIn("no stored PDB", err)

    def test_find_refuses_text_that_is_not_a_build_line(self):
        self.assertEqual(self.run_main("find", "CRASH 0xC0000005 at WowClient64.exe+0x1234")[0], 1)

    def allow_rs(self, exe: str, xvid: str, rt="a" * 64) -> Path:
        path = self.tmp / "allow.rs"
        path.write_text(f'const PINNED: [(&str, &str, bool); 3] = [\n    ("WowClient64.exe", "{exe}", true),\n'
                        f'    ("XvidDecoder.dll", "{xvid}", false),\n    ("msvcp140.dll", "{rt}", false),\n];\n')
        return path

    def test_shipped_wants_every_pinned_exe_and_decoder_stored_and_ignores_the_runtime(self):
        a = artefact(self.tmp / "a")
        self.run_main("add", a)
        exe, xvid = B.sha256(a / "WowClient64.exe"), B.sha256(a / "XvidDecoder.dll")
        code, out, _ = self.run_main("shipped", "--allow-rs", self.allow_rs(exe, xvid))
        self.assertEqual(code, 0, out)
        self.assertEqual(sum(l.startswith("ok:") for l in out.splitlines()), 2)
        self.assertNotIn("msvcp140", out)

    def test_shipped_fails_for_a_pinned_build_that_was_never_stored(self):
        a = artefact(self.tmp / "a")
        self.run_main("add", a)
        code, out, _ = self.run_main("shipped", "--allow-rs",
                                     self.allow_rs("e" * 64, B.sha256(a / "XvidDecoder.dll")))
        self.assertEqual(code, 1)
        self.assertIn("MISSING: no stored PDB for the pinned WowClient64.exe eeeeeeeeeeee", out)

    def test_shipped_with_an_empty_store_fails(self):
        self.assertEqual(self.run_main("shipped", "--allow-rs", self.allow_rs("e" * 64, "f" * 64))[0], 1)

    def test_a_pin_still_pending_is_not_a_missing_pdb(self):
        code, out, _ = self.run_main("shipped", "--allow-rs",
                                     self.allow_rs("PIN_PENDING_WowClient64.exe", "PIN_PENDING_XvidDecoder.dll"))
        self.assertEqual(code, 0)
        self.assertEqual(out.count("pending:"), 2)

    def test_the_real_allow_rs_table_is_readable(self):
        rows = dict(B.pinned_rows(B.ALLOW_RS))
        self.assertIn("WowClient64.exe", rows)
        self.assertIn("XvidDecoder.dll", rows)


def real_artefact() -> Path | None:
    candidates = [Path(os.environ["TORMENT_REBUILD_ARTEFACT"])] if os.environ.get("TORMENT_REBUILD_ARTEFACT") else []
    candidates += sorted(SCRATCH.glob("client-rebuild-run*"), reverse=True)
    for c in candidates:
        if (c / "WowClient64.exe").is_file() and (c / "WowClient64.pdb").is_file():
            return c
    return None


class RealArtefact(Tmp):
    @classmethod
    def setUpClass(cls):
        cls.real = real_artefact()
        if cls.real is None:
            raise unittest.SkipTest("no client-rebuild artefact on disk")

    def test_the_real_pair_checks(self):
        code, out, err = self.run_main("check", self.real)
        self.assertEqual((code, err), (0, ""), out)

    def test_objdump_reads_the_same_stamp_size_guid_and_age(self):
        if not shutil.which("objdump"):
            self.skipTest("no objdump")
        text = subprocess.run(["objdump", "-x", str(self.real / "WowClient64.exe")], capture_output=True, text=True,
                              env=dict(os.environ, TZ="UTC", LC_ALL="C")).stdout
        stamp = calendar.timegm(time.strptime(re.search(r"^Time/Date\s+(.+)$", text, re.M).group(1), "%a %b %d %H:%M:%S %Y"))
        size = int(re.search(r"^SizeOfImage\s+([0-9a-f]+)", text, re.M).group(1), 16)
        cv = re.search(r"RSDS signature ([0-9a-f]{32}) age (\d+) pdb", text)
        guid = str(uuid.UUID(cv.group(1))).upper()
        ident = B.read_image((self.real / "WowClient64.exe").read_bytes())
        self.assertEqual((ident.stamp, ident.size, ident.guid, ident.age), (stamp, size, guid, int(cv.group(2))))

    def test_stored_it_is_found_from_its_own_first_line(self):
        self.assertEqual(self.run_main("add", self.real)[0], 0)
        line = B.read_image((self.real / "WowClient64.exe").read_bytes()).line("WowClient64.exe")
        code, out, _ = self.run_main("find", line)
        self.assertEqual(code, 0)
        self.assertEqual(Path(out.strip()).read_bytes(), (self.real / "WowClient64.pdb").read_bytes())


# What the Windows headers give crash_log.cpp, laid out to the PE format. _snprintf_s drops the C length
# modifier, as DWORD is 32 bits on Windows and unsigned int here.
SHIM = r"""
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstdlib>
#include <cstring>
#include <string>
typedef uint8_t BYTE; typedef uint16_t WORD; typedef uint32_t DWORD; typedef int32_t LONG; typedef uint64_t ULONGLONG;
#define MAX_PATH 260
#define _TRUNCATE ((size_t)-1)
#define IMAGE_DIRECTORY_ENTRY_DEBUG 6
#define IMAGE_DEBUG_TYPE_CODEVIEW 2
struct GUID { DWORD Data1; WORD Data2; WORD Data3; BYTE Data4[8]; };
struct IMAGE_DOS_HEADER { WORD e_magic; WORD pad[29]; LONG e_lfanew; };
struct IMAGE_FILE_HEADER { WORD Machine; WORD NumberOfSections; DWORD TimeDateStamp; DWORD PointerToSymbolTable;
                           DWORD NumberOfSymbols; WORD SizeOfOptionalHeader; WORD Characteristics; };
struct IMAGE_DATA_DIRECTORY { DWORD VirtualAddress; DWORD Size; };
struct IMAGE_OPTIONAL_HEADER { WORD Magic; BYTE MajorLinkerVersion; BYTE MinorLinkerVersion; DWORD SizeOfCode;
    DWORD SizeOfInitializedData; DWORD SizeOfUninitializedData; DWORD AddressOfEntryPoint; DWORD BaseOfCode;
    ULONGLONG ImageBase; DWORD SectionAlignment; DWORD FileAlignment; WORD MajorOperatingSystemVersion;
    WORD MinorOperatingSystemVersion; WORD MajorImageVersion; WORD MinorImageVersion; WORD MajorSubsystemVersion;
    WORD MinorSubsystemVersion; DWORD Win32VersionValue; DWORD SizeOfImage; DWORD SizeOfHeaders; DWORD CheckSum;
    WORD Subsystem; WORD DllCharacteristics; ULONGLONG SizeOfStackReserve; ULONGLONG SizeOfStackCommit;
    ULONGLONG SizeOfHeapReserve; ULONGLONG SizeOfHeapCommit; DWORD LoaderFlags; DWORD NumberOfRvaAndSizes;
    IMAGE_DATA_DIRECTORY DataDirectory[16]; };
struct IMAGE_NT_HEADERS { DWORD Signature; IMAGE_FILE_HEADER FileHeader; IMAGE_OPTIONAL_HEADER OptionalHeader; };
struct IMAGE_DEBUG_DIRECTORY { DWORD Characteristics; DWORD TimeDateStamp; WORD MajorVersion; WORD MinorVersion;
    DWORD Type; DWORD SizeOfData; DWORD AddressOfRawData; DWORD PointerToRawData; };
static_assert(sizeof(IMAGE_DOS_HEADER) == 64 && offsetof(IMAGE_DOS_HEADER, e_lfanew) == 0x3C, "dos header");
static_assert(sizeof(IMAGE_FILE_HEADER) == 20 && offsetof(IMAGE_FILE_HEADER, TimeDateStamp) == 4, "file header");
static_assert(offsetof(IMAGE_OPTIONAL_HEADER, SizeOfImage) == 56 && offsetof(IMAGE_OPTIONAL_HEADER, DataDirectory) == 112 &&
              sizeof(IMAGE_OPTIONAL_HEADER) == 240, "optional header (PE32+)");
static_assert(offsetof(IMAGE_NT_HEADERS, OptionalHeader) == 24 && sizeof(IMAGE_NT_HEADERS) == 264, "nt headers");
static_assert(sizeof(IMAGE_DEBUG_DIRECTORY) == 28 && offsetof(IMAGE_DEBUG_DIRECTORY, AddressOfRawData) == 20, "debug dir");
static_assert(sizeof(GUID) == 16, "guid");
static int _snprintf_s(char* buf, size_t size, size_t, const char* fmt, ...) {
    std::string f;
    for (const char* p = fmt; *p; ++p) { if (*p == 'l' && (p[1] == 'X' || p[1] == 'u')) continue; f += *p; }
    va_list ap; va_start(ap, fmt); int n = vsnprintf(buf, size, f.c_str(), ap); va_end(ap); return n;
}
"""

MAIN = r"""
int main(int argc, char** argv) {
    FILE* f = fopen(argv[1], "rb");
    if (!f) return 2;
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    unsigned char* image = (unsigned char*)malloc(n);  // exactly SizeOfImage: ASan flags any read past it
    if (fread(image, 1, n, f) != (size_t)n) return 2;
    char out[MAX_PATH + 256];
    BuildLine(image, argv[2], out, sizeof(out));
    fputs(out, stdout);
    free(image);
    return 0;
}
"""


def build_line_from(patch: Path) -> str:
    """The added lines of patch 0009 from `static void BuildLine(` to the function's closing brace."""
    added = [l[1:] for l in patch.read_text().splitlines() if l.startswith("+") and not l.startswith("+++")]
    start = next(i for i, l in enumerate(added) if l.startswith("static void BuildLine("))
    end = next(i for i in range(start, len(added)) if added[i] == "}")
    return "\n".join(added[start:end + 1])


class PatchedCode(Tmp):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("g++"):
            raise unittest.SkipTest("no g++")
        cls.dir = Path(tempfile.mkdtemp())
        src = cls.dir / "build_line.cpp"
        src.write_text(SHIM + build_line_from(PATCH) + MAIN)
        cls.exe = cls.dir / "build_line"
        result = subprocess.run(["g++", "-std=c++17", "-Wall", "-Werror", "-fsanitize=address,undefined",
                                 "-fno-sanitize-recover=all", "-o", str(cls.exe), str(src)],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(f"patch 0009's BuildLine does not compile:\n{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, True)

    def mapped(self, data: bytes) -> Path:
        """The image as the loader maps it, exactly SizeOfImage bytes."""
        ident_size = struct.unpack_from("<I", data, struct.unpack_from("<I", data, 0x3C)[0] + 24 + 56)[0]
        nt = struct.unpack_from("<I", data, 0x3C)[0]
        nsec, opt_size = struct.unpack_from("<H", data, nt + 6)[0], struct.unpack_from("<H", data, nt + 20)[0]
        headers = struct.unpack_from("<I", data, nt + 24 + 60)[0]
        mem = bytearray(ident_size)
        mem[:headers] = data[:headers]
        for i in range(nsec):
            s = nt + 24 + opt_size + 40 * i
            vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", data, s + 8)
            n = min(raw_size, vsize or raw_size)
            mem[va:va + n] = data[raw_ptr:raw_ptr + n]
        path = self.tmp / "mapped.bin"
        path.write_bytes(mem)
        return path

    def line_of(self, data: bytes, module="WowClient64.exe") -> str:
        result = subprocess.run([str(self.exe), str(self.mapped(data)), module], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_the_c_line_is_the_python_line_plus_a_newline(self):
        for kw in ({}, {"age": 12, "size_of_image": 0xBF9000}, {"stamp": 0x00000001}, {"dir_size": 0},
                   {"dir_rva": 0x2FF0}, {"cv_rva": 0x2FF8}, {"nul": False}, {"pdb": "WowClient64.pdb"},
                   {"guid": "00000000-0000-0000-0000-000000000000"}):
            data = pe(**kw)
            self.assertEqual(self.line_of(data), B.read_image(data).line("WowClient64.exe") + "\n", kw)

    def test_the_c_line_on_the_real_exe_is_the_python_line(self):
        real = real_artefact()
        if real is None:
            self.skipTest("no client-rebuild artefact on disk")
        for image in ("WowClient64.exe", "XvidDecoder.dll"):
            data = (real / image).read_bytes()
            self.assertEqual(self.line_of(data, image), B.read_image(data).line(image) + "\n", image)

    def test_the_log_opens_with_the_build_line_before_a_handler_can_write(self):
        # The hunk is in file order: the console is opened, then the build line is logged, then the crash handler.
        text = PATCH.read_text()
        self.assertLess(text.index("CONOUT$"), text.index("LogLine(build);"))
        self.assertLess(text.index("LogLine(build);"), text.index("AddVectoredExceptionHandler"))


class Workflow(unittest.TestCase):
    text = WORKFLOW.read_text()

    def test_the_build_is_still_relwithdebinfo_and_checked_for_it(self):
        self.assertIn("--config RelWithDebInfo", self.text)
        self.assertIn("build_id.py", self.text)
        self.assertRegex(self.text, r"python -I \$tool check \.")

    def test_the_check_runs_on_the_exact_files_the_artefact_stages(self):
        self.assertRegex(self.text, r"python -I \$tool ident WowClient64\.exe XvidDecoder\.dll")
        self.assertIn("build-id.txt", self.text)
        self.assertIn("sizeofimage=", self.text)  # the exe is checked for the format string patch 0009 adds

    def test_a_change_to_the_tool_reruns_the_build(self):
        self.assertIn("'client-extension/wowdecomp/build_id.py'", self.text)

    def test_no_pdb_goes_into_a_launcher_payload(self):
        manifest = (REPO / "client-patch" / "manifest.py").read_text()
        files = re.search(r"CLIENT_REBUILD_FILES\s*=\s*\((.*?)\)", manifest, re.S).group(1)
        self.assertNotIn("pdb", files.lower())
        allow = B.ALLOW_RS.read_text()
        self.assertNotIn(".pdb", re.search(r"const PINNED[^=]*=\s*\[(.*?)\n\];", allow, re.S).group(1).lower())


if __name__ == "__main__":
    sys.exit(unittest.main())

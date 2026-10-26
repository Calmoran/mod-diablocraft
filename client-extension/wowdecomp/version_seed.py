#!/usr/bin/env python3
"""The authserver's version seed for a client build: the value `build_info.winChecksumSeed` must
hold for `StrictVersionCheck` to let that client log in.

At login the client sends SHA1(A, checksum), where checksum is an HMAC-SHA1 keyed by the server's
16-byte version challenge over three inputs (wowdecomp `WoW/Source/WowSvcs/WowSvcsClient/
ChecksumExecutables.cpp`): its own loaded image, `DivxDecoder.dll` as loaded, and `unicows.dll` read
as a file. The authserver (`AuthSession::VerifyVersion`) computes the same SHA1 with build_info's
seed in place of checksum, so the seed is that checksum for AzerothCore's fixed challenge.

A loaded image is hashed as the client's `ComputeChecksum` hashes it (`Engine/Source/Os/Win64/
OsVersionHash.cpp`): the header's e_csum as zeros, relocated values put back to the file's base,
each import address table replaced by its name table, import descriptors with their time stamp and
forwarder chain zeroed, writable sections as zeros, every section padded with zeros to the section
alignment. This module maps the PE file the way the loader does and runs that walk on it, so the
seed comes from the build artefact without running the client.

The 64-bit client loads `XvidDecoder.dll`, never a module named `DivxDecoder.dll`, so that input
hashes nothing for it; the stock 32-bit client loads `DivxDecoder.dll`. `unicows.dll` is read from
the game folder, so the seed holds for a folder with that file as given here, and a folder without
it sends another proof.

    python3 version_seed.py --exe WowClient64.exe --unicows unicows.dll
    python3 version_seed.py --exe Wow.exe --divx DivxDecoder.dll --unicows unicows.dll
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import struct
import sys
from pathlib import Path

# AzerothCore's VersionChallenge, sent in every logon challenge
# (src/server/apps/authserver/Server/AuthSession.cpp).
VERSION_CHALLENGE = bytes.fromhex("BAA31E99A00B2157FC373FB369CDD2F1")

IMAGE_SCN_MEM_WRITE = 0x80000000
IMAGE_SCN_CNT_INITIALIZED_DATA = 0x40
IMAGE_SCN_MEM_READ = 0x40000000
IMAGE_DIRECTORY_ENTRY_IMPORT = 1
IMAGE_DIRECTORY_ENTRY_BASERELOC = 5
IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT = 13
SIZEOF_OPTIONAL_HEADER32 = 224
SIZEOF_IMPORT_DESCRIPTOR = 20
E_CSUM_OFFSET = 0x12

REL_ABSOLUTE, REL_HIGH, REL_LOW, REL_HIGHLOW, REL_DIR64 = 0, 1, 2, 3, 10
M32, M64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF

# Entry types of OsVersionHashEntry: 0 import thunks (hash the name table), 1 import descriptor,
# 2 relocated value, 3 zeros.
THUNKS, DESCRIPTOR, RELOCATED, ZEROS = 0, 1, 2, 3


class PeError(ValueError):
    pass


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]


class Image:
    """A PE file laid out as the loader maps it: headers at 0, each section's raw data at its RVA, the
    rest zeros. `load_delta` relocates it as the loader does for a base other than the file's."""

    def __init__(self, pe: bytes, load_delta: int = 0):
        if len(pe) < 0x40 or pe[:2] != b"MZ":
            raise PeError("not a PE image (no MZ header)")
        lfanew = _u32(pe, 0x3C)
        if not lfanew or pe[lfanew:lfanew + 4] != b"PE\0\0":
            raise PeError("no PE signature")
        nsec = _u16(pe, lfanew + 6)
        opt_size = _u16(pe, lfanew + 20)
        opt = lfanew + 24
        magic = _u16(pe, opt)
        if magic == 0x10B:
            self.is32 = True
            image_base = _u32(pe, opt + 28)
            dirs = opt + 96
        elif magic == 0x20B:
            self.is32 = False
            image_base = _u64(pe, opt + 24)
            dirs = opt + 112
        else:
            raise PeError(f"unknown optional header magic {magic:#x}")
        self.lfanew, self.opt, self.opt_size, self.dirs = lfanew, opt, opt_size, dirs
        self.image_base = image_base
        self.section_alignment = _u32(pe, opt + 32)
        self.file_alignment = _u32(pe, opt + 36)
        size_of_image = _u32(pe, opt + 56)
        self.size_of_headers = _u32(pe, opt + 60)
        self.number_of_dirs = _u32(pe, dirs - 4)
        mem = bytearray(size_of_image)
        mem[: self.size_of_headers] = pe[: self.size_of_headers]
        self.sections = []
        first = opt + opt_size
        for i in range(nsec):
            s = first + 40 * i
            vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", pe, s + 8)
            chars = _u32(pe, s + 36)
            n = min(raw_size, vsize if vsize else raw_size)
            mem[va:va + n] = pe[raw_ptr:raw_ptr + n]
            self.sections.append((va, vsize, chars))
        self.mem = mem
        self.address = image_base + load_delta
        if load_delta:
            self._relocate(load_delta)

    def directory(self, index: int) -> tuple[int, int]:
        return struct.unpack_from("<II", self.mem, self.dirs + 8 * index)

    def _relocate(self, delta: int) -> None:
        va, size = self.directory(IMAGE_DIRECTORY_ENTRY_BASERELOC)
        for off, kind, _ in _relocations(self.mem, va, size):
            if kind == REL_HIGHLOW:
                struct.pack_into("<I", self.mem, off, (_u32(self.mem, off) + delta) & M32)
            elif kind == REL_DIR64:
                struct.pack_into("<Q", self.mem, off, (_u64(self.mem, off) + delta) & M64)
            elif kind == REL_LOW:
                struct.pack_into("<H", self.mem, off, (_u16(self.mem, off) + delta) & 0xFFFF)
            elif kind == REL_HIGH:
                struct.pack_into("<H", self.mem, off, (_u16(self.mem, off) + (delta >> 16)) & 0xFFFF)


def _relocations(mem, va: int, size: int):
    """(offset, type, size) per fixup of the base relocation directory, absolute fixups left out."""
    if not va or not size:
        return
    block, end = va, va + size
    sizes = {REL_HIGH: 2, REL_LOW: 2, REL_HIGHLOW: 4, REL_DIR64: 8}
    while block < end:
        page, block_size = struct.unpack_from("<II", mem, block)
        if not block_size:
            break
        count = (block_size - 8) // 2
        for k in range(count):
            fix = _u16(mem, block + 8 + 2 * k)
            kind = fix >> 12
            if kind == REL_ABSOLUTE:
                continue
            if kind not in sizes:
                raise PeError(f"relocation type {kind} the client does not hash")
            yield page + (fix & 0xFFF), kind, sizes[kind]
        block += 8 + 2 * count


def _entries(img: Image) -> list[tuple[int, int, int, int]]:
    """The client's OsVersionHash entries (offset, size, type, param), sorted by offset."""
    out = [(E_CSUM_OFFSET, 2, ZEROS, 0)]
    # AddRelocationEntries: only when the image is not at its file base.
    if img.address != img.image_base:
        va, size = img.directory(IMAGE_DIRECTORY_ENTRY_BASERELOC)
        out += [(off, n, RELOCATED, kind) for off, kind, n in _relocations(img.mem, va, size)]
    # AddImportEntries
    imp_va, imp_size = img.directory(IMAGE_DIRECTORY_ENTRY_IMPORT)
    if imp_va:
        if imp_size < SIZEOF_IMPORT_DESCRIPTOR:
            raise PeError("import directory smaller than one descriptor")
        width = 4 if img.is32 else 8
        at, i = imp_va, 0
        while True:
            d = imp_va + SIZEOF_IMPORT_DESCRIPTOR * i
            original, _, _, name, first = struct.unpack_from("<IIIII", img.mem, d)
            if not name or not first:
                break
            n = 0
            while int.from_bytes(img.mem[first + n * width:first + (n + 1) * width], "little"):
                n += 1
            out.append((first, n * width + width, THUNKS, original))
            out.append((at, SIZEOF_IMPORT_DESCRIPTOR, DESCRIPTOR, 0))
            at += SIZEOF_IMPORT_DESCRIPTOR
            i += 1
            if SIZEOF_IMPORT_DESCRIPTOR * (i + 1) > imp_size:
                break
    out.sort(key=lambda e: e[0])
    return out


def _hash_entry(feed, img: Image, entry, data: bytes, at: int) -> None:
    offset, size, kind, param = entry
    if kind == THUNKS:
        feed(bytes(img.mem[param:param + size]) if param else bytes(size))
    elif kind == DESCRIPTOR:
        d = bytearray(data[at:at + SIZEOF_IMPORT_DESCRIPTOR].ljust(SIZEOF_IMPORT_DESCRIPTOR, b"\0"))
        d[4:12] = bytes(8)  # TimeDateStamp, ForwarderChain
        feed(bytes(d))
    elif kind == RELOCATED:
        delta = (img.address - img.image_base) & M64
        raw = data[at:at + size].ljust(size, b"\0")
        if not delta:
            feed(raw)
        elif param == REL_HIGH:
            feed(struct.pack("<I", (((_u16(raw, 0) << 16) - (delta & M32)) & M32) >> 16)[:2])
        elif param == REL_LOW:
            feed(struct.pack("<I", (_u16(raw, 0) - (delta & 0xFFFF)) & 0xFFFF)[:2])
        elif param == REL_HIGHLOW:
            feed(struct.pack("<I", (_u32(raw, 0) - delta) & M32))
        else:
            feed(struct.pack("<Q", (_u64(raw, 0) - delta) & M64))
    else:
        feed(bytes(size))


def _walk(feed, img: Image, entries, data: bytes, base: int, length: int, index: int, origin: int) -> int:
    """HashSection's loop over `length` bytes of `data` from `base`, whose first byte is at RVA
    `origin`: plain runs between entries, each entry hashed by its type. Returns the next entry."""
    pos = base
    while True:
        nxt = base + (entries[index][0] - origin) if index < len(entries) else None
        chunk = (base - pos + length) & M32
        if nxt is not None and ((nxt - pos) & M32) < chunk:
            chunk = (nxt - pos) & M32
        if chunk:
            feed(bytes(data[pos:pos + chunk]))
            pos += chunk
        else:
            _hash_entry(feed, img, entries[index], data, pos)
            pos += entries[index][1]
            index += 1
        if ((pos - base) & M32) >= length:
            return index


def _hash_section(feed, img: Image, entries, va: int, vsize: int, chars: int) -> None:
    align = img.section_alignment
    padding = ((vsize + align - 1) & ~(align - 1)) - vsize
    if chars & IMAGE_SCN_MEM_WRITE:
        feed(bytes(vsize + padding))
        return
    index = 0
    while index < len(entries) and entries[index][0] < va:
        index += 1
    if vsize:
        index = _walk(feed, img, entries, img.mem, va, vsize, index, va)
    if padding:
        _walk(feed, img, entries, bytes(padding), 0, padding, index, va + vsize)


def image_stream(img: Image) -> bytes:
    """Every byte the client feeds its HMAC for a loaded image, in order (ComputeChecksum)."""
    if img.opt_size < SIZEOF_OPTIONAL_HEADER32 or img.number_of_dirs <= IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT:
        raise PeError("optional header too small for the client's checksum")
    out = bytearray()
    entries = _entries(img)
    _hash_section(out.extend, img, entries, 0, img.size_of_headers, IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ)
    for va, vsize, chars in img.sections:
        _hash_section(out.extend, img, entries, va, vsize, chars)
    return bytes(out)


def seed(exe: bytes, divx: bytes | None = None, unicows: bytes | None = None,
         challenge: bytes = VERSION_CHALLENGE, load_delta: int = 0) -> str:
    """build_info's seed (40 upper-case hex) for a client whose image is `exe`, with `divx` loaded
    as DivxDecoder.dll (None: not loaded) and `unicows` the unicows.dll file (None: absent)."""
    mac = hmac.new(challenge, digestmod=hashlib.sha1)
    mac.update(image_stream(Image(exe, load_delta)))
    if divx is not None:
        mac.update(image_stream(Image(divx, load_delta)))
    if unicows is not None:
        mac.update(unicows)
    return mac.hexdigest().upper()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exe", required=True, type=Path, help="the client exe (WowClient64.exe or Wow.exe)")
    ap.add_argument("--divx", type=Path, help="DivxDecoder.dll, for a client that loads it (the stock 32-bit one)")
    ap.add_argument("--unicows", type=Path, help="unicows.dll from the game folder")
    a = ap.parse_args(argv)
    read = lambda p: p.read_bytes() if p else None  # noqa: E731
    try:
        print(seed(a.exe.read_bytes(), read(a.divx), read(a.unicows)))
    except PeError as e:
        print(f"version_seed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

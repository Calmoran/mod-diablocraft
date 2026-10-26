#!/usr/bin/env python3
"""Which build is it, and where is its PDB: the rebuilt client's build id and its private PDB store.

The rebuilt WowClient64.exe writes the build's identity as the first line of WowClient_crash.log (patch 0009,
Tools/WowClient/crash_log.cpp):

    BUILD WowClient64.exe timedatestamp=6AD97161 sizeofimage=BF9000 pdb=WowClient64.pdb guid=CA1312F0-... age=1

the image's PE TimeDateStamp and SizeOfImage, and the GUID and age of the PDB its CodeView entry names. A crash
line is `WowClient64.exe+0x<offset>`; the names behind the offset come from the PDB of exactly that build.
The PDB never ships to players (decisions.md 2026-10-20): the launcher's payload is a whitelist that has no
.pdb in it (client-patch/manifest.py CLIENT_REBUILD_FILES, allow.rs). CI artefacts expire, so each shipped build's
PDBs are kept here, in a private store outside the repository:

    <store>/<TimeDateStamp>-<SizeOfImage>/   WowClient64.exe/.pdb, XvidDecoder.dll/.pdb, SHA256SUMS.txt,
                                             wowdecomp-commit.txt, build.txt (the BUILD lines, run, exe sha256)

The store is $TORMENT_PDB_STORE, else $XDG_DATA_HOME/torment/client-pdb (~/.local/share/torment/client-pdb).

    build_id.py ident IMAGE...              the BUILD line each exe or dll would write (CI writes build-id.txt with it)
    build_id.py check DIR                   DIR is the unpacked client-rebuild artefact (or bin/Win): each image's
                                            PDB is the one its CodeView entry names, and SHA256SUMS.txt holds
    build_id.py add DIR [--run N]           check, then keep the build's files in the store (safe to repeat)
    build_id.py find LOG|LINE               the stored PDB for a crash log's first line
    build_id.py shipped [--allow-rs FILE]   every build the launcher pins (allow.rs PINNED) has its PDBs stored

Standard library only; CI runs it as `python -I` with no checkout beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import struct
import sys
import tempfile
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALLOW_RS = REPO / "launcher" / "engine" / "src" / "allow.rs"
# The builds' images, each with the PDB it is linked with. Only these have symbols to keep.
PAIRS = (("WowClient64.exe", "WowClient64.pdb"), ("XvidDecoder.dll", "XvidDecoder.pdb"))
KEPT = ("WowClient64.exe", "WowClient64.pdb", "XvidDecoder.dll", "XvidDecoder.pdb", "SHA256SUMS.txt",
        "wowdecomp-commit.txt")
IMAGE_DIRECTORY_ENTRY_DEBUG = 6
IMAGE_DEBUG_TYPE_CODEVIEW = 2
LINE = re.compile(r"^BUILD (?P<module>\S+) timedatestamp=(?P<stamp>[0-9A-F]{8}) sizeofimage=(?P<size>[0-9A-F]+) "
                  r"pdb=(?P<pdb>\S+) guid=(?P<guid>[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}) age=(?P<age>\d+)$")


class BuildIdError(ValueError):
    pass


def store_root() -> Path:
    if os.environ.get("TORMENT_PDB_STORE"):
        return Path(os.environ["TORMENT_PDB_STORE"])
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / "torment" / "client-pdb"


def guid_text(raw: bytes) -> str:
    """A GUID as the symbol tools and the crash log print it (the first three fields little-endian)."""
    return str(uuid.UUID(bytes_le=raw)).upper()


class Identity:
    """What names a build's image: TimeDateStamp, SizeOfImage and the CodeView entry (pdb name, GUID, age)."""

    def __init__(self, stamp: int, size: int, pdb: str | None, guid: str | None, age: int | None):
        self.stamp, self.size, self.pdb, self.guid, self.age = stamp, size, pdb, guid, age

    @property
    def key(self) -> str:
        return f"{self.stamp:08X}-{self.size:X}"

    def line(self, module: str) -> str:
        """The line crash_log.cpp's BuildLine writes, byte for byte (tests compile the C++ to prove it)."""
        pdb = "pdb=none" if self.pdb is None else f"pdb={self.pdb} guid={self.guid} age={self.age}"
        return f"BUILD {module} timedatestamp={self.stamp:08X} sizeofimage={self.size:X} {pdb}"


def read_image(pe: bytes) -> Identity:
    """The identity of a PE image from its file bytes, reading the debug directory as the loader maps it."""
    if len(pe) < 0x40 or pe[:2] != b"MZ":
        raise BuildIdError("not a PE image (no MZ header)")
    nt = struct.unpack_from("<I", pe, 0x3C)[0]
    if not nt or pe[nt:nt + 4] != b"PE\0\0":
        raise BuildIdError("no PE signature")
    nsec, stamp = struct.unpack_from("<H", pe, nt + 6)[0], struct.unpack_from("<I", pe, nt + 8)[0]
    opt_size = struct.unpack_from("<H", pe, nt + 20)[0]
    opt = nt + 24
    magic = struct.unpack_from("<H", pe, opt)[0]
    if magic not in (0x10B, 0x20B):
        raise BuildIdError(f"unknown optional header magic {magic:#x}")
    dirs = opt + (96 if magic == 0x10B else 112)
    size = struct.unpack_from("<I", pe, opt + 56)[0]
    mem = bytearray(size)
    headers = struct.unpack_from("<I", pe, opt + 60)[0]
    mem[:headers] = pe[:headers]
    for i in range(nsec):
        s = opt + opt_size + 40 * i
        vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", pe, s + 8)
        n = min(raw_size, vsize or raw_size)
        mem[va:va + n] = pe[raw_ptr:raw_ptr + n]
    dva, dsize = struct.unpack_from("<II", pe, dirs + 8 * IMAGE_DIRECTORY_ENTRY_DEBUG)
    entry_size = 28
    for at in range(0, dsize - dsize % entry_size, entry_size):
        if dva + at + entry_size > size:
            break
        kind, data_size, rva = struct.unpack_from("<III", mem, dva + at + 12)
        if kind != IMAGE_DEBUG_TYPE_CODEVIEW or data_size < 25 or rva + data_size > size:
            continue
        cv = bytes(mem[rva:rva + data_size])
        if cv[:4] != b"RSDS" or b"\0" not in cv[24:]:
            continue
        name = cv[24:cv.index(b"\0", 24)].decode("utf-8", "replace")
        return Identity(stamp, size, name.rsplit("\\", 1)[-1], guid_text(cv[4:20]), struct.unpack_from("<I", cv, 20)[0])
    return Identity(stamp, size, None, None, None)


def read_pdb(pdb: bytes) -> tuple[str, int]:
    """The GUID and age of an MSF 7.00 PDB, from its PDB info stream (stream 1)."""
    magic = b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0"
    if pdb[:32] != magic:
        raise BuildIdError("not a PDB (MSF 7.00 header missing)")
    block, _free, _count, dir_size, _unused, map_block = struct.unpack_from("<6I", pdb, 32)
    dir_blocks = -(-dir_size // block)
    # The block map lists the blocks of the stream directory; the directory lists every stream's blocks.
    listed = struct.unpack_from(f"<{dir_blocks}I", pdb, map_block * block)
    directory = b"".join(pdb[b * block:(b + 1) * block] for b in listed)[:dir_size]
    streams = struct.unpack_from("<I", directory, 0)[0]
    sizes = struct.unpack_from(f"<{streams}I", directory, 4)
    at = 4 + 4 * streams
    blocks = []
    for n in sizes:
        count = -(-n // block) if n != 0xFFFFFFFF else 0
        blocks.append(struct.unpack_from(f"<{count}I", directory, at))
        at += 4 * count
    if streams < 2 or sizes[1] < 28:
        raise BuildIdError("the PDB has no info stream")
    info = b"".join(pdb[b * block:(b + 1) * block] for b in blocks[1])[:28]
    _version, _signature, age = struct.unpack_from("<III", info, 0)
    return guid_text(info[12:28]), age


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_sums(folder: Path) -> list[str]:
    """Problems in SHA256SUMS.txt against the files beside it (the workflow writes it over dist/)."""
    sums = folder / "SHA256SUMS.txt"
    if not sums.is_file():
        return []
    problems = []
    for text in sums.read_text().splitlines():
        match = re.match(r"^([0-9A-Fa-f]{64})  (.+)$", text)
        if not match:
            problems.append(f"SHA256SUMS.txt: unreadable line {text!r}")
            continue
        target = folder / match.group(2).replace("\\", "/")
        if not target.is_file():
            problems.append(f"SHA256SUMS.txt names {match.group(2)}, which is not in {folder}")
        elif sha256(target) != match.group(1).lower():
            problems.append(f"{match.group(2)} does not match SHA256SUMS.txt")
    return problems


def check_folder(folder: Path) -> tuple[list[str], list[str]]:
    """(BUILD lines, problems) for a folder holding the images and their PDBs."""
    lines, problems = [], []
    for image, pdb in PAIRS:
        if not (folder / image).is_file() or not (folder / pdb).is_file():
            problems.append(f"{image} and {pdb} are not both in {folder}")
            continue
        ident = read_image((folder / image).read_bytes())
        lines.append(ident.line(image))
        if ident.pdb is None:
            problems.append(f"{image} has no CodeView entry: it was not linked with /debug (RelWithDebInfo)")
            continue
        if ident.pdb.lower() != pdb.lower():
            problems.append(f"{image} names {ident.pdb}, not {pdb}")
        try:
            guid, age = read_pdb((folder / pdb).read_bytes())
        except (BuildIdError, struct.error) as e:
            problems.append(f"{pdb}: {e}")
            continue
        if (guid, age) != (ident.guid, ident.age):
            problems.append(f"{pdb} is {guid} age {age}, but {image} was linked with {ident.guid} age {ident.age}")
    return lines, problems + check_sums(folder)


def cmd_ident(args) -> int:
    for image in args.images:
        print(read_image(Path(image).read_bytes()).line(Path(image).name))
    return 0


def cmd_check(args) -> int:
    lines, problems = check_folder(Path(args.dir))
    print("\n".join(lines))
    for p in problems:
        print(f"build_id: {p}", file=sys.stderr)
    return 1 if problems else 0


def cmd_add(args) -> int:
    folder = Path(args.dir)
    lines, problems = check_folder(folder)
    if problems:
        for p in problems:
            print(f"build_id: {p}", file=sys.stderr)
        return 1
    ident = read_image((folder / "WowClient64.exe").read_bytes())
    root = store_root()
    dest = root / ident.key
    if dest.exists():
        for name in ("WowClient64.exe", "WowClient64.pdb", "XvidDecoder.pdb"):
            if sha256(dest / name) != sha256(folder / name):
                print(f"build_id: {dest} already holds a different {name}; stored builds are never replaced",
                      file=sys.stderr)
                return 1
        print(f"already stored: {dest}")
        return 0
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    staging = Path(tempfile.mkdtemp(prefix=".adding-", dir=root))
    try:
        for name in KEPT:
            if (folder / name).is_file():
                shutil.copy2(folder / name, staging / name)
        run = f"run {args.run}" if args.run else "run unknown"
        (staging / "build.txt").write_text("\n".join(lines) + f"\n{run}\nWowClient64.exe sha256 "
                                           f"{sha256(folder / 'WowClient64.exe')}\n")
        for f in staging.iterdir():
            f.chmod(0o600)
        staging.chmod(0o700)
        staging.rename(dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"stored: {dest}")
    return 0


def parse_line(text: str) -> dict[str, str]:
    match = LINE.match(text.strip())
    if not match:
        raise BuildIdError(f"not a BUILD line: {text.strip()[:120]!r}")
    return match.groupdict()


def cmd_find(args) -> int:
    source = Path(args.log)
    text = source.read_text(errors="replace").splitlines()[0] if source.is_file() else args.log
    want = parse_line(text)
    dest = store_root() / f"{want['stamp']}-{want['size']}"
    pdb = dest / want["pdb"]
    if not pdb.is_file():
        print(f"build_id: no stored PDB for {want['stamp']}-{want['size']} in {store_root()}", file=sys.stderr)
        return 1
    guid, age = read_pdb(pdb.read_bytes())
    if (guid, str(age)) != (want["guid"], want["age"]):
        print(f"build_id: {pdb} is {guid} age {age}, the log says {want['guid']} age {want['age']}", file=sys.stderr)
        return 1
    print(pdb)
    return 0


def pinned_rows(allow_rs: Path) -> list[tuple[str, str]]:
    block = re.search(r"const PINNED[^=]*=\s*\[(.*?)\n\];", allow_rs.read_text(), re.S)
    if not block:
        raise BuildIdError(f"no PINNED table in {allow_rs}")
    return re.findall(r'\(\s*"([^"]+)",\s*"([^"]+)",\s*(?:true|false)\s*\)', block.group(1))


def cmd_shipped(args) -> int:
    root = store_root()
    folders = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")] if root.is_dir() else []
    missing = 0
    for target, sha in pinned_rows(Path(args.allow_rs)):
        pair = next((p for p in PAIRS if p[0].lower() == target.lower()), None)
        if pair is None:
            continue  # the VC++ runtime has no PDB of ours
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            print(f"pending: {target} is {sha}")
            continue
        found = next((d for d in folders if (d / target).is_file() and sha256(d / target) == sha), None)
        if found is None or not (found / pair[1]).is_file():
            print(f"MISSING: no stored PDB for the pinned {target} {sha[:12]} in {root}")
            missing += 1
        else:
            print(f"ok: {target} {sha[:12]} -> {found / pair[1]}")
    return 1 if missing else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ident").add_argument("images", nargs="+")
    sub.add_parser("check").add_argument("dir")
    add = sub.add_parser("add")
    add.add_argument("dir")
    add.add_argument("--run", help="the CI run the artefact came from, kept in build.txt")
    sub.add_parser("find").add_argument("log")
    sub.add_parser("shipped").add_argument("--allow-rs", default=str(ALLOW_RS))
    args = ap.parse_args(argv)
    try:
        return {"ident": cmd_ident, "check": cmd_check, "add": cmd_add, "find": cmd_find,
                "shipped": cmd_shipped}[args.cmd](args)
    except (BuildIdError, struct.error, OSError) as e:
        print(f"build_id: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

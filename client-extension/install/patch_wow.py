#!/usr/bin/env python3
"""Patch a stock 3.3.5.12340 (build 12340) Wow.exe to load WarcraftXL.dll.

This writes tswow's loader patch: a jump over the client's own "LoadLibraryA"
call into a code cave that loads WarcraftXL.dll instead, and the DLL-name string
the cave pushes. The exact bytes are tswow's, not ours:

  reference/tswow/tswow-scripts/util/ClientPatches.ts:137-162 (EXTENSION_DLL patch)
    - stage  0x28E19C  the jump into the cave (replaces "LoadLibraryA")
    - cave   0x3738B8  call LoadLibraryA on the name below, then jump back
    - name   0x5E2A71  the 20-byte DLL-name field, set to "WarcraftXL.dll"

Torment's filename replaces tswow's "ClientExtensions.dll"; the cave and the
offsets are unchanged, because the designer's exe is byte-for-byte tswow's known clean
build (its MD5 is tswow's CLEAN_CLIENT_MD5, reference/tswow/tswow-scripts/
runtime/Client.ts:32), so those file offsets apply to it as-is.

By-hand install for the designer's dev client only (brief C3). The player-facing
delivery is the launcher's bead (C4); this script changes no launcher.

Usage:
    python3 patch_wow.py /path/to/Wow.exe

It refuses any exe whose SHA256 is not in KNOWN below, printing the hash it saw
so a hash can be added. On a match it keeps the untouched exe beside the patched
one ("Wow.exe.orig" next to "Wow.exe") and patches Wow.exe in place. The
upstream tswow code does the same: it copies Wow.exe to a "_clean" file before
patching (Client.ts:190).

Nothing here ever runs against a real Wow.exe on the Linux box; only the test's
synthetic buffer does (client-extension/install/test_patch_wow.py).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# The known-good stock clients, keyed by SHA256 (the check). Second value is the
# MD5, which matches tswow's CLEAN_CLIENT_MD5 (runtime/Client.ts:32) and is kept
# only to recognise the build by hand; the third is a note.
KNOWN: dict[str, tuple[str, str]] = {
    # sha256                                                            md5 (== tswow CLEAN_CLIENT_MD5)                note
    "aa63a5750d60ef16746c686b3d5e26876d98953eab08b1c026cd0faf78e88cb8": (
        "45892bdedd0ad70aed4ccd22d9fb5984",
        "the designer's stock 3.3.5.12340 Wow.exe (the clean build tswow patches)",
    ),
}

# The SHA256 each known stock exe has once patched: the expected result, checked before anything
# is written, so a patch that comes out different is refused like an unknown exe.
PATCHED: dict[str, str] = {
    # stock sha256 -> patched sha256 (the designer's exe after this script, on his PC; the PM, 2026-10-12)
    "aa63a5750d60ef16746c686b3d5e26876d98953eab08b1c026cd0faf78e88cb8":
        "ef091efc80718c7c9da4f06b3b6b3ddf6679dd7dcd5e890b6dfa31919580f828",
}

DLL_NAME = b"WarcraftXL.dll"
DLL_NAME_FIELD = 20  # the name field tswow writes at 0x5E2A71 is exactly 20 bytes

# (file offset, the exact bytes written there) — ClientPatches.ts:137-162.
PATCHES: list[tuple[int, bytes]] = [
    # stage: jump to the cave (replaces the 6-byte "LoadLibraryA" region); 0x90 pads it
    (0x28E19C, bytes([0xE9, 0x19, 0x57, 0x0E, 0x00, 0x90])),
    # cave: call LoadLibraryA(dll), then jump back to 0x28E1A2
    (0x3738B8, bytes([
        0xEB, 0x26,                          # short jump past the cave body
        0xFF, 0x15, 0x48, 0xF2, 0x9D, 0x00,  # call dword ptr [0x9DF248]
        0x60,                                # pushad
        0x68, 0x71, 0x42, 0x9E, 0x00,        # push 0x9E4271 (the name below)
        0xFF, 0x15, 0x48, 0xF2, 0x9D, 0x00,  # call dword ptr [0x9DF248]
        0x61,                                # popad
        0xE9, 0xD0, 0xA8, 0xF1, 0xFF,        # jump back into the client
    ])),
    # name: "WarcraftXL.dll", NUL-padded to the 20-byte field
    (0x5E2A71, DLL_NAME.ljust(DLL_NAME_FIELD, b"\x00")),
]

MAX_END = max(off + len(patch) for off, patch in PATCHES)


class Refused(Exception):
    """The exe's SHA256 is not in the known list; nothing was written."""

    def __init__(self, sha256: str, md5: str):
        super().__init__(f"SHA256 {sha256} is not a known stock client")
        self.sha256 = sha256
        self.md5 = md5


class Mismatch(Exception):
    """The patched image's SHA256 is not the expected result; nothing was written."""

    def __init__(self, sha256: str, expected: str):
        super().__init__(f"patched SHA256 {sha256} is not the expected {expected}")
        self.sha256 = sha256
        self.expected = expected


def hashes(data: bytes) -> tuple[str, str]:
    return hashlib.sha256(data).hexdigest(), hashlib.md5(data).hexdigest()


def patch_bytes(data: bytes, known: dict[str, tuple[str, str]] = KNOWN) -> bytes:
    """Return the patched image. Refuse (raise Refused) if the SHA256 is unknown, and raise
    Mismatch if the result's SHA256 is not the one PATCHED expects for that exe."""
    sha256, md5 = hashes(data)
    if sha256 not in known:
        raise Refused(sha256, md5)
    if len(data) < MAX_END:
        raise ValueError(
            f"image is {len(data)} bytes, too short for the patch (needs {MAX_END})"
        )
    image = bytearray(data)
    for offset, patch in PATCHES:
        image[offset:offset + len(patch)] = patch
    result = bytes(image)
    expected = PATCHED.get(sha256)
    if expected is not None:
        got = hashlib.sha256(result).hexdigest()
        if got != expected:
            raise Mismatch(got, expected)
    return result


def patch_file(src: str | Path, known: dict[str, tuple[str, str]] = KNOWN) -> Path:
    """Keep the untouched copy beside src, then patch src in place. Return the copy."""
    src = Path(src)
    original = src.read_bytes()
    patch = patch_bytes(original, known)  # refuses before anything is written
    backup = src.with_name(src.name + ".orig")
    backup.write_bytes(original)  # the untouched copy, beside the patched exe
    src.write_bytes(patch)
    return backup


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} /path/to/Wow.exe", file=sys.stderr)
        return 2
    src = Path(argv[1])
    data = src.read_bytes()
    sha256, md5 = hashes(data)
    print(f"{src}\n  sha256 {sha256}\n  md5    {md5}")
    try:
        backup = patch_file(src, KNOWN)
    except Refused:
        print(
            "REFUSED: this exe's SHA256 is not on the known list; nothing was "
            "written.\nIf it is a stock 3.3.5.12340 client, add the SHA256 above "
            "to KNOWN in this script and run again.",
            file=sys.stderr,
        )
        return 1
    except Mismatch as mismatch:
        print(
            f"REFUSED: the patched exe would have SHA256 {mismatch.sha256}, not the expected "
            f"{mismatch.expected}; nothing was written.",
            file=sys.stderr,
        )
        return 1
    print(f"patched {src}; untouched copy kept at {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

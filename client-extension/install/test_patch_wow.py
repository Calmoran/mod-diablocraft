#!/usr/bin/env python3
"""Checks for patch_wow.py, on a synthetic byte buffer (never a real Wow.exe).

Proves the four things the C3 brief asks for:
  * the offsets and the exact bytes written (stage 0x28E19C, cave 0x3738B8,
    name 0x5E2A71), by comparing the whole patched buffer to one built from this
    test's own literals — a change in the script's bytes or offsets fails here;
  * the loader patch is internally consistent: the stage jump lands inside the
    cave, and the cave's jump-back returns to just after the stage;
  * an exe whose SHA256 is not on the known list is refused (and nothing is
    written), with the hash it saw printed for adding it;
  * the untouched copy is kept beside the patched exe.

Run: python3 client-extension/install/test_patch_wow.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patch_wow  # noqa: E402

# The expected bytes, written here as literals independent of the script, from
# reference/tswow/tswow-scripts/util/ClientPatches.ts:137-162.
STAGE = (0x28E19C, bytes([0xE9, 0x19, 0x57, 0x0E, 0x00, 0x90]))
CAVE = (0x3738B8, bytes([
    0xEB, 0x26,
    0xFF, 0x15, 0x48, 0xF2, 0x9D, 0x00,
    0x60,
    0x68, 0x71, 0x42, 0x9E, 0x00,
    0xFF, 0x15, 0x48, 0xF2, 0x9D, 0x00,
    0x61,
    0xE9, 0xD0, 0xA8, 0xF1, 0xFF,
]))
NAME = (0x5E2A71, b"WarcraftXL.dll" + b"\x00" * 6)  # 20-byte field, NUL-padded

# The designer's stock client, the first known entry the brief/PM added.
ALEX_SHA256 = "aa63a5750d60ef16746c686b3d5e26876d98953eab08b1c026cd0faf78e88cb8"
ALEX_MD5 = "45892bdedd0ad70aed4ccd22d9fb5984"  # == tswow CLEAN_CLIENT_MD5
# The SHA256 of the designer's exe after patch_wow.py patched it on his PC (C3; the PM, 2026-10-12).
ALEX_PATCHED_SHA256 = "ef091efc80718c7c9da4f06b3b6b3ddf6679dd7dcd5e890b6dfa31919580f828"

failures: list[str] = []


def expect(ok: bool, msg: str) -> None:
    if not ok:
        failures.append(msg)


def synthetic(size: int, salt: int = 0) -> bytes:
    return bytes(range(256)) * (size // 256 + 1) + bytes([salt])


def expected_image(original: bytes) -> bytes:
    image = bytearray(original)
    for offset, patch in (STAGE, CAVE, NAME):
        image[offset:offset + len(patch)] = patch
    return bytes(image)


def rel32_at(image: bytes, offset: int) -> int:
    return int.from_bytes(image[offset:offset + 4], "little", signed=True)


def check_the_bytes_and_offsets() -> None:
    size = patch_wow.MAX_END + 64
    data = synthetic(size)
    sha, _ = patch_wow.hashes(data)
    patched = patch_wow.patch_bytes(data, {sha: ("", "")})

    # whole-buffer compare: every byte outside the three spans is untouched
    expect(patched == expected_image(data), "patched buffer != expected image")
    # and the spans are exactly right
    expect(patched[STAGE[0]:STAGE[0] + len(STAGE[1])] == STAGE[1], "stage bytes wrong")
    expect(patched[CAVE[0]:CAVE[0] + len(CAVE[1])] == CAVE[1], "cave bytes wrong")
    expect(patched[NAME[0]:NAME[0] + 20] == NAME[1], "name field wrong")

    # internal consistency of the loader patch
    jump_target = STAGE[0] + 5 + rel32_at(patched, STAGE[0] + 1)
    expect(jump_target == CAVE[0] + 2, f"stage jump target {hex(jump_target)} not in cave")
    expect(CAVE[0] < jump_target < CAVE[0] + len(CAVE[1]), "stage jump lands outside the cave")
    back = CAVE[0] + 21 + 5 + rel32_at(patched, CAVE[0] + 22)
    expect(back == STAGE[0] + len(STAGE[1]), f"cave jump-back {hex(back)} != stage end")


def check_refusal() -> None:
    data = synthetic(patch_wow.MAX_END + 64)
    sha, md5 = patch_wow.hashes(data)
    # the default (real) known list must not know this buffer
    try:
        patch_wow.patch_bytes(data)
        failures.append("a buffer with an unknown hash was not refused")
    except patch_wow.Refused as refused:
        expect(refused.sha256 == sha, "Refused carried the wrong sha256")
    # a different byte changes the hash -> still refused
    other = synthetic(patch_wow.MAX_END + 64, salt=1)
    expect(patch_wow.hashes(other)[0] != sha, "salt did not change the hash")
    try:
        patch_wow.patch_bytes(other)
        failures.append("a second unknown hash was not refused")
    except patch_wow.Refused:
        pass
    # the real known list holds the designer's entry, hash and MD5
    entry = patch_wow.KNOWN.get(ALEX_SHA256)
    expect(entry is not None, "the designer's sha256 is missing from KNOWN")
    if entry is not None:
        expect(entry[0] == ALEX_MD5, "the designer's md5 column is wrong")


def check_expected_result() -> None:
    # the real list pairs the designer's stock hash with the hash his patched exe had
    expect(patch_wow.PATCHED.get(ALEX_SHA256) == ALEX_PATCHED_SHA256,
           "PATCHED does not map the designer's stock sha256 to his patched sha256")
    data = synthetic(patch_wow.MAX_END + 64)
    sha, _ = patch_wow.hashes(data)
    good = patch_wow.hashes(expected_image(data))[0]
    saved = dict(patch_wow.PATCHED)
    try:
        # a result that matches its expected hash passes
        patch_wow.PATCHED[sha] = good
        expect(patch_wow.patch_bytes(data, {sha: ("", "")}) == expected_image(data),
               "a result matching its expected hash was not returned")
        # a result that does not is refused, and patch_file writes nothing
        patch_wow.PATCHED[sha] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            wow = Path(tmp) / "Wow.exe"
            wow.write_bytes(data)
            try:
                patch_wow.patch_file(wow, {sha: ("", "")})
                failures.append("a result with the wrong hash was not refused")
            except patch_wow.Mismatch as mismatch:
                expect(mismatch.sha256 == good, "Mismatch carried the wrong sha256")
            expect(wow.read_bytes() == data, "a mismatch modified the exe")
            expect(not (Path(tmp) / "Wow.exe.orig").exists(), "a mismatch wrote a backup")
    finally:
        patch_wow.PATCHED.clear()
        patch_wow.PATCHED.update(saved)


def check_kept_copy() -> None:
    original = synthetic(patch_wow.MAX_END + 64)
    sha = hashlib.sha256(original).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        wow = Path(tmp) / "Wow.exe"
        wow.write_bytes(original)
        backup = patch_wow.patch_file(wow, {sha: ("", "")})
        expect(backup == Path(tmp) / "Wow.exe.orig", f"backup path {backup} wrong")
        expect(backup.exists(), "the untouched copy was not written")
        expect(backup.read_bytes() == original, "the untouched copy is not the original")
        expect(wow.read_bytes() == expected_image(original), "Wow.exe is not the patched image")


def check_refusal_writes_nothing() -> None:
    original = synthetic(patch_wow.MAX_END + 64)
    with tempfile.TemporaryDirectory() as tmp:
        wow = Path(tmp) / "Wow.exe"
        wow.write_bytes(original)
        try:
            patch_wow.patch_file(wow)  # default known list: no match
            failures.append("patch_file did not refuse an unknown exe")
        except patch_wow.Refused:
            pass
        expect(wow.read_bytes() == original, "refusal modified the exe")
        expect(not (Path(tmp) / "Wow.exe.orig").exists(), "refusal wrote a backup")


def check_cli_prints_the_hash() -> None:
    original = synthetic(patch_wow.MAX_END + 64)
    sha = hashlib.sha256(original).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        wow = Path(tmp) / "Wow.exe"
        wow.write_bytes(original)
        proc = subprocess.run(
            [sys.executable, str(Path(patch_wow.__file__)), str(wow)],
            capture_output=True, text=True,
        )
        expect(proc.returncode == 1, f"CLI exit {proc.returncode}, expected 1")
        expect(sha in proc.stdout, "the CLI did not print the sha256 it saw")
        expect("REFUSED" in proc.stderr, "the CLI did not report the refusal")
        expect(not (Path(tmp) / "Wow.exe.orig").exists(), "refused CLI wrote a backup")


def main() -> int:
    check_the_bytes_and_offsets()
    check_refusal()
    check_expected_result()
    check_kept_copy()
    check_refusal_writes_nothing()
    check_cli_prints_the_hash()
    if failures:
        for line in failures:
            print(f"FAIL: {line}")
        print(f"{len(failures)} checks failed")
        return 1
    print("patch_wow: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

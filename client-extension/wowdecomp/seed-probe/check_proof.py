#!/usr/bin/env python3
"""Checks the version-proof probe: the bytes the client's checksum code hashed for the probe exe, as
loaded (version_proof_probe.cpp), must equal version_seed.py's walk over the exe's file. Equal, the
seed version_seed.py gives for WowClient64.exe is the proof that exe sends, wherever ASLR loads it.

    python check_proof.py version_proof_probe.exe stream-1.bin [stream-2.bin ...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from version_seed import Image, image_stream  # noqa: E402


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    exe = Path(argv[0])
    expected = image_stream(Image(exe.read_bytes()))
    failed = 0
    for name in argv[1:]:
        got = Path(name).read_bytes()
        if got == expected:
            print(f"{name}: equal to the walk over {exe.name}'s file ({len(got)} bytes)")
            continue
        failed += 1
        at = next((i for i, (a, b) in enumerate(zip(got, expected)) if a != b), min(len(got), len(expected)))
        print(f"{name}: differs from the walk over {exe.name}'s file at byte {at} "
              f"(probe {len(got)} bytes, file walk {len(expected)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""The Damage Scalar of every revived monster's attack, decoded from D3's power files: data/d3/necromancer_revive_attacks.csv.

    python3 mod-diablocraft/scripts/generate/classes/generate_necromancer_revive_attacks.py

Revive (P6_Necro_Revive) lets a revived monster keep its own attack; each of the 55 `p6_Necro_Revive_*` attack powers states
a 'Damage Scalar' (a few spell it 'Damage Scale') that scales the revived monster's blow: 1.0 on most, 1.5 on the charges and
slams, 0.33, 0.5, 0.85 and 0.9 on others (decisions.md 2026-10-21, q-1021-36 option b). This reads them with
scripts/decode_pow.py (it needs the client archives and /usr/bin/smpq, as that script does) so the sheet can be made again;
the game reads the committed sheet through generate_necromancer_revive_scalars.py and never runs this.
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE.parents[2]
sys.path.insert(0, str(HERE.parents[1]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import decode_pow  # noqa: E402

SHEET = MODULE / "data/d3/necromancer_revive_attacks.csv"
LABEL = re.compile(r"SF_\d+ 'Damage Scal(?:ar|e)' = (\S+)")


def powers():
    names = [n.split("/")[-1][:-4] for n in decode_pow.list_files("Power/")
             if n.lower().endswith(".pow") and "p6_necro_revive_" in n.lower()]
    return sorted(names)


def scalar_of(name):
    report = subprocess.run([sys.executable, str(HERE.parents[1] / "decode_pow.py"), "power", name],
                            capture_output=True, text=True, timeout=180, check=True).stdout
    found = LABEL.search(report)
    return found.group(1) if found else ""


def main():
    rows = [(name, scalar_of(name)) for name in powers()]
    with SHEET.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n", quoting=csv.QUOTE_ALL)
        writer.writerow(["power", "damage_scalar", "source"])
        for name, scalar in rows:
            writer.writerow([name, scalar, "decode_pow.py power " + name + (
                "" if scalar else " (no Damage Scalar label: a helper)")])
    print(f"wrote {SHEET.relative_to(MODULE.parent)} ({len(rows)} powers, {sum(1 for _, s in rows if s)} with a scalar)")


if __name__ == "__main__":
    main()

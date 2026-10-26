"""Write the frozen inventory of the module's positional `n[k]` reads.

Step 4 migrates those reads to the accessor one file at a time and then
deletes the tables they read, so the step 3 comparison cannot keep scanning
the live sources: it would shrink as the migration progresses and break when
the headers go. This writes them down once, from a commit's own sources, with
the value each read got from the frozen table.

    python mod-diablocraft/scripts/freeze_positional_reads.py [commit]

Default commit: 7702de8, the baseline the whole rewrite is measured against -
the sheets were tokenised there and no record had moved yet. Re-run it only
when the PM has agreed the inventory itself should change, and say why in the
worker log: a smaller inventory is a weaker test.
"""

from __future__ import annotations

import csv
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "mod-diablocraft" / "scripts"
MANIFEST = REPO_ROOT / "mod-diablocraft" / "tests" / "spell_numbers" / "positional_reads.csv"
DEFAULT_BASELINE = "7702de8"

# Reads whose row the token report's anchors cannot see from nearby lines.
# dc_barbarian_call_of_the_ancients.cpp keeps its base row in a Base() helper 250 lines above the
# read, and that helper names the skill (dc_barbarian_call_of_the_ancients.cpp:41-45).
UNANCHORED = {("src/classes/barbarian/dc_barbarian_call_of_the_ancients.cpp", 309): "Call of the Ancients"}

# A line that guards on a rune name tells us which row the read is of. The
# report's anchors take the first thing they recognise, which for a line
# guarded on BOTH a skill and a rune is the skill - and then the read is
# recorded against the base row rather than the rune's. dc_combat.cpp:1325-1326
# are exactly that: Find(shell.spellId) under `skill=="Ancient Spear" &&
# rune=="Boulder Toss"` reads spell 81049's own first number, 20, not Ancient
# Spear's 25 (PM verified against 7702de8, 2026-09-20).
# The rule is about the VARIABLE the read is of, not about the line. A line
# can hold a base read and a rune read at once - dc_abilities.cpp:344 is
# `Base("Battle Rage")->n[2] + r->n[0] * Nearby(p, p, r->n[1]).size()` inside
# `if (Rune(*r, "Into the Fray"))` - so each read is resolved from its own
# owner: a named base row stays the base row, and a variable takes the rune
# that the innermost `Rune(*variable, "...")` above it proves.
OWNER = re.compile(r'([A-Za-z_]\w*(?:\("[^"]*"\))?)\s*(?:->|\.)n\[')
NAMED_BASE = ("Base(", "RowFor(")
BASE_VARIABLES = ("b", "base")
GUARD_LOOKBACK = 30


def guarded_rune(read, lines):
    """The rune this read's own owner is guarded as, or "" for the base row."""
    owner = OWNER.search(read["expr"])[1]
    if owner.startswith(NAMED_BASE) or owner in BASE_VARIABLES:
        return ""
    guard = re.compile(r'Rune\(\s*\*?%s\s*,\s*"([^"]+)"\)' % re.escape(owner))
    number = read["line"]
    for index in range(number - 1, max(-1, number - 1 - GUARD_LOOKBACK), -1):
        found = guard.search(lines[index])
        if found:
            return found[1]
    # The other shape: the row came from the shell being cast and the line
    # itself guards on the shell's rune name, as dc_combat.cpp:1325-1326 do.
    found = re.search(r'rune\s*==\s*"([^"]+)"', read["code"])
    return found[1] if found else ""

ABILITY_ROW = re.compile(r'\{(\d+), "([^"]*)", "([^"]*)", \{([^}]*)\}')
PASSIVE_ROW = re.compile(r'\{(\d+), "([^"]*)", \{([^}]*)\}')


def checkout(commit, into):
    archive = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", commit, "mod-diablocraft"],
                             capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(into)], input=archive, check=True)
    return into / "mod-diablocraft"


def numbers(text, pattern, key):
    out = {}
    for match in pattern.findall(text):
        out[key(match)] = [piece.strip() for piece in match[-1].split(",") if piece.strip()]
    return out


def main(commit=DEFAULT_BASELINE):
    with tempfile.TemporaryDirectory() as directory:
        module = checkout(commit, Path(directory))
        spec = importlib.util.spec_from_file_location("skill_tokens_report",
                                                      SCRIPTS / "skill_tokens_report.py")
        report = importlib.util.module_from_spec(spec)
        sys.modules["skill_tokens_report"] = report
        spec.loader.exec_module(report)
        report.MODULE_ROOT = module          # the frozen sources, not the live ones
        reads = report.positional_reads()

        sources = {path: (module / path).read_text(encoding="utf-8").splitlines()
                   for path in {read["file"] for read in reads}}
        ability = numbers((module / "src/combat/dc_ability_data.h").read_text(encoding="utf-8"),
                          ABILITY_ROW, lambda match: (match[1], match[2]))
        passives = numbers((module / "src/combat/dc_passive_data.h").read_text(encoding="utf-8"),
                           PASSIVE_ROW, lambda match: match[1])

    rows, corrected = [], []
    for read in reads:
        skill = read["skill"] or UNANCHORED.get((read["file"], read["line"]), "")
        rune = read["rune"]
        named = guarded_rune(read, sources[read["file"]])
        if named and named != rune:
            corrected.append("%s:%d %s: %s -> %s - %s"
                             % (read["file"], read["line"], read["expr"],
                                rune or "(base row)", named, read["code"][:60]))
            rune = named
        read = dict(read, rune=rune)
        table = passives.get(read["passive"], []) if read["passive"] \
            else ability.get((skill, read["rune"]), [])
        if read["index"] >= len(table):
            raise SystemExit("%s:%d reads past its own frozen table"
                             % (read["file"], read["line"]))
        rows.append({"file": read["file"], "line": read["line"], "expr": read["expr"],
                     "variable": read["variable"], "index": read["index"], "skill": skill,
                     "rune": read["rune"], "passive": read["passive"], "anchor": read["how"],
                     "frozen_value": table[read["index"]], "code": read["code"]})

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8", newline="") as stream:
        stream.write("# Every positional n[k] read the module made at %s, with the number the\n"
                     % commit)
        stream.write("# tables gave it there. Produced by scanning that commit's own sources with\n")
        stream.write("# skill_tokens_report.positional_reads(); step 4 migrates these reads away\n")
        stream.write("# and deletes the tables, so this file is what test_spell_numbers.py keeps\n")
        stream.write("# comparing against. Regenerate only with the PM's agreement:\n")
        stream.write("#   python mod-diablocraft/scripts/freeze_positional_reads.py %s\n" % commit)
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for line in corrected:
        print("  resolved by its own guard: " + line)
    print("froze %d reads at %s -> %s (%d resolved by a rune guard)"
          % (len(rows), commit, MANIFEST.relative_to(REPO_ROOT), len(corrected)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASELINE)

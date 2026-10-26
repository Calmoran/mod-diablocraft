"""The Barbarian's C++ as the tests read it (R1: class code lives in src/classes/barbarian/).

The skills' abilities were one file, src/combat/dc_abilities.cpp; they are now a dispatcher and a file per skill. A source-text
test that asked "does the abilities code do X" asks `abilities()`: every file of the folder that is not the primaries, the passives
or the Ancients, joined in name order with dc_barbarian.cpp first.
"""
import csv
import re
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "src" / "classes" / "barbarian"
OTHER = ("primar", "passives", "call_of_the_ancients")
# The passives that need code, and the state they keep (the shared half, which passives a player has, is combat/dc_passives.cpp).
PASSIVES = FOLDER / "dc_barbarian_passives.cpp"


def files(suffixes=(".cpp", ".h")):
    """The ability files of the folder: dc_barbarian.cpp first, then the others by name."""
    found = sorted(p for p in FOLDER.glob("dc_barbarian*") if p.suffix in suffixes and not any(o in p.name for o in OTHER))
    return sorted(found, key=lambda p: (p.name != "dc_barbarian.cpp", p.name))


def abilities(suffixes=(".cpp", ".h")):
    return "\n".join(p.read_text(encoding="utf-8") for p in files(suffixes))


def by_skill(suffixes=(".cpp", ".h")):
    """[(skill name, or None for a file that is not one skill's, its text)] for the ability files, dc_barbarian_<skill>.cpp being named for its skill."""
    with (FOLDER.parents[2] / "data" / "d3" / "barbarian_skills.csv").open(encoding="utf-8", newline="") as stream:
        skills = {re.sub(r"\W+", "_", row["skill_name"].lower()): row["skill_name"] for row in csv.DictReader(stream)}
    return [(skills.get(p.stem[len("dc_barbarian_"):]), p.read_text(encoding="utf-8")) for p in files(suffixes)]


def named(name):
    """One file of the folder by its name."""
    return (FOLDER / name).read_text(encoding="utf-8")


class _Joined:
    """Quacks like the Path of the old abilities file for the tests that call read_text on it."""

    def read_text(self, encoding="utf-8"):
        return abilities((".cpp",))


CPP = _Joined()

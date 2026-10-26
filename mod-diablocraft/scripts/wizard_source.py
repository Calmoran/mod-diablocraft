"""The Wizard's C++ as the tests read it (R1: class code lives in src/classes/wizard/).

The Wizard was one file, src/classes/wizard/dc_wizard.cpp; it is now a dispatch and a file per skill or family. A source-text test that
asked "does the Wizard's code do X" asks `CPP`: every .cpp of the folder joined, dc_wizard.cpp first and the others in name order.
"""
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "src" / "classes" / "wizard"


def files(suffixes=(".cpp",)):
    """The folder's files: dc_wizard.cpp first, then the others by name."""
    found = sorted(p for p in FOLDER.glob("dc_wizard*") if p.suffix in suffixes)
    return sorted(found, key=lambda p: (p.name != "dc_wizard.cpp", p.name))


def source(suffixes=(".cpp",)):
    return "\n".join(p.read_text(encoding="utf-8") for p in files(suffixes))


def named(name):
    """One file of the folder by its name."""
    return (FOLDER / name).read_text(encoding="utf-8")


class _Joined:
    """Quacks like the Path of the old dc_wizard.cpp for the tests that call read_text on it."""

    def read_text(self, encoding="utf-8"):
        return source((".cpp",))


CPP = _Joined()

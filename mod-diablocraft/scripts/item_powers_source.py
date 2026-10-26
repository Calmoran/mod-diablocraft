"""The item powers' C++ as the tests read it (R4: the engine is one file per power kind in src/combat/).

The engine was one file, src/combat/dc_item_powers.cpp; it is now the core and a file per power kind, sharing the declarations of
dc_item_powers_internal.h (its includes too). A source-text test that asked "does the item powers code do X" asks `text()`: the
header's #include lines (the header holds declarations, so its prototypes are not text a test should find), dc_item_powers.cpp and
the other dc_item_powers_*.cpp files joined in name order. A test that needs one function asks `named(file)` for the file that holds it.
"""
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "src" / "combat"
HEADER = "dc_item_powers_internal.h"


def files():
    """dc_item_powers.cpp, then the power kinds' files by name."""
    kinds = sorted(p for p in FOLDER.glob("dc_item_powers_*.cpp"))
    return [FOLDER / "dc_item_powers.cpp", *kinds]


def includes():
    return "".join(line + "\n" for line in (FOLDER / HEADER).read_text(encoding="utf-8").split("\n") if line.startswith("#include"))


def text():
    return includes() + "\n" + "\n".join(p.read_text(encoding="utf-8") for p in files())


def text_with_header():
    """text() and then the whole internal header, for a test that reads the state's declarations (a struct's members) as well. The header
    comes last, so a function's definition is still the first place its name stands."""
    return text() + "\n" + (FOLDER / HEADER).read_text(encoding="utf-8")


def named(name):
    """One file of the engine by its name."""
    return (FOLDER / name).read_text(encoding="utf-8")


class _Joined:
    """Quacks like the Path of the old engine file for the tests that call read_text on it."""

    def read_text(self, encoding="utf-8"):
        return text()


class _JoinedWithHeader:
    def read_text(self, encoding="utf-8"):
        return text_with_header()


CPP = _Joined()
CPP_WITH_HEADER = _JoinedWithHeader()

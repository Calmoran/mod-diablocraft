"""The crafting folder as the tests read it (R4: dc_crafting.cpp is split per artisan).

src/crafting/ holds the shared helpers (dc_crafting_shared.cpp), one file per artisan (dc_mystic.cpp, dc_jeweler.cpp,
dc_repair.cpp), Kanai's Cube (dc_cube.cpp) and the wiring (dc_crafting.cpp: the window bridge's Game, the commands, the
route registration), with the declarations they share in dc_crafting_internal.h. A source-text test that asks "does the
crafting code do X" asks `source()`; one that asks it of a single function reads the file that holds it.
"""
from pathlib import Path

CRAFTING = Path(__file__).resolve().parents[1] / "src" / "crafting"
# The files, in the order source() joins them: the header last, so a search for a function finds its definition first.
FILES = ("dc_crafting_shared.cpp", "dc_mystic.cpp", "dc_jeweler.cpp", "dc_repair.cpp", "dc_cube.cpp", "dc_crafting.cpp",
         "dc_crafting_internal.h")


def read(name):
    """One file of the folder."""
    return (CRAFTING / name).read_text(encoding="utf-8")


def source():
    """Every crafting .cpp and the internal header, joined. A file the folder gains must be named in FILES, so no
    test skips it."""
    found = sorted([path.name for path in CRAFTING.glob("dc_*.cpp")] + ["dc_crafting_internal.h"])
    assert found == sorted(FILES), "src/crafting holds %s, crafting_source.FILES names %s" % (found, sorted(FILES))
    return "\n".join(read(name) for name in FILES)

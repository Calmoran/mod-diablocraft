"""The loot code as the tests read it (R4: dc_loot.cpp is split, delivery in its own file).

src/loot/ holds the roll, the loaded data and the hooks (dc_loot.cpp) and the delivery of a drop (dc_loot_delivery.cpp: the
bags, the buffer behind a full bag, the ground and corpse claim, the account materials), with the declarations they share in
dc_loot_internal.h. A source-text test that asks "does the loot code do X" asks `source()`; one that asks it of a single
function reads the file that holds it (`read(name)`).
"""
from pathlib import Path

LOOT = Path(__file__).resolve().parents[1] / "src" / "loot"
# The files, in the order source() joins them. The internal header is not in the join: it declares what the .cpp files
# define, so a search for a function's signature would find two.
FILES = ("dc_loot.cpp", "dc_loot_delivery.cpp")


def read(name):
    """One file of the folder."""
    return (LOOT / name).read_text(encoding="utf-8")


def source():
    """Both dc_loot*.cpp, joined. A file the split gains must be named in FILES, so no test skips it."""
    found = sorted(path.name for path in LOOT.glob("dc_loot*.cpp"))
    assert found == sorted(FILES), "src/loot holds %s, loot_source.FILES names %s" % (found, sorted(FILES))
    return "\n".join(read(name) for name in FILES)

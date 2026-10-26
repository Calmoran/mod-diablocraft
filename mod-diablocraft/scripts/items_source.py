"""The items folder as the tests read it (R4: dc_items.cpp is split by job).

src/items/ holds the loaded data and the affix -> stat sheet (dc_items_data.cpp), the item rows (dc_items_store.cpp),
the roll and the quality decision (dc_items_roll.cpp), the item side of the Mystic's enchant (dc_items_enchant.cpp),
the stat contributions and the equip rules (dc_items_equip.cpp), legendary gems as items and the field socket path
(dc_items_gems.cpp) and the startup load, hooks, sweeps and `.dc` commands (dc_items.cpp), with the declarations they
share in dc_items_internal.h. A source-text test that asks "does the items code do X" asks `source()`; one that asks
it of one function reads the file that holds it (`read(name)`); one that compiles a struct reads it from `header()`.
"""
from pathlib import Path

ITEMS = Path(__file__).resolve().parents[1] / "src" / "items"
# The files, in the order source() joins them. The internal header is not in the join: it declares what the .cpp
# files define, so a search for a function's signature would find two.
FILES = ("dc_items_data.cpp", "dc_items_store.cpp", "dc_items_roll.cpp", "dc_items_enchant.cpp", "dc_items_equip.cpp",
         "dc_items_gems.cpp", "dc_items.cpp")
HEADER = "dc_items_internal.h"


def read(name):
    """One file of the folder."""
    return (ITEMS / name).read_text(encoding="utf-8")


def source():
    """Every dc_items*.cpp, joined. A file the split gains must be named in FILES, so no test skips it."""
    found = sorted(path.name for path in ITEMS.glob("dc_items*.cpp"))
    assert found == sorted(FILES), "src/items holds %s, items_source.FILES names %s" % (found, sorted(FILES))
    return "\n".join(read(name) for name in FILES)


def header():
    """The internal header: the structs the files share and the declarations."""
    return read(HEADER)


def block(marker, text):
    """From marker to the closing brace that matches the first `{` after it, through a following `;`."""
    assert text.count(marker) == 1, "%r is not unique" % marker
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    if text[end] == ";":
        end += 1
    return text[start:end] + "\n"


def struct(name):
    """A struct of the internal header (BaseItem, ElementalAffix, StatMapping), whole."""
    return block("struct %s\n" % name, header())


def table(name, text=None):
    """An array of dc_items_data.cpp (ElementalAffixes, ResistAffixes), whole. `text` is the source to cut it from (a
    mutant's); the default is the file."""
    return block("ElementalAffix const %s[] =" % name, read("dc_items_data.cpp") if text is None else text)


def mappings(text=None):
    """Mappings(), the affix -> stat sheet, whole."""
    return block("std::unordered_map<std::string, StatMapping> const& Mappings()",
                 read("dc_items_data.cpp") if text is None else text)


def lists(text=None):
    """What a program needs for the elemental and resist lists: ElementalAffix and the two arrays."""
    return struct("ElementalAffix") + table("ElementalAffixes", text) + table("ResistAffixes", text)


def stat_map(text=None):
    """What a program needs for the affix -> stat sheet: StatMapping and Mappings() (after lists())."""
    return struct("StatMapping") + mappings(text)


def sheet(text=None):
    """The whole sheet as one cut, in the order the single file had it: the two structs, the elemental and resist lists
    with their lookups and rolls, and Mappings(). `text` is dc_items_data.cpp's text (a mutant passes its own); the
    structs come from the header."""
    text = read("dc_items_data.cpp") if text is None else text
    start = text.index("ElementalAffix const ElementalAffixes[]")
    return struct("ElementalAffix") + struct("StatMapping") + text[start:text.index("// Contribution ids must be stable", start)]

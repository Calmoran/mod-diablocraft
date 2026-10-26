"""The rifts and the elite affixes as one text each, for the tests that read them whole.

dc_rifts.cpp and the elite affixes (one file per affix) are split over several files that share one namespace;
a test that checks a string anywhere in the system, or cuts a function out by its signature, reads the files joined.
The headers come last: they declare functions the .cpp files define, and a cut finds the first match.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
RIFTS = ("rifts/dc_rifts.cpp", "rifts/dc_rift_open.cpp", "rifts/dc_rift_scripts.cpp", "rifts/dc_rifts_shared.h")
_SHARED = ("dc_affix_common.cpp", "dc_affix_hazards.cpp", "dc_affix_unit_script.cpp")
AFFIXES = tuple("monsters/affixes/" + name for name in _SHARED + tuple(sorted(
    p.name for p in (SRC / "monsters/affixes").glob("dc_affix_*.cpp") if p.name not in _SHARED))
    + ("dc_affix_internal.h",))


def joined(files, src=SRC):
    return "".join((Path(src) / name).read_text(encoding="utf-8") for name in files)


def rifts_text(src=SRC):
    return joined(RIFTS, src)


def affixes_text(src=SRC):
    return joined(AFFIXES, src)

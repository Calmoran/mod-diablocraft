"""The Monk's Mantras as the tests read them (R2: one mechanism with four flavours is one file).

The four Mantras were a .cpp each; they are now src/classes/monk/dc_monk_mantras.cpp: the mechanism they share (the first
`namespace DC::Combat::Monk::Mantras` block: the lookups, the pulse loop, the press), a section per Mantra (`namespace
DC::Combat::Monk::<Name>`), and the always-on hook (the last `Mantras` block). A source-text test that asked "does Mantra X's
code do Y" asks `section("X")`; one that asks it of the shared loop asks `mechanism()`.
"""
import re
from pathlib import Path

MONK = Path(__file__).resolve().parents[1] / "src" / "classes" / "monk"
MANTRAS = MONK / "dc_monk_mantras.cpp"
# The section names, in the file's order.
NAMES = ("Salvation", "Healing", "Retribution", "Conviction")


def mantras():
    return MANTRAS.read_text(encoding="utf-8")


def _block(text, name, start=0):
    opening = "namespace DC::Combat::Monk::%s\n{" % name
    closing = "} // namespace DC::Combat::Monk::%s" % name
    at = text.index(opening, start)
    return text[at:text.index(closing, at) + len(closing)]


def section(name):
    """One Mantra's section: its state, its pulse and the entry points dc_monk.cpp calls."""
    if name not in NAMES:
        raise KeyError(name)
    return _block(mantras(), name)


def mechanism():
    """What the four share: the lookups, the pulse loop and the press."""
    return _block(mantras(), "Mantras")


def hook():
    """The always-on hook: the last Mantras block."""
    text = mantras()
    return _block(text, "Mantras", text.rindex("namespace DC::Combat::Monk::Mantras\n{"))


def flavour(name):
    """What a Mantra's section tells the mechanism: {"period": the pulse's tunable, "boosts": whether the press opens a
    boost window of the skill's duration_seconds}."""
    found = re.search(r'Mantras::Flavour const flavour\{\s*\.skill = Skill,\s*\.period = "([a-z0-9_]+)",\s*'
                      r'\.boosts = (true|false),', section(name))
    if not found:
        raise AssertionError("%s: no flavour" % name)
    return {"period": found.group(1), "boosts": found.group(2) == "true"}


def reads(name):
    """The sheet rows one Mantra's code reads by name, as (token, qualifier): its section's own, the radius_yards the
    mechanism's InAura reads for it, and the duration_seconds its press reads when it boosts."""
    text = section(name)
    found = {(token, qualifier or "") for token, qualifier in
             re.findall(r'Numbers::(?:Num|Get|Own)\(\s*[^,()]+(?:\([^()]*\))?,\s*"([a-z_]+)"(?:,\s*"([a-z_]+)")?', text)}
    if "Mantras::InAura(" in text:
        found.add(("radius_yards", ""))
    if flavour(name)["boosts"]:
        found.add(("duration_seconds", ""))
    return found


def tunables(name):
    """The monk.csv tunables one Mantra's code reads: Tune and Has in its section, and its pulse's period."""
    text = section(name)
    return set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text)) | set(re.findall(r'Has\("monk", "([a-z0-9_]+)"\)', text)) | {
        flavour(name)["period"]}

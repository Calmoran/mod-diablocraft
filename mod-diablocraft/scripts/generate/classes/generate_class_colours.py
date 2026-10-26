#!/usr/bin/env python3
"""Generate the class colours from one table, data/class_colours.csv (d3_class, token, hex).

Every D3 class has a row from day one; the colours are the designer's (his names: Barbarian Red,
Crusader Yellow, Demon Hunter Violet, Monk Orange, Necromancer Teal, Witch Doctor Green,
Wizard Blue). A class is LIVE when it has a class_map.csv row; only live rows reach the client,
so a class slot that is still its stock class (the Paladin until the Crusader takes it, the
Hunter until the Demon Hunter does) keeps its stock colour. A planned row is data only, checked
like any other, and goes live with no edit when its class joins class_map.csv.

Two blocks are written between their BEGIN/END lines, the rest of each file left as it is:

  client-patch/art/Interface/FrameXML/Constants.lua    RAID_CLASS_COLORS entries, the table the
                                                       game and ElvUI read for class-coloured
                                                       names (chat, party frames, unit frames).
  client-patch/art/Interface/GlueXML/CharacterCreate.lua
                                                       TORMENT_CLASS_COLORS for the login screens,
                                                       which do not load FrameXML: the create
                                                       screen's labels, tooltips and ring, and
                                                       the character list's class word (which
                                                       GetCharacterInfo gives by name, hence the
                                                       name field).

Cross-checks that fail the run: one row per D3 class (the classes of d3/class_resources.csv), no
token twice, a hex of six digits, a colour row for every live class, and for each live row the
token is the class_map.csv class's token and the client ChrClasses.dbc row of that class carries
the same token (Filename) and the D3 name (Name_Lang_enUS) the character list shows.

Run from the repo root:

    python mod-diablocraft/scripts/generate/classes/generate_class_colours.py [--check]
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_class_resources import class_token  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
TABLE = MODULE / "data/class_colours.csv"
CLASS_MAP = MODULE / "data/d3/class_map.csv"
D3_CLASSES = MODULE / "data/d3/class_resources.csv"
CLIENT_CHRCLASSES = ROOT / "client-patch/dbc/ChrClasses.dbc"
CONSTANTS = ROOT / "client-patch/art/Interface/FrameXML/Constants.lua"
CREATE = ROOT / "client-patch/art/Interface/GlueXML/CharacterCreate.lua"
BEGIN = "-- BEGIN class colours"
END = "-- END class colours"
HEX = re.compile(r"[0-9A-F]{6}")


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def chrclasses(path=None):
    """The client's ChrClasses rows by class id: (file token, enUS name)."""
    from dbc_store import Store, schema
    store = Store(Path(path or CLIENT_CHRCLASSES).read_bytes(), schema(ROOT, "chrclasses_dbc"))
    return {i: (store.decode(i)["Filename"], store.decode(i)["Name_Lang_enUS"]) for i in store.rows}


def rows(table=None, class_map=None, d3_classes=None, client=None):
    """The table's rows, each with r/g/b and whether it is live; refuses a table the checks fail."""
    table = read(table or TABLE)
    live = {r["d3_class"].strip(): r for r in read(class_map or CLASS_MAP)}
    classes = {r["d3_class"].strip() for r in read(d3_classes or D3_CLASSES)}
    client = chrclasses() if client is None else client
    seen_class, seen_token, out = set(), set(), []
    for row in table:
        name, token, hexed = row["d3_class"].strip(), row["token"].strip(), row["hex"].strip().upper()
        where = f"class_colours.csv {name or '(blank)'}"
        if name not in classes:
            raise SystemExit(f"{where}: not a D3 class of d3/class_resources.csv")
        if name in seen_class or token in seen_token:
            raise SystemExit(f"{where}: the class or the token {token} is in the table twice")
        if not HEX.fullmatch(hexed):
            raise SystemExit(f"{where}: hex {row['hex']!r} is not six hex digits")
        if not re.fullmatch(r"[A-Z]+", token):
            raise SystemExit(f"{where}: token {token!r} is not a class file token")
        seen_class.add(name)
        seen_token.add(token)
        entry = dict(d3_class=name, token=token, hex=hexed, live=name in live,
                     r=int(hexed[0:2], 16) / 255, g=int(hexed[2:4], 16) / 255, b=int(hexed[4:6], 16) / 255)
        if entry["live"]:
            wow = live[name]
            if token != class_token(wow["wow_class"]):
                raise SystemExit(f"{where}: token {token}, but class_map.csv puts it on {wow['wow_class']} "
                                 f"({class_token(wow['wow_class'])})")
            wow_id = int(wow["wow_class_id"])
            if client.get(wow_id) != (token, name):
                raise SystemExit(f"{where}: ChrClasses.dbc class {wow_id} is {client.get(wow_id)}, "
                                 f"not ({token!r}, {name!r}); regenerate the class data first")
        out.append(entry)
    missing = classes - seen_class
    if missing:
        raise SystemExit("class_colours.csv: no row for " + ", ".join(sorted(missing)))
    return out


def number(x):
    return f"{x:.3f}"


def render_frame(entries):
    lines = [BEGIN + " (generate_class_colours.py from class_colours.csv; regenerate, never edit)",
             "-- The live D3 classes in their Torment colours; every other class keeps its stock colour above."]
    for e in entries:
        if e["live"]:
            lines.append(f'RAID_CLASS_COLORS["{e["token"]}"] = {{ r = {number(e["r"])}, g = {number(e["g"])}, '
                         f'b = {number(e["b"])} }};')
    return "\n".join(lines + [END]) + "\n"


def render_glue(entries):
    lines = [BEGIN + " (generate_class_colours.py from class_colours.csv; regenerate, never edit)",
             "-- The login screens do not load FrameXML's RAID_CLASS_COLORS: the live D3 classes' colours, by file",
             "-- token, with the class name the character list shows. A class not here keeps the stock look.",
             "TORMENT_CLASS_COLORS = {"]
    for e in entries:
        if e["live"]:
            lines.append(f'\t["{e["token"]}"]\t= {{ r = {number(e["r"])}, g = {number(e["g"])}, b = {number(e["b"])}, '
                         f'hex = "{e["hex"].lower()}", name = "{e["d3_class"]}" }},')
    return "\n".join(lines + ["};", END]) + "\n"


def splice(text, block, path):
    """text with its one BEGIN..END block replaced by block."""
    start, stop = text.find(BEGIN), text.find(END)
    if start < 0 or stop < start or text.count(BEGIN) != 1 or text.count(END) != 1:
        raise SystemExit(f"{path}: needs exactly one '{BEGIN}' ... '{END}' block")
    stop = text.index("\n", stop) + 1
    return text[:start] + block + text[stop:]


def outputs(entries):
    """{path: the file's text with its block regenerated}."""
    return {path: splice(path.read_text(encoding="utf-8"), render(entries), path)
            for path, render in ((CONSTANTS, render_frame), (CREATE, render_glue))}


def shown(path):
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if a file is not what the table generates")
    args = parser.parse_args(argv)
    entries = rows()
    stale = []
    for path, text in outputs(entries).items():
        if path.read_text(encoding="utf-8") != text:
            stale.append(path)
            if not args.check:
                path.write_text(text, encoding="utf-8", newline="\n")
    if args.check and stale:
        print("stale: " + ", ".join(str(shown(p)) for p in stale) + "; run generate_class_colours.py")
        return 1
    live = [e["d3_class"] for e in entries if e["live"]]
    print(f"class colours: {len(entries)} rows, live {', '.join(live)} -> "
          f"{shown(CONSTANTS)}, {shown(CREATE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

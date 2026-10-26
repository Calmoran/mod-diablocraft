"""CharBaseInfo.dbc lists only the playable classes, every class in class_map.csv, for every race.

Run from the repo root, then package with client-patch/build.sh.
The optional argument is a stock extracted CharBaseInfo.dbc path (its layout is checked, its rows are not kept).

The playable classes are class_map.csv's wow_class_id column (Barbarian 1, Wizard 8, Monk 12). generate_class_creation.py
calls build() for it, so the Monk's pairs follow the sheet (diablocraft-1cuvw).

The stock create screen draws a class with no row for the chosen race as disabled: greyed, darkened, not
clickable, and with the stock "You must choose a different race to be this class." tooltip
(CharacterCreateEnumerateClasses: IsRaceClassValid false). That is the whole lock on an unmodified client; the
GlueXML route was refused by the client's signature check (Nightly 52, client-patch/parked/README.md). The server
gate (dc_world.cpp CanAccountCreateCharacter) refuses the other eight classes regardless.

Races are 1-8, 10, 11 (Human, Orc, Dwarf, Night Elf, Undead, Tauren, Gnome, Troll, Blood Elf, Draenei): 10 rows a class.
"""
import csv
from pathlib import Path
import struct
import sys

RACES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11)
MODULE = Path(__file__).resolve().parents[2] / 'mod-diablocraft'


def playable_classes(module=MODULE):
    with (Path(module) / 'data/d3/class_map.csv').open(encoding='utf-8-sig', newline='') as stream:
        return tuple(sorted(int(row['wow_class_id']) for row in csv.DictReader(stream)))


def wanted_pairs(module=MODULE):
    return [(r, c) for r in RACES for c in playable_classes(module)]


def build(raw, module=MODULE):
    magic, count, fields, size, strings = struct.unpack_from('<4s4I', raw)
    if (magic, fields, size) != (b'WDBC', 2, 2) or len(raw) != 20 + count * size + strings:
        raise ValueError('Expected stock 3.3.5a CharBaseInfo.dbc (two byte fields)')
    rows = wanted_pairs(module)
    return (struct.pack('<4s4I', magic, len(rows), fields, size, strings)
            + b''.join(bytes(r) for r in rows) + raw[20 + count * size:])


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'azerothcore-wotlk' / 'build/server/data/dbc/CharBaseInfo.dbc'
    output = Path(__file__).with_name('CharBaseInfo.dbc')
    output.write_bytes(build(source.read_bytes()))
    print('Wrote', output, 'with', len(wanted_pairs()), 'pairs (every class in class_map.csv for every race).')

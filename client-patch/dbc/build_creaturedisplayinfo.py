"""Build the client CreatureDisplayInfo.dbc: the stock table, every row byte for byte, plus Torment's own display rows.

Archon form (diablocraft-ie3xd, ruling 2026-10-11/12): the player wears Algalon the Observer at about a player's height, and the size must be
right from the first frame. The client tweens a change of the unit's object scale (OBJECT_FIELD_SCALE_X: the designer saw the GM scale command
shrink him over about a second) but loads a new display at its own display scale (`.morph 29553` showed Algalon at once, at full size).
So the scale is not sent at all: the form is its own display row, `display_id`'s row (model, textures, sounds) with its display scale
times `scale`, at `form_display_id`, and the server only swaps the display id (dc_wizard.cpp EnterArchon).

The three numbers are the Archon rows of mod-diablocraft/data/d3/wizard_archon_values.csv. The string block is the stock one unchanged, so
a copied row's texture offsets stay valid. The server needs no row: it never reads a player's current display from its own store for
anything but the humanoid test, which a display without extra info fails either way.

    python3 client-patch/dbc/build_creaturedisplayinfo.py
"""
import csv
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STOCK = ROOT / "azerothcore-wotlk/build/server/data/dbc/CreatureDisplayInfo.dbc"
OUT = ROOT / "client-patch/dbc/CreatureDisplayInfo.dbc"
SHEET = ROOT / "mod-diablocraft/data/d3/wizard_archon_values.csv"
FIRST_TORMENT_ID = 33000   # above the stock table (it ends at 32754)
FIELDS, SCALE_FIELD = 16, 4  # DBCfmt.h CreatureDisplayInfofmt "nixifxxxxxxxxxxx": id, model, sound, extra, scale, ...


def archon_rows(sheet=SHEET):
    """{token: value} of the Archon skill's own rows (display_id, scale, form_display_id)."""
    with sheet.open(encoding="utf-8", newline="") as stream:
        return {r["token"]: r["value"] for r in csv.DictReader(stream) if r["ability"] == "Archon"}


def build(stock, rows):
    """The stock file's bytes with the form's row added; refuses an id it cannot stand behind."""
    magic, count, fields, size, strings = struct.unpack_from("<4sIIII", stock)
    if magic != b"WDBC" or fields != FIELDS or size != FIELDS * 4:
        raise SystemExit("CreatureDisplayInfo.dbc: not the 3.3.5 layout")
    body = stock[20:20 + count * size]
    records = {struct.unpack_from("<I", body, i * size)[0]: body[i * size:(i + 1) * size] for i in range(count)}
    source, form, scale = int(rows["display_id"]), int(rows["form_display_id"]), float(rows["scale"])
    if source not in records:
        raise SystemExit("display_id %d is not a stock display" % source)
    if form in records or form < FIRST_TORMENT_ID:
        raise SystemExit("form_display_id %d is a stock id or below %d" % (form, FIRST_TORMENT_ID))
    if not 0 < scale <= 1:
        raise SystemExit("scale %g is not a shrink between 0 and 1" % scale)
    row = bytearray(records[source])
    struct.pack_into("<I", row, 0, form)
    struct.pack_into("<f", row, SCALE_FIELD * 4, struct.unpack_from("<f", row, SCALE_FIELD * 4)[0] * scale)
    return struct.pack("<4sIIII", magic, count + 1, fields, size, strings) + body + bytes(row) + stock[20 + count * size:]


def main():
    OUT.write_bytes(build(STOCK.read_bytes(), archon_rows()))
    print("wrote %s (stock rows plus the Archon form)" % OUT.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Append the Diablocraft currency rows to a stock 3.3.5a CurrencyTypes.dbc.

Run from the repo root:

    python client-patch/dbc/build_currencytypes.py

Reads the stock DBC (default: the server's extracted copy), appends one row per
material in CURRENCIES, and writes client-patch/dbc/CurrencyTypes.dbc. Rerunning
is safe: the script refuses to append a row whose ItemID or BitIndex is already
present, so it can never double-add.

Format (WDBC, 3.3.5a): 20-byte header then fixed-width records, then a string
block. CurrencyTypes has four uint32 fields and no strings - names and icons come
from the item_template row the ItemID points at.
"""

import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Always build from the stock file. The server's own copy is the patched one we
# deployed last time, and appending to that would double every row.
_SERVER_DBC = REPO_ROOT / "azerothcore-wotlk/build/server/data/dbc/CurrencyTypes.dbc"
DEFAULT_SOURCE = _SERVER_DBC.with_suffix(".dbc.stock") if _SERVER_DBC.with_suffix(".dbc.stock").is_file() else _SERVER_DBC
OUTPUT = Path(__file__).resolve().parent / "CurrencyTypes.dbc"

# 06-loot L10. ItemID is our item_template entry (see
# mod-diablocraft/data/sql/db-world/updates/loot_0003_currency_items.sql).
# Category 1 is "Miscellaneous" in the stock CurrencyCategory.dbc.
# Category 3 is "Unused" with flags 3; it is not the visible miscellaneous group.
CATEGORY = 1
CURRENCIES = [
    # (row ID, item entry, name - for the log only)
    (1000, 102000, "Death's Breath"),
    (1001, 102001, "Reusable Parts"),
    (1002, 102002, "Arcane Dust"),
    (1003, 102003, "Veiled Crystal"),
    (1004, 102004, "Forgotten Soul"),
    # 09-rifts F7. Unused until Greater Rifts (F6); it only accumulates.
    (1005, 102005, "Greater Rift Keystone"),
    (1006, 102006, "Gold Bar"), # 06 L13: one bar = 100,000 gold
    # kadala.md 3.4: keeps item 102007 a valid currency at load; the account ledger holds the count.
    (1007, 102007, "Blood Shard"),
    # bounties.md 5.5: the five act reagents, ledger materials like the Blood Shard.
    (1008, 102008, "Khanduran Rune"),
    (1009, 102009, "Caldeum Nightshade"),
    (1010, 102010, "Arreat War Tapestry"),
    (1011, 102011, "Corrupted Angel Flesh"),
    (1012, 102012, "Westmarch Holy Water"),
    # kanais-cube.md 6.3: Primordial Ashes, a ledger material like the Blood Shard.
    (1013, 102013, "Primordial Ashes"),
]
FIRST_BIT_INDEX = 30          # 1-29 are taken by stock rows; the field is 64-bit
MAX_BIT_INDEX = 64


def read_dbc(path):
    data = path.read_bytes()
    magic, records, fields, record_size, string_size = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise SystemExit(f"{path}: not a WDBC file")
    if fields != 4 or record_size != 16:
        raise SystemExit(f"{path}: expected 4 uint32 fields of 16 bytes, got {fields}/{record_size}")
    body = data[20:20 + records * record_size]
    strings = data[20 + records * record_size:]
    if len(strings) != string_size:
        raise SystemExit(f"{path}: string block is {len(strings)} bytes, header says {string_size}")
    rows = [struct.unpack("<4I", body[i * 16:(i + 1) * 16]) for i in range(records)]
    return rows, strings


def write_dbc(path, rows, strings):
    header = struct.pack("<4sIIII", b"WDBC", len(rows), 4, 16, len(strings))
    body = b"".join(struct.pack("<4I", *row) for row in rows)
    path.write_bytes(header + body + strings)


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.is_file():
        raise SystemExit(f"{source}: not found. Pass the path to a stock CurrencyTypes.dbc.")
    rows, strings = read_dbc(source)
    used_ids = {row[0] for row in rows}
    used_items = {row[1] for row in rows}
    used_bits = {row[3] for row in rows}
    print(f"{source.name}: {len(rows)} stock rows, highest ID {max(used_ids)}, highest BitIndex {max(used_bits)}")

    bit = FIRST_BIT_INDEX
    for row_id, item_id, name in CURRENCIES:
        if item_id in used_items:
            raise SystemExit(f"item {item_id} ({name}) already has a CurrencyTypes row; refusing to duplicate")
        if row_id in used_ids:
            raise SystemExit(f"row id {row_id} is already used; pick another block")
        while bit in used_bits:
            bit += 1
        if bit > MAX_BIT_INDEX:
            raise SystemExit("out of BitIndex slots; PLAYER_FIELD_KNOWN_CURRENCIES holds 64")
        rows.append((row_id, item_id, CATEGORY, bit))
        used_ids.add(row_id)
        used_items.add(item_id)
        used_bits.add(bit)
        print(f"  + {name}: ID {row_id}, item {item_id}, category {CATEGORY}, BitIndex {bit}")
        bit += 1

    rows.sort(key=lambda row: row[0])
    write_dbc(OUTPUT, rows, strings)
    print(f"wrote {OUTPUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

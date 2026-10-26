#!/usr/bin/env python3
"""Append Kadala's Blood Shard prices to the stock 3.3.5a ItemExtendedCost.dbc (diablocraft-sfvq, kadala.md Part 4).

Run from the repo root:

    python client-patch/dbc/build_itemextendedcost.py

The vendor window draws an item's price only from the client's own ItemExtendedCost.dbc, and the client reads the
highest-numbered patch's copy INSTEAD of its own, so this keeps every stock row and appends ours. The rows are not
typed here: they are read out of kadala_0001_vendor.sql's `itemextendedcost_dbc` insert, the migration the server
loads the same prices from, so the price shown and the price charged are one row. A row id that is already in the
stock file is refused.

Format (WDBC, 3.3.5a): 20-byte header, 16 uint32 fields (64 bytes) per record, then the string block (one NUL; the
table has no strings), copied through untouched.
"""
import re
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Always build from the stock file: the server never patches this one, so its copy is the stock copy.
DEFAULT_SOURCE = REPO_ROOT / "azerothcore-wotlk/build/server/data/dbc/ItemExtendedCost.dbc"
MIGRATION = REPO_ROOT / "mod-diablocraft/data/sql/db-world/updates/kadala_0001_vendor.sql"
OUTPUT = Path(__file__).resolve().parent / "ItemExtendedCost.dbc"
FIELDS, RECORD = 16, 64
INSERT = re.compile(r"INSERT INTO `itemextendedcost_dbc`.*?VALUES\n(.*?);", re.S)
ROW = re.compile(r"^\(([\d, ]+)\)[,]?$", re.M)


def read_dbc(path):
    data = path.read_bytes()
    magic, records, fields, size, string_size = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise SystemExit(f"{path}: not a WDBC file")
    if fields != FIELDS or size != RECORD:
        raise SystemExit(f"{path}: expected {FIELDS} uint32 fields of {RECORD} bytes, got {fields}/{size}")
    body = data[20:20 + records * size]
    strings = data[20 + records * size:]
    if len(strings) != string_size:
        raise SystemExit(f"{path}: string block is {len(strings)} bytes, header says {string_size}")
    return [struct.unpack("<16I", body[i * size:(i + 1) * size]) for i in range(records)], strings


def write_dbc(path, rows, strings):
    path.write_bytes(struct.pack("<4sIIII", b"WDBC", len(rows), FIELDS, RECORD, len(strings))
                     + b"".join(struct.pack("<16I", *row) for row in rows) + strings)


def migration_rows(path=MIGRATION):
    """The rows kadala_0001_vendor.sql inserts into itemextendedcost_dbc, in the file's order."""
    block = INSERT.search(path.read_text(encoding="utf-8"))
    rows = [tuple(int(v) for v in m.split(",")) for m in ROW.findall(block.group(1))] if block else []
    if not rows or any(len(r) != FIELDS for r in rows):
        raise SystemExit(f"{path}: no {FIELDS}-column itemextendedcost_dbc rows found")
    return rows


def build(stock, ours):
    """Stock rows unchanged, ours appended; a clash on the row id is a hard error."""
    used = {row[0] for row in stock}
    ids = [row[0] for row in ours]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"duplicate row ids in the migration: {ids}")
    clash = sorted(used & set(ids))
    if clash:
        raise SystemExit(f"row ids {clash} are already in the source file; refusing to overwrite")
    return list(stock) + list(ours)


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.is_file():
        raise SystemExit(f"{source}: not found. Pass the path to a stock ItemExtendedCost.dbc.")
    stock, strings = read_dbc(source)
    ours = migration_rows()
    rows = build(stock, ours)
    write_dbc(OUTPUT, rows, strings)
    print(f"{source.name}: {len(stock)} stock rows kept, highest ID {max(r[0] for r in stock)}")
    for row in ours:
        print(f"  + ID {row[0]}: {row[9]} x item {row[4]}")
    print(f"wrote {OUTPUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

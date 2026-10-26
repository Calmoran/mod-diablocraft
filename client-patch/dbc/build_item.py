#!/usr/bin/env python3
"""Append the Diablocraft item rows to a stock 3.3.5a Item.dbc.

Run from the repo root:

    python client-patch/dbc/build_item.py \
        --mysql "C:/Program Files/MySQL/MySQL Server 8.4/bin/mysql.exe" \
        --defaults-file azerothcore-wotlk/build/mysql/root-client.ini

Why this exists (docs/test-item-icons.md has the full trace): the 3.3.5a client
resolves an item's inventory icon and its equip slot from its *own* Item.dbc, not
from the server's item query response. Stock Item.dbc stops at entry 56806, and
every Diablocraft item is 100000 or above, so the client had no display info for
any of them - a "?" icon in the bag, and right-click equip doing nothing because
the client does not know the item is equippable. Dragging to the slot still
worked, because that path is validated server-side.

The server does not need these rows: ObjectMgr::LoadItemTemplates inserts the
template into its store before it looks the entry up in Item.dbc, so the miss
only skips the optional DBC-attribute cross-check.

Every field is read from item_template, which generate_sql.py built from the
CSVs. Nothing here invents a value.

Format (WDBC, 3.3.5a): a 20-byte header, then fixed-width records, then a string
block. Item.dbc is "niiiiiii" - eight 4-byte fields and no strings - so the stock
string block is copied through untouched.

Rerunning is safe: an entry already present in the source DBC is skipped, so the
script can never double-add.
"""

import argparse
import json
import re
import struct
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Always build from the stock file. The server's own copy is whatever was
# extracted last; if a patched Item.dbc ever lands there, appending to it would
# double every row.
_SERVER_DBC = REPO_ROOT / "azerothcore-wotlk/build/server/data/dbc/Item.dbc"
_STOCK = _SERVER_DBC.with_suffix(".dbc.stock")
DEFAULT_SOURCE = _STOCK if _STOCK.is_file() else _SERVER_DBC
OUTPUT = Path(__file__).resolve().parent / "Item.dbc"

# DBCStructure.h ItemEntry, in order. SoundOverrideSubclassID and Material are
# int32; the rest are uint32.
COLUMNS = ("entry", "class", "subclass", "SoundOverrideSubclass", "Material",
           "displayid", "InventoryType", "sheath")
SIGNED = {3, 4}

# Stock 3.3.5a ends at 56806 (DBCStores.cpp uses that id as its "is this a real
# 3.3.5a client" check). Anything at or below it is Blizzard's and already in the
# file; the query below is bounded by the ids actually in the DBC rather than by
# this number, which is here only to explain the gap.
LAST_STOCK_ITEM = 56806


class Database:
    def __init__(self, mysql, defaults, name):
        if not name.replace("_", "").isalnum():
            raise ValueError("Invalid database name")
        self.name = name
        self.args = [mysql, "--defaults-file=" + str(Path(defaults).resolve()),
                     "--no-login-paths", "--batch", "--raw", "--skip-column-names", name]

    def query(self, sql):
        return subprocess.check_output(self.args, input=sql, text=True,
                                       encoding="utf-8").splitlines()


def read_dbc(path):
    data = path.read_bytes()
    magic, records, fields, size, string_size = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise SystemExit(f"{path}: not a WDBC file")
    if fields != 8 or size != 32:
        raise SystemExit(f"{path}: expected 8 fields of 32 bytes, got {fields}/{size}")
    body = data[20:20 + records * size]
    strings = data[20 + records * size:]
    if len(strings) != string_size:
        raise SystemExit(f"{path}: string block is {len(strings)} bytes, header says {string_size}")
    ids = {struct.unpack_from("<I", body, index * size)[0] for index in range(records)}
    return body, strings, ids, records


def custom_items(db):
    pairs = ",".join(f"'{column}',`{column}`" for column in COLUMNS)
    rows = db.query(f"SELECT JSON_OBJECT({pairs}) FROM `item_template` ORDER BY `entry`")
    return [json.loads(line) for line in rows]


# One item_template row as generate_sql.py renders it: entry, class, subclass,
# name, displayid, Quality, InventoryType, ... (TEMPLATE_COLUMNS and the shells').
TEMPLATE_ROW = re.compile(r"^\((\d+), (\d+), (\d+), '(?:[^']|'')*', (\d+), \d+, (\d+)", re.M)
SHEATH_SQL = REPO_ROOT / "mod-diablocraft/data/sql/db-world/updates/items_0022_item_sheath.sql"
# The base items added after 0002 (the Shaman's Ritual Mace and Totem) are sheathed by the migration that inserts them.
ADDED_SHEATH_SQL = REPO_ROOT / "mod-diablocraft/data/sql/db-world/updates/items_0057_shaman_item_types.sql"
SHEATH_ROW = re.compile(r"SET `sheath`=(\d+) WHERE `entry` IN \(([\d,]+)\);")


def sync_from_sql(paths):
    """Rewrite class/subclass/displayid/InventoryType of rows already in
    Item.dbc from the generator's own item_template render - no database.

    diablocraft-class-parity (ruling 2026-09-23, Q1 option B): armor became
    Miscellaneous (items_0009/items_0010 carry it as targeted UPDATEs, so the
    full rows are read from generate_sql.py's mirrors), and the client must agree with the
    server about what an item is. Every rendered entry must already be in the
    DBC (appending stays the --mysql path's job) and nothing else is touched.

    diablocraft-pru6e: sheath too, from the generated items_0022 migration
    (b3gs1), so the client hangs a sheathed weapon where the server says;
    every other row of ours keeps the table's 0."""
    body, strings, present, records = read_dbc(OUTPUT)
    sheaths = {int(entry): int(value) for path in (SHEATH_SQL, ADDED_SHEATH_SQL)
               for value, ids in SHEATH_ROW.findall(path.read_text(encoding="utf-8")) for entry in ids.split(",")}
    body = bytearray(body)
    index = {struct.unpack_from("<I", body, n * 32)[0]: n for n in range(records)}
    changed = seen = 0
    for path in paths:
        rows = TEMPLATE_ROW.findall(Path(path).read_text(encoding="utf-8"))
        if not rows:
            raise SystemExit(f"{path}: no item_template rows found")
        for entry, item_class, subclass, display, inventory in rows:
            entry = int(entry)
            if entry not in index:
                raise SystemExit(f"{path}: entry {entry} is not in Item.dbc; append it with --mysql first")
            offset = index[entry] * 32
            record = list(struct.unpack_from("<IIIiiIII", body, offset))
            wanted = record[:]
            wanted[1], wanted[2], wanted[5], wanted[6] = int(item_class), int(subclass), int(display), int(inventory)
            wanted[7] = sheaths.pop(entry, 0)
            seen += 1
            if wanted != record:
                struct.pack_into("<IIIiiIII", body, offset, *wanted)
                changed += 1
    if sheaths:
        raise SystemExit(f"{SHEATH_SQL.name} and {ADDED_SHEATH_SQL.name}: {len(sheaths)} entries are not in the item_template render")
    OUTPUT.write_bytes(struct.pack("<4sIIII", b"WDBC", records, 8, 32, len(strings)) + bytes(body) + strings)
    print(f"synced {seen} rows from the item_template render, {changed} changed")


# Items whose item_template row is a hand-written migration, not the generator's,
# so neither --from-sql nor a database is needed to place them: one row per
# entry, in the DBC's own column order after the entry. Each must match its
# migration (mod-diablocraft/scripts/tests/items/test_bottomless_potion.py reads both).
#   102200  items_0015_bottomless_potion.sql: potion (class 0, subclass 1),
#           Material 3, display 24152 (INV_Potion_54), no inventory type.
#           generate_potion_icons.py then sets its own display (diablocraft-71scy).
HAND_WRITTEN = {
    102200: (0, 1, -1, 3, 24152, 0, 0),
}


def add_hand_written():
    """Append the HAND_WRITTEN rows Item.dbc does not have yet; rerunning adds nothing."""
    body, strings, present, records = read_dbc(OUTPUT)
    missing = {entry: row for entry, row in HAND_WRITTEN.items() if entry not in present}
    appended = bytearray()
    for entry, row in sorted(missing.items()):
        appended += struct.pack("<IIIiiIII", entry, *row)
    OUTPUT.write_bytes(struct.pack("<4sIIII", b"WDBC", records + len(missing), 8, 32, len(strings))
                       + body + bytes(appended) + strings)
    print(f"appended {len(missing)} hand-written rows ({len(HAND_WRITTEN) - len(missing)} already there)")


# Hand-written and generated migrations whose item_template rows have no database to read yet (Kadala, Part 4:
# the Blood Shard and the 17 Mystery items; the 27 set caches, Part 9; the five act reagents, bounties W3; the five Horadric Caches, bounties W4;
# Primordial Ashes, Kanai's Cube 1). Their INSERT names its columns, so any column order works.
MIGRATIONS = REPO_ROOT / "mod-diablocraft/data/sql/db-world/updates"
APPEND_SQL = ("account_economy_0003_blood_shards.sql", "kadala_0001_vendor.sql", "set_caches_0007.sql",
              "account_economy_0004_act_reagents.sql", "bounties_0003_caches.sql",
              "account_economy_0005_primordial_ashes.sql")
INSERT = re.compile(r"INSERT INTO `item_template`\s*\(([^)]*)\)\s*VALUES\n(.*?);\n", re.S)
VALUE = re.compile(r"'(?:[^']|'')*'|-?\d+")


def sql_item_rows(path):
    """{entry: DBC record} for every item_template row a migration inserts; a column it omits is the table's default."""
    rows = {}
    for columns, values in INSERT.findall(Path(path).read_text(encoding="utf-8")):
        names = [c.strip(" `\n") for c in columns.split(",")]
        for line in values.splitlines():
            cells = VALUE.findall(line)
            if len(cells) != len(names):
                raise SystemExit(f"{path}: {len(cells)} values for {len(names)} columns in {line[:60]!r}")
            row = dict(zip(names, cells))
            get = lambda name, default: int(row.get(name, default))
            rows[int(row["entry"])] = (get("class", 0), get("subclass", 0), get("SoundOverrideSubclass", -1),
                                       get("Material", 0), get("displayid", 0), get("InventoryType", 0), 0)
    if not rows:
        raise SystemExit(f"{path}: no item_template rows found")
    return rows


def append_from_sql(paths):
    """Append the migrations' item rows Item.dbc does not have yet; rerunning adds nothing."""
    body, strings, present, records = read_dbc(OUTPUT)
    wanted = {}
    for path in paths:
        wanted.update(sql_item_rows(path))
    missing = {entry: row for entry, row in wanted.items() if entry not in present}
    appended = b"".join(struct.pack("<IIIiiIII", entry, *row) for entry, row in sorted(missing.items()))
    OUTPUT.write_bytes(struct.pack("<4sIIII", b"WDBC", records + len(missing), 8, 32, len(strings))
                       + body + appended + strings)
    print(f"appended {len(missing)} migration rows ({len(wanted) - len(missing)} already there)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hand-written", action="store_true",
                        help="append the HAND_WRITTEN rows (no database, no SQL)")
    parser.add_argument("--from-sql", nargs="*", metavar="SQL", default=None,
                        help="sync existing rows from generated item_template SQL instead of MySQL; "
                             "with no files, the generator's item_template and shell mirrors")
    parser.add_argument("--append-sql", nargs="*", metavar="SQL", default=None,
                        help="append item rows from migrations (no database); with no files, the Blood Shard, Kadala's and the set caches")
    known = parser.parse_known_args()[0]
    if known.append_sql is not None:
        append_from_sql(known.append_sql or [MIGRATIONS / name for name in APPEND_SQL])
        return
    if known.hand_written:
        add_hand_written()
        return
    if known.from_sql is not None:
        mirrors = REPO_ROOT / "mod-diablocraft/data" / "generated"
        sync_from_sql(known.from_sql or [mirrors / "item_template.sql", mirrors / "unidentified_shells.sql"])
        return
    parser.add_argument("--mysql", required=True)
    parser.add_argument("--defaults-file", required=True)
    parser.add_argument("--database", default="acore_world")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE),
                        help="Stock Item.dbc to append to")
    args = parser.parse_args()

    source = Path(args.source)
    body, strings, present, records = read_dbc(source)
    print(f"source {source}: {records} records, ids up to {max(present)}")

    rows = custom_items(Database(args.mysql, args.defaults_file, args.database))
    missing = [row for row in rows if int(row["entry"]) not in present]
    if not missing:
        raise SystemExit("Every item_template entry is already in the DBC; nothing to do.")
    skipped = len(rows) - len(missing)

    appended = bytearray()
    for row in missing:
        record = bytearray(32)
        for index, column in enumerate(COLUMNS):
            value = int(row[column] or 0)
            struct.pack_into("<i" if index in SIGNED else "<I", record, index * 4, value)
        appended += record

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(
        struct.pack("<4sIIII", b"WDBC", records + len(missing), 8, 32, len(strings))
        + body + bytes(appended) + strings)
    print(f"appended {len(missing)} rows ({skipped} already stock), "
          f"entries {missing[0]['entry']}-{missing[-1]['entry']}")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    print("Bump client_patch in VERSION and run client-patch/build.ps1 -Install "
          "with the game closed.")


if __name__ == "__main__":
    main()

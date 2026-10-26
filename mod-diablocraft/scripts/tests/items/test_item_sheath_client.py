#!/usr/bin/env python3
"""The client half of the sheath (diablocraft-pru6e, after b3gs1): client-patch/dbc/Item.dbc carries the same sheath
as the server's item_template for every one of our items.

The server's values are the generated items_0022 migration (every other item of ours keeps the table's 0). The
committed Item.dbc must be what build_item.py --from-sql writes from a copy with every sheath zeroed (the production
path, run here on a scratch copy). That patch-4.MPQ carries this Item.dbc byte for byte is test_kadala_client_rows's one check.
"""
import re
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "client-patch/dbc"))
import build_item  # noqa: E402

DBC = ROOT / "client-patch/dbc/Item.dbc"
MIGRATION = ROOT / "mod-diablocraft/data/sql/db-world/updates/items_0022_item_sheath.sql"
# The base items added after 0002 (the Shaman's Ritual Mace and Totem) are sheathed by the migration that inserts them.
ADDED_MIGRATION = ROOT / "mod-diablocraft/data/sql/db-world/updates/items_0057_shaman_item_types.sql"


def server_sheaths():
    found = {}
    for path in (MIGRATION, ADDED_MIGRATION):
        for value, ids in re.findall(r"SET `sheath`=(\d+) WHERE `entry` IN \(([\d,]+)\);", path.read_text()):
            for entry in ids.split(","):
                found[int(entry)] = int(value)
    assert found, "no sheath rows in the migration"
    return found


def records(path):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 4)[0]
    return [struct.unpack_from("<IIIiiIII", data, 20 + n * 32) for n in range(count)]


def test_client_sheath_equals_the_server_for_every_item_of_ours():
    server = server_sheaths()
    rows = {row[0]: row for row in records(DBC)}
    missing = set(server) - set(rows)
    assert not missing, f"{len(missing)} sheathed items have no Item.dbc row: {sorted(missing)[:5]}"
    wrong = [(e, rows[e][7], server.get(e, 0)) for e in rows if e > build_item.LAST_STOCK_ITEM
             and rows[e][7] != server.get(e, 0)]
    assert not wrong, f"{len(wrong)} rows differ (entry, client, server): {wrong[:5]}"
    assert len({v for v in server.values()}) > 1


def test_committed_dbc_is_the_from_sql_output():
    committed = DBC.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "Item.dbc"
        body = bytearray(committed)
        for n in range(struct.unpack_from("<I", body, 4)[0]):
            if struct.unpack_from("<I", body, 20 + n * 32)[0] > build_item.LAST_STOCK_ITEM:
                struct.pack_into("<I", body, 20 + n * 32 + 28, 0)
        scratch.write_bytes(bytes(body))
        output, build_item.OUTPUT = build_item.OUTPUT, scratch
        try:
            mirrors = ROOT / "mod-diablocraft/data/generated"
            build_item.sync_from_sql([mirrors / "item_template.sql", mirrors / "unidentified_shells.sql"])
        finally:
            build_item.OUTPUT = output
        assert scratch.read_bytes() == committed


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok", name)

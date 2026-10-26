"""diablocraft-ywkp (Kadala Part 9): the client's Item.dbc rows for the set caches.

The client draws a bag or vendor icon only from its own Item.dbc, which has no row for 101114 to 101140 and 101146 to 101175 until the
patch carries them. Each check reads the shipped file and compares it with the caches the sheet lists now
(set_caches.csv) and with the migration's item_template rows, not with what the builder read. The committed
patch-4.MPQ carrying the same Item.dbc is test_kadala_client_rows's one check.
"""
import csv
import struct
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DBC = REPO / "client-patch/dbc"
sys.path.insert(0, str(DBC))
import build_item as item  # noqa: E402

CACHES = item.MIGRATIONS / "set_caches_0007.sql"


def read_rows(path):
    data = path.read_bytes()
    _, records, _, size, _ = struct.unpack("<4sIIII", data[:20])
    return [struct.unpack_from("<IIIiiIII", data, 20 + n * size) for n in range(records)]


def cache_entries():
    with (REPO / "mod-diablocraft/data/d3/set_caches.csv").open(encoding="utf-8", newline="") as handle:
        return sorted(int(row["entry"]) for row in csv.DictReader(handle))


class SetCacheClientRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_rows(DBC / "Item.dbc")
        cls.by_entry = {row[0]: row for row in cls.rows}

    def test_every_cache_the_sheet_lists_has_exactly_one_row(self):
        entries = cache_entries()
        self.assertEqual(57, len(entries))
        self.assertEqual(len(self.rows), len(self.by_entry), "duplicate Item.dbc entry")
        for entry in entries:
            self.assertTrue(entry in self.by_entry, f"no Item.dbc row for cache {entry}")

    def test_a_row_is_the_migrations_item_and_its_icon_exists(self):
        migration = item.sql_item_rows(CACHES)
        self.assertEqual(cache_entries(), sorted(migration))
        displays = {r[0] for r in read_rows_display()}
        for entry, (klass, sub, sound, material, display, inventory, sheath) in migration.items():
            self.assertEqual((entry, klass, sub, sound, material, display, inventory, sheath), self.by_entry[entry])
            self.assertEqual((15, 0, 0), (klass, sub, inventory), "a cache is a plain miscellaneous item")
            self.assertTrue(display in displays, f"cache {entry}: display {display} is not in ItemDisplayInfo.dbc")

    def test_the_default_append_list_carries_the_caches(self):
        self.assertIn("set_caches_0007.sql", item.APPEND_SQL)


def read_rows_display():
    data = (DBC / "ItemDisplayInfo.dbc").read_bytes()
    _, records, _, size, _ = struct.unpack("<4sIIII", data[:20])
    return [struct.unpack_from("<I", data, 20 + n * size) for n in range(records)]


if __name__ == "__main__":
    unittest.main()

"""diablocraft-sfvq (Kadala Part 4): the client's rows for Kadala's window.

The window draws a price only from the client's ItemExtendedCost.dbc and an icon only from its Item.dbc, so each
check reads the shipped file and compares it with what the generator renders NOW (kadala.csv, kadala_entries.csv),
not with the migration the builder read. The committed patch-4.MPQ must carry the same files.
"""
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_kadala as gen

REPO = Path(__file__).resolve().parents[4]
DBC = REPO / "client-patch/dbc"
sys.path.insert(0, str(DBC))
import build_currencytypes as currency  # noqa: E402
import build_item as item  # noqa: E402
import build_itemextendedcost as cost  # noqa: E402

SHARD = 102007


def rendered_costs():
    block = cost.INSERT.search(gen.render())
    return [tuple(int(v) for v in m.split(",")) for m in cost.ROW.findall(block.group(1))]


def rendered_vendor():
    return [tuple(int(v) for v in m.split(", ")) for m in re.findall(r"^\((\d+, \d+, \d+, \d+, \d+, \d+, \d+)\)", gen.render(), re.M)]


class KadalaClientRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock, cls.stock_strings = cost.read_dbc(cost.DEFAULT_SOURCE)
        cls.shipped, cls.shipped_strings = cost.read_dbc(DBC / "ItemExtendedCost.dbc")

    def test_stock_rows_are_kept_and_the_generated_prices_are_the_only_addition(self):
        self.assertEqual(self.stock, self.shipped[:len(self.stock)])
        self.assertEqual(self.stock_strings, self.shipped_strings)
        self.assertEqual(rendered_costs(), self.shipped[len(self.stock):])

    def test_the_prices_are_the_sheet_prices_in_blood_shards(self):
        added = self.shipped[len(self.stock):]
        self.assertEqual([25, 50, 75, 100], [r[9] for r in added])
        for row in added:
            self.assertEqual(SHARD, row[4], row)
            self.assertEqual((0, 0, 0), row[1:4])  # no honor, arena points or bracket
            self.assertEqual([0] * 4, list(row[5:9]))
            self.assertEqual([0, 0, 0, 0], list(row[10:14]))

    def test_every_price_an_entry_is_sold_for_has_a_row(self):
        ids = {r[0] for r in self.shipped}
        vendor = rendered_vendor()
        self.assertEqual(17, len(vendor))
        for _npc, _slot, _item, _max, _incr, extended, _build in vendor:
            self.assertIn(extended, ids)

    def test_item_rows_cover_the_shard_and_every_mystery_entry(self):
        rows = {}
        data = (DBC / "Item.dbc").read_bytes()
        _, records, _, size, _ = struct.unpack("<4sIIII", data[:20])
        for n in range(records):
            row = struct.unpack_from("<IIIiiIII", data, 20 + n * size)
            self.assertNotIn(row[0], rows, f"duplicate Item.dbc entry {row[0]}")
            rows[row[0]] = row
        self.assertEqual((10, 0, 7045), (rows[SHARD][1], rows[SHARD][2], rows[SHARD][5]))
        entries = gen.read("kadala_entries.csv")
        self.assertEqual(17, len(entries))
        shown = {r["item_entry"]: r["name"] for r in entries}
        for line in re.findall(r"^  \((\d+), 15, 0, '((?:[^']|'')*)', (\d+),", gen.render(), re.M):
            entry, name, display = int(line[0]), line[1], int(line[2])
            self.assertEqual(shown[str(entry)], name)
            self.assertIn(entry, rows, name)
            self.assertEqual((15, 0, display, 0), (rows[entry][1], rows[entry][2], rows[entry][5], rows[entry][6]), name)

    def test_the_shard_is_a_currency_row(self):
        rows, _ = currency.read_dbc(DBC / "CurrencyTypes.dbc")
        mine = [r for r in rows if r[1] == SHARD]
        self.assertEqual([(1007, SHARD, 1, 37)], mine)

    def test_the_builder_refuses_a_collision_and_a_rerun_adds_nothing(self):
        with self.assertRaises(SystemExit):
            cost.build(self.stock, [(2997,) + (0,) * 15])
        with self.assertRaises(SystemExit):
            cost.build(self.stock, [(3000,) + (0,) * 15, (3000,) + (0,) * 15])
        rows = item.sql_item_rows(item.MIGRATIONS / "kadala_0001_vendor.sql")
        self.assertEqual(set(range(102300, 102317)), set(rows))

    def test_the_committed_archive_carries_these_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("ItemExtendedCost", "Item", "CurrencyTypes"):
                subprocess.run(["smpq", "-x", str(REPO / "client-patch/patch-4.MPQ"), f"DBFilesClient/{name}.dbc"],
                               cwd=tmp, check=True, capture_output=True)
                self.assertEqual((DBC / f"{name}.dbc").read_bytes(), (Path(tmp) / f"DBFilesClient/{name}.dbc").read_bytes(), name)


if __name__ == "__main__":
    unittest.main()

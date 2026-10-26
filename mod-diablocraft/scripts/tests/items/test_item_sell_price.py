"""diablocraft-item-base-sell-price: a vendor pays D3's base price for a base item.

Ruling 2026-10-04 (card q-1004-08, option a): "lets do a base price and then eventually we can move
to the correct price model". All 1114 base items had SellPrice 0 and the stock core refuses to buy
an item worth 0 (ItemHandler.cpp:654, SELL_ERR_CANT_SELL_ITEM), so vendors bought nothing. D3's
vendor pays floor(price / 25) (docs/research/item-sell-prices.md 2.2); this prices a base item at its
own ItemTable.Cost and nothing more.

The cost of each base item is data/d3/base_item_costs.csv (blizzless-diiis 6292f950), the 25 is the
economy.csv item_sell_divisor row, and generate_sql.render_sell_price turns both into
items_0021_item_sell_price.sql. These tests drive that production function and read what it wrote.
docs/research/item-sell-prices.csv is a frozen second source, read here and never by the generator.
"""
import csv
import pathlib
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_sql as g

MODULE = g.MODULE_ROOT
D3 = MODULE / "data" / "d3"
RESEARCH = MODULE.parent / "docs" / "research" / "item-sell-prices.csv"
HEADER = ["d3_id", "d3_gamebalance_id", "match_type", "d3_cost", "source"]
PIN = "6292f950"
D3_DIVISOR = 25
UPDATE = re.compile(r"^UPDATE `item_template` SET `SellPrice`=(\d+) WHERE `entry` IN \((\d+(?:,\d+)*)\);$")
# The three items the research states by name (item-sell-prices.md section 4.3 and the brief).
NAMED = {"Axe_1H_206": 9, "Amulet16": 35, "Unique_Helm_Set_01_p1": 576}


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


# The base items with no D3 row, each priced as the D3 item it is built like (base_item_costs.csv match_type class_peer).
PEERS = {"Shaman_RitualMace_001": "Flail_1H_201", "Shaman_Totem_001": "NecromancerTalisman_004",
         "Shaman_Unique_RitualMace_001": "Unique_Flail_1H_105_x1"}


def d3_rows():
    """The cost rows that come from D3's own tables (every row but the class-peer ones)."""
    return [row for row in rows(D3 / "base_item_costs.csv") if row["match_type"] != "class_peer"]


def prices(sql):
    """{entry: SellPrice} out of the rendered UPDATEs.

    A line that is neither a comment nor one SellPrice-only UPDATE fails here, and so does an
    entry named twice, so a test that gets this far has seen nothing but SellPrice writes."""
    found = {}
    for line in sql.splitlines():
        if not line or line.startswith("--"):
            continue
        match = UPDATE.match(line)
        if not match:
            raise AssertionError("not a SellPrice-only UPDATE: " + line[:140])
        for entry in match.group(2).split(","):
            if int(entry) in found:
                raise AssertionError(f"entry {entry} is priced twice")
            found[int(entry)] = int(match.group(1))
    return found


def by_d3_id(sql):
    entry_of = {row["d3_id"]: int(row["item_entry"]) for row in rows(D3 / "base_item_ids.csv")}
    priced = prices(sql)
    return {d3_id: priced[entry] for d3_id, entry in entry_of.items() if entry in priced}


def migration_path():
    return MODULE / "data" / "sql" / "db-world" / "updates" / g.SELL_PRICE_MIGRATION


class Tree(unittest.TestCase):
    """The real sheets copied into a temp tree, so a test can break one without touching the repo."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / "data" / "d3").mkdir(parents=True)
        (self.root / "data" / "tunables").mkdir(parents=True)
        for name in ("base_items.csv", "base_item_ids.csv", "base_item_costs.csv"):
            shutil.copyfile(D3 / name, self.root / "data" / "d3" / name)
        # 0002 is the record of which base items shipped: the frozen render covers these, the added-base migration the rest.
        updates = self.root / "data" / "sql" / "db-world" / "updates"
        updates.mkdir(parents=True)
        shutil.copyfile(MODULE / "data" / "sql" / "db-world" / "updates" / "0002_dc_base_item.sql", updates / "0002_dc_base_item.sql")
        shutil.copyfile(MODULE / "data" / "tunables" / "economy.csv", self.root / "data" / "tunables" / "economy.csv")
        self.items = self.root / "data" / "d3" / "base_items.csv"
        self.costs = self.root / "data" / "d3" / "base_item_costs.csv"
        self.economy = self.root / "data" / "tunables" / "economy.csv"
        # Tests never default to live data: everything below is read and written under the temp dir.
        for path in (self.items, self.costs, self.economy):
            self.assertTrue(path.is_relative_to(self.root), path)

    def render(self):
        return g.render_sell_price(self.items)

    def set_divisor(self, value=None):
        """Put `value` in the item_sell_divisor row's `value` cell; None removes the row."""
        with self.economy.open(encoding="utf-8", newline="") as stream:
            table = list(csv.reader(stream))
        found = [row for row in table if row[0] == "item_sell_divisor"]
        self.assertEqual(len(found), 1, "economy.csv must hold exactly one item_sell_divisor row")
        if value is None:
            table.remove(found[0])
        else:
            found[0][2] = value
        with self.economy.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream, lineterminator="\n").writerows(table)

    def edit_costs(self, change, header=HEADER):
        sheet = rows(self.costs)
        change(sheet)
        with self.costs.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, header, lineterminator="\n")
            writer.writeheader()
            writer.writerows(sheet)


class Sheet(unittest.TestCase):
    def test_one_row_per_base_item_under_the_expected_header(self):
        costs = D3 / "base_item_costs.csv"
        with costs.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(next(csv.reader(stream)), HEADER)
        listed = [row["d3_id"] for row in rows(costs)]
        self.assertEqual(sorted(listed), sorted(row["d3_id"] for row in rows(D3 / "base_items.csv")))
        self.assertEqual(len(set(listed)), len(listed), "a d3_id is listed twice")
        self.assertEqual(len(listed), 1114 + len(PEERS))

    def test_every_cost_is_a_whole_number_and_names_its_source_and_pin(self):
        for row in d3_rows():
            self.assertRegex(row["d3_cost"], r"^[0-9]+$", row)
            self.assertIn(PIN, row["source"], row)
            self.assertIn("GameBalance/Items_", row["source"], row)
            self.assertIn(row["match_type"], ("exact", "patch_ancestor"), row)

    def test_a_torment_base_item_is_priced_as_the_d3_item_it_names(self):
        # The Shaman's Ritual Mace, Totem and legendary Ritual Mace have no D3 row (xnrvn.3): each names its class peer,
        # and its cost is that D3 row's cost, read from the same sheet.
        peers = [row for row in rows(D3 / "base_item_costs.csv") if row["match_type"] == "class_peer"]
        self.assertEqual(sorted(row["d3_id"] for row in peers), sorted(PEERS))
        d3 = {row["d3_id"]: row for row in d3_rows()}
        for row in peers:
            self.assertEqual(row["d3_gamebalance_id"], PEERS[row["d3_id"]], row)
            self.assertEqual(row["d3_cost"], d3[row["d3_gamebalance_id"]]["d3_cost"], row)
            self.assertTrue(row["source"].startswith("Torment: no D3 row"), row)
            self.assertNotIn(row["d3_id"], d3)

    def test_the_costs_are_the_research_sheets_costs(self):
        research = {row["d3_id"]: row for row in rows(RESEARCH)}
        mine = {row["d3_id"]: row for row in d3_rows()}
        self.assertEqual(mine.keys(), research.keys())
        for d3_id, row in mine.items():
            for column in ("d3_gamebalance_id", "match_type", "d3_cost"):
                self.assertEqual(row[column], research[d3_id][column], (d3_id, column))

    def test_the_divisor_row_carries_d3s_published_25(self):
        # d3_value is what D3 published; `value` is the designer's override and is not asserted here.
        found = [row for row in rows(MODULE / "data" / "tunables" / "economy.csv") if row["name"] == "item_sell_divisor"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["d3_value"], str(D3_DIVISOR))


class Prices(Tree):
    def test_every_base_item_sells_for_its_cost_over_the_divisor_and_none_for_nothing(self):
        sql, count = self.render()
        cost = {row["d3_id"]: int(row["d3_cost"]) for row in rows(self.costs) if row["match_type"] != "class_peer"}
        generated = by_d3_id(sql)
        self.assertEqual(count, 1114)
        self.assertEqual(generated.keys(), cost.keys())
        for d3_id, price in generated.items():
            self.assertIsNotNone(price, f"{d3_id} has no SellPrice UPDATE")
            self.assertEqual(price, cost[d3_id] // D3_DIVISOR, d3_id)
            if price == 0:
                self.assertLess(cost[d3_id], D3_DIVISOR, f"{d3_id} sells for nothing but D3's cost is {cost[d3_id]}")

    def test_the_generated_prices_are_the_frozen_researchs(self):
        sql, _ = self.render()
        generated = by_d3_id(sql)
        research = {row["d3_id"]: int(row["d3_sell_price_base"]) for row in rows(RESEARCH)}
        self.assertEqual(generated, research)

    def test_a_torment_base_item_sells_for_its_peers_cost_over_the_divisor(self):
        # The frozen render leaves the added base items out; the added-base migration prices them from the same sheet.
        wanted = {entry: int(row["d3_cost"]) // D3_DIVISOR
                  for row in rows(D3 / "base_item_costs.csv") if row["match_type"] == "class_peer"
                  for entry in [int(next(r["item_entry"] for r in rows(D3 / "base_item_ids.csv") if r["d3_id"] == row["d3_id"]))]}
        added = g.added_entries(D3 / "base_items.csv")
        self.assertEqual(set(wanted), added)
        sql = g.render_added_base_items(D3 / "base_items.csv")[0]
        priced = {}
        for price, found in re.findall(r"SET `SellPrice`=(\d+) WHERE `entry` IN \(([\d,]+)\);", sql):
            for entry in found.split(","):
                priced[int(entry)] = int(price)
        self.assertEqual(priced, wanted)

    def test_the_named_examples(self):
        generated = by_d3_id(self.render()[0])
        for d3_id, price in NAMED.items():
            self.assertEqual(generated[d3_id], price, d3_id)

    def test_only_sell_price_is_written_never_buy_price(self):
        sql, _ = self.render()
        statements = [line for line in sql.splitlines() if line and not line.startswith("--")]
        self.assertTrue(statements)
        self.assertFalse([line[:80] for line in statements if "BuyPrice" in line])
        # prices() refuses any line that is not a comment or one SellPrice-only UPDATE.
        self.assertEqual(len(prices(sql)), 1114)

    def test_changing_the_divisor_row_changes_the_output(self):
        before = by_d3_id(self.render()[0])
        self.set_divisor("50")
        after = by_d3_id(self.render()[0])
        cost = {row["d3_id"]: int(row["d3_cost"]) for row in rows(self.costs) if row["match_type"] != "class_peer"}
        self.assertNotEqual(before, after)
        self.assertEqual(after, {d3_id: value // 50 for d3_id, value in cost.items()})
        self.assertEqual(after["Amulet16"], 17)
        # Blank again: the row falls back to D3's published 25.
        self.set_divisor("")
        self.assertEqual(by_d3_id(self.render()[0]), before)

    def test_a_missing_or_unusable_divisor_is_refused_not_defaulted(self):
        self.set_divisor(None)
        with self.assertRaisesRegex(ValueError, "item_sell_divisor"):
            self.render()

    def test_a_zero_divisor_is_refused(self):
        self.set_divisor("0")
        with self.assertRaisesRegex(ValueError, "item_sell_divisor"):
            self.render()

    def test_every_update_names_a_template_row_the_applied_render_created(self):
        # 0002_dc_item_template is applied and frozen: its rows are the ones the UPDATEs must hit.
        applied = MODULE / "data" / "sql" / "db-world" / "updates" / "0002_dc_item_template.sql"
        entries = {int(entry) for entry, *_ in g.TEMPLATE_ROW.findall(applied.read_text(encoding="utf-8"))}
        self.assertEqual(len(entries), 1114)
        self.assertEqual(set(prices(self.render()[0])), entries)

    def test_the_committed_migration_is_what_the_sheets_render(self):
        sql, _ = g.render_sell_price(D3 / "base_items.csv")
        self.assertEqual(migration_path().read_text(encoding="utf-8"), sql,
                         "regenerate: python3 mod-diablocraft/scripts/generate/tooling/generate_sql.py")


class Rejections(Tree):
    """Every way the cost sheet can be wrong, each its own defect; the fixture is the real data."""

    def test_the_fixture_renders_before_anything_is_broken(self):
        self.assertEqual(self.render()[0], g.render_sell_price(D3 / "base_items.csv")[0])

    def test_a_base_item_with_no_cost_is_rejected(self):
        dropped = []
        self.edit_costs(lambda sheet: dropped.append(sheet.pop(400)))
        with self.assertRaisesRegex(g.DataError, r"no d3_cost for .*%s" % dropped[0]["d3_id"]):
            self.render()

    def test_a_cost_for_something_that_is_not_a_base_item_is_rejected(self):
        self.edit_costs(lambda sheet: sheet.append(dict(sheet[0], d3_id="Not_A_Base_Item")))
        with self.assertRaisesRegex(g.DataError, "not a base item"):
            self.render()

    def test_a_d3_id_listed_twice_is_rejected(self):
        self.edit_costs(lambda sheet: sheet.append(dict(sheet[7])))
        with self.assertRaisesRegex(g.DataError, "duplicate d3_id"):
            self.render()

    def test_a_cost_that_is_not_a_whole_number_of_zero_or_more_is_rejected(self):
        for bad in ("", "abc", "12.5", "-25"):
            with self.subTest(cost=bad):
                self.edit_costs(lambda sheet: sheet[3].update(d3_cost=bad))
                with self.assertRaisesRegex(g.DataError, "d3_cost"):
                    self.render()

    def test_a_cost_with_no_source_is_rejected(self):
        self.edit_costs(lambda sheet: sheet[3].update(source=" "))
        with self.assertRaisesRegex(g.DataError, "source"):
            self.render()

    def test_a_different_header_is_rejected(self):
        self.edit_costs(lambda sheet: [row.update(cost=row.pop("d3_cost")) for row in sheet],
                        header=["d3_id", "d3_gamebalance_id", "match_type", "source", "cost"])
        with self.assertRaisesRegex(g.DataError, "expected columns"):
            self.render()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Sheathed weapons hang on the character (diablocraft-b3gs1; generate_sql.py SHEATH, render_sheath).

Every weapon and off-hand base item gets a non-zero item_template.sheath and every other base item none; the committed
migration is the render; and every SHEATH value is rederived from the stock items on the fixture's world database (the
commonest non-zero sheath of that class, subclass and InventoryType, else of that class and InventoryType), so a value
typed wrong, or a kind the generator emits with no value, fails here. The stock check needs the fixture mysqld and is
skipped without it.
"""
import collections
import csv
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import generate_sql as G  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
BASE = MODULE / "data/d3/base_items.csv"
MIGRATION = MODULE / "data/sql/db-world/updates" / G.SHEATH_MIGRATION


def base_rows():
    with BASE.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def test_every_weapon_and_off_hand_has_a_sheath_and_nothing_else_does():
    sql, count = G.render_sheath(BASE)
    assert MIGRATION.read_text() == sql
    written = {}
    for value, ids in re.findall(r"SET `sheath`=(\d+) WHERE `entry` IN \(([\d,]+)\);", sql):
        for entry in ids.split(","):
            assert int(entry) not in written, entry
            written[int(entry)] = int(value)
    rows = base_rows()
    entries = G.read_base_item_ids(BASE.with_name("base_item_ids.csv"), {r["d3_id"] for r in rows})
    # The frozen migration covers the base items 0002 shipped; the added-base migration sheaths its own (below).
    shipped = G.shipped_entries(BASE)
    hands = {entries[r["d3_id"]]: r for r in rows
             if r["slot"] in ("onehand", "twohand", "offhand") and entries[r["d3_id"]] in shipped}
    assert set(written) == set(hands) and count == len(hands) == 490, (count, len(hands))
    assert all(value > 0 for value in written.values())
    for entry, row in hands.items():
        assert written[entry] == G.SHEATH[G.classify(row, BASE, 0, row)], row["d3_id"]
    # the named kinds of the brief: a two-hander on the back, a one-hander at the hip, a staff, a shield, an off-hand
    by_type = {row["type"]: written[entry] for entry, row in hands.items()}
    assert (by_type["Two-Handed Sword"], by_type["Sword"], by_type["Staff"], by_type["Shield"], by_type["Source"]) == (1, 3, 2, 4, 7)


def test_an_added_weapon_and_off_hand_are_sheathed_by_the_added_migration():
    # The Shaman's Ritual Mace hangs as a mace at the hip and her Totem as an off-hand (diablocraft-xnrvn.3).
    sql, _ = G.render_added_base_items(BASE)
    by_type = {}
    rows = base_rows()
    entries = G.read_base_item_ids(BASE.with_name("base_item_ids.csv"), {r["d3_id"] for r in rows})
    for value, ids in re.findall(r"SET `sheath`=(\d+) WHERE `entry` IN \(([\d,]+)\);", sql):
        for entry in ids.split(","):
            by_type[int(entry)] = int(value)
    added = {entries[r["d3_id"]]: r for r in rows if entries[r["d3_id"]] in G.added_entries(BASE)}
    assert set(by_type) == set(added) and added, (by_type, added)
    for entry, row in added.items():
        assert by_type[entry] == G.SHEATH[G.classify(row, BASE, 0, row)], row["d3_id"]
    assert {added[e]["type"]: v for e, v in by_type.items()} == {"Ritual Mace": 3, "Totem": 7}


def test_every_value_is_the_stock_items():
    mysql, defaults = fixture_db.mysql_and_defaults([])
    query = ("SELECT class, subclass, InventoryType, sheath, COUNT(*) FROM item_template WHERE entry < 60000 AND sheath > 0 "
             "GROUP BY class, subclass, InventoryType, sheath")
    done = subprocess.run([mysql, "--defaults-file=" + str(defaults), "--no-login-paths", "-N", "-B", "acore_world", "-e", query],
                          capture_output=True, text=True)
    if done.returncode != 0:
        print("SKIP the fixture mysqld is down (fixture_mysql.sh start)")
        return
    exact, by_type = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for line in done.stdout.splitlines():
        item_class, subclass, inventory, sheath, count = map(int, line.split("\t"))
        exact[(item_class, subclass, inventory)][sheath] += count
        by_type[(item_class, inventory)][sheath] += count
    assert sum(exact[(2, 7, 13)].values()) > 100, "the fixture holds no stock weapons"
    emitted = {G.classify(r, BASE, 0, r) for r in base_rows() if r["slot"] in ("onehand", "twohand", "offhand")}
    assert emitted == set(G.SHEATH), emitted ^ set(G.SHEATH)
    for kind, value in G.SHEATH.items():
        stock = exact[kind] or by_type[(kind[0], kind[2])]
        assert stock.most_common(1)[0][0] == value, (kind, value, stock)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)

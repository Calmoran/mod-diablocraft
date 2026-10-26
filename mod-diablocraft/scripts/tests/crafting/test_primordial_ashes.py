"""diablocraft-wpt7l.1 - Kanai's Cube bead 1: Primordial Ashes as a ledger material, entry 102013.

What this proves, and what it does not:

  * The sheet (`data/d3/account_economy.csv`) carries Primordial Ashes as a material right after the five act
    reagents, under the name both D3 sheets spend and pay it in (`cube_recipes.csv` the Primal upgrade's 100,
    `rarity_tiers.csv` a Primal's salvage of 55), a second source.
  * The generated world SQL is the new migration 0005, byte for byte; the reagents' 0004 is left without it.
    Replayed twice over 0004 on a disposable MySQL it writes the ledger kind row and the currency item row
    (class 10, BagFamily 8192, the generator's icon, which the client's ItemDisplayInfo.dbc names
    inv_elemental_mote_fire01).
  * The client builders list it (CurrencyTypes row 1013, Item.dbc reading 0005), and both Lua lists the
    Materials panel reads hold it with the sheet's name.
  * NOT covered: the committed DBC files and patch-4.MPQ (test_currencytypes.py and test_kadala_client_rows.py
    check those), where Ashes come from (salvage by quality is Cube bead 2), and the panel's look in game.
"""
import csv
import pathlib
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_account_economy_sql import MYSQL, ROOT, isolated

MODULE = ROOT / "mod-diablocraft"
sys.path.insert(0, str(ROOT / "client-patch/dbc"))
import build_currencytypes  # noqa: E402
import build_item  # noqa: E402
import generate_account_economy as generator  # noqa: E402

ASHES = 102013
UPDATES = MODULE / "data/sql/db-world/updates"
MIGRATION = UPDATES / "account_economy_0005_primordial_ashes.sql"
REAGENTS = UPDATES / "account_economy_0004_act_reagents.sql"


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print("PASS " + name, flush=True)


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def sheet():
    return {int(r["item_entry"]): r for r in rows(MODULE / "data/d3/account_economy.csv")}


def icon_name(display):
    data = (ROOT / "client-patch/dbc/ItemDisplayInfo.dbc").read_bytes()
    _, count, fields, size, _ = struct.unpack("<4sIIII", data[:20])
    strings = data[20 + count * size:]
    for index in range(count):
        record = struct.unpack_from(f"<{fields}I", data, 20 + index * size)
        if record[0] == display:
            return strings[record[5]:strings.index(b"\0", record[5])].decode().lower()
    return None


def test_data():
    kinds = sheet()
    row = kinds.get(ASHES, {})
    check(row.get("kind") == "material" and row.get("copper_per_item") == "0", "Primordial Ashes are a ledger material")
    check(sorted(kinds)[-2:] == [102012, ASHES], "the entry is the next after the act reagents")
    recipes = (MODULE / "data/d3/cube_recipes.csv").read_text(encoding="utf-8")
    tiers = (MODULE / "data/d3/rarity_tiers.csv").read_text(encoding="utf-8")
    check(f"100 {row.get('name')} +" in recipes and f"55 {row.get('name')} (" in tiers,
          "the name is the one the Cube spends and a Primal's salvage pays")
    check(generator.CURRENCY_ITEMS.get(ASHES, (0,))[0] == 38611 and icon_name(38611) == "inv_elemental_mote_fire01",
          "the currency item row draws the stock fire-mote icon")
    check(generator.WORLD_LEDGER_MIGRATION == MIGRATION.name, "the generator writes the new migration 0005")
    world = (MODULE / "data/generated/account_economy_world.sql").read_text(encoding="utf-8")
    check(world == MIGRATION.read_text(encoding="utf-8"), "the generated mirror and the migration are the same file")
    check(generator.render(MODULE)[0] == world, "the committed SQL is the generator's render of the sheet")
    check(str(ASHES) not in REAGENTS.read_text(encoding="utf-8"), "the reagents' 0004 is left as it was")


def test_client_lists():
    kinds = sheet()
    currencies = {entry: row_id for row_id, entry, _ in build_currencytypes.CURRENCIES}
    check(currencies.get(ASHES) == 1013, "CurrencyTypes row 1013")
    check(MIGRATION.name in build_item.APPEND_SQL, "Item.dbc appends the new migration's row")
    check(build_item.sql_item_rows(MIGRATION)[ASHES][4] == generator.CURRENCY_ITEMS[ASHES][0],
          "Item.dbc takes the generator's icon")
    server = (MODULE / "lua/aio/dc_account.lua").read_text(encoding="utf-8")
    listed = re.search(r"^A\.MATERIALS = \{([^}]*)\}", server, re.M).group(1)
    check(ASHES in {int(n) for n in re.findall(r"\d+", listed)}, "the server reader lists it")
    client = (ROOT / "client-patch/addons/Torment/Economy.lua").read_text(encoding="utf-8")
    panel = re.search(r"^local CURRENCIES = \{(.*?)^\}", client, re.M | re.S).group(1)
    shown = {int(e): n for e, n in re.findall(r'entry = (\d+), name = "([^"]*)"', panel)}
    check(shown.get(ASHES) == kinds[ASHES]["name"], "the Materials panel lists it by its sheet name")


def test_mysql(port):
    base = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root"]
    subprocess.run(base, input="CREATE DATABASE primordial_ashes CHARACTER SET utf8mb4;", text=True, check=True)

    def sql(text):
        done = subprocess.run(base + ["--batch", "--raw", "--skip-column-names", "--database=primordial_ashes"],
                              input=text, text=True, capture_output=True)
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.strip()

    sql("CREATE TABLE item_template (entry INT UNSIGNED PRIMARY KEY, class TINYINT, subclass TINYINT, name VARCHAR(255), "
        "displayid INT, Quality TINYINT, Flags INT UNSIGNED, BuyCount TINYINT, BuyPrice BIGINT, SellPrice INT, "
        "InventoryType TINYINT, maxcount INT, stackable INT, BagFamily INT, Material TINYINT, bonding TINYINT, "
        "ItemLevel SMALLINT, description VARCHAR(255)) ENGINE=InnoDB;"
        "INSERT INTO item_template (entry, name) VALUES (102006, 'Gold Bar');")
    sql(REAGENTS.read_text(encoding="utf-8"))
    world = MIGRATION.read_text(encoding="utf-8")
    sql(world)
    sql(world)
    name = sheet()[ASHES]["name"]
    row = sql(f"SELECT class, name, displayid, stackable, BagFamily, BuyPrice, SellPrice FROM item_template WHERE entry={ASHES}")
    check(row == f"10\t{name}\t38611\t2147483647\t8192\t0\t0", "the migration replays over 0004 and writes the currency item row")
    check(sql(f"SELECT kind, copper_per_item FROM dc_account_economy_kind WHERE item_entry={ASHES}") == "material\t0",
          "and the ledger kind row")
    check(sql("SELECT COUNT(*) FROM dc_account_economy_kind WHERE kind='material'") == "13", "13 materials in all")
    check(sql("SELECT displayid FROM item_template WHERE entry=102012") == "23731", "the reagent rows are unchanged")
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_data()
    test_client_lists()
    isolated(test_mysql)

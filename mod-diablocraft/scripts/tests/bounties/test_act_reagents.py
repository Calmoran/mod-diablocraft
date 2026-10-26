"""diablocraft-dm9vg.3 - Bounties W3: the five act reagents as ledger materials 102008-102012.

What this proves, and what it does not:

  * The sheet (`data/d3/account_economy.csv`) carries the five, as materials, in D3's act order, and their
    names are the cube sheet's own five columns (`data/d3/cube_costs.csv`), a second source.
  * The generated world SQL is the new migration, byte for byte, and replayed twice on a disposable MySQL it
    writes a ledger kind row and a currency item row for each (class 10, BagFamily 8192, the icon the
    generator names). The applied 0003 migration is left as it was.
  * The client builders list them (CurrencyTypes rows 1008-1012, Item.dbc reading the new migration), and both
    Lua lists the Materials panel reads hold them with the sheet's names.
  * The Blacksmith's bounty recipes stay off: every p2_ActBountyReagent cost row still maps to entry 0
    (brief: the recipes are their own beads).
  * NOT covered: the committed DBC files and patch-4.MPQ (test_kadala_client_rows.py checks those), and the
    panel's look in game (the test sheet's Checks).
"""
import csv
import pathlib
import re
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

REAGENTS = range(102008, 102013)
MIGRATION = MODULE / "data/sql/db-world/updates/account_economy_0004_act_reagents.sql"


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print("PASS " + name, flush=True)


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def sheet():
    return {int(r["item_entry"]): r for r in rows(MODULE / "data/d3/account_economy.csv")}


def test_data():
    kinds = sheet()
    check(all(e in kinds and kinds[e]["kind"] == "material" and kinds[e]["copper_per_item"] == "0" for e in REAGENTS),
          "the five are ledger materials")
    check(sorted(e for e in kinds if e > 102007)[:5] == list(REAGENTS), "they follow the Blood Shard")
    cube = next(csv.reader((MODULE / "data/d3/cube_costs.csv").open(encoding="utf-8")))
    columns = cube[cube.index("khanduran_rune"):cube.index("westmarch_holy_water") + 1]
    names = [kinds[e]["name"].lower().replace(" ", "_") for e in REAGENTS]
    check(names == columns, f"names and act order match the cube sheet: {columns}")
    check(sorted(e for e in generator.CURRENCY_ITEMS if e in REAGENTS) == list(REAGENTS),
          "each has a generated currency item row")
    # The mirror follows the newest ledger migration (0005 since Primordial Ashes, Kanai's Cube 1); 0004 keeps the five.
    newest = MIGRATION.with_name(generator.WORLD_LEDGER_MIGRATION)
    check(newest.name > MIGRATION.name, "the generator writes a migration after 0004, never into it")
    world = (MODULE / "data/generated/account_economy_world.sql").read_text(encoding="utf-8")
    check(world == newest.read_text(encoding="utf-8"), "the generated mirror and the newest migration are the same file")
    check(generator.render(MODULE)[0] == world, "the committed SQL is the generator's render of the sheet")
    blacksmith = [r for r in rows(MODULE / "data/d3/blacksmith_catalog_materials.csv")
                  if r["d3_id"].startswith("p2_ActBountyReagent_")]
    check(len(blacksmith) == 140 and all(r["item_entry"] == "0" for r in blacksmith),
          "the 140 Blacksmith reagent cost rows stay unmapped (recipes off)")


def test_client_lists():
    kinds = sheet()
    currencies = {entry: row_id for row_id, entry, _ in build_currencytypes.CURRENCIES}
    check([currencies.get(e) for e in REAGENTS] == list(range(1008, 1013)), "CurrencyTypes rows 1008-1012")
    check(MIGRATION.name in build_item.APPEND_SQL, "Item.dbc appends the new migration's rows")
    dbc_rows = build_item.sql_item_rows(MIGRATION)
    check(all(dbc_rows[e][4] == generator.CURRENCY_ITEMS[e][0] for e in REAGENTS), "Item.dbc takes the generator's icons")
    server = (MODULE / "lua/aio/dc_account.lua").read_text(encoding="utf-8")
    listed = re.search(r"^A\.MATERIALS = \{([^}]*)\}", server, re.M).group(1)
    check(set(REAGENTS) <= {int(n) for n in re.findall(r"\d+", listed)}, "the server reader lists them")
    client = (ROOT / "client-patch/addons/Torment/Economy.lua").read_text(encoding="utf-8")
    panel = re.search(r"^local CURRENCIES = \{(.*?)^\}", client, re.M | re.S).group(1)
    shown = {int(e): n for e, n in re.findall(r'entry = (\d+), name = "([^"]*)"', panel)}
    check(all(shown.get(e) == kinds[e]["name"] for e in REAGENTS), "the Materials panel lists them by their sheet names")


def test_mysql(port):
    base = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root"]
    subprocess.run(base, input="CREATE DATABASE act_reagents CHARACTER SET utf8mb4;", text=True, check=True)

    def sql(text):
        done = subprocess.run(base + ["--batch", "--raw", "--skip-column-names", "--database=act_reagents"],
                              input=text, text=True, capture_output=True)
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.strip()

    sql("CREATE TABLE item_template (entry INT UNSIGNED PRIMARY KEY, class TINYINT, subclass TINYINT, name VARCHAR(255), "
        "displayid INT, Quality TINYINT, Flags INT UNSIGNED, BuyCount TINYINT, BuyPrice BIGINT, SellPrice INT, "
        "InventoryType TINYINT, maxcount INT, stackable INT, BagFamily INT, Material TINYINT, bonding TINYINT, "
        "ItemLevel SMALLINT, description VARCHAR(255)) ENGINE=InnoDB;"
        "INSERT INTO item_template (entry, name) VALUES (102006, 'Gold Bar');")
    sql((MODULE / "data/sql/db-world/updates/account_economy_0003_blood_shards.sql").read_text(encoding="utf-8"))
    world = MIGRATION.read_text(encoding="utf-8")
    sql(world)
    sql(world)
    kinds = sheet()
    for entry in REAGENTS:
        row = sql(f"SELECT class, name, displayid, stackable, BagFamily, BuyPrice, SellPrice FROM item_template WHERE entry={entry}")
        check(row == f"10\t{kinds[entry]['name']}\t{generator.CURRENCY_ITEMS[entry][0]}\t2147483647\t8192\t0\t0",
              f"{kinds[entry]['name']}: the migration replays over 0003 and writes its currency item row")
    check(sql("SELECT COUNT(*) FROM dc_account_economy_kind WHERE kind='material' AND item_entry BETWEEN 102008 AND 102012") == "5",
          "and the five ledger kind rows")
    check(sql("SELECT displayid FROM item_template WHERE entry=102007") == "7045", "the Blood Shard row is unchanged")
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_data()
    test_client_lists()
    isolated(test_mysql)

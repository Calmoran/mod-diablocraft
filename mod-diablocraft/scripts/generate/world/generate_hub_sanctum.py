"""Generate the Sanctum of Torment rows: Yogg-Saron's arena as open map 750 (diablocraft-ugfc).

One source, data/d3/world_sanctum_dbc.csv, drives both sides in one run:

* client: Map.dbc, WorldMapArea.dbc, Light.dbc, AreaTable.dbc, DungeonMap.dbc and DungeonMapChunk.dbc in
  client-patch/dbc, each written from the stock file with rows cloned or renamed (append-only: every stock row is
  kept byte for byte). The last two are the world map's floors (diablocraft-bk308): Ulduar's map is drawn per floor,
  and the client finds the floor by map and WMO group, so map 750 needs Ulduar's rows of both under its own id;
* server: the matching world_NNNN migration, the `map_dbc` and `areatable_dbc` rows of the same two files (the
  core loads the binary DBC and then overlays the table, DBCStores.cpp). The server's own DBC files stay stock.
  It needs no WorldMapArea or Light row: it reads the first only for `.gps` and `.go zonexy` and the second only
  for a script's light override, and none overrides on map 750. It never reads DungeonMap or DungeonMapChunk.

A row is a clone of `source_id` with the sheet's fields set; a row whose id equals its source is a rename in place.
A clone whose id already exists in the stock file is a collision and the run stops, unless that row is exactly
what the sheet would build, so rerunning over our own output is a no-op.

    python3 mod-diablocraft/scripts/generate/world/generate_hub_sanctum.py [--stock-dir DIR]

The stock DBCs default to the server's extracted copies. The client files are coupled to the migration
(applied_migrations.py): once world_0030 is applied, a changed sheet needs a new migration, not an edit.
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration  # noqa: E402
from dbc_store import Store, schema, sql_value  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
SOURCE = MODULE / "data/d3/world_sanctum_dbc.csv"
STOCK_DIR = ROOT / "azerothcore-wotlk/build/server/data/dbc"
CLIENT_DIR = ROOT / "client-patch/dbc"
MIGRATION = MODULE / "data/sql/db-world/updates/world_0030_sanctum_map.sql"
OPEN_RIFT_SOURCE = MODULE / "data/d3/world_open_rift_dbc.csv"  # the layer generate_open_rift_map.py adds on top

# DBC file -> (the core's table for it, whether the server needs the row).
TABLES = {
    "Map": ("map_dbc", True),
    "WorldMapArea": ("worldmaparea_dbc", False),
    "Light": ("light_dbc", False),
    "AreaTable": ("areatable_dbc", True),
    "DungeonMap": (None, False),
    "DungeonMapChunk": (None, False),
    "WorldMapOverlay": ("worldmapoverlay_dbc", False),  # the open-rift layer's alone (zone fog, diablocraft-y0gjt)
}
# The client-only files the core has no table (and no schema file) for: the 3.3.5a columns, all 4 bytes wide.
COLUMNS = {
    "DungeonMap": [("ID", "int", ""), ("MapID", "int", ""), ("FloorIndex", "int", ""), ("MinX", "float", ""),
                   ("MaxX", "float", ""), ("MinY", "float", ""), ("MaxY", "float", ""), ("ParentWorldMapID", "int", "")],
    "DungeonMapChunk": [("ID", "int", ""), ("MapID", "int", ""), ("WmoGroupID", "int", ""), ("DungeonMapID", "int", ""),
                        ("MinZ", "float", "")],
}


class SanctumError(Exception):
    pass


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SanctumError(f"{path}: no rows")
    return rows


def records(rows):
    """{(table, id): (source_id, {field: raw value})}, in file order."""
    out = {}
    for line, row in enumerate(rows, start=2):
        table = (row.get("table") or "").strip()
        if table not in TABLES:
            raise SanctumError(f"world_sanctum_dbc.csv:{line}: table {table!r} is not one of {sorted(TABLES)}")
        try:
            key = (table, int(row["id"]))
            source = int(row["source_id"])
        except (TypeError, ValueError):
            raise SanctumError(f"world_sanctum_dbc.csv:{line}: id and source_id are integers") from None
        field = (row.get("field") or "").strip()
        if not field or not row.get("value"):
            raise SanctumError(f"world_sanctum_dbc.csv:{line}: field and value are required")
        have_source, fields = out.setdefault(key, (source, {}))
        if have_source != source:
            raise SanctumError(f"world_sanctum_dbc.csv:{line}: {table} {key[1]} has two different source ids")
        if field in fields:
            raise SanctumError(f"world_sanctum_dbc.csv:{line}: {table} {key[1]} sets {field} twice")
        fields[field] = row["value"]
    return out


def typed(column, raw, where):
    name, kind, flags = column
    try:
        if kind in ("varchar", "text"):
            return raw
        if kind == "float":
            return float(raw)
        return int(raw)
    except ValueError:
        raise SanctumError(f"{where}: {name} is {kind} and {raw!r} is not") from None


def columns(table):
    return COLUMNS.get(table) or schema(ROOT, TABLES[table][0])


def stock_path(stock_dir, table):
    stock = Path(stock_dir) / f"{table}.dbc.stock"
    return stock if stock.is_file() else Path(stock_dir) / f"{table}.dbc"


def build_table(table, wanted, stock_dir):
    """(Store, [row dicts that are ours]) for one DBC."""
    columns_ = columns(table)
    names = [c[0] for c in columns_]
    path = stock_path(stock_dir, table)
    if not path.is_file():
        raise SanctumError(f"{path}: not found; pass --stock-dir with the stock extracted DBCs")
    store = Store(path.read_bytes(), columns_)
    ours = []
    for (_, row_id), (source_id, fields) in wanted.items():
        where = f"{table} {row_id}"
        unknown = sorted(set(fields) - set(names[1:]))
        if unknown:
            raise SanctumError(f"{where}: {unknown} are not columns of {table}")
        if source_id not in store.rows:
            raise SanctumError(f"{path.name} has no row {source_id} to clone for {where}")
        values = store.decode(source_id)
        values["ID"] = row_id
        for field, raw in fields.items():
            values[field] = typed(columns_[names.index(field)], raw, where)
        if row_id in store.rows and row_id != source_id and store.decode(row_id) != values:
            raise SanctumError(f"{path.name} already has a different row {row_id}; refusing to overwrite it")
        store.encode(values)
        ours.append(values)
    return store, ours


def changed_stock_rows(table, stock_dir, store):
    """The ids of stock rows that are not in the output byte for byte."""
    stock = Store(stock_path(stock_dir, table).read_bytes(), store.columns)
    return sorted(k for k, v in stock.rows.items() if store.rows.get(k) != v)


def migration_sql(server_rows):
    lines = ["-- Generated by generate_hub_sanctum.py from data/d3/world_sanctum_dbc.csv (diablocraft-ugfc).",
             "-- Overlays for the Sanctum of Torment, Yogg-Saron's arena as open map 750: the core reads the binary DBC",
             "-- and then these tables, so the server sees the same Map and AreaTable rows the client's patch carries.",
             "SET NAMES utf8mb4;"]
    for table, rows, columns in server_rows:
        sql_table = TABLES[table][0]
        names = [c[0] for c in columns]
        lines.append("DELETE FROM `%s` WHERE `ID` IN (%s);" % (sql_table, ",".join(str(r["ID"]) for r in rows)))
        lines.append("INSERT INTO `%s` (%s) VALUES\n%s;" % (
            sql_table, ",".join(f"`{n}`" for n in names),
            ",\n".join("(" + ",".join(sql_value(r[n]) for n in names) + ")" for r in rows)))
    return "\n".join(lines) + "\n"


def generate(source, stock_dir):
    """({DBC file name: bytes}, migration sql). Writes nothing; both paths are the caller's."""
    wanted = records(read_rows(source))
    outputs, server_rows = {}, []
    for table in TABLES:
        mine = {k: v for k, v in wanted.items() if k[0] == table}
        if not mine:
            continue
        store, ours = build_table(table, mine, stock_dir)
        renamed = {row for (_, row), (src, _) in mine.items() if row == src}
        lost = set(changed_stock_rows(table, stock_dir, store)) - renamed
        if lost:
            raise SanctumError(f"{table}.dbc: stock rows {sorted(lost)} changed that should not have")
        outputs[f"{table}.dbc"] = store.bytes()
        if TABLES[table][1]:
            server_rows.append((table, ours, store.columns))
    return outputs, migration_sql(server_rows)


def emit(module_root, migration, client_dir, outputs, sql):
    """Write the migration, then the client files coupled to it; False when the coupling held them back."""
    write_migration(module_root, migration, sql)
    return write_coupled_outputs(module_root, migration, sql,
                                 [(Path(client_dir) / name, data) for name, data in outputs.items()],
                                 label="Sanctum of Torment client DBCs")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stock-dir", default=str(STOCK_DIR), help="folder with the stock extracted DBCs")
    args = parser.parse_args(argv)
    if OPEN_RIFT_SOURCE.is_file():
        # The client DBCs are single files: a Sanctum-only render would drop the later layer's rows.
        return "generate_hub_sanctum: the client DBCs carry a later layer (open-world rifts); run generate_open_rift_map.py, which builds this layer first"
    try:
        outputs, sql = generate(SOURCE, args.stock_dir)
    except SanctumError as error:
        return f"generate_hub_sanctum: {error}"
    if not emit(MODULE, MIGRATION, CLIENT_DIR, outputs, sql):
        return "generate_hub_sanctum: the client DBCs were held back (see the warning above)"
    for name, data in outputs.items():
        print(f"{name}: {len(data)} bytes -> client-patch/dbc/{name}")
    print(f"migration: {MIGRATION.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())

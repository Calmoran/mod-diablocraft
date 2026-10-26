"""Generate Torment's own placeable world objects: object displays plus the decoration templates wearing them (diablocraft-8jd5).

Two sheets, one row per asset in each:

* data/d3/world_object_displays.csv: a GameObjectDisplayInfo row (id above the stock maximum 9624, model path, size box);
* data/d3/world_objects.csv: a type 5 (generic, decoration) gameobject_template wearing one of those displays, or a stock
  one (a model the client already has a display for needs no new row: diablocraft-jn9r, add_world_object.py does the lookup).

One run writes the client's GameObjectDisplayInfo.dbc (the stock file plus our rows, every stock row byte for byte), the
server overlay world_0036_world_objects.sql (the core loads the binary DBC and then the `gameobjectdisplayinfo_dbc` table,
as it does map_dbc for the Sanctum) and the templates. Nothing is spawned.

    python3 mod-diablocraft/scripts/generate/world/generate_world_objects.py [--stock-dir DIR]

The DBC is coupled to the migration (applied_migrations.py): once world_0036 is applied, a changed sheet needs a new migration.
world_0036 is applied (dev, 2026-10-12), so the render ships as world_0043_world_objects.sql (diablocraft-cq7p2: the Zone Walls);
world_0036 stays as it was applied. world_0043 is applied on dev too, so the walls' Blocked Passage model ships as
world_0051_world_objects.sql (diablocraft-ep332). world_0051 is applied on dev too, so the orb pick round's four displays and
candidate template ship as world_0052_world_objects.sql (diablocraft-xwwg9). When it is applied, point MIGRATION at the next free world_ number.
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
DISPLAYS = MODULE / "data/d3/world_object_displays.csv"
OBJECTS = MODULE / "data/d3/world_objects.csv"
STOCK_DIR = ROOT / "azerothcore-wotlk/build/server/data/dbc"
CLIENT_DIR = ROOT / "client-patch/dbc"
MIGRATION = MODULE / "data/sql/db-world/updates/world_0052_world_objects.sql"
STOCK_MAX_DISPLAY = 9624  # the stock table ends here; ours start above it
OBJECT_RANGE = range(910090, 910100)  # Torment's object block for placeable assets
GENERIC = 5  # GAMEOBJECT_TYPE_GENERIC: a decoration with no use, quest or gossip
BOX = ["min_x", "min_y", "min_z", "max_x", "max_y", "max_z"]
BOX_COLUMNS = ["GeoBoxMinX", "GeoBoxMinY", "GeoBoxMinZ", "GeoBoxMaxX", "GeoBoxMaxY", "GeoBoxMaxZ"]
TEMPLATE_COLUMNS = (["entry", "type", "displayId", "name", "IconName", "castBarCaption", "unk1", "size"]
                    + [f"Data{i}" for i in range(24)] + ["AIName", "ScriptName", "VerifiedBuild"])


class ObjectError(Exception):
    pass


def read_sheet(path, ints, floats=()):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ObjectError(f"{path.name}: no rows")
    for row in rows:
        for field, kind in [(f, int) for f in ints] + [(f, float) for f in floats]:
            try:
                row[field] = kind(row[field])
            except (KeyError, ValueError):
                raise ObjectError(f"{path.name}: {field} {row.get(field)!r} is not a number")
    return rows


def displays(source=DISPLAYS):
    rows = read_sheet(source, ["display_id"], BOX)
    ids = [r["display_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ObjectError(f"{source.name}: a display_id appears twice")
    for row in rows:
        if row["display_id"] <= STOCK_MAX_DISPLAY:
            raise ObjectError(f"{source.name}: display {row['display_id']} is not above the stock maximum {STOCK_MAX_DISPLAY}")
        if not row["model_path"].strip() or not row["name"].strip():
            raise ObjectError(f"{source.name}: display {row['display_id']} has no model_path or name")
    return rows


def objects(display_rows, source=OBJECTS, stock_ids=()):
    rows = read_sheet(source, ["entry", "display_id"], ["size"])
    entries = [r["entry"] for r in rows]
    if len(set(entries)) != len(entries):
        raise ObjectError(f"{source.name}: an entry appears twice")
    known = {r["display_id"] for r in display_rows} | set(stock_ids)
    for row in rows:
        if row["entry"] not in OBJECT_RANGE:
            raise ObjectError(f"{source.name}: entry {row['entry']} is outside Torment's object block {OBJECT_RANGE.start}-{OBJECT_RANGE.stop - 1}")
        if row["display_id"] not in known:
            raise ObjectError(f"{source.name}: entry {row['entry']} wears display {row['display_id']}, which neither {DISPLAYS.name} nor the stock table holds")
        if row["size"] <= 0 or not row["name"].strip():
            raise ObjectError(f"{source.name}: entry {row['entry']} needs a name and a positive size")
    return rows


def stock_store(stock_dir):
    """The stock GameObjectDisplayInfo as a Store."""
    stock = Path(stock_dir) / "GameObjectDisplayInfo.dbc.stock"
    stock = stock if stock.is_file() else Path(stock_dir) / "GameObjectDisplayInfo.dbc"
    if not stock.is_file():
        raise ObjectError(f"{stock}: not found; pass --stock-dir with the stock extracted DBCs")
    return Store(stock.read_bytes(), schema(ROOT, "gameobjectdisplayinfo_dbc"))


def build_dbc(display_rows, stock_dir):
    """(Store with the stock rows plus ours, [our row dicts])."""
    columns = schema(ROOT, "gameobjectdisplayinfo_dbc")
    store = stock_store(stock_dir)
    ours = []
    for row in display_rows:
        values = {name: 0 for name, _, _ in columns}
        values.update(ID=row["display_id"], ModelName=row["model_path"], **dict(zip(BOX_COLUMNS, [float(row[f]) for f in BOX])))
        if row["display_id"] in store.rows and store.decode(row["display_id"]) != values:
            raise ObjectError(f"the stock table already has a different row {row['display_id']}; refusing to overwrite it")
        store.encode(values)
        ours.append(values)
    return store, ours


def migration_sql(ours, object_rows):
    names = [c[0] for c in schema(ROOT, "gameobjectdisplayinfo_dbc")]
    lines = ["-- Generated by generate_world_objects.py from data/d3/world_object_displays.csv and data/d3/world_objects.csv (diablocraft-8jd5).",
             "-- Torment's own object displays (the core loads the binary GameObjectDisplayInfo.dbc and then this table, as for map_dbc;",
             "-- the client's patch carries the same rows) and the decoration templates wearing them. Nothing is spawned.",
             "SET NAMES utf8mb4;",
             "DELETE FROM `gameobjectdisplayinfo_dbc` WHERE `ID` IN (%s);" % ",".join(str(v["ID"]) for v in ours),
             "INSERT INTO `gameobjectdisplayinfo_dbc` (%s) VALUES" % ",".join(f"`{n}`" for n in names)]
    lines.append(",\n".join("(%s)" % ",".join(sql_value(v[n]) for n in names) for v in ours) + ";")
    lines.append("DELETE FROM `gameobject_template` WHERE `entry` IN (%s);" % ",".join(str(r["entry"]) for r in object_rows))
    lines.append("INSERT INTO `gameobject_template` (%s) VALUES" % ",".join(f"`{n}`" for n in TEMPLATE_COLUMNS))
    rows = []
    for r in object_rows:
        v = {"entry": r["entry"], "type": GENERIC, "displayId": r["display_id"], "name": r["name"], "IconName": "",
             "castBarCaption": "", "unk1": "", "size": r["size"], "AIName": "", "ScriptName": "", "VerifiedBuild": 12340}
        rows.append("(%s)" % ",".join(sql_value(v.get(n, 0)) for n in TEMPLATE_COLUMNS))
    lines.append(",\n".join(rows) + ";")
    return "\n".join(lines) + "\n"


def generate(stock_dir, display_source=DISPLAYS, object_source=OBJECTS):
    """({DBC file name: bytes}, migration sql). Writes nothing."""
    display_rows = displays(display_source)
    store, ours = build_dbc(display_rows, stock_dir)
    object_rows = objects(display_rows, object_source, store.rows)
    return {"GameObjectDisplayInfo.dbc": store.bytes()}, migration_sql(ours, object_rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stock-dir", default=str(STOCK_DIR), help="folder with the stock extracted DBCs")
    args = parser.parse_args(argv)
    try:
        outputs, sql = generate(args.stock_dir)
    except ObjectError as error:
        return f"generate_world_objects: {error}"
    write_migration(MODULE, MIGRATION, sql)
    if not write_coupled_outputs(MODULE, MIGRATION, sql, [(CLIENT_DIR / n, d) for n, d in outputs.items()],
                                 label="object display client DBC"):
        return "generate_world_objects: the client DBC was held back (see the warning above)"
    for name, data in outputs.items():
        print(f"{name}: {len(data)} bytes -> client-patch/dbc/{name}")
    print(f"migration: {MIGRATION.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())

"""Generate the Dungeon Finder's rows: Torment's activities in LFGDungeons (diablocraft-v1sw4).

Step (a) of docs/research/lfg-takeover.md 10.5, the client probe. One sheet, data/d3/lfg_activities.csv, drives
both sides in one run (research 2.2 and 10.3):

* every stock row but the zone rows is neutralised, not deleted: Group_Id 0 takes it out of the Specific list, and
  a level range of 0-0 (no player's level) takes the five random rows 258-262 out of the dropdown and every row out
  of the joinable set. The ids stay, so nothing that names one finds a hole. The 59 zone rows (type 4, Group_Id 0
  already, in neither list) stay byte for byte stock: a faction change reads their MinLevel to withhold flight nodes
  above the character's level (CharacterHandler.cpp:2313-2324);
* per activity, a visible random row (type 6, the dropdown entry; a clone of 261, Random Lich King Dungeon) and a
  hidden key row (type 1 with Group_Id 0, so in no list; a clone of 202, Utgarde Keep) on the hub's map, plus its
  lfg_dungeon_template row at the hub spawn: the core skips a non-random row with no position (LFGMgr.cpp:324-336).
  Nobody is teleported there (decisions.md 2026-10-10); the position only keeps the row loaded;
* client: client-patch/dbc/LFGDungeons.dbc (the whole file, the client reads the patch's copy instead of its own),
  and client-patch/addons/Torment/LFGRows.lua, the visible-to-hidden id map the addon's probe joins with;
* server: the world_0039 migration, the same rows into `lfgdungeons_dbc` (the core loads the binary DBC and then
  overlays the table, DBCStores.cpp:337) and the hidden rows' `lfg_dungeon_template`.

A sheet id that is already a stock row, or used twice, is refused. A visible row's Group_Id is its clone's (4), which
after the neutralising holds no non-random row, so a stock expansion of it finds nothing and the core refuses the join.

    python3 mod-diablocraft/scripts/generate/world/generate_lfg_dungeons.py [--stock-dir DIR]
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
SOURCE = MODULE / "data/d3/lfg_activities.csv"
HUB_POINTS = MODULE / "data/d3/world_hub_points.csv"
STOCK_DIR = ROOT / "azerothcore-wotlk/build/server/data/dbc"
CLIENT_DBC = ROOT / "client-patch/dbc/LFGDungeons.dbc"
ADDON_ROWS = ROOT / "client-patch/addons/Torment/LFGRows.lua"
MIGRATION = MODULE / "data/sql/db-world/updates/world_0039_lfg_dungeons.sql"
VISIBLE_TEMPLATE = 261  # Random Lich King Dungeon: type 6, normal, expansion 2
HIDDEN_TEMPLATE = 202  # Utgarde Keep: type 1, normal, expansion 2
TYPE_RANDOM, TYPE_DUNGEON, TYPE_ZONE = 6, 1, 4


class LfgError(Exception):
    pass


def read_sheet(path=SOURCE):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise LfgError(f"{path}: no rows")
    out, seen = [], set()
    for line, row in enumerate(rows, start=2):
        try:
            ids = int(row["visible_id"]), int(row["hidden_id"])
            levels = int(row["min_level"]), int(row["max_level"])
        except (TypeError, ValueError):
            raise LfgError(f"lfg_activities.csv:{line}: ids and levels are integers") from None
        if not (row.get("activity") or "").strip() or not (row.get("name") or "").strip():
            raise LfgError(f"lfg_activities.csv:{line}: activity and name are required")
        if seen & set(ids) or ids[0] == ids[1]:
            raise LfgError(f"lfg_activities.csv:{line}: id {sorted(seen & set(ids)) or ids[0]} is used twice")
        if not 0 < levels[0] <= levels[1]:
            raise LfgError(f"lfg_activities.csv:{line}: levels {levels} are not a range")
        seen |= set(ids)
        out.append({"activity": row["activity"].strip(), "visible": ids[0], "hidden": ids[1],
                    "name": row["name"].strip(), "min": levels[0], "max": levels[1]})
    return out


def hub_spawn(path=HUB_POINTS):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["name"] == "spawn":
                return int(row["map_id"]), tuple(float(row[k]) for k in "xyzo")
    raise LfgError(f"{path}: no spawn row")


def stock_path(stock_dir):
    stock = Path(stock_dir) / "LFGDungeons.dbc.stock"
    return stock if stock.is_file() else Path(stock_dir) / "LFGDungeons.dbc"


def generate(stock_dir, source=SOURCE, hub_points=HUB_POINTS):
    """(dbc bytes, migration sql, addon lua). Writes nothing."""
    path = stock_path(stock_dir)
    if not path.is_file():
        raise LfgError(f"{path}: not found; pass --stock-dir with the stock extracted DBCs")
    columns = schema(ROOT, "lfgdungeons_dbc")
    store = Store(path.read_bytes(), columns)
    activities = read_sheet(source)
    hub_map, spawn = hub_spawn(hub_points)
    taken = sorted({i for a in activities for i in (a["visible"], a["hidden"])} & set(store.rows))
    if taken:
        raise LfgError(f"{path.name} already has rows {taken}; Torment's ids must be free")
    rows = []
    for key in sorted(store.rows):
        values = store.decode(key)
        if values["TypeID"] != TYPE_ZONE:
            values.update(Group_Id=0, MinLevel=0, MaxLevel=0)
        rows.append(values)
    templates = {kind: store.decode(i) for kind, i in (("visible", VISIBLE_TEMPLATE), ("hidden", HIDDEN_TEMPLATE))}
    for a in activities:
        for kind in ("visible", "hidden"):
            values = dict(templates[kind], ID=a[kind], Name_Lang_enUS=a["name"], MinLevel=a["min"],
                          MaxLevel=a["max"], Target_Level=a["max"], Target_Level_Min=a["min"],
                          Target_Level_Max=a["max"])
            if kind == "hidden":
                values.update(MapID=hub_map, Group_Id=0)
            rows.append(values)
    for values in rows:
        store.encode(values)
    return store.bytes(), migration_sql(columns, rows, activities, spawn), addon_lua(activities)


def migration_sql(columns, rows, activities, spawn):
    names = [c[0] for c in columns]
    hidden = [a["hidden"] for a in activities]
    lines = ["-- Generated by generate_lfg_dungeons.py from data/d3/lfg_activities.csv (diablocraft-v1sw4).",
             "-- The Dungeon Finder's rows: every stock LFGDungeons row but the zone rows (type 4, kept stock)",
             "-- neutralised (Group_Id 0, levels 0-0), and per activity a visible random row and a hidden key row,",
             "-- the same rows client-patch/dbc/LFGDungeons.dbc carries.",
             "-- The hidden rows' entrance is the hub spawn: nobody is teleported there, the core only needs a position.",
             "SET NAMES utf8mb4;",
             "DELETE FROM `lfgdungeons_dbc` WHERE `ID` IN (%s);" % ",".join(str(r["ID"]) for r in rows),
             "INSERT INTO `lfgdungeons_dbc` (%s) VALUES\n%s;" % (
                 ",".join(f"`{n}`" for n in names),
                 ",\n".join("(" + ",".join(sql_value(r[n]) for n in names) + ")" for r in rows)),
             "DELETE FROM `lfg_dungeon_template` WHERE `dungeonId` IN (%s);" % ",".join(map(str, hidden)),
             "INSERT INTO `lfg_dungeon_template` (`dungeonId`,`name`,`position_x`,`position_y`,`position_z`,"
             "`orientation`,`VerifiedBuild`) VALUES\n%s;" % ",\n".join(
                 "(%d,%s,%s,0)" % (a["hidden"], sql_value(a["name"]), ",".join(sql_value(v) for v in spawn))
                 for a in activities)]
    return "\n".join(lines) + "\n"


def addon_lua(activities):
    lines = ["-- luacheck: globals TormentLFGRows",
             "-- Generated by mod-diablocraft/scripts/generate/world/generate_lfg_dungeons.py from data/d3/lfg_activities.csv; do not edit.",
             "-- The Dungeon Finder's activities: visible dropdown row id -> hidden key row id.",
             "TormentLFGRows = {"]
    lines += ["    [%d] = %d, -- %s" % (a["visible"], a["hidden"], a["name"]) for a in activities]
    return "\n".join(lines + ["}"]) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stock-dir", default=str(STOCK_DIR), help="folder with the stock extracted DBCs")
    args = parser.parse_args(argv)
    try:
        dbc, sql, lua = generate(args.stock_dir)
    except LfgError as error:
        return f"generate_lfg_dungeons: {error}"
    write_migration(MODULE, MIGRATION, sql)
    if not write_coupled_outputs(MODULE, MIGRATION, sql, [(CLIENT_DBC, dbc), (ADDON_ROWS, lua)],
                                 label="Dungeon Finder client rows"):
        return "generate_lfg_dungeons: the client rows were held back (see the warning above)"
    print(f"LFGDungeons.dbc: {len(dbc)} bytes -> {CLIENT_DBC.relative_to(ROOT)}")
    print(f"addon rows -> {ADDON_ROWS.relative_to(ROOT)}")
    print(f"migration: {MIGRATION.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())

"""Generate the open-world rift maps: a continent's terrain as a private instance map, Kalimdor as 751 (diablocraft-kw18),
the Eastern Kingdoms as 752 (diablocraft-hyoic.6) and Outland as 753 (diablocraft-hyoic.9; docs/research/bounty-acts.md 6).

The Sanctum's method (generate_hub_sanctum.py, decisions.md 2026-10-03) with more layers. The client DBCs are single
files, so each layer is built over the one before it and every sheet ends up in the same four files:

* data/d3/world_sanctum_dbc.csv (the Sanctum, world_0030, unchanged) is the first layer;
* then LAYERS in order, one clone map each: world_open_rift_dbc.csv (Map 751, a clone of Kalimdor's row 1 made a party
  dungeon, its 22 WorldMapArea rows and 127 Light rows cloned onto it), world_open_rift_ek_dbc.csv (Map 752 from the
  Eastern Kingdoms' row 0, its 26 WorldMapArea rows and 82 Light rows) and world_open_rift_outland_dbc.csv (Map 753 from
  row 530, Outland's 9 WorldMapArea rows and map 530's 176 Light rows). The source row's directory, loading screen and
  name rules are kept, so the client reads the continent's own terrain. Map 751 also carries the 230 WorldMapOverlay rows
  of those Kalimdor world maps, cloned onto the clones (3000 + the original, zone fog, diablocraft-y0gjt): the client
  lights an explored sub-area only through an overlay of the world map on screen. They are the client's alone; 752 and 753
  have none.

Each layer's server overlay is its own migration (world_0035 for 751, world_0045 for 752, world_0046 for 753): `map_dbc` (from the sheet),
plus the two rows the core needs before it lets anybody into a dungeon-type map (research
docs/research/open-world-rifts.md section 3, items 1 and 2): `instance_template` (the clone, parent its source
continent) and one `mapdifficulty_dbc` row for the normal difficulty (a higher setting is downscaled to it). Nothing is
hardcoded: the ids, the parent and the party size are read from the sheet's Map row.

    python3 mod-diablocraft/scripts/generate/rifts/generate_open_rift_map.py [--stock-dir DIR]

The map files (maps/vmaps/mmaps of the source continent under the clone's id) are links made by `link_map_clone.py
--sheet <the layer's sheet>`, run by the PM on each data folder. The client files are coupled to the last layer's
migration (applied_migrations.py), as the Sanctum's are to its own.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_sanctum as sanctum  # noqa: E402
from applied_migrations import write_migration  # noqa: E402
from dbc_store import Store, schema, sql_value  # noqa: E402

MODULE = sanctum.MODULE
ROOT = sanctum.ROOT
SOURCE = MODULE / "data/d3/world_open_rift_dbc.csv"
MIGRATION = MODULE / "data/sql/db-world/updates/world_0035_open_rift_map.sql"
EK_SOURCE = MODULE / "data/d3/world_open_rift_ek_dbc.csv"
EK_MIGRATION = MODULE / "data/sql/db-world/updates/world_0045_open_rift_ek_map.sql"
OUTLAND_SOURCE = MODULE / "data/d3/world_open_rift_outland_dbc.csv"
OUTLAND_MIGRATION = MODULE / "data/sql/db-world/updates/world_0046_open_rift_outland_map.sql"
# The layers over the Sanctum's, in build order: (sheet, its migration, the bead, whose terrain the header names).
LAYERS = ((SOURCE, MIGRATION, "diablocraft-kw18", "Kalimdor's"),
          (EK_SOURCE, EK_MIGRATION, "diablocraft-hyoic.6", "the Eastern Kingdoms'"),
          (OUTLAND_SOURCE, OUTLAND_MIGRATION, "diablocraft-hyoic.9", "Outland's"))
# A stock five-player dungeon with a normal row: the template of the one MapDifficulty row (Utgarde Keep).
DIFFICULTY_TEMPLATE_MAP = 574
# The MapDifficulty id: map id x 10 + difficulty, free in stock (its ids end at 753).
DIFFICULTY_ID_FACTOR = 10


def map_row(source=SOURCE):
    """(map id, source map id, {field: raw value}) of the sheet's one Map row."""
    maps = {k: v for k, v in sanctum.records(sanctum.read_rows(source)).items() if k[0] == "Map"}
    if len(maps) != 1:
        raise sanctum.SanctumError(f"{source}: expected exactly one Map row, found {len(maps)}")
    ((_, map_id), (source_id, fields)), = maps.items()
    return map_id, source_id, fields


def difficulty_row(stock_dir, map_id, max_players):
    columns = schema(ROOT, "mapdifficulty_dbc")
    path = sanctum.stock_path(stock_dir, "MapDifficulty")
    if not path.is_file():
        raise sanctum.SanctumError(f"{path}: not found; pass --stock-dir with the stock extracted DBCs")
    store = Store(path.read_bytes(), columns)
    template = [i for i in sorted(store.rows)
                if (v := store.decode(i))["MapID"] == DIFFICULTY_TEMPLATE_MAP and v["Difficulty"] == 0]
    if not template:
        raise sanctum.SanctumError(f"MapDifficulty has no normal row for map {DIFFICULTY_TEMPLATE_MAP}")
    values = store.decode(template[0])
    values.update({"ID": map_id * DIFFICULTY_ID_FACTOR, "MapID": map_id, "Difficulty": 0, "RaidDuration": 0,
                   "MaxPlayers": max_players, "Message_Lang_enUS": "", "Difficultystring": ""})
    return columns, values


def migration_sql(map_sql, map_id, parent, columns, difficulty, source=SOURCE, bead="diablocraft-kw18", continent="Kalimdor's"):
    names = [c[0] for c in columns]
    lines = ["-- Generated by generate_open_rift_map.py from data/d3/%s (%s)." % (Path(source).name, bead),
             "-- Overlays for the open-world rift map %d, %s terrain as a private party instance: the Map row" % (map_id, continent),
             "-- (map_dbc), the instance_template row and the normal-difficulty row the core demands before it lets",
             "-- anyone in. The client's patch carries the same Map, WorldMapArea and Light rows."]
    lines += ["SET NAMES utf8mb4;", map_sql.split("SET NAMES utf8mb4;\n", 1)[1].rstrip("\n")]
    lines.append("DELETE FROM `mapdifficulty_dbc` WHERE `ID` IN (%d);" % difficulty["ID"])
    lines.append("INSERT INTO `mapdifficulty_dbc` (%s) VALUES\n(%s);" % (
        ",".join(f"`{n}`" for n in names), ",".join(sql_value(difficulty[n]) for n in names)))
    lines.append("DELETE FROM `instance_template` WHERE `map` IN (%d);" % map_id)
    lines.append("INSERT INTO `instance_template` (`map`,`parent`,`script`,`allowMount`) VALUES (%d,%d,'',1);" % (map_id, parent))
    return "\n".join(lines) + "\n"


def layer(base, stock_dir, source):
    """({DBC file name: bytes} with `source`'s rows over `base`, the sheet's map_dbc sql). Writes nothing."""
    with tempfile.TemporaryDirectory(prefix="open_rift_layer_") as layer:
        for name, data in base.items():
            (Path(layer) / name).write_bytes(data)
        # tables this layer does not touch keep the layer below's file (or stock); the others are read from the temp folder
        for table in sanctum.TABLES:
            plain = Path(layer) / f"{table}.dbc"
            if not plain.exists():
                plain.write_bytes(sanctum.stock_path(stock_dir, table).read_bytes())
        own, map_sql = sanctum.generate(source, layer)
    outputs = {**base, **own}
    return outputs, map_sql


def generate(stock_dir, sanctum_source=sanctum.SOURCE, layers=LAYERS):
    """({DBC file name: bytes} after every layer, {migration path: sql} in layer order). Writes nothing."""
    outputs, _ = sanctum.generate(sanctum_source, stock_dir)
    sqls = {}
    for source, migration, bead, continent in layers:
        map_id, parent, fields = map_row(source)
        outputs, map_sql = layer(outputs, stock_dir, source)
        columns, difficulty = difficulty_row(stock_dir, map_id, int(fields["MaxPlayers"]))
        sqls[migration] = migration_sql(map_sql, map_id, parent, columns, difficulty, source, bead, continent)
    return outputs, sqls


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stock-dir", default=str(sanctum.STOCK_DIR), help="folder with the stock extracted DBCs")
    args = parser.parse_args(argv)
    try:
        outputs, sqls = generate(args.stock_dir)
    except sanctum.SanctumError as error:
        return f"generate_open_rift_map: {error}"
    *earlier, last = sqls
    for migration in earlier:
        write_migration(MODULE, migration, sqls[migration])
    # the client files carry every layer, so they follow the last layer's migration
    if not sanctum.emit(MODULE, last, sanctum.CLIENT_DIR, outputs, sqls[last]):
        return "generate_open_rift_map: the client DBCs were held back (see the warning above)"
    for name, data in outputs.items():
        print(f"{name}: {len(data)} bytes -> client-patch/dbc/{name}")
    for migration in sqls:
        print(f"migration: {migration.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())

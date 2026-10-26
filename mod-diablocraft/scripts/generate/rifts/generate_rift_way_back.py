#!/usr/bin/env python3
"""The way back out of a rift floor (rift floors Part F4, diablocraft-o69g, docs/proposals/rift-floors.md 4.5, 6.7).

    python3 mod-diablocraft/scripts/generate/rifts/generate_rift_way_back.py                    # sheet -> rifts_0022_way_back.sql (offline)
    python3 mod-diablocraft/scripts/generate/rifts/generate_rift_way_back.py --survey [--dbc P] # AreaTrigger.dbc + world database -> the sheet

Every rift dungeon has stock way-out triggers: a trigger on its map in AreaTrigger.dbc whose `areatrigger_teleport` row leads to
another map (Ragefire Chasm's exit to Orgrimmar, Dire Maul's seven). Stock, stepping on one teleports a player to the dungeon's
entrance on the continent. The sheet data/d3/rift_way_back.csv lists them (`map_id`, `trigger`, `name`, `target_map`, and the pool
row nearest the trigger with its straight distance from that row's arrival point); the migration hands each to the module's
area trigger script (`areatrigger_scripts`, ScriptName below), which in a live rift floor leads up a floor (to the exit portal of the
floor above) or, from floor 1, to the hub (src/rifts/dc_rift_exit.cpp). Outside a rift the script leaves the stock teleport alone.
A trigger the designer switched off (data/d3/rift_way_none.csv, diablocraft-hcwjv) goes to NONE_SCRIPT_NAME instead, which in a live rift
floor does nothing; the survey sheet still lists it, because it is a way-out trigger.

The survey refuses a trigger that already has another script of its own. The sheet is the source; `--survey` rewrites it.
"""
import argparse
import csv
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
D3 = MODULE / "data/d3"
SHEET = D3 / "rift_way_back.csv"
COLUMNS = ("map_id", "trigger", "name", "target_map", "nearest_dungeon", "arrival_yards")
# rifts_0022 is applied (update 9) and frozen: the whole render (DELETE then INSERT) ships as rifts_0030 (diablocraft-hcwjv).
NAME = "rifts_0030_way_back.sql"
# Constant (an identity, not a game number): the name src/rifts/dc_rift_exit.cpp registers; test_rift_way_back.py reads both.
SCRIPT_NAME = "dc_rift_way_back"
NONE_SCRIPT_NAME = "dc_rift_way_none"
NONE_SHEET = D3 / "rift_way_none.csv"
# AreaTrigger.dbc (3.3.5a): id, map, x, y, z, radius, box length, width, height, yaw.
DBC_RECORD = "<2I8f"
DBC_SIZE = 40


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def read_pool():
    return [row for row in read_csv(D3 / "rift_dungeons.csv") if row["recommended"].strip().lower() == "yes"]


def read_triggers(path):
    """{trigger id: (map, x, y, z)} from AreaTrigger.dbc."""
    raw = Path(path).read_bytes()
    magic, count, fields, size, _ = struct.unpack_from("<4s4I", raw)
    if magic != b"WDBC" or fields != 10 or size != DBC_SIZE:
        raise ValueError(f"{path}: not a 3.3.5a AreaTrigger.dbc")
    out = {}
    for n in range(count):
        row = struct.unpack_from(DBC_RECORD, raw, 20 + n * size)
        out[row[0]] = (row[1], row[2], row[3], row[4])
    return out


def survey(pool, triggers, teleports, scripts):
    """The way-out triggers of the pool's maps. `triggers` {id: (map, x, y, z)}; `teleports` {id: (target_map, name)} (the
    areatrigger_teleport rows); `scripts` {id: ScriptName} (areatrigger_scripts). Raises when a pool row has none, or when a
    trigger already belongs to another script."""
    rows = []
    for dungeon in pool:
        mine = [p for p in pool if p["map_id"] == dungeon["map_id"]]
        if dungeon is not mine[0]:
            continue    # a map shared by two rows (Scarlet Monastery) is listed once
        found = []
        for trigger, (map_id, x, y, z) in triggers.items():
            if str(map_id) != dungeon["map_id"] or trigger not in teleports or teleports[trigger][0] == map_id:
                continue
            if scripts.get(trigger, SCRIPT_NAME) not in (SCRIPT_NAME, NONE_SCRIPT_NAME):
                raise ValueError(f"trigger {trigger} ({teleports[trigger][1]}) already has the script {scripts[trigger]}")
            near = min(((math.dist((x, y, z), (float(p["entry_x"]), float(p["entry_y"]), float(p["entry_z"]))), p["name"])
                        for p in mine))
            found.append({"map_id": map_id, "trigger": trigger, "name": teleports[trigger][1], "target_map": teleports[trigger][0],
                          "nearest_dungeon": near[1], "arrival_yards": f"{near[0]:.1f}"})
        if not found:
            raise ValueError(f"{dungeon['name']} (map {dungeon['map_id']}) has no way-out trigger")
        rows += sorted(found, key=lambda r: float(r["arrival_yards"]))
    return rows


def render(rows, none=()):
    """`none`: the rift_way_none.csv rows; each must be one of `rows`."""
    off = {str(r["trigger"]) for r in none}
    unknown = off - {str(r["trigger"]) for r in rows}
    if unknown:
        raise ValueError(f"rift_way_none.csv lists triggers that are no way-out trigger: {sorted(unknown)}")
    ids = ", ".join(str(r["trigger"]) for r in rows)
    values = ",\n".join(f"  ({r['trigger']}, '{NONE_SCRIPT_NAME if str(r['trigger']) in off else SCRIPT_NAME}')" for r in rows)
    return "\n".join([
        f"-- Generated by generate_rift_way_back.py from data/d3/rift_way_back.csv (diablocraft-o69g); never edit.",
        "-- Rift floors Part F4 (docs/proposals/rift-floors.md 4.5): each rift dungeon's stock way-out triggers go to the module's area",
        "-- trigger script, which leads a player in a live rift floor up a floor, or from floor 1 to the hub, and leaves any other player",
        "-- to the stock teleport. A trigger in data/d3/rift_way_none.csv does nothing in a live rift floor (diablocraft-hcwjv).",
        f"DELETE FROM `areatrigger_scripts` WHERE `entry` IN ({ids});",
        f"INSERT INTO `areatrigger_scripts` (`entry`, `ScriptName`) VALUES\n{values};",
        "",
    ])


def generate(sheet=None, none_sheet=None):
    sql = render(read_csv(sheet or SHEET), read_csv(none_sheet or NONE_SHEET))
    target = MODULE / "data/sql/db-world/updates" / NAME
    write_migration(MODULE, target, sql)
    write_coupled_outputs(MODULE, target, sql, [(MODULE / "data/generated/rift_way_back.sql", sql)], label="rift way-back triggers")
    print(f"Generated {NAME}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--survey", action="store_true", help="read AreaTrigger.dbc and the world database, write the sheet")
    parser.add_argument("--dbc", default=str(ROOT / "azerothcore-wotlk/build/server/data/dbc/AreaTrigger.dbc"))
    parser.add_argument("--mysql")
    parser.add_argument("--defaults-file")
    args = parser.parse_args()
    if args.survey:
        import fixture_db
        from generate_area_copies import Database
        mysql, defaults = (args.mysql, args.defaults_file) if args.mysql and args.defaults_file else fixture_db.mysql_and_defaults([])
        db = Database(mysql, defaults, "acore_world")
        teleports = {int(a): (int(b), n) for a, b, n in (line.split("\t") for line in db.query("SELECT id, target_map, Name FROM areatrigger_teleport"))}
        scripts = {int(a): n for a, n in (line.split("\t") for line in db.query("SELECT entry, ScriptName FROM areatrigger_scripts"))}
        rows = survey(read_pool(), read_triggers(args.dbc), teleports, scripts)
        with SHEET.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(COLUMNS)
            writer.writerows([[r[c] for c in COLUMNS] for r in rows])
        print(f"{len(rows)} way-out triggers on {len({r['map_id'] for r in rows})} maps")
    generate()


if __name__ == "__main__":
    main()

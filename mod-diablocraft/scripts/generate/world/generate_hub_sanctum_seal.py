#!/usr/bin/env python3
"""Generate the Sanctum door's migration (diablocraft-976b): Yogg-Saron's arena door, shut and unclickable, once (the Sanctum is one phase, diablocraft-k4ce).

The Sanctum of Torment is map 750, a clone of map 603 (Ulduar); the arena's own door is its one way out. The designer's
GM-spawned door (stock entry 194773, addon flags 32) OPENED on a click. The core's GameObject::Use returns at once for
a not-selectable object, so this migration makes entry 910019, a copy of the stock door with startOpen off and the
addon flags raised by not-selectable + locked, and spawns it shut (state 1) where the stock spawn stands. One row, in phase 1: the tier 2-10
copies this migration used to write go in world_00NN_sanctum_one_copy.sql (generate_sanctum_one_copy.py).

The position is the stock spawn's (guid 55078 on map 603), carried in data/d3/world_sanctum_seal.csv: World places
nothing on its own judgement. Everything is guarded: a row that is not this door stops the migration before it writes.
The area rule and the area registry row (dc_area_source) come with it, so the area filter lets the
spawn stand. Nothing here moves the hub: that is generate_hub_sanctum_move.py.

    python3 mod-diablocraft/scripts/generate/world/generate_hub_sanctum_seal.py
"""
import csv
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration
from generate_area_copies import insert
from generate_hub_placements import source_snapshot, upsert

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/d3/world_sanctum_seal.csv"
AREAS = ROOT / "data/d3/world_areas.csv"
POINTS = ROOT / "data/d3/world_hub_points.csv"
NAME = "world_0031_sanctum_seal.sql"
LOCKED, NOT_SELECTABLE = 0x02, 0x10     # GameObjectFlags (SharedDefines.h): the test pins both against the core
CLOSED_FLAGS = LOCKED | NOT_SELECTABLE  # the donor's own flags (32, never despawn) stay
HEADER = {"kind", "entry", "donor_entry", "name", "map_id", "area_id", "x", "y", "z", "o", "rotation2", "rotation3",
          "spawntimesecs", "animprogress", "source_guid", "placement_source", "guid_source"}
DOOR = "dc_sanctum_door"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def door_row(path=DATA):
    found = rows(path)
    if len(found) != 1 or set(found[0]) != HEADER or found[0]["kind"] != "door":
        raise ValueError("Expected one door row in world_sanctum_seal.csv")
    row = found[0]
    if not row["placement_source"] or not row["guid_source"]:
        raise ValueError("The Sanctum door needs its placement and GUID sources")
    hub = {r["name"]: r for r in rows(POINTS)}["spawn"]
    row["map_id"], row["area_id"] = int(row["map_id"]), int(row["area_id"])
    if (row["map_id"], row["area_id"]) != (int(hub["map_id"]), int(hub["area_id"])):
        raise ValueError("The Sanctum door must stand in the hub's map and area")
    for key in ("entry", "donor_entry", "source_guid", "spawntimesecs", "animprogress"):
        try:
            row[key] = int(row[key])
        except ValueError:
            raise ValueError(f"Sanctum door: {key} is not a whole number: {row[key]!r}") from None
    for key in ("x", "y", "z", "o", "rotation2", "rotation3"):
        try:
            row[key] = float(row[key])
        except ValueError:
            raise ValueError(f"Sanctum door: {key} is not a number: {row[key]!r}") from None
        if not math.isfinite(row[key]):
            raise ValueError(f"Sanctum door: {key} is not finite")
    if row["entry"] <= 0 or row["entry"] == row["donor_entry"]:
        raise ValueError("The Sanctum door needs its own template entry; the donor's must never be overwritten")
    if not 0 <= row["o"] < 2 * math.pi or abs(row["rotation2"] ** 2 + row["rotation3"] ** 2 - 1) > 0.001:
        raise ValueError("Sanctum door: facing or rotation is not a rotation about z")
    if not 0 <= row["animprogress"] <= 255 or row["spawntimesecs"] < 0:
        raise ValueError("Sanctum door: animprogress or respawn time out of range")
    if not 0 < row["source_guid"] < 2**32:
        raise ValueError("Sanctum door: invalid GUID block")
    return row


def area_rule(map_id, area_id, path=AREAS):
    found = [r for r in rows(path) if (r["map_id"], r["area_id"]) == (str(map_id), str(area_id))]
    if len(found) != 1 or (found[0]["status"], found[0]["phase_scope"]) != ("open", "all"):
        raise ValueError(f"world_areas.csv needs one open, all-phase rule for {map_id}/{area_id}")
    return found[0]


def generate(path=DATA, areas=AREAS):
    door = door_row(path)
    rule = area_rule(door["map_id"], door["area_id"], areas)
    map_id, area_id, entry, donor = door["map_id"], door["area_id"], door["entry"], door["donor_entry"]
    guid = door["source_guid"]
    # a plain quoted literal, not literal()'s CONVERT: the guard compares it with a column of another collation
    name = "'" + door["name"].replace("\\", "\\\\").replace("'", "''") + "'"
    guards = [
        f"EXISTS(SELECT 1 FROM gameobject_template WHERE entry={donor} AND type=0)",
        f"NOT EXISTS(SELECT 1 FROM gameobject_template WHERE entry={entry}) OR "
        f"EXISTS(SELECT 1 FROM gameobject_template WHERE entry={entry} AND type=0 AND name={name})",
        f"NOT EXISTS(SELECT 1 FROM gameobject WHERE guid={guid}) OR EXISTS(SELECT 1 FROM gameobject "
        f"WHERE guid={guid} AND id={entry} AND map={map_id} AND phaseMask=1)",
        f"NOT EXISTS(SELECT 1 FROM dc_area_spawn WHERE kind='g' AND spawn_guid={guid})",
        f"NOT EXISTS(SELECT 1 FROM dc_area_source WHERE kind='g' AND source_guid={guid}) OR EXISTS("
        f"SELECT 1 FROM dc_area_source WHERE kind='g' AND source_guid={guid} AND map_id={map_id} "
        f"AND area_id={area_id} AND entry={entry})",
    ]
    # dc_world_areas has no key (it is the rules sheet as a table): a rule is replaced, never upserted
    statements = [f"DELETE FROM `dc_world_areas` WHERE `map_id`={map_id} AND `area_id`={area_id};",
                  insert("dc_world_areas", dict(map_id=map_id, area_id=area_id, phase_scope=rule["phase_scope"],
                                                status=rule["status"], note=rule["note"])),
                  f"CREATE TEMPORARY TABLE {DOOR}_template LIKE gameobject_template;",
                  f"INSERT INTO {DOOR}_template SELECT * FROM gameobject_template WHERE entry={donor};",
                  # startOpen off: with state 1 (shut) the door's collision is on, as the client draws it shut
                  f"UPDATE {DOOR}_template SET entry={entry},name={name},Data0=0,AIName='',ScriptName='';",
                  f"REPLACE INTO gameobject_template SELECT * FROM {DOOR}_template;",
                  f"DROP TEMPORARY TABLE {DOOR}_template;",
                  f"CREATE TEMPORARY TABLE {DOOR}_addon LIKE gameobject_template_addon;",
                  f"INSERT INTO {DOOR}_addon SELECT * FROM gameobject_template_addon WHERE entry={donor};",
                  f"UPDATE {DOOR}_addon SET entry={entry},flags=flags|{CLOSED_FLAGS};",
                  f"REPLACE INTO gameobject_template_addon SELECT * FROM {DOOR}_addon;",
                  f"DROP TEMPORARY TABLE {DOOR}_addon;"]
    # the post-condition: whatever the donor's addon row held, the Sanctum's door ends locked and not selectable
    after = [f"EXISTS(SELECT 1 FROM gameobject_template_addon WHERE entry={entry} AND flags&{CLOSED_FLAGS}={CLOSED_FLAGS})"]
    placed = dict(guid=guid, id=entry, map=map_id, zoneId=area_id, areaId=area_id, spawnMask=1, phaseMask=1,
                  position_x=door["x"], position_y=door["y"], position_z=door["z"], orientation=door["o"],
                  rotation0=0, rotation1=0, rotation2=door["rotation2"], rotation3=door["rotation3"],
                  spawntimesecs=door["spawntimesecs"], animprogress=door["animprogress"], state=1)
    statements += [upsert("gameobject", placed), source_snapshot("gameobject", "g", map_id, area_id, guid)]
    lines = ["-- Generated by generate_hub_sanctum_seal.py from world_sanctum_seal.csv and world_areas.csv; never edit.",
             f"-- The Sanctum of Torment's door: template {entry}, a copy of stock door {donor} (startOpen off, flags |= "
             f"{CLOSED_FLAGS}: locked + not selectable, so GameObject::Use returns at once), spawned shut, once.",
             "-- Placement: " + door["placement_source"] + ".",
             f"-- GUID {guid}: " + door["guid_source"] + ".",
             "-- Apply to the world database with worldserver stopped.",
             "SET NAMES utf8mb4;",
             f"CREATE TEMPORARY TABLE {DOOR}_guard (ok INT NOT NULL CHECK(ok=1));",
             "START TRANSACTION;"]
    lines += [f"INSERT INTO {DOOR}_guard VALUES (({g}));" for g in guards]
    lines += statements
    lines += [f"INSERT INTO {DOOR}_guard VALUES (({g}));" for g in after]
    lines += ["COMMIT;", f"DROP TEMPORARY TABLE {DOOR}_guard;", ""]
    return "\n".join(lines)


def main():
    sql = generate()
    migration = ROOT / "data/sql/db-world/updates" / NAME
    if migration.exists() and not migration.read_text(encoding="utf-8").startswith(
            "-- Generated by generate_hub_sanctum_seal.py"):
        raise ValueError(NAME + " is already owned by another migration; choose the next free world number")
    write_migration(ROOT, migration, sql)
    write_coupled_outputs(ROOT, migration, sql, [(ROOT / "data/generated" / NAME, sql)],
                          label="Sanctum seal generated SQL mirror")
    print(NAME + ": the Sanctum door, shut, once")


if __name__ == "__main__":
    main()

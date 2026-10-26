#!/usr/bin/env python3
"""Generate the hub flip (diablocraft-976b): the hub leaves Scryer's Tier for the Sanctum of Torment (map 750, area 4273).

The Sanctum is ONE shared phase (diablocraft-k4ce, docs/research/cross-tier-sanctum.md 3): every hub thing has one row, in phase 1, and
nothing here writes a tier 2-10 copy. The copies the old model left on a database go in world_00NN_sanctum_one_copy.sql
(generate_sanctum_one_copy.py).

The hub's data files already name the Sanctum; this turns them into ONE guarded, idempotent migration:

  world_areas.csv           every area rule is written, so the old hub closes and the Sanctum stays open
  world_hub_points.csv      spawn, town_portal, rift_exit (dc_world_hub_point, dc_world_hub, the start rows of
                            playercreateinfo) and the graveyard (game_graveyard + graveyard_zone, death and falls)
  world_hub_placements.csv  the Blacksmith, Mystic, Stash, Rift Keeper, Jeweler, Kadala, the three Heroic Training Dummies, the obelisk and
                            the two tome objects, moved by GUID, their area registry re-keyed; the designer's scenery (SCENERY), which keeps his
                            rotation as placed
  world_tester_coffer.csv   the Tester's Coffer, moved the same way

World places nothing on its own judgement: every position is a cell that the designer's .gps reading fills (card q-1003-39,
applied by diablocraft-ftoz). Until then this generator REFUSES and names every blank cell; ftoz fills the cells and
commits the migration this writes. An existing row is MOVED (its map, area and position change, nothing else), so a
row the designer placed by hand keeps its other fields; a row that is not there yet is inserted from the placement's JSON.
Everything is guarded: a guid that holds someone else's row stops the migration before it writes.

    python3 mod-diablocraft/scripts/generate/world/generate_hub_sanctum_move.py [--name world_00NN_sanctum_hub_move.sql]
"""
import argparse
import csv
import json
import math
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import reserved_number, write_coupled_outputs, write_migration
from generate_area_copies import insert
from generate_hub_placements import TABLES, TOME_ENTRY, source_snapshot, tunable_positive, upsert, upsert_existing
from generate_hub_tester_coffer import ENTRY as COFFER_ENTRY
import generate_hub_sanctum_seal as seal

ROOT = Path(__file__).resolve().parents[3]
D3 = ROOT / "data/d3"
POINTS, PLACEMENTS, COFFER, AREAS = (D3 / name for name in (
    "world_hub_points.csv", "world_hub_placements.csv", "world_tester_coffer.csv", "world_areas.csv"))
UPDATES = ROOT / "data/sql/db-world/updates"
SUFFIX = "_sanctum_hub_move.sql"
GUARD = "dc_sanctum_move_guard"
POINT_NAMES = ("spawn", "town_portal", "rift_exit")
GRAVEYARD_ID = 910000  # game_graveyard.ID: a number space of its own (the stock rows end at 1720); an identity, not a tunable
# The managed hub services: the four artisans, the Jeweler and Kadala, the obelisk, the tome and its book stack, and the
# Heroic Training Dummy (entry 31146), which is three spawns on one entry: the hand-placed creature GUIDs of the old hub.
DUMMY_ENTRY, DUMMY_COUNT = 31146, 3
# 910005 is Kadala, who stands where the designer put her (diablocraft-bb67).
SERVICES = {"c": {910000, 910001, 910002, 910003, 910004, 910005}, "g": {910011, 910016}}
# The designer's own scenery (card q-1005-04): a campfire, a table and a book, stock templates he placed once with the GObject Editor and
# said can go to all layers. They keep his rotation quaternion as placed (the editor's rotation is what the client draws).
# diablocraft-bb67 adds what he put on and around the table and the platform with the Azeroth World Editor: the stairs (910090),
# four stock decorations (180338, 180425, 180340, 182005) and the five table pieces and the platform made with add_world_object.py (910092-910096).
SCENERY = {1799, 180324, 2695, 910090, 910092, 910093, 910094, 910095, 910096, 180338, 180425, 180340, 182005}
# The adder's templates (world_objects.csv) are written by world_0036, which sorts after this file: a fresh database has none of them
# yet when this runs, so their template guard is left out (a spawn without its template only logs, and 0036 follows in the same start).
LATER_TEMPLATES = {int(r["entry"]) for r in csv.DictReader((D3 / "world_objects.csv").open(encoding="utf-8-sig", newline=""))}
# What the designer's editor left on Torment Development that the layout replaces (his export 2026_10_10_00_project.sql, never run): his Platform and
# Red Aura rows and templates (the adder gave those their own numbers), his stock Ritual Candle, Book of the Dead and Musty Scroll (clickable or
# lootable; the table wears the adder's look-alikes) and his extra Tome (the Tome group stands there now). A row goes only if the guid still
# holds that entry; a database without them is untouched.
DEV_LEFTOVERS = ((8001559, 910087), (8001563, 910016), (8001564, 910089), (8001567, 176188), (8001568, 183983), (8001569, 2555))
DEV_LEFTOVER_TEMPLATES = (910087, 910089)
XYZO, PLACE = ("x", "y", "z", "o"), ("position_x", "position_y", "position_z", "orientation")
MOVE = {"c": ("map", "zoneId", "areaId") + PLACE,
        "g": ("map", "zoneId", "areaId") + PLACE + ("rotation0", "rotation1", "rotation2", "rotation3")}
COFFER_HEADER = {"map_id", "area_id", "x", "y", "z", "o", "placement_source", "source_guid", "guid_source"}
PLACEMENT_HEADER = {"kind", "source_guid", "placement", "source"}   # no copy_guids: one row per thing


def reading(cells, keys, what, pending):
    """The four numbers as {x, y, z, o} from the cells named by `keys`; None (with `what` noted in `pending`) while one is blank."""
    if any(cells.get(key) is None or str(cells[key]).strip() == "" for key in keys):
        pending.append(what)
        return None
    try:
        values = [float(cells[key]) for key in keys]
    except ValueError:
        raise ValueError(f"{what}: a position cell is not a number: {[cells[key] for key in keys]!r}") from None
    if not all(map(math.isfinite, values)) or not 0 <= values[3] < 2 * math.pi:
        raise ValueError(f"{what}: a position is not finite, or the facing is outside [0, 2*pi)")
    return dict(zip(XYZO, values))


def guid_block(guid, what):
    if not isinstance(guid, int) or not 0 < guid < 2**32:
        raise ValueError(f"{what}: {guid!r} is not a GUID")
    return guid


def load(points=POINTS, placements=PLACEMENTS, coffer=COFFER, areas=AREAS, door=seal.DATA):
    """The whole input, checked. Returns (plan, pending): `pending` names every position cell that is still blank."""
    pending = []
    found = seal.rows(points)
    if sorted(r["name"] for r in found) != sorted(POINT_NAMES + ("graveyard",)):
        raise ValueError("world_hub_points.csv needs exactly spawn, town_portal, rift_exit and graveyard")
    spawn = next(r for r in found if r["name"] == "spawn")
    if any((r["map_id"], r["area_id"]) != (spawn["map_id"], spawn["area_id"]) for r in found):
        raise ValueError("The hub points and the graveyard must share one map and area")
    map_id, area_id = int(spawn["map_id"]), int(spawn["area_id"])
    spots = {r["name"]: reading(r, XYZO, "world_hub_points.csv " + r["name"], pending) for r in found}
    gate = seal.door_row(door)
    if (gate["map_id"], gate["area_id"]) != (map_id, area_id):
        raise ValueError("The Sanctum door must stand in the hub's map and area")
    rules = seal.rows(areas)
    seal.area_rule(map_id, area_id, areas)
    ruled = set()
    for rule in rules:
        key = (int(rule["map_id"]), int(rule["area_id"]))
        if key in ruled or rule["status"] not in ("open", "closed") or rule["phase_scope"] not in ("all", "tier", "campaign"):
            raise ValueError(f"world_areas.csv: a duplicate or invalid rule for {key}")
        ruled.add(key)

    managed, seen = [], set()
    sheet = seal.rows(placements)
    if sheet and set(sheet[0]) != PLACEMENT_HEADER:
        raise ValueError(f"world_hub_placements.csv needs exactly the columns {sorted(PLACEMENT_HEADER)}: the Sanctum has no tier copies")
    for source in sheet:
        kind, row = source["kind"], json.loads(source["placement"])
        guid = int(source["source_guid"])
        label = f"world_hub_placements.csv {kind}:{row.get('id')} (guid {guid})"
        if (kind not in TABLES or row["guid"] != guid or row["phaseMask"] != 1
                or (row["map"], row["areaId"], row["zoneId"]) != (map_id, area_id, area_id) or not source["source"]):
            raise ValueError(f"Invalid hub service source: {label}")
        place = reading(row, PLACE, label, pending)
        if kind == "g" and place and row["id"] not in SCENERY:
            for key, wanted in (("rotation2", math.sin(place["o"] / 2)), ("rotation3", math.cos(place["o"] / 2))):
                if row.get(key) is not None and abs(row[key] - wanted) > 1e-4:
                    raise ValueError(f"{label}: {key} is derived from the facing; leave the cell null or make it agree")
        managed.append(dict(kind=kind, entry=row["id"], guid=guid, base=row, place=place, source=source["source"], label=label))
    wanted = [(k, e) for k, entries in SERVICES.items() for e in entries] + [("c", DUMMY_ENTRY)] * DUMMY_COUNT + [("g", e) for e in SCENERY]
    if sorted((m["kind"], m["entry"]) for m in managed) != sorted(wanted):
        raise ValueError(f"world_hub_placements.csv needs exactly one row for each of the hub services and {DUMMY_COUNT} for the training dummy")

    cells = seal.rows(coffer)
    if len(cells) != 1 or set(cells[0]) != COFFER_HEADER or not cells[0]["placement_source"] or not cells[0]["guid_source"]:
        raise ValueError("Expected one sourced Tester's Coffer row in world_tester_coffer.csv")
    cell = cells[0]
    if (int(cell["map_id"]), int(cell["area_id"])) != (map_id, area_id):
        raise ValueError("The Tester's Coffer must stand in the hub's map and area")
    first = guid_block(int(cell["source_guid"]), "world_tester_coffer.csv source_guid")
    smith = [m for m in managed if (m["kind"], m["entry"]) == ("c", 910000)][0]
    respawn = int(smith["base"]["spawntimesecs"])  # the sourced hub-NPC respawn period, no new number
    if respawn <= 0:
        raise ValueError("The Blacksmith's respawn time must be positive")
    managed.append(dict(kind="c", entry=COFFER_ENTRY, guid=first,
                        base=dict(id=COFFER_ENTRY, spawnMask=1, spawntimesecs=respawn), source=cell["placement_source"] + "; GUIDs: " + cell["guid_source"],
                        place=reading(cell, XYZO, "world_tester_coffer.csv", pending), label="world_tester_coffer.csv", coffer=True))
    for m in managed:
        if (m["kind"], guid_block(m["guid"], m["label"])) in seen:
            raise ValueError(f"{m['label']}: GUID {m['guid']} is used twice")
        seen.add((m["kind"], m["guid"]))
    return dict(map_id=map_id, area_id=area_id, spots=spots, managed=managed, rules=rules), pending


def placed(m, plan):
    """The row the move writes: the placement's own fields, in the hub, at the position."""
    x, y, z, o = (m["place"][key] for key in XYZO)
    place = dict(zip(PLACE, (x, y, z, o)))
    if m["kind"] == "g" and m["entry"] not in SCENERY:
        place.update(rotation0=0.0, rotation1=0.0, rotation2=math.sin(o / 2), rotation3=math.cos(o / 2))
    return dict(m["base"], guid=m["guid"], phaseMask=1, map=plan["map_id"], zoneId=plan["area_id"], areaId=plan["area_id"], **place)


def one_line(text):
    return " ".join(text.split())


def generate(points=POINTS, placements=PLACEMENTS, coffer=COFFER, areas=AREAS, door=seal.DATA):
    plan, pending = load(points, placements, coffer, areas, door)
    if pending:
        raise ValueError("Hub positions still pending (card q-1003-39, applied by diablocraft-ftoz): " + "; ".join(pending))
    map_id, area_id, spots = plan["map_id"], plan["area_id"], plan["spots"]
    spawn, grave = spots["spawn"], spots["graveyard"]
    guards = ["EXISTS(SELECT 1 FROM dc_world_hub_point WHERE name='spawn')",
              f"NOT EXISTS(SELECT 1 FROM game_graveyard WHERE ID={GRAVEYARD_ID}) OR EXISTS(SELECT 1 FROM game_graveyard WHERE ID={GRAVEYARD_ID} AND Map={map_id})"]
    comment = f"Sanctum of Torment hub graveyard (diablocraft-976b, map {map_id} area {area_id})"
    statements = ["-- the area rules: the old hub closes, the Sanctum stays open (dc_world_areas has no key)"]
    for rule in plan["rules"]:
        key = f"`map_id`={int(rule['map_id'])} AND `area_id`={int(rule['area_id'])}"
        statements += [f"DELETE FROM `dc_world_areas` WHERE {key};",
                       insert("dc_world_areas", dict(map_id=int(rule["map_id"]), area_id=int(rule["area_id"]), phase_scope=rule["phase_scope"],
                                                     status=rule["status"], note=rule["note"]))]
    statements += ["-- new characters start at the spawn: every start row at the old hub (the spawn row as it is now) follows",
                   f"UPDATE playercreateinfo c JOIN dc_world_hub_point o ON o.name='spawn' SET c.map={map_id},c.zone={area_id},"
                   f"c.position_x={spawn['x']},c.position_y={spawn['y']},c.position_z={spawn['z']},c.orientation={spawn['o']} "
                   "WHERE c.map=o.map_id AND c.zone=o.area_id;",
                   "-- the named points the C++ reads at startup, and the hub row the race/class migrations read"]
    for name in POINT_NAMES:
        spot = spots[name]
        statements.append(f"REPLACE INTO dc_world_hub_point VALUES('{name}',{map_id},{area_id},{spot['x']},{spot['y']},{spot['z']},{spot['o']});")
    statements += ["REPLACE INTO dc_world_hub SELECT 1,map_id,area_id,x,y,z,o FROM dc_world_hub_point WHERE name='spawn';",
                   "-- the graveyard: a player who falls out of the world repops here; the stock link of area 4273 to graveyard 1384 stays "
                   "(the core prefers a graveyard on the player's own map)",
                   upsert("game_graveyard", dict(ID=GRAVEYARD_ID, Map=map_id, x=grave["x"], y=grave["y"], z=grave["z"], Comment=comment),
                          ["Map", "x", "y", "z", "Comment"]),
                   upsert("graveyard_zone", dict(ID=GRAVEYARD_ID, GhostZone=area_id, Faction=0, Comment=comment), ["Faction", "Comment"])]
    tome_size = tunable_positive("ui", "tome_scale_multiplier")
    statements += ["-- the Tome's template size (diablocraft-bb67, the designer's export line 44; ui.csv tome_scale_multiplier)",
                   f"UPDATE `gameobject_template` SET `size`={tome_size} WHERE `entry`={TOME_ENTRY};",
                   "-- the designer's editor leftovers the layout replaces (DEV_LEFTOVERS)"]
    statements += [f"DELETE FROM `gameobject` WHERE `guid`={guid} AND `id`={entry};" for guid, entry in DEV_LEFTOVERS]
    statements += [f"DELETE FROM `gameobject_template` WHERE `entry`={entry} AND NOT EXISTS(SELECT 1 FROM `gameobject` WHERE `id`={entry});"
                   for entry in DEV_LEFTOVER_TEMPLATES]
    after = [f"EXISTS(SELECT 1 FROM gameobject_template WHERE entry={TOME_ENTRY} AND ABS(size-({tome_size}))<0.000001)"]
    for m in plan["managed"]:
        kind, entry, table = m["kind"], m["entry"], TABLES[m["kind"]]
        guid = m["guid"]
        statements.append(f"-- {table} {entry} (source guid {guid}): {one_line(m['source'])}")
        if entry not in LATER_TEMPLATES:
            guards.append(f"EXISTS(SELECT 1 FROM {table}_template WHERE entry={entry})")
        guards.append(f"NOT EXISTS(SELECT 1 FROM {table} WHERE guid={guid}) OR EXISTS(SELECT 1 FROM {table} WHERE guid={guid} AND id={entry} AND phaseMask=1)")
        guards.append(f"NOT EXISTS(SELECT 1 FROM dc_area_spawn WHERE kind='{kind}' AND spawn_guid={guid})")
        statements.append(upsert_existing(table, placed(m, plan), MOVE[kind]))
        # the registry rows of this source under any key (the old hub's, a stale scan's, the old copies') go; the hub's one row is written again
        here = f"kind='{kind}' AND source_guid={guid}"
        statements += [f"DELETE FROM dc_area_spawn WHERE {here};", f"DELETE FROM dc_area_source WHERE {here};",
                       source_snapshot(table, kind, map_id, area_id, guid)]
        after.append(f"(SELECT COUNT(*) FROM {table} WHERE guid={guid} AND id={entry} AND phaseMask=1 AND map={map_id} AND areaId={area_id} AND zoneId={area_id})=1 "
                     f"AND (SELECT COUNT(*) FROM dc_area_source WHERE {here})=1 "
                     f"AND (SELECT COUNT(*) FROM dc_area_source WHERE {here} AND map_id={map_id} AND area_id={area_id} AND entry={entry})=1 "
                     f"AND (SELECT COUNT(*) FROM dc_area_spawn WHERE {here})=0")
    after += [f"(SELECT COUNT(*) FROM dc_world_hub_point WHERE name IN ('spawn','town_portal','rift_exit') AND map_id={map_id} AND area_id={area_id})=3",
              f"EXISTS(SELECT 1 FROM dc_world_hub WHERE id=1 AND map_id={map_id} AND area_id={area_id})",
              f"EXISTS(SELECT 1 FROM game_graveyard g JOIN graveyard_zone z ON z.ID=g.ID WHERE g.ID={GRAVEYARD_ID} AND g.Map={map_id} AND z.GhostZone={area_id})",
              f"EXISTS(SELECT 1 FROM dc_world_areas WHERE map_id={map_id} AND area_id={area_id} AND status='open' AND phase_scope='all')"]
    lines = ["-- Generated by generate_hub_sanctum_move.py from world_hub_points.csv, world_hub_placements.csv, world_tester_coffer.csv and "
             "world_areas.csv; never edit.",
             f"-- The hub moves to the Sanctum of Torment (map {map_id}, area {area_id}); the old hub's rules close. Positions are the designer's .gps "
             "readings (card q-1003-39, applied by diablocraft-ftoz).",
             "-- Moves existing rows (map, area, position only); inserts the rows that are not there yet. Apply to the world database with worldserver stopped.",
             "SET NAMES utf8mb4;",
             f"CREATE TEMPORARY TABLE {GUARD} (ok INT NOT NULL CHECK(ok=1));",
             "START TRANSACTION;"]
    lines += [f"INSERT INTO {GUARD} VALUES (({g}));" for g in guards]
    lines += statements
    lines += [f"INSERT INTO {GUARD} VALUES (({g}));" for g in after]
    lines += ["COMMIT;", f"DROP TEMPORARY TABLE {GUARD};", ""]
    return "\n".join(lines)


def migration_name(updates=UPDATES, suffix=SUFFIX, module_root=ROOT):
    """A rerun rewrites its own migration; the first run takes the next free world number, above any dev reserves."""
    mine = sorted(updates.glob("world_*" + suffix))
    if mine:
        return mine[-1].name
    numbers = [int(found.group(1)) for found in (re.match(r"world_(\d+)_", path.name) for path in updates.glob("world_*.sql")) if found]
    return f"world_{max(numbers + [reserved_number(module_root, 'world')]) + 1:04d}{suffix}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="migration file name (default: the existing one, else the next free world number)")
    args = parser.parse_args()
    try:
        sql = generate()
    except ValueError as error:
        raise SystemExit(str(error))
    name = args.name or migration_name()
    migration = UPDATES / name
    if migration.exists() and not migration.read_text(encoding="utf-8").startswith("-- Generated by generate_hub_sanctum_move.py"):
        raise SystemExit(name + " is already owned by another migration; choose the next free world number")
    write_migration(ROOT, migration, sql)
    write_coupled_outputs(ROOT, migration, sql, [(ROOT / "data/generated" / name, sql)], label="Sanctum hub move generated SQL mirror")
    print(name + ": the hub moved to the Sanctum, the old hub closed")


if __name__ == "__main__":
    main()

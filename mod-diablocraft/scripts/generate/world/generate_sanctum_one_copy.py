#!/usr/bin/env python3
"""Generate the Sanctum's one-copy migration (diablocraft-k4ce): the nine extra copies of every hub thing go.

The Sanctum of Torment is ONE shared phase (docs/research/cross-tier-sanctum.md 3 and 4.3): every hub thing has a single row in phase 1, and
generate_hub_sanctum_move.py / generate_hub_sanctum_seal.py write nothing else. A database the old model touched still holds the tier 2-10
copies (the placement sheet's, bb67's and Kadala's included, the Tester's Coffer's and the door's); this migration deletes them:

  world_sanctum_retired_copies.csv   every retired copy GUID with its kind, entry and source (the sheet as it was at nightly 03e2946a)

For each copy it deletes the creature or gameobject row and its addon, formation, link, movement and sparring rows, then the registry row in
dc_area_spawn; every other copy the registry holds for the Sanctum goes the same way. The sources (phase 1) are never touched. It stops before
any write when a copy GUID holds another entry's row, a phase-1 row or a registered source. It stops after the writes (nothing is kept) when a
copy is left, the Sanctum's registry holds a copy, the registry would not load (a (kind, guid) owned twice, a tier outside 1..N: the core fails
closed on both, dc_world_areas.cpp:53-79) or a Sanctum source lost its phase-1 row.

Run with worldserver stopped, after world_0031 and world_0032:

    python3 mod-diablocraft/scripts/generate/world/generate_sanctum_one_copy.py [--name world_00NN_sanctum_one_copy.sql]
"""
import argparse
import csv
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration
from generate_area_copies import SIMPLE
from generate_hub_placements import launch_tier_count
import generate_hub_sanctum_move as move
import generate_hub_sanctum_seal as seal

ROOT = Path(__file__).resolve().parents[3]
RETIRED = ROOT / "data/d3/world_sanctum_retired_copies.csv"
COFFER = ROOT / "data/d3/world_tester_coffer.csv"
SUFFIX = "_sanctum_one_copy.sql"
GUARD, COPIES = "dc_sanctum_one_copy_guard", "dc_sanctum_retired_copy"
BASE = {"c": "creature", "g": "gameobject"}
HEADER = {"kind", "entry", "source_guid", "tier", "copy_guid", "source"}


def sources_now(placements=move.PLACEMENTS, coffer=COFFER, door=seal.DATA):
    """{(kind, source_guid): entry} for every thing that stands in the Sanctum now: the sheet's, the coffer's and the door's."""
    found = {}
    for row in seal.rows(placements):
        found[row["kind"], int(row["source_guid"])] = int(json.loads(row["placement"])["id"])
    found["c", int(seal.rows(coffer)[0]["source_guid"])] = move.COFFER_ENTRY
    found["g", int(seal.rows(door)[0]["source_guid"])] = int(seal.rows(door)[0]["entry"])
    return found


def load(retired=RETIRED, **now):
    """The retired copies as (kind, entry, source_guid, tier, copy_guid), checked against what stands now and the launch tiers."""
    tiers, live = launch_tier_count(), sources_now(**now)
    rows = seal.rows(retired)
    if not rows or set(rows[0]) != HEADER:
        raise ValueError(f"world_sanctum_retired_copies.csv needs the columns {sorted(HEADER)} and at least one row")
    found, taken, per_source = [], set(), {}
    for row in rows:
        if not row["source"]:
            raise ValueError("A retired copy needs its source note")
        try:
            kind, entry, source, tier, copy = row["kind"], int(row["entry"]), int(row["source_guid"]), int(row["tier"]), int(row["copy_guid"])
        except ValueError:
            raise ValueError(f"A retired copy has a cell that is not a whole number: {row}") from None
        if kind not in BASE or not 0 < copy < 2**32 or not 0 < source < 2**32 or not 2 <= tier <= tiers:
            raise ValueError(f"A retired copy is out of range (kind c/g, GUIDs, tiers 2..{tiers}): {row}")
        if (kind, copy) in taken:
            raise ValueError(f"Copy GUID {kind}:{copy} is retired twice")
        taken.add((kind, copy))
        if (kind, copy) in live:
            raise ValueError(f"Copy GUID {kind}:{copy} is a source that stands in the Sanctum now; a source is never retired")
        if live.get((kind, source), entry) != entry:
            raise ValueError(f"Retired group {kind}:{source} names entry {entry}, but the Sanctum's source is entry {live[kind, source]}")
        per_source.setdefault((kind, source), {})[tier] = entry
        found.append((kind, entry, source, tier, copy))
    for key, by_tier in per_source.items():
        if set(by_tier) != set(range(2, tiers + 1)) or len(set(by_tier.values())) != 1:
            raise ValueError(f"Retired group {key[0]}:{key[1]} must hold tiers 2..{tiers} of one entry")
    return found


def generate(retired=RETIRED, **now):
    copies = load(retired, **now)
    points = {r["name"]: r for r in seal.rows(seal.POINTS)}["spawn"]
    map_id, area_id, tiers = int(points["map_id"]), int(points["area_id"]), launch_tier_count()
    gone = f"{COPIES} r"
    guards = []
    for kind, table in BASE.items():
        guards += [f"NOT EXISTS(SELECT 1 FROM {table} s JOIN {gone} ON r.kind='{kind}' AND r.guid=s.guid WHERE s.id<>r.entry)",   # another entry's row
                   f"NOT EXISTS(SELECT 1 FROM {table} s JOIN {gone} ON r.kind='{kind}' AND r.guid=s.guid WHERE s.phaseMask=1)"]  # a source
    guards += [f"NOT EXISTS(SELECT 1 FROM dc_area_source s JOIN {gone} ON r.kind=s.kind AND r.guid=s.source_guid)",
               "NOT EXISTS(SELECT 1 FROM dc_area_spawn d JOIN dc_area_source s ON s.kind=d.kind AND s.source_guid=d.spawn_guid)"]
    statements = [f"-- every other copy the registry holds for the Sanctum goes with them (entry 0: no entry check; a source was refused above)",
                  f"INSERT IGNORE INTO {COPIES} SELECT kind,spawn_guid,0 FROM dc_area_spawn WHERE map_id={map_id} AND area_id={area_id};"]
    for kind, tables in SIMPLE.items():
        statements += [f"DELETE s FROM `{table}` s JOIN {gone} ON r.kind='{kind}' AND r.guid=s.`{key}`;" for table, key in tables.items()]
    statements += [f"DELETE s FROM creature_formations s JOIN {gone} ON r.kind='c' AND (r.guid=s.leaderGUID OR r.guid=s.memberGUID);",
                   f"DELETE s FROM linked_respawn s JOIN {gone} ON (r.kind=IF(s.linkType IN (0,1),'c','g') AND r.guid=s.guid) "
                   "OR (r.kind=IF(s.linkType IN (0,3),'c','g') AND r.guid=s.linkedGuid);"]
    statements += [f"DELETE s FROM {table} s JOIN {gone} ON r.kind='{kind}' AND r.guid=s.guid;" for kind, table in BASE.items()]
    statements.append(f"DELETE s FROM dc_area_spawn s JOIN {gone} ON r.kind=s.kind AND r.guid=s.spawn_guid;")
    after = [f"NOT EXISTS(SELECT 1 FROM {table} s JOIN {gone} ON r.kind='{kind}' AND r.guid=s.guid)" for kind, table in BASE.items()]
    after += [f"NOT EXISTS(SELECT 1 FROM dc_area_spawn WHERE map_id={map_id} AND area_id={area_id})",
              f"NOT EXISTS(SELECT 1 FROM dc_area_spawn s JOIN {gone} ON r.kind=s.kind AND r.guid=s.spawn_guid)",
              # what the core's registry loader checks (dc_world_areas.cpp): a tier in 1..N, no (kind, guid) owned twice
              f"NOT EXISTS(SELECT 1 FROM dc_area_spawn WHERE tier<1 OR tier>{tiers})",
              "NOT EXISTS(SELECT 1 FROM (SELECT kind,guid FROM (SELECT kind,source_guid guid FROM dc_area_source UNION ALL "
              "SELECT kind,spawn_guid FROM dc_area_spawn) o GROUP BY kind,guid HAVING COUNT(*)>1) d)",
              # every source of the Sanctum still stands, in phase 1
              f"NOT EXISTS(SELECT 1 FROM dc_area_source s WHERE s.map_id={map_id} AND s.area_id={area_id} AND NOT EXISTS("
              "SELECT 1 FROM creature c WHERE s.kind='c' AND c.guid=s.source_guid AND c.id=s.entry AND c.phaseMask=1) AND NOT EXISTS("
              "SELECT 1 FROM gameobject g WHERE s.kind='g' AND g.guid=s.source_guid AND g.id=s.entry AND g.phaseMask=1))"]
    values = ",".join(f"('{kind}',{copy},{entry})" for kind, entry, _, _, copy in copies)
    lines = ["-- Generated by generate_sanctum_one_copy.py from world_sanctum_retired_copies.csv, world_hub_placements.csv, world_tester_coffer.csv, "
             "world_sanctum_seal.csv and world_hub_points.csv; never edit.",
             f"-- The Sanctum of Torment (map {map_id}, area {area_id}) is one shared phase: its {len(copies)} tier 2-{tiers} copies go, with their addon, "
             "formation, link and registry rows. The sources (phase 1) stay. Apply to the world database with worldserver stopped.",
             "SET NAMES utf8mb4;",
             f"CREATE TEMPORARY TABLE {GUARD} (ok INT NOT NULL CHECK(ok=1));",
             f"CREATE TEMPORARY TABLE {COPIES} (kind CHAR(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, guid INT UNSIGNED NOT NULL, entry INT UNSIGNED NOT NULL, PRIMARY KEY(kind,guid));",
             f"INSERT INTO {COPIES} VALUES {values};",
             "START TRANSACTION;"]
    lines += [f"INSERT INTO {GUARD} VALUES (({g}));" for g in guards]
    lines += statements
    lines += [f"INSERT INTO {GUARD} VALUES (({g}));" for g in after]
    lines += ["COMMIT;", f"DROP TEMPORARY TABLE {GUARD};", f"DROP TEMPORARY TABLE {COPIES};", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="migration file name (default: the existing one, else the next free world number)")
    args = parser.parse_args()
    try:
        sql = generate()
    except ValueError as error:
        raise SystemExit(str(error))
    name = args.name or move.migration_name(move.UPDATES, SUFFIX)
    migration = move.UPDATES / name
    if migration.exists() and not migration.read_text(encoding="utf-8").startswith("-- Generated by generate_sanctum_one_copy.py"):
        raise SystemExit(name + " is already owned by another migration; choose the next free world number")
    write_migration(ROOT, migration, sql)
    write_coupled_outputs(ROOT, migration, sql, [(ROOT / "data/generated" / name, sql)], label="Sanctum one-copy generated SQL mirror")
    print(name + ": the Sanctum's tier copies removed")


if __name__ == "__main__":
    main()

# Constant (audit 148, 1.0): Default stock-rank/AutoBalance health bound; Overflow-check input only; does not set creature scaling.
# Constant (audit 151, 18446744073709551615): Safe maximum scaled creature health, the 64-bit Life pool's (diablocraft-12in); Representation guard.
# Constant (audit 152, 4294967295): Maximum generated spawn GUID; Unsigned 32-bit storage bound.
"""Generate tier copies from one server-resolved open-area snapshot. Standard library only.

Run `dc areas scan MAP AREA` in the server console, stop worldserver, then run this
script with --mysql, --defaults-file, --map and --area. Apply its SQL before restart.
Credentials stay in the MySQL defaults file. No database changes are made here.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration
from tunable_values import integer as tunable_integer
import argparse
import csv
import json
import math
from pathlib import Path
import subprocess


SIMPLE = {
    "c": {"creature_addon": "guid", "creature_movement_override": "SpawnId",
          "creature_multispawn": "spawnId", "creature_sparring": "GUID",
          "vehicle_accessory": "guid"},
    "g": {"gameobject_addon": "guid"},
}
BASE = {"c": "creature", "g": "gameobject"}


def literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "CONVERT(X'" + value.encode("utf-8").hex() + "' USING utf8mb4)"
    if isinstance(value, (int, float)) and math.isfinite(value):
        return str(value)
    raise ValueError(f"Cannot convert SQL value: {value!r}")


def insert(table, row):
    return (f"INSERT INTO `{table}` (" + ",".join(f"`{k}`" for k in row) + ") VALUES ("
            + ",".join(literal(v) for v in row.values()) + ");")


class Database:
    def __init__(self, mysql, defaults, name):
        if not name.replace("_", "").isalnum():
            raise ValueError("Invalid database name")
        self.name = name
        self.args = [mysql, "--defaults-file=" + str(Path(defaults).resolve()),
                     "--no-login-paths", "--batch", "--raw", "--skip-column-names", name]

    def query(self, sql):
        return subprocess.check_output(self.args, input=sql, text=True, encoding="utf-8").splitlines()

    def rows(self, table, where="1", order=""):
        columns = self.query("SELECT COLUMN_NAME FROM information_schema.columns WHERE "
                             f"TABLE_SCHEMA='{self.name}' AND TABLE_NAME='{table}' ORDER BY ORDINAL_POSITION")
        if not columns:
            raise ValueError(f"Missing table {table}")
        pairs = ",".join(f"'{col}',s.`{col}`" for col in columns)
        return [json.loads(line) for line in self.query(
            f"SELECT JSON_OBJECT({pairs}) FROM `{table}` s WHERE {where} " + order)]


def hub_key():
    """The hub's (map, area), from the live points sheet: the Sanctum is one shared phase and never takes tier copies (diablocraft-k4ce)."""
    with (Path(__file__).resolve().parents[3] / "data/d3/world_hub_points.csv").open(encoding="utf-8-sig", newline="") as stream:
        spawn = next(r for r in csv.DictReader(stream) if r["name"] == "spawn")
    return int(spawn["map_id"]), int(spawn["area_id"])


def generate(db, map_id, area_id, extra_health_multiplier=1.0):
    if (map_id, area_id) == hub_key():
        raise ValueError(f"Area {map_id}:{area_id} is the hub, one shared phase: it takes no tier copies")
    scope = f"map_id={map_id} AND area_id={area_id}"
    rules = db.rows("dc_world_areas", scope)
    if len(rules) != 1 or rules[0]["status"] != "open" or rules[0]["phase_scope"] not in ("all", "tier"):
        raise ValueError(f"Area {map_id}:{area_id} is not open for launch tiers: {rules}")
    sources = db.rows("dc_area_source", scope, "ORDER BY kind,source_guid")
    if not sources:
        raise ValueError("No resolved source snapshot. Run dc areas scan MAP AREA first.")
    owned = db.rows("dc_area_spawn", scope, "ORDER BY kind,source_guid,tier")
    old = {(r["kind"], r["source_guid"], r["tier"]): r["spawn_guid"] for r in owned}
    next_id = {k: int(db.query(f"SELECT COALESCE(MAX(guid),0) FROM {t}")[0]) for k, t in BASE.items()}
    mapping, originals, children = {}, {}, {}
    ids = {k: {r["source_guid"] for r in sources if r["kind"] == k} for k in BASE}
    if not math.isfinite(extra_health_multiplier) or extra_health_multiplier < 1:
        raise ValueError("Extra health multiplier must be finite and at least one")
    # Stock rank rates and AB normal/boss defaults are 1.0. Supply an upper
    # bound here if configured otherwise; runtime checks the exact multiplier too.
    health_rows = db.query(f"SELECT s.source_guid,t.entry,MAX(CEIL(CASE t.exp WHEN 0 THEN b.basehp0 WHEN 1 THEN b.basehp1 WHEN 2 THEN b.basehp2 END*t.HealthModifier)) "
        "FROM dc_area_source s JOIN creature_template t ON t.entry=s.entry "
        "OR t.entry IN (SELECT entry FROM creature_multispawn WHERE spawnId=s.source_guid) "
        "JOIN creature_classlevelstats b ON b.class=t.unit_class AND b.level BETWEEN t.minlevel AND t.maxlevel "
        f"WHERE s.map_id={map_id} AND s.area_id={area_id} AND s.kind='c' AND t.ScriptName<>'npc_training_dummy' GROUP BY s.source_guid,t.entry")
    launch_tiers = tunable_integer("monsters", "launch_tier_count", minimum=1)
    tier_rows = db.query("SELECT t.tier,t.monster_health_multiplier_pct FROM dc_difficulty_tiers t JOIN dc_tier_phase p ON p.tier_name=t.tier ORDER BY p.tier_id")
    party = float(db.query("SELECT MAX(monster_life_multiplier_pct) FROM dc_party_scaling WHERE context='open_world'")[0]) / 100
    if len(tier_rows) != launch_tiers or not math.isfinite(party) or party < 1:
        raise ValueError("Expected configured launch tiers and valid open-world party scaling")
    for health_row in health_rows:
        guid, entry, baseline = health_row.split('\t')
        for tier_row in tier_rows:
            tier, pct = tier_row.split('\t')
            life = math.floor(max(1, float(baseline)) * float(pct) / 100 * party * extra_health_multiplier)
            if life < 1 or life > 2**64 - 1:
                raise ValueError(f"Life overflow: spawn={guid} entry={entry} tier={tier} baseline={baseline} max_party_life={life}")
    guard = [f"EXISTS(SELECT 1 FROM dc_world_areas WHERE {scope} AND status='open' AND phase_scope IN ('all','tier'))",
             f"(SELECT COUNT(*) FROM dc_area_source WHERE {scope})={len(sources)}"]
    for source in sources:
        kind, guid = source["kind"], source["source_guid"]
        if kind not in BASE or source["source_phase"] & 1 == 0:
            raise ValueError(f"Invalid baseline source: {source}")
        table = BASE[kind]
        match = (f"s.guid={guid} AND s.map=a.map_id AND s.id=a.entry AND s.phaseMask=a.source_phase "
                 "AND s.position_x=a.position_x AND s.position_y=a.position_y AND "
                 "s.position_z=a.position_z AND s.orientation=a.orientation")
        valid = (f"SELECT COUNT(*) FROM {table} s JOIN dc_area_source a ON a.kind='{kind}' "
                 f"AND a.source_guid=s.guid WHERE a.map_id={map_id} AND a.area_id={area_id} AND {match}")
        if db.query(valid) != ["1"]:
            raise ValueError(f"Source changed since area scan; rescan before generating: {source}")
        guard.append(f"({valid})=1")
        row = db.rows(table, f"guid={guid}")[0]
        originals[kind, guid] = row
        children[kind, guid] = {t: db.rows(t, f"`{key}`={guid}") for t, key in SIMPLE[kind].items()}
        # These relationships need a deliberate area-contained policy before an area
        # using them can open. Fail with the actual row; never copy an entire pool/map.
        unsupported = {"pool_" + table: f"guid={guid}",
                       "game_event_" + table: f"guid={guid}",
                       "spawn_group": f"spawnType={0 if kind=='c' else 1} AND spawnId={guid}",
                       "smart_scripts": f"source_type={0 if kind=='c' else 1} AND entryorguid=-{guid}",
                       "conditions": f"SourceTypeOrReferenceId=22 AND SourceId={0 if kind=='c' else 1} AND SourceEntry=-{guid}"}
        if kind == "c":
            unsupported.update({t: f"guid={guid}" for t in (
                "game_event_model_equip", "game_event_npc_vendor", "game_event_npcflag")})
        for related, predicate in unsupported.items():
            rows = db.rows(related, predicate)
            if rows:
                raise ValueError(f"Unsupported area relationship {related}: {rows[0]}")
        fixed_conditions = db.rows("conditions", f"ConditionTypeOrReference=31 AND ConditionValue1={3 if kind=='c' else 5} AND ConditionValue3={guid}")
        if fixed_conditions:
            raise ValueError(f"Condition references a fixed spawn GUID: {fixed_conditions[0]}")
        # Template scripts with fixed GUID targets would still target another tier.
        for script in db.rows("smart_scripts", f"source_type={0 if kind=='c' else 1} AND entryorguid={row['id']} AND target_type IN (10,14)"):
            raise ValueError(f"Template script has a fixed spawn GUID target: {script}")
        for tier in range(2, launch_tiers + 1):
            key = kind, guid, tier
            if key in old:
                dest = old[key]
            else:
                next_id[kind] += 1
                dest = next_id[kind]
            if dest > 4294967295:
                raise ValueError(f"Spawn GUID overflow: {key}")
            if dest in ids[kind]:
                raise ValueError(f"Owned copy overlaps an original source: {key} -> {dest}")
            mapping[key] = dest
            guard.append(f"NOT EXISTS(SELECT 1 FROM {table} WHERE guid={dest}) OR EXISTS(SELECT 1 FROM dc_area_spawn WHERE {scope} AND kind='{kind}' AND source_guid={guid} AND tier={tier} AND spawn_guid={dest})")

    def mapped(kind, guid, tier, row):
        if guid not in ids[kind]:
            raise ValueError(f"Cross-area placement relationship: {row}")
        return mapping[kind, guid, tier]

    extra = []
    cids = ",".join(map(str, sorted(ids["c"]))) or "0"
    for row in db.rows("creature_formations", f"leaderGUID IN ({cids}) OR memberGUID IN ({cids})", "ORDER BY leaderGUID,memberGUID"):
        for tier in range(2, launch_tiers + 1):
            extra.append(insert("creature_formations", dict(row,
                leaderGUID=mapped("c", row["leaderGUID"], tier, row),
                memberGUID=mapped("c", row["memberGUID"], tier, row))))
    # Link type encodes the source and destination object kinds.
    all_ids = ",".join(map(str, sorted(ids["c"] | ids["g"]))) or "0"
    for row in db.rows("linked_respawn", f"guid IN ({all_ids}) OR linkedGuid IN ({all_ids})", "ORDER BY guid,linkType"):
        typ = row["linkType"]
        if typ not in range(4):
            raise ValueError(f"Unknown respawn link type: {row}")
        a, b = ("c" if typ in (0, 1) else "g"), ("c" if typ in (0, 3) else "g")
        if row["guid"] not in ids[a] and row["linkedGuid"] not in ids[b]:
            continue
        for tier in range(2, launch_tiers + 1):
            extra.append(insert("linked_respawn", dict(row,
                guid=mapped(a, row["guid"], tier, row), linkedGuid=mapped(b, row["linkedGuid"], tier, row))))

    out = [f"-- Generated by generate_area_copies.py for open area {map_id}:{area_id}; never edit.",
           "-- Stop worldserver before applying. Original phase-1 placements are retained.",
           "CREATE TEMPORARY TABLE dc_area_guard (ok INT CHECK(ok=1));", "START TRANSACTION;"]
    # All checks precede mutation. A stale source or newly occupied GUID aborts SQL.
    out += [f"INSERT INTO dc_area_guard VALUES (({test}));" for test in guard]
    owned_scope = f"m.map_id={map_id} AND m.area_id={area_id}"
    for kind, tables in SIMPLE.items():
        for table, key in tables.items():
            out.append(f"DELETE s FROM `{table}` s JOIN dc_area_spawn m ON m.kind='{kind}' AND m.spawn_guid=s.`{key}` WHERE {owned_scope};")
    for col in ("leaderGUID", "memberGUID"):
        out.append(f"DELETE s FROM creature_formations s JOIN dc_area_spawn m ON m.kind='c' AND m.spawn_guid=s.{col} WHERE {owned_scope};")
    for col, types in (("guid", "0,1"), ("linkedGuid", "0,3")):
        out.append(f"DELETE s FROM linked_respawn s JOIN dc_area_spawn m ON m.kind=IF(s.linkType IN ({types}),'c','g') AND m.spawn_guid=s.{col} WHERE {owned_scope};")
    for kind, table in BASE.items():
        out.append(f"DELETE s FROM {table} s JOIN dc_area_spawn m ON m.kind='{kind}' AND m.spawn_guid=s.guid WHERE {owned_scope};")
    out.append(f"DELETE FROM dc_area_spawn WHERE {scope};")
    for (kind, guid, tier), dest in mapping.items():
        row = dict(originals[kind, guid], guid=dest, phaseMask=tier, areaId=area_id)
        out.append(insert(BASE[kind], row))
        out.append(insert("dc_area_spawn", dict(map_id=map_id, area_id=area_id,
            kind=kind, source_guid=guid, tier=tier, spawn_guid=dest)))
        for table, rows in children[kind, guid].items():
            for child in rows:
                out.append(insert(table, dict(child, **{SIMPLE[kind][table]: dest})))
    out += extra + ["COMMIT;", "DROP TEMPORARY TABLE dc_area_guard;", ""]
    return "\n".join(out), len(sources), len(mapping)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysql", required=True)
    parser.add_argument("--defaults-file", required=True)
    parser.add_argument("--database", default="acore_world")
    parser.add_argument("--map", type=int, required=True, dest="map_id")
    parser.add_argument("--area", type=int, required=True, dest="area_id")
    parser.add_argument("--extra-health-multiplier", type=float, default=1.0,
                        help="Upper bound on configured stock rank and AutoBalance health modifiers (defaults: 1)")
    args = parser.parse_args()
    if min(args.map_id, args.area_id) < 0 or max(args.map_id, args.area_id) > 4294967295:
        parser.error("Map and area must be unsigned 32-bit integers")
    sql, sources, copies = generate(Database(args.mysql, args.defaults_file, args.database), args.map_id, args.area_id, args.extra_health_multiplier)
    module = Path(__file__).resolve().parents[3]
    data = module / "data"
    name = f"difficulty_area_{args.map_id}_{args.area_id}.sql"
    generated = data / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / name).write_text(sql, encoding="utf-8", newline="\n")
    write_migration(module, data / "sql/db-world/updates" / name, sql)
    print(f"Area {args.map_id}:{args.area_id}: {sources} originals, {copies} copies; {name}")


if __name__ == "__main__":
    main()

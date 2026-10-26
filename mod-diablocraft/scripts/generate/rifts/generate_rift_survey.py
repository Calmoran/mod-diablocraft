#!/usr/bin/env python3
"""The survey of the rift dungeons (diablocraft-7vhj, docs/proposals/monster-spawning.md section 3.5.1, Part S0).

    python3 mod-diablocraft/scripts/generate/rifts/generate_rift_survey.py                      # sheets -> rift_survey_0001.sql (offline)
    python3 mod-diablocraft/scripts/generate/rifts/generate_rift_survey.py --survey [--force]   # world database + navmesh -> sheets
    python3 mod-diablocraft/scripts/generate/rifts/generate_rift_survey.py --export --mysql M --defaults-file D   # dev tables -> sheets

For each of the 30 recommended rows of rift_dungeons.csv (no hand placement), the survey:
  1. reads the `creature` rows on the row's map, in the world database the core loads, that spawn in normal difficulty;
  2. keeps the combatants: not a critter, a trigger or unselectable, and hostile to players of both teams by the faction table
     (FactionTemplate.dbc, the core's own rule);
  3. keeps the row's part of the map: the natives the navmesh reaches from the row's entry point;
  4. makes packs of the natives in one stock formation or within `pack_link_yards` on one floor; a pack's anchor is the
     native nearest its centre, a stock position;
  5. makes areas of anchors by walking distance, at most `area_max_yards` across;
  6. tags each area S, M or L by the natives it holds;
  7. ties each stock patrol path to the anchor nearest its first point;
  8. finds the exit point rift floors falls back on: the reachable ground farthest from the entry by walking distance;
  9. writes the report: today's natives against the expected bodies, elite packs and solos.

Sheets (data/d3/, the sheet is the source; `source` is `survey` or `alex`): rift_areas, rift_anchors, rift_routes,
rift_native_filter, rift_exit_points. The knobs are data/tunables/rift_survey.csv (the report's estimate reads the spawn sheets: area_defaults.csv, cluster_recipes.csv, rifts.csv). The report is
data/generated/rift_survey_report.csv. The default run turns the sheets into the migration rift_survey_0001.sql and its
mirror; it needs no database. `--survey` refuses while a sheet holds a row of the designer's (`source` alex) unless `--force`;
`--export` brings his edits from the dev world database's tables into the sheets (Parts S4, S5 write them there; rift floors F2's
`.dc floor exit here` writes dc_rift_exit_spot, which replaces the survey's far point of that dungeon in rift_exit_points.csv).

Pylons and shrines (Part P4, diablocraft-0x640, docs/proposals/pylons.md 6.6): rift_pylon_spots.csv holds one spot at the centre of each M and L area (the
area's anchor nearest the centre of its anchors, so a spot is on the ground), with the walk from the entry point the anchor has. `--survey` (and
`--pylon-spots`, offline, from the committed area and anchor sheets) writes it; the designer adds, moves and removes spots with `.dc pylon spot`, which edit
dc_rift_pylon_spot, and `--export` brings that table home like the others. Its migration is its own, rift_pylon_spot_0002.sql (0001 is applied and frozen), so the survey's
migration (and any anchor edit of the designer's it would re-apply over) is not touched.
"""
import argparse
import collections
import csv
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration  # noqa: E402
from generate_area_copies import Database  # noqa: E402
from generate_rifts import quote  # noqa: E402
import rift_navmesh  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
D3 = MODULE / "data/d3"
KNOBS = MODULE / "data/tunables/rift_survey.csv"
SPAWN_SHEETS = MODULE / "data/tunables"   # the spawn sheets (diablocraft-dt7c) own the estimate's figures
# rift_survey_0001 and 0002 are applied (update 9, applied_migrations.csv) and frozen; the renders ship as the next pair.
# Each is a whole, idempotent render, so the new pair simply runs after the old one. rift_survey_0004 is merged and applied on
# dev, so it is frozen too: the open zones' exit points (yh7el) shipped as rift_survey_0005, which re-rendered the zones whole;
# 0005 is applied too, so the zones' rerun at the designer's spacing and area cap (71kk3) ships as rift_survey_0006.
NAME = "rift_survey_0003.sql"
OPEN_NAME = "rift_survey_0006.sql"
OPEN_ZONES = "rift_open_zones.csv"
PYLON_SHEET = "rift_pylon_spots.csv"
# rift_pylon_spot_0001 is applied and frozen; the spots after the open zones' rerun at the designer's spacing and area cap (71kk3) ship as 0002,
# the whole table again (an idempotent replace), so it simply runs after the first.
PYLON_NAME = "rift_pylon_spot_0002.sql"
PYLON_COLUMNS = ("dungeon", "spot", "area", "x", "y", "z", "o", "entry_walk_yards", "source")
PYLON_TABLE = ("dc_rift_pylon_spot", "`dungeon` VARCHAR(64) NOT NULL, `spot` INT UNSIGNED NOT NULL, `area` INT UNSIGNED NOT NULL, "
               "`x` DOUBLE NOT NULL, `y` DOUBLE NOT NULL, `z` DOUBLE NOT NULL, `o` DOUBLE NOT NULL, `entry_walk_yards` DOUBLE NULL, "
               "`source` VARCHAR(8) NOT NULL, PRIMARY KEY (`dungeon`, `spot`)")
PYLON_TAGS = ("M", "L")   # 6.6: a spot at the centre of each M and L area (the plan's identity, not a tunable)
REPORT = MODULE / "data/generated/rift_survey_report.csv"
# Constants (identities of the core's data, not tunables): the unit and creature flags the combatant filter reads
# (Unit.h UNIT_FLAG_NOT_SELECTABLE, CreatureData flags_extra CREATURE_FLAG_EXTRA_TRIGGER, creature type CREATURE_TYPE_CRITTER),
# the normal-difficulty spawn bit (rifts use DUNGEON_DIFFICULTY_NORMAL, dc_rifts.cpp), the two playable faction templates
# a creature must be hostile to both of (FactionTemplate.dbc 1 Human, 2 Orc), and the dungeon rows in use.
UNIT_NOT_SELECTABLE, EXTRA_TRIGGER, TYPE_CRITTER, SPAWN_NORMAL = 0x02000000, 128, 8, 1
PLAYER_FACTION_TEMPLATES = (1, 2)

SHEETS = {
    "rift_areas.csv": ("dungeon", "area", "tag", "natives", "density_min", "density_max", "nospawn", "source"),
    "rift_anchors.csv": ("dungeon", "anchor", "area", "x", "y", "z", "o", "pack_size", "native_guid", "native_entry",
                         "entry_walk_yards", "source"),
    "rift_routes.csv": ("dungeon", "path_id", "anchor", "start_x", "start_y", "start_z", "points", "length_yards", "source"),
    "rift_native_filter.csv": ("map_id", "spawn_guid", "dungeon", "anchor"),
    "rift_exit_points.csv": ("dungeon", "x", "y", "z", "o", "walk_yards", "source"),
}
# The tables the migration makes: one per sheet, with the column types the sheets need.
TABLES = {
    "rift_areas.csv": ("dc_rift_area", "`dungeon` VARCHAR(64) NOT NULL, `area` INT UNSIGNED NOT NULL, `tag` CHAR(1) NOT NULL, "
                       "`natives` INT UNSIGNED NOT NULL, `density_min` INT UNSIGNED NULL, `density_max` INT UNSIGNED NULL, "
                       "`nospawn` TINYINT UNSIGNED NOT NULL, `source` VARCHAR(8) NOT NULL, PRIMARY KEY (`dungeon`, `area`)"),
    "rift_anchors.csv": ("dc_rift_anchor", "`dungeon` VARCHAR(64) NOT NULL, `anchor` INT UNSIGNED NOT NULL, `area` INT UNSIGNED NOT NULL, "
                         "`x` DOUBLE NOT NULL, `y` DOUBLE NOT NULL, `z` DOUBLE NOT NULL, `o` DOUBLE NOT NULL, "
                         "`pack_size` INT UNSIGNED NOT NULL, `native_guid` INT UNSIGNED NULL, `native_entry` INT UNSIGNED NULL, "
                         "`entry_walk_yards` DOUBLE NULL, `source` VARCHAR(8) NOT NULL, PRIMARY KEY (`dungeon`, `anchor`)"),
    "rift_routes.csv": ("dc_rift_route", "`dungeon` VARCHAR(64) NOT NULL, `path_id` INT UNSIGNED NOT NULL, `anchor` INT UNSIGNED NOT NULL, "
                        "`start_x` DOUBLE NOT NULL, `start_y` DOUBLE NOT NULL, `start_z` DOUBLE NOT NULL, `points` INT UNSIGNED NOT NULL, "
                        "`length_yards` DOUBLE NOT NULL, `source` VARCHAR(8) NOT NULL, PRIMARY KEY (`dungeon`, `path_id`)"),
    "rift_native_filter.csv": ("dc_rift_native_filter", "`map_id` INT UNSIGNED NOT NULL, `spawn_guid` INT UNSIGNED NOT NULL, "
                               "`dungeon` VARCHAR(64) NOT NULL, `anchor` INT UNSIGNED NOT NULL, PRIMARY KEY (`map_id`, `spawn_guid`)"),
    "rift_exit_points.csv": ("dc_rift_exit_point", "`dungeon` VARCHAR(64) NOT NULL, `x` DOUBLE NOT NULL, `y` DOUBLE NOT NULL, "
                             "`z` DOUBLE NOT NULL, `o` DOUBLE NOT NULL, `walk_yards` DOUBLE NULL, `source` VARCHAR(8) NOT NULL, "
                             "PRIMARY KEY (`dungeon`)"),
}
REPORT_COLUMNS = ("dungeon", "map_id", "spawn_rows", "combatants_on_map", "natives_today", "off_navmesh", "other_part", "anchors",
                  "areas_s", "areas_m", "areas_l", "expected_anchors", "expected_bodies", "bodies_vs_today", "expected_elite_packs",
                  "expected_solos", "anchors_with_route", "anchors_near_entry", "exit_walk_yards")


# -- sheets --------------------------------------------------------------------------------------------------------------

def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def write_csv(path, columns, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows([[row[c] for c in columns] for row in rows])


def read_knobs(path=KNOBS, spawn=SPAWN_SHEETS):
    """{name: float, or None for a row the designer has not set}. The survey's own inputs come from rift_survey.csv; the figures of the
    report's estimate belong to the spawn sheets (Part S1) and are read from them: the area defaults (density_<tag>_min/_max,
    allow_<tag>_<size>), the cluster sizes (size_<size>_min/_max) and three rifts.csv knobs."""
    out = {}
    for row in read_csv(path):
        out[row["name"]] = float(row["value"]) if row["value"].strip() else None
    for row in read_csv(Path(spawn) / "area_defaults.csv"):
        t = row["tag"].lower()
        out[f"density_{t}_min"], out[f"density_{t}_max"] = float(row["anchors_min"]), float(row["anchors_max"])
        for size in ("small", "medium", "large"):
            out[f"allow_{t}_{size}"] = row[size] == "yes"
    for row in read_csv(Path(spawn) / "cluster_recipes.csv"):
        if not row["family"].strip() and row["size"] != "patrol":
            out[f"size_{row['size']}_min"], out[f"size_{row['size']}_max"] = float(row["bodies_min"]), float(row["bodies_max"])
    rifts = {r["name"]: r["value"].strip() for r in read_csv(Path(spawn) / "rifts.csv")}
    for name in ("elite_chance_pct", "solo_share_pct", "entry_clear_yards", "open_zone_spacing_yards", "open_zone_area_max_yards"):
        out[name] = float(rifts[name]) if rifts[name] else None
    return out


def dungeons():
    """The 30 recommended rows of rift_dungeons.csv, in sheet order."""
    return [r for r in read_csv(D3 / "rift_dungeons.csv") if r["recommended"].strip().lower() == "yes"]


def read_sheets(directory=None, missing_ok=False):
    directory = directory or D3
    return {name: (read_csv(Path(directory) / name) if (Path(directory) / name).exists() or not missing_ok else []) for name in SHEETS}


def open_zone_names(directory=None):
    """The names of the open zones (rift_open_zones.csv, Part S6). Their rows share the sheets above with the dungeons', but
    come from generate_open_zone_survey.py and fill their own migration, rift_survey_0002.sql."""
    path = Path(directory or D3) / OPEN_ZONES
    return {row["name"] for row in read_csv(path)} if path.exists() else set()


def has_alex(sheets):
    return any(row.get("source") == "alex" for rows in sheets.values() for row in rows)


def read_pylon_spots(directory=None):
    path = Path(directory or D3) / PYLON_SHEET
    return read_csv(path) if path.exists() else []


def pylon_spots(sheets):
    """6.6: one spot at the centre of each M and L area: the area's anchor nearest the mean of its anchors (a spot is on the ground,
    as an anchor is), its walk from the entry point the anchor's own. Numbered from 1 per dungeon in area order, so a re-run gives the
    same sheet. Every dungeon and open zone of the area sheet gets its spots."""
    anchors = collections.defaultdict(list)
    for row in sheets["rift_anchors.csv"]:
        anchors[(row["dungeon"], row["area"])].append(row)
    out, counts = [], collections.Counter()
    for area in sheets["rift_areas.csv"]:
        members = anchors.get((area["dungeon"], area["area"]))
        if area["tag"] not in PYLON_TAGS or not members:
            continue
        mean = [sum(float(m[k]) for m in members) / len(members) for k in ("x", "y", "z")]
        centre = min(members, key=lambda m: (sum((float(m[k]) - c) ** 2 for k, c in zip(("x", "y", "z"), mean)), int(m["anchor"])))
        counts[area["dungeon"]] += 1
        out.append(dict(dungeon=area["dungeon"], spot=counts[area["dungeon"]], area=area["area"], x=centre["x"], y=centre["y"],
                        z=centre["z"], o=centre["o"], entry_walk_yards=centre["entry_walk_yards"], source="survey"))
    return out


def render_pylon_spots(rows):
    """rift_pylon_spot_0002.sql (0001 before it): the whole table, dungeons and open zones alike, replaced from the sheet."""
    table, definition = PYLON_TABLE
    names = ", ".join(f"`{c}`" for c in PYLON_COLUMNS)
    parts = ["-- Generated by generate_rift_survey.py from rift_pylon_spots.csv in data/d3 (diablocraft-0x640); never edit.",
             "-- The spots pylons and shrines may stand on (docs/proposals/pylons.md 6.6, Part P4). Dev edits (.dc pylon spot) come home through --export.",
             "SET NAMES utf8mb4;",
             f"CREATE TABLE IF NOT EXISTS `{table}` ({definition}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;", f"DELETE FROM `{table}`;"]
    for start in range(0, len(rows), 500):
        values = ",\n".join("(" + ", ".join(sql_value(r[c]) for c in PYLON_COLUMNS) + ")" for r in rows[start:start + 500])
        parts.append(f"INSERT INTO `{table}` ({names}) VALUES\n{values};")
    return "\n".join(parts) + "\n"


# -- the faction table -----------------------------------------------------------------------------------------------------

class Factions:
    """FactionTemplate.dbc: hostile to a player, by the core's FactionTemplateEntry::IsHostileTo."""

    def __init__(self, path):
        raw = Path(path).read_bytes()
        magic, count, fields, size, _ = struct.unpack_from("<4s4I", raw)
        if magic != b"WDBC" or fields != 14 or size != 56:
            raise ValueError(f"{path}: not a 3.3.5a FactionTemplate.dbc")
        self.rows = {}
        for n in range(count):
            r = struct.unpack_from("<14I", raw, 20 + n * size)
            self.rows[r[0]] = dict(faction=r[1], ours=r[3], friendly=r[4], hostile=r[5], enemies=r[6:10], friends=r[10:14])

    def hostile(self, template, other):
        a, b = self.rows.get(template), self.rows.get(other)
        if a is None or b is None or template == other:
            return False
        if b["faction"]:
            if b["faction"] in a["enemies"]:
                return True
            if b["faction"] in a["friends"]:
                return False
        return bool(a["hostile"] & b["ours"])

    def hostile_to_players(self, template):
        # Both: a creature friendly to one team (an Alliance guard that fights only Horde) is not a rift fighter.
        return all(self.hostile(template, p) for p in PLAYER_FACTION_TEMPLATES)


# -- the world database ------------------------------------------------------------------------------------------------------

def load_natives(db, maps, box=None):
    """[native dict] of every `creature` row on the maps, with its template and patrol path, ordered by guid. `box` is
    (x0, x1, y0, y1): only the rows inside it (a zone of a continent, not the continent's 30,000 rows)."""
    ids = ",".join(str(m) for m in sorted(maps))
    inside = f" AND c.position_x BETWEEN {box[0]} AND {box[1]} AND c.position_y BETWEEN {box[2]} AND {box[3]}" if box else ""
    query = (
        "SELECT JSON_OBJECT('guid',c.guid,'entry',c.id,'map',c.map,'x',c.position_x,'y',c.position_y,'z',c.position_z,"
        "'o',c.orientation,'spawn_mask',c.spawnMask,'phase_mask',c.phaseMask,'rank',t.`rank`,'type',t.type,"
        "'flags_extra',t.flags_extra,'unit_flags',t.unit_flags,'faction',t.faction,'name',t.name,"
        "'path_id',COALESCE(a.path_id,0)) FROM creature c JOIN creature_template t ON t.entry=c.id "
        f"LEFT JOIN creature_addon a ON a.guid=c.guid WHERE c.map IN ({ids}){inside} ORDER BY c.guid")
    return [json.loads(line) for line in db.query(query)]


def load_formations(db, guids):
    if not guids:
        return []
    ids = ",".join(str(g) for g in sorted(guids))
    return [tuple(int(v) for v in line.split("\t")) for line in db.query(
        f"SELECT leaderGUID, memberGUID FROM creature_formations WHERE memberGUID IN ({ids})")]


def load_paths(db, path_ids):
    out = {}
    if path_ids:
        ids = ",".join(str(p) for p in sorted(path_ids))
        for line in db.query(f"SELECT id, point, position_x, position_y, position_z FROM waypoint_data WHERE id IN ({ids}) ORDER BY id, point"):
            pid, point, x, y, z = line.split("\t")
            out.setdefault(int(pid), []).append((int(point), float(x), float(y), float(z)))
    return out


# -- the survey of one dungeon -----------------------------------------------------------------------------------------------

def combatant(native, factions):
    """None for a combatant, else the reason it is not one."""
    if not native["spawn_mask"] & SPAWN_NORMAL:
        return "not in normal difficulty"
    if not native["phase_mask"] & 1:
        return "not in the visible phase"
    if native["type"] == TYPE_CRITTER:
        return "critter"
    if native["flags_extra"] & EXTRA_TRIGGER:
        return "trigger"
    if native["unit_flags"] & UNIT_NOT_SELECTABLE:
        return "unselectable"
    if not factions.hostile_to_players(native["faction"]):
        return "not hostile to players"
    return None


def make_packs(natives, formations, knobs):
    """Natives in one formation, or within pack_link_yards on one floor, are one pack: [[native]], by lowest guid."""
    link, floor = knobs["pack_link_yards"], knobs["floor_tolerance_yards"]
    parent = list(range(len(natives)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        parent[find(i)] = find(j)

    index = {n["guid"]: i for i, n in enumerate(natives)}
    for leader, member in formations:
        if leader in index and member in index:
            join(index[leader], index[member])
    for i, a in enumerate(natives):
        for j in range(i + 1, len(natives)):
            b = natives[j]
            if abs(a["z"] - b["z"]) < floor and math.hypot(a["x"] - b["x"], a["y"] - b["y"]) <= link:
                join(i, j)
    groups = collections.defaultdict(list)
    for i, n in enumerate(natives):
        groups[find(i)].append(n)
    return sorted((sorted(g, key=lambda n: n["guid"]) for g in groups.values()), key=lambda g: g[0]["guid"])


def anchor_of(pack):
    """The native nearest the pack's centre, a stock position; the lowest guid on a tie."""
    cx, cy, cz = (sum(n[k] for n in pack) / len(pack) for k in "xyz")
    return min(pack, key=lambda n: (math.dist((n["x"], n["y"], n["z"]), (cx, cy, cz)), n["guid"]))


def make_areas(anchors, distance, cap):
    """Complete-linkage clusters of anchor indexes: every pair in a cluster is within `cap` walking yards.

    `distance(i, j)` is the walking yards between two anchors, inf when beyond the cap. Merges the closest pair
    first, ties by index, so the result is the same on every run."""
    import heapq
    clusters = {i: [i] for i in range(len(anchors))}
    link = {}
    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            d = distance(i, j)
            if d <= cap:
                link[(i, j)] = d
    heap = [(d, i, j) for (i, j), d in link.items()]
    heapq.heapify(heap)
    next_id = len(anchors)
    while heap:
        d, i, j = heapq.heappop(heap)
        if i not in clusters or j not in clusters:
            continue
        merged = next_id
        next_id += 1
        for k in list(clusters):
            if k in (i, j):
                continue
            a, b = link.get(tuple(sorted((i, k)))), link.get(tuple(sorted((j, k))))
            if a is not None and b is not None:
                link[(k, merged)] = max(a, b)
                heapq.heappush(heap, (max(a, b), k, merged))
        clusters[merged] = clusters.pop(i) + clusters.pop(j)
    return sorted((sorted(c) for c in clusters.values()), key=lambda c: c[0])


def tag_of(natives, knobs):
    return "L" if natives >= knobs["tag_large_min_natives"] else ("M" if natives >= knobs["tag_medium_min_natives"] else "S")


def survey_dungeon(row, natives, formations, paths, base, avoid, factions, knobs, extra=None, with_exit=True):
    """One dungeon row's anchors, areas, routes, exit point and counts, from the natives on its map.

    `base` is the map's navmesh and `avoid` the entry points (x, y, z) of the other dungeon rows on that map.
    An open zone (generate_open_zone_survey.py, Part S6) adds anchors that no native stands at: `extra(mesh, reached,
    anchors)` returns [{x, y, z, o, poly}] for the thin ground, and `with_exit` False leaves the exit point out (a zone has
    no end; its exit is the designer's spot)."""
    snap = (knobs["snap_xy_yards"], knobs["snap_z_yards"], knobs["snap_z_far_yards"])
    entry = (float(row["entry_x"]), float(row["entry_y"]), float(row["entry_z"]))
    start = base.locate(*entry, *snap)
    if start is None:
        raise ValueError(f"{row['name']}: the entry point is not on the navmesh")
    others = [p for p in (base.locate(*a, *snap) for a in avoid) if p is not None]
    mesh, reached = base.with_bridges(start, others, knobs["fragment_bridge_yards"])
    from_entry = mesh.distances(*entry, start)
    counts = collections.Counter()
    kept = []
    for n in natives:
        reason = combatant(n, factions)
        if reason:
            counts[reason] += 1
            continue
        counts["combatants_on_map"] += 1
        poly = mesh.locate(n["x"], n["y"], n["z"], *snap)
        if poly is None:
            counts["off_navmesh"] += 1
            continue
        if poly not in reached:
            counts["other_part_of_map"] += 1
            continue
        n = dict(n, poly=poly)
        kept.append(n)
    packs = make_packs(kept, formations, knobs)
    anchors = []
    for pack in packs:
        a = anchor_of(pack)
        anchors.append(dict(native=a, size=len(pack), members=[m["guid"] for m in pack], poly=a["poly"]))
    for spot in (extra(mesh, reached, anchors) if extra else []):
        anchors.append(dict(native=dict(spot, guid=None, entry=None), size=0, members=[], poly=spot["poly"]))
    cap = knobs["area_max_yards"]
    near = {}

    def distance(i, j):
        a, b = anchors[i], anchors[j]
        if i not in near:
            n = a["native"]
            near[i] = mesh.distances(n["x"], n["y"], n["z"], a["poly"], cap)
        n = b["native"]
        if a["poly"] == b["poly"]:
            return math.dist((a["native"]["x"], a["native"]["y"], a["native"]["z"]), (n["x"], n["y"], n["z"]))
        return mesh.reach(near[i], b["poly"], n["x"], n["y"], n["z"])

    clusters = make_areas(anchors, distance, cap)
    # Numbers: anchors by their native's guid, areas by their lowest anchor.
    order = sorted(range(len(anchors)), key=lambda i: (anchors[i]["native"]["guid"] is None, anchors[i]["native"]["guid"] or 0))
    anchor_id = {i: k + 1 for k, i in enumerate(order)}
    clusters.sort(key=lambda c: min(anchor_id[i] for i in c))
    area_rows, anchor_rows, area_of = [], [], {}
    for k, cluster in enumerate(clusters, start=1):
        natives_in = sum(anchors[i]["size"] for i in cluster)
        area_rows.append(dict(dungeon=row["name"], area=k, tag=tag_of(natives_in, knobs), natives=natives_in,
                              density_min="", density_max="", nospawn=0, source="survey"))
        for i in cluster:
            area_of[i] = k
    for i in order:
        a, n = anchors[i], anchors[i]["native"]
        walk = mesh.reach(from_entry, a["poly"], n["x"], n["y"], n["z"])
        anchor_rows.append(dict(dungeon=row["name"], anchor=anchor_id[i], area=area_of[i], x=round(n["x"], 4), y=round(n["y"], 4),
                                z=round(n["z"], 4), o=round(n["o"], 4), pack_size=a["size"], native_guid=n["guid"] or "",
                                native_entry=n["entry"] or "", entry_walk_yards=round(walk, 1), source="survey"))
    members = {m: anchor_id[i] for i, a in enumerate(anchors) for m in a["members"]}
    route_rows = routes_for(row, kept, anchor_rows, paths, knobs)
    return dict(areas=area_rows, anchors=anchor_rows, routes=route_rows, members=members, kept=kept, counts=counts,
                exit=exit_point(row, mesh, reached, from_entry, knobs) if with_exit else None)


def routes_for(row, kept, anchor_rows, paths, knobs):
    """Each stock patrol path of a kept native, tied to the anchor nearest its first point (one row per path)."""
    floor = knobs["floor_tolerance_yards"]
    out = {}
    for n in kept:
        pid = n["path_id"]
        if not pid or pid in out or pid not in paths or not anchor_rows:
            continue
        points = paths[pid]
        _, sx, sy, sz = points[0]
        near = [a for a in anchor_rows if abs(a["z"] - sz) < floor] or anchor_rows
        a = min(near, key=lambda a: (math.hypot(a["x"] - sx, a["y"] - sy), a["anchor"]))
        length = sum(math.dist(points[i][1:], points[i + 1][1:]) for i in range(len(points) - 1))
        out[pid] = dict(dungeon=row["name"], path_id=pid, anchor=a["anchor"], start_x=round(sx, 4), start_y=round(sy, 4),
                        start_z=round(sz, 4), points=len(points), length_yards=round(length, 1), source="survey")
    return [out[p] for p in sorted(out)]


def exit_point(row, mesh, reached, from_entry, knobs):
    """The reachable ground farthest from the entry by walking distance (rift-floors.md 4.4's fallback)."""
    best = None
    for index in sorted(reached):
        poly = mesh.polys[index]
        if not poly.ground or poly.slope > knobs["max_slope_degrees"]:
            continue
        d = mesh.reach(from_entry, index, poly.cx, poly.cy, poly.cz)
        if d < math.inf and (best is None or (d, -index) > best[0]):
            best = ((d, -index), index)
    if best is None:
        raise ValueError(f"{row['name']}: no ground to put an exit on")
    poly = mesh.polys[best[1]]
    return dict(dungeon=row["name"], x=round(poly.cx, 4), y=round(poly.cy, 4), z=round(poly.cz, 4), o=0, walk_yards=round(best[0][0], 1),
                source="survey")


def estimate(areas, anchors, routes, knobs):
    """The report row's expected figures from the area defaults and the cluster sizes (all the plan's starts)."""
    sizes = {k: (knobs[f"size_{k}_min"] + knobs[f"size_{k}_max"]) / 2 for k in ("small", "medium", "large")}
    allowed = {t: tuple(k for k in sizes if knobs[f"allow_{t.lower()}_{k}"]) for t in "SML"}
    filled = bodies = 0.0
    for a in areas:
        t = a["tag"].lower()
        mean = (knobs[f"density_{t}_min"] + knobs[f"density_{t}_max"]) / 2
        filled += mean
        bodies += mean * sum(sizes[s] for s in allowed[a["tag"]]) / len(allowed[a["tag"]])
    solo, elite = knobs["solo_share_pct"] / 100, knobs["elite_chance_pct"] / 100
    return filled, bodies, filled * (1 - solo) * elite, filled * solo


def report_row(row, result, spawn_rows, knobs):
    areas, counts = result["areas"], result["counts"]
    tags = collections.Counter(a["tag"] for a in areas)
    filled, bodies, elite, solos = estimate(areas, result["anchors"], result["routes"], knobs)
    today = len(result["kept"])
    clear = knobs.get("entry_clear_yards")
    return dict(dungeon=row["name"], map_id=row["map_id"], spawn_rows=spawn_rows, combatants_on_map=counts["combatants_on_map"],
                natives_today=today, off_navmesh=counts["off_navmesh"], other_part=counts["other_part_of_map"], anchors=len(result["anchors"]),
                areas_s=tags["S"], areas_m=tags["M"], areas_l=tags["L"], expected_anchors=round(filled, 1),
                expected_bodies=round(bodies), bodies_vs_today=round(bodies / today, 2) if today else "",
                expected_elite_packs=round(elite, 1), expected_solos=round(solos, 1),
                anchors_with_route=len({r["anchor"] for r in result["routes"]}),
                anchors_near_entry=sum(1 for a in result["anchors"] if clear and a["entry_walk_yards"] < clear) if clear else "",
                exit_walk_yards=result["exit"]["walk_yards"])


def survey_rows(rows, natives, formations, paths, mesh_of, factions, knobs):
    """Every dungeon row: {sheet name: [row]} and the report rows. A native belongs to the first row that reaches it."""
    sheets = {name: [] for name in SHEETS}
    report, claimed = [], {}
    for row in rows:
        map_id = int(row["map_id"])
        avoid = [(float(r["entry_x"]), float(r["entry_y"]), float(r["entry_z"])) for r in rows
                 if int(r["map_id"]) == map_id and r is not row]
        on_map = [n for n in natives if n["map"] == map_id and n["guid"] not in claimed]
        result = survey_dungeon(row, on_map, formations, paths, mesh_of(map_id), avoid, factions, knobs)
        for guid, anchor in result["members"].items():
            claimed[guid] = row["name"]
            sheets["rift_native_filter.csv"].append(dict(map_id=map_id, spawn_guid=guid, dungeon=row["name"], anchor=anchor))
        sheets["rift_areas.csv"] += result["areas"]
        sheets["rift_anchors.csv"] += result["anchors"]
        sheets["rift_routes.csv"] += result["routes"]
        sheets["rift_exit_points.csv"].append(result["exit"])
        report.append(report_row(row, result, sum(1 for n in natives if n["map"] == map_id), knobs))
    sheets["rift_native_filter.csv"].sort(key=lambda r: (r["map_id"], r["spawn_guid"]))
    return sheets, report


def survey(db, mmaps, factions, knobs, rows=None):
    """The 30 dungeons from the world database and the mmaps."""
    rows = rows or dungeons()
    natives = load_natives(db, {int(r["map_id"]) for r in rows})
    formations = load_formations(db, {n["guid"] for n in natives})
    paths = load_paths(db, {n["path_id"] for n in natives if n["path_id"]})
    meshes = {}

    def mesh_of(map_id):
        if map_id not in meshes:
            meshes[map_id] = rift_navmesh.Navmesh.from_map(map_id, mmaps)
        return meshes[map_id]

    return survey_rows(rows, natives, formations, paths, mesh_of, factions, knobs)


# -- the migration ------------------------------------------------------------------------------------------------------------

def sql_value(value):
    if value == "" or value is None:
        return "NULL"
    try:
        float(value)
        return str(value)
    except ValueError:
        return quote(value)


def render(sheets, zones=None):
    """The migration text. Without `zones`, the dungeons' rift_survey_0001.sql: every row but the open zones' (their own
    migration), each table emptied first of the dungeons' rows only. With `zones` (a set of names), the open zones' rift_survey_0002.sql: it deletes
    only those zones' rows from tables 0001 made, so applying it never touches a dungeon's rows or the designer's edits there."""
    if zones is None:
        skip = open_zone_names()
        parts = [f"-- Generated by generate_rift_survey.py from the rift_*.csv sheets in data/d3 (diablocraft-7vhj); never edit.",
                 "-- The survey of the rift dungeons (docs/proposals/monster-spawning.md 3.5.1, Part S0): areas, anchors, stock patrol routes,",
                 "-- the natives the spawner refuses and each dungeon's exit point. Dev edits come home through --export, then a new migration.",
                 "SET NAMES utf8mb4;"]
    else:
        skip = None
        names = ", ".join(quote(z) for z in sorted(zones))
        parts = [f"-- Generated by generate_open_zone_survey.py from the rift_*.csv sheets in data/d3 (diablocraft-9ff9); never edit.",
                 "-- The open zones' anchors, areas and stock patrol routes (docs/proposals/monster-spawning.md 3.5.2, Part S6), in the tables",
                 "-- rift_survey_0001.sql made. Only these zones' rows are deleted first; the dungeons' rows stay as they are.",
                 "SET NAMES utf8mb4;"]
    for name, columns in SHEETS.items():
        table, definition = TABLES[name]
        if zones is None:
            # Only the dungeons' rows are emptied: the updater re-applies this file whenever its hash changes (dev runs
            # Updates.Redundancy 1, after every --export), and the open zones' rows (rift_survey_0002.sql, which does not re-run)
            # must survive it.
            keep = f" WHERE `dungeon` NOT IN ({', '.join(quote(z) for z in sorted(skip))})" if skip else ""
            parts += [f"CREATE TABLE IF NOT EXISTS `{table}` ({definition}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;", f"DELETE FROM `{table}`{keep};"]
            rows = [r for r in sheets[name] if r["dungeon"] not in skip]
        else:
            parts.append(f"DELETE FROM `{table}` WHERE `dungeon` IN ({names});")
            rows = [r for r in sheets[name] if r["dungeon"] in zones]
        names_sql = ", ".join(f"`{c}`" for c in columns)
        for start in range(0, len(rows), 500):
            values = ",\n".join("(" + ", ".join(sql_value(r[c]) for c in columns) + ")" for r in rows[start:start + 500])
            parts.append(f"INSERT INTO `{table}` ({names_sql}) VALUES\n{values};")
    return "\n".join(parts) + "\n"


def generate(directory=None):
    sheets = read_sheets(directory)
    zones = open_zone_names(directory)
    jobs = [(NAME, render(sheets))]
    if zones and any(r["dungeon"] in zones for rows in sheets.values() for r in rows):
        jobs.append((OPEN_NAME, render(sheets, zones)))
    jobs.append((PYLON_NAME, render_pylon_spots(read_pylon_spots(directory))))
    for name, sql in jobs:
        target = MODULE / "data/sql/db-world/updates" / name
        write_migration(MODULE, target, sql)
        write_coupled_outputs(MODULE, target, sql, [(MODULE / "data/generated" / name, sql)], label="rift survey rows")
        print(f"Generated {name}")


# -- --export ------------------------------------------------------------------------------------------------------------------

EXPORTED = ("rift_areas.csv", "rift_anchors.csv", "rift_routes.csv", "rift_exit_points.csv")


def export(db, directory=None):
    """The dev tables' rows into the sheets, the designer's edits included. The native filter and the report stay the survey's.
    The rows keep the order the survey writes them in (the dungeons in rift_dungeons.csv order, then the id), so a sheet with one edit
    differs from the committed one in the edited rows only."""
    directory = directory or D3
    rank = {row["name"]: index for index, row in enumerate(read_csv(D3 / "rift_dungeons.csv"))}
    for row in read_csv(D3 / OPEN_ZONES):          # then the open zones in their sheet's order, as the zone survey writes them (hmnei)
        rank.setdefault(row["name"], len(rank))
    for name in EXPORTED:
        table, _ = TABLES[name]
        columns = SHEETS[name]
        pairs = ",".join(f"'{c}',`{c}`" for c in columns)
        rows = [json.loads(line) for line in db.query(f"SELECT JSON_OBJECT({pairs}) FROM `{table}`")]
        rows.sort(key=lambda r: (rank.get(r["dungeon"], len(rank)), r["dungeon"], r[columns[1]]))
        write_csv(Path(directory) / name, columns, [{c: ("" if r[c] is None else r[c]) for c in columns} for r in rows])
    placed = export_exit_spots(db, directory)
    export_pylon_spots(db, directory)
    print("exported " + ", ".join(EXPORTED) + (f"; {placed} exit spots of the designer's" if placed else ""))


def export_pylon_spots(db, directory=None):
    """The spots table (the designer's `.dc pylon spot` edits included) into rift_pylon_spots.csv, in the survey's order: the dungeons in
    rift_dungeons.csv order, the open zones after them, then the spot number. A database without the table leaves the sheet alone."""
    if not db.query(f"SHOW TABLES LIKE '{PYLON_TABLE[0]}'"):
        return
    rank = {row["name"]: index for index, row in enumerate(read_csv(D3 / "rift_dungeons.csv"))}
    for row in read_csv(D3 / OPEN_ZONES):          # the open zones in their sheet's order, as the survey writes them
        rank.setdefault(row["name"], len(rank))
    pairs = ",".join(f"'{c}',`{c}`" for c in PYLON_COLUMNS)
    rows = [json.loads(line) for line in db.query(f"SELECT JSON_OBJECT({pairs}) FROM `{PYLON_TABLE[0]}`")]
    rows.sort(key=lambda r: (rank.get(r["dungeon"], len(rank)), r["dungeon"], r["spot"]))
    write_csv(Path(directory or D3) / PYLON_SHEET, PYLON_COLUMNS, [{c: ("" if r[c] is None else r[c]) for c in PYLON_COLUMNS} for r in rows])


def export_exit_spots(db, directory):
    """The spots the designer placed with `.dc floor exit here` (dc_rift_exit_spot, rift floors F2) replace the survey's far point in
    rift_exit_points.csv, marked `source` alex with no walk. The table is the dev world's own, so a database without it exports
    the survey's points unchanged. Returns how many spots went in."""
    if not db.query("SHOW TABLES LIKE 'dc_rift_exit_spot'"):
        return 0
    spots = {}
    for line in db.query("SELECT JSON_OBJECT('dungeon',`dungeon`,'x',`x`,'y',`y`,'z',`z`,'o',`o`) FROM `dc_rift_exit_spot`"):
        spot = json.loads(line)
        spots[spot["dungeon"]] = spot
    columns = SHEETS["rift_exit_points.csv"]
    path = Path(directory or D3) / "rift_exit_points.csv"
    rows = read_csv(path)
    # An open zone's row is its farthest anchor (generate_open_zone_survey.py with_zone_exits, yh7el); a zone without one gets his
    # spot as a new row, after the dungeons'.
    for name in sorted((set(spots) & open_zone_names(directory)) - {row["dungeon"] for row in rows}):
        rows.append({"dungeon": name, "x": "", "y": "", "z": "", "o": "", "walk_yards": "", "source": ""})
    unknown = set(spots) - {row["dungeon"] for row in rows}
    if unknown:
        raise ValueError(f"dc_rift_exit_spot names dungeons the sheet does not have: {sorted(unknown)}")
    for row in rows:
        if row["dungeon"] in spots:
            spot = spots[row["dungeon"]]
            row.update(x=spot["x"], y=spot["y"], z=spot["z"], o=spot["o"], walk_yards="", source="alex")
    write_csv(path, columns, rows)
    return len(spots)


def with_open_zones(sheets, committed):
    """The dungeon survey's sheets and, after them, the open zones' rows of the committed ones: those are
    generate_open_zone_survey.py's, and a dungeon survey must not drop them."""
    zones = open_zone_names()
    return {name: rows + [r for r in committed[name] if r["dungeon"] in zones] for name, rows in sheets.items()}


def write_survey(sheets, report, directory=None, report_path=None):
    directory = directory or D3
    for name, columns in SHEETS.items():
        write_csv(Path(directory) / name, columns, sheets[name])
    write_csv(report_path or REPORT, REPORT_COLUMNS, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--survey", action="store_true", help="read the world database and the navmesh, write the sheets and the report")
    parser.add_argument("--export", action="store_true", help="bring the dev world database's tables into the sheets")
    parser.add_argument("--pylon-spots", action="store_true", help="write rift_pylon_spots.csv from the committed area and anchor sheets (offline)")
    parser.add_argument("--force", action="store_true", help="--survey over sheets that hold rows of the designer's")
    parser.add_argument("--mysql")
    parser.add_argument("--defaults-file")
    parser.add_argument("--mmaps", help="the mmaps folder (default: the build's server data)")
    args = parser.parse_args()
    if args.survey or args.export:
        import fixture_db
        mysql, defaults = (args.mysql, args.defaults_file) if args.mysql and args.defaults_file else fixture_db.mysql_and_defaults([])
        db = Database(mysql, defaults, "acore_world")
    if args.pylon_spots:
        if any(r["source"] == "alex" for r in read_pylon_spots()) and not args.force:
            parser.error("the spot sheet holds rows of the designer's (source alex): --export brings his edits in; --force writes it over them")
        write_csv(D3 / PYLON_SHEET, PYLON_COLUMNS, pylon_spots(read_sheets()))
    elif args.export:
        export(db)
    elif args.survey:
        if (has_alex(read_sheets(missing_ok=True)) or any(r["source"] == "alex" for r in read_pylon_spots())) and not args.force:
            parser.error("the sheets hold rows of the designer's (source alex): --export brings his edits in; --force surveys over them")
        mmaps = args.mmaps or ROOT / "azerothcore-wotlk/build/server/data/mmaps"
        factions = Factions(Path(mmaps).parent / "dbc/FactionTemplate.dbc")
        sheets, report = survey(db, mmaps, factions, read_knobs())
        merged = with_open_zones(sheets, read_sheets(missing_ok=True))
        write_survey(merged, report)
        write_csv(D3 / PYLON_SHEET, PYLON_COLUMNS, pylon_spots(merged))
        print(f"surveyed {len(report)} dungeons: {len(sheets['rift_anchors.csv'])} anchors, {len(sheets['rift_areas.csv'])} areas, "
              f"{len(sheets['rift_routes.csv'])} routes, {len(sheets['rift_native_filter.csv'])} natives refused")
    generate()


if __name__ == "__main__":
    main()

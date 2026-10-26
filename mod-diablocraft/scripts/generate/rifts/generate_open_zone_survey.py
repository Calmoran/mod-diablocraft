#!/usr/bin/env python3
"""The survey of the open zones (diablocraft-9ff9, docs/proposals/monster-spawning.md section 3.5.2, Part S6).

    python3 mod-diablocraft/scripts/generate/rifts/generate_open_zone_survey.py                    # sheets -> rift_survey_0002.sql (offline)
    python3 mod-diablocraft/scripts/generate/rifts/generate_open_zone_survey.py --survey [--force] # world database + navmesh -> sheets

An open zone is a walled-in zone of a continent that the rift copies (Un'Goro on map 751, rift_open_zones.csv). The copy has no
creature rows of its own, so, as generate_rift_survey.py does for a dungeon, this survey:
  1. reads the zone from the terrain, as the core does (the 16 x 16 area ids of the continent's `.map` tiles, AreaTable's
     children of the zone): the `creature` rows of the continent that stand in it, these rows' own areaId being 0;
  2. keeps the combatants, makes packs, anchors, areas and tags, and ties the stock patrol paths to anchors, all by the
     dungeon survey's own code (steps 2 to 7 of 3.5.1), on the zone's navmesh, from the zone's entrance (rifts.csv
     open_rift_entry_*, the designer's .gps);
  3. fills thin ground: points on the walkable ground (not water, not steeper than max_slope_degrees, reachable from the
     entrance, inside the zone) at least `open_zone_spacing_yards` from every other anchor, sampled offline so the designer can see and
     change them (3.5.2 step 2). Blank spacing samples nothing: the anchors are the natives' only;
  4. groups anchors into areas with the zone's own cap, `open_zone_area_max_yards` (blank: the dungeons' area_max_yards).

It writes the zone's rows into the sheets the dungeon survey writes (rift_areas, rift_anchors, rift_routes in data/d3), beside the
dungeons' rows, its report data/generated/rift_open_zone_report.csv, and the migration rift_survey_0002.sql with its mirror.
It writes no native-filter row: the natives are on the continent itself, where they stay (the copy has none to refuse). Each
zone's exit point (rift_exit_points.csv, source survey) is its anchor farthest from the entrance by walk, D3's exit at the floor's
far end (rift floors 4.14, diablocraft-yh7el; a dungeon's is its farthest ground, generate_rift_survey.py exit_point); a spot the designer
placed with `.dc floor exit here` (source alex) replaces it. Every run writes them from the anchors sheet, so a pruned anchor moves
its zone's exit too. `--survey` refuses while the sheets hold a row of
The designer's (`source` alex) unless `--force`; `--export` of generate_rift_survey.py brings his edits home for the zone as for a dungeon.
After every `--survey`, run prune_open_zone_spots.py: the survey reads the terrain only, and the core's WMO areas put some anchors in
another zone (diablocraft-hyoic.8).
"""
import argparse
import collections
import csv
import math
import struct
import sys
import zlib
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_rift_survey as S  # noqa: E402
import rift_navmesh  # noqa: E402
from generate_area_copies import Database  # noqa: E402

MODULE, ROOT, D3 = S.MODULE, S.ROOT, S.D3
RIFTS = MODULE / "data/tunables/rifts.csv"
REPORT = MODULE / "data/generated/rift_open_zone_report.csv"
ZONE_SHEETS = ("rift_areas.csv", "rift_anchors.csv", "rift_routes.csv")
REPORT_COLUMNS = ("zone", "map_id", "source_map", "tiles", "spawn_rows_in_box", "spawn_rows_in_zone", "combatants", "natives_today",
                  "off_navmesh", "other_part", "native_anchors", "sampled_anchors", "areas_s", "areas_m", "areas_l",
                  "expected_anchors", "expected_bodies", "expected_elite_packs", "expected_solos", "anchors_with_route",
                  "anchors_near_entry", "area_cap_yards", "spacing_yards")
# Constants (identities of the core's data files, not tunables): the 16 x 16 area grid of a `.map` tile and its header
# (MapDefines.h map_fileheader, map_areaHeader; GridMap.cpp), the flag "one area id for the whole tile", the tile size
# (SIZE_OF_GRIDS), and the AreaTable.dbc layout of 3.3.5a (36 fields, id / continent / parent area first).
MAP_MAGIC, MAP_VERSION, CHUNKS, NO_AREA, GRID = b"MAPS", 9, 16, 0x0001, rift_navmesh.GRID
# Ours: the sampling lattice is shifted by this part of its pitch (3/8, exact in binary) so that none of its points lies on the
# navmesh's own grid lines, where two polygons would claim it; the polygons' corners are on a 0.2667-yard grid.
PHASE = 0.375
AREA_FIELDS, AREA_SIZE = 36, 144


# -- the sheet and the knobs ------------------------------------------------------------------------------------------------

def read_zones(directory=None):
    return S.read_csv(Path(directory or D3) / S.OPEN_ZONES)


def entrance(zone_row, path=RIFTS):
    """(x, y, z) of the zone's entrance (rifts.csv <entry_tunable>_x/_y/_z, diablocraft-hmnei), or None while all three are blank: the
    zone is off and has nothing to survey from (no stand-in point). Some but not all set is refused."""
    rows = {r["name"]: r["value"].strip() for r in S.read_csv(path)}
    values = [rows.get(f"{zone_row['entry_tunable']}_{axis}", "") for axis in "xyz"]
    if not any(values):
        return None
    if not all(values):
        raise ValueError(f"rifts.csv {zone_row['entry_tunable']}_x, _y and _z are partly blank: a zone's entrance is all of them or none")
    return tuple(float(v) for v in values)


def zone_knobs(knobs):
    """The dungeon knobs with the zone's area cap: blank falls back to the dungeons' own (rift_survey.csv area_max_yards)."""
    cap = knobs.get("open_zone_area_max_yards")
    return dict(knobs, area_max_yards=cap if cap else knobs["area_max_yards"])


# -- the zone, read from the terrain ----------------------------------------------------------------------------------------

class AreaTable:
    """AreaTable.dbc: which area ids are the zone's, as the core's zone lookup has it (an area's parent is its zone)."""

    def __init__(self, path):
        raw = Path(path).read_bytes()
        magic, count, fields, size, _ = struct.unpack_from("<4s4I", raw)
        if magic != b"WDBC" or fields != AREA_FIELDS or size != AREA_SIZE:
            raise ValueError(f"{path}: not a 3.3.5a AreaTable.dbc")
        self.parent = {}
        for n in range(count):
            area, _, parent = struct.unpack_from("<3I", raw, 20 + n * size)
            self.parent[area] = parent

    def zone_ids(self, zone):
        """The zone and every area whose parent is it."""
        return {zone} | {area for area, parent in self.parent.items() if parent == zone}


def read_chunks(path):
    """(one area id for the whole tile, or None; the 256 area ids, or None) of one `.map` tile."""
    with Path(path).open("rb") as stream:
        header = stream.read(44)
        if header[:4] != MAP_MAGIC or struct.unpack_from("<I", header, 4)[0] != MAP_VERSION:
            raise ValueError(f"{path}: not a version {MAP_VERSION} map tile")
        stream.seek(struct.unpack_from("<I", header, 12)[0])
        _, flags, grid_area = struct.unpack("<IHH", stream.read(8))
        if flags & NO_AREA:
            return grid_area, None
        ids = array("H")
        ids.frombytes(stream.read(2 * CHUNKS * CHUNKS))
        return None, ids


class Zone:
    """Which points of a continent are in the zone: the area id of the 16 x 16 chunk under the point is one of `inside`."""

    def __init__(self, maps_dir, map_id, inside):
        self.inside_ids, self.tiles, self._chunks = set(inside), set(), {}
        for path in sorted(Path(maps_dir).glob(f"{map_id:03d}????.map")):
            gx, gy = int(path.name[3:5]), int(path.name[5:7])
            uniform, ids = read_chunks(path)
            if uniform is not None:
                if uniform in self.inside_ids:
                    self.tiles.add((gx, gy))
                self._chunks[(gx, gy)] = (uniform, None)
            elif any(a in self.inside_ids for a in ids):
                self.tiles.add((gx, gy))
                self._chunks[(gx, gy)] = (None, ids)
        if not self.tiles:
            raise ValueError(f"no tile of map {map_id} holds area {sorted(self.inside_ids)[:3]}...")

    def area_at(self, x, y):
        tile = self._chunks.get((int(math.floor(32 - x / GRID)), int(math.floor(32 - y / GRID))))
        if tile is None:
            return None
        uniform, ids = tile
        return uniform if ids is None else ids[(int(CHUNKS * (32 - x / GRID)) & 15) * CHUNKS + (int(CHUNKS * (32 - y / GRID)) & 15)]

    def inside(self, x, y):
        return self.area_at(x, y) in self.inside_ids

    def box(self):
        """(x0, x1, y0, y1) over the tiles that hold the zone (a tile spans (31 - gx) * GRID to (32 - gx) * GRID)."""
        gx = [t[0] for t in self.tiles]
        gy = [t[1] for t in self.tiles]
        return ((31 - max(gx)) * GRID, (32 - min(gx)) * GRID, (31 - max(gy)) * GRID, (32 - min(gy)) * GRID)


# -- thin ground ------------------------------------------------------------------------------------------------------------

def sampler(zone, knobs, entry=None):
    """The `extra` of survey_dungeon: points on the walkable ground at least `open_zone_spacing_yards` from every anchor.

    Candidates are the points of a lattice (half the spacing apart, shifted by PHASE) that fall on a ground polygon of the part of the map the
    entrance reaches, inside the zone, and not steeper than max_slope_degrees. They are tried in an order fixed by a hash of
    the lattice cell, not in sweep order, so the points that stay are spread evenly rather than in rows; each is kept if no
    anchor (a native's, or a point kept before) is nearer than the spacing on the same floor. The same inputs give the same
    points. Blank (or 0) spacing samples nothing.

    With `entry`, ground the entrance cannot walk to is skipped: the navmesh's `reached` set counts a fragment that
    with_bridges joined by a portal at a vertex two fragments share, and the walk from the entrance never reaches it (an anchor
    there would get entry_walk_yards inf, which no table takes; diablocraft-71kk3, 6 spots at 40 yards). The natives' own
    anchors are the dungeon survey's and are left as they are."""
    spacing = knobs.get("open_zone_spacing_yards")
    if not spacing or spacing <= 0:
        return None
    floor, slope = knobs["floor_tolerance_yards"], knobs["max_slope_degrees"]
    pitch = spacing / 2

    def sample(mesh, reached, anchors):
        candidates = []
        walked = None
        if entry is not None:
            walked = mesh.distances(*entry, mesh.locate(*entry, knobs["snap_xy_yards"], knobs["snap_z_yards"], knobs["snap_z_far_yards"]))
        for index in sorted(reached):
            poly = mesh.polys[index]
            if not poly.ground or poly.slope > slope:
                continue
            if walked is not None and not any(n in walked for n in mesh.poly_nodes[index]):
                continue
            x0, y0, x1, y1 = poly.box
            for i in range(math.ceil(x0 / pitch - PHASE), math.floor(x1 / pitch - PHASE) + 1):
                for j in range(math.ceil(y0 / pitch - PHASE), math.floor(y1 / pitch - PHASE) + 1):
                    x, y = (i + PHASE) * pitch, (j + PHASE) * pitch
                    if poly.contains(x, y) and zone.inside(x, y):
                        candidates.append((zlib.crc32(f"{i},{j}".encode()), i, j, index, x, y, poly.height(x, y)))
        candidates.sort(key=lambda c: c[:4])
        cells = collections.defaultdict(list)
        cell = lambda x, y: (int(x // spacing), int(y // spacing))
        for a in anchors:
            n = a["native"]
            cells[cell(n["x"], n["y"])].append((n["x"], n["y"], n["z"]))
        kept = []
        for _, _, _, index, x, y, z in candidates:
            cx, cy = cell(x, y)
            if any(abs(z - oz) < floor and math.hypot(x - ox, y - oy) < spacing
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1) for ox, oy, oz in cells.get((cx + dx, cy + dy), ())):
                continue
            cells[(cx, cy)].append((x, y, z))
            kept.append(dict(x=x, y=y, z=z, o=0.0, poly=index))
        return kept

    return sample


# -- the survey of one zone -------------------------------------------------------------------------------------------------

def survey_zone(zone_row, db, mmaps, maps_dir, areas, factions, knobs, entry):
    """{sheet name: [row]}, the report row and the pieces tests look at, for one row of rift_open_zones.csv."""
    source, name = int(zone_row["source_map"]), zone_row["name"]
    zone = Zone(maps_dir, source, areas.zone_ids(int(zone_row["zone_id"])))
    box = zone.box()
    in_box = S.load_natives(db, {source}, box)
    natives = [n for n in in_box if zone.inside(n["x"], n["y"])]
    formations = S.load_formations(db, {n["guid"] for n in natives})
    paths = S.load_paths(db, {n["path_id"] for n in natives if n["path_id"]})
    mesh = rift_navmesh.Navmesh.from_map(source, mmaps, zone.tiles)
    return survey_natives(zone_row, zone, in_box, natives, formations, paths, mesh, factions, knobs, entry)


def survey_natives(zone_row, zone, in_box, natives, formations, paths, mesh, factions, knobs, entry):
    knobs = zone_knobs(knobs)
    row = dict(name=zone_row["name"], map_id=zone_row["map_id"], entry_x=entry[0], entry_y=entry[1], entry_z=entry[2])
    result = S.survey_dungeon(row, natives, formations, paths, mesh, [], factions, knobs, extra=sampler(zone, knobs, entry), with_exit=False)
    sheets = {name: result[key] for name, key in (("rift_areas.csv", "areas"), ("rift_anchors.csv", "anchors"), ("rift_routes.csv", "routes"))}
    areas, anchors = result["areas"], result["anchors"]
    tags = collections.Counter(a["tag"] for a in areas)
    filled, bodies, elite, solos = S.estimate(areas, anchors, result["routes"], knobs)
    clear = knobs.get("entry_clear_yards")
    report = dict(zone=zone_row["name"], map_id=zone_row["map_id"], source_map=zone_row["source_map"], tiles=len(zone.tiles),
                  spawn_rows_in_box=len(in_box), spawn_rows_in_zone=len(natives), combatants=result["counts"]["combatants_on_map"],
                  natives_today=len(result["kept"]), off_navmesh=result["counts"]["off_navmesh"], other_part=result["counts"]["other_part_of_map"],
                  native_anchors=sum(1 for a in anchors if a["native_guid"] != ""), sampled_anchors=sum(1 for a in anchors if a["native_guid"] == ""),
                  areas_s=tags["S"], areas_m=tags["M"], areas_l=tags["L"], expected_anchors=round(filled, 1), expected_bodies=round(bodies),
                  expected_elite_packs=round(elite, 1), expected_solos=round(solos, 1), anchors_with_route=len({r["anchor"] for r in result["routes"]}),
                  anchors_near_entry=sum(1 for a in anchors if a["entry_walk_yards"] < clear) if clear else "",
                  area_cap_yards=knobs["area_max_yards"], spacing_yards=knobs.get("open_zone_spacing_yards") or "")
    return sheets, report


def with_zone_exits(sheets, zone_names=None):
    """`sheets` with each open zone's exit point (rift_exit_points.csv) its anchor farthest from the entrance by walk (the highest
    entry_walk_yards, the lowest anchor number on a tie), source survey, after the dungeons' rows in the zone sheet's order; a zone
    whose row is the designer's (source alex) keeps it."""
    names = [z["name"] for z in read_zones()] if zone_names is None else list(zone_names)
    rows = sheets["rift_exit_points.csv"]
    alex = {r["dungeon"]: r for r in rows if r["dungeon"] in names and r["source"] == "alex"}
    out = [r for r in rows if r["dungeon"] not in names]
    for name in names:
        if name in alex:
            out.append(alex[name])
            continue
        walked = [a for a in sheets["rift_anchors.csv"] if a["dungeon"] == name and a["entry_walk_yards"] not in ("", None)]
        if walked:
            far = max(walked, key=lambda a: (float(a["entry_walk_yards"]), -int(a["anchor"])))
            out.append(dict(dungeon=name, x=far["x"], y=far["y"], z=far["z"], o="0", walk_yards=far["entry_walk_yards"], source="survey"))
    return {**sheets, "rift_exit_points.csv": out}


def merge(sheets, committed, zone_names):
    """The committed sheets with the zones' rows replaced by `sheets` (the zone's rows go last, as --export sorts them)."""
    out = {name: [r for r in rows if r["dungeon"] not in zone_names] for name, rows in committed.items()}
    for name, rows in sheets.items():
        out[name] += rows
    return out


# -- main -------------------------------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--survey", action="store_true", help="read the world database, the terrain and the navmesh; write the sheets and the report")
    parser.add_argument("--force", action="store_true", help="--survey over sheets that hold rows of the designer's")
    parser.add_argument("--mysql")
    parser.add_argument("--defaults-file")
    parser.add_argument("--mmaps", help="the mmaps folder (default: the build's server data); maps and dbc are beside it")
    args = parser.parse_args()
    if args.survey:
        import fixture_db
        committed = S.read_sheets(missing_ok=True)
        if S.has_alex(committed) and not args.force:
            parser.error("the sheets hold rows of the designer's (source alex): generate_rift_survey.py --export brings his edits in; --force surveys over them")
        mysql, defaults = (args.mysql, args.defaults_file) if args.mysql and args.defaults_file else fixture_db.mysql_and_defaults([])
        db = Database(mysql, defaults, "acore_world")
        mmaps = Path(args.mmaps or ROOT / "azerothcore-wotlk/build/server/data/mmaps")
        data = mmaps.parent
        areas, factions = AreaTable(data / "dbc/AreaTable.dbc"), S.Factions(data / "dbc/FactionTemplate.dbc")
        zones = read_zones()
        found, reports = {name: [] for name in ZONE_SHEETS}, []
        for zone_row in list(zones):
            entry = entrance(zone_row)
            if entry is None:
                print(f"{zone_row['name']}: no entrance yet (rifts.csv {zone_row['entry_tunable']}_*), not surveyed; its sheet rows stay as they are")
                zones.remove(zone_row)
                continue
            sheets, report = survey_zone(zone_row, db, mmaps, data / "maps", areas, factions, S.read_knobs(), entry)
            for name in ZONE_SHEETS:
                found[name] += sheets[name]
            reports.append(report)
        merged = merge(found, committed, {z["name"] for z in zones})
        for name in ZONE_SHEETS:
            S.write_csv(D3 / name, S.SHEETS[name], merged[name])
        S.write_csv(REPORT, REPORT_COLUMNS, reports)
        for report in reports:
            print(f"surveyed {report['zone']}: {report['native_anchors']} native + {report['sampled_anchors']} sampled anchors, "
                  f"{report['areas_s']}/{report['areas_m']}/{report['areas_l']} S/M/L areas, {report['anchors_with_route']} patrols")
    exits = with_zone_exits(S.read_sheets())["rift_exit_points.csv"]
    S.write_csv(D3 / "rift_exit_points.csv", S.SHEETS["rift_exit_points.csv"], exits)
    S.generate()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Find the wall spots of the Un'Goro rift copy (diablocraft-jj6n): where the navmesh lets a player walk from the entrance
to the edge of the zone, printed as the rows of rifts.csv `open_rift_wall_NN_x/_y/_z/_r/_map` (_map is the copy map, COPY_MAP; a spot without it is dead,
InWallSpot stops the list at the first spot missing a row). Read-only; nothing is written.

The inside of the zone is the polygons whose centre lies in Un'Goro's areas (the survey's own Zone, generate_open_zone_survey.py).
The part the entrance reaches is the walking graph over those polygons alone; a crossing is a shared edge between that part and a
polygon outside the zone (any slope the navmesh walks, up to its 60 degrees). Crossings within RADIUS yards of the first of a cluster
(sorted by x, y) are one spot, as the research clustered its candidates (docs/research/open-world-rifts.md 2.3). Run after the
terrain, the navmesh or the entrance changes:  python3 mod-diablocraft/scripts/find_open_rift_walls.py [--data <server data dir>]
"""
import argparse
import csv
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_open_zone_survey as G  # noqa: E402
import rift_navmesh as N  # noqa: E402

ROOT = HERE.parents[1]
RADIUS = 25.0
COPY_MAP = 751  # the Kalimdor copy, where Un'Goro's spots live (world_open_rift_dbc.csv)
CANDIDATES = ROOT / "docs/research/open-world-rifts-exits.csv"


def crossings(mesh, zone, entry):
    """[((x, y, z), slope)]: the edges where the part of the zone the entrance walks to meets ground outside the zone."""
    inside = {i for i, poly in enumerate(mesh.polys) if zone.inside(poly.cx, poly.cy)}
    parent = {}

    def find(i):
        parent.setdefault(i, i)
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, _, _ in mesh.portals:
        if a in inside and b in inside:
            parent[find(a)] = find(b)
    start = mesh.locate(*entry, 5, 5, 20)
    if start is None:
        raise SystemExit("the entrance is off the navmesh")
    mine = {i for i in inside if find(i) == find(start)}
    found = []
    for a, b, p, q in mesh.portals:
        for here, there in ((a, b), (b, a)):
            if here in mine and there not in inside:
                found.append((tuple((p[i] + q[i]) / 2 for i in range(3)), max(mesh.polys[a].slope, mesh.polys[b].slope)))
    return sorted(found)


def spots(found):
    """[(centre, crossings in it, lowest slope)]: greedy clusters, the first crossing of each is its centre."""
    left, out = list(found), []
    while left:
        centre = left[0][0]
        members = [c for c in left if math.dist(c[0], centre) <= RADIUS]
        left = [c for c in left if c not in members]
        out.append((centre, len(members), min(c[1] for c in members)))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(ROOT / "azerothcore-wotlk/build/server/data"))
    data = Path(parser.parse_args().data)
    zone = G.Zone(data / "maps", 1, G.AreaTable(data / "dbc/AreaTable.dbc").zone_ids(490))
    tiles = {(gx + dx, gy + dy) for gx, gy in zone.tiles for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    mesh = N.Navmesh.from_map(1, data / "mmaps", tiles)
    candidates = [(r["exit_id"], float(r["x"]), float(r["y"]), float(r["z"])) for r in csv.DictReader(CANDIDATES.open(encoding="utf-8"))]
    for n, (centre, count, slope) in enumerate(spots(crossings(mesh, zone, G.entrance())), 1):
        near = [name for name, x, y, z in candidates if math.dist(centre, (x, y, z)) <= RADIUS]
        print(f"{n:02d}  x {centre[0]:.1f}  y {centre[1]:.1f}  z {centre[2]:.1f}  crossings {count}  lowest slope {slope:.1f}  candidates {','.join(near) or '-'}  map {COPY_MAP}")


if __name__ == "__main__":
    main()

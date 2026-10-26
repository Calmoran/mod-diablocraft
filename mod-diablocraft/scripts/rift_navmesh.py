"""A map's navmesh from the server's .mmtile files, as a walking graph (diablocraft-7vhj, the survey of monster-spawning.md S0).

Read-only. A tile holds convex ground polygons; a polygon's neighbours are named inside the tile and, on a tile border,
found here by matching the two border edges that overlap. The graph's nodes are the shared edges' midpoints and a
polygon's midpoints are joined by straight lines (a polygon is convex), so a walking distance is a shortest path over
straight legs: close to what the core's path finder walks, with no string pulling. Haiku's `navexits.py` (open-world
rifts, 2026-10-08) was the model for reading the tile.

Tile layout (MMapDefines.h, dtNavMesh): MmapTileHeader and its recast config (56 bytes), then dtMeshHeader (100 bytes),
vertices, polygons, links, detail meshes, detail vertices, detail triangles, BV tree and off-mesh connections. A vertex
is stored (nav x, nav y, nav z) = (wow y, wow z, wow x).
"""
import collections
import heapq
import math
import struct
from pathlib import Path

# Constants (identities of the file format and the world, not tunables): SIZE_OF_GRIDS (MapDefines.h), the tile magics,
# the recast header size, and NAV_GROUND (MapDefines.h NavTerrain), the only terrain the survey walks.
GRID = 533.3333
DT_NAV_MAGIC, MMAP_MAGIC, DT_VERSION = 0x444E4156, 0x4D4D4150, 7
HEADER = 56
EXT_LINK, OFFMESH_TYPE, NAV_GROUND = 0x8000, 1, 0x01
BORDER_EPS = 0.5          # how near a vertex must lie to the tile's edge to be on the border
OVERLAP_MIN = 0.05        # yards two border edges must share to be one portal
CLIMB = 3.0               # yards two border edges may differ in height and still join (dtNavMeshParams walkableClimb)


def align4(n):
    return (n + 3) & ~3


class Poly:
    __slots__ = ("pts", "ground", "slope", "cx", "cy", "cz", "box")

    def __init__(self, pts, ground=True, slope=0.0):
        self.pts, self.ground, self.slope = pts, ground, slope
        n = len(pts)
        self.cx, self.cy, self.cz = (sum(p[i] for p in pts) / n for i in range(3))
        self.box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))

    def contains(self, x, y):
        sign = 0
        for i, (ax, ay, _) in enumerate(self.pts):
            bx, by, _ = self.pts[(i + 1) % len(self.pts)]
            c = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
            if abs(c) < 1e-9:
                continue
            s = 1 if c > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                return False
        return True

    def height(self, x, y):
        """The polygon's height under (x, y): the plane of the triangle of its fan that holds the point."""
        a = self.pts[0]
        for i in range(1, len(self.pts) - 1):
            b, c = self.pts[i], self.pts[i + 1]
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-12:
                continue
            u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
            v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
            if min(u, v, 1 - u - v) >= -1e-6:
                return u * a[2] + v * b[2] + (1 - u - v) * c[2]
        return self.cz

    def distance_xy(self, x, y):
        """Straight distance from (x, y) to the polygon's outline, 0 inside."""
        if self.contains(x, y):
            return 0.0
        best = math.inf
        for i, (ax, ay, _) in enumerate(self.pts):
            bx, by, _ = self.pts[(i + 1) % len(self.pts)]
            dx, dy = bx - ax, by - ay
            t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(x - ax - t * dx, y - ay - t * dy))
        return best


class Navmesh:
    """Polygons, and the walking graph over their shared edges. Build it with `from_polygons` or `from_map`."""

    def __init__(self):
        self.polys = []
        self.nodes = []        # (x, y, z) of a portal
        self.adj = []          # node -> [(node, yards)]
        self.poly_nodes = []   # polygon -> its portals
        self.portals = []      # the shared edges the graph was built from
        self._grid = {}
        self._cid = None
        self.stats = {}

    # -- building --------------------------------------------------------------------------------------------------

    @classmethod
    def from_polygons(cls, polys, portals):
        """polys: [Poly]; portals: [(poly a, poly b, (x1, y1, z1), (x2, y2, z2))] each shared edge once."""
        mesh = cls()
        mesh.polys = list(polys)
        mesh.portals = list(portals)
        mesh.poly_nodes = [[] for _ in mesh.polys]
        for a, b, p, q in portals:
            node = len(mesh.nodes)
            mesh.nodes.append(tuple((p[i] + q[i]) / 2 for i in range(3)))
            mesh.poly_nodes[a].append(node)
            mesh.poly_nodes[b].append(node)
        mesh.adj = [[] for _ in mesh.nodes]
        for nodes in mesh.poly_nodes:
            for i, m in enumerate(nodes):
                for n in nodes[i + 1:]:
                    cost = math.dist(mesh.nodes[m], mesh.nodes[n])
                    mesh.adj[m].append((n, cost))
                    mesh.adj[n].append((m, cost))
        for index, poly in enumerate(mesh.polys):
            x0, y0, x1, y1 = poly.box
            for bx in range(int(x0 // 10), int(x1 // 10) + 1):
                for by in range(int(y0 // 10), int(y1 // 10) + 1):
                    mesh._grid.setdefault((bx, by), []).append(index)
        return mesh

    @classmethod
    def from_map(cls, map_id, mmaps_dir, tiles=None):
        """The map's whole navmesh, or only the tiles {(gx, gy)} (a continent's zone, not its 988 tiles)."""
        polys, portals, borders = [], [], {}
        for path in sorted(Path(mmaps_dir).glob(f"{map_id:03d}????.mmtile")):
            gx, gy = int(path.name[3:5]), int(path.name[5:7])
            if tiles is not None and (gx, gy) not in tiles:
                continue
            read_tile(path, gx, gy, polys, portals, borders)
        inside = len(portals)
        match_borders(borders, portals)
        mesh = cls.from_polygons(polys, portals)
        mesh.stats = dict(border_edges=sum(len(v) for v in borders.values()), border_portals=len(portals) - inside)
        return mesh

    # -- asking ----------------------------------------------------------------------------------------------------

    def locate(self, x, y, z, snap_xy, snap_z, far_z=None):
        """The polygon under (x, y, z): the nearest in height among those holding the point within snap_z, else the
        nearest outline within snap_xy and snap_z; then, as the core does (PathGenerator.cpp:245), the same with
        `far_z` for the height, when given. Any terrain counts: water and lava are mesh a creature stands in. None when
        the point is off the mesh."""
        for height in (snap_z,) if far_z is None else (snap_z, far_z):
            best = None
            near = {i for bx in (-1, 0, 1) for by in (-1, 0, 1) for i in self._grid.get((int(x // 10) + bx, int(y // 10) + by), ())}
            for index in sorted(near):
                poly = self.polys[index]
                d = poly.distance_xy(x, y)
                if d > snap_xy:
                    continue
                dz = abs(poly.height(x, y) - z)
                if dz > height:
                    continue
                key = (d > 0, dz if d == 0 else d + dz, index)
                if best is None or key < best[0]:
                    best = (key, index)
            if best is not None:
                return best[1]
        return None

    def distances(self, x, y, z, poly, limit=math.inf):
        """Dijkstra from a point in `poly` over the portals, stopping past `limit` yards: {node: yards}."""
        seen = {}
        heap = [(math.dist((x, y, z), self.nodes[n]), n) for n in self.poly_nodes[poly]]
        heapq.heapify(heap)
        while heap:
            d, node = heapq.heappop(heap)
            if node in seen or d > limit:
                continue
            seen[node] = d
            for other, cost in self.adj[node]:
                if other not in seen and d + cost <= limit:
                    heapq.heappush(heap, (d + cost, other))
        return seen

    def reach(self, seen, poly, x, y, z):
        """Yards from the Dijkstra source to the point (x, y, z) in `poly`; inf when not reached."""
        return min((seen[n] + math.dist((x, y, z), self.nodes[n]) for n in self.poly_nodes[poly] if n in seen),
                   default=math.inf)

    def components(self):
        """[set of polygons] the walking graph keeps apart, and the component id of each polygon."""
        if self._cid is None:
            parent = list(range(len(self.polys)))

            def find(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i

            for a, b, _, _ in self.portals:
                parent[find(a)] = find(b)
            groups = {}
            for i in range(len(self.polys)):
                groups.setdefault(find(i), set()).add(i)
            self._parts = sorted(groups.values(), key=min)
            self._cid = {i: k for k, part in enumerate(self._parts) for i in part}
        return self._parts, self._cid

    def with_bridges(self, start, avoid, bridge):
        """A copy of this mesh in which every fragment near the component of `start` is joined to it.

        The mmaps leave stairs, ledges and thin steps as separate fragments a few yards from the floor they belong
        to. A fragment joins when its nearest vertex is within `bridge` yards of the component (or of a fragment
        already joined), it holds none of the polygons in `avoid` (another dungeon's entry on the same map), and it is
        smaller than the component of `start` as the mesh has it: so a whole wing that is larger than the dungeon is
        never swallowed. The join is a portal at the middle of the gap. Returns (mesh, polygons of the joined part)."""
        parts, cid = self.components()
        own = parts[cid[start]]
        skip = {cid[p] for p in avoid} | {cid[start]}
        cell = lambda v: (int(v[0] // bridge), int(v[1] // bridge), int(v[2] // bridge))
        # Vertices of the fragments that may join, by cell; the frontier is the vertices of what has joined so far.
        eligible = {k for k, part in enumerate(parts) if k not in skip and len(part) < len(own)}
        cells = {}
        for index, poly in enumerate(self.polys):
            if cid[index] in eligible:
                for v in poly.pts:
                    cells.setdefault(cell(v), []).append((v, index))
        reached = set(own)
        joined = set()
        frontier = collections.deque(v for i in sorted(own) for v in self.polys[i].pts)
        extra = []
        while frontier:
            v = frontier.popleft()
            c = cell(v)
            hit = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for w, index in cells.get((c[0] + dx, c[1] + dy, c[2] + dz), ()):
                            if cid[index] in joined:
                                continue
                            d = math.dist(v, w)
                            if d <= bridge and (hit is None or (d, index) < hit[0]):
                                hit = ((d, index), w, index)
            if hit is not None:
                _, w, index = hit
                joined.add(cid[index])
                part = parts[cid[index]]
                reached |= part
                extra.append((v, w, index))
                frontier.extend(u for i in sorted(part) for u in self.polys[i].pts)
        owner = {}
        for j in reached:
            for q in self.polys[j].pts:
                owner.setdefault(q, j)
        portals = list(self.portals)
        for v, w, index in extra:
            portals.append((owner[v], index, v, w))
        return Navmesh.from_polygons(self.polys, portals), reached

    def component(self, poly):
        """Every polygon the walking graph joins to `poly`."""
        parts, cid = self.components()
        return parts[cid[poly]]


# -- reading the tile files --------------------------------------------------------------------------------------------

def read_tile(path, gx, gy, polys, portals, borders):
    data = path.read_bytes()
    if struct.unpack_from("<I", data, 0)[0] != MMAP_MAGIC:
        raise ValueError(f"{path.name}: not an mmtile")
    size = struct.unpack_from("<I", data, 12)[0]
    v = struct.unpack_from("<iiiiiI9i3f6ff", data, HEADER)
    if v[0] != DT_NAV_MAGIC or v[1] != DT_VERSION:
        raise ValueError(f"{path.name}: not a version {DT_VERSION} navmesh tile")
    poly_n, vert_n, link_n, dm_n, dv_n, dt_n, bv_n, om_n = v[6:14]
    bmin = v[18:21]
    xmin, ymin = (31 - gx) * GRID, (31 - gy) * GRID
    if abs(bmin[2] - xmin) > 1 or abs(bmin[0] - ymin) > 1:
        raise ValueError(f"{path.name}: the tile's box disagrees with its name")
    p = HEADER + 100
    verts_off = p
    p += align4(12 * vert_n)
    polys_off = p
    p += align4(32 * poly_n)
    p += align4(16 * link_n) + align4(12 * dm_n) + align4(12 * dv_n) + align4(4 * dt_n) + align4(16 * bv_n) + align4(36 * om_n)
    if p != HEADER + size or p != len(data):
        raise ValueError(f"{path.name}: the sizes do not add up")
    verts = struct.unpack_from("<%df" % (3 * vert_n), data, verts_off)
    base = len(polys)
    local = {}      # tile polygon index -> index in polys (off-mesh connections are skipped)
    raw = []
    for k in range(poly_n):
        f = struct.unpack_from("<I6H6HHBB", data, polys_off + 32 * k)
        count, kind = f[14], f[15]
        if (kind >> 6) == OFFMESH_TYPE:
            continue
        pts = [(verts[3 * q + 2], verts[3 * q], verts[3 * q + 1]) for q in f[1:1 + count]]
        local[k] = base + len(raw)
        raw.append((k, pts, f[7:7 + count], kind & 0x3F))
    for k, pts, neis, terrain in raw:
        polys.append(Poly(pts, ground=terrain == NAV_GROUND, slope=slope_of(pts)))
    for k, pts, neis, _ in raw:
        index = local[k]
        for e, nei in enumerate(neis):
            a, b = pts[e], pts[(e + 1) % len(pts)]
            if nei == 0:
                continue
            if nei & EXT_LINK:
                for axis, coord in border_of(a, b, xmin, ymin):
                    borders.setdefault((axis, round(coord)), []).append((index, a, b))
            elif nei - 1 in local and k < nei - 1:
                portals.append((index, local[nei - 1], a, b))


def border_of(a, b, xmin, ymin):
    """[(axis, coordinate)] of the tile edge both ends of the segment lie on."""
    found = []
    for axis, low in ((0, xmin), (1, ymin)):
        for coord in (low, low + GRID):
            if abs(a[axis] - coord) < BORDER_EPS and abs(b[axis] - coord) < BORDER_EPS:
                found.append((axis, coord))
    return found


def match_borders(borders, portals):
    """Join the polygons whose border edges overlap on the same tile edge, from two different tiles."""
    for (axis, _), edges in borders.items():
        other = 1 - axis
        spans = [(min(a[other], b[other]), max(a[other], b[other]), index, a, b) for index, a, b in edges]
        spans.sort(key=lambda s: s[:3])
        for i, (lo, hi, ia, a1, b1) in enumerate(spans):
            for lo2, hi2, ib, a2, b2 in spans[i + 1:]:
                if lo2 >= hi - OVERLAP_MIN:
                    break
                if ia == ib or min(hi, hi2) - max(lo, lo2) < OVERLAP_MIN:
                    continue
                mid = (max(lo, lo2) + min(hi, hi2)) / 2
                za, zb = height_on(a1, b1, other, mid), height_on(a2, b2, other, mid)
                if abs(za - zb) > CLIMB:
                    continue
                p = tuple(mid if i == other else (a1[i] if i == axis else za) for i in range(3))
                portals.append((ia, ib, p, p))


def height_on(a, b, axis, value):
    span = b[axis] - a[axis]
    t = 0.5 if abs(span) < 1e-9 else (value - a[axis]) / span
    return a[2] + max(0.0, min(1.0, t)) * (b[2] - a[2])


def slope_of(pts):
    """The polygon's steepest incline in degrees, from its first three vertices."""
    (ax, ay, az), (bx, by, bz), (qx, qy, qz) = pts[0], pts[1], pts[2]
    ux, uy, uz, wx, wy, wz = bx - ax, by - ay, bz - az, qx - ax, qy - ay, qz - az
    nx, ny, nz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return math.degrees(math.acos(min(1.0, abs(nz) / length)))

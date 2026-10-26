"""diablocraft-976b: with the Sanctum's door shut, the arena is a closed room as far as the walking mesh can tell.

    python3 mod-diablocraft/scripts/tests/world/test_hub_sanctum_navmesh.py        # DC_DATA_DIR=<server data dir> to point elsewhere

Map 750 is a clone of map 603: link_map_clone.py makes its mmap tiles symlinks to 603's, so the Detour tiles of
Ulduar around Yogg-Saron's arena ARE the Sanctum's walkable ground. This test reads them, joins the polygons across
tile borders, starts on the arena floor in front of the door and walks the graph twice: with no door (the way the designer's
GM-spawned door left it once clicked open) the walkable ground runs out through the doorway; with the door shut, as
the migration spawns it (door slab = the display's box from GameObjectDisplayInfo.dbc times the template's size), it
never gets west of the door.

What this proves, and what it does not: it is the WALKING graph only. A jump, a fall, a knock-back, a mount that
flies or a swim is not an edge of it, so it cannot say the arena has no other way out; only a person walking its rim
with .gm off (the designer's dev check) can. It says the door is what keeps a walker in, and that the doorway is fully covered.
Skipped (loudly) when the server data folder has no 603 tiles.
"""
import collections
import math
import os
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_sanctum_seal as seal  # noqa: E402
import link_map_clone as link  # noqa: E402

ROOT = HERE.parents[1]
DATA = Path(os.environ.get("DC_DATA_DIR") or ROOT / "azerothcore-wotlk/build/server/data")
GRID = 533.3333333
DISPLAY, SIZE = 8081, 0.77   # stock template 194773 (and so 910019): display Ulduar doors 01, size 0.77
NEAR_Z = 6.0                 # yards: a polygon edge this close to the door's height can touch it
IN_FRONT = 30.0              # yards east of the door along the arena, where the walk starts


class Mesh:
    """The walkable polygons of one map's Detour tiles; a blocked(a, b) edge test lets a door close an edge."""

    SIDE = {0: (0, -1), 2: (-1, 0), 4: (0, 1), 6: (1, 0)}   # border side code -> file tile offset

    def __init__(self, folder, map_id, blocked=None):
        self.folder, self.map_id, self.tiles = folder, map_id, {}
        self.blocked = blocked or (lambda a, b: False)

    def tile(self, tx, ty):
        if (tx, ty) not in self.tiles:
            self.tiles[tx, ty] = self.load(tx, ty)
        return self.tiles[tx, ty]

    def load(self, tx, ty):
        path = self.folder / ("%03d%02d%02d.mmtile" % (self.map_id, tx, ty))
        if not path.exists():
            return None
        data = path.read_bytes()
        offset = next(o for o in range(0, 80, 4) if struct.unpack_from("<2I", data, o) == (0x444E4156, 7))   # "DNAV", v7
        header = struct.unpack_from("<15i3f3f3ff", data, offset)
        polys, verts, climb = header[6], header[7], header[17]
        offset += 100
        points = [struct.unpack_from("<3f", data, offset + 12 * i) for i in range(verts)]
        offset += 12 * verts
        out = []
        for _ in range(polys):
            vs = struct.unpack_from("<6H", data, offset + 4)
            links = struct.unpack_from("<6H", data, offset + 16)
            _, count, area_type = struct.unpack_from("<HBB", data, offset + 28)
            pts = [(points[k][2], points[k][0], points[k][1]) for k in vs[:count]]   # world x, y, z
            out.append(dict(pts=pts, links=links[:count], ground=area_type >> 6 == 0,
                            centre=tuple(sum(p[j] for p in pts) / count for j in range(3))))
            offset += 32
        return dict(polys=out, climb=climb)

    def neighbours(self, tx, ty, i):
        tile = self.tile(tx, ty)
        poly = tile["polys"][i]
        found = []
        for e, link_ in enumerate(poly["links"]):
            a, b = poly["pts"][e], poly["pts"][(e + 1) % len(poly["pts"])]
            if link_ == 0 or self.blocked(a, b):
                continue
            if not link_ & 0x8000:
                if tile["polys"][link_ - 1]["ground"]:
                    found.append((tx, ty, link_ - 1))
                continue
            side = link_ & 0xF
            if side not in self.SIDE:
                continue
            ntx, nty = tx + self.SIDE[side][0], ty + self.SIDE[side][1]
            other = self.tile(ntx, nty)
            if other is None:
                continue
            for j, q in enumerate(other["polys"]):
                if q["ground"] and any(
                        q["links"][k] == 0x8000 | ((side + 4) & 7) and self.overlap(
                            a, b, q["pts"][k], q["pts"][(k + 1) % len(q["pts"])], side, max(tile["climb"], other["climb"]) * 2)
                        for k in range(len(q["pts"]))):
                    found.append((ntx, nty, j))
        return found

    @staticmethod
    def overlap(a, b, c, d, side, climb):
        """Two border edges (a-b of one tile, c-d of its neighbour) share a stretch the walker can step across."""
        axis = 1 if side in (2, 6) else 0
        low = max(min(a[axis], b[axis]), min(c[axis], d[axis]))
        high = min(max(a[axis], b[axis]), max(c[axis], d[axis]))
        if high - low < 0.01:
            return False

        def z_at(p, q, t):
            return min(p[2], q[2]) if abs(q[axis] - p[axis]) < 1e-6 else p[2] + (t - p[axis]) / (q[axis] - p[axis]) * (q[2] - p[2])
        return min(abs(z_at(a, b, low) - z_at(c, d, low)), abs(z_at(a, b, high) - z_at(c, d, high))) <= climb

    def poly_at(self, x, y, z, tolerance=15.0):
        tx, ty = int(32 - x / GRID), int(32 - y / GRID)
        best = None
        for i, poly in enumerate(self.tile(tx, ty)["polys"]):
            if not poly["ground"]:
                continue
            pts, inside = poly["pts"], False
            for k in range(len(pts)):
                (x1, y1), (x2, y2) = pts[k][:2], pts[(k + 1) % len(pts)][:2]
                if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    inside = not inside
            if inside and abs(poly["centre"][2] - z) < tolerance and (best is None or abs(poly["centre"][2] - z) < best[0]):
                best = (abs(poly["centre"][2] - z), i)
        return None if best is None else (tx, ty, best[1])

    def reach(self, start):
        seen, queue = {start}, collections.deque([start])
        while queue:
            for nxt in self.neighbours(*queue.popleft()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def centres(self, polys):
        return [self.tiles[tx, ty]["polys"][i]["centre"] for tx, ty, i in polys]


def display_box(display):
    data = (DATA / "dbc/GameObjectDisplayInfo.dbc").read_bytes()
    magic, records, fields, size, _ = struct.unpack_from("<4s4I", data)
    assert magic == b"WDBC"
    for r in range(records):
        if struct.unpack_from("<I", data, 20 + r * size)[0] == display:
            box = struct.unpack_from("<%df" % fields, data, 20 + r * size)[12:18]
            return box[:3], box[3:]
    raise AssertionError(f"display {display} is not in GameObjectDisplayInfo.dbc")


class ShutDoor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.source = link.clone_ids()
        mmaps = DATA / "mmaps"
        if not (DATA / "dbc/GameObjectDisplayInfo.dbc").exists() or not list(mmaps.glob("%03d*.mmtile" % cls.source)):
            message = f"no mmap tiles of map {cls.source} / no DBC under {DATA}; set DC_DATA_DIR to a server data folder"
            print("SKIPPED, THE SEAL IS NOT PROVEN HERE: " + message, file=sys.stderr)
            raise unittest.SkipTest(message)
        cls.door = seal.door_row()
        low, high = display_box(DISPLAY)
        cls.half_width, cls.half_thick = (high[0] - low[0]) / 2 * SIZE, (high[1] - low[1]) / 2 * SIZE
        cls.mmaps = mmaps

    def blocked(self, a, b):
        """The door's slab (in the door's own axes: width along local x, thickness along local y) takes the edge."""
        d = self.door
        dx, dy = (a[0] + b[0]) / 2 - d["x"], (a[1] + b[1]) / 2 - d["y"]
        local_x = dx * math.cos(d["o"]) + dy * math.sin(d["o"])
        local_y = -dx * math.sin(d["o"]) + dy * math.cos(d["o"])
        return abs(local_x) <= self.half_width and abs(local_y) <= self.half_thick and abs(a[2] - d["z"]) < NEAR_Z

    def walk(self, door_shut):
        mesh = Mesh(self.mmaps, self.source, self.blocked if door_shut else None)
        d = self.door
        start = mesh.poly_at(d["x"] + IN_FRONT, d["y"], d["z"])
        self.assertIsNotNone(start, "no walkable polygon on the arena floor in front of the door")
        return mesh, mesh.reach(start)

    def test_the_door_is_what_keeps_a_walker_in(self):
        door = self.door
        open_mesh, open_walk = self.walk(False)
        shut_mesh, shut_walk = self.walk(True)
        west_open = [c for c in open_mesh.centres(open_walk) if c[0] < door["x"] - 20]
        west_shut = [c for c in shut_mesh.centres(shut_walk) if c[0] < door["x"] + self.half_thick]
        print(f"walkable polygons from the arena floor: door open {len(open_walk)}, door shut {len(shut_walk)}; "
              f"slab {self.half_width:.2f} x {self.half_thick:.2f} yd")
        self.assertTrue(west_open, "with no door the walk should run out through the doorway (is the door in the right place?)")
        self.assertEqual(west_shut, [], "a walker gets past the shut door")
        self.assertLess(len(shut_walk), len(open_walk))
        self.assertTrue(shut_walk <= open_walk)

    def test_a_door_too_thin_to_cover_the_doorway_would_not_seal_it(self):
        # The result must not be an accident of the slab size: shrink the slab to a sliver and the walk escapes.
        _, shut = self.walk(True)
        self.half_thick = 0.1
        _, sliver = self.walk(True)
        self.assertGreater(len(sliver), len(shut), "a sliver of a door still sealed the arena: the test proves nothing")


if __name__ == "__main__":
    unittest.main()

"""diablocraft-9ff9 - the survey of the open zones (monster-spawning.md 3.5.2, Part S6): Un'Goro on the rift copy, map 751.

What this proves, and what it does not:

  * The rules, on small made-up meshes whose answers are known by arithmetic: the `.map` area grid and AreaTable's children
    (the zone read from the terrain), thin-ground sampling (the spacing's edge, water, steep ground, ground the entrance does not
    reach, ground outside the zone, two floors, the height of a slope, blank spacing, an order that is not a sweep), the zone's
    own area cap with the dungeons' as the fallback, the sheets the zone survey writes (three; no native-filter row; the exit point is with_zone_exits', test_rift_exit_rows.py),
    the merge into the committed sheets and the migration that touches only the zone's rows. The same checks run against 24
    single-rule mutants of the generator, the survey code it reuses and the migration text, each of which must turn them red.
  * The data. The survey is re-run on the fixture world copy and the real maps and mmaps: the zone is the 25 tiles and 11 child
    areas the research found, holds the entrance and the four graveyards and 946 of the Planner's 947 crater-floor natives; the
    committed sheets are what the survey produces; a rehearsal at a spacing and a cap of the test's own (not the designer's) keeps every
    sampled point apart, on reachable ground and inside the zone.
  * `rift_survey_0002.sql` is replayed on a disposable MySQL after `rift_survey_0001.sql`, twice, and the dungeons' rows are
    still there; a migration that deleted every row is killed. A CHANGED 0001 applied after 0002 (what dev's Redundancy 1 does after an
    --export) leaves the zone's rows; a 0001 that emptied every row is killed.
  * NOT proved: that the points look right in game (the designer's pass on dev, once Part F5 puts the zone in the pool), that the spawner
    reads these rows (Part F5), and the two numbers the designer sets (spacing and area cap, blank in rifts.csv).
"""
import collections
import contextlib
import csv
import math
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import types

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db
import generate_open_zone_survey as O
import generate_rift_survey as S
import rift_navmesh as NM
from test_account_economy_sql import MYSQL, ROOT, isolated
from test_rift_survey import Factions, corridor, dungeon, module_from, native, rect_mesh
from test_slot_vendors import check, mutate

MODULE = ROOT / "mod-diablocraft"
ZONE_SOURCE = MODULE / "scripts/generate/rifts/generate_open_zone_survey.py"
SURVEY_SOURCE = MODULE / "scripts/generate/rifts/generate_rift_survey.py"
DATA = ROOT / "azerothcore-wotlk/build/server/data"
ZONE_NAME = "Un'Goro Crater"


class Stub:
    """A zone that is wherever the predicate says."""

    tiles = {(0, 0)}

    def __init__(self, inside=lambda x, y: True):
        self.inside = inside


def knobs_with(**more):
    knobs = S.read_knobs()
    knobs.update(more)
    return knobs


def sample(o, mesh, knobs, anchors=(), zone=None, reached=None, entry=None):
    """[(x, y, z)] the sampler keeps on the mesh, with `anchors` as (x, y, z) of natives."""
    found = o.sampler(zone or Stub(), knobs, entry)
    taken = [dict(native=dict(x=x, y=y, z=z)) for x, y, z in anchors]
    return [(p["x"], p["y"], p["z"]) for p in found(mesh, set(range(len(mesh.polys))) if reached is None else reached, taken)]


def field(nm, size=100, **more):
    return rect_mesh([(0, 0, size, size, 0)], nm)


def pairwise(points, spacing, floor):
    return all(not (abs(a[2] - b[2]) < floor and math.hypot(a[0] - b[0], a[1] - b[1]) < spacing) for i, a in enumerate(points) for b in points[i + 1:])


# ---- a map tile on disk --------------------------------------------------------------------------------------------------------

def write_map(path, ids=None, uniform=None):
    """A `.map` file with the header of the core's map_fileheader (area offset at byte 12) and an area section."""
    header = b"MAPS" + struct.pack("<I", 9) + bytes(4) + struct.pack("<I", 44) + bytes(28)
    body = struct.pack("<IHH", int.from_bytes(b"AREA", "little"), 1 if uniform is not None else 0, uniform or 0)
    if uniform is None:
        body += struct.pack("<256H", *ids)
    pathlib.Path(path).write_bytes(header + body)


def write_area_table(path, rows):
    """An AreaTable.dbc of 3.3.5a's shape: (id, continent, parent) first in each 36-field record."""
    records = b"".join(struct.pack("<3I33I", a, 1, p, *([0] * 33)) for a, p in rows)
    pathlib.Path(path).write_bytes(struct.pack("<4s4I", b"WDBC", len(rows), 36, 144, 1) + records + b"\0")


def centre(gx, gy, lx, ly):
    """The middle of chunk (lx, ly) of tile (gx, gy), by the inverse of the core's own mapping."""
    return (32 - (gx + (lx + 0.5) / 16)) * S_GRID, (32 - (gy + (ly + 0.5) / 16)) * S_GRID


S_GRID = NM.GRID


# ---- the rules -----------------------------------------------------------------------------------------------------------------

def synthetic_checks(o, g, nm):
    knobs = knobs_with(open_zone_spacing_yards=20.0, open_zone_area_max_yards=None)
    spacing, floor = 20.0, knobs["floor_tolerance_yards"]

    # The zone from the terrain: chunk ids of a tile, a uniform tile, a tile with none of the zone, and AreaTable's children.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        ids = [0] * 256
        ids[3 * 16 + 5], ids[3 * 16 + 6], ids[4 * 16 + 5] = 541, 490, 999     # a child area, the zone itself, another zone's
        write_map(tmp / "0014041.map", ids=ids)
        write_map(tmp / "0014142.map", uniform=490)
        write_map(tmp / "0014243.map", uniform=17)
        write_area_table(tmp / "AreaTable.dbc", [(490, 0), (541, 490), (537, 490), (999, 0), (1000, 999)])
        table = o.AreaTable(tmp / "AreaTable.dbc")
        check(table.zone_ids(490) == {490, 541, 537}, "the zone's areas are the zone and the areas whose parent it is (not another zone's child)")
        zone = o.Zone(tmp, 1, table.zone_ids(490))
        check(zone.tiles == {(40, 41), (41, 42)}, "a tile belongs to the zone when a chunk of it does, or the whole tile is its area")
        check(zone.area_at(*centre(40, 41, 3, 5)) == 541 and zone.inside(*centre(40, 41, 3, 5)), "a chunk of a child area is in the zone")
        check(zone.area_at(*centre(40, 41, 3, 6)) == 490, "a chunk of the zone itself is in it")
        check(zone.area_at(*centre(40, 41, 4, 5)) == 999 and not zone.inside(*centre(40, 41, 4, 5)), "a chunk of another zone is not")
        check(not zone.inside(*centre(40, 41, 5, 5)), "a chunk with no area is not")
        check(zone.inside(*centre(41, 42, 15, 0)) and zone.inside(*centre(41, 42, 0, 15)), "a tile with one area for all of it is the zone everywhere")
        check(zone.area_at(*centre(42, 43, 1, 1)) == 17 and not zone.inside(*centre(42, 43, 1, 1)), "a tile of another zone is read and is not the zone")
        check(zone.area_at(-1000 * S_GRID, 0) is None, "a point on no tile has no area")
        x0, x1, y0, y1 = zone.box()
        check(around(x0, (31 - 41) * S_GRID) and around(x1, (32 - 40) * S_GRID) and around(y0, (31 - 42) * S_GRID) and around(y1, (32 - 41) * S_GRID),
              "the box spans the tiles that hold the zone")
        (tmp / "bad.dbc").write_bytes(b"WDBC" + bytes(30))
        try:
            o.AreaTable(tmp / "bad.dbc")
        except ValueError:
            check(True, "a file that is not a 3.3.5a AreaTable is refused")
        else:
            raise AssertionError("a bad AreaTable was read")
        (tmp / "0019999.map").write_bytes(b"NOPE" + bytes(60))
        try:
            o.read_chunks(tmp / "0019999.map")
        except ValueError:
            check(True, "a file that is not a version 9 map tile is refused")
        else:
            raise AssertionError("a bad map tile was read")

    # Thin ground: the spacing, and its edge. A corridor with lattice points at x = 3.75, 13.75, 23.75 (the pitch is half the spacing,
    # the lattice is shifted by 3/8 of it) and y = 3.75.
    strip = rect_mesh([(0, 0, 25, 5, 0)], nm)
    got = sample(o, strip, knobs, anchors=[(3.75, 3.75, 0)])
    check(got == [(23.75, 3.75, 0.0)], "a native anchor keeps the points nearer than the spacing away and not the one exactly the spacing away")
    got = sample(o, strip, knobs)
    check(len(got) >= 2 and all(p in [(3.75, 3.75, 0.0), (13.75, 3.75, 0.0), (23.75, 3.75, 0.0)] for p in got) and pairwise(got, spacing, floor),
          "with no anchor, the points are on the lattice and a spacing apart")

    # A field: every kept point is a spacing from the others, and nothing is left bare (any lattice point has an anchor near).
    big = field(nm)
    got = sample(o, big, knobs)
    check(len(got) > 4 and pairwise(got, spacing, floor), "on open ground the points are at least a spacing apart")
    lattice = [(10.0 * i + 3.75, 10.0 * j + 3.75) for i in range(10) for j in range(10)]
    check(all(any(math.hypot(x - p[0], y - p[1]) < spacing for p in got) for x, y in lattice), "no lattice point is left more than a spacing from a kept point")
    check(sample(o, big, knobs) == got, "the same ground gives the same points")
    check(len({p[0] for p in got}) > math.ceil(100 / spacing) + 2, "the points are not in rows (a sweep keeps one column per spacing, 5 here)")
    near = sample(o, big, knobs, anchors=[(50.0, 50.0, 0.0)])
    check(all(math.hypot(p[0] - 50, p[1] - 50) >= spacing for p in near), "no point is nearer than the spacing to a native's anchor")

    # Where it does not sample.
    half = rect_mesh([(0, 0, 50, 50, 0), (50, 0, 100, 50, 0, False)], nm)
    check(all(p[0] <= 50 for p in sample(o, half, knobs)) and sample(o, half, knobs), "water is not sampled")
    steep = [NM.Poly([(0, 0, 0), (50, 0, 0), (50, 50, 40), (0, 50, 40)], ground=True, slope=knobs["max_slope_degrees"] + 1)]
    check(sample(o, NM.Navmesh.from_polygons(steep, []), knobs) == [], "ground steeper than the limit is not sampled")
    mild = [NM.Poly([(0, 0, 0), (50, 0, 0), (50, 50, 30), (0, 50, 30)], ground=True, slope=knobs["max_slope_degrees"])]
    got = sample(o, NM.Navmesh.from_polygons(mild, []), knobs)
    check(got and all(around(z, 0.6 * y, 1e-6) for _, y, z in got), "ground at the limit is sampled, at the height of the ground under the point")
    check(sample(o, big, knobs, reached=set()) == [] and all(p[0] <= 50 for p in sample(o, big, knobs, reached={i for i, q in enumerate(big.polys) if q.cx < 50})),
          "ground the entrance does not reach is not sampled")
    check(all(p[0] < 30 for p in sample(o, big, knobs, zone=Stub(lambda x, y: x < 30))) and sample(o, big, knobs, zone=Stub(lambda x, y: x < 30)),
          "ground outside the zone is not sampled")
    # 71kk3: a fragment the navmesh's `reached` set counts but no walk from the entrance reaches (with_bridges joined it at a shared
    # vertex of another fragment) would give its anchors entry_walk_yards inf; with the entrance the sampler leaves it bare.
    islands = rect_mesh([(0, 0, 25, 25, 0), (60, 0, 85, 25, 0)], nm)
    check(any(p[0] > 60 for p in sample(o, islands, knobs)), "without an entrance both fragments of a reached set are sampled")
    walkable = sample(o, islands, knobs, entry=(2.5, 2.5, 0.0))
    check(walkable and all(p[0] < 30 for p in walkable), "ground the walk from the entrance never reaches is not sampled, though the reached set holds it")
    for blank in (None, 0, -5):
        check(o.sampler(Stub(), knobs_with(open_zone_spacing_yards=blank)) is None, f"a spacing of {blank} samples nothing")

    # Two floors: points on the floor above are kept where it is a floor higher, not where it is the same floor.
    for rise, same in ((floor + 12, False), (floor - 4, True)):
        two = rect_mesh([(0, 0, 50, 50, 0), (0, 0, 50, 50, rise)], nm)
        got = sample(o, two, knobs)
        low, high = [p for p in got if p[2] < rise / 2], [p for p in got if p[2] >= rise / 2]
        check(pairwise(got, spacing, floor), f"two floors {rise} yards apart: no two points on one floor are nearer than the spacing")
        over = any(math.hypot(a[0] - b[0], a[1] - b[1]) < spacing for a in low for b in high)
        if same:
            check(not over and len(got) == len(sample(o, field(nm, 50), knobs)), f"floors {rise} yards apart (under the floor tolerance) are one floor: none stand above another")
        else:
            check(low and high and over, f"floors {rise} yards apart (past the floor tolerance) are two floors: points stand above one another")

    # The entrance is the designer's rows of rifts.csv, and a blank is an error, not a guess.
    with tempfile.TemporaryDirectory() as tmp:
        sheet = pathlib.Path(tmp) / "rifts.csv"
        sheet.write_text("name,d3_value,value,unit,notes\nopen_rift_entry_x,,-7900.5,yards,x\nopen_rift_entry_y,,-2135.25,yards,y\nopen_rift_entry_z,,-249.5,yards,z\n", encoding="utf-8")
        ungoro, tanaris = dict(entry_tunable="open_rift_entry"), dict(entry_tunable="open_rift_entry_tanaris")
        check(o.entrance(ungoro, sheet) == (-7900.5, -2135.25, -249.5), "the entrance is read from rifts.csv")
        check(o.entrance(tanaris, sheet) is None, "a zone whose rows are blank has no entrance and is not surveyed (hmnei)")
        sheet.write_text("name,d3_value,value,unit,notes\nopen_rift_entry_x,,-7900.5,yards,x\nopen_rift_entry_y,,,yards,y\nopen_rift_entry_z,,-249.5,yards,z\n", encoding="utf-8")
        try:
            o.entrance(ungoro, sheet)
        except ValueError as error:
            check("blank" in str(error), "a blank entrance is refused, and the message says why")
        else:
            raise AssertionError("a blank entrance was read")

    # One zone surveyed from made-up natives: three sheets, numbers, tags, the cap.
    row = dict(name=ZONE_NAME, map_id="751", source_map="1")
    mesh = corridor(nm, 200)
    zone = Stub(lambda x, y: True)
    natives = [native(1, 20, 2.5, path_id=0), native(2, 100, 2.5, path_id=77), native(3, 101, 2.5)]
    paths = {77: [(1, 100.0, 2.5, 0.0), (2, 120.0, 2.5, 0.0)]}
    sheets, report = o.survey_natives(row, zone, natives, natives, [], paths, mesh, Factions, knobs_with(open_zone_spacing_yards=None, open_zone_area_max_yards=None), (2.5, 2.5, 0.0))
    check(set(sheets) == {"rift_areas.csv", "rift_anchors.csv", "rift_routes.csv"}, "the zone survey writes three sheets: no native filter; the exit is with_zone_exits' (yh7el)")
    check([a["native_guid"] for a in sheets["rift_anchors.csv"]] == [1, 2] and all(a["dungeon"] == ZONE_NAME for a in sheets["rift_anchors.csv"]),
          "anchors are the natives' packs, named for the zone")
    check(report["native_anchors"] == 2 and report["sampled_anchors"] == 0 and report["spacing_yards"] == "", "blank spacing: natives' anchors only")
    check(len({a["area"] for a in sheets["rift_anchors.csv"]}) == 2 and report["area_cap_yards"] == knobs["area_max_yards"],
          "a blank area cap is the dungeons' (40 yards): anchors 80 yards apart are two areas")
    check([r["path_id"] for r in sheets["rift_routes.csv"]] == [77], "the stock patrol path is tied to an anchor")
    wide = knobs_with(open_zone_spacing_yards=None, open_zone_area_max_yards=100.0)
    sheets, report = o.survey_natives(row, zone, natives, natives, [], paths, mesh, Factions, wide, (2.5, 2.5, 0.0))
    check(len({a["area"] for a in sheets["rift_anchors.csv"]}) == 1 and report["area_cap_yards"] == 100.0, "the zone's own area cap joins anchors 80 yards apart")
    check(o.zone_knobs(knobs_with(open_zone_area_max_yards=None))["area_max_yards"] == knobs["area_max_yards"]
          and o.zone_knobs(knobs_with(open_zone_area_max_yards=77.0))["area_max_yards"] == 77.0, "the area cap is the zone's when set, else the dungeons'")

    sheets, report = o.survey_natives(row, zone, natives, natives, [], paths, mesh, Factions, knobs, (2.5, 2.5, 0.0))
    anchors = sheets["rift_anchors.csv"]
    sampled = [a for a in anchors if a["native_guid"] == ""]
    check(sampled and report["sampled_anchors"] == len(sampled) and report["native_anchors"] == 2, "with a spacing, thin ground adds anchors that no native stands at")
    check([a["anchor"] for a in anchors] == list(range(1, len(anchors) + 1)) and [a["native_guid"] for a in anchors[:2]] == [1, 2],
          "anchors are numbered from 1, the natives' first, then the sampled points")
    check(all(a["pack_size"] == 0 and a["native_entry"] == "" and a["source"] == "survey" for a in sampled), "a sampled anchor has no pack, no native and source survey")
    check(all(a["entry_walk_yards"] < 1e6 for a in anchors), "every anchor, sampled or not, has a walk from the entrance")
    check(sum(a["natives"] for a in sheets["rift_areas.csv"]) == 1 + 1 + 1, "an area counts natives only: the sampled points add none (packs of 1 and 2 natives, 3 in all)")
    check(all(a["tag"] == "S" for a in sheets["rift_areas.csv"] if a["natives"] == 0), "an area of sampled points alone is small")

    # The sheets: merge, and the migration.
    committed = {name: [dict(dungeon="Old", area=1), dict(dungeon=ZONE_NAME, area=9)] for name in S.SHEETS}
    merged = o.merge({"rift_areas.csv": [dict(dungeon=ZONE_NAME, area=1)]}, committed, {ZONE_NAME})
    check([r["area"] for r in merged["rift_areas.csv"]] == [1, 1] and [r["dungeon"] for r in merged["rift_areas.csv"]] == ["Old", ZONE_NAME],
          "the survey's rows replace the zone's, the dungeons' stay, the zone's go last")
    check(merged["rift_anchors.csv"] == [dict(dungeon="Old", area=1)], "a sheet the zone writes no rows to loses its old zone rows")
    kept = S.with_open_zones({name: [dict(dungeon="Old", area=7)] for name in S.SHEETS}, committed)
    check(all([r["dungeon"] for r in rows] == ["Old", ZONE_NAME] and rows[0]["area"] == 7 for rows in kept.values()),
          "a dungeon survey keeps the committed zone's rows after its own")
    sheets = {name: [] for name in S.SHEETS}
    sheets["rift_areas.csv"] = [dict(dungeon="Old", area=1, tag="S", natives=1, density_min="", density_max="", nospawn=0, source="survey"),
                                dict(dungeon=ZONE_NAME, area=2, tag="L", natives=9, density_min="", density_max="", nospawn=0, source="survey")]
    sql = S.render(sheets, {ZONE_NAME})
    check("DELETE FROM `dc_rift_area` WHERE `dungeon` IN ('Un''Goro Crater');" in sql, "the zone's migration deletes its own rows by name, quoted")
    check("CREATE TABLE" not in sql and "DELETE FROM `dc_rift_area`;" not in sql, "it makes no table and empties none")
    check("'Old'" not in sql and "(\'Un\'\'Goro Crater\', 2, \'L\', 9," in sql, "it inserts the zone's rows and not the dungeons'")
    check(sql.count("DELETE FROM") == 5, "it clears the zone from all five tables")
    plain = S.render(sheets)
    check("'Old'" in plain and "(\'Un\'\'Goro Crater\', 2" not in plain, "the dungeons' migration keeps the dungeons' rows and leaves the zone's out")
    # every open zone of the sheet, entrance or not (hyoic.5: the acts grow the sheet, so the list is read from it)
    every = ", ".join("'" + n.replace("'", "''") + "'" for n in sorted(z["name"] for z in O.read_zones()))
    check(f"DELETE FROM `dc_rift_area` WHERE `dungeon` NOT IN ({every});" in plain
          and "DELETE FROM `dc_rift_area`;" not in plain,
          "and empties each table of the dungeons' rows only, so a re-applied 0001 leaves every open zone's (hmnei: every zone of the sheet, entrance or not)")


def around(a, b, tolerance=0.06):
    return abs(a - b) <= tolerance


# ---- the mutants -------------------------------------------------------------------------------------------------------------

ZONE_MUTANTS = [
    ("the spacing's edge is excluded", "math.hypot(x - ox, y - oy) < spacing", "math.hypot(x - ox, y - oy) <= spacing"),
    ("the floor is ignored", "if any(abs(z - oz) < floor and", "if any(True and"),
    ("water is sampled", "if not poly.ground or poly.slope > slope:", "if poly.slope > slope:"),
    ("steep ground is sampled", "if not poly.ground or poly.slope > slope:", "if not poly.ground:"),
    ("ground outside the zone is sampled", "if poly.contains(x, y) and zone.inside(x, y):", "if poly.contains(x, y):"),
    ("the points are tried in a sweep", "candidates.sort(key=lambda c: c[:4])", "candidates.sort(key=lambda c: c[1:4])"),
    ("the point is at the polygon's centre height", "poly.height(x, y)))", "poly.cz))"),
    ("unreached ground is sampled", "for index in sorted(reached):", "for index in range(len(mesh.polys)):"),
    ("native anchors are not kept apart", "for a in anchors:\n            n = a[\"native\"]", "for a in anchors[:0]:\n            n = a[\"native\"]"),
    ("a blank spacing still samples", "if not spacing or spacing <= 0:", "if spacing is None:"),
    ("a fragment the entrance cannot walk to is sampled", "if walked is not None and not any(n in walked for n in mesh.poly_nodes[index]):", "if False:"),
    ("the lattice is a spacing apart", "pitch = spacing / 2", "pitch = spacing"),
    ("the lattice is not shifted off the navmesh's grid", "PHASE = 0.375", "PHASE = 0.0"),
    ("the area cap is always the dungeons'", "dict(knobs, area_max_yards=cap if cap else knobs[\"area_max_yards\"])", "dict(knobs)"),
    ("a blank area cap is zero", "cap if cap else knobs[\"area_max_yards\"]", "cap or 0.0001"),
    ("the zone's rows are kept when it is surveyed again", "out = {name: [r for r in rows if r[\"dungeon\"] not in zone_names] for name, rows in committed.items()}",
     "out = {name: list(rows) for name, rows in committed.items()}"),
    ("the entrance is guessed when blank", "if not all(values):", "if False:"),
    ("a chunk of a child area is not the zone's", "return {zone} | {area for area, parent in self.parent.items() if parent == zone}", "return {zone}"),
    ("every area is the zone's child", "if parent == zone}", "if parent}"),
    ("a whole-tile area is read as chunks", "if flags & NO_AREA:", "if False:"),
]
SURVEY_MUTANTS = [
    ("a dungeon survey drops the zone's rows", 'rows + [r for r in committed[name] if r["dungeon"] in zones]', "rows"),
    ("a sampled anchor sorts before the natives'", '(anchors[i]["native"]["guid"] is None, anchors[i]["native"]["guid"] or 0)', '(anchors[i]["native"]["guid"] is not None, anchors[i]["native"]["guid"] or 0)'),
    ("a sampled anchor has a pack", "anchors.append(dict(native=dict(spot, guid=None, entry=None), size=0,", "anchors.append(dict(native=dict(spot, guid=None, entry=None), size=1,"),
    ("the zone's migration deletes every dungeon's rows", 'parts.append(f"DELETE FROM `{table}` WHERE `dungeon` IN ({names});")', 'parts.append(f"DELETE FROM `{table}`;")'),
    ("the dungeons' migration keeps the zone's rows", 'rows = [r for r in sheets[name] if r["dungeon"] not in skip]', "rows = list(sheets[name])"),
]


def run_synthetic(o, g, nm):
    with contextlib.redirect_stdout(open("/dev/null", "w")):
        synthetic_checks(o, g, nm)


def test_rules_and_mutants():
    synthetic_checks(O, S, NM)
    for what, old, new in ZONE_MUTANTS:
        mutant = module_from(ZONE_SOURCE, old, new, "generate_open_zone_survey_mutant")
        try:
            run_synthetic(mutant, S, NM)
        except (AssertionError, ValueError, KeyError, IndexError, ZeroDivisionError, TypeError):
            print("PASS mutant killed: " + what, flush=True)
            continue
        raise AssertionError("zone mutant survived: " + what)
    here = sys.modules[__name__]
    for what, old, new in SURVEY_MUTANTS:
        mutant = module_from(SURVEY_SOURCE, old, new, "generate_rift_survey_mutant")
        real = (O.S, here.S)
        O.S = here.S = mutant      # the zone's generator and this file both reach the survey code through S
        try:
            run_synthetic(O, mutant, NM)
        except (AssertionError, ValueError, KeyError, IndexError, ZeroDivisionError, TypeError):
            print("PASS mutant killed: " + what, flush=True)
            continue
        finally:
            O.S, here.S = real
        raise AssertionError("survey mutant survived: " + what)


# ---- the real data ---------------------------------------------------------------------------------------------------------------

def committed_zone_rows():
    sheets = S.read_sheets()
    return {name: [r for r in rows if r["dungeon"] == ZONE_NAME] for name, rows in sheets.items()}


def test_data():
    mysql, defaults = fixture_db.mysql_and_defaults([])
    db = S.Database(mysql, defaults, "acore_world")
    areas = O.AreaTable(DATA / "dbc/AreaTable.dbc")
    factions = S.Factions(DATA / "dbc/FactionTemplate.dbc")
    zones = O.read_zones()
    check(zones[0]["name"] == ZONE_NAME and zones[0]["map_id"] == "751" and zones[0]["source_map"] == "1" and zones[0]["zone_id"] == "490",
          "the first open zone: Un'Goro Crater, zone 490 of map 1, the copy on map 751")
    check([z["key"] for z in zones][:5] == ["ungoro", "tanaris", "thousandneedles", "azshara", "moonglade"] and len(zones) == 40
          and all(O.entrance(z) is not None for z in zones),
          "every open zone has an entrance (hmnei: the designer's .gps of 2026-10-11 for the first five; hyoic.5, hyoic.8 and hyoic.10: the stock .tele spots for the next 35)")
    clone = [r for r in S.read_csv(MODULE / "data/d3/world_open_rift_dbc.csv") if r["table"] == "Map" and r["id"] == "751" and r["field"] == "InstanceType"]
    check(len(clone) == 1 and clone[0]["source_id"] == zones[0]["source_map"], "the copy's map id and source map are the Map row of the open-rift sheet")
    check("`map_id` FROM `dc_rift_open_zone`" in (MODULE / "src/rifts/dc_open_rift.cpp").read_text(encoding="utf-8")
          and "('ungoro', 'Un''Goro Crater', 751, 490, 'open_rift_entry', 2, 1)" in (MODULE / "data/sql/db-world/updates/rifts_0026_open_zones.sql").read_text(encoding="utf-8"),
          "dc_open_rift.cpp reads each zone's map from its zone table (hyoic.7), which holds the same zone on the same map")

    inside = areas.zone_ids(490)
    check(inside == {490, 537, 538, 539, 540, 541, 542, 543, 1942, 1943, 4381, 4382}, "AreaTable gives Un'Goro its 11 child areas (the research's list)")
    zone = O.Zone(DATA / "maps", 1, inside)
    check(zone.tiles == {(gx, gy) for gx in range(43, 48) for gy in range(32, 37)}, "the zone's tiles are gx 43 to 47, gy 32 to 36 (the research's 25)")
    entry = O.entrance(zones[0])
    check(zone.inside(*entry[:2]), "the designer's entrance is in the zone")
    for name, (x, y) in dict(marshlands=(-7205.56, -2436.67), central=(-7351.04, -1315.89), marshal=(-6160.06, -1142.43), shaper=(-6115.09, -1339.45)).items():
        check(zone.inside(x, y), f"Un'Goro's graveyard {name} is in the zone")
    # hmnei: each of the other four entrances stands in its own zone (Tanaris's in Gadgetzan, area 976, a child of 440)
    for other in zones[1:]:
        own = O.Zone(DATA / "maps", int(other["source_map"]), areas.zone_ids(int(other["zone_id"])))   # hyoic.8, hyoic.10: the Eastern Kingdoms' zones read map 0, Outland's map 530
        point = O.entrance(other)
        check(own.inside(*point[:2]) and (other["source_map"] != "1" or not zone.inside(*point[:2])), f"the designer's {other['name']} entrance is in {other['name']}")
    check(976 in areas.zone_ids(440), "Gadgetzan is part of Tanaris")

    knobs = S.read_knobs()
    check(knobs["open_zone_spacing_yards"] == 40.0 and knobs["open_zone_area_max_yards"] == 120.0,
          "the spacing and the area cap are the designer's 40 and 120 yards in rifts.csv (card q-1016-24, diablocraft-71kk3)")
    sheets, report = O.survey_zone(zones[0], db, DATA / "mmaps", DATA / "maps", areas, factions, knobs, entry)
    check(report["tiles"] == 25 and report["spawn_rows_in_zone"] < report["spawn_rows_in_box"], "the box holds creatures of the rim and other zones, which the zone leaves out")
    floor_natives = [n for n in S.load_natives(db, {1}, zone.box()) if n["z"] < -100]
    mine = {n["guid"] for n in S.load_natives(db, {1}, zone.box()) if zone.inside(n["x"], n["y"])}
    got = len(mine & {n["guid"] for n in floor_natives})
    check(0.99 * len(floor_natives) <= got <= len(floor_natives) and got == report["spawn_rows_in_zone"] and len(floor_natives) >= 940,
          f"the zone's natives are the Planner's crater-floor ones: {got} of {len(floor_natives)} below z -100 (his 'about 948')")
    anchors = sheets["rift_anchors.csv"]
    check(report["natives_today"] == report["combatants"] and report["other_part"] == 0 and report["off_navmesh"] == 0,
          f"every combatant of the zone ({report['combatants']}) is on the navmesh and reachable from the entrance")
    bare, bare_report = O.survey_zone(zones[0], db, DATA / "mmaps", DATA / "maps", areas, factions,
                                      dict(knobs, open_zone_spacing_yards=None, open_zone_area_max_yards=None), entry)
    check(len(bare["rift_anchors.csv"]) == bare_report["native_anchors"] and bare_report["sampled_anchors"] == 0, "blank spacing: the anchors are the natives' packs")
    check(len(anchors) == report["native_anchors"] + report["sampled_anchors"] and report["native_anchors"] == bare_report["native_anchors"]
          and report["sampled_anchors"] > 0 and report["spacing_yards"] == 40.0 and report["area_cap_yards"] == 120.0,
          "at the designer's 40 yards the thin ground gets sampled anchors beside the same natives', in areas of up to 120 yards")
    check(all(zone.inside(a["x"], a["y"]) for a in anchors), "every anchor stands in the zone")
    check(all(a["entry_walk_yards"] < 1e6 for a in anchors), "every anchor can be walked to from the entrance")
    paths = {int(r["path_id"]) for r in sheets["rift_routes.csv"]}
    stock = {int(line) for line in db.query("SELECT DISTINCT id FROM waypoint_data")}
    check(paths and paths <= stock and len(paths) <= 33, f"{len(paths)} patrol routes, each a stock waypoint path (the Planner counted 33 movers)")
    check({r["anchor"] for r in sheets["rift_routes.csv"]} <= {a["anchor"] for a in anchors}, "every route is tied to an anchor of the zone")
    check(all(r["dungeon"] == ZONE_NAME for rows in sheets.values() for r in rows) and "rift_native_filter.csv" not in sheets and "rift_exit_points.csv" not in sheets,
          "no native-filter row (the natives stay on the continent); the exit point is with_zone_exits' (yh7el)")
    committed = S.read_sheets()
    check(not [r for r in committed["rift_native_filter.csv"] if r["map_id"] == "751" or r["dungeon"] == ZONE_NAME or r["map_id"] == "1"], "the committed filter refuses nothing on map 1 or 751")
    far = max((a for a in committed["rift_anchors.csv"] if a["dungeon"] == ZONE_NAME), key=lambda a: (float(a["entry_walk_yards"]), -int(a["anchor"])))
    check([(r["x"], r["y"], r["source"]) for r in committed["rift_exit_points.csv"] if r["dungeon"] == ZONE_NAME] == [(far["x"], far["y"], "survey")]
          or [r["source"] for r in committed["rift_exit_points.csv"] if r["dungeon"] == ZONE_NAME] == ["alex"],
          "the committed exit point for the zone is its farthest anchor by walk, or the designer's spot (yh7el)")
    check(len({r["dungeon"] for r in committed["rift_anchors.csv"]}) == 30 + len(zones) and {z["name"] for z in zones} <= {r["dungeon"] for r in committed["rift_anchors.csv"]},
          "the anchor sheet holds the 30 dungeons and every open zone")

    # The committed sheets are the survey, unless the designer has edited them.
    if S.has_alex(committed):
        print("SKIP the committed sheets hold rows of the designer's; they are the source now", flush=True)
    else:
        zone_rows = committed_zone_rows()
        for name in O.ZONE_SHEETS:
            fresh = [{c: str(r[c]) for c in S.SHEETS[name]} for r in sheets[name]]
            check(fresh == [{c: r[c] for c in S.SHEETS[name]} for r in zone_rows[name]], f"{name}: the zone's rows are what the survey produces")
        want = list(csv.DictReader(open(O.REPORT, encoding="utf-8")))
        check([r["zone"] for r in want] == [z["name"] for z in zones], "the report has a row per zone, in sheet order (hmnei)")
        check({c: str(report[c]) for c in O.REPORT_COLUMNS} == {c: want[0][c] for c in O.REPORT_COLUMNS}, "the report's Un'Goro row is what the survey produces")
    check((MODULE / "data/generated" / S.OPEN_NAME).read_text(encoding="utf-8") == S.render(committed, S.open_zone_names())
          == (MODULE / "data/sql/db-world/updates" / S.OPEN_NAME).read_text(encoding="utf-8"), "the zone's migration and its mirror are what the sheets render")
    check((MODULE / "data/generated" / S.NAME).read_text(encoding="utf-8") == S.render(committed)
          == (MODULE / "data/sql/db-world/updates" / S.NAME).read_text(encoding="utf-8"), "the dungeons' migration is the same with the zone's rows in the sheets")

    # A rehearsal with numbers of the test's own (not the designer's): the points keep their distance and stand on reachable ground in the zone.
    rehearsal = dict(knobs, open_zone_spacing_yards=80.0, open_zone_area_max_yards=120.0)
    sheets, report = O.survey_zone(zones[0], db, DATA / "mmaps", DATA / "maps", areas, factions, rehearsal, entry)
    anchors = sheets["rift_anchors.csv"]
    sampled = [a for a in anchors if a["native_guid"] == ""]
    check(len(sampled) > 100 and report["native_anchors"] == len(anchors) - len(sampled), f"at 80 yards the thin ground gets {len(sampled)} more anchors")
    mesh = NM.Navmesh.from_map(1, DATA / "mmaps", zone.tiles)
    snap = (rehearsal["snap_xy_yards"], rehearsal["snap_z_yards"], rehearsal["snap_z_far_yards"])
    floor = rehearsal["floor_tolerance_yards"]
    points = [(a["x"], a["y"], a["z"]) for a in anchors]
    cells = collections.defaultdict(list)
    for p in points:
        cells[(int(p[0] // 80), int(p[1] // 80))].append(p)
    close = 0
    for a in sampled:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for p in cells.get((int(a["x"] // 80) + dx, int(a["y"] // 80) + dy), ()):
                    if p != (a["x"], a["y"], a["z"]) and abs(p[2] - a["z"]) < floor and math.hypot(p[0] - a["x"], p[1] - a["y"]) < 80 - 0.01:
                        close += 1
    check(close == 0, "no sampled point is nearer than 80 yards to any other anchor on its floor")
    check(all(zone.inside(a["x"], a["y"]) for a in sampled), "every sampled point is in the zone")
    located = [mesh.locate(a["x"], a["y"], a["z"], *snap) for a in sampled]
    check(all(p is not None for p in located), "every sampled point is on the navmesh")
    check(all(mesh.polys[p].ground and mesh.polys[p].slope <= rehearsal["max_slope_degrees"] for p in located), "on ground that is not water and not steeper than the limit")
    check(all(a["entry_walk_yards"] < 1e6 for a in sampled), "and the entrance can walk to each")
    again, _ = O.survey_zone(zones[0], db, DATA / "mmaps", DATA / "maps", areas, factions, rehearsal, entry)
    check(again == sheets, "the same inputs give the same sheets")
    check(len({a["area"] for a in anchors}) < len(anchors) and report["areas_l"] >= 1, "the wider area cap gives areas of several anchors, some large")


# ---- the replay -----------------------------------------------------------------------------------------------------------------

def test_mysql(port):
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root", "--batch",
               "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

    def sql(text, database=None):
        done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                              capture_output=True, encoding="utf-8")
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.rstrip("\n")

    first = (MODULE / "data/sql/db-world/updates" / S.NAME).read_text(encoding="utf-8")
    second = (MODULE / "data/sql/db-world/updates" / S.OPEN_NAME).read_text(encoding="utf-8")
    sheets = S.read_sheets()
    zones = S.open_zone_names()   # hmnei: every open zone is in the zones' migration
    in_zones = "dungeon IN (" + ", ".join(S.quote(z) for z in sorted(zones)) + ")"
    zone_rows = {name: sum(1 for r in rows if r["dungeon"] in zones) for name, rows in sheets.items()}
    dungeon_rows = {name: len(rows) - zone_rows[name] for name, rows in sheets.items()}
    sql("CREATE DATABASE rift_zone CHARACTER SET utf8mb4;")
    sql(first, "rift_zone")
    sql(second, "rift_zone")
    sql(second, "rift_zone")
    for name in S.SHEETS:
        table = S.TABLES[name][0]
        check(sql(f"SELECT COUNT(*) FROM `{table}` WHERE {in_zones}", "rift_zone") == str(zone_rows[name]),
              f"applied twice: {table} holds the zones' {zone_rows[name]} rows once")
        check(sql(f"SELECT COUNT(*) FROM `{table}` WHERE NOT {in_zones}", "rift_zone") == str(dungeon_rows[name]),
              f"{table} still holds the dungeons' {dungeon_rows[name]} rows")
    check(sql("SELECT COUNT(*) FROM dc_rift_route r LEFT JOIN dc_rift_anchor a ON a.dungeon=r.dungeon AND a.anchor=r.anchor WHERE a.anchor IS NULL", "rift_zone") == "0",
          "every route names an anchor that exists")
    check(sql("SELECT COUNT(*) FROM dc_rift_anchor a LEFT JOIN dc_rift_area r ON r.dungeon=a.dungeon AND r.area=a.area WHERE r.area IS NULL", "rift_zone") == "0",
          "every anchor is in an area that exists")
    check(sql(f"SELECT COUNT(*) FROM dc_rift_native_filter WHERE {in_zones}", "rift_zone") == "0", "the zones refuse no native")
    check(sql(f"SELECT COUNT(*) FROM dc_rift_anchor WHERE {in_zones} AND native_guid IS NULL", "rift_zone") == str(
        sum(1 for r in sheets["rift_anchors.csv"] if r["dungeon"] in zones and r["native_guid"] == "")), "a blank native reads back as NULL")

    # The designer's edit of a dungeon's anchor survives the zone's migration being applied again; a migration that deleted every row does not.
    edited = sheets["rift_anchors.csv"][0]
    sql(f"UPDATE dc_rift_anchor SET x=x+1, source='alex' WHERE dungeon={S.quote(edited['dungeon'])} AND anchor={edited['anchor']};", "rift_zone")
    sql(second, "rift_zone")
    check(sql(f"SELECT source FROM dc_rift_anchor WHERE dungeon={S.quote(edited['dungeon'])} AND anchor={edited['anchor']}", "rift_zone") == "alex",
          "applying the zone's migration leaves a dungeon's edited anchor alone")
    wipe = re.sub(r"WHERE `dungeon` IN \([^)]*\)", "", second)
    check(wipe != second, "the mutant removed the WHERE")
    sql(wipe, "rift_zone")
    check(sql("SELECT COUNT(*) FROM dc_rift_anchor", "rift_zone") == str(zone_rows["rift_anchors.csv"]), "mutant killed: without its WHERE the zone's migration empties the dungeons' rows")

    # The updater re-applies 0001 when its hash changes (dev runs Updates.Redundancy 1, after every --export); 0002 then does not re-run,
    # so a changed 0001 applied after 0002 must leave the zone's rows where they are (diablocraft-set6).
    def zone_counts():
        return {name: sql(f"SELECT COUNT(*) FROM `{S.TABLES[name][0]}` WHERE {in_zones}", "rift_zone") for name in S.SHEETS}

    sql("DROP DATABASE rift_zone;")
    sql("CREATE DATABASE rift_zone CHARACTER SET utf8mb4;")
    sql(first, "rift_zone")
    sql(second, "rift_zone")
    want = {name: str(zone_rows[name]) for name in S.SHEETS}
    check(zone_counts() == want, "0001 then 0002: the zone's rows are there")
    changed = first + "-- a later --export changed a dungeon row, so this file's hash is new\nUPDATE dc_rift_anchor SET x=x+1 WHERE anchor=1;\n"
    sql(changed, "rift_zone")
    check(zone_counts() == want, "a changed 0001 applied after 0002 leaves the zone's rows")
    check(sql("SELECT COUNT(*) FROM dc_rift_anchor", "rift_zone") == str(dungeon_rows["rift_anchors.csv"] + zone_rows["rift_anchors.csv"]),
          "and the dungeons' rows are 0001's again, once")
    emptying = re.sub(r"( WHERE `dungeon` NOT IN \([^)]*\))(;)", r"\2", first)
    check(emptying != first, "the mutant removed the NOT IN")
    sql(emptying, "rift_zone")
    check(zone_counts() == {name: "0" for name in S.SHEETS}, "mutant killed: a 0001 that empties every row loses the zone's")

    # --export brings the zone's rows home with the dungeons', zone last.
    sql("DROP DATABASE rift_zone;")
    sql("CREATE DATABASE rift_zone CHARACTER SET utf8mb4;")
    sql(first, "rift_zone")
    sql(second, "rift_zone")
    with tempfile.TemporaryDirectory(dir=str(fixture_db.fixture_dir() / "disposable")) as tmp:
        defaults = pathlib.Path(tmp) / "client.cnf"
        defaults.write_text(f"[client]\nhost=127.0.0.1\nport={port}\nuser=root\n", encoding="utf-8")
        folder = pathlib.Path(tmp) / "d3"
        folder.mkdir()
        S.export(S.Database(MYSQL, defaults, "rift_zone"), folder)
        got = S.read_sheets(folder, missing_ok=True)
        check(len(got["rift_anchors.csv"]) == len(sheets["rift_anchors.csv"])
              and [r["dungeon"] for r in got["rift_anchors.csv"]] == [r["dungeon"] for r in sheets["rift_anchors.csv"]]
              and got["rift_anchors.csv"][-1]["dungeon"] in zones,
              "the export brings the zones' anchors home after the dungeons', in the sheet's order")
        check([r["native_guid"] for r in got["rift_anchors.csv"] if r["dungeon"] == ZONE_NAME]
              == [r["native_guid"] for r in sheets["rift_anchors.csv"] if r["dungeon"] == ZONE_NAME], "and a sampled anchor's blank native comes back blank")
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_rules_and_mutants()
    test_data()
    isolated(test_mysql)

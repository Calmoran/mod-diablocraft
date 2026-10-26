"""diablocraft-7vhj - the survey of the rift dungeons (monster-spawning.md 3.5.1, Part S0).

What this proves, and what it does not:

  * The rules, on small made-up dungeons whose answers are known by arithmetic: the combatant filter (each reason and a
    keeper), packs (the link distance's edge, the floor, a chain, a stock formation), the anchor (nearest the centre), the
    S/M/L tags at their edges, walking distance (a corridor, and two rooms 16 yards apart through a wall whose walk is
    long), the area cap at its edge, the navmesh's parts (an unreachable room, a fragment that joins and three that do
    not), two dungeon rows on one map, stock patrol paths, the exit point, the report's estimate and the migration's
    text. The same checks run against 37 single-rule mutants of the survey and the navmesh code, each of which must turn
    them red.
  * The data. The survey is re-run on the fixture world copy and the real mmaps and must equal the committed sheets; its
    counts are held against the Planner's measurement in monster-spawning.md Appendix B (spawn rows exactly, combatants
    and packs within the stated reasons); the two Scarlet Monastery rows get anchors that share no native; Dire Maul East
    leaves its other wings out; the faction rule agrees with the Planner's hand list.
  * `rift_survey_0001.sql` is replayed twice on a disposable MySQL and read back; `--export` brings edits made in those
    tables (a moved anchor, an added one of the designer's, a removed route) into the sheets; `--survey` refuses over his rows.
  * NOT proved: that the areas look right in game (the designer's pass on dev, Part S4), and the spawner (Part S2).
"""
import collections
import contextlib
import csv
import math
import pathlib
import re
import subprocess
import sys
import tempfile
import types

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db
import generate_rift_survey as G
import rift_navmesh as NM
from test_account_economy_sql import MYSQL, ROOT, isolated
from test_slot_vendors import check, mutate

MODULE = ROOT / "mod-diablocraft"
SURVEY_SOURCE = MODULE / "scripts/generate/rifts/generate_rift_survey.py"
MESH_SOURCE = MODULE / "scripts/rift_navmesh.py"
PLAN = ROOT / "docs/proposals/monster-spawning.md"
DATA = ROOT / "azerothcore-wotlk/build/server/data"


# ---- small dungeons ---------------------------------------------------------------------------------------------------

def square(x, y, s, z, ground=True):
    return NM.Poly([(x, y, z), (x + s, y, z), (x + s, y + s, z), (x, y + s, z)], ground=ground)


def rect_mesh(rects, nm, s=5):
    """A navmesh of s-yard squares over the rectangles (x0, y0, x1, y1, z[, ground]); squares sharing an edge are joined."""
    polys, keys = [], {}
    for rect in rects:
        x0, y0, x1, y1, z = rect[:5]
        for i in range(int((x1 - x0) // s)):
            for j in range(int((y1 - y0) // s)):
                keys[(x0 + i * s, y0 + j * s, z)] = len(polys)
                polys.append(nm.Poly([(x0 + i * s, y0 + j * s, z), (x0 + i * s + s, y0 + j * s, z),
                                      (x0 + i * s + s, y0 + j * s + s, z), (x0 + i * s, y0 + j * s + s, z)],
                                     ground=rect[5] if len(rect) > 5 else True))
    portals = []
    for (x, y, z), a in keys.items():
        for dx, dy in ((s, 0), (0, s)):
            b = keys.get((x + dx, y + dy, z))
            if b is not None:
                edge = ((x + s, y, z), (x + s, y + s, z)) if dx else ((x, y + s, z), (x + s, y + s, z))
                portals.append((a, b) + edge)
    return nm.Navmesh.from_polygons(polys, portals)


def native(guid, x, y, z=0.0, **fields):
    row = dict(guid=guid, entry=1000 + guid, map=1, x=x, y=y, z=z, o=1.5, spawn_mask=1, phase_mask=1, rank=0, type=7,
               flags_extra=0, unit_flags=0, faction=14, name=f"n{guid}", path_id=0)
    row.update(fields)
    return row


class Factions:
    """Stand-in for the faction table: faction 35 is friendly, everything else is hostile."""

    @staticmethod
    def hostile_to_players(faction):
        return faction != 35


def dungeon(name="Test Dungeon", map_id=1, entry=(2.5, 2.5, 0.0)):
    return dict(name=name, map_id=str(map_id), entry_x=str(entry[0]), entry_y=str(entry[1]), entry_z=str(entry[2]))


def corridor(nm, length=200, extra=()):
    return rect_mesh([(0, 0, length, 5, 0)] + list(extra), nm)


def run(g, mesh, natives, formations=(), paths=None, row=None, avoid=()):
    return g.survey_dungeon(row or dungeon(), natives, list(formations), paths or {}, mesh, list(avoid), Factions, g.read_knobs())


def around(a, b, tolerance=0.06):
    return abs(a - b) <= tolerance


# ---- the rules ----------------------------------------------------------------------------------------------------------

def synthetic_checks(g, nm):
    knobs = g.read_knobs()
    link, floor, cap = knobs["pack_link_yards"], knobs["floor_tolerance_yards"], knobs["area_max_yards"]

    # The combatant filter: each reason, and a keeper.
    keep = native(1, 0, 0)
    check(g.combatant(keep, Factions) is None, "a hostile fighting native is a combatant")
    for reason, change in (("not in normal difficulty", dict(spawn_mask=2)), ("not in the visible phase", dict(phase_mask=2)),
                           ("critter", dict(type=g.TYPE_CRITTER)), ("trigger", dict(flags_extra=g.EXTRA_TRIGGER)),
                           ("unselectable", dict(unit_flags=g.UNIT_NOT_SELECTABLE)), ("not hostile to players", dict(faction=35))):
        check(g.combatant(native(1, 0, 0, **change), Factions) == reason, f"not a combatant: {reason}")
    check(g.combatant(native(1, 0, 0, spawn_mask=3), Factions) is None, "a native in both difficulties is a combatant")

    # Packs.
    def packs(places, formations=()):
        natives = [native(i + 1, x, y, z) for i, (x, y, z) in enumerate(places)]
        return [[n["guid"] for n in p] for p in g.make_packs(natives, formations, knobs)]

    check(packs([(0, 0, 0), (link, 0, 0)]) == [[1, 2]], "two natives exactly the link distance apart are one pack")
    check(len(packs([(0, 0, 0), (link + 0.5, 0, 0)])) == 2, "two natives past the link distance are two packs")
    check(packs([(0, 0, 0), (0, 0, floor - 0.1)]) == [[1, 2]], "natives just under the floor tolerance apart in height are one pack")
    check(len(packs([(0, 0, 0), (0, 0, floor)])) == 2, "natives a floor apart in height are two packs")
    check(packs([(0, 0, 0), (link - 1, 0, 0), (2 * link - 2, 0, 0)]) == [[1, 2, 3]], "a chain of links is one pack")
    check(packs([(0, 0, 0), (100, 0, 0), (200, 0, 0)], [(1, 3)]) == [[1, 3], [2]], "a stock formation joins natives far apart")
    check(len(packs([(0, 0, 0), (100, 0, 0)], [(1, 99)])) == 2, "a formation member that is not here joins nothing")
    pack = [native(1, 0, 0), native(2, 6, 0), native(3, 12, 0)]
    check(g.anchor_of(pack)["guid"] == 2, "the anchor is the native nearest the pack's centre")
    check(g.anchor_of([native(5, 0, 0), native(4, 0, 0)])["guid"] == 4, "a tie goes to the lower guid")

    # Tags.
    for count, tag in ((1, "S"), (3, "S"), (4, "M"), (7, "M"), (8, "L"), (30, "L")):
        check(g.tag_of(count, knobs) == tag, f"{count} natives make an {tag} area")

    # A straight corridor: walking distance is the length of the walk.
    mesh = corridor(nm)
    spaced = [native(k + 1, 7.5 + 12 * k, 2.5) for k in range(14)]          # 12 apart, past the link: 14 packs
    result = run(g, mesh, spaced)
    anchors = {a["native_guid"]: a for a in result["anchors"]}
    check(len(anchors) == 14, "fourteen packs make fourteen anchors")
    check(all(around(a["entry_walk_yards"], abs(a["x"] - 2.5), 0.11) for a in anchors.values()),
          "each anchor's walking distance from the entry is the corridor's length to it")
    by_area = collections.defaultdict(list)
    for a in result["anchors"]:
        by_area[a["area"]].append(a)
    check(sum(len(v) for v in by_area.values()) == 14 and len(by_area) < 14, "every anchor is in one area and areas hold several")
    check(all(max(a["x"] for a in v) - min(a["x"] for a in v) <= cap for v in by_area.values()), "no area is wider than the cap")
    check(len(by_area) <= math.ceil(14 / 4) + 1, "areas are as full as the cap allows (4 anchors 12 apart span 36)")
    check([a["area"] for a in run(g, mesh, spaced)["anchors"]] == [a["area"] for a in result["anchors"]], "the same survey twice gives the same areas")
    check(sorted(a["anchor"] for a in result["anchors"]) == list(range(1, 15)), "anchors are numbered from 1 in native order")
    check([a["native_guid"] for a in sorted(result["anchors"], key=lambda a: a["anchor"])] == sorted(anchors), "anchor numbers follow the native's guid")

    # The cap's edge: 40 yards apart is one area, 41 is two.
    edge = run(g, mesh, [native(1, 20, 2.5), native(2, 20 + cap, 2.5)])
    check(len({a["area"] for a in edge["anchors"]}) == 1, "two anchors exactly the cap apart share an area")
    edge = run(g, mesh, [native(1, 20, 2.5), native(2, 21 + cap, 2.5)])
    check(len({a["area"] for a in edge["anchors"]}) == 2, "two anchors past the cap are two areas")

    # Walking, not straight lines: two rooms 20 yards apart through a wall, joined by a long way round.
    rooms = rect_mesh([(0, 0, 25, 25, 0), (0, 40, 25, 65, 0), (25, 0, 125, 5, 0), (120, 5, 125, 60, 0), (25, 55, 125, 60, 0)], nm)
    two = run(g, rooms, [native(1, 12.5, 22.5), native(2, 12.5, 42.5)])
    straight = math.hypot(0, 20)
    check(straight <= cap and len({a["area"] for a in two["anchors"]}) == 2,
          "rooms 20 yards apart through a wall are two areas, though a straight line would join them")
    check(two["anchors"][1]["entry_walk_yards"] > 200, "the walk round the wall is long")

    # What the navmesh keeps: a native in a room the entry cannot reach, one off the mesh, and fragments.
    split = rect_mesh([(0, 0, 50, 5, 0), (0, 100, 50, 105, 0)], nm)
    r = run(g, split, [native(1, 20, 2.5), native(2, 20, 102.5), native(3, 300, 300)])
    check([a["native_guid"] for a in r["anchors"]] == [1], "only the entry's part of the map is kept")
    check(r["counts"]["other_part_of_map"] == 1 and r["counts"]["off_navmesh"] == 1, "the other room and the off-mesh native are counted")
    b = knobs["fragment_bridge_yards"]

    # A fragment is a few squares of floor beside the corridor, `gap` yards off (the gap is a whole number of yards).
    def fragment_mesh(gap, cells):
        base = rect_mesh([(0, 0, 100, 5, 0)], nm)
        extra = rect_mesh([(30, 5 + gap, 30 + 5 * cells, 10 + gap, 0)], nm)
        polys = base.polys + extra.polys
        shift = len(base.polys)
        portals = base.portals + [(a + shift, c + shift, p, q) for a, c, p, q in extra.portals]
        return nm.Navmesh.from_polygons(polys, portals)
    inside, outside = int(b) - 1, int(b) + 4
    r = run(g, fragment_mesh(inside, 3), [native(1, 10, 2.5), native(2, 37.5, 7.5 + inside)])
    check(len(r["anchors"]) == 2, "a small fragment within the bridge distance joins the dungeon's part")
    r = run(g, fragment_mesh(outside, 3), [native(1, 10, 2.5), native(2, 37.5, 7.5 + outside)])
    check([a["native_guid"] for a in r["anchors"]] == [1], "a fragment past the bridge distance does not")
    r = run(g, fragment_mesh(inside, 30), [native(1, 10, 2.5), native(2, 37.5, 7.5 + inside)])
    check([a["native_guid"] for a in r["anchors"]] == [1], "a fragment larger than the dungeon's part is a wing of its own and does not join")
    def stacked(height):
        base = rect_mesh([(0, 0, 100, 5, 0)], nm)
        extra = rect_mesh([(30, 0, 45, 5, height)], nm)
        shift = len(base.polys)
        return nm.Navmesh.from_polygons(base.polys + extra.polys, base.portals + [(a + shift, c + shift, p, q) for a, c, p, q in extra.portals])
    r = run(g, stacked(b - 1), [native(1, 10, 2.5), native(2, 37.5, 2.5, b - 1)])
    check(len(r["anchors"]) == 2, "a fragment floor just under the bridge distance above the corridor joins")
    r = run(g, stacked(b + 1), [native(1, 10, 2.5), native(2, 37.5, 2.5, b + 1)])
    check([a["native_guid"] for a in r["anchors"]] == [1], "a fragment floor just over the bridge distance above does not (the distance is in 3D)")
    r = run(g, fragment_mesh(inside, 20), [native(1, 10, 2.5), native(2, 37.5, 7.5 + inside)])
    check([a["native_guid"] for a in r["anchors"]] == [1], "a fragment exactly as large as the dungeon's part does not join either")
    r = run(g, fragment_mesh(inside, 3), [native(1, 10, 2.5), native(2, 37.5, 7.5 + inside)], avoid=[(37.5, 7.5 + inside, 0.0)])
    check([a["native_guid"] for a in r["anchors"]] == [1], "a fragment holding another dungeon's entry does not join")
    r = run(g, fragment_mesh(inside, 3), [native(1, 10, 2.5), native(2, 37.5, 7.5 + inside)])
    check(35 < r["anchors"][1]["entry_walk_yards"] < 80, "a joined fragment is walkable: the anchor in it has a short, finite walk from the entry")

    # Two dungeon rows on one map get their own natives and no native twice.
    pair = rect_mesh([(0, 0, 50, 5, 0), (0, 100, 50, 105, 0)], nm)
    rows = [dungeon("First", 1, (2.5, 2.5, 0.0)), dungeon("Second", 1, (2.5, 102.5, 0.0))]
    natives = [native(1, 20, 2.5), native(2, 33, 2.5), native(3, 20, 102.5), native(4, 40, 102.5), native(5, 45, 102.5)]
    sheets, report = g.survey_rows(rows, natives, [], {}, lambda m: pair, Factions, knobs)
    anchors = sheets["rift_anchors.csv"]
    first = {a["native_guid"] for a in anchors if a["dungeon"] == "First"}
    second = {a["native_guid"] for a in anchors if a["dungeon"] == "Second"}
    check(first == {1, 2} and second == {3, 4}, "each row on a shared map gets the natives of its own part (4 and 5 are one pack, anchored on 4)")
    check(not (first & second), "the two rows share no anchor")
    filtered = [r["spawn_guid"] for r in sheets["rift_native_filter.csv"]]
    check(sorted(filtered) == [1, 2, 3, 4, 5] and len(filtered) == len(set(filtered)), "every native is refused once, by one dungeon")
    check({r["dungeon"] for r in sheets["rift_native_filter.csv"] if r["spawn_guid"] in (1, 2)} == {"First"}, "the filter names the dungeon of the native")
    check([r["spawn_rows"] for r in report] == [5, 5], "the report counts the map's spawn rows")
    both = [dungeon("A", 1, (2.5, 2.5, 0.0)), dungeon("B", 1, (102.5, 2.5, 0.0))]
    sheets, _ = g.survey_rows(both, [native(1, 20, 2.5), native(2, 60, 2.5)], [], {}, lambda m: mesh, Factions, knobs)
    check({(r["spawn_guid"], r["dungeon"]) for r in sheets["rift_native_filter.csv"]} == {(1, "A"), (2, "A")} and not
          [a for a in sheets["rift_anchors.csv"] if a["dungeon"] == "B"], "a native two rows can reach belongs to the first")

    # Stock patrol paths.
    patrol = [native(1, 20, 2.5, path_id=77), native(2, 100, 2.5), native(3, 150, 2.5, path_id=78, type=g.TYPE_CRITTER)]
    paths = {77: [(1, 98.0, 2.5, 0.0), (2, 120.0, 2.5, 0.0), (3, 140.0, 2.5, 0.0)], 78: [(1, 150.0, 2.5, 0.0), (2, 160.0, 2.5, 0.0)]}
    r = run(g, mesh, patrol, paths=paths)
    check([(x["path_id"], x["points"], x["length_yards"]) for x in r["routes"]] == [(77, 3, 42.0)], "a kept native's path becomes a route; a critter's does not")
    check(r["routes"][0]["anchor"] == next(a["anchor"] for a in r["anchors"] if a["native_guid"] == 2),
          "the route ties to the anchor nearest its first point, not to the walker's own anchor")

    # The exit point: the farthest walkable ground, not water, not a cliff.
    far = corridor(nm, 100, extra=[(100, 0, 150, 5, 0, False)])
    r = run(g, far, [native(1, 20, 2.5)])
    check(r["exit"]["x"] > 95 and r["exit"]["x"] < 100, "the exit point is the corridor's far end, past which there is only water")
    check(around(r["exit"]["walk_yards"], r["exit"]["x"] - 2.5, 0.6), "its walk is measured from the entry")
    steep = [NM.Poly([(100, 0, 0), (105, 0, 0), (105, 5, 20), (100, 5, 20)], ground=True, slope=60)]
    base = corridor(nm, 100)
    glued = nm.Navmesh.from_polygons(base.polys + steep, base.portals + [(len(base.polys) - 1, len(base.polys), (100, 0, 0), (100, 5, 0))])
    check(run(g, glued, [native(1, 20, 2.5)])["exit"]["x"] < 100, "ground steeper than the limit is not an exit")

    # The report's estimate from the area defaults.
    areas = [dict(tag="S"), dict(tag="M"), dict(tag="L")]
    filled, bodies, elite, solos = g.estimate(areas, [], [], knobs)
    check(around(filled, 5.0, 1e-9) and around(bodies, 4 + 1.5 * 6 + 2.5 * (4 + 8 + 16) / 3, 1e-9), "an S, an M and an L area: 5 anchors and 36.3 bodies")
    check(around(elite, 5 * 0.9 * 0.25, 1e-9) and around(solos, 0.5, 1e-9), "elite packs and solos from the chance and the solo share")

    # The migration's text.
    sheets = {name: [] for name in g.SHEETS}
    sheets["rift_exit_points.csv"] = [dict(dungeon="Don't", x=1.5, y=-2, z=3, o=0, walk_yards="", source="survey")]
    sql = g.render(sheets)
    check("('Don''t', 1.5, -2, 3, 0, NULL, 'survey')" in sql, "text is quoted, numbers are not, a blank is NULL")
    for table, _ in g.TABLES.values():
        check(sql.index(f"DELETE FROM `{table}`") < (sql.index(f"INSERT INTO `{table}`") if f"INSERT INTO `{table}`" in sql else 10 ** 9),
              f"{table} is emptied before it is filled")
    check(sql.count("CREATE TABLE IF NOT EXISTS") == 5, "five tables")


def navmesh_checks(nm):
    # Walking distance over portals: exact on a straight corridor, and a corner costs what it should.
    mesh = rect_mesh([(0, 0, 100, 5, 0)], nm)
    p = mesh.locate(2.5, 2.5, 0, 3, 5)
    seen = mesh.distances(2.5, 2.5, 0, p)
    q = mesh.locate(92.5, 2.5, 0, 3, 5)
    check(around(mesh.reach(seen, q, 92.5, 2.5, 0), 90.0, 1e-6), "the walk along a corridor is its length")
    check(mesh.locate(2.5, 2.5, 30, 3, 5) is None and mesh.locate(2.5, 2.5, 30, 3, 5, far_z=50) == p,
          "a point 30 yards above the floor is found only with the far height, as the core does")
    check(mesh.locate(-2.0, 2.5, 0, 3, 5) == p and mesh.locate(-4.0, 2.5, 0, 3, 5) is None, "a point just off the edge snaps, past the snap distance it does not")
    two = rect_mesh([(0, 0, 50, 5, 0), (0, 0, 50, 5, 4)], nm)
    check(two.polys[two.locate(2.5, 2.5, 3.5, 3, 5)].cz == 4 and two.polys[two.locate(2.5, 2.5, 0.2, 3, 5)].cz == 0,
          "the polygon nearest in height is chosen on floors 4 yards apart")
    check(len(two.components()[0]) == 2, "stacked floors with no stair are two parts")
    # Border matching: overlapping edges join, others do not.
    def joined(edges):
        out = []
        nm.match_borders({(0, 0): edges}, out)
        return [(a, b) for a, b, _, _ in out]
    seg = lambda i, y0, y1, z=0.0: (i, (0.0, y0, z), (0.0, y1, z))
    check(joined([seg(0, 0, 10), seg(1, 5, 15)]) == [(0, 1)], "two border edges that overlap are joined")
    check(joined([seg(0, 0, 10), seg(1, 10, 20)]) == [], "two border edges that only touch are not")
    check(joined([seg(0, 0, 10), seg(1, 20, 30)]) == [], "two border edges apart are not")
    check(joined([seg(0, 0, 10), seg(1, 2, 2.01)]) == [], "a sliver of an edge inside another is not a portal")
    check(joined([seg(0, 0, 10), seg(1, 0, 10, nm.CLIMB + 1)]) == [], "border edges at different heights are not")
    check(joined([seg(0, 0, 10), seg(0, 5, 15)]) == [], "a polygon is not joined to itself")


# ---- the mutants ----------------------------------------------------------------------------------------------------------

SURVEY_MUTANTS = [
    ("a pack link of the exact distance is not one", "<= link", "< link"),
    ("natives on other floors join a pack", 'abs(a["z"] - b["z"]) < floor and', ""),
    ("a floor tolerance of one more", 'abs(a["z"] - b["z"]) < floor', 'abs(a["z"] - b["z"]) <= floor'),
    ("formations are ignored", "join(index[leader], index[member])", "pass"),
    ("the anchor is the farthest native", "return min(pack, key=", "return max(pack, key="),
    ("a tie goes to the higher guid", "n[\"guid\"]))\n\n\ndef make_areas", "-n[\"guid\"]))\n\n\ndef make_areas"),
    ("an L area needs one more native", 'natives >= knobs["tag_large_min_natives"]', 'natives > knobs["tag_large_min_natives"]'),
    ("an M area needs one more native", 'natives >= knobs["tag_medium_min_natives"]', 'natives > knobs["tag_medium_min_natives"]'),
    ("heroic-only natives are kept", 'if not native["spawn_mask"] & SPAWN_NORMAL:', "if False:"),
    ("other phases are kept", 'if not native["phase_mask"] & 1:', "if False:"),
    ("critters are kept", 'if native["type"] == TYPE_CRITTER:', "if False:"),
    ("triggers are kept", 'if native["flags_extra"] & EXTRA_TRIGGER:', "if False:"),
    ("unselectable natives are kept", 'if native["unit_flags"] & UNIT_NOT_SELECTABLE:', "if False:"),
    ("friendly natives are kept", "if not factions.hostile_to_players(native[\"faction\"]):", "if False:"),
    ("the entry's part of the map is not enforced", "if poly not in reached:", "if False:"),
    ("off-mesh natives are kept", "if poly is None:", "if False:"),
    ("the area cap is twice as wide", "if d <= cap:", "if d <= cap * 2:"),
    ("the area cap excludes its edge", "if d <= cap:", "if d < cap:"),
    ("areas use straight lines", "return mesh.reach(near[i], b[\"poly\"], n[\"x\"], n[\"y\"], n[\"z\"])",
     "return math.dist((a[\"native\"][\"x\"], a[\"native\"][\"y\"], a[\"native\"][\"z\"]), (n[\"x\"], n[\"y\"], n[\"z\"]))"),
    ("a native is claimed by two rows", 'and n["guid"] not in claimed', ""),
    ("a route ties to the farthest anchor", "near = [a for a in anchor_rows if abs(a[\"z\"] - sz) < floor] or anchor_rows\n        a = min(", "near = [a for a in anchor_rows if abs(a[\"z\"] - sz) < floor] or anchor_rows\n        a = max("),
    ("water is a valid exit", "if not poly.ground or poly.slope > knobs[\"max_slope_degrees\"]:", "if poly.slope > knobs[\"max_slope_degrees\"]:"),
    ("a cliff is a valid exit", "if not poly.ground or poly.slope > knobs[\"max_slope_degrees\"]:", "if not poly.ground:"),
    ("the exit is the nearest ground", "(d, -index) > best[0]", "(d, -index) < best[0]"),
    ("S areas fill two anchors", "filled += mean", "filled += mean + (a[\"tag\"] == \"S\")"),
    ("numbers are quoted in the migration", "return str(value)", "return quote(value)"),
    ("a blank is not NULL", 'if value == "" or value is None:', "if value is None:"),
    ("a table is not emptied first", 'f"DELETE FROM `{table}`{keep};"]', '""]'),
]
MESH_MUTANTS = [
    ("a fragment as large as the dungeon joins", "len(part) < len(own)", "len(part) <= len(own)"),
    ("another dungeon's entry may be swallowed", "skip = {cid[p] for p in avoid} | {cid[start]}", "skip = {cid[start]}"),
    ("the bridge distance is ignored", "if d <= bridge and", "if True and"),
    ("the second height try is dropped", "for height in (snap_z,) if far_z is None else (snap_z, far_z):", "for height in (snap_z,):"),
    ("the sideways snap is ignored", "if d > snap_xy:", "if False:"),
    ("the nearest height is not chosen", "key = (d > 0, dz if d == 0 else d + dz, index)", "key = (d > 0, index)"),
    ("a climb of any height joins border edges", "if abs(za - zb) > CLIMB:", "if False:"),
    ("border edges that touch join", "or min(hi, hi2) - max(lo, lo2) < OVERLAP_MIN", "or False"),
    ("a polygon joins itself across a border", "if ia == ib or", "if"),
]


def module_from(path, old, new, package_name):
    source = mutate(path.read_text(encoding="utf-8"), old, new)
    module = types.ModuleType(package_name)
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def test_rules_and_mutants():
    synthetic_checks(G, NM)
    navmesh_checks(NM)
    for what, old, new in SURVEY_MUTANTS:
        mutant = module_from(SURVEY_SOURCE, old, new, "generate_rift_survey_mutant")
        try:
            with contextlib.redirect_stdout(open("/dev/null", "w")):
                synthetic_checks(mutant, NM)
        except (AssertionError, ValueError, KeyError, IndexError, ZeroDivisionError):
            print("PASS mutant killed: " + what, flush=True)
            continue
        raise AssertionError("survey mutant survived: " + what)
    for what, old, new in MESH_MUTANTS:
        mutant = module_from(MESH_SOURCE, old, new, "rift_navmesh_mutant")
        try:
            with contextlib.redirect_stdout(open("/dev/null", "w")):
                synthetic_checks(G, mutant)
                navmesh_checks(mutant)
        except (AssertionError, ValueError, KeyError, IndexError, ZeroDivisionError):
            print("PASS mutant killed: " + what, flush=True)
            continue
        raise AssertionError("navmesh mutant survived: " + what)


# ---- the real data -------------------------------------------------------------------------------------------------------

def plan_measurement():
    """{map: (spawn rows, combatants, packs, S, M, L, estimate)} from Appendix B of the plan."""
    out = {}
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (\d+) \| .+? \| (\d+) \| (\d+) \| (\d+) \| (\d+) / (\d+) / (\d+) \| (\d+) \|$", line)
        if m:
            out[int(m.group(1))] = tuple(int(m.group(i)) for i in range(2, 9))
    return out


def test_data():
    mysql, defaults = fixture_db.mysql_and_defaults([])
    db = G.Database(mysql, defaults, "acore_world")
    factions = G.Factions(DATA / "dbc/FactionTemplate.dbc")
    knobs = G.read_knobs()
    # The faction rule against the Planner's hand list (monster-spawning.md 8: factions 35, 714, 1770, 534, 1667, 290, 1355).
    check(not any(factions.hostile_to_players(f) for f in (35, 714, 1770, 534, 1667, 290, 1355)), "the Planner's seven friendly factions are not hostile by the faction table")
    check(factions.hostile_to_players(14), "faction 14 (monster) is hostile to players")
    check(not factions.hostile(1, 1) and factions.hostile(14, 1), "a faction is not hostile to itself; the monster faction is hostile to Human")

    rows = G.dungeons()
    check(len(rows) == 30 and len({int(r["map_id"]) for r in rows}) == 29, "30 recommended rows on 29 maps")
    sheets, report = G.survey(db, DATA / "mmaps", factions, knobs, rows)
    plan = plan_measurement()
    check(len(plan) == 29, "Appendix B has 29 maps")
    by_map = collections.defaultdict(list)
    for r in report:
        by_map[int(r["map_id"])].append(r)
    for map_id, (spawn, combatants, packs, s, m, l, estimate) in sorted(plan.items()):
        mine = by_map[map_id]
        check(all(r["spawn_rows"] == spawn for r in mine), f"map {map_id}: the world database has the Planner's {spawn} spawn rows")
        got = sum(r["combatants_on_map"] for r in mine) if len(mine) == 1 else mine[0]["combatants_on_map"]
        check(0.5 * combatants <= got <= combatants, f"map {map_id}: {got} combatants against the Planner's {combatants} (heroic-only and other-phase rows are not counted)")
        if len(mine) == 1 and map_id != 429:
            anchors = mine[0]["anchors"]
            check(0.5 * packs <= anchors <= 1.05 * packs, f"map {map_id}: {anchors} anchors against the Planner's {packs} packs")
    today = sum(r["natives_today"] for r in report)
    bodies = sum(r["expected_bodies"] for r in report)
    check(1.7 <= bodies / today <= 2.4, f"the defaults give about twice today's monsters ({bodies} bodies for {today} natives)")
    check(all(1.4 <= r["bodies_vs_today"] <= 2.6 for r in report), "every dungeon's estimate is within 1.4 and 2.6 of its natives")
    # What is off the mesh is airborne: Utgarde Keep's 14 Proto-Drake Riders fly 100 to 250 yards above the floor.
    check(all(r["off_navmesh"] <= 0.15 * r["combatants_on_map"] for r in report) and sum(r["off_navmesh"] for r in report) == 27,
          "27 combatants in all are off the navmesh (flyers), no dungeon has more than a seventh of its own there")

    # The shared maps.
    anchors = sheets["rift_anchors.csv"]
    graveyard = {a["native_guid"] for a in anchors if a["dungeon"] == "Scarlet Monastery - Graveyard"}
    library = {a["native_guid"] for a in anchors if a["dungeon"] == "Scarlet Monastery - Library"}
    check(graveyard and library and not (graveyard & library), "Scarlet Monastery's two rows get anchors that share no native")
    check({r["dungeon"] for r in sheets["rift_native_filter.csv"] if r["spawn_guid"] in graveyard} == {"Scarlet Monastery - Graveyard"}, "the filter gives the Graveyard's natives to the Graveyard")
    dire = next(r for r in report if r["map_id"] == "429")
    check(dire["other_part"] > 400 and dire["natives_today"] < 0.5 * 787, "Dire Maul East leaves its other wings out")
    filtered = [(r["map_id"], r["spawn_guid"]) for r in sheets["rift_native_filter.csv"]]
    check(len(filtered) == len(set(filtered)) == today, "every native is refused once, and the filter is the natives kept")
    check({a["native_guid"] for a in anchors} <= {g for _, g in filtered}, "every anchor's native is refused")
    check(len(sheets["rift_exit_points.csv"]) == 30 and all(e["walk_yards"] > 100 for e in sheets["rift_exit_points.csv"]), "30 exit points, each far from the entry")
    check(all(a["entry_walk_yards"] < 1e6 for a in anchors), "every anchor can be walked to from the entry")

    # The navmesh's tile borders: every multi-tile dungeon map joins across them.
    for map_id in sorted(plan):
        mesh = NM.Navmesh.from_map(map_id, DATA / "mmaps")
        if mesh.stats["border_edges"]:
            check(mesh.stats["border_portals"] >= 0.4 * mesh.stats["border_edges"], f"map {map_id}: tile borders are joined ({mesh.stats['border_portals']} portals for {mesh.stats['border_edges']} edges)")

    # The committed sheets are the survey, unless the designer has edited them.
    committed = G.read_sheets()
    zones = G.open_zone_names()
    committed = {name: [r for r in rows if r["dungeon"] not in zones] for name, rows in committed.items()}   # the open zones' rows are Part S6's
    if G.has_alex(committed):
        print("SKIP the committed sheets hold rows of the designer's; they are the source now", flush=True)
    else:
        for name, columns in G.SHEETS.items():
            fresh = [{c: str(r[c]) for c in columns} for r in sheets[name]]
            check(fresh == [{c: r[c] for c in columns} for r in committed[name]], f"{name} is what the survey produces")
        want = list(csv.DictReader(open(G.REPORT, encoding="utf-8")))
        check([{c: str(r[c]) for c in G.REPORT_COLUMNS} for r in report] == [{c: r[c] for c in G.REPORT_COLUMNS} for r in want], "the report is what the survey produces")
    check((MODULE / "data/generated" / G.NAME).read_text(encoding="utf-8") == G.render(committed)
          == (MODULE / "data/sql/db-world/updates" / G.NAME).read_text(encoding="utf-8"), "the migration and its mirror are what the sheets render")
    # The designer's unset knob is reported, not filled in.
    check(G.read_knobs()["entry_clear_yards"] is None, "the entry clear distance is the designer's to set and is blank")


# ---- the replay and the export ----------------------------------------------------------------------------------------------

def test_mysql(port):
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root", "--batch",
               "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

    def sql(text, database=None):
        done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                              capture_output=True, encoding="utf-8")
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.rstrip("\n")

    text = (MODULE / "data/sql/db-world/updates" / G.NAME).read_text(encoding="utf-8")
    zones = G.open_zone_names()
    sheets = {name: [r for r in rows if r["dungeon"] not in zones] for name, rows in G.read_sheets().items()}
    sql("CREATE DATABASE rift_survey CHARACTER SET utf8mb4;")
    sql(text, "rift_survey")
    sql(text, "rift_survey")
    for name in G.SHEETS:
        table = G.TABLES[name][0]
        check(sql(f"SELECT COUNT(*) FROM `{table}`", "rift_survey") == str(len(sheets[name])), f"twice applied: {table} reads back its {len(sheets[name])} rows")
    check(sql("SELECT COUNT(*) FROM dc_rift_route r LEFT JOIN dc_rift_anchor a ON a.dungeon=r.dungeon AND a.anchor=r.anchor WHERE a.anchor IS NULL", "rift_survey") == "0",
          "every route names an anchor that exists")
    check(sql("SELECT COUNT(*) FROM dc_rift_anchor a LEFT JOIN dc_rift_area r ON r.dungeon=a.dungeon AND r.area=a.area WHERE r.area IS NULL", "rift_survey") == "0",
          "every anchor is in an area that exists")
    check(sql("SELECT COUNT(*) FROM dc_rift_anchor", "rift_survey") == sql("SELECT COUNT(DISTINCT dungeon, anchor) FROM dc_rift_anchor", "rift_survey"), "anchor numbers are unique inside a dungeon")
    check(sql("SELECT COUNT(DISTINCT dungeon) FROM dc_rift_exit_point", "rift_survey") == "30", "one exit point per dungeon")
    # The cut DELETE: replaying a migration that keeps its old rows fails on the primary key.
    sql("CREATE DATABASE rift_mutant CHARACTER SET utf8mb4;")
    mutant = re.sub(r"^DELETE FROM `dc_rift_anchor`[^;\n]*;$", "", text, count=1, flags=re.M)
    check(mutant != text, "the mutant removed the anchor DELETE")
    sql(mutant, "rift_mutant")
    try:
        sql(mutant, "rift_mutant")
    except RuntimeError:
        check(True, "mutant killed: without its DELETE the migration does not replay")
    else:
        raise AssertionError("a migration that keeps its old rows replayed")

    # --export: edits made in the dev tables come home.
    with tempfile.TemporaryDirectory(dir=str(fixture_db.fixture_dir() / "disposable")) as tmp:
        defaults = pathlib.Path(tmp) / "client.cnf"
        defaults.write_text(f"[client]\nhost=127.0.0.1\nport={port}\nuser=root\n", encoding="utf-8")
        folder = pathlib.Path(tmp) / "d3"
        folder.mkdir()
        db = G.Database(MYSQL, defaults, "rift_survey")
        first = sheets["rift_anchors.csv"][0]
        sql(f"UPDATE dc_rift_anchor SET x=x+1, source='alex' WHERE dungeon={G.quote(first['dungeon'])} AND anchor={first['anchor']};"
            f"INSERT INTO dc_rift_anchor VALUES ({G.quote(first['dungeon'])}, 9999, {first['area']}, 1.5, 2.5, 3.5, 0, 1, NULL, NULL, NULL, 'alex');"
            f"DELETE FROM dc_rift_route WHERE dungeon={G.quote(sheets['rift_routes.csv'][0]['dungeon'])} AND path_id={sheets['rift_routes.csv'][0]['path_id']};"
            "UPDATE dc_rift_area SET tag='L', source='alex' WHERE dungeon=" + G.quote(first['dungeon']) + f" AND area={first['area']};", "rift_survey")
        G.export(db, folder)
        got = G.read_sheets(folder, missing_ok=True)
        check(len(got["rift_anchors.csv"]) == len(sheets["rift_anchors.csv"]) + 1, "the added anchor is in the exported sheet")
        moved = next(r for r in got["rift_anchors.csv"] if r["dungeon"] == first["dungeon"] and r["anchor"] == first["anchor"])
        check(float(moved["x"]) == round(float(first["x"]) + 1, 4) and moved["source"] == "alex", "the moved anchor is exported with its new place and source alex")
        added = next(r for r in got["rift_anchors.csv"] if r["anchor"] == "9999")
        check((added["x"], added["native_guid"], added["entry_walk_yards"], added["source"]) == ("1.5", "", "", "alex"), "an anchor of the designer's has no native and no walk; blanks come back blank")
        check(len(got["rift_routes.csv"]) == len(sheets["rift_routes.csv"]) - 1, "the removed route is gone from the exported sheet")
        check(next(r for r in got["rift_areas.csv"] if r["dungeon"] == first["dungeon"] and r["area"] == first["area"])["tag"] == "L", "the re-tagged area is exported")
        check(len(got["rift_exit_points.csv"]) == 30, "the exit points come home too")
        check(G.has_alex(got), "the exported sheets show rows of the designer's")
        check(not (folder / "rift_native_filter.csv").exists(), "the native filter is the survey's and is not exported")
        # --survey refuses over his rows, and --force does not need the database to get past the refusal.
        saved = (G.D3, sys.argv)
        try:
            G.D3 = folder
            sys.argv = ["generate/rifts/generate_rift_survey.py", "--survey", "--mysql", str(MYSQL), "--defaults-file", str(defaults)]
            try:
                G.main()
            except SystemExit as stop:
                check(stop.code == 2, "--survey refuses to run over rows of the designer's")
            else:
                raise AssertionError("--survey ran over rows of the designer's")
        finally:
            G.D3, sys.argv = saved
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_rules_and_mutants()
    test_data()
    isolated(test_mysql)

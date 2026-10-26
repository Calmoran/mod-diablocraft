"""diablocraft-976b: the hub flip moves everything the old hub held to the Sanctum of Torment, or refuses.

    python3 mod-diablocraft/scripts/tests/world/test_hub_sanctum_move.py        # needs the fixture mysqld (fixture_mysql.sh start)

generate_hub_sanctum_move.py turns the hub's data files into one migration. It REFUSES while a position is blank (World
places nothing on its own judgement: the designer's .gps readings, card q-1003-39, are applied by diablocraft-ftoz), so the
live files, which have no readings yet, are refused here, naming every blank cell. What the migration does is proven on
temp copies of those files whose cells are filled with SYNTHETIC readings (they stand in for the designer's, are distinct for
every spot so a swap shows, and are never shipped), applied to a disposable database on the fixture mysqld that holds
the Scryer-era state (the old hub's rows as the frozen migrations left them, seeded from tests/scryer_hub). Pinned:

  * every managed row (the artisans, the Jeweler, Kadala, obelisk, tome and stack, the scenery, the Tester's Coffer) stands ONCE on map 750
    area 4273 at its reading, in phase 1, keeps its other fields, and leaves nothing behind on the old hub's map (the Sanctum is one shared
    phase, diablocraft-k4ce: the tier 2-10 copies of the old model are taken away by generate_sanctum_one_copy.py, which the tests that look at the
    end state apply after the move);
  * the area registry holds each managed source once, under the hub's key, and no copy; the old key is gone;
  * the named points, the hub row and every start row at the old hub (class 1, and the Wizard rows of world_0028) follow
    the spawn; a stock start row elsewhere does not;
  * the old hub's rules are closed and the Sanctum's open; the graveyard exists and the core's choice for area 4273 on
    map 750 resolves to it (before the flip it resolves to the Storm Peaks graveyard 1384 on map 571);
  * applying twice changes nothing, a database with none of the old rows gets every row, and a row that is not ours
    (a foreign guid, a foreign registry owner, a missing template) stops the migration before it writes.

Limits: the arena floor is not consulted (the readings' heights are ftoz's check); the core's graveyard algorithm is
modelled over the rows and pinned against its source text, never run.
"""
import csv
import json
import math
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_sanctum_move as move  # noqa: E402
import generate_hub_sanctum_seal as seal  # noqa: E402
import generate_sanctum_one_copy as one  # noqa: E402
import tunable_values  # noqa: E402
from generate_area_copies import insert  # noqa: E402
from scryer_hub import LEGACY  # noqa: E402
from test_hub_sanctum_seal import Scratch  # noqa: E402

ROOT = HERE.parents[1]
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch"
CORE = ROOT / "azerothcore-wotlk/src/server"
MAP, AREA, OLD_MAP, OLD_AREA, TIERS = 750, 4273, 530, 3703, 10
TABLES = ("dc_world_areas", "dc_world_hub_point", "dc_world_hub", "playercreateinfo", "game_graveyard", "graveyard_zone",
          "creature", "gameobject", "creature_template", "gameobject_template", "dc_area_source", "dc_area_spawn", "dc_tier_phase",
          "gameobject_addon", "gameobject_template_addon", "gameobject_template_locale",   # world_0034 touches these
          "creature_addon", "creature_movement_override", "creature_multispawn", "creature_sparring", "vehicle_accessory",
          "creature_formations", "linked_respawn")   # the one-copy migration deletes from these
COFFER_ENTRY, TOME, JEWELER, SMITH, GRAVEYARD, KADALA, PILLAR = 910018, 910016, 910004, 910000, 910000, 910005, 910010
STRAY = 8000998   # a creature of the dummy's entry that no sheet manages
DUMMY, DUMMIES = 31146, (8000108, 8000109, 8000110)   # the Heroic Training Dummy and its three hand-placed creature guids of the old hub


def ignore(sql):
    return sql.replace("INSERT INTO", "INSERT IGNORE INTO", 1)


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def edit(path, change):
    rows = read(path)
    change(rows)
    write(path, rows)


def edit_placement(path, entry, **cells):
    def change(rows):
        for row in rows:
            placement = json.loads(row["placement"])
            if placement["id"] == entry:
                placement.update(cells)
                row["placement"] = json.dumps(placement, separators=(",", ":"))
    edit(path, change)


def spot(index):
    """Synthetic reading number `index`: its own x, y, z and facing, so that two spots swapped shows."""
    return dict(x=100.0 + index * 3.25, y=-200.0 - index * 2.5, z=300.0 + index * 1.5, o=(0.2 + index * 0.25) % 6.2)   # wraps inside the circle for index > 24


class Data:
    """Temp copies of the live hub CSVs with every position cell filled by a synthetic reading."""

    def __init__(self, folder):
        self.folder = Path(folder)
        assert SCRATCH in self.folder.parents, "test data must live under the scratch folder"
        self.points, self.placements = self.folder / "world_hub_points.csv", self.folder / "world_hub_placements.csv"
        self.coffer, self.areas = self.folder / "world_tester_coffer.csv", self.folder / "world_areas.csv"
        shutil.copy(move.AREAS, self.areas)
        self.readings, index = {}, iter(range(1, 100))
        rows = read(move.POINTS)
        for row in rows:
            self.readings[row["name"]] = spot(next(index))
            row.update({key: repr(value) for key, value in self.readings[row["name"]].items()})
        write(self.points, rows)
        rows = read(move.PLACEMENTS)
        for row in rows:
            placement, reading = json.loads(row["placement"]), spot(next(index))
            self.readings[(row["kind"], placement["id"], int(row["source_guid"]))] = reading
            placement.update(position_x=reading["x"], position_y=reading["y"], position_z=reading["z"], orientation=reading["o"])
            row["placement"] = json.dumps(placement, separators=(",", ":"))
        write(self.placements, rows)
        rows = read(move.COFFER)
        self.readings["coffer"] = spot(next(index))
        rows[0].update({key: repr(value) for key, value in self.readings["coffer"].items()})
        write(self.coffer, rows)

    def generate(self):
        return move.generate(self.points, self.placements, self.coffer, self.areas)

    def load(self):
        return move.load(self.points, self.placements, self.coffer, self.areas)

    def services(self):
        """(kind, entry, guid, reading) for every managed spawn, read from the input files, not from the generator."""
        found = []
        for row in read(self.placements):
            placement = json.loads(row["placement"])
            found.append((row["kind"], placement["id"], int(row["source_guid"]), self.readings[(row["kind"], placement["id"], int(row["source_guid"]))]))
        found.append(("c", COFFER_ENTRY, int(read(self.coffer)[0]["source_guid"]), self.readings["coffer"]))
        return found


def retired_copies():
    """{(kind, source_guid): {tier: copy guid}} of the old model, from the retired-copies sheet the one-copy migration reads."""
    found = {}
    for row in read(one.RETIRED):
        found.setdefault((row["kind"], int(row["source_guid"])), {})[int(row["tier"])] = int(row["copy_guid"])
    return found


def seed(db, old_rows=True):
    """The Scryer-era state on a scratch database: shared rows copied from the fixture database, the old hub's own seeded from
    tests/scryer_hub (positions of the old hub, map 530 area 3703), the way the frozen migrations and the designer's hand work left them."""
    sql = ["INSERT INTO creature_template SELECT * FROM acore_world.creature_template WHERE entry IN (910000,910001,910002,910003,910004,910018,31146);",
           # Kadala's template is written by kadala_0001, which the fixture (a dump of live) does not have: a copy of the Blacksmith's under her entry
           f"CREATE TEMPORARY TABLE kadala_template LIKE creature_template; INSERT INTO kadala_template SELECT * FROM creature_template WHERE entry={SMITH}; "
           f"UPDATE kadala_template SET entry={KADALA}; INSERT INTO creature_template SELECT * FROM kadala_template;",
           "INSERT INTO gameobject_template SELECT * FROM acore_world.gameobject_template WHERE entry IN (910011,910016,1799,180324,2695,180338,180425,180340,182005);",
           # world_0036's templates (the adder's) are NOT seeded on purpose: a fresh database has none of them when this migration runs

           "INSERT INTO dc_tier_phase SELECT * FROM acore_world.dc_tier_phase;",
           "INSERT INTO game_graveyard SELECT * FROM acore_world.game_graveyard WHERE ID IN (994,1384);",
           "INSERT INTO graveyard_zone SELECT * FROM acore_world.graveyard_zone WHERE ID IN (994,1384);"]
    for rule in read(LEGACY / "world_areas.csv"):
        sql.append(insert("dc_world_areas", dict(map_id=int(rule["map_id"]), area_id=int(rule["area_id"]), phase_scope=rule["phase_scope"],
                                                  status=rule["status"], note=rule["note"])))
    old = {r["name"]: r for r in read(LEGACY / "world_hub_points.csv")}
    for name, row in old.items():
        xyz = {axis: tunable_values.value("ui", f"hub_{name}_{axis}_yards") for axis in "xyz"}
        sql.append(insert("dc_world_hub_point", dict(name=name, map_id=OLD_MAP, area_id=OLD_AREA, **xyz, o=float(row["o"]))))
        if name == "spawn":
            sql.append(insert("dc_world_hub", dict(id=1, map_id=OLD_MAP, area_id=OLD_AREA, **xyz, o=float(row["o"]))))
            start = dict(map=OLD_MAP, zone=OLD_AREA, position_x=xyz["x"], position_y=xyz["y"], position_z=xyz["z"], orientation=float(row["o"]))
    for race, klass in ((1, 1), (2, 1), (10, 1), (2, 8), (3, 8), (4, 8), (6, 8)):  # class 8: the Wizard rows world_0028 put at the hub
        sql.append(insert("playercreateinfo", dict(race=race, **{"class": klass}, **start)))
    for race, klass, where in ((1, 4, dict(map=0, zone=12, position_x=-8949.95, position_y=-132.493, position_z=83.5312, orientation=0.0)),
                               (10, 2, dict(map=OLD_MAP, zone=3431, position_x=10349.6, position_y=-6357.29, position_z=33.4026, orientation=5.31605)),
                               (3, 2, dict(map=1, zone=OLD_AREA, position_x=1.0, position_y=2.0, position_z=3.0, orientation=0.5))):
        sql.append(insert("playercreateinfo", dict(race=race, **{"class": klass}, **where)))
    # stock start rows (a stock zone; the old hub's map with another zone; another map with only the old hub's zone number): none is the hub's
    if old_rows:
        old_services = {(r["kind"], json.loads(r["placement"])["id"]): r for r in read(LEGACY / "world_hub_placements.csv")}
        for source in read(move.PLACEMENTS):
            kind, entry = source["kind"], json.loads(source["placement"])["id"]
            if entry in move.SCENERY or entry == KADALA:   # the designer's scenery and Kadala are not on the old hub: the migration inserts them
                continue
            table, tier_one_only = move.TABLES[kind], entry in (JEWELER, TOME, DUMMY)
            legacy = old_services.get((kind, entry))
            row = json.loads((legacy or source)["placement"])
            if not legacy:  # the Jeweler and the dummies: live-only, never exported; the Blacksmith's old spot, shifted
                row.update(position_x=-2100.0, position_y=5530.0, position_z=51.0, orientation=3.2)
            guids = {1: int(source["source_guid"]), **retired_copies().get((kind, int(source["source_guid"])), {})}
            for tier, guid in guids.items():
                if tier > 1 and tier_one_only:
                    continue
                zone = 0 if tier_one_only else OLD_AREA
                sql.append(insert(table, dict(row, guid=guid, phaseMask=tier, map=OLD_MAP, zoneId=zone, areaId=zone)))
            registered = not tier_one_only or entry in (JEWELER, DUMMY)  # the Jeweler's and the dummies' stale scan rows, as in the live-shaped fixture
            if registered:
                sql.append(insert("dc_area_source", dict(map_id=OLD_MAP, area_id=OLD_AREA, kind=kind, source_guid=guids[1], entry=entry, source_phase=1,
                                                         position_x=row["position_x"], position_y=row["position_y"], position_z=row["position_z"],
                                                         orientation=row["orientation"])))
            if not tier_one_only:
                sql += [insert("dc_area_spawn", dict(map_id=OLD_MAP, area_id=OLD_AREA, kind=kind, source_guid=guids[1], tier=t, spawn_guid=g))
                        for t, g in guids.items() if t > 1]
        coffer = read(LEGACY / "world_tester_coffer.csv")[0]
        first = int(read(move.COFFER)[0]["source_guid"])
        for tier in range(1, TIERS + 1):
            sql.append(insert("creature", dict(guid=first + tier - 1, id=COFFER_ENTRY, map=OLD_MAP, zoneId=OLD_AREA, areaId=OLD_AREA, spawnMask=1, phaseMask=tier,
                                               position_x=float(coffer["x"]), position_y=float(coffer["y"]), position_z=float(coffer["z"]),
                                               orientation=float(coffer["o"]), spawntimesecs=300)))
            if tier > 1:
                sql.append(insert("dc_area_spawn", dict(map_id=OLD_MAP, area_id=OLD_AREA, kind="c", source_guid=first, tier=tier, spawn_guid=first + tier - 1)))
        sql.append(insert("dc_area_source", dict(map_id=OLD_MAP, area_id=OLD_AREA, kind="c", source_guid=first, entry=COFFER_ENTRY, source_phase=1,
                                                 position_x=float(coffer["x"]), position_y=float(coffer["y"]), position_z=float(coffer["z"]), orientation=float(coffer["o"]))))
        # a stale copy row of the Blacksmith under the old key (an old scan's leftover, tier 11): the registry must not keep it
        sql.append(insert("dc_area_spawn", dict(map_id=OLD_MAP, area_id=OLD_AREA, kind="c", source_guid=8000068, tier=11, spawn_guid=8000999)))
        # what the move must leave alone: the designer's hand edits on managed rows, a stray creature of the dummy's entry (the move goes by
        # guid, not by entry), a stale scan row of an unmanaged object
        sql += ["UPDATE creature SET ScriptName='hand-edit-source' WHERE guid=8000068;",
                "UPDATE creature SET curhealth=4321 WHERE guid=8000072;",
                "INSERT INTO creature (guid,id,map,zoneId,areaId,spawnMask,phaseMask,position_x,position_y,position_z,orientation,spawntimesecs) "
                f"VALUES ({STRAY},31146,{OLD_MAP},0,0,1,1,-2085.44,5551.9,51.2674,3.46594,300);",
                insert("dc_area_source", dict(map_id=OLD_MAP, area_id=OLD_AREA, kind="g", source_guid=8001488, entry=191128, source_phase=1,
                                              position_x=-2058.6, position_y=5495.48, position_z=54.5399, orientation=5.8716))]
    db.query("\n".join(sql))


def snapshot(db):
    return [sorted(db.query(f"SELECT * FROM `{table}`").splitlines()) for table in TABLES]


def closest_graveyard(db, map_id, area_id, x, y, z):
    """The core's GetClosestGraveyard for a neutral player at that place, over the scratch rows: the graveyards linked to the
    area, the nearest one on the player's own map first; otherwise whichever other one the core would settle for."""
    linked = [line.split("\t") for line in db.query(
        f"SELECT g.ID,g.Map,g.x,g.y,g.z FROM graveyard_zone z JOIN game_graveyard g ON g.ID=z.ID WHERE z.GhostZone={area_id} AND z.Faction=0 ORDER BY g.ID").splitlines()]
    near = [((float(gx) - x) ** 2 + (float(gy) - y) ** 2 + (float(gz) - z) ** 2, int(ident)) for ident, gmap, gx, gy, gz in linked if int(gmap) == map_id]
    if near:
        return min(near)[1]
    return int(linked[-1][0]) if linked else None  # the entrance-map ordering of the core is not modelled: no map 750 row here


class Refusals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.folder = tempfile.mkdtemp(prefix="move-refuse-", dir=SCRATCH)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def data(self, name):
        folder = Path(self.folder) / re.sub(r"\W+", "_", name)
        folder.mkdir(exist_ok=True)
        return Data(folder)

    def test_the_live_files_are_refused_naming_every_blank_cell_or_generate(self):
        # State-independent: before diablocraft-ftoz fills the readings the files are refused, after it they generate.
        blanks = []
        for row in read(move.POINTS):
            if any(not row[key].strip() for key in "xyzo"):
                blanks.append("world_hub_points.csv " + row["name"])
        for row in read(move.PLACEMENTS):
            placement = json.loads(row["placement"])
            if any(placement.get(key) is None for key in move.PLACE):
                blanks.append(f"world_hub_placements.csv {row['kind']}:{placement['id']} (guid {row['source_guid']})")
        if any(not read(move.COFFER)[0][key].strip() for key in "xyzo"):
            blanks.append("world_tester_coffer.csv")
        if blanks:
            with self.assertRaises(ValueError) as caught:
                move.generate()
            for label in blanks:
                self.assertIn(label, str(caught.exception))
            self.assertIn("q-1003-39", str(caught.exception))
        else:
            self.assertIn("REPLACE INTO dc_world_hub_point VALUES('spawn',750,4273,", move.generate())

    def test_one_blank_cell_is_refused_and_named(self):
        cases = {
            "world_hub_points.csv spawn": lambda d: edit(d.points, lambda rows: rows[0].update(x="")),
            "world_hub_points.csv graveyard": lambda d: edit(d.points, lambda rows: [r.update(o=" ") for r in rows if r["name"] == "graveyard"]),
            "world_hub_points.csv rift_exit": lambda d: edit(d.points, lambda rows: [r.update(z="") for r in rows if r["name"] == "rift_exit"]),
            "world_hub_placements.csv c:910004": lambda d: edit_placement(d.placements, 910004, orientation=None),
            "world_hub_placements.csv g:910016": lambda d: edit_placement(d.placements, 910016, position_z=None),
            "world_tester_coffer.csv": lambda d: edit(d.coffer, lambda rows: rows[0].update(y="")),
        }
        for label, blank in cases.items():
            with self.subTest(label):
                data = self.data(label)
                blank(data)
                with self.assertRaises(ValueError) as caught:
                    data.generate()
                self.assertIn(label, str(caught.exception))
                self.assertIn("pending", str(caught.exception))

    def test_every_blank_cell_is_named_not_only_the_first(self):
        data = self.data("several")
        edit(data.points, lambda rows: rows[1].update(x=""))
        edit_placement(data.placements, 910000, position_x=None)
        edit(data.coffer, lambda rows: rows[0].update(z=""))
        with self.assertRaises(ValueError) as caught:
            data.generate()
        for label in ("world_hub_points.csv town_portal", "c:910000", "world_tester_coffer.csv"):
            self.assertIn(label, str(caught.exception))

    def test_data_that_is_not_the_hub_is_refused(self):
        def points(**cells):
            return lambda d: edit(d.points, lambda rows: rows[0].update(**cells))
        cases = {
            "the spawn on another map": points(map_id="530"),
            "the spawn in another area": points(area_id="3703"),
            "a point on a number that is not a number": points(x="abc"),
            "a facing outside the circle": points(o="7"),
            "a facing that is nan": points(o="nan"),
            "a point at infinity": points(x="inf"),
            "the graveyard on the old hub's map": lambda d: edit(d.points, lambda rows: [r.update(map_id="530") for r in rows if r["name"] == "graveyard"]),
            "a missing point": lambda d: edit(d.points, lambda rows: rows.pop()),
            "an extra point": lambda d: edit(d.points, lambda rows: rows.append(dict(rows[0], name="fountain"))),
            "a placement on the old hub's map": lambda d: edit_placement(d.placements, 910001, map=530),
            "a placement in the old hub's area": lambda d: edit_placement(d.placements, 910001, areaId=3703, zoneId=3703),
            "a placement of an entry that is no hub service": lambda d: edit_placement(d.placements, 910001, id=910050),
            "a placement outside tier 1": lambda d: edit_placement(d.placements, 910001, phaseMask=2),
            "a placement whose zone is the old hub's": lambda d: edit_placement(d.placements, 910001, zoneId=3703),
            "a placement whose area is the old hub's": lambda d: edit_placement(d.placements, 910001, areaId=3703),
            "a sheet that still has copy guids": lambda d: edit(d.placements, lambda rows: [r.update(copy_guids="{}") for r in rows]),
            "a coffer with no placement source": lambda d: edit(d.coffer, lambda rows: rows[0].update(placement_source="")),
            "an area rule with a phase scope that is none of them": lambda d: edit(d.areas, lambda rows: rows[0].update(phase_scope="some")),
            "a placement with a facing outside the circle": lambda d: edit_placement(d.placements, 910001, orientation=-1.0),
            "a placement with a position that is not a number": lambda d: edit_placement(d.placements, 910001, position_y="abc"),
            "a placement with no source note": lambda d: edit(d.placements, lambda rows: rows[0].update(source="")),
            "a source guid that is not the row's": lambda d: edit(d.placements, lambda rows: rows[0].update(source_guid="8000999")),
            "two placements on one guid": lambda d: edit(d.placements, lambda rows: rows[1].update(
                source_guid=rows[0]["source_guid"],
                placement=json.dumps(dict(json.loads(rows[1]["placement"]), guid=int(rows[0]["source_guid"])), separators=(",", ":")))),
            "a service twice": lambda d: edit(d.placements, lambda rows: rows.append(rows[0])),
            "a service missing": lambda d: edit(d.placements, lambda rows: rows.pop()),
            "a dummy missing": lambda d: edit(d.placements, lambda rows: rows.remove(next(r for r in rows if json.loads(r["placement"])["id"] == DUMMY))),
            "a fourth dummy": lambda d: edit(d.placements, lambda rows: rows.append(dict(
                next(r for r in rows if json.loads(r["placement"])["id"] == DUMMY), source_guid="8000900",
                placement=json.dumps(dict(json.loads(next(r for r in rows if json.loads(r["placement"])["id"] == DUMMY)["placement"]), guid=8000900),
                                     separators=(",", ":"))))),
            "the coffer in the old hub": lambda d: edit(d.coffer, lambda rows: rows[0].update(map_id="530", area_id="3703")),
            "the coffer on a placement's guid": lambda d: edit(d.coffer, lambda rows: rows[0].update(source_guid="8000068")),
            "a coffer with no guid source": lambda d: edit(d.coffer, lambda rows: rows[0].update(guid_source="")),
            "a hub area that is not open": lambda d: edit(d.areas, lambda rows: [r.update(status="closed") for r in rows if r["area_id"] == "4273"]),
            "an area rule twice": lambda d: edit(d.areas, lambda rows: rows.append(dict(rows[0]))),
            "an area rule with a status that is neither": lambda d: edit(d.areas, lambda rows: rows[0].update(status="ajar")),
            "the coffer in another area of the hub's map": lambda d: edit(d.coffer, lambda rows: rows[0].update(area_id="9999")),
            "the coffer on another map in the hub's area": lambda d: edit(d.coffer, lambda rows: rows[0].update(map_id="751")),
            "a coffer file with an extra column": lambda d: edit(d.coffer, lambda rows: rows[0].update(extra="x")),
            "two coffers": lambda d: edit(d.coffer, lambda rows: rows.append(dict(rows[0]))),
            "a coffer on a guid past the last": lambda d: edit(d.coffer, lambda rows: rows[0].update(source_guid="4294967296")),
            "a Blacksmith that never respawns": lambda d: edit_placement(d.placements, 910000, spawntimesecs=0),
            "a service again on other guids": lambda d: edit(d.placements, lambda rows: rows.append(dict(
                rows[0], source_guid="8000900",
                placement=json.dumps(dict(json.loads(rows[0]["placement"]), guid=8000900), separators=(",", ":"))))),
            "an obelisk rotation that disagrees with its facing": lambda d: edit_placement(d.placements, 910011, rotation2=0.0, rotation3=1.0),
        }
        for label, damage in cases.items():
            with self.subTest(label):
                data = self.data(label)
                damage(data)
                with self.assertRaises(ValueError):
                    data.generate()

    def test_the_door_must_stand_where_the_hub_does(self):
        # Everything but the door moves to another open area, or to another map, so only the door rule can refuse it: the door
        # sheet still agrees with the live hub file, which is where seal.door_row looks, and the placements and the coffer agree
        # with the moved hub.
        for map_id, area_id in ((750, 9999), (751, 4273)):
            with self.subTest(f"the hub at {map_id}/{area_id}"):
                data = self.data(f"hub at {map_id} {area_id}")
                edit(data.points, lambda rows: [r.update(map_id=str(map_id), area_id=str(area_id)) for r in rows])
                edit(data.areas, lambda rows: rows.append(dict(rows[0], map_id=str(map_id), area_id=str(area_id), status="open",
                                                               phase_scope="all", note="elsewhere")))
                edit(data.coffer, lambda rows: rows[0].update(map_id=str(map_id), area_id=str(area_id)))
                edit(data.placements, lambda rows: [row.update(placement=json.dumps(
                    dict(json.loads(row["placement"]), map=map_id, areaId=area_id, zoneId=area_id), separators=(",", ":"))) for row in rows])
                with self.assertRaises(ValueError) as caught:
                    data.generate()
                self.assertIn("door must stand in the hub's map and area", str(caught.exception))

    def test_a_rotation_that_agrees_with_its_facing_is_accepted(self):
        data = self.data("agreeing rotation")
        o = data.readings[("g", 910011, 8001469)]["o"]
        edit_placement(data.placements, 910011, rotation2=math.sin(o / 2), rotation3=math.cos(o / 2))
        self.assertIn("rotation2", data.generate())

    def test_the_migration_name_is_the_next_free_world_number_or_its_own(self):
        with tempfile.TemporaryDirectory(prefix="move-name-", dir=SCRATCH) as folder:
            updates = Path(folder)
            for name in ("world_0030_a.sql", "world_0031_b.sql", "0001_dc_x.sql"):
                (updates / name).write_text("", encoding="utf-8")
            self.assertEqual(move.migration_name(updates), "world_0032_sanctum_hub_move.sql")
            (updates / "world_0032_sanctum_hub_move.sql").write_text("", encoding="utf-8")
            (updates / "world_0033_c.sql").write_text("", encoding="utf-8")
            self.assertEqual(move.migration_name(updates), "world_0032_sanctum_hub_move.sql", "a rerun rewrites its own file")


class FlipBase(unittest.TestCase):
    """The move's generated SQL and the helpers its tests share; no test of its own."""

    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.folder = tempfile.mkdtemp(prefix="move-flip-", dir=SCRATCH)
        cls.data = Data(cls.folder)
        cls.sql = cls.data.generate()
        cls.copies = one.generate()   # the migration that follows the move and takes the old model's tier copies away
        cls.services = cls.data.services()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def apply(self):
        """The move, then the one-copy migration: the end state every test below looks at."""
        self.db.query(self.sql)
        self.db.query(self.copies)

    def lines(self, sql):
        return [line.split("\t") for line in self.db.query(sql).splitlines()]

    def near(self, found, wanted, message=""):
        self.assertEqual(len(found), len(wanted), message)
        for got, want in zip(found, wanted):
            self.assertLess(abs(float(got) - float(want)), 1e-3, f"{message}: {got} != {want}")


class FlipApplied(FlipBase):
    """The tests that only read the end state of the move: it is applied once to one seeded database, and tearDownClass fails if a
    test changed it. A test that writes, or reads the state before the move, is in Flip, which seeds a database for each."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db = Scratch(TABLES)
        seed(cls.db, True)
        cls.db.query(cls.sql)
        cls.db.query(cls.copies)
        cls.applied = snapshot(cls.db)

    @classmethod
    def tearDownClass(cls):
        try:
            unchanged = snapshot(cls.db) == cls.applied
        finally:
            cls.db.drop()
            super().tearDownClass()
        assert unchanged, "a test changed the shared, applied database"

    def test_every_managed_spawn_stands_in_the_sanctum_at_its_reading(self):
        for kind, entry, guid, reading in self.services:
            table = move.TABLES[kind]
            rotation = ",rotation0,rotation1,rotation2,rotation3" if kind == "g" else ""
            rows = self.lines(f"SELECT guid,id,map,zoneId,areaId,phaseMask,spawnMask,position_x,position_y,position_z,orientation{rotation} "
                              f"FROM {table} WHERE guid={guid}")
            self.assertEqual(len(rows), 1, f"{kind}:{entry} stands once")
            row = rows[0]
            self.assertEqual([int(v) for v in row[:7]], [guid, entry, MAP, AREA, AREA, 1, 1], f"{kind}:{entry}")
            self.near(row[7:11], [reading["x"], reading["y"], reading["z"], reading["o"]], f"{kind}:{entry} position")   # the Tome too: no float
            if kind == "g" and entry in move.SCENERY:   # the designer's quaternion as his editor stored it, not derived from the facing
                kept = next(json.loads(r["placement"]) for r in read(move.PLACEMENTS) if int(r["source_guid"]) == guid)
                self.near(row[11:], [kept[f"rotation{i}"] for i in range(4)], f"{kind}:{entry} rotation kept")
            elif kind == "g":
                self.near(row[11:], [0, 0, math.sin(reading["o"] / 2), math.cos(reading["o"] / 2)], f"{kind}:{entry} rotation")
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM creature WHERE map={OLD_MAP} AND id IN (910000,910001,910002,910003,910004,910018)"), "0")
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM gameobject WHERE map={OLD_MAP} AND id IN (910011,910016)"), "0")
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM creature WHERE id IN (910000,910001,910002,910003,910004,910018)"), "6")
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM gameobject WHERE id IN (910011,910016)"), "2")
        # the three dummies stand once each and nothing else of their entry moved
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM creature WHERE id={DUMMY} AND map={MAP}"), "3")
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM creature WHERE id={DUMMY} AND map={OLD_MAP}"), "1", "only the stray")
        # nothing of the hub stands in a tier phase, on any map, and the Sanctum has one phase
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM creature WHERE phaseMask<>1"), "0")
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM gameobject WHERE phaseMask<>1"), "0")

    def test_the_move_changes_the_place_and_nothing_else(self):
        # The designer's hand edit on a managed source survives (one on a managed copy went with the copy); a creature that is not a managed guid and
        # the unmanaged scan row stand.
        self.assertEqual(self.db.query("SELECT ScriptName FROM creature WHERE guid=8000068"), "hand-edit-source")
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM creature WHERE guid=8000072"), "0", "the Blacksmith's tier-2 copy, hand edit and all, is gone")
        self.assertEqual(self.db.query(f"SELECT map,zoneId,areaId FROM creature WHERE guid={STRAY}"), f"{OLD_MAP}\t0\t0")
        self.assertEqual(self.db.query("SELECT map_id,area_id,entry FROM dc_area_source WHERE kind='g' AND source_guid=8001488"), f"{OLD_MAP}\t{OLD_AREA}\t191128")
        # The Rift Keeper is the row the old hub had, only elsewhere: its other columns are the seeded ones.
        self.assertEqual(self.db.query("SELECT COUNT(*),COUNT(DISTINCT curhealth,npcflag,spawntimesecs,wander_distance) FROM creature WHERE id=910003"), "1\t1")

    def test_the_jeweler_and_the_dummies_are_managed_rows_with_no_copy(self):
        jeweler = next(g for kind, entry, g, _ in self.services if entry == JEWELER)
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM creature WHERE id={JEWELER}"), "1")
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM dc_area_source WHERE kind='c' AND source_guid={jeweler} AND map_id={OLD_MAP}"), "0",
                         "the Jeweler's stale scan row under the old key is gone")
        dummies = [(g, reading) for kind, entry, g, reading in self.services if entry == DUMMY]
        self.assertEqual([g for g, _ in dummies], list(DUMMIES), "the three old-hub guids are the sources")
        for guid, reading in dummies:
            self.near(self.db.query(f"SELECT position_x,position_y,position_z,orientation FROM creature WHERE guid={guid}").split("\t"),
                      [reading[k] for k in "xyzo"], "the dummy's own row moved to its spot")
        self.assertEqual(self.db.query(f"SELECT COUNT(DISTINCT position_x,position_y) FROM creature WHERE id={DUMMY} AND map={MAP}"), "3", "three spots, not one")

    def test_the_area_registry_holds_each_source_once_under_the_hubs_key_and_no_copy(self):
        for kind, entry, guid, reading in self.services:
            self.assertEqual(self.lines(f"SELECT map_id,area_id,entry,source_phase FROM dc_area_source WHERE kind='{kind}' AND source_guid={guid}"),
                             [[str(MAP), str(AREA), str(entry), "1"]], f"{kind}:{entry} source")
            self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM dc_area_spawn WHERE kind='{kind}' AND source_guid={guid}"), "0", f"{kind}:{entry} has no copy row")
            # the source row is the stored spawn, to the bit (the area copier checks it)
            table = move.TABLES[kind]
            self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM dc_area_source s JOIN {table} t ON t.guid=s.source_guid WHERE s.kind='{kind}' AND s.source_guid={guid} "
                                           "AND t.id=s.entry AND t.position_x=s.position_x AND t.position_y=s.position_y AND t.position_z=s.position_z "
                                           "AND t.orientation=s.orientation"), "1", f"{kind}:{entry} source snapshot")
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM dc_area_spawn"), "0", "the Sanctum's registry holds no copy at all")
        # no (kind, guid) is owned twice: the core's area loader throws on that
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM (SELECT kind,guid FROM (SELECT kind,source_guid guid FROM dc_area_source "
                                       "UNION ALL SELECT kind,spawn_guid FROM dc_area_spawn) o GROUP BY kind,guid HAVING COUNT(*)>1) d"), "0")

    def test_the_old_hub_closes_and_the_sanctum_opens(self):
        wanted = sorted((r["map_id"], r["area_id"], r["phase_scope"], r["status"], r["note"]) for r in read(self.data.areas))
        self.assertEqual(sorted(tuple(r) for r in self.lines("SELECT map_id,area_id,phase_scope,status,note FROM dc_world_areas")), wanted)
        status = {(r[0], r[1]): r[2] for r in self.lines("SELECT map_id,area_id,status FROM dc_world_areas")}
        self.assertEqual(status[(str(OLD_MAP), str(OLD_AREA))], "closed")
        self.assertEqual(status[(str(MAP), str(AREA))], "open")

    def test_the_tome_template_grows_and_the_adders_templates_are_not_needed_to_apply(self):
        self.assertEqual(self.db.query(f"SELECT size FROM gameobject_template WHERE entry={TOME}"), "2")
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM gameobject_template WHERE entry BETWEEN 910090 AND 910099"), "0", "none of them was seeded")
        for entry in sorted(move.LATER_TEMPLATES & move.SCENERY):
            self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM gameobject WHERE id={entry}"), "1", f"{entry} stands once without its template")
        self.assertNotIn(f"gameobject_template WHERE entry={910092})", self.sql, "no guard asks for a template world_0036 writes later")


class Flip(FlipBase):
    def setUp(self, old_rows=True):
        self.db = Scratch(TABLES)
        self.addCleanup(self.db.drop)
        seed(self.db, old_rows)

    def test_the_migration_is_guarded_and_transactional(self):
        self.assertTrue(self.sql.startswith("-- Generated by generate_hub_sanctum_move.py"))
        self.assertIn("START TRANSACTION;", self.sql)
        self.assertEqual(self.sql.count("\nCOMMIT;"), 1)
        self.assertLess(self.sql.index("INSERT INTO dc_sanctum_move_guard"), self.sql.index("DELETE FROM `dc_world_areas`"))
        self.assertNotIn("DELETE FROM creature", self.sql)
        # the only spawn rows it deletes are the designer's editor leftovers, each by guid AND entry
        deleted = re.findall(r"DELETE FROM `gameobject` WHERE `guid`=(\d+) AND `id`=(\d+);", self.sql)
        self.assertEqual([(int(g), int(e)) for g, e in deleted], list(move.DEV_LEFTOVERS))
        self.assertEqual(self.sql.count("DELETE FROM `gameobject`"), len(deleted), "no delete of a gameobject by anything but guid and entry")
        self.assertEqual(self.sql.count("DELETE FROM gameobject"), 0)

    def test_it_applies_after_world_0034_retired_the_pillar(self):
        """diablocraft-j8yb: bb67's regenerated move still guarded on the pillar's template (910010), which world_0034 deletes, so dev's
        worldserver stopped at 'Reapplying update world_0032' (ERROR 3819). Here the Scryer-era pillar (template, ten spawns, their registry
        rows, from the frozen old-hub sheet) is seeded, the real world_0034 runs, and only then the move: it must apply, and write no pillar."""
        old = next(r for r in read(LEGACY / "world_hub_placements.csv") if json.loads(r["placement"])["id"] == PILLAR)
        row, copies = json.loads(old["placement"]), json.loads(old["copy_guids"])
        guids = {1: int(old["source_guid"]), **{int(t): g for t, g in copies.items()}}
        self.db.query("INSERT IGNORE INTO gameobject_template SELECT * FROM acore_world.gameobject_template WHERE entry=910010;")
        for tier, guid in guids.items():
            self.db.query(ignore(insert("gameobject", dict(row, guid=guid, phaseMask=tier, map=OLD_MAP, zoneId=OLD_AREA, areaId=OLD_AREA))))
            if tier > 1:
                self.db.query(ignore(insert("dc_area_spawn", dict(map_id=OLD_MAP, area_id=OLD_AREA, kind="g", source_guid=guids[1], tier=tier, spawn_guid=guid))))
        self.db.query(ignore(insert("dc_area_source", dict(map_id=OLD_MAP, area_id=OLD_AREA, kind="g", source_guid=guids[1], entry=PILLAR, source_phase=1,
                                                    position_x=row["position_x"], position_y=row["position_y"], position_z=row["position_z"],
                                                    orientation=row["orientation"]))))
        self.db.query((move.UPDATES / "world_0034_tier_obelisk_retired.sql").read_text(encoding="utf-8"))
        self.assertEqual(self.db.query(f"SELECT (SELECT COUNT(*) FROM gameobject_template WHERE entry={PILLAR}) + (SELECT COUNT(*) FROM gameobject WHERE id={PILLAR})"), "0",
                         "world_0034 took the pillar away")
        self.apply()
        self.assertEqual(self.db.query(f"SELECT (SELECT COUNT(*) FROM gameobject_template WHERE entry={PILLAR}) + (SELECT COUNT(*) FROM gameobject WHERE id={PILLAR})"
                                       f" + (SELECT COUNT(*) FROM dc_area_source WHERE kind='g' AND entry={PILLAR})"), "0", "the move brings no pillar back")
        self.assertNotIn(str(PILLAR), self.sql, "nothing in the migration names the pillar")
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM gameobject WHERE id=910011 AND map={MAP}"), "1", "the obelisk still stands, once")

    def test_the_move_alone_writes_no_copy(self):
        """The move (without the one-copy migration) writes only phase-1 rows and no registry copy row; the old model's copies it leaves
        for generate_sanctum_one_copy.py."""
        self.db.query(self.sql)
        before = {t: self.db.query(f"SELECT COUNT(*) FROM {t} WHERE phaseMask>1") for t in ("creature", "gameobject")}
        self.setUp(old_rows=False)
        self.db.query(self.sql)
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM creature WHERE phaseMask<>1"), "0")
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM gameobject WHERE phaseMask<>1"), "0")
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM dc_area_spawn"), "0")
        self.assertGreater(int(before["creature"]), 0, "the seeded old model does hold copies for this to be telling")

    def test_the_points_the_hub_row_and_the_start_rows_follow_the_readings(self):
        stock = self.lines("SELECT * FROM playercreateinfo WHERE NOT (map=530 AND zone=3703) ORDER BY race,`class`")
        self.assertEqual(len(stock), 3)
        self.apply()
        readings = self.data.readings
        rows = self.lines("SELECT name,map_id,area_id,x,y,z,o FROM dc_world_hub_point ORDER BY name")
        self.assertEqual([r[0] for r in rows], ["rift_exit", "spawn", "town_portal"], "no graveyard row in the points table")
        for row in rows:
            self.assertEqual((row[1], row[2]), (str(MAP), str(AREA)))
            self.near(row[3:], [readings[row[0]][k] for k in "xyzo"], row[0])
        hub = self.lines("SELECT id,map_id,area_id,x,y,z,o FROM dc_world_hub")
        self.assertEqual(hub[0][:3], ["1", str(MAP), str(AREA)])
        self.near(hub[0][3:], [readings["spawn"][k] for k in "xyzo"], "dc_world_hub")
        start = self.lines("SELECT race,`class`,map,zone,position_x,position_y,position_z,orientation FROM playercreateinfo ORDER BY race,`class`")
        moved = [r for r in start if r[2] == str(MAP)]
        self.assertEqual({(r[0], r[1]) for r in moved}, {("1", "1"), ("2", "1"), ("10", "1"), ("2", "8"), ("3", "8"), ("4", "8"), ("6", "8")},
                         "class 1 and the Wizard rows of world_0028 start in the Sanctum")
        for row in moved:
            self.assertEqual(row[3], str(AREA))
            self.near(row[4:], [readings["spawn"][k] for k in "xyzo"], f"start row {row[:2]}")
        self.assertEqual(self.lines("SELECT * FROM playercreateinfo WHERE NOT (map=750 AND zone=4273) ORDER BY race,`class`"), stock, "stock start rows stay")
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM playercreateinfo WHERE map={OLD_MAP} AND zone={OLD_AREA}"), "0")

    def test_death_in_the_sanctum_resolves_to_the_new_graveyard(self):
        grave = self.data.readings["graveyard"]
        before = closest_graveyard(self.db, MAP, AREA, grave["x"], grave["y"], grave["z"])
        self.assertEqual(before, 1384, "before the flip the Sanctum's area is linked to the Storm Peaks graveyard only (map 571)")
        stock = self.db.query("SELECT * FROM graveyard_zone WHERE ID IN (994,1384) ORDER BY ID,GhostZone")
        self.apply()
        for where in (grave, self.data.readings["spawn"], dict(x=0.0, y=0.0, z=0.0)):
            self.assertEqual(closest_graveyard(self.db, MAP, AREA, where["x"], where["y"], where["z"]), GRAVEYARD)
        row = self.lines(f"SELECT ID,Map,x,y,z FROM game_graveyard WHERE ID={GRAVEYARD}")[0]
        self.assertEqual(row[:2], [str(GRAVEYARD), str(MAP)])
        self.near(row[2:], [grave["x"], grave["y"], grave["z"]], "graveyard position")
        self.assertEqual(self.db.query(f"SELECT Faction FROM graveyard_zone WHERE ID={GRAVEYARD} AND GhostZone={AREA}"), "0", "neutral: every team")
        self.assertEqual(self.db.query("SELECT * FROM graveyard_zone WHERE ID IN (994,1384) ORDER BY ID,GhostZone"), stock, "the stock links stay as they were")
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM graveyard_zone WHERE ID=1384 AND GhostZone={AREA}"), "1")

    def test_applying_twice_changes_nothing(self):
        self.apply()
        first = snapshot(self.db)
        self.apply()
        self.assertEqual(snapshot(self.db), first)

    def test_a_database_without_the_old_rows_gets_every_row(self):
        self.setUp(old_rows=False)
        self.apply()
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM creature"), "10")   # the four artisans, the Jeweler, Kadala, the 3 dummies, the coffer
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM gameobject"), "15")   # 2 managed objects, the campfire, table and book, and the designer's ten table and platform groups
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM dc_area_source"), "25")   # one source row per creature (10) and gameobject (15)
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM dc_area_spawn"), "0")
        self.assertEqual(self.db.query(f"SELECT COUNT(*) FROM creature WHERE map<>{MAP} OR areaId<>{AREA} OR zoneId<>{AREA}"), "0")
        # an inserted row is the placement's own JSON (the Mystic's live export), and the coffer takes the Blacksmith's respawn period
        self.assertEqual(self.db.query("SELECT curhealth,spawnMask,spawntimesecs FROM creature WHERE guid=8000069"), "12600\t1\t300")
        self.assertEqual(self.db.query(f"SELECT DISTINCT spawntimesecs,spawnMask FROM creature WHERE id={COFFER_ENTRY}"), "300\t1")
        first = snapshot(self.db)
        self.apply()
        self.assertEqual(snapshot(self.db), first)

    def test_the_coffer_respawns_like_the_blacksmith_and_no_other_npc(self):
        data = Data(tempfile.mkdtemp(prefix="move-respawn-", dir=SCRATCH))
        self.addCleanup(shutil.rmtree, data.folder, ignore_errors=True)
        edit_placement(data.placements, SMITH, spawntimesecs=777)
        self.setUp(old_rows=False)  # an existing coffer row keeps its own respawn time: only inserted rows take the Blacksmith's
        self.db.query(data.generate())
        self.assertEqual(self.db.query(f"SELECT DISTINCT spawntimesecs FROM creature WHERE id={COFFER_ENTRY}"), "777")

    def test_alexs_own_rows_on_dev_go_with_the_copies_and_each_thing_stands_once(self):
        """Card q-1005-04: on Torment Development the designer had deleted every layer and placed ONE Covetous Shen, a campfire, a table and a book
        by hand, all in phase 10 and in no area; diablocraft-bb67 added Kadala's hand spawn the same way. They hold the tier-10 GUIDs of the
        old model's managed rows, so they are tier copies: the one-copy migration deletes them, and the source the move writes stands alone."""
        self.setUp(old_rows=False)
        hand = {(kind, entry): retired_copies()[kind, guid][10] for kind, entry, guid, _ in self.services
                if (kind, entry) in (("c", 910004), ("g", 1799), ("g", 180324), ("g", 2695), ("c", KADALA))}
        self.assertEqual(hand, {("c", 910004): 8000131, ("g", 1799): 8001522, ("g", 180324): 8001526, ("g", 2695): 8001531, ("c", KADALA): 8000159},
                         "the hand rows are the tier-10 copies of the retired sheet")
        for guid, entry in ((8000131, 910004), (8000159, KADALA)):
            self.db.query("INSERT INTO creature (guid,id,map,zoneId,areaId,spawnMask,phaseMask,position_x,position_y,position_z,orientation,spawntimesecs,curhealth) "
                          f"VALUES ({guid},{entry},{MAP},0,0,1,10,1954.46,28.2846,329.276,5.37519,300,170253);")
        for guid, entry in ((8001522, 1799), (8001526, 180324), (8001531, 2695)):
            self.db.query("INSERT INTO gameobject (guid,id,map,zoneId,areaId,spawnMask,phaseMask,position_x,position_y,position_z,orientation,"
                          f"rotation0,rotation1,rotation2,rotation3,spawntimesecs,animprogress,state) VALUES ({guid},{entry},{MAP},0,0,1,10,1,2,3,0.5,0,0,-0.5,0.5,300,0,1);")
        self.apply()
        for entry, table in ((910004, "creature"), (KADALA, "creature"), (1799, "gameobject"), (180324, "gameobject"), (2695, "gameobject")):
            self.assertEqual(self.db.query(f"SELECT COUNT(*),SUM(phaseMask=1 AND map={MAP} AND areaId={AREA} AND zoneId={AREA}) FROM {table} WHERE id={entry}"), "1\t1", entry)
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM creature WHERE guid IN (8000131,8000159) AND phaseMask=10"), "0")
        first = snapshot(self.db)
        self.apply()
        self.assertEqual(snapshot(self.db), first)

    def test_alexs_editor_leftovers_go_and_a_row_that_is_not_theirs_stays(self):
        """His export's Platform, Red Aura, Ritual Candle, Book of the Dead and Musty Scroll rows and his extra Tome are deleted; a row on one
        of those guids that holds another entry is not, and a template another spawn still wears is not."""
        self.setUp(old_rows=False)
        rows = [(guid, entry) for guid, entry in move.DEV_LEFTOVERS if guid != 8001569] + [(8001569, 12345), (8001700, 910089)]
        for guid, entry in rows:
            self.db.query("INSERT INTO gameobject (guid,id,map,zoneId,areaId,spawnMask,phaseMask,position_x,position_y,position_z,orientation,"
                          f"rotation0,rotation1,rotation2,rotation3,spawntimesecs,animprogress,state) VALUES ({guid},{entry},{MAP},0,0,1,1,1,2,3,0.5,0,0,0,1,300,0,1);")
        self.db.query("INSERT INTO gameobject_template (entry,type,displayId,name) VALUES (910087,5,7060,'Platform'),(910089,5,264,'Red Aura');")
        self.apply()
        self.assertEqual(self.db.query("SELECT guid,id FROM gameobject WHERE guid IN (8001559,8001563,8001564,8001567,8001568,8001569,8001700) ORDER BY guid"),
                         "8001569\t12345\n8001700\t910089", "only the entries on his guids went")
        self.assertEqual(self.db.query("SELECT entry FROM gameobject_template WHERE entry IN (910087,910089) ORDER BY entry"), "910089",
                         "his Platform template went, the Red Aura one stays while a spawn wears it")

    def test_a_row_that_is_not_ours_stops_the_migration_before_it_writes(self):
        cases = {
            "a dummy guid held by another entry": f"UPDATE creature SET id=910000 WHERE guid={DUMMIES[1]}",
            "a dummy in another tier's phase": f"UPDATE creature SET phaseMask=2 WHERE guid={DUMMIES[2]}",
            "the dummy's template missing": "DELETE FROM creature_template WHERE entry=31146",
            "the coffer's source claiming another entry": "UPDATE creature SET id=910000 WHERE guid=8000112",
            "the source guid of a gameobject held by another entry": "UPDATE gameobject SET id=180322 WHERE guid=8001469",
            "a source guid registered as a copy": "INSERT INTO dc_area_spawn (map_id,area_id,kind,source_guid,tier,spawn_guid) VALUES (530,3703,'c',123,2,8000068)",
            "the Jeweler's template missing": "DELETE FROM creature_template WHERE entry=910004",
            "the obelisk's template missing": "DELETE FROM gameobject_template WHERE entry=910011",
            "graveyard 910000 held by another map": "INSERT INTO game_graveyard (ID,Map,x,y,z,Comment) VALUES (910000,571,0,0,0,'foreign')",
            "no spawn point to take the old hub from": "DELETE FROM dc_world_hub_point WHERE name='spawn'",
        }
        # A rollback hides where it stopped, so the line of the error says it: every case must fail at a guard line, before the
        # first statement, not at the closing post-condition that would also catch a foreign row after the moves.
        guards = self.sql.splitlines().index("-- the area rules: the old hub closes, the Sanctum stays open (dc_world_areas has no key)")
        for label, damage in cases.items():
            with self.subTest(label):
                self.db.query(damage)
                before = snapshot(self.db)
                done = self.db.run(self.sql)
                self.assertNotEqual(done.returncode, 0, "the migration went through")
                self.assertRegex(done.stderr, r"ERROR (3819|1048)", "it stopped, but not at a guard: " + done.stderr[:200])
                self.assertLessEqual(int(re.search(r"at line (\d+)", done.stderr).group(1)), guards, "it stopped after the guards: " + done.stderr[:200])
                self.assertEqual(snapshot(self.db), before, "it wrote before it stopped")
                self.setUp()  # a fresh database for the next case

    def test_a_statement_that_did_nothing_is_caught_by_the_post_condition(self):
        # If any statement of one family is cut out, the closing guards must abort and leave nothing behind.
        families = {"the registry's source rows": r"INSERT INTO dc_area_source \(map_id[^;]*;",
                    "the graveyard link": r"INSERT INTO `graveyard_zone`[^;]*;",
                    "the hub row": r"REPLACE INTO dc_world_hub SELECT[^;]*;",
                    "the points": r"REPLACE INTO dc_world_hub_point VALUES\('rift_exit'[^;]*;",
                    "the registry's old copy rows going": r"DELETE FROM dc_area_spawn WHERE[^;]*;",
                    "the registry's old source rows going": r"DELETE FROM dc_area_source WHERE[^;]*;",
                    "the coffer's row": r"INSERT INTO `creature` \(`id`,`spawnMask`,`spawntimesecs`,`guid`,`phaseMask`[^;]*VALUES \(910018,1,\d+,\d+,1,[^;]*;",
                    "the Sanctum's own rule": r"INSERT INTO `dc_world_areas` \([^;]*VALUES \(750,4273,[^;]*;"}
        for label, pattern in families.items():
            with self.subTest(label):
                broken = re.sub(pattern, "SELECT 1;", self.sql)
                self.assertNotEqual(broken, self.sql, f"no statement for {label} to remove")
                before = snapshot(self.db)
                done = self.db.run(broken)
                self.assertNotEqual(done.returncode, 0, "the migration went through without " + label)
                self.assertRegex(done.stderr, r"ERROR (3819|1048)", "it stopped, but not at a guard: " + done.stderr[:200])
                self.assertEqual(snapshot(self.db), before)
                self.setUp()

    def test_a_statement_that_did_the_wrong_thing_is_caught_by_the_post_condition(self):
        # Each clause of the closing check must be able to stop the migration on its own: one statement is damaged so that
        # everything else still counts right (the same rows, left in the old map, area or zone, or registered under the wrong
        # key), and the migration must abort at the closing check, after the statements, and leave nothing behind.
        def stays(column):
            return (rf"(VALUES \(910000,750,8000068,[^;]*?)`{column}`=VALUES\(`{column}`\)", rf"\1`{column}`=`{column}`")
        damage = {
            "a row that stays on the old map": stays("map"),
            "a row that stays in the old area": stays("areaId"),
            "a row that stays in the old zone": stays("zoneId"),
            "a source registered in another area": (r"SELECT 750,4273,'c',8000068,", "SELECT 750,1,'c',8000068,"),
            "the graveyard on another map": (r"(INSERT INTO `game_graveyard` [^;]*?VALUES \(910000,)750,", r"\g<1>751,"),
            "the graveyard linked to another zone": (r"(INSERT INTO `graveyard_zone` [^;]*?VALUES \(910000,)4273,", r"\g<1>4274,"),
            "a point in another area": (r"VALUES\('rift_exit',750,4273,", "VALUES('rift_exit',750,4274,"),
            "a point on another map": (r"VALUES\('rift_exit',750,4273,", "VALUES('rift_exit',751,4273,"),
            "the hub row in another area": (r"REPLACE INTO dc_world_hub SELECT 1,map_id,area_id,", "REPLACE INTO dc_world_hub SELECT 1,map_id,0,"),
            "the hub row on another map": (r"REPLACE INTO dc_world_hub SELECT 1,map_id,area_id,", "REPLACE INTO dc_world_hub SELECT 1,751,area_id,"),
            "the Sanctum's rule closed": (r"(VALUES \(750,4273,CONVERT\(X'616c6c' USING utf8mb4\),)CONVERT\(X'6f70656e' USING utf8mb4\)",
                                          r"\1CONVERT(X'636c6f736564' USING utf8mb4)"),
            "the Sanctum's rule for one tier": (r"(VALUES \(750,4273,)CONVERT\(X'616c6c' USING utf8mb4\)", r"\1CONVERT(X'74696572' USING utf8mb4)"),
        }
        lines = self.sql.splitlines()
        closing = lines.index("COMMIT;")  # 0-based index of COMMIT; walk back over the closing guards: their first line is number closing + 1
        while lines[closing - 1].startswith("INSERT INTO dc_sanctum_move_guard"):
            closing -= 1
        for label, (pattern, replacement) in damage.items():
            with self.subTest(label):
                broken, count = re.subn(pattern, replacement, self.sql, count=1)
                self.assertEqual(count, 1, f"no statement to damage for {label}")
                before = snapshot(self.db)
                done = self.db.run(broken)
                self.assertNotEqual(done.returncode, 0, "the migration went through with " + label)
                self.assertRegex(done.stderr, r"ERROR (3819|1048)", "it stopped, but not at a guard: " + done.stderr[:200])
                self.assertGreater(int(re.search(r"at line (\d+)", done.stderr).group(1)), closing, "it stopped before the closing check: " + done.stderr[:200])
                self.assertEqual(snapshot(self.db), before)
                self.setUp()

    def test_a_graveyard_that_is_already_there_follows_the_reading(self):
        # A rerun after the reading moved: the row and its link are updated, not skipped.
        grave = self.data.readings["graveyard"]
        self.db.query(f"INSERT INTO game_graveyard (ID,Map,x,y,z,Comment) VALUES ({GRAVEYARD},{MAP},1,2,3,'an older reading'); "
                      f"INSERT INTO graveyard_zone (ID,GhostZone,Faction,Comment) VALUES ({GRAVEYARD},{AREA},1,'an older link')")
        self.apply()
        row = self.lines(f"SELECT Map,x,y,z FROM game_graveyard WHERE ID={GRAVEYARD}")[0]
        self.assertEqual(row[0], str(MAP))
        self.near(row[1:], [grave["x"], grave["y"], grave["z"]], "the graveyard moved to the reading")
        self.assertEqual(self.db.query(f"SELECT Faction FROM graveyard_zone WHERE ID={GRAVEYARD} AND GhostZone={AREA}"), "0", "neutral again")


class CoreFacts(unittest.TestCase):
    """What the graveyard model above stands on, read from the pinned core's source (never built or run here)."""

    def test_the_core_looks_up_the_area_first_and_prefers_a_graveyard_on_the_players_map(self):
        text = (CORE / "game/Misc/GameGraveyard.cpp").read_text(encoding="utf-8")
        body = text.split("GraveyardStruct const* Graveyard::GetClosestGraveyard(uint32 mapId", 1)[1]
        self.assertLess(body.index("GraveyardStore.equal_range(areaId)"), body.index("GraveyardStore.equal_range(zoneId)"))
        self.assertRegex(body, r"if \(mapId != entry->Map\)")
        self.assertRegex(body, r"if \(entryNear\)\s*return entryNear;\s*if \(entryEntr\)\s*return entryEntr;\s*return entryFar;")


if __name__ == "__main__":
    unittest.main()

"""diablocraft-ftoz: the Sanctum hub stands where the designer's .gps readings (card q-1003-39) put it.

    python3 mod-diablocraft/scripts/tests/world/test_hub_sanctum_readings.py   # the migration cases need the fixture mysqld (fixture_mysql.sh start),
                                                                   # the floor cases the server data folder (DC_DATA_DIR; skipped loudly without)

diablocraft-976b built the flip and left every position blank; this task fills them from the designer's answer to the card. READINGS is that
answer, transcribed number for number from the `.gps` lines he pasted (the card's file lives in the agent scratch folder and does not outlive
the task), so it is a second copy for the data cells to be compared with, not a restatement of them. Pinned:

  * every cell of the hub data files holds its reading, and the card's rulings stand: the rift exit is the town portal's spot, the graveyard
    is the spawn's, the tome is the stack's (the generator floats it), and the two spots with no reading (the obelisk, the designer still has to say
    where; the Stash, which the card never listed) are flagged PROVISIONAL and nothing else is;
  * by the card's own evidence nothing floats or sinks: Z and the `.gps` FloorZ agree to a hundredth of a yard on every reading;
  * the obelisk stands where the rift quest finds it: within the code's search radius of a player taking the quest at the Rift Keeper;
  * the committed migration is what the generator writes from those files, and applied to a scratch database seeded Scryer-style it puts every
    spawn of every tier on a number of READINGS (not of the data files), with the hub row and the start rows following the spawn;
  * on the arena's walking mesh each spot has exactly one ground polygon within 6 yd of its height, the polygon is within the mesh's measured
    error of that height, and a player can walk to it from the arena floor with the door shut; the check catches a spot that floats, sinks or
    stands on another level.

What it does not prove: the mesh is a walking graph with a polygon plane for its height (measured against the designer's FloorZ it is off by -0.35 to
+0.90 yd, hence the tolerance), so the exact floor is FloorZ's, which exists only for the readings the designer took; the provisional spots' heights come
from the mesh corrected by their neighbour's FloorZ, and the designer's own .gps replaces them; nothing here was seen in game (his dev check is).
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
import generate_sanctum_one_copy as one  # noqa: E402
import generate_world_objects as objects  # noqa: E402
import test_hub_sanctum_navmesh as nav  # noqa: E402
from test_hub_sanctum_move import SCRATCH, TABLES, Data, seed  # noqa: E402
from test_hub_sanctum_seal import Scratch  # noqa: E402

ROOT = HERE.parents[1]
MAP, AREA = 750, 4273
# The designer's answer to card q-1003-39 (2026-10-04): x, y, z, orientation, and the FloorZ his .gps printed. Items 9 (a second difficulty pillar:
# there is none, 910011 is the Rift Obelisk), 11 ("same as 1, but just slightly higher": the tome over its stack), 13 (the obelisk, no reading yet)
# and 14 ("same exact as spawn") have no numbers of their own.
READINGS = {
    "spawn": (1907.5111, -24.066214, 330.72403, 6.270593, 330.72397),
    "town_portal": (1960.4799, -4.998772, 325.86954, 3.3371348, 325.86948),
    "rift_exit": (1960.4799, -4.998772, 325.86954, 3.3371348, 325.86948),
    "blacksmith": (1950.5061, 23.951012, 329.3435, 5.282561, 329.3435),
    "mystic": (1956.9464, 32.283268, 330.24683, 5.196139, 330.24673),
    "rift_keeper": (1950.4575, -24.220394, 326.46335, 3.155683, 326.46335),
    "coffer": (1935.3857, -23.56033, 327.82968, 3.1909845, 327.8302),
}
# The designer's answer to cards q-1004-15 and q-1004-12 (2026-10-04, diablocraft-sanctum-jeweler-dummies): x, y, z, orientation, no FloorZ (the floor test
# below stands in for it). The dummies' facing is World's choice, one for all three: the circular mean of the designer's own 0.468, 6.276 and 1.388.
DUMMY_FACING = 0.6026884
READINGS_1004 = {
    "dummy_center": (1957.4902, -81.73436, 329.86935, DUMMY_FACING),
    "dummy_left": (1956.7986, -77.412445, 329.58234, DUMMY_FACING),
    "dummy_right": (1960.7241, -84.9604, 330.1041, DUMMY_FACING),
}
# The designer's own placements on Torment Development with the GObject Editor (card q-1005-04, option B, read from the dev world database
# 2026-10-05): the one Covetous Shen he left standing, which replaces the Jeweler's .gps reading above, and a campfire, a table and a book he said
# can go to all layers. x, y, z, orientation as the migration writes them (the shortest float32 text of the database's values).
READINGS_1005 = {
    "jeweler": (1954.463, 28.284613, 329.27557, 5.375188),
    "campfire": (1953.3011, 25.12668, 329.1241, 2.4024549),
    "table": (1940.47, 19.7596, 329.66302, 0.0156306),
    "book": (1941.8392, 19.813763, 330.54486, 0.23830691),
}
# The designer's layout in the Azeroth World Editor (2026-10-09, diablocraft-bb67), transcribed from the lines of his export 2026_10_10_00_project.sql
# (never run): x, y, z, orientation. It moves the Rift Obelisk, Rift Keeper, Kadala, the Campfire, the Stash, the Blacksmith, Covetous Shen, the
# Mystic and the Tome (these replace their earlier readings above), and adds the stairs, the platform and what stands on the table.
READINGS_1009 = {
    "obelisk": (1981.4307946115384, -27.857825747327773, 332.6264567286634, 3.7604),
    "rift_keeper": (1981.7909627908873, -24.2204, 332.5950096559808, 3.7076257715233294),
    "kadala": (1952.27, -10.548111534779814, 326.13, 2.52267),
    "campfire": (1955.0446274800759, 23.119651502961688, 329.06588489273463, 2.40245),
    "stash": (1944.7120088959714, 21.492023359082744, 329.57, 5.28256),
    "blacksmith": (1953.4014088411602, 22.75984898996156, 329.0246236350216, 6.141062333255706),
    "jeweler": (1954.9770778173463, 25.746909345855816, 329.23315283812707, 5.37519),
    "mystic": (1935.8785136146312, 19.07354256654343, 329.9252627667394, 5.831548396321525),
    "tome": (1940.5966044328486, 19.90584217841123, 330.57306265066103, 4.692410419104963),
    "stairs": (1957.3135028232387, -27.822905369053174, 326.26539100154156, 3.161017508481482),
    "candle01": (1939.3339039346197, 20.661157163355877, 330.5656302907737, 5.197196123866191),
    "skull_candle": (1939.3991400625464, 19.14450433511672, 330.5774200354902, 4.95207929189929),
    "candle03": (1939.011071930997, 20.34174279722692, 330.55487425990094, 5.01421534258591),
    "scroll": (1939.302917965982, 19.854115544122667, 330.5770292238392, 5.420412304882292),
    "platform": (1981.0141051199585, -27.499431865829443, 329.5817762403788, 2.5729427172602763),
    "red_aura_small": (1940.610604966286, 19.853143419801814, 330.52946605532196, 4.277025457091591),
    "ritual_candle": (1938.8549413780809, 20.012342574018, 330.5721050803362, 5.0805085337632025),
    "book_of_the_dead": (1941.9462369204723, 19.895149153307216, 330.4954005391657, 4.752185166495012),
    "musty_scroll": (1942.0586481278303, 19.377874659785014, 330.61324019711344, 6.248638520687512),
}
# what stands where the designer's own quaternion says (rotation0..3 as his editor stored them): the scenery keeps it in every tier; the rest derive it from the facing
SCENERY_ROTATION = {
    "campfire": (0.0, 0.0, 0.0, 1.0), "table": (0.0, 0.0, -0.707107, 0.707107), "book": (0.0, 0.0, -0.6238797, 0.7815205),
    "stairs": (0, 0, 0.999953, -0.009712), "candle01": (0, 0, 0.516702, -0.856165), "skull_candle": (0, 0, 0.617494, -0.786575),
    "candle03": (0, 0, 0.592763, -0.805377), "scroll": (0, 0, 0.418131, -0.908387), "platform": (0, 0, 0.959851, 0.28051),
    "red_aura_small": (0, 0, 0.843131, -0.537708), "ritual_candle": (0, 0, 0.565747, -0.824579),
    "book_of_the_dead": (-0.002809, -0.016959, 0.692696, -0.721025), "musty_scroll": (-0.204266, -0.00385, 0.018447, -0.978734),
}
DUMMY, DUMMY_NAMES = 31146, {8000108: "dummy_center", 8000109: "dummy_left", 8000110: "dummy_right"}
ENTRY_NAMES = {910000: "blacksmith", 910001: "mystic", 910002: "stash", 910003: "rift_keeper", 910004: "jeweler", 910005: "kadala",
               910011: "obelisk", 910016: "tome", 1799: "campfire", 180324: "table", 2695: "book",
               910090: "stairs", 910092: "platform", 910093: "red_aura_small", 910094: "ritual_candle", 910095: "book_of_the_dead",
               910096: "musty_scroll", 180338: "candle01", 180425: "skull_candle", 180340: "candle03", 182005: "scroll"}
GAMEOBJECTS = {910011, 910016, 1799, 180324, 2695, 910090, 910092, 910093, 910094, 910095, 910096, 180338, 180425, 180340, 182005}
# the readings the data holds now: the earlier cards' numbers, except where the designer's layout replaced them
LIVE = {**{k: v for k, v in {**READINGS, **READINGS_1004, **READINGS_1005}.items() if k not in READINGS_1009}, **READINGS_1009}
ON_THE_PLATFORM = {"obelisk", "rift_keeper"}   # they stand on the designer's platform, a decoration the walking mesh does not know
COFFER_ENTRY = 910018
SERVICES = [("c", entry, name) for entry, name in ENTRY_NAMES.items() if entry not in GAMEOBJECTS] + \
           [("g", entry, name) for entry, name in ENTRY_NAMES.items() if entry in GAMEOBJECTS] + [("c", COFFER_ENTRY, "coffer")]
SAME_SPOT = ({"spawn", "graveyard"}, {"town_portal", "rift_exit"})   # the card's own rulings (item 11, the tome over its stack, ended with the layout)
PROVISIONAL = set()   # the obelisk and the Stash had no reading on the card; the designer's layout gave both
FLOOR_EVIDENCE = 0.01   # yd: Z against the .gps FloorZ; the largest difference on the card is 0.0009
LEVEL = 6.0             # yd: the walking surfaces this close to a spot's height are the candidates for the floor under it
MESH_ERROR = 1.5        # yd: a polygon's plane against the true floor; measured -0.35 .. +0.90 over the designer's nine floor readings


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def number(cell, what):
    if cell is None or str(cell).strip() == "":
        raise AssertionError(f"{what} is blank")
    return float(cell)


def live_spots():
    """name -> (x, y, z, o) from the hub's data files, and name -> its note."""
    found, notes = {}, {}
    for row in read(move.POINTS):
        found[row["name"]] = tuple(number(row[key], f"{row['name']} {key}") for key in "xyzo")
        notes[row["name"]] = row["source"]
    for row in read(move.PLACEMENTS):
        placement = json.loads(row["placement"])
        name = DUMMY_NAMES[int(row["source_guid"])] if placement["id"] == DUMMY else ENTRY_NAMES[placement["id"]]
        found[name] = tuple(number(placement[key], f"{name} {key}") for key in move.PLACE)
        notes[name] = row["source"]
    coffer = read(move.COFFER)[0]
    found["coffer"] = tuple(number(coffer[key], f"coffer {key}") for key in "xyzo")
    notes["coffer"] = coffer["placement_source"]
    return found, notes


def plane_z(points, x, y):
    """The height of a walkable polygon (a fan of triangles from its first vertex) at (x, y); None outside it."""
    for k in range(1, len(points) - 1):
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = points[0], points[k], points[k + 1]
        d = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(d) < 1e-9:
            continue
        a = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / d
        b = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / d
        if min(a, b, 1 - a - b) >= -1e-6:
            return a * z1 + b * z2 + (1 - a - b) * z3
    return None


def surfaces(mesh, x, y):
    """Every ground polygon over (x, y), as (height, (tile x, tile y, polygon))."""
    tx, ty = int(32 - x / nav.GRID), int(32 - y / nav.GRID)
    return [(h, (tx, ty, i)) for i, poly in enumerate(mesh.tile(tx, ty)["polys"]) if poly["ground"]
            for h in [plane_z(poly["pts"], x, y)] if h is not None]


def floor_problems(mesh, walk, name, x, y, z):
    """What is wrong with standing at (x, y, z): not one floor under it, a floor too far off its height, or one a walker cannot reach."""
    near = [(h, key) for h, key in surfaces(mesh, x, y) if abs(h - z) < LEVEL]
    if len(near) != 1:
        return [f"{name}: {len(near)} walking surfaces within {LEVEL} yd of z {z} (wants exactly one)"]
    h, key = near[0]
    problems = []
    if abs(h - z) > MESH_ERROR:
        problems.append(f"{name}: z {z} but the walking floor there is {h:.2f}: it floats or sinks")
    if key not in walk:
        problems.append(f"{name}: the floor under it is not reachable on foot from the arena floor with the door shut")
    return problems


def doubles(*columns):
    """The columns as DOUBLE: the world database stores positions as FLOAT, which the client prints to six digits (1950.5061 as 1950.51)."""
    return ",".join(f"CAST({column} AS DOUBLE)" for column in columns)


def finds_the_obelisk(distance, search, interact):
    """dc_rifts.cpp looks for the obelisk within `search` yd of the player who takes the quest; he stands within `interact` of the Keeper."""
    return distance <= search - interact


def core_number(path, pattern):
    return float(re.search(pattern, path.read_text(encoding="utf-8")).group(1))


class ReadingsAreInTheData(unittest.TestCase):
    def test_every_reading_is_in_its_cell(self):
        spots, _ = live_spots()
        for name, reading in LIVE.items():
            self.assertEqual(spots[name], reading[:4], name)
        self.assertEqual(set(spots) - set(LIVE), {"graveyard"}, "every managed spot has a reading here (the graveyard is the spawn's)")

    def test_the_three_dummies_share_one_facing_and_stand_on_three_spots(self):
        spots, _ = live_spots()
        dummies = [spots[name] for name in DUMMY_NAMES.values()]
        self.assertEqual({d[3] for d in dummies}, {DUMMY_FACING}, "one facing for all three")
        self.assertEqual(len({d[:2] for d in dummies}), 3)

    def test_the_cards_rulings_stand(self):
        spots, notes = live_spots()
        self.assertEqual(spots["graveyard"], spots["spawn"], "item 14: same exact as the spawn")
        self.assertEqual(spots["rift_exit"], spots["town_portal"], "item 3: the same spot as the town portal")
        table = spots["table"]   # item 11 (the tome over its stack) ended: the Tome stands on the designer's table, at his z, with no float
        self.assertLess(math.dist(spots["tome"][:2], table[:2]), 2.0, "the Tome stands on the table")
        self.assertIn("Rift Obelisk", notes["obelisk"], "910011 is the obelisk, not a second pillar (item 9)")
        self.assertFalse([name for name in ENTRY_NAMES.values() if "pillar" in name], "the difficulty pillar is retired (world_0034)")

    def test_no_two_spots_share_a_place_but_the_ones_the_card_names(self):
        spots, _ = live_spots()
        by_place = {}
        for name, (x, y, _, _) in spots.items():
            by_place.setdefault((x, y), set()).add(name)
        for names in by_place.values():
            self.assertTrue(len(names) == 1 or names in SAME_SPOT, f"spots on one place: {sorted(names)}")

    def test_nothing_floats_or_sinks_by_the_cards_own_evidence(self):
        for name, (x, y, z, o, floor) in READINGS.items():
            self.assertLess(abs(z - floor), FLOOR_EVIDENCE, f"{name}: Z {z} against FloorZ {floor}")

    def test_every_note_names_its_source_and_only_the_spots_without_a_reading_are_provisional(self):
        _, notes = live_spots()
        for name, note in notes.items():
            self.assertNotIn("PENDING", note, name)
            for want in (("diablocraft-bb67", "2026_10_10_00_project.sql") if name in READINGS_1009 else
                         ("q-1005-04", "diablocraft-sanctum-jeweler-dummies") if name in READINGS_1005 else
                         ("q-1004-15", "q-1004-12", "diablocraft-sanctum-jeweler-dummies") if name in READINGS_1004 else ("q-1003-39", "diablocraft-ftoz")):
                self.assertIn(want, note, name)
            self.assertEqual("PROVISIONAL" in note, name in PROVISIONAL, name)
        self.assertEqual(PROVISIONAL & set(LIVE), set(), "a spot with a reading is no longer provisional")

    def test_the_obelisk_is_where_the_rift_quest_finds_it(self):
        # dc_rifts.cpp looks for the obelisk within OBELISK_SEARCH_YARDS of the player who takes the quest; he stands within the core's
        # interaction distance of the Rift Keeper, so the obelisk has to be that much closer to the Keeper than the radius.
        spots, _ = live_spots()
        search = core_number(ROOT / "mod-diablocraft/src/rifts/dc_rifts_shared.h", r"OBELISK_SEARCH_YARDS\s*=\s*([0-9.]+)f")
        interact = core_number(ROOT / "azerothcore-wotlk/src/server/game/Entities/Object/ObjectDefines.h", r"define INTERACTION_DISTANCE\s+([0-9.]+)f")
        self.assertTrue(finds_the_obelisk(math.dist(spots["obelisk"][:3], spots["rift_keeper"][:3]), search, interact))
        # the rule has an edge, and a bound that let a farther obelisk through would prove nothing
        self.assertTrue(finds_the_obelisk(search - interact, search, interact))
        self.assertFalse(finds_the_obelisk(search - interact + 0.01, search, interact))


class TheMigrationCarriesTheReadings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = move.migration_name()
        cls.path = move.UPDATES / cls.name

    def test_the_committed_migration_is_what_the_generator_writes(self):
        self.assertTrue(self.path.is_file(), f"{self.name} is not committed")
        sql = move.generate()
        self.assertEqual(self.path.read_text(encoding="utf-8"), sql)
        mirror = ROOT / "mod-diablocraft/data/generated" / self.name
        self.assertEqual(mirror.read_text(encoding="utf-8"), sql, "the data/generated mirror")
        copies = one.generate()   # the migration that takes the old model's tier copies away (diablocraft-k4ce)
        name = move.migration_name(move.UPDATES, one.SUFFIX)
        self.assertEqual((move.UPDATES / name).read_text(encoding="utf-8"), copies, name)
        self.assertEqual((ROOT / "mod-diablocraft/data/generated" / name).read_text(encoding="utf-8"), copies, "the data/generated mirror of " + name)
        self.assertGreater(name, self.name, "it sorts after the move, which it follows")

    def database(self):
        db = Scratch(TABLES)
        self.addCleanup(db.drop)
        seed(db)
        return db

    def migrate(self, db):
        """The two migrations in file order: the move, then the one that takes the tier copies away."""
        db.query(self.path.read_text(encoding="utf-8"))
        db.query((move.UPDATES / move.migration_name(move.UPDATES, one.SUFFIX)).read_text(encoding="utf-8"))

    def test_applied_to_a_scryer_era_database_every_spawn_stands_once_on_a_reading(self):
        db = self.database()
        self.migrate(db)
        self.assert_on_readings(db)

    def test_a_later_reading_moves_the_spawns_again(self):
        # Dev applies this migration, then the designer gives the obelisk's and the Stash's real .gps and the generator is run again: the
        # second run has to move rows a first run already placed (here, synthetic readings first), not skip them.
        db = self.database()
        folder = tempfile.mkdtemp(prefix="readings-rerun-", dir=SCRATCH)
        self.addCleanup(shutil.rmtree, folder, True)
        db.query(Data(folder).generate())
        self.assertEqual(db.query(f"SELECT COUNT(*) FROM creature WHERE id=910000 AND ABS(position_x-1950.5061)<0.01"), "0", "the first run did not place it")
        self.migrate(db)
        self.assert_on_readings(db)

    def assert_on_readings(self, db):
        spots, _ = live_spots()

        def near(found, wanted, message):
            self.assertEqual(len(found), len(wanted), message)
            for got, want in zip(found, wanted):
                self.assertLess(abs(float(got) - want), 1e-3, f"{message}: {got} != {want}")

        for kind, entry, name in SERVICES:
            x, y, z, o = LIVE[name][:4] if name in LIVE else spots[name]
            table = "creature" if kind == "c" else "gameobject"
            rows = [line.split("\t") for line in db.query(
                f"SELECT phaseMask,map,areaId,{doubles('position_x', 'position_y', 'position_z', 'orientation')} "
                f"FROM {table} WHERE id={entry} ORDER BY phaseMask").splitlines()]
            self.assertEqual([int(r[0]) for r in rows], [1], f"{name} stands once, in phase 1")
            for row in rows:
                self.assertEqual(row[1:3], [str(MAP), str(AREA)], f"{name} tier {row[0]}")
                near(row[3:], [x, y, z, o], f"{name} tier {row[0]}")
            if name in SCENERY_ROTATION:   # the designer's quaternion as his editor stored it
                turned = [line.split("\t") for line in db.query(
                    f"SELECT {doubles('rotation0', 'rotation1', 'rotation2', 'rotation3')} FROM gameobject WHERE id={entry}").splitlines()]
                self.assertEqual(len(turned), 1, name)
                for got in turned:
                    near(got, list(SCENERY_ROTATION[name]), f"{name} rotation")
        for row in read(move.PLACEMENTS):   # the dummies share an entry, so each is found by its guids
            if json.loads(row["placement"])["id"] != DUMMY:
                continue
            name = DUMMY_NAMES[int(row["source_guid"])]
            rows = [line.split("\t") for line in db.query(
                f"SELECT phaseMask,map,areaId,{doubles('position_x', 'position_y', 'position_z', 'orientation')} FROM creature "
                f"WHERE id={DUMMY} AND guid={int(row['source_guid'])}").splitlines()]
            self.assertEqual([int(r[0]) for r in rows], [1], f"{name} stands once, in phase 1")
            for r in rows:
                self.assertEqual(r[1:3], [str(MAP), str(AREA)], f"{name} tier {r[0]}")
                near(r[3:], list(READINGS_1004[name]), f"{name} tier {r[0]}")
        for point in ("spawn", "town_portal", "rift_exit"):
            row = db.query(f"SELECT map_id,area_id,{doubles('x', 'y', 'z', 'o')} FROM dc_world_hub_point WHERE name='{point}'").split("\t")
            self.assertEqual(row[:2], [str(MAP), str(AREA)], point)
            near(row[2:], list(READINGS[point][:4]), point)
        near(db.query(f"SELECT {doubles('x', 'y', 'z', 'o')} FROM dc_world_hub WHERE id=1").split("\t"), list(READINGS["spawn"][:4]), "the hub row is the spawn")
        near(db.query(f"SELECT {doubles('x', 'y', 'z')} FROM game_graveyard WHERE ID=910000").split("\t"), list(READINGS["spawn"][:3]), "the graveyard is the spawn")
        starts = [line.split("\t") for line in db.query(
            f"SELECT {doubles('position_x', 'position_y', 'position_z', 'orientation')} FROM playercreateinfo WHERE map={MAP} AND zone={AREA}").splitlines()]
        self.assertEqual(len(starts), 7, "class 1 and the Wizard rows start in the Sanctum")
        for row in starts:
            near(row, list(READINGS["spawn"][:4]), "a start row is the spawn")


class FloorUnderTheSpots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            nav.ShutDoor.setUpClass()
        except unittest.SkipTest as skip:
            print("SKIPPED, THE FLOOR UNDER THE SPOTS IS NOT CHECKED HERE: " + str(skip), file=sys.stderr)
            raise
        cls.mesh, cls.walk = nav.ShutDoor("test_the_door_is_what_keeps_a_walker_in").walk(True)

    def test_every_spot_stands_on_one_floor_a_walker_reaches(self):
        spots, _ = live_spots()
        problems = []
        for name, (x, y, z, _) in sorted(spots.items()):
            if name not in ON_THE_PLATFORM | {"platform"}:   # the platform is raised on purpose (its origin is 4.5 yd over the floor) and they stand on it (test below)
                problems += floor_problems(self.mesh, self.walk, name, x, y, z)
        self.assertEqual(problems, [])

    def test_the_obelisk_and_the_keeper_stand_on_the_platform(self):
        """The platform is a decoration (display 7060, size 2.2), so the mesh has no floor for them; they must be inside its footprint and its height."""
        spots, _ = live_spots()
        box = objects.stock_store(objects.STOCK_DIR).decode(7060)
        size = next(r["size"] for r in objects.objects(objects.displays(), objects.OBJECTS, objects.stock_store(objects.STOCK_DIR).rows) if r["name"] == "Platform")
        self.assertEqual(size, 2.2)
        reach = size * max(abs(box[k]) for k in ("GeoBoxMinX", "GeoBoxMinY", "GeoBoxMaxX", "GeoBoxMaxY"))
        px, py, pz, _ = spots["platform"]
        for name in sorted(ON_THE_PLATFORM):
            x, y, z, _ = spots[name]
            self.assertLess(math.dist((x, y), (px, py)), reach, f"{name} is inside the platform's footprint")
            self.assertTrue(pz + size * box["GeoBoxMinZ"] < z < pz + size * box["GeoBoxMaxZ"], f"{name} is inside the platform's height")

    def test_the_check_catches_a_spot_that_floats_sinks_or_stands_on_another_level(self):
        x, y, z, _, _ = READINGS["rift_keeper"]
        self.assertEqual(floor_problems(self.mesh, self.walk, "keeper", x, y, z), [])
        self.assertIn("floats or sinks", floor_problems(self.mesh, self.walk, "keeper high", x, y, z + 3.0)[0])
        self.assertIn("floats or sinks", floor_problems(self.mesh, self.walk, "keeper low", x, y, z - 3.0)[0])
        # the floor 84 yd under the Keeper's spot (a vision chamber's): a walking surface of its own that nobody reaches from the arena
        under = [h for h, key in surfaces(self.mesh, x, y) if key not in self.walk and abs(h - z) < 100]
        self.assertEqual(len(under), 1, "no unreachable level under the Keeper to test with")
        chamber = floor_problems(self.mesh, self.walk, "vision chamber", x, y, under[0])
        self.assertEqual(len(chamber), 1)
        self.assertIn("not reachable", chamber[0])


if __name__ == "__main__":
    unittest.main()

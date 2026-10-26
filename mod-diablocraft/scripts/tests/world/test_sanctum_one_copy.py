"""diablocraft-k4ce: the Sanctum is one shared phase, so its tier 2-10 copies go and nothing else does.

    python3 mod-diablocraft/scripts/tests/world/test_sanctum_one_copy.py        # needs the fixture mysqld (fixture_mysql.sh start)

generate_sanctum_one_copy.py reads world_sanctum_retired_copies.csv (every copy GUID of the old model) and writes the migration that deletes them.
The data is checked against the live sheets (a copy is never a source that stands now), and the migration is applied to a disposable database
on the fixture mysqld that holds the state Torment Development has: every hub thing in map 750 as a phase-1 source plus its nine copies, all
registered, with addon, formation and link rows on the copies, the designer's phase-10 hand rows among them, a registry copy no sheet knows, and the
rows that must survive (the sources and their own rows, a stray phase-1 creature, a copy of another area). Pinned:

  * every retired copy, its addon, formation, link and registry rows are gone; every source, its rows and the other area's copy are untouched;
  * a registry copy the sheet does not know, in the Sanctum, goes with them; the Sanctum's registry ends holding sources only;
  * applying twice changes nothing, and a database that never had the copies is untouched;
  * a copy GUID held by another entry, by a phase-1 row, or registered as a source, and a registry that would not load, stop it before it
    deletes anything (or, for the registry, after, with nothing kept); cutting any delete statement is caught by the closing check.

Limits: the characters database (respawn rows keyed by copy GUIDs) is not touched or modelled; the core's own cleanup of those is read in
docs/test-diablocraft-k4ce.md.
"""
import csv
import json
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
from generate_area_copies import insert  # noqa: E402
from test_hub_sanctum_move import SCRATCH, read, write  # noqa: E402
from test_hub_sanctum_seal import Scratch, csv_door  # noqa: E402

MAP, AREA, OTHER_MAP, OTHER_AREA = 750, 4273, 1, 876
TABLES = ("creature", "gameobject", "creature_addon", "gameobject_addon", "creature_movement_override", "creature_multispawn", "creature_sparring",
          "vehicle_accessory", "creature_formations", "linked_respawn", "dc_area_source", "dc_area_spawn")
STRAY, FOREIGN_COPY, UNKNOWN_COPY = 8000998, 9100001, 9000001   # a phase-1 creature no sheet knows; another area's copy; a Sanctum registry copy no sheet knows


def sources():
    """[(kind, entry, guid, row)] for everything that stands in the Sanctum: the sheet's, the coffer and the door, as rows of their tables."""
    found = []
    for r in read(move.PLACEMENTS):
        placement = json.loads(r["placement"])
        # the sheet leaves a derived rotation null; the stored row has one
        found.append((r["kind"], placement["id"], int(r["source_guid"]), dict({k: 0 if v is None and k.startswith("rotation") else v for k, v in placement.items()}, phaseMask=1)))
    coffer = read(move.COFFER)[0]
    found.append(("c", move.COFFER_ENTRY, int(coffer["source_guid"]), dict(
        guid=int(coffer["source_guid"]), id=move.COFFER_ENTRY, map=MAP, zoneId=AREA, areaId=AREA, spawnMask=1, phaseMask=1, position_x=float(coffer["x"]),
        position_y=float(coffer["y"]), position_z=float(coffer["z"]), orientation=float(coffer["o"]), spawntimesecs=300)))
    door = csv_door()
    found.append(("g", int(door["entry"]), int(door["source_guid"]), dict(
        guid=int(door["source_guid"]), id=int(door["entry"]), map=MAP, zoneId=AREA, areaId=AREA, spawnMask=1, phaseMask=1, position_x=float(door["x"]),
        position_y=float(door["y"]), position_z=float(door["z"]), orientation=float(door["o"]), rotation2=float(door["rotation2"]),
        rotation3=float(door["rotation3"]), spawntimesecs=int(door["spawntimesecs"]), animprogress=int(door["animprogress"]), state=1)))
    return found


def registry(kind, entry, row):
    return insert("dc_area_source", dict(map_id=MAP, area_id=AREA, kind=kind, source_guid=row["guid"], entry=entry, source_phase=1, position_x=row["position_x"],
                                         position_y=row["position_y"], position_z=row["position_z"], orientation=row["orientation"]))


def seed(db, copies=True):
    """Torment Development's state before this migration: the sources and (with `copies`) the old model's nine copies of each, registered."""
    table = move.TABLES
    sql = []
    by_source = {}
    for r in read(one.RETIRED):
        by_source.setdefault((r["kind"], int(r["source_guid"])), []).append((int(r["tier"]), int(r["copy_guid"])))
    for kind, entry, guid, row in sources():
        sql += [insert(table[kind], row), registry(kind, entry, row)]
        if kind == "c":
            sql.append(f"INSERT INTO creature_addon (guid,path_id,mount,bytes1,bytes2,emote,visibilityDistanceType,auras) VALUES ({guid},0,0,0,0,0,0,'');")
        else:
            sql.append(f"INSERT INTO gameobject_addon (guid,invisibilityType,invisibilityValue) VALUES ({guid},0,0);")
        if not copies:
            continue
        for tier, copy in by_source[kind, guid]:
            sql.append(insert(table[kind], dict(row, guid=copy, phaseMask=tier)))
            sql.append(insert("dc_area_spawn", dict(map_id=MAP, area_id=AREA, kind=kind, source_guid=guid, tier=tier, spawn_guid=copy)))
            if kind == "c":
                sql.append(f"INSERT INTO creature_addon (guid,path_id,mount,bytes1,bytes2,emote,visibilityDistanceType,auras) VALUES ({copy},0,0,0,0,0,0,'');")
                sql.append(f"INSERT INTO creature_sparring (GUID,SparringPCT) VALUES ({copy},50);")
            else:
                sql.append(f"INSERT INTO gameobject_addon (guid,invisibilityType,invisibilityValue) VALUES ({copy},0,0);")
    smith, smith_row = next((g, row) for k, e, g, row in sources() if e == 910000)
    mystic = next(g for k, e, g, row in sources() if e == 910001)
    if copies:
        c2, c3 = by_source["c", smith][0][1], by_source["c", mystic][0][1]
        sql += [f"INSERT INTO creature_formations (leaderGUID,memberGUID,dist,angle,groupAI,point_1,point_2) VALUES ({smith},{c2},1,1,0,0,0);",   # source <-> copy
                f"INSERT INTO creature_formations (leaderGUID,memberGUID,dist,angle,groupAI,point_1,point_2) VALUES ({c2},{c3},1,1,0,0,0);",
                f"INSERT INTO linked_respawn (guid,linkedGuid,linkType) VALUES ({c2},{c3},0);"]
        # The designer's hand placement in phase 10 is a copy GUID, unregistered here; and a registry copy no sheet knows (with its creature)
        sql += [insert("creature", dict(smith_row, guid=UNKNOWN_COPY, phaseMask=4)),
                insert("dc_area_spawn", dict(map_id=MAP, area_id=AREA, kind="c", source_guid=8000997, tier=2, spawn_guid=UNKNOWN_COPY))]
    # what must survive: a stray phase-1 creature, another area's copy and its source, and the sources' own formation
    sql += [insert("creature", dict(smith_row, guid=STRAY, map=OTHER_MAP, zoneId=0, areaId=0, phaseMask=1)),
            insert("creature", dict(smith_row, guid=FOREIGN_COPY, map=OTHER_MAP, zoneId=0, areaId=0, phaseMask=2)),
            insert("dc_area_spawn", dict(map_id=OTHER_MAP, area_id=OTHER_AREA, kind="c", source_guid=STRAY, tier=2, spawn_guid=FOREIGN_COPY)),
            insert("dc_area_source", dict(map_id=OTHER_MAP, area_id=OTHER_AREA, kind="c", source_guid=STRAY, entry=910000, source_phase=1, position_x=1, position_y=2,
                                          position_z=3, orientation=0)),
            f"INSERT INTO creature_formations (leaderGUID,memberGUID,dist,angle,groupAI,point_1,point_2) VALUES ({smith},{mystic},1,1,0,0,0);"]
    db.query("\n".join(sql))


def snapshot(db):
    return [sorted(db.query(f"SELECT * FROM `{table}`").splitlines()) for table in TABLES]


class RetiredCopies(unittest.TestCase):
    def test_every_hub_thing_retires_nine_copies_and_no_copy_is_a_source(self):
        copies = one.load()
        live = one.sources_now()
        self.assertEqual(len(live), 26, "the sheet's 24 groups, the coffer and the door")
        self.assertEqual(len(copies), 27 * 9)
        # the book stack's source is off the sheet since diablocraft-jn9l (world_0038 removes it), but world_0037 still retires its copies
        self.assertEqual({(k, s) for k, _, s, _, _ in copies}, set(live) | {("g", 8001491)}, "a retired group for every source that stands, and the old book stack")
        self.assertFalse({(k, c) for k, _, _, _, c in copies} & set(live))

    def test_the_pillar_is_not_here(self):
        self.assertNotIn(910010, {entry for _, entry, _, _, _ in one.load()}, "world_0034 retired the pillar and everything of it")

    def test_a_committed_migration_is_what_the_generator_writes(self):
        name = move.migration_name(move.UPDATES, one.SUFFIX)
        self.assertTrue((move.UPDATES / name).is_file(), f"{name} is not committed")
        sql = one.generate()
        self.assertEqual((move.UPDATES / name).read_text(encoding="utf-8"), sql)
        self.assertEqual((one.ROOT / "data/generated" / name).read_text(encoding="utf-8"), sql, "the data/generated mirror")


class Refusals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.folder = Path(tempfile.mkdtemp(prefix="one-copy-refuse-", dir=SCRATCH))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def refuses(self, label, change):
        rows = read(one.RETIRED)
        change(rows)
        path = self.folder / (re.sub(r"\W+", "_", label) + ".csv")
        write(path, rows)
        with self.assertRaises(ValueError, msg=label):
            one.generate(path)

    def test_data_that_is_not_the_retired_copies_is_refused(self):
        live = sorted(one.sources_now())[0]
        self.refuses("a copy that is a source standing now", lambda rows: rows[0].update(copy_guid=str(live[1]), kind=live[0]))
        self.refuses("a copy retired twice", lambda rows: rows[1].update(copy_guid=rows[0]["copy_guid"]))
        self.refuses("a tier outside 2..N", lambda rows: rows[0].update(tier="11"))
        self.refuses("tier one", lambda rows: rows[0].update(tier="1"))
        self.refuses("a group that lost a tier", lambda rows: rows.pop(0))
        self.refuses("a group with two entries", lambda rows: rows[0].update(entry="910001"))
        self.refuses("an entry that is not the source's", lambda rows: [r.update(entry="31146") for r in rows if r["source_guid"] == rows[0]["source_guid"]])
        self.refuses("a kind that is neither", lambda rows: rows[0].update(kind="x"))
        self.refuses("a copy that is not a number", lambda rows: rows[0].update(copy_guid="abc"))
        self.refuses("a copy past the last guid", lambda rows: rows[0].update(copy_guid=str(2 ** 32)))
        self.refuses("no source note", lambda rows: rows[0].update(source=""))
        self.refuses("an extra column", lambda rows: rows[0].update(extra="x"))
        self.refuses("no rows", lambda rows: rows.clear() or rows.append({}))


class Migration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = one.generate()

    def setUp(self, copies=True):
        self.db = Scratch(TABLES)
        self.addCleanup(self.db.drop)
        seed(self.db, copies)

    def count(self, table, where="1"):
        return int(self.db.query(f"SELECT COUNT(*) FROM {table} WHERE {where}"))

    def retired(self, kind):
        return ",".join(r["copy_guid"] for r in read(one.RETIRED) if r["kind"] == kind)

    def test_every_copy_and_its_rows_go_and_every_source_and_its_rows_stay(self):
        live = sources()
        c_live, g_live = [g for k, _, g, _ in live if k == "c"], [g for k, _, g, _ in live if k == "g"]
        self.assertEqual((self.count("creature"), self.count("gameobject")), (len(c_live) + 90 + 1 + 2, len(g_live) + 144), "the state before: sources, copies, the unknown copy, two strays")
        self.db.query(self.sql)
        for kind, table in (("c", "creature"), ("g", "gameobject")):
            self.assertEqual(self.count(table, f"guid IN ({self.retired(kind)})"), 0, f"every {table} copy is gone")
        self.assertEqual(self.count("creature", f"guid IN ({','.join(map(str, c_live))}) AND phaseMask=1"), len(c_live), "every creature source stands, in phase 1")
        self.assertEqual(self.count("gameobject", f"guid IN ({','.join(map(str, g_live))}) AND phaseMask=1"), len(g_live), "every gameobject source stands")
        self.assertEqual(self.count("creature_addon", f"guid IN ({self.retired('c')})") + self.count("gameobject_addon", f"guid IN ({self.retired('g')})"), 0)
        self.assertEqual(self.count("creature_addon"), len(c_live), "the sources' addon rows stay")
        self.assertEqual(self.count("gameobject_addon"), len(g_live))
        self.assertEqual(self.count("creature_sparring"), 0)
        self.assertEqual(self.count("creature_formations"), 1, "only the formation of two sources stays")
        self.assertEqual(self.count("linked_respawn"), 0)
        self.assertEqual(self.count("dc_area_spawn", f"map_id={MAP} AND area_id={AREA}"), 0, "the Sanctum's registry holds no copy")
        self.assertEqual(self.count("dc_area_source", f"map_id={MAP} AND area_id={AREA}"), len(live), "and every source")
        self.assertEqual(self.count("creature", f"guid={UNKNOWN_COPY}"), 0, "a registry copy no sheet knows goes too")
        # what is not the Sanctum's stays
        self.assertEqual(self.count("creature", f"guid IN ({STRAY},{FOREIGN_COPY})"), 2)
        self.assertEqual(self.count("dc_area_spawn"), 1)
        self.assertEqual((self.count("creature"), self.count("gameobject")), (len(c_live) + 2, len(g_live)), "nothing else went")

    def test_applying_twice_changes_nothing(self):
        self.db.query(self.sql)
        first = snapshot(self.db)
        self.db.query(self.sql)
        self.assertEqual(snapshot(self.db), first)

    def test_a_database_that_never_had_the_copies_is_untouched(self):
        self.setUp(copies=False)
        before = snapshot(self.db)
        self.db.query(self.sql)
        self.assertEqual(snapshot(self.db), before)

    def test_a_row_that_is_not_ours_stops_it_before_it_deletes(self):
        first = read(one.RETIRED)[0]
        copy, table = first["copy_guid"], "creature" if first["kind"] == "c" else "gameobject"
        smith = next(g for k, e, g, _ in sources() if e == 910000)
        other = next(g for k, e, g, _ in sources() if e == 910001)
        cases = {
            "a copy guid held by another entry": f"UPDATE {table} SET id=12345 WHERE guid={copy}",
            "a copy guid held by a phase-1 row (a source)": f"UPDATE {table} SET phaseMask=1 WHERE guid={copy}",
            "a copy guid registered as a source": f"INSERT INTO dc_area_source (map_id,area_id,kind,source_guid,entry,source_phase,position_x,position_y,position_z,orientation) "
                                                  f"VALUES ({OTHER_MAP},{OTHER_AREA},'{first['kind']}',{copy},{first['entry']},1,0,0,0,0)",
            "a Sanctum registry copy that is a source": f"INSERT INTO dc_area_spawn (map_id,area_id,kind,source_guid,tier,spawn_guid) VALUES ({MAP},{AREA},'c',{smith},11,{other})",
        }
        for label, damage in cases.items():
            with self.subTest(label):
                self.db.query(damage)
                before = snapshot(self.db)
                done = self.db.run(self.sql)
                self.assertNotEqual(done.returncode, 0, "the migration went through")
                self.assertRegex(done.stderr, r"ERROR 3819", "it stopped, but not at a guard: " + done.stderr[:200])
                self.assertEqual(snapshot(self.db), before, "it wrote before it stopped")
                self.setUp()

    def test_a_registry_that_would_not_load_stops_it_and_keeps_nothing(self):
        smith = next(g for k, e, g, _ in sources() if e == 910000)
        cases = {
            "a (kind, guid) owned twice, as a source and a copy": f"INSERT INTO dc_area_spawn (map_id,area_id,kind,source_guid,tier,spawn_guid) "
                                                                 f"VALUES ({OTHER_MAP},{OTHER_AREA},'c',{STRAY},3,{smith})",
            "a copy tier past the launch tiers": f"UPDATE dc_area_spawn SET tier=11 WHERE spawn_guid={FOREIGN_COPY}",
        }
        # the first is stopped by the guard before the writes; the second is only caught by the closing check, after every delete, and the
        # rollback keeps nothing
        for label, damage in cases.items():
            with self.subTest(label):
                self.db.query(damage)
                before = snapshot(self.db)
                done = self.db.run(self.sql)
                self.assertNotEqual(done.returncode, 0, "the migration went through")
                self.assertRegex(done.stderr, r"ERROR 3819")
                self.assertEqual(snapshot(self.db), before, "it kept something")
                self.setUp()

    def test_a_delete_that_did_nothing_is_caught_by_the_closing_check(self):
        families = {"the creature copies": r"DELETE s FROM creature s JOIN [^;]*;",
                    "the gameobject copies": r"DELETE s FROM gameobject s JOIN [^;]*;",
                    "the registry's copies": r"DELETE s FROM dc_area_spawn s JOIN [^;]*;",
                    "the registry copy no sheet knows": r"INSERT IGNORE INTO dc_sanctum_retired_copy SELECT[^;]*;"}
        for label, pattern in families.items():
            with self.subTest(label):
                broken = re.sub(pattern, "SELECT 1;", self.sql)
                self.assertNotEqual(broken, self.sql, f"no statement for {label} to remove")
                before = snapshot(self.db)
                done = self.db.run(broken)
                self.assertNotEqual(done.returncode, 0, "the migration went through without " + label)
                self.assertRegex(done.stderr, r"ERROR 3819")
                self.assertEqual(snapshot(self.db), before)
                self.setUp()

    def test_the_migration_deletes_nothing_by_a_range_or_a_whole_table(self):
        self.assertTrue(self.sql.startswith("-- Generated by generate_sanctum_one_copy.py"))
        self.assertEqual(self.sql.count("\nCOMMIT;"), 1)
        self.assertLess(self.sql.index("INSERT INTO dc_sanctum_one_copy_guard"), self.sql.index("DELETE s FROM"))
        for found in re.findall(r"DELETE [^;]*;", self.sql):
            self.assertIn("JOIN dc_sanctum_retired_copy r", found, "every delete goes by the retired list: " + found)


if __name__ == "__main__":
    unittest.main()

"""diablocraft-976b: the Sanctum's door is shut, and nothing a player does opens it. One door in phase 1 (diablocraft-k4ce).

    python3 mod-diablocraft/scripts/tests/world/test_hub_sanctum_seal.py

The hub is Yogg-Saron's arena (map 750, a clone of map 603); its one way out is the arena's own door. The designer's
GM-spawned door (stock entry 194773, flags 32) OPENED when he clicked it. The Sanctum gets its own template of that
door (910019): same look, startOpen off, flags not-selectable + locked on top of the donor's. The core's
GameObject::Use returns at once for a not-selectable object, so a click does nothing.

The migration is applied here to a disposable database on the fixture mysqld (a copy of the live-shaped world
database, never the live one): what it writes, that it is idempotent, and that a foreign row stops it before any write.
The core's own source is read to pin the two facts the flag value rests on.
"""
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import generate_hub_sanctum_seal as seal  # noqa: E402

ROOT = HERE.parents[1]
CORE = ROOT / "azerothcore-wotlk/src/server"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch"
DONOR, ENTRY, STOCK_GUID, MAP, AREA, FIRST = 194773, 910019, 55078, 750, 4273, 8001511
TABLES = ("dc_world_areas", "gameobject_template", "gameobject_template_addon", "gameobject",
          "dc_area_source", "dc_area_spawn", "dc_tier_phase")


class Scratch:
    """A disposable database on the fixture mysqld, with empty tables shaped like the world database's."""

    def __init__(self, tables=TABLES):
        mysql, defaults = fixture_db.mysql_and_defaults([])
        self.argv = [mysql, "--defaults-file=" + str(Path(defaults).resolve()), "--no-login-paths",
                     "--batch", "--skip-column-names"]
        self.name = "dc_976b_" + uuid.uuid4().hex[:10]
        self.query(f"CREATE DATABASE `{self.name}`", database=None)
        for table in tables:
            self.query(f"CREATE TABLE `{table}` LIKE acore_world.`{table}`")

    def run(self, sql, database=True):
        return subprocess.run(self.argv + ([self.name] if database else []), input=sql, text=True,
                              encoding="utf-8", capture_output=True)

    def query(self, sql, database=True):
        done = self.run(sql, database)
        if done.returncode:
            raise AssertionError(done.stderr)
        return done.stdout.strip()

    def drop(self):
        self.run(f"DROP DATABASE IF EXISTS `{self.name}`", database=False)


def core(path):
    return (CORE / path).read_text(encoding="utf-8")


def csv_door():
    with seal.DATA.open(encoding="utf-8", newline="") as stream:
        return next(csv.DictReader(stream))


class SealMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = seal.generate()

    def setUp(self):
        self.db = Scratch()
        self.addCleanup(self.db.drop)
        self.db.query(f"INSERT INTO gameobject_template SELECT * FROM acore_world.gameobject_template WHERE entry={DONOR}")
        self.db.query(f"INSERT INTO gameobject_template_addon SELECT * FROM acore_world.gameobject_template_addon WHERE entry={DONOR}")
        self.db.query("INSERT INTO dc_tier_phase SELECT * FROM acore_world.dc_tier_phase")

    def apply(self):
        self.db.query(self.sql)

    def count(self, source, where="1"):
        return int(self.db.query(f"SELECT COUNT(*) FROM {source} WHERE {where}"))

    def test_the_data_row_is_the_arenas_own_door(self):
        # World places nothing on its own judgement: the position is the stock spawn's, as the stock row stores it.
        row = csv_door()
        near = " AND ".join(f"ABS(`{column}`-{row[key]})<0.0001" for column, key in (
            ("position_x", "x"), ("position_y", "y"), ("position_z", "z"), ("orientation", "o"),
            ("rotation2", "rotation2"), ("rotation3", "rotation3"), ("spawntimesecs", "spawntimesecs"),
            ("animprogress", "animprogress")))
        stock = self.db.query(f"SELECT COUNT(*) FROM acore_world.gameobject WHERE guid={STOCK_GUID} AND id={DONOR} "
                              f"AND map=603 AND rotation0=0 AND rotation1=0 AND {near}", database=None)
        self.assertEqual(stock, "1", "world_sanctum_seal.csv no longer matches the stock door spawn")
        self.assertEqual((int(row["map_id"]), int(row["area_id"]), int(row["donor_entry"]), int(row["entry"])),
                         (MAP, AREA, DONOR, ENTRY))

    def test_the_template_is_the_donors_door_that_cannot_be_clicked(self):
        self.apply()
        donor = self.db.query(f"SELECT type,displayId,size,faction,flags FROM gameobject_template t JOIN gameobject_template_addon a "
                              f"ON a.entry=t.entry WHERE t.entry={DONOR}").split("\t")
        clone = self.db.query(f"SELECT type,displayId,size,faction,flags,name,Data0,AIName='' AND ScriptName='' FROM gameobject_template t "
                              f"JOIN gameobject_template_addon a ON a.entry=t.entry WHERE t.entry={ENTRY}").split("\t")
        self.assertEqual(clone[:4], donor[:4], "same door, same look")
        self.assertEqual(clone[5:], ["Sanctum Door", "0", "1"], "startOpen off, no script, no AI")
        flags = int(clone[4])
        self.assertEqual(flags & 0x10, 0x10, "GO_FLAG_NOT_SELECTABLE: GameObject::Use returns at once")
        self.assertEqual(flags & 0x02, 0x02, "GO_FLAG_LOCKED")
        self.assertEqual(flags & 0x20, 0x20, "the donor's GO_FLAG_NODESPAWN stays")
        # The stock door is left as it was (the designer's own test door used it, and it opens on a click).
        self.assertEqual(int(donor[4]), 0x20)
        self.assertEqual(self.db.query(f"SELECT Data0 FROM gameobject_template WHERE entry={DONOR}"), "1")

    def test_one_door_spawns_shut_in_phase_one(self):
        # the Sanctum is one shared phase (diablocraft-k4ce): one door, not ten
        self.apply()
        row = csv_door()
        rows = self.db.query("SELECT guid,id,map,zoneId,areaId,spawnMask,phaseMask,state,rotation0,rotation1,spawntimesecs,animprogress "
                             "FROM gameobject").splitlines()
        self.assertEqual(len(rows), 1)
        guid, entry, map_id, zone, area, mask, phase, state, r0, r1, respawn, anim = rows[0].split("\t")
        self.assertEqual((int(guid), int(entry), int(map_id), int(zone), int(area), int(mask), int(phase), int(state)),
                         (FIRST, ENTRY, MAP, AREA, AREA, 1, 1, 1))
        self.assertEqual((float(r0), float(r1), int(respawn), int(anim)), (0, 0, int(row["spawntimesecs"]), int(row["animprogress"])))
        self.assertEqual(self.count("gameobject", " AND ".join(
            f"ABS({column}-{row[key]})<0.0001" for column, key in (("position_x", "x"), ("position_y", "y"), ("position_z", "z"),
                                                                    ("orientation", "o"), ("rotation2", "rotation2"), ("rotation3", "rotation3")))), 1)

    def test_the_area_registry_owns_the_door_and_no_copy(self):
        self.apply()
        self.assertEqual(self.db.query("SELECT map_id,area_id,kind,source_guid,entry,source_phase FROM dc_area_source"),
                         f"{MAP}\t{AREA}\tg\t{FIRST}\t{ENTRY}\t1")
        self.assertEqual(self.count("dc_area_spawn"), 0)
        # the registered source is the stored spawn, to the bit (the area copier checks it)
        self.assertEqual(self.count("dc_area_source s JOIN gameobject g ON g.guid=s.source_guid",
                                    "g.id=s.entry AND g.map=s.map_id AND g.position_x=s.position_x AND g.position_y=s.position_y "
                                    "AND g.position_z=s.position_z AND g.orientation=s.orientation"), 1)

    def test_the_hub_area_is_open_on_the_new_map(self):
        self.apply()
        with (seal.AREAS).open(encoding="utf-8", newline="") as stream:
            rule = next(r for r in csv.DictReader(stream) if (r["map_id"], r["area_id"]) == (str(MAP), str(AREA)))
        self.assertEqual(self.db.query("SELECT map_id,area_id,phase_scope,status,note FROM dc_world_areas"),
                         "\t".join((str(MAP), str(AREA), "all", "open", rule["note"])))

    def test_applying_twice_changes_nothing(self):
        self.apply()
        first = [self.db.query(f"SELECT * FROM `{t}` ORDER BY 1,2,3") for t in TABLES]
        self.apply()
        self.assertEqual([self.db.query(f"SELECT * FROM `{t}` ORDER BY 1,2,3") for t in TABLES], first)

    def test_a_foreign_row_stops_the_migration_before_it_writes(self):
        door = f"({{guid}},{{entry}},{MAP},0,0,1,{{phase}},1877.86,-24.1376,335.281,1.5708,0,0,0.707108,0.707106,180,255,1,'',0,NULL)"
        cases = {
            "someone else's gameobject on the door guid": f"INSERT INTO gameobject VALUES {door.format(guid=FIRST, entry=1, phase=1)}",
            "our guid on another map": f"INSERT INTO gameobject VALUES {door.format(guid=FIRST, entry=ENTRY, phase=1)}; "
                                       f"UPDATE gameobject SET map=1 WHERE guid={FIRST}",
            "our guid in the wrong phase": f"INSERT INTO gameobject VALUES {door.format(guid=FIRST, entry=ENTRY, phase=3)}",
            "a foreign template on 910019": f"INSERT INTO gameobject_template (entry,type,displayId,name) VALUES ({ENTRY},5,43,'Stack of Tomes')",
            "the source guid already a copy of another source": f"INSERT INTO dc_area_spawn (map_id,area_id,kind,source_guid,tier,spawn_guid) "
                                                                f"VALUES (530,3703,'g',123,2,{FIRST})",
            "the source guid registered for another entry": f"INSERT INTO dc_area_source (map_id,area_id,kind,source_guid,entry,source_phase,"
                                                            f"position_x,position_y,position_z,orientation) VALUES ({MAP},{AREA},'g',{FIRST},5,1,0,0,0,0)",
            "the donor's addon row gone": f"DELETE FROM gameobject_template_addon WHERE entry={DONOR}",
            "the donor gone": f"DELETE FROM gameobject_template WHERE entry={DONOR}",
            "the donor is not a door": f"UPDATE gameobject_template SET type=5 WHERE entry={DONOR}",
        }
        for label, damage in cases.items():
            with self.subTest(label):
                self.db.query(damage)
                before = [self.db.query(f"SELECT * FROM `{t}` ORDER BY 1,2,3") for t in TABLES]
                done = self.db.run(self.sql)
                self.assertNotEqual(done.returncode, 0, "the migration went through")
                self.assertEqual([self.db.query(f"SELECT * FROM `{t}` ORDER BY 1,2,3") for t in TABLES], before, "it wrote before it stopped")
                self.setUp()  # a fresh database for the next case

    def test_a_template_without_the_flags_is_refused_after_the_write(self):
        # The post-condition guard: if the statement that sets the flags did nothing (here it is cut out), the
        # migration must abort and leave nothing behind, never a door that a click opens.
        broken = re.sub(r"UPDATE dc_sanctum_door_addon SET [^;]*;", "", self.sql)
        self.assertNotEqual(broken, self.sql, "the migration has no flag-setting statement to remove")
        self.assertNotEqual(self.db.run(broken).returncode, 0)
        self.assertEqual(self.count("gameobject_template", f"entry={ENTRY}"), 0)

    def test_the_generator_refuses_a_door_that_would_overwrite_the_stock_one(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        good = csv_door()
        for label, change in {"the donor's own entry": {"entry": str(DONOR)}, "the old hub's map": {"map_id": "530"},
                              "a blank position": {"x": ""}, "no source guid": {"source_guid": ""},
                              "a facing outside the circle": {"o": "7"}}.items():
            with self.subTest(label), tempfile.TemporaryDirectory(prefix="seal-refuse-", dir=SCRATCH) as folder:
                path = Path(folder) / "world_sanctum_seal.csv"
                with path.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(good), lineterminator="\n")
                    writer.writeheader()
                    writer.writerow(dict(good, **change))
                with self.assertRaises(ValueError):
                    seal.generate(path)
        # An open rule that is not the hub's is no reason to stand the door there (the points sheet names the hub).
        with self.subTest("an open area that is not the hub's"), tempfile.TemporaryDirectory(prefix="seal-refuse-", dir=SCRATCH) as folder:
            path, areas = Path(folder) / "world_sanctum_seal.csv", Path(folder) / "world_areas.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(good), lineterminator="\n")
                writer.writeheader()
                writer.writerow(dict(good, area_id="9999"))
            areas.write_text(f"map_id,area_id,phase_scope,status,note\n{MAP},9999,all,open,not the hub\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                seal.generate(path, areas)


class CoreFacts(unittest.TestCase):
    """The two things the door's flag value stands on, read from the pinned core (never built or run here)."""

    def test_flag_values(self):
        shared = core("shared/SharedDefines.h")
        values = {name: int(value, 16) for name, value in re.findall(r"\b(GO_FLAG_\w+)\s*=\s*(0x[0-9A-Fa-f]+)", shared)}
        self.assertEqual((values["GO_FLAG_LOCKED"], values["GO_FLAG_NOT_SELECTABLE"], values["GO_FLAG_NODESPAWN"]), (0x02, 0x10, 0x20))
        self.assertEqual(seal.CLOSED_FLAGS, values["GO_FLAG_LOCKED"] | values["GO_FLAG_NOT_SELECTABLE"])

    def test_use_returns_before_anything_else_for_a_not_selectable_object(self):
        text = core("game/Entities/GameObject/GameObject.cpp")
        body = text.split("void GameObject::Use(Unit* user)\n{", 1)[1]
        first = re.match(r"\s*(//[^\n]*\n\s*)?if \(HasGameObjectFlag\(GO_FLAG_NOT_SELECTABLE\)\)\s*return;", body)
        self.assertIsNotNone(first, "GameObject::Use no longer begins with the not-selectable return")


if __name__ == "__main__":
    unittest.main()

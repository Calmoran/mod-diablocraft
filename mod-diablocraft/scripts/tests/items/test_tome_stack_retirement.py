"""diablocraft-jn9l: world_0038 removes the Tome's book stack spawn (910017) everywhere, keeps its template, and nothing else.

    python3 mod-diablocraft/scripts/tests/items/test_tome_stack_retirement.py        # needs the fixture mysqld (fixture_mysql.sh start)

Pinned: the migration and its data/generated mirror are the render; applied to a disposable database seeded with every
910017 spawn and registry row the fixture's acore_world holds (the old hub's stack and its tier copies, left by the frozen
migrations) plus a spawn addon, it leaves no spawn, addon or registry row of the entry, keeps the template and the Tome
(910016) with its registry untouched, and a second apply changes nothing. Each DELETE dropped from the render leaves rows
behind (single-rule mutants, run in the suite).
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_tome_stack_retirement as retire  # noqa: E402
from test_hub_sanctum_seal import Scratch  # noqa: E402

MODULE = HERE.parent
STACK, TOME = 910017, 910016
TABLES = ("gameobject", "gameobject_addon", "gameobject_template", "dc_area_source", "dc_area_spawn")


def leftovers(db):
    return {
        "gameobject": db.query(f"SELECT COUNT(*) FROM gameobject WHERE id={STACK}"),
        "gameobject_addon": db.query("SELECT COUNT(*) FROM gameobject_addon WHERE guid IN (8001491, 8001493)"),
        "dc_area_source": db.query(f"SELECT COUNT(*) FROM dc_area_source WHERE entry={STACK}"),
        "dc_area_spawn": db.query("SELECT COUNT(*) FROM dc_area_spawn WHERE kind='g' AND source_guid=8001491"),
    }


class TomeStackRetirement(unittest.TestCase):
    def setUp(self):
        self.db = Scratch(TABLES)
        self.addCleanup(self.db.drop)
        q = self.db.query
        ids = f"{STACK},{TOME}"
        q(f"INSERT INTO gameobject SELECT * FROM acore_world.gameobject WHERE id IN ({ids})")
        q(f"INSERT INTO gameobject_template SELECT * FROM acore_world.gameobject_template WHERE entry IN ({ids})")
        # the fixture holds the stack's old-hub spawn but no registry: seed the source and one tier copy the way world_0023 left them
        q("INSERT INTO gameobject SELECT 8001493, id, map, zoneId, areaId, spawnMask, 2, position_x, position_y, position_z, orientation, "
          "rotation0, rotation1, rotation2, rotation3, spawntimesecs, animprogress, state, ScriptName, VerifiedBuild, Comment "
          "FROM acore_world.gameobject WHERE guid=8001491")
        q(f"INSERT INTO dc_area_source (map_id, area_id, kind, source_guid, entry, source_phase, position_x, position_y, position_z, orientation) "
          f"SELECT map, areaId, 'g', guid, id, 1, position_x, position_y, position_z, orientation FROM gameobject WHERE guid=8001491")
        q("INSERT INTO dc_area_spawn (map_id, area_id, kind, source_guid, tier, spawn_guid) SELECT map_id, area_id, kind, source_guid, 2, 8001493 FROM dc_area_source")
        q(f"INSERT INTO dc_area_source SELECT * FROM acore_world.dc_area_source WHERE kind='g' AND entry={TOME}")
        q("INSERT INTO gameobject_addon (guid) VALUES (8001491), (8001493)")
        before = leftovers(self.db)
        # The seed must hold every kind of row the migration removes, or a green run proves nothing.
        self.assertTrue(all(int(n) > 0 for n in before.values()), before)
        self.tome = self.tome_rows()

    def tome_rows(self):
        q = self.db.query
        return (q(f"SELECT * FROM gameobject WHERE id={TOME} ORDER BY guid"),
                q(f"SELECT * FROM gameobject_template WHERE entry IN ({STACK},{TOME}) ORDER BY entry"),
                q(f"SELECT * FROM dc_area_source WHERE entry={TOME} ORDER BY source_guid"))

    def test_migration_and_mirror_are_the_render(self):
        sql = retire.render()
        for path in (MODULE / "data/sql/db-world/updates" / retire.NAME, MODULE / "data/generated" / retire.NAME):
            self.assertEqual(path.read_text(encoding="utf-8"), sql, path)

    def test_removes_every_stack_spawn_and_keeps_the_template(self):
        self.db.query(retire.render())
        self.assertEqual(leftovers(self.db), {table: "0" for table in leftovers(self.db)})
        self.assertEqual(self.tome_rows(), self.tome)   # the Tome and both templates stand
        self.db.query(retire.render())   # a rerun finds nothing and fails on nothing
        self.assertEqual(self.tome_rows(), self.tome)

    def test_each_delete_is_needed(self):
        lines = retire.render().splitlines()
        deletes = [i for i, line in enumerate(lines) if line.startswith("DELETE")]
        self.assertEqual(len(deletes), 4)
        for i in deletes:
            db = Scratch(TABLES)
            try:
                for table in TABLES:
                    db.query(f"INSERT INTO `{table}` SELECT * FROM `{self.db.name}`.`{table}`")
                db.query("\n".join(lines[:i] + lines[i + 1:]))
                self.assertNotEqual(leftovers(db), {t: "0" for t in leftovers(db)}, lines[i])
            finally:
                db.drop()


if __name__ == "__main__":
    unittest.main()

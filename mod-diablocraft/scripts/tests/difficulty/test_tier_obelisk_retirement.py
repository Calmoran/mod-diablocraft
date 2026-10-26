"""diablocraft-fjqx: world_0034 removes the hub's difficulty obelisk (910010) everywhere, and nothing else.

    python3 mod-diablocraft/scripts/tests/difficulty/test_tier_obelisk_retirement.py        # needs the fixture mysqld (fixture_mysql.sh start)

Pinned: the migration and its data/generated mirror are the render; applied to a disposable database seeded with
every 910010 row the fixture's acore_world holds (the GM-island and Scryer-era spawns and their tier-copy registry,
left by the frozen migrations) plus a spawn addon, template addon and locale row, it leaves no row of the entry in
any table, keeps the Rift Obelisk (910011) and its registry untouched, and a second apply changes nothing. Each
DELETE dropped from the render leaves rows behind (single-rule mutants, run in the suite).
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_tier_obelisk_retirement as retire  # noqa: E402
from test_hub_sanctum_seal import Scratch  # noqa: E402

MODULE = HERE.parent
OBELISK, RIFT = 910010, 910011
TABLES = ("gameobject", "gameobject_addon", "gameobject_template", "gameobject_template_addon",
          "gameobject_template_locale", "dc_area_source", "dc_area_spawn")


def leftovers(db):
    spawns = f"SELECT guid FROM gameobject WHERE id={OBELISK}"
    return {
        "gameobject": db.query(f"SELECT COUNT(*) FROM gameobject WHERE id={OBELISK}"),
        "gameobject_addon": db.query("SELECT COUNT(*) FROM gameobject_addon WHERE guid IN (8000000, 8001468)"),
        "gameobject_template": db.query(f"SELECT COUNT(*) FROM gameobject_template WHERE entry={OBELISK}"),
        "gameobject_template_addon": db.query(f"SELECT COUNT(*) FROM gameobject_template_addon WHERE entry={OBELISK}"),
        "gameobject_template_locale": db.query(f"SELECT COUNT(*) FROM gameobject_template_locale WHERE entry={OBELISK}"),
        "dc_area_source": db.query(f"SELECT COUNT(*) FROM dc_area_source WHERE entry={OBELISK}"),
        "dc_area_spawn": db.query("SELECT COUNT(*) FROM dc_area_spawn WHERE kind='g' AND source_guid IN (8000000, 8001468)"),
    }


class ObeliskRetirement(unittest.TestCase):
    def setUp(self):
        self.db = Scratch(TABLES)
        self.addCleanup(self.db.drop)
        q = self.db.query
        ids = f"{OBELISK},{RIFT}"
        q(f"INSERT INTO gameobject SELECT * FROM acore_world.gameobject WHERE id IN ({ids})")
        q(f"INSERT INTO gameobject_template SELECT * FROM acore_world.gameobject_template WHERE entry IN ({ids})")
        q(f"INSERT INTO dc_area_source SELECT * FROM acore_world.dc_area_source WHERE kind='g' AND entry IN ({ids})")
        q("INSERT INTO dc_area_spawn SELECT s.* FROM acore_world.dc_area_spawn s JOIN acore_world.dc_area_source src "
          f"USING (map_id, area_id, kind, source_guid) WHERE s.kind='g' AND src.entry IN ({ids})")
        q("INSERT INTO gameobject_addon (guid) VALUES (8000000), (8001468)")
        q(f"INSERT INTO gameobject_template_addon (entry) VALUES ({OBELISK})")
        q(f"INSERT INTO gameobject_template_locale (entry, locale, name) VALUES ({OBELISK}, 'deDE', 'Schwierigkeit')")
        before = leftovers(self.db)
        # The seed must hold every kind of row the migration removes, or a green run proves nothing.
        self.assertTrue(all(int(n) > 0 for n in before.values()), before)
        self.rift = self.rift_rows()
        self.assertNotEqual(self.rift[0], "")

    def rift_rows(self):
        q = self.db.query
        return (q(f"SELECT * FROM gameobject WHERE id={RIFT} ORDER BY guid"),
                q(f"SELECT * FROM gameobject_template WHERE entry={RIFT}"),
                q(f"SELECT * FROM dc_area_source WHERE entry={RIFT} ORDER BY source_guid"),
                q(f"SELECT s.* FROM dc_area_spawn s JOIN dc_area_source src USING (map_id, area_id, kind, source_guid) "
                  f"WHERE src.entry={RIFT} ORDER BY s.spawn_guid"))

    def test_migration_and_mirror_are_the_render(self):
        sql = retire.render()
        for path in (MODULE / "data/sql/db-world/updates" / retire.NAME, MODULE / "data/generated" / retire.NAME):
            self.assertEqual(path.read_text(encoding="utf-8"), sql, path)

    def test_removes_every_obelisk_row_and_nothing_else(self):
        self.db.query(retire.render())
        self.assertEqual(leftovers(self.db), {table: "0" for table in TABLES})
        self.assertEqual(self.rift_rows(), self.rift)
        self.db.query(retire.render())   # a rerun finds nothing and fails on nothing
        self.assertEqual(self.rift_rows(), self.rift)

    def test_each_delete_is_needed(self):
        lines = retire.render().splitlines()
        deletes = [i for i, line in enumerate(lines) if line.startswith("DELETE")]
        self.assertEqual(len(deletes), 7)
        for i in deletes:
            db = Scratch(TABLES)
            try:
                for table in TABLES:
                    db.query(f"INSERT INTO `{table}` SELECT * FROM `{self.db.name}`.`{table}`")
                db.query("\n".join(lines[:i] + lines[i + 1:]))
                self.assertNotEqual(leftovers(db), {t: "0" for t in TABLES}, lines[i])
            finally:
                db.drop()


if __name__ == "__main__":
    unittest.main()

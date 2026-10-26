"""diablocraft-nw0w: dc_legendary_gem and dc_legendary_gem_item join on gem_id with no COLLATE.

    python3 mod-diablocraft/scripts/tests/legendaries/test_legendary_gem_collation.py        # needs the fixture mysqld (fixture_mysql.sh start)

legendary_gems_0001 (live since update 8) names no collation, so on a database whose default is not utf8mb4_unicode_ci the
table differs from dc_legendary_gem_item's. legendary_gems_0004_collation converts it. Run on a disposable database whose
default is utf8mb4_0900_ai_ci (the fixture's, and MySQL 8's): the bare join and the .dc gem list's query (read out of dc_items.cpp) raise error 1267 after 0001 and 0002
alone (the test sees the bug), and run after 0004, which also keeps the rows and runs twice.
"""
import unittest
import uuid
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crafting_queries import cpp_queries
from test_hub_sanctum_seal import Scratch

ROOT = Path(__file__).resolve().parents[3]
UPDATES = ROOT / "data/sql/db-world/updates"
# the one production bare join: the .dc gem list in dc_items.cpp, read out of the source
(LIST,) = [q for q in cpp_queries((ROOT / "src/items/dc_items.cpp").read_text(encoding="utf-8"))
           if "JOIN dc_legendary_gem g" in q]
JOIN = "SELECT COUNT(*) FROM dc_legendary_gem g JOIN dc_legendary_gem_item i ON i.gem_id = g.gem_id"


class GemCollation(unittest.TestCase):
    def setUp(self):
        self.db = Scratch(tables=())
        self.addCleanup(self.db.drop)
        self.db.query(f"ALTER DATABASE `{self.db.name}` COLLATE utf8mb4_0900_ai_ci", database=None)
        for name in ("legendary_gems_0001", "legendary_gems_0002_items"):
            sql = (UPDATES / f"{name}.sql").read_text(encoding="utf-8")
            # 0002 also writes item_template rows; only its dc_legendary_gem_item table matters here
            self.db.query("\n".join(line for line in sql.splitlines() if "item_template" not in line
                                    and "dc_legendary_gem_template" not in line))

    def migrate(self):
        self.db.query((UPDATES / "legendary_gems_0004_collation.sql").read_text(encoding="utf-8"))

    def test_bare_join_fails_before_and_runs_after(self):
        for query in (JOIN, LIST):
            before = self.db.run(query)
            self.assertNotEqual(before.returncode, 0)
            self.assertIn("1267", before.stderr)
        rows = self.db.query("SELECT COUNT(*) FROM dc_legendary_gem")
        self.migrate()
        self.assertEqual(self.db.query("SELECT COUNT(*) FROM dc_legendary_gem"), rows)
        joined = self.db.query(JOIN)
        self.assertGreater(int(joined), 0)
        self.assertGreater(len(self.db.query(LIST).splitlines()), 0)

    def test_twice_is_harmless(self):
        self.migrate()
        self.migrate()
        self.assertGreater(int(self.db.query(JOIN)), 0)
        self.assertGreater(len(self.db.query(LIST).splitlines()), 0)


if __name__ == "__main__":
    unittest.main()

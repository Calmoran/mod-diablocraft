#!/usr/bin/env python3
"""A fresh characters DB must build from the core's base schema plus our updates (diablocraft-fresh-chars-migration-order).

The core updater applies db-characters/updates in filename order. A live DB grew one
migration at a time, so an ordering fault (an ALTER sorting before the CREATE it needs)
never showed there; an empty realm (Horadrim, the wipe, CI) hits it on the first start.
This test does what a first start does, in a scratch database on the fixture mysqld, and
fails naming the migration and the error. Without the fixture it is skipped.
"""
import re
import subprocess
import unittest
import uuid
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db

MODULE = Path(__file__).resolve().parents[3]
UPDATES = MODULE / "data/sql/db-characters/updates"


def core_base():
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=MODULE,
                            capture_output=True, text=True, check=True).stdout.strip()
    return sorted((Path(common).parent / "azerothcore-wotlk/data/sql/base/db_characters").glob("*.sql"))


class FreshCharactersDb(unittest.TestCase):
    def mysql(self, *args, stdin=None):
        return subprocess.run([fixture_db.mysql_exe(), "--defaults-file=" + str(fixture_db.defaults_file()),
                               "--no-login-paths", *args], input=stdin, capture_output=True, text=True)

    def test_updates_apply_in_updater_order_on_an_empty_database(self):
        if self.mysql("-e", "SELECT 1").returncode != 0:
            self.skipTest("the fixture mysqld is down (fixture_mysql.sh start)")
        base = core_base()
        self.assertTrue(base, "the core's base characters schema was not found")
        db = "fresh_chars_" + uuid.uuid4().hex[:10]
        self.assertEqual(self.mysql("-e", f"CREATE DATABASE {db}").returncode, 0)
        try:
            for path in base:
                result = self.mysql(db, stdin=path.read_text(encoding="utf-8"))
                self.assertEqual(result.returncode, 0, f"{path.name}: {result.stderr}")
            files = sorted(UPDATES.glob("*.sql"), key=lambda p: p.name)  # the core's own comparison
            self.assertTrue(files)
            for path in files:
                result = self.mysql(db, stdin=path.read_text(encoding="utf-8"))
                self.assertEqual(result.returncode, 0,
                                 f"{path.name} fails on a fresh characters DB (a migration it needs sorts later): {result.stderr.strip()}")
        finally:
            self.mysql("-e", f"DROP DATABASE IF EXISTS {db}")


    def test_the_weapon_damage_columns_round_trip_and_the_alter_is_idempotent(self):
        """G1: dc_item_affix's two-part columns exist on a fresh DB, a two-part row round-trips
        through them, and re-running the guarded ALTER changes nothing."""
        if self.mysql("-e", "SELECT 1").returncode != 0:
            self.skipTest("the fixture mysqld is down (fixture_mysql.sh start)")
        migration = UPDATES / "items_0006_weapon_damage.sql"
        self.assertTrue(migration.exists(), "the G1 characters migration is missing")
        db = "g1_weapon_damage_" + uuid.uuid4().hex[:10]
        self.assertEqual(self.mysql("-e", f"CREATE DATABASE {db}").returncode, 0)
        try:
            for name in ("items_0001_item_instance.sql", "items_0002_item_affix.sql",
                         "items_crafting_0001_artisans.sql", migration.name):
                path = UPDATES / name
                result = self.mysql(db, stdin=path.read_text(encoding="utf-8"))
                self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")
                if name == migration.name:
                    again = self.mysql(db, stdin=path.read_text(encoding="utf-8"))
                    self.assertEqual(again.returncode, 0, f"{name} is not idempotent: {again.stderr}")
            columns = self.mysql(db, "-N", "-B", "-e",
                                 "SELECT column_name FROM information_schema.columns "
                                 "WHERE table_schema=DATABASE() AND table_name='dc_item_affix' "
                                 "AND column_name IN ('value2','range_min2','range_max2') ORDER BY column_name")
            self.assertEqual(columns.stdout.split(), ["range_max2", "range_min2", "value2"])
            insert = ("INSERT INTO dc_item_affix(item_guid,seq,affix_id,value,range_min,range_max,"
                      "value2,range_min2,range_max2,kind,rerolled) "
                      "VALUES(1,1,'wpnfir',981,981,1199,1490,1175,1490,'preset',0)")
            self.assertEqual(self.mysql(db, "-e", insert).returncode, 0)
            row = self.mysql(db, "-N", "-B", "-e", "SELECT value,range_min,range_max,value2,range_min2,"
                                                   "range_max2 FROM dc_item_affix WHERE item_guid=1")
            values = row.stdout.split()
            self.assertEqual(values, ["981", "981", "1199", "1490", "1175", "1490"])
            # The stored pair keeps the rolled invariant: value2 (the max) above value (the min).
            self.assertGreater(float(values[3]), float(values[0]))
        finally:
            self.mysql("-e", f"DROP DATABASE IF EXISTS {db}")

    def test_every_affix_kind_the_cpp_writes_is_stored_in_strict_mode(self):
        """diablocraft-obdh9: the C++ stored kind 'power' that dc_item_affix's ENUM refused (errno 1265),
        which failed the account operation and kicked the player. Every kind literal the items and
        crafting code writes or compares must insert on a fresh DB built from every update."""
        if self.mysql("-e", "SELECT 1").returncode != 0:
            self.skipTest("the fixture mysqld is down (fixture_mysql.sh start)")
        source = "".join(p.read_text(encoding="utf-8") for d in ("src/items", "src/crafting")
                         for p in sorted((MODULE / d).glob("*.[ch]*")))
        # A Cube recipe line's kind (spend, make, take) is not an affix kind: leave `line.kind` out.
        kinds = set(re.findall(r'(?<!line)\.kind\s*[!=]=\s*"(\w+)"', source))
        kinds |= set(re.findall(r'fill\(\w+,[^;]*?"(\w+)"\)', source))
        kinds |= set(re.findall(r"kind\s*=\s*'(\w+)'", source))
        kinds |= set(re.findall(r"INSERT INTO dc_item_affix[^;]*?'(\w+)',\s*0", source))
        self.assertTrue({"primary", "secondary", "socket", "gem", "power"} <= kinds, f"the source scan broke: {kinds}")
        db = "affix_kinds_" + uuid.uuid4().hex[:10]
        self.assertEqual(self.mysql("-e", f"CREATE DATABASE {db}").returncode, 0)
        try:
            for path in core_base() + sorted(UPDATES.glob("*.sql"), key=lambda p: p.name):
                result = self.mysql(db, stdin=path.read_text(encoding="utf-8"))
                self.assertEqual(result.returncode, 0, f"{path.name}: {result.stderr}")
            for seq, kind in enumerate(sorted(kinds)):
                result = self.mysql(db, "-e", "SET SESSION sql_mode='STRICT_TRANS_TABLES'; "
                                    f"INSERT INTO dc_item_affix(item_guid,seq,affix_id,kind) VALUES(1,{seq},'x','{kind}')")
                self.assertEqual(result.returncode, 0, f"kind '{kind}' does not fit dc_item_affix.kind: {result.stderr.strip()}")
        finally:
            self.mysql("-e", f"DROP DATABASE IF EXISTS {db}")


if __name__ == "__main__":
    unittest.main()

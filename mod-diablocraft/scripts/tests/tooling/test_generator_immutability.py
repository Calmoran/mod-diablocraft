"""Fixture tests for the applied-state guard and the deploy-time manifest tool.

No database and no live server: the refresh tool is driven from an evidence CSV
and a temporary repository, so the whole contract is exercised offline.
"""

import argparse
import contextlib
import csv
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import applied_migrations as am
import generate_tier_unlocks
import refresh_applied_migrations as refresh

REAL_MODULE = pathlib.Path(__file__).resolve().parents[3]


def write_manifest(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["path", "sha1", "provenance"])
        for row in rows:
            writer.writerow(row)


class AppliedGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.updates = self.root / "data/sql/db-world/updates"
        self.updates.mkdir(parents=True)
        self.applied = self.updates / "0001_dc_thing.sql"
        self.applied.write_text("SELECT 1;\n", encoding="utf-8")
        write_manifest(self.root / "data/sql/applied_migrations.csv",
                       [["db-world/updates/0001_dc_thing.sql", am.sha1(b"SELECT 1;\n"), "test"]])

    def test_listed_and_identical_is_a_silent_no_op(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            wrote = am.write_migration(self.root, self.applied, "SELECT 1;\n")
        self.assertFalse(wrote)
        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(self.applied.read_text(encoding="utf-8"), "SELECT 1;\n")

    def test_listed_and_different_leaves_the_file_and_warns(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            wrote = am.write_migration(self.root, self.applied, "SELECT 2;\n")
        self.assertFalse(wrote)
        self.assertEqual(self.applied.read_text(encoding="utf-8"), "SELECT 1;\n")
        self.assertIn("0001_dc_thing.sql", buffer.getvalue())
        self.assertIn("WARNING", buffer.getvalue())

    def test_unlisted_path_regenerates(self):
        target = self.updates / "0002_dc_thing.sql"
        wrote = am.write_migration(self.root, target, "SELECT 3;\n")
        self.assertTrue(wrote)
        self.assertEqual(target.read_text(encoding="utf-8"), "SELECT 3;\n")

    def test_is_applied_matches_the_manifest(self):
        self.assertTrue(am.is_applied(self.root, self.applied))
        self.assertFalse(am.is_applied(self.root, self.updates / "0009_dc_other.sql"))

    def test_absolute_and_relative_targets_resolve_the_same_key(self):
        self.assertEqual(am.manifest_key(self.root, self.applied),
                         am.manifest_key(self.root, "data/sql/db-world/updates/0001_dc_thing.sql"))

    def test_missing_manifest_fails_closed(self):
        bare = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        target = bare / "data/sql/db-world/updates/0001_dc_x.sql"
        with self.assertRaises(am.AppliedStateError) as caught:
            am.write_migration(bare, target, "SELECT 1;\n")
        self.assertIn("missing", str(caught.exception))
        self.assertFalse(target.exists())
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(bare)

    def test_malformed_manifest_fails_closed(self):
        bare = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        manifest = bare / "data/sql/applied_migrations.csv"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("not_path,not_sha1\nx,y\n", encoding="utf-8")
        target = bare / "data/sql/db-world/updates/0001_dc_x.sql"
        with self.assertRaises(am.AppliedStateError) as caught:
            am.write_migration(bare, target, "SELECT 1;\n")
        self.assertIn("path", str(caught.exception))
        self.assertFalse(target.exists())

    def test_unreadable_manifest_fails_closed(self):
        bare = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        (bare / "data/sql/applied_migrations.csv").mkdir(parents=True)
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(bare)

    def _manifest(self, text):
        bare = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        manifest = bare / "data/sql/applied_migrations.csv"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(text, encoding="utf-8")
        return bare

    def test_zero_byte_manifest_fails_closed(self):
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(self._manifest(""))

    def test_wrong_header_manifest_fails_closed(self):
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(self._manifest("sha1,path,provenance\n"))

    def test_malformed_sha1_fails_closed(self):
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(self._manifest(
                "path,sha1,provenance\ndb-world/updates/x.sql,not-a-sha1,p\n"))

    def test_blank_field_fails_closed(self):
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(self._manifest("path,sha1,provenance\n,,\n"))

    def test_header_only_manifest_is_an_empty_authority(self):
        self.assertEqual(am.load_manifest(self._manifest("path,sha1,provenance\n")), {})


class DevAppliedGuard(unittest.TestCase):
    """applied_migrations_dev.csv: a file dev applied before live is frozen like a live one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.updates = self.root / "data/sql/db-world/updates"
        self.updates.mkdir(parents=True)
        self.on_dev = self.updates / "0002_dc_dev.sql"
        self.on_dev.write_text("SELECT 2;\n", encoding="utf-8")
        write_manifest(self.root / "data/sql/applied_migrations.csv",
                       [["db-world/updates/0001_dc_live.sql", am.sha1(b"SELECT 1;\n"), "live"]])
        self.dev = self.root / "data/sql/applied_migrations_dev.csv"
        write_manifest(self.dev, [["db-world/updates/0002_dc_dev.sql", am.sha1(b"SELECT 2;\n"), "dev"]])

    def test_a_file_only_dev_applied_is_frozen(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            wrote = am.write_migration(self.root, self.on_dev, "SELECT 22;\n")
        self.assertFalse(wrote)
        self.assertEqual(self.on_dev.read_text(encoding="utf-8"), "SELECT 2;\n")
        self.assertIn("WARNING", buffer.getvalue())
        self.assertTrue(am.is_applied(self.root, self.on_dev))

    def test_without_a_dev_manifest_only_live_rows_are_applied(self):
        self.dev.unlink()
        self.assertTrue(am.write_migration(self.root, self.on_dev, "SELECT 22;\n"))
        self.assertTrue(am.is_applied(self.root, self.updates / "0001_dc_live.sql"))

    def test_a_malformed_dev_manifest_fails_closed(self):
        self.dev.write_text("path,sha1\n", encoding="utf-8")
        with self.assertRaises(am.AppliedStateError):
            am.write_migration(self.root, self.on_dev, "SELECT 22;\n")
        self.assertEqual(self.on_dev.read_text(encoding="utf-8"), "SELECT 2;\n")

    def test_dev_and_live_disagreeing_on_a_hash_fails_closed(self):
        write_manifest(self.dev, [["db-world/updates/0001_dc_live.sql", am.sha1(b"SELECT 9;\n"), "dev"]])
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(self.root)


class ReservedRows(unittest.TestCase):
    """A branch's migration dev applied has a reserved row in the dev manifest (diablocraft-2kmef): the path,
    no hash. Its number is taken for every generator that picks one; nothing is frozen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "data/sql/db-world/updates").mkdir(parents=True)
        write_manifest(self.root / "data/sql/applied_migrations.csv", [])
        self.dev = self.root / "data/sql/applied_migrations_dev.csv"

    def reserve(self, *names, provenance="reserved on dev, branch: confirmed against the dev updates table"):
        write_manifest(self.dev, [[f"db-world/updates/{name}", "", provenance] for name in names])

    def test_a_reserved_row_is_read_without_freezing_anything(self):
        self.reserve("tunables_0015.sql")
        self.assertEqual(am.load_manifest(self.root), {})
        self.assertEqual(am.load_reserved(self.root), {"db-world/updates/tunables_0015.sql"})
        target = self.root / "data/sql/db-world/updates/tunables_0015.sql"
        self.assertFalse(am.is_applied(self.root, target))
        self.assertTrue(am.write_migration(self.root, target, "SELECT 1;\n"))   # the branch's own worktree may write it

    def test_the_highest_reserved_number_is_per_series(self):
        self.reserve("tunables_0015.sql", "tunables_0012.sql", "world_0070_x.sql", "items_0050_x.sql")
        self.assertEqual(am.reserved_number(self.root, "tunables"), 15)
        self.assertEqual(am.reserved_number(self.root, "world"), 70)
        self.assertEqual(am.reserved_number(self.root, "items"), 50)
        self.assertEqual(am.reserved_number(self.root, "crafting"), 0)
        self.assertEqual(am.reserved_number(self.root, "item"), 0)    # a prefix, not a substring

    def test_without_a_dev_manifest_nothing_is_reserved(self):
        self.assertEqual(am.reserved_number(self.root, "tunables"), 0)

    def test_a_row_applied_after_the_branch_landed_is_not_reserved_any_more(self):
        write_manifest(self.dev, [["db-world/updates/tunables_0015.sql", "", "reserved on dev, branch: a"],
                                  ["db-world/updates/tunables_0015.sql", am.sha1(b"x"), "dev"]])
        self.assertEqual(am.load_reserved(self.root), set())

    def test_a_blank_hash_needs_the_reserved_provenance(self):
        self.reserve("tunables_0015.sql", provenance="confirmed against the dev updates table")
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(self.root)

    def test_the_live_manifest_takes_no_reserved_row(self):
        write_manifest(self.root / "data/sql/applied_migrations.csv",
                       [["db-world/updates/tunables_0015.sql", "", "reserved on dev, branch: a"]])
        with self.assertRaises(am.AppliedStateError):
            am.load_manifest(self.root)


class CoupledOutputs(unittest.TestCase):
    """A companion output may follow a changed sheet only with a new migration.

    decisions.md 2026-09-23 (F2): when a run changes a companion output while
    its matching applied migration stayed frozen and no new migration covers
    it, the generator flags it. The gate lives in `write_coupled_outputs`.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.updates = self.root / "data/sql/db-world/updates"
        self.updates.mkdir(parents=True)
        self.migration = self.updates / "0001_dc_thing.sql"
        self.migration.write_text("SELECT 1;\n", encoding="utf-8")
        self.header = self.root / "src/dc_thing_data.h"
        self.header.parent.mkdir(parents=True)
        self.header.write_text("// v1\n", encoding="utf-8")
        write_manifest(self.root / "data/sql/applied_migrations.csv",
                       [["db-world/updates/0001_dc_thing.sql",
                         am.sha1(b"SELECT 1;\n"), "test"]])

    def publish(self, migration_content, header_content, *, migration=None, outputs=None):
        target = migration or self.migration
        if outputs is None:
            outputs = [(self.header, header_content)]
        return am.write_coupled_outputs(self.root, target, migration_content, outputs,
                                        label="test companion")

    def test_state_new_for_an_unlisted_migration(self):
        self.assertEqual(
            am.migration_state(self.root, self.updates / "0002_dc_x.sql", "SELECT 2;\n"),
            am.MIGRATION_NEW)

    def test_state_unchanged_when_the_render_matches(self):
        self.assertEqual(am.migration_state(self.root, self.migration, b"SELECT 1;\n"),
                         am.MIGRATION_UNCHANGED)

    def test_state_frozen_when_the_render_differs(self):
        self.assertEqual(am.migration_state(self.root, self.migration, b"SELECT 2;\n"),
                         am.MIGRATION_FROZEN)

    def test_new_migration_publishes_the_companion(self):
        wrote = self.publish("SELECT 9;\n", "// v2\n",
                             migration=self.updates / "0002_dc_thing.sql")
        self.assertTrue(wrote)
        self.assertEqual(self.header.read_text(encoding="utf-8"), "// v2\n")

    def test_unchanged_migration_publishes_a_pure_companion_change(self):
        wrote = self.publish(b"SELECT 1;\n", "// v2\n")
        self.assertTrue(wrote)
        self.assertEqual(self.header.read_text(encoding="utf-8"), "// v2\n")

    def test_frozen_migration_holds_the_companion_and_warns(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            wrote = self.publish(b"SELECT 2;\n", "// v2\n")
        self.assertFalse(wrote)
        self.assertEqual(self.header.read_text(encoding="utf-8"), "// v1\n")
        self.assertIn("WARNING", buffer.getvalue())
        self.assertIn("0001_dc_thing.sql", buffer.getvalue())

    def test_frozen_migration_with_an_identical_companion_is_silent(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            wrote = self.publish(b"SELECT 2;\n", "// v1\n")
        self.assertTrue(wrote)
        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(self.header.read_text(encoding="utf-8"), "// v1\n")

    def test_one_changed_companion_holds_the_whole_set(self):
        other = self.root / "client/Thing.dbc"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"old")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            wrote = self.publish(b"SELECT 2;\n", "// v1\n",
                                 outputs=[(self.header, "// v1\n"), (other, b"new")])
        self.assertFalse(wrote)
        self.assertEqual(other.read_bytes(), b"old")
        self.assertIn("WARNING", buffer.getvalue())

    def test_missing_authority_fails_closed(self):
        bare = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        with self.assertRaises(am.AppliedStateError):
            am.write_coupled_outputs(
                bare, bare / "data/sql/db-world/updates/x.sql", b"SELECT 1;\n",
                [(bare / "header.h", b"// v1\n")], label="x")
        self.assertFalse((bare / "header.h").exists())


class CompanionMigrationPath(unittest.TestCase):
    """A companion migration must be one the core updater will read (F1).

    The updater loads a database's `updates/` directory only, and only files
    whose extension is exactly `.sql` (`UpdateFetcher.cpp:86`). A `--migration`
    in `data/generated/`, a `db-world` path outside `updates/`, another
    database's `updates/`, or a `.txt`/suffixless/`.SQL` name would publish the
    companions while the DB rows never change.
    """

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.module = self.root / "mod-diablocraft"
        self.updates = self.module / "data/sql/db-world/updates"
        self.updates.mkdir(parents=True)

    def test_the_generators_own_updates_directory_is_accepted(self):
        target = self.updates / "world_0016_x.sql"
        self.assertEqual(am.require_companion_migration(self.module, target, self.updates),
                         target.resolve())

    def test_a_txt_extension_is_rejected(self):
        target = self.updates / "world_0016_x.txt"
        with self.assertRaises(am.CompanionMigrationError):
            am.require_companion_migration(self.module, target, self.updates)

    def test_a_missing_extension_is_rejected(self):
        target = self.updates / "world_0016_x"
        with self.assertRaises(am.CompanionMigrationError):
            am.require_companion_migration(self.module, target, self.updates)

    def test_an_uppercase_sql_extension_is_rejected(self):
        target = self.updates / "world_0016_x.SQL"
        with self.assertRaises(am.CompanionMigrationError):
            am.require_companion_migration(self.module, target, self.updates)

    def test_a_path_in_data_generated_is_rejected(self):
        target = self.module / "data/generated/world_0016_x.sql"
        with self.assertRaises(am.CompanionMigrationError):
            am.require_companion_migration(self.module, target, self.updates)

    def test_a_db_world_path_outside_updates_is_rejected(self):
        target = self.module / "data/sql/db-world/world_0016_x.sql"
        with self.assertRaises(am.CompanionMigrationError):
            am.require_companion_migration(self.module, target, self.updates)

    def test_another_databases_updates_directory_is_rejected(self):
        target = self.module / "data/sql/db-characters/updates/world_0016_x.sql"
        with self.assertRaises(am.CompanionMigrationError):
            am.require_companion_migration(self.module, target, self.updates)

    def test_a_fixture_tree_outside_data_sql_is_accepted(self):
        tree = self.root / "fixture-module/updates"
        tree.mkdir(parents=True)
        target = tree / "x.sql"
        self.assertEqual(am.require_companion_migration(self.root / "fixture-module", target, tree),
                         target.resolve())

    def test_a_relative_target_resolves_against_the_module_root(self):
        target = "data/sql/db-world/updates/world_0016_x.sql"
        self.assertEqual(am.require_companion_migration(self.module, target, self.updates),
                         (self.module / target).resolve())


class MissingAuthorityPreservesAppliedFile(unittest.TestCase):
    """Codex review: with no authority the tier generator overwrote an applied
    migration. It must now fail closed, whatever the applied bytes are."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "data/d3").mkdir(parents=True)
        (self.root / "data/generated").mkdir(parents=True)
        (self.root / "data/sql/db-world/updates").mkdir(parents=True)
        shutil.copyfile(REAL_MODULE / "data/d3/difficulty_tiers.csv",
                        self.root / "data/d3/difficulty_tiers.csv")
        self.migration = self.root / "data/sql/db-world/updates/difficulty_0008_unlock_rules.sql"
        self.migration.write_bytes(b"-- the applied bytes must survive\n")
        self.before = self.migration.read_bytes()

    def test_missing_authority_raises_and_preserves_the_applied_file(self):
        with self.assertRaises(am.AppliedStateError):
            generate_tier_unlocks.generate(self.root)
        self.assertEqual(self.migration.read_bytes(), self.before)

    def test_unreadable_authority_raises_and_preserves_the_applied_file(self):
        (self.root / "data/sql/applied_migrations.csv").mkdir()
        with self.assertRaises(am.AppliedStateError):
            generate_tier_unlocks.generate(self.root)
        self.assertEqual(self.migration.read_bytes(), self.before)

    def test_zero_byte_authority_raises_and_preserves_the_applied_file(self):
        (self.root / "data/sql/applied_migrations.csv").write_bytes(b"")
        with self.assertRaises(am.AppliedStateError):
            generate_tier_unlocks.generate(self.root)
        self.assertEqual(self.migration.read_bytes(), self.before)

    def test_wrong_header_authority_raises_and_preserves_the_applied_file(self):
        (self.root / "data/sql/applied_migrations.csv").write_text(
            "sha1,path,provenance\n", encoding="utf-8")
        with self.assertRaises(am.AppliedStateError):
            generate_tier_unlocks.generate(self.root)
        self.assertEqual(self.migration.read_bytes(), self.before)

    def test_malformed_row_raises_and_preserves_the_applied_file(self):
        (self.root / "data/sql/applied_migrations.csv").write_text(
            "path,sha1,provenance\n"
            "db-world/updates/difficulty_0008_unlock_rules.sql,not-a-sha1,test\n",
            encoding="utf-8")
        with self.assertRaises(am.AppliedStateError):
            generate_tier_unlocks.generate(self.root)
        self.assertEqual(self.migration.read_bytes(), self.before)

    def test_blank_field_raises_and_preserves_the_applied_file(self):
        (self.root / "data/sql/applied_migrations.csv").write_text(
            "path,sha1,provenance\n,,\n", encoding="utf-8")
        with self.assertRaises(am.AppliedStateError):
            generate_tier_unlocks.generate(self.root)
        self.assertEqual(self.migration.read_bytes(), self.before)

    def test_header_only_authority_is_a_valid_empty_authority(self):
        (self.root / "data/sql/applied_migrations.csv").write_text(
            "path,sha1,provenance\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            generate_tier_unlocks.generate(self.root)
        self.assertNotEqual(self.migration.read_bytes(), self.before)

    def test_present_authority_freezes_the_applied_file(self):
        manifest = self.root / "data/sql/applied_migrations.csv"
        manifest.write_text(
            "path,sha1,provenance\n"
            f"db-world/updates/difficulty_0008_unlock_rules.sql,{am.sha1(self.before)},test\n",
            encoding="utf-8", newline="\n")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            generate_tier_unlocks.generate(self.root)
        self.assertEqual(self.migration.read_bytes(), self.before)
        self.assertIn("WARNING", buffer.getvalue())
        self.assertIn("difficulty_0008_unlock_rules.sql", buffer.getvalue())


class WaitForVersion(unittest.TestCase):
    """The deploy step captures the launch boundary before starting the server.
    The appender truncates the log (mode `w`), so these cover a marker already
    present before the first look, a stale marker from the previous run, and a
    truncation/replacement, plus the timeout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = pathlib.Path(self.tmp.name) / "Server.log"

    def write_log(self, text, mtime):
        self.log.write_text(text, encoding="utf-8")
        os.utime(self.log, (mtime, mtime))

    def test_marker_already_present_for_this_start_is_accepted(self):
        now = time.time()
        self.write_log("banner\n[DC version] module=0.0.0\n", now)
        ok, reason = refresh.wait_for_version(self.log, now - 5, 0.2, poll=0.01)
        self.assertTrue(ok, reason)

    def test_previous_start_marker_is_never_accepted(self):
        now = time.time()
        self.write_log("[DC version] module=0.0.0\n", now - 100)
        ok, reason = refresh.wait_for_version(self.log, now, 0.2, poll=0.01)
        self.assertFalse(ok, reason)
        self.assertIn("launch boundary", reason)

    def test_truncation_then_marker_is_accepted(self):
        now = time.time()
        self.write_log(("old line\n" * 200) + "[DC version] old\n", now - 100)

        def restart():
            time.sleep(0.05)
            self.write_log("new start\n[DC version] module=0.0.0\n", time.time())

        thread = threading.Thread(target=restart)
        thread.start()
        ok, reason = refresh.wait_for_version(self.log, now, 1.0, poll=0.01)
        thread.join()
        self.assertTrue(ok, reason)

    def test_timeout_returns_false_and_reads_nothing(self):
        now = time.time()
        self.write_log("banner only\n", now)
        ok, reason = refresh.wait_for_version(self.log, now, 0.15, poll=0.01)
        self.assertFalse(ok)
        self.assertIn("launch boundary", reason)


class LiveConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.conf = self.root / "worldserver.conf"

    def args(self, **overrides):
        values = dict(conf=str(self.conf), wait_log=None, since=None, wait=1, query_timeout=1)
        values.update(overrides)
        return argparse.Namespace(**values)

    def write_conf(self, **values):
        self.conf.write_text(
            "".join(f'{key} = "{value}"\n' for key, value in values.items()), encoding="utf-8")

    def test_incomplete_config_is_rejected(self):
        self.write_conf(WorldDatabaseInfo="127.0.0.1;3306;u;p;acore_world")
        with self.assertRaises(SystemExit) as caught:
            refresh.live_rows(self.args(), self.root)
        self.assertIn("CharacterDatabaseInfo", str(caught.exception))

    def test_malformed_connection_is_rejected(self):
        self.write_conf(WorldDatabaseInfo="127.0.0.1;3306;u;p;acore_world",
                        CharacterDatabaseInfo="only;three;fields",
                        LoginDatabaseInfo="127.0.0.1;3306;u;p;acore_auth")
        with self.assertRaises(SystemExit) as caught:
            refresh.live_rows(self.args(), self.root)
        self.assertIn("CharacterDatabaseInfo", str(caught.exception))

    def test_wait_log_requires_a_startup_boundary(self):
        self.write_conf(WorldDatabaseInfo="127.0.0.1;3306;u;p;acore_world",
                        CharacterDatabaseInfo="127.0.0.1;3306;u;p;acore_characters",
                        LoginDatabaseInfo="127.0.0.1;3306;u;p;acore_auth")
        with self.assertRaises(SystemExit) as caught:
            refresh.live_rows(self.args(wait_log=str(self.root / "Server.log")), self.root)
        self.assertIn("--since", str(caught.exception))

    def test_stale_startup_marker_fails_before_any_database_read(self):
        self.write_conf(WorldDatabaseInfo="127.0.0.1;3306;u;p;acore_world",
                        CharacterDatabaseInfo="127.0.0.1;3306;u;p;acore_characters",
                        LoginDatabaseInfo="127.0.0.1;3306;u;p;acore_auth")
        log = self.root / "Server.log"
        log.write_text("[DC version] module=0.0.0\n", encoding="utf-8")
        os.utime(log, (time.time() - 100, time.time() - 100))
        with unittest.mock.patch.object(refresh, "query_updates") as query:
            with self.assertRaises(SystemExit) as caught:
                refresh.live_rows(self.args(wait_log=str(log), since=time.time(), wait=1),
                                  self.root)
            self.assertIn("startup not confirmed", str(caught.exception))
            query.assert_not_called()


class QueryTimeout(unittest.TestCase):
    def test_mysql_process_is_bounded(self):
        connection = {"host": "h", "port": "3306", "user": "u",
                      "password": "p", "database": "acore_world"}
        with unittest.mock.patch.object(refresh.subprocess, "run",
                                        side_effect=subprocess.TimeoutExpired(cmd="mysql",
                                                                              timeout=1)):
            with self.assertRaises(RuntimeError) as caught:
                refresh.query_updates(connection, 1)
        self.assertIn("timed out", str(caught.exception))


class DevOptionFile(unittest.TestCase):
    """--cnf: the dev realm's world `updates` table through the refresh user's option file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.connection = {"cnf": "/x/dev-realm-refresh.cnf", "database": "torment_devrealm_world"}

    def args(self, **overrides):
        values = dict(conf=None, cnf="/x/dev-realm-refresh.cnf", world_db="torment_devrealm_world",
                      wait_log=None, since=None, wait=1, query_timeout=1, realm="dev")
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_the_option_file_is_mysqls_first_option_and_no_password_is_passed(self):
        completed = subprocess.CompletedProcess([], 0, stdout="a.sql\tabc\tmodule\n", stderr="")
        with unittest.mock.patch.dict(os.environ, {"MYSQL_PWD": "leaked"}), \
                unittest.mock.patch.object(refresh.subprocess, "run", return_value=completed) as run:
            rows = refresh.query_updates(self.connection, 5)
        argv, env = run.call_args.args[0], run.call_args.kwargs["env"]
        self.assertEqual(argv[:2], ["mysql", "--defaults-extra-file=/x/dev-realm-refresh.cnf"])
        self.assertEqual(argv[-1], "torment_devrealm_world")
        self.assertFalse([a for a in argv if a in ("-h", "-P", "-u") or a.startswith("--password")], argv)
        self.assertNotIn("MYSQL_PWD", env)
        self.assertEqual(rows, {"a.sql": ("ABC", "MODULE")})

    def test_a_conf_login_still_uses_the_environment_password(self):
        connection = {"host": "h", "port": "3306", "user": "u", "password": "p", "database": "acore_world"}
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with unittest.mock.patch.object(refresh.subprocess, "run", return_value=completed) as run:
            refresh.query_updates(connection, 5)
        self.assertEqual(run.call_args.kwargs["env"]["MYSQL_PWD"], "p")
        self.assertEqual(run.call_args.args[0][:3], ["mysql", "-h", "h"])

    def test_it_reads_the_one_database_it_is_given_and_nothing_else(self):
        with unittest.mock.patch.object(refresh, "query_updates", return_value={"a.sql": ("AB", "MODULE")}) as query:
            rows = refresh.live_rows(self.args(), self.root)
        query.assert_called_once_with(self.connection, 1)
        self.assertEqual(list(rows), ["world"])
        self.assertIn("confirmed against the dev updates table: torment_devrealm_world.updates", rows["world"]["a.sql"][2])

    def test_a_missing_world_db_is_refused_before_any_read(self):
        with unittest.mock.patch.object(refresh, "query_updates") as query:
            with self.assertRaises(SystemExit) as caught:
                refresh.live_rows(self.args(world_db=None), self.root)
        self.assertIn("--world-db", str(caught.exception))
        query.assert_not_called()

    def test_the_marker_is_still_awaited_before_the_read(self):
        log = self.root / "Server.log"
        log.write_text("[DC version] module=0.0.0\n", encoding="utf-8")
        os.utime(log, (time.time() - 100, time.time() - 100))
        with unittest.mock.patch.object(refresh, "query_updates") as query:
            with self.assertRaises(SystemExit) as caught:
                refresh.live_rows(self.args(wait_log=str(log), since=time.time()), self.root)
        self.assertIn("startup not confirmed", str(caught.exception))
        query.assert_not_called()

    def test_a_cnf_and_a_conf_are_two_logins(self):
        with unittest.mock.patch.object(sys, "argv", ["refresh", "--dev", "--cnf", "a", "--conf", "b"]), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                refresh.main()
        self.assertEqual(caught.exception.code, 2)


class RefreshTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.module = self.root / "mod-diablocraft"
        self.updates = self.module / "data/sql/db-world/updates"
        self.updates.mkdir(parents=True)
        self.applied = self.updates / "0001_dc_old.sql"
        self.applied.write_text("SELECT 1;\n", encoding="utf-8")
        self.new = self.updates / "0002_dc_new.sql"
        self.new.write_text("SELECT 2;\n", encoding="utf-8")
        self.manifest = self.module / "data/sql/applied_migrations.csv"
        write_manifest(self.manifest,
                       [["db-world/updates/0001_dc_old.sql", am.sha1(b"SELECT 1;\n"), "seed"]])
        self.evidence = self.root / "evidence.csv"
        with self.evidence.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["path", "sha1", "state", "provenance"])
            writer.writerow(["db-world/updates/0001_dc_old.sql", am.sha1(b"SELECT 1;\n"),
                             "MODULE", "seed"])
            writer.writerow(["db-world/updates/0002_dc_new.sql", am.sha1(b"SELECT 2;\n"),
                             "MODULE", "fresh"])

    def main_args(self, apply=False):
        args = ["refresh", "--repo-root", str(self.root), "--manifest", str(self.manifest),
                "--evidence", str(self.evidence)]
        return args + (["--apply"] if apply else [])

    def test_evidence_reader_splits_database_and_name(self):
        rows = refresh.evidence_rows(self.evidence)
        self.assertIn("0002_dc_new.sql", rows["world"])

    def test_collect_finds_only_repo_files_the_live_data_confirms(self):
        found, mismatches = refresh.collect(self.root, refresh.evidence_rows(self.evidence))
        self.assertEqual(sorted(found), ["db-world/updates/0001_dc_old.sql",
                                         "db-world/updates/0002_dc_new.sql"])
        self.assertEqual(mismatches, [])

    def test_collect_reports_a_changed_applied_file(self):
        self.new.write_text("SELECT 999;\n", encoding="utf-8")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            found, mismatches = refresh.collect(self.root, refresh.evidence_rows(self.evidence))
        self.assertNotIn("db-world/updates/0002_dc_new.sql", found)
        self.assertIn("db-world/updates/0002_dc_new.sql", mismatches)
        self.assertIn("changed after it was applied", errors.getvalue())

    def test_main_appends_only_absent_rows(self):
        with unittest.mock.patch.object(sys, "argv", self.main_args(apply=True)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(refresh.main(), 0)
        with self.manifest.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([row["path"] for row in rows],
                         ["db-world/updates/0001_dc_old.sql", "db-world/updates/0002_dc_new.sql"])
        self.assertEqual(rows[0]["provenance"], "seed")
        self.assertEqual(rows[1]["provenance"], "fresh")

    def test_main_is_nonzero_on_a_changed_applied_file(self):
        self.new.write_text("SELECT 999;\n", encoding="utf-8")
        with unittest.mock.patch.object(sys, "argv", self.main_args()), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(refresh.main(), 1)

    def test_dry_run_writes_nothing(self):
        args = self.main_args()
        with unittest.mock.patch.object(sys, "argv", args), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(refresh.main(), 0)
        with self.manifest.open(encoding="utf-8", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def dev_args(self):
        return ["refresh", "--repo-root", str(self.root), "--dev", "--evidence", str(self.evidence), "--apply"]

    def test_dev_writes_its_own_manifest_and_skips_what_live_lists(self):
        live_before = self.manifest.read_bytes()
        with unittest.mock.patch.object(sys, "argv", self.dev_args()), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(refresh.main(), 0)
        self.assertEqual(self.manifest.read_bytes(), live_before)
        with (self.module / "data/sql/applied_migrations_dev.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([(row["path"], row["provenance"]) for row in rows],
                         [("db-world/updates/0002_dc_new.sql", "fresh")])
        self.assertTrue(am.is_applied(self.module, self.new))

    def test_dev_provenance_says_dev(self):
        rows = refresh.evidence_rows(self.evidence_without_provenance(), "dev")
        self.assertIn("confirmed against the dev updates table", rows["world"]["0002_dc_new.sql"][2])

    def evidence_without_provenance(self):
        path = self.root / "bare.csv"
        path.write_text("path,sha1,state\ndb-world/updates/0002_dc_new.sql," + am.sha1(b"SELECT 2;\n") + ",MODULE\n",
                        encoding="utf-8")
        return path

    def test_dev_fails_when_a_live_listed_file_is_applied_on_dev_as_other_bytes(self):
        self.applied.write_text("SELECT 111;\n", encoding="utf-8")
        with self.evidence.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["path", "sha1", "state", "provenance"])
            writer.writerow(["db-world/updates/0001_dc_old.sql", am.sha1(b"SELECT 111;\n"), "MODULE", "dev"])
        errors = io.StringIO()
        with unittest.mock.patch.object(sys, "argv", self.dev_args()), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            self.assertEqual(refresh.main(), 1)
        self.assertIn("applied on dev as", errors.getvalue())
        self.assertFalse((self.module / "data/sql/applied_migrations_dev.csv").exists())

    def test_read_manifest_of_a_missing_file_is_empty(self):
        self.assertEqual(refresh.read_manifest(self.root / "nope.csv"), [])

    # ---- --merge-from: a dev host's rows into this checkout's manifest
    def merge_source(self, rows):
        path = self.root / "host.csv"
        write_manifest(path, rows)
        return path

    def merge(self, source, *extra, manifest=None):
        args = ["refresh", "--repo-root", str(self.root), "--merge-from", str(source), "--apply",
                "--manifest", str(manifest or self.manifest), *extra]
        errors = io.StringIO()
        with unittest.mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(errors):
            return refresh.main(), errors.getvalue()

    def manifest_rows(self, path):
        with path.open(encoding="utf-8", newline="") as stream:
            return [(row["path"], row["provenance"]) for row in csv.DictReader(stream)]

    def test_merge_appends_only_absent_rows_and_never_rewrites(self):
        source = self.merge_source([["db-world/updates/0001_dc_old.sql", am.sha1(b"SELECT 1;\n"), "host says so"],
                                    ["db-world/updates/0002_dc_new.sql", am.sha1(b"SELECT 2;\n"), "from the host"]])
        code, _ = self.merge(source)
        self.assertEqual(code, 0)
        self.assertEqual(self.manifest_rows(self.manifest),
                         [("db-world/updates/0001_dc_old.sql", "seed"), ("db-world/updates/0002_dc_new.sql", "from the host")])

    def test_merge_of_a_different_hash_is_an_error_and_the_row_stays(self):
        source = self.merge_source([["db-world/updates/0001_dc_old.sql", am.sha1(b"SELECT 999;\n"), "other bytes"]])
        before = self.manifest.read_bytes()
        code, errors = self.merge(source)
        self.assertEqual(code, 1)
        self.assertIn("leaving the manifest row as it was", errors)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_merge_refuses_a_malformed_hash_and_writes_nothing(self):
        source = self.merge_source([["db-world/updates/0002_dc_new.sql", "not-a-sha", "from the host"]])
        before = self.manifest.read_bytes()
        code, errors = self.merge(source)
        self.assertEqual(code, 1)
        self.assertIn("malformed sha1", errors)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_a_dev_merge_skips_what_live_lists_and_reads_no_database(self):
        dev = self.module / "data/sql/applied_migrations_dev.csv"
        source = self.merge_source([["db-world/updates/0001_dc_old.sql", am.sha1(b"SELECT 1;\n"), "host"],
                                    ["db-world/updates/0002_dc_new.sql", am.sha1(b"SELECT 2;\n"), "host"]])
        with unittest.mock.patch.object(refresh, "query_updates") as query:
            code, _ = self.merge(source, "--dev", manifest=dev)
        self.assertEqual(code, 0)
        query.assert_not_called()
        self.assertEqual(self.manifest_rows(dev), [("db-world/updates/0002_dc_new.sql", "host")])
        self.assertTrue(am.is_applied(self.module, self.new))

    def test_a_merge_reserves_a_row_whose_file_is_not_in_this_checkout_and_says_so(self):
        # dev runs unreviewed branches: a migration only a branch has cannot carry a hash in nightly's manifest,
        # so it is a reserved row (path, no hash): its number stays taken (diablocraft-2kmef)
        dev = self.module / "data/sql/applied_migrations_dev.csv"
        source = self.merge_source([["db-world/updates/0002_dc_new.sql", am.sha1(b"SELECT 2;\n"), "host"],
                                    ["db-world/updates/0003_dc_branch_only.sql", am.sha1(b"SELECT 3;\n"), "host"]])
        stdout = io.StringIO()
        args = ["refresh", "--repo-root", str(self.root), "--merge-from", str(source), "--apply",
                "--manifest", str(dev), "--dev"]
        with unittest.mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(refresh.main(), 0)
        self.assertEqual(self.manifest_rows(dev), [("db-world/updates/0002_dc_new.sql", "host"),
                                                   ("db-world/updates/0003_dc_branch_only.sql", "reserved on dev, branch: host")])
        self.assertIn("0003_dc_branch_only.sql", stdout.getvalue())
        self.assertIn("not in this checkout", stdout.getvalue())
        # reserved is not applied: the number is taken, the file is not frozen
        self.assertFalse(am.is_applied(self.module, self.updates / "0003_dc_branch_only.sql"))
        self.assertEqual(am.load_reserved(self.module), {"db-world/updates/0003_dc_branch_only.sql"})

    def test_a_merge_of_only_branch_rows_writes_a_reserved_manifest(self):
        dev = self.module / "data/sql/applied_migrations_dev.csv"
        source = self.merge_source([["db-world/updates/0003_dc_branch_only.sql", am.sha1(b"SELECT 3;\n"), "host"]])
        code, _ = self.merge(source, "--dev", manifest=dev)
        self.assertEqual(code, 0)
        self.assertEqual(self.manifest_rows(dev), [("db-world/updates/0003_dc_branch_only.sql", "reserved on dev, branch: host")])
        self.assertEqual(dev.read_text(encoding="utf-8").splitlines()[1].split(",")[1], "")
        before = dev.read_bytes()
        self.merge(source, "--dev", manifest=dev)    # a second merge adds nothing
        self.assertEqual(dev.read_bytes(), before)

    def test_a_live_manifest_merge_still_skips_a_row_whose_file_is_not_in_this_checkout(self):
        source = self.merge_source([["db-world/updates/0003_dc_branch_only.sql", am.sha1(b"SELECT 3;\n"), "host"]])
        before = self.manifest.read_bytes()
        code, _ = self.merge(source)
        self.assertEqual(code, 0)
        self.assertEqual(self.manifest.read_bytes(), before)   # the live manifest takes no reserved rows

    def test_a_reserved_row_gives_way_to_the_real_one_once_the_file_reaches_the_checkout(self):
        dev = self.module / "data/sql/applied_migrations_dev.csv"
        source = self.merge_source([["db-world/updates/0003_dc_branch_only.sql", am.sha1(b"SELECT 3;\n"), "host"]])
        self.merge(source, "--dev", manifest=dev)
        self.assertEqual(am.load_reserved(self.module), {"db-world/updates/0003_dc_branch_only.sql"})
        (self.updates / "0003_dc_branch_only.sql").write_text("SELECT 3;\n", encoding="utf-8")   # the branch merged
        code, _ = self.merge(source, "--dev", manifest=dev)
        self.assertEqual(code, 0)
        self.assertEqual(self.manifest_rows(dev), [("db-world/updates/0003_dc_branch_only.sql", "host")])
        self.assertEqual(am.load_reserved(self.module), set())
        self.assertTrue(am.is_applied(self.module, self.updates / "0003_dc_branch_only.sql"))

    def test_a_dev_merge_of_a_file_live_lists_under_other_bytes_is_an_error(self):
        dev = self.module / "data/sql/applied_migrations_dev.csv"
        source = self.merge_source([["db-world/updates/0001_dc_old.sql", am.sha1(b"SELECT 5;\n"), "host"]])
        code, errors = self.merge(source, "--dev", manifest=dev)
        self.assertEqual(code, 1)
        self.assertIn("applied on dev as", errors)
        self.assertFalse(dev.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

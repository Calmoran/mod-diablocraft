"""An applied migration file must never change. Proven, not remembered.

I rewrote `items_0004_skill_affixes.sql` to add two columns. It was already
applied, and the core records a hash of every update file and re-hashes them on
start, so editing it made an applied migration look changed. The columns belong
in a NEW file; the applied one is frozen.

`mod-diablocraft/data/sql/applied_migrations.csv` is the manifest: the path, the
SHA1, and **where that hash came from**. Provenance is a column because one of
the two entries was confirmed against the live `updates` table and the other was
not, and a test that treats a guess and a measurement alike teaches the wrong
thing.

The hash is SHA1 of the file's bytes. That is not folklore: the core at the
pinned revision computes
`ByteArrayToHexStr(Acore::Crypto::SHA1::GetDigestOf(ReadSQLUpdate(filePath)))`,
and the one hash the PM read out of the live table matches the SHA1 of those
exact bytes. A test asserts the core still does it that way.
"""
import csv
import hashlib
import pathlib
import subprocess
import sys
import unittest

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from applied_migrations import RESERVED  # noqa: E402

MODULE = pathlib.Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
SQL = MODULE / "data" / "sql"
MANIFEST = SQL / "applied_migrations.csv"
CORE_PIN = (pathlib.Path(ROOT) / "core-commit.txt").read_text().split()[0]  # the pin moves with core-commit.txt
CORE = ROOT / "azerothcore-wotlk"


def manifest():
    with MANIFEST.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def sha1_of(path):
    return hashlib.sha1(path.read_bytes()).hexdigest().upper()


class Frozen(unittest.TestCase):
    def setUp(self):
        self.rows = manifest()
        self.assertTrue(self.rows, "the manifest is empty, so this suite checks nothing")

    def test_every_applied_file_still_hashes_to_what_was_applied(self):
        for row in self.rows:
            with self.subTest(path=row["path"]):
                path = SQL / row["path"]
                self.assertTrue(path.is_file(), f"{row['path']} is gone")
                self.assertEqual(sha1_of(path), row["sha1"],
                                 f"{row['path']} has changed since it was applied. Put the change "
                                 f"in a NEW migration; the applied one is frozen.")

    def test_every_manifest_entry_names_a_real_update_file(self):
        for row in self.rows:
            with self.subTest(path=row["path"]):
                self.assertIn("/updates/", row["path"])
                self.assertTrue(row["path"].endswith(".sql"))
                self.assertTrue((SQL / row["path"]).is_file())

    def test_every_entry_says_where_its_hash_came_from(self):
        """A confirmed hash and an assumed one are not the same evidence."""
        for row in self.rows:
            with self.subTest(path=row["path"]):
                self.assertTrue(row["provenance"].strip())
        confirmed = [row for row in self.rows if "confirmed against the live" in row["provenance"]]
        self.assertTrue(confirmed, "no entry is confirmed against the live updates table")

    def test_the_hashes_are_well_formed_sha1(self):
        for row in self.rows:
            with self.subTest(path=row["path"]):
                self.assertRegex(row["sha1"], r"^[0-9A-F]{40}$")


class DevFrozen(unittest.TestCase):
    """applied_migrations_dev.csv: a file dev applied before live is held to the same bytes."""

    def test_every_dev_applied_file_still_hashes_to_what_was_applied_and_live_does_not_list_it(self):
        path = SQL / "applied_migrations_dev.csv"
        if not path.is_file():
            self.skipTest("no dev manifest in this checkout")
        live = {row["path"] for row in manifest()}
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream, strict=True))
        for row in rows:
            with self.subTest(path=row["path"]):
                self.assertNotIn(row["path"], live)
                self.assertTrue(row["provenance"].strip())
                if row["sha1"] == "" and row["provenance"].startswith(RESERVED):
                    # A branch's migration dev applied (diablocraft-2kmef): the path with no hash, its number
                    # taken. Checked only while the file is not in the tree; once it lands the refresh must
                    # replace the row with the real one, or the file is applied on dev and not frozen.
                    self.assertFalse((SQL / row["path"]).is_file(),
                                     f"{row['path']} is in the tree but its dev row is still reserved. "
                                     f"Run dev_realm.sh refresh-migrations to replace it with the hash.")
                    continue
                self.assertEqual(sha1_of(SQL / row["path"]), row["sha1"],
                                 f"{row['path']} has changed since dev applied it. Put the change in a NEW migration.")


class GeneratorsLeaveAppliedFilesAlone(unittest.TestCase):
    """The regression for the mistake itself: running the generators must not
    touch a file that has already been applied."""

    def snapshot(self):
        return {row["path"]: sha1_of(SQL / row["path"]) for row in manifest()}

    def run_generator(self, module_name, entry):
        module = __import__(module_name)
        getattr(module, entry)()

    def test_the_affix_generator_does_not_write_an_applied_file(self):
        before = self.snapshot()
        self.run_generator("generate_skill_affixes", "main")
        self.assertEqual(self.snapshot(), before)

    def test_the_catalogue_generators_do_not_write_an_applied_file(self):
        before = self.snapshot()
        self.run_generator("generate_class_catalogue", "generate")
        self.run_generator("generate_skill_id_migration", "generate")
        self.assertEqual(self.snapshot(), before)

    def test_the_affix_ids_land_in_their_own_new_migration(self):
        new = SQL / "db-world/updates/items_0005_skill_affix_ids.sql"
        self.assertTrue(new.is_file())
        body = new.read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE dc_skill_affix", body)
        self.assertIn("ADD COLUMN class_id", body)
        self.assertIn("ADD COLUMN skill_id", body)
        self.assertIn("UPDATE dc_skill_affix SET class_id=", body)
        # And the frozen file still has neither column.
        applied = (SQL / "db-world/updates/items_0004_skill_affixes.sql").read_text(encoding="utf-8")
        self.assertNotIn("class_id", applied)
        self.assertNotIn("skill_id", applied)

    def test_the_generated_mirror_matches_the_frozen_migration(self):
        mirror = MODULE / "data" / "generated" / "skill_affixes.sql"
        applied = SQL / "db-world/updates/items_0004_skill_affixes.sql"
        self.assertEqual(mirror.read_bytes(), applied.read_bytes())

    def test_the_new_migration_carries_no_semicolon_in_a_literal(self):
        body = (SQL / "db-world/updates/items_0005_skill_affix_ids.sql").read_text(encoding="utf-8")
        import re
        for literal in re.findall(r"'((?:[^']|'')*)'", body):
            self.assertNotIn(";", literal, literal)


class TheCommittedBlobIsTheAppliedFile(unittest.TestCase):
    """A fresh checkout must reproduce the applied bytes.

    The working tree can be filtered by the host's EOL settings, so this hashes
    the committed blob itself - what every clone actually starts from. The
    path-specific `.../crafting_0003_crafting_tunables.sql -text` attribute
    keeps that blob byte-exact; without it the mixed-EOL crafting_0003 blob
    normalised to LF and a fresh clone hashed differently from the live
    `updates` row.
    """

    def test_every_committed_blob_hashes_to_its_manifest_sha1(self):
        for row in manifest():
            with self.subTest(path=row["path"]):
                blob = subprocess.run(
                    ["git", "-C", str(ROOT), "cat-file", "blob",
                     f"HEAD:mod-diablocraft/data/sql/{row['path']}"],
                    capture_output=True, check=True).stdout
                self.assertEqual(
                    hashlib.sha1(blob).hexdigest().upper(), row["sha1"],
                    f"the committed blob for {row['path']} is not the applied file; a fresh "
                    f"checkout would hash differently")

    def test_module_migrations_are_not_eol_converted(self):
        result = subprocess.run(
            ["git", "-C", str(ROOT), "check-attr", "text", "--",
             "mod-diablocraft/data/sql/db-world/updates/crafting_0003_crafting_tunables.sql"],
            capture_output=True, text=True, check=True).stdout
        self.assertIn("text: unset", result, "module migrations must not be EOL-converted")


class TheHashIsTheCoresHash(unittest.TestCase):
    def test_the_core_still_hashes_update_files_with_sha1(self):
        """If the core ever changed this, the manifest would be measuring the
        wrong thing while still passing."""
        try:
            source = subprocess.run(
                ["git", "-C", str(CORE), "show",
                 f"{CORE_PIN}:src/server/database/Updater/UpdateFetcher.cpp"],
                capture_output=True, text=True, check=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as error:
            raise unittest.SkipTest(f"core not readable at the pin: {error}")
        self.assertIn("SHA1::GetDigestOf(ReadSQLUpdate(filePath))", source)

    def test_the_confirmed_hash_is_the_sha1_of_those_exact_bytes(self):
        row = next(r for r in manifest() if "confirmed against the live" in r["provenance"])
        self.assertEqual(sha1_of(SQL / row["path"]), row["sha1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

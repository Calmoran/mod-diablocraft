#!/usr/bin/env python3
"""A migration already on nightly may not be edited or deleted by a branch, applied on dev or not (diablocraft-coi85).

    python3 mod-diablocraft/scripts/tests/release/test_merged_migrations_frozen.py

Why: test_applied_migrations checks only the files listed in applied_migrations*.csv, and a file gets a row there
only after a dev deploy's refresh. Between the merge and that refresh nothing stopped a branch rewriting the file
(Combat's 2c rewrote the merged tunables_0077 in that gap). test_migration_numbers checks names only.

What it reads, and who writes it: no file of its own, and no list for anyone to keep. Git is the list. Nightly's
tree holds every merged migration, and the PM's merge writes it by merging, so there is no hash file to update at a
merge and no window between a merge and an update. The test takes the merge-base of HEAD with `nightly` (and with
`origin/nightly` when that exists), and every `mod-diablocraft/data/sql/db-*/updates/**/*.sql` that is in the
merge-base must still be there with the same bytes. It diffs the merge-base against the WORKING TREE, so an edit
not yet committed fails too (a generator run is caught before the commit). It needs a git checkout with a
`nightly` branch, which every worker worktree and the main checkout have; no database, no server, no build.

Two allowed changes. The first: restoring the bytes the deploy recorded (the same file name in applied_migrations.csv or
applied_migrations_dev.csv AT THE MERGE-BASE, written by the deploy refresh). A branch that puts a wrongly edited
file back to the bytes dev applied (f4aj1 did that for tunables_0012) is not an edit of applied state. The rows
are read from the merge-base, never from the branch, so a branch cannot list its own edit.

The second: ONE_TIME_EDITS below, named entries and no general allow list. An entry says: this one file, whose bytes at the
merge-base hash to `old_sha256`, may become the bytes that hash to `new_sha256`, for the stated bead and reason (a migration
that never applied anywhere). Any other bytes, any other path, a deleted file, a merge-base whose bytes are not the old ones:
red. The entry is tested in this file, a changed hash fails it, and it needs no upkeep: once the edit is on nightly the file at
the merge-base already is the new bytes, nothing differs, and the entry sits unused.

Not covered, said plainly:
  * an edit that already reached nightly (a PM merge of a branch that never ran this test): HEAD on nightly has
    nothing to differ from. The branch's own run, and the Reviewer's, are the gate;
  * `data/generated/` mirrors and other output: they regenerate with their sheets (applied_migrations.py ties a
    companion to a new migration), so freezing them here would block ordinary work;
  * a checkout with no `nightly` ref: the test skips and says what to fetch. Run it from a worktree or the main
    checkout.

Run by the gate through the `always` row in test_rules.csv: it reads git and no tracked file, so a changed file
would never select it.
"""
import csv
import hashlib
import io
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SQL = "mod-diablocraft/data/sql"
# What the core's updater loads: a .sql (exactly) under a db-*/updates folder, any depth.
MIGRATION = re.compile(r"^" + re.escape(SQL) + r"/db-[^/]+/updates/.+\.sql$")
MANIFESTS = (SQL + "/applied_migrations.csv", SQL + "/applied_migrations_dev.csv")
BASE_REFS = ("nightly", "origin/nightly")
SHA1 = re.compile(r"^[0-9A-F]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Narrow, one-time, named (diablocraft-3yvay, the Architect and the PM, 2026-10-23). Never a pattern: a path and two hashes.
ONE_TIME_EDITS = {
    SQL + "/db-world/updates/followers_0010_skill_values.sql": {
        "bead": "diablocraft-3yvay",
        "old_sha256": "60bbaf6b48ca622ac8b1a204d03bdeb3babbc7e3663142129312e3d6db80eee9",
        "new_sha256": "2811d7c5a3031275eee80f805cdcfcba30c243a2551bc0d65edc77c107c3bd73",
        "reason": "never applied anywhere: its unit column was VARCHAR(32), the Enchantress' 'percent of weapon damage, Arcane' is "
                  "33 characters, the updater halted on it and no row was written; the new bytes widen the column before the rows",
    },
}


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=check)


def existing_refs(repo, refs=BASE_REFS):
    return [ref for ref in refs
            if git(repo, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False).returncode == 0]


def applied_at(repo, base):
    """{migration path: {sha1}} the deploy recorded, read from the commit `base`, never from the branch."""
    applied = {}
    for manifest in MANIFESTS:
        shown = git(repo, "show", f"{base}:{manifest}", check=False)
        if shown.returncode != 0:
            continue
        for row in csv.DictReader(io.StringIO(shown.stdout.decode("utf-8")), strict=True):
            if SHA1.match(row.get("sha1", "")):
                applied.setdefault(SQL + "/" + row["path"], set()).add(row["sha1"])
    return applied


def violations(repo, refs=None, edits=None):
    """One line per merged migration the working tree edits or deletes, against each of `refs` (default: nightly's).

    A path is reported once, under the first ref that holds it.
    """
    repo = Path(repo)
    edits = ONE_TIME_EDITS if edits is None else edits
    found = {}
    for ref in (existing_refs(repo) if refs is None else refs):
        merge_base = git(repo, "merge-base", "HEAD", ref, check=False)
        if merge_base.returncode != 0:
            found.setdefault("", f"HEAD shares no history with {ref}, so no migration can be compared")
            continue
        base = merge_base.stdout.decode().strip()
        applied = applied_at(repo, base)
        # --no-renames: a rename is a delete of the merged name plus an add, and the delete is the failure.
        diff = git(repo, "diff", "--no-renames", "--name-status", "-z", base, "--", SQL).stdout.decode("utf-8")
        tokens = diff.split("\0")
        for status, path in zip(tokens[0::2], tokens[1::2]):
            if status == "A" or not MIGRATION.match(path):
                continue
            if status == "M":
                on_disk = repo / path
                if on_disk.is_file() and hashlib.sha1(on_disk.read_bytes()).hexdigest().upper() in applied.get(path, ()):
                    continue  # put back to the bytes the deploy recorded
                one_time = edits.get(path)
                if one_time and on_disk.is_file():
                    was = git(repo, "show", f"{base}:{path}", check=False).stdout
                    if (hashlib.sha256(was).hexdigest() == one_time["old_sha256"]
                            and hashlib.sha256(on_disk.read_bytes()).hexdigest() == one_time["new_sha256"]):
                        continue  # the one named change, to the one named bytes
            what = "is deleted" if status == "D" else "is edited"
            found.setdefault(path, f"{path} {what}; it is already on {ref} (merge-base {base[:9]}). Put the change "
                                   f"in a NEW migration with the next free number; to undo an edit: "
                                   f"git show {base[:9]}:{path} > {path}")
    return list(found.values())


class TheBranchLeavesMergedMigrationsAlone(unittest.TestCase):
    def test_no_migration_on_nightly_is_edited_or_deleted(self):
        refs = existing_refs(REPO)
        if not refs:
            self.skipTest("no `nightly` or `origin/nightly` ref in this checkout, so merged migrations are unknown; "
                          "run `git fetch origin nightly` or use a worktree")
        self.assertEqual(violations(REPO, refs), [])


class FixtureRepo(unittest.TestCase):
    """A throwaway git repo shaped like ours: `nightly` holds the merged migrations, the branch is the work."""
    WORLD = SQL + "/db-world/updates/"
    CHARS = SQL + "/db-characters/updates/"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.assertNotEqual(self.repo, REPO)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "commit.gpgsign", "false")
        git(self.repo, "checkout", "-q", "-b", "nightly")
        self.write(self.WORLD + "tunables_0001.sql", "INSERT 1;\n")
        self.write(self.WORLD + "items_0002.sql", "INSERT 2;\n")
        self.write(self.WORLD + "sub/items_0003.sql", "INSERT 3;\n")
        self.write(self.CHARS + "chars_0001.sql", "ALTER 1;\n")
        self.write(self.WORLD + "notes.txt", "not a migration\n")
        self.write(SQL + "/README.md", "readme\n")
        self.write("mod-diablocraft/data/generated/mirror.sql", "mirror\n")
        self.commit("merged")
        git(self.repo, "checkout", "-q", "-b", "w/branch")

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def commit(self, message):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)

    def found(self):
        return violations(self.repo, ["nightly"])

    def assertRed(self, *paths):
        found = self.found()
        for path in paths:
            self.assertTrue(any(line.startswith(path + " ") for line in found), (path, found))
        self.assertEqual(len(found), len(paths), found)

    def assertGreen(self):
        self.assertEqual(self.found(), [])


class RedOnAnEditOrDelete(FixtureRepo):
    def test_a_clean_branch_is_green(self):
        self.assertGreen()

    def test_an_edit_committed_on_the_branch_is_red(self):
        self.write(self.WORLD + "tunables_0001.sql", "INSERT 1 CHANGED;\n")
        self.commit("edit")
        self.assertRed(self.WORLD + "tunables_0001.sql")

    def test_an_edit_not_yet_committed_is_red(self):
        self.write(self.WORLD + "tunables_0001.sql", "INSERT 1 CHANGED;\n")
        self.assertRed(self.WORLD + "tunables_0001.sql")

    def test_a_staged_edit_is_red(self):
        self.write(self.WORLD + "tunables_0001.sql", "INSERT 1 CHANGED;\n")
        git(self.repo, "add", "-A")
        self.assertRed(self.WORLD + "tunables_0001.sql")

    def test_a_delete_is_red(self):
        (self.repo / (self.WORLD + "items_0002.sql")).unlink()
        self.commit("delete")
        self.assertRed(self.WORLD + "items_0002.sql")

    def test_a_delete_not_yet_committed_is_red(self):
        (self.repo / (self.WORLD + "items_0002.sql")).unlink()
        self.assertRed(self.WORLD + "items_0002.sql")

    def test_a_rename_is_red_for_the_old_name(self):
        (self.repo / (self.WORLD + "items_0002.sql")).rename(self.repo / (self.WORLD + "items_0009.sql"))
        self.commit("rename")
        self.assertRed(self.WORLD + "items_0002.sql")

    def test_a_rename_does_not_hide_the_edit_listed_after_it(self):
        """git's rename entries carry two paths; read as one they shift every entry behind them."""
        (self.repo / (self.WORLD + "items_0002.sql")).rename(self.repo / (self.WORLD + "items_0009.sql"))
        self.write(self.WORLD + "tunables_0001.sql", "INSERT 1 CHANGED;\n")
        self.commit("rename and edit")
        self.assertRed(self.WORLD + "items_0002.sql", self.WORLD + "tunables_0001.sql")

    def test_a_trailing_newline_is_an_edit(self):
        self.write(self.WORLD + "tunables_0001.sql", "INSERT 1;")
        self.assertRed(self.WORLD + "tunables_0001.sql")

    def test_a_line_ending_change_is_an_edit(self):
        self.write(self.WORLD + "tunables_0001.sql", "INSERT 1;\r\n")
        self.assertRed(self.WORLD + "tunables_0001.sql")

    def test_the_other_database_and_a_subfolder_count(self):
        self.write(self.CHARS + "chars_0001.sql", "ALTER 1 CHANGED;\n")
        self.write(self.WORLD + "sub/items_0003.sql", "INSERT 3 CHANGED;\n")
        self.assertRed(self.CHARS + "chars_0001.sql", self.WORLD + "sub/items_0003.sql")

    def test_every_offence_is_listed_not_just_the_first(self):
        self.write(self.WORLD + "tunables_0001.sql", "x\n")
        (self.repo / (self.WORLD + "items_0002.sql")).unlink()
        self.assertRed(self.WORLD + "tunables_0001.sql", self.WORLD + "items_0002.sql")

    def test_the_message_names_the_fix(self):
        self.write(self.WORLD + "tunables_0001.sql", "x\n")
        line = self.found()[0]
        self.assertIn("NEW migration", line)
        self.assertIn("git show", line)
        self.assertIn("nightly", line)


class GreenOnWhatIsAllowed(FixtureRepo):
    def test_a_new_migration_is_green(self):
        self.write(self.WORLD + "tunables_0002.sql", "INSERT NEW;\n")
        self.commit("new")
        self.assertGreen()

    def test_a_new_migration_edited_again_on_the_branch_is_green(self):
        self.write(self.WORLD + "tunables_0002.sql", "INSERT NEW;\n")
        self.commit("new")
        self.write(self.WORLD + "tunables_0002.sql", "INSERT NEW AGAIN;\n")
        self.commit("edit own file")
        self.assertGreen()

    def test_a_file_that_is_not_a_migration_is_green(self):
        self.write(self.WORLD + "notes.txt", "changed\n")
        self.write(SQL + "/README.md", "changed\n")
        self.write("mod-diablocraft/data/generated/mirror.sql", "changed\n")
        self.assertGreen()

    def test_an_sql_file_outside_an_updates_folder_is_green(self):
        self.write(SQL + "/db-world/base/x.sql", "a\n")
        self.commit("base")
        git(self.repo, "checkout", "-q", "nightly")
        git(self.repo, "merge", "-q", "--ff-only", "w/branch")
        git(self.repo, "checkout", "-q", "w/branch")
        self.write(SQL + "/db-world/base/x.sql", "b\n")
        self.assertGreen()

    def test_nightly_moving_on_does_not_blame_the_branch(self):
        """The merge-base, not nightly's tip: a file nightly added or edited after the branch left is not the branch's."""
        git(self.repo, "checkout", "-q", "nightly")
        self.write(self.WORLD + "items_0010.sql", "LATER;\n")
        self.write(self.WORLD + "tunables_0001.sql", "NIGHTLY EDITED IT;\n")
        self.commit("nightly moves")
        git(self.repo, "checkout", "-q", "w/branch")
        self.assertGreen()

    def test_merging_nightly_in_keeps_a_branch_green(self):
        git(self.repo, "checkout", "-q", "nightly")
        self.write(self.WORLD + "items_0010.sql", "LATER;\n")
        self.commit("nightly moves")
        git(self.repo, "checkout", "-q", "w/branch")
        git(self.repo, "merge", "-q", "--no-edit", "nightly")
        self.assertGreen()

    def test_nightly_itself_is_green(self):
        git(self.repo, "checkout", "-q", "nightly")
        self.assertGreen()


class RestoringTheAppliedBytes(FixtureRepo):
    """f4aj1: tunables_0012 put back to the bytes dev applied. Allowed; any other bytes are not."""
    APPLIED = "INSERT 1 AS DEV APPLIED IT;\n"

    def setUp(self):
        super().setUp()
        git(self.repo, "checkout", "-q", "nightly")
        self.write(self.WORLD + "tunables_0001.sql", "INSERT 1 WRONGLY EDITED;\n")
        digest = hashlib.sha1(self.APPLIED.encode()).hexdigest().upper()
        self.write(SQL + "/applied_migrations_dev.csv",
                   "path,sha1,provenance\ndb-world/updates/tunables_0001.sql," + digest + ",confirmed on dev\n"
                   "db-world/updates/reserved_0001.sql,,\"reserved on dev, branch x\"\n")
        self.commit("nightly holds a wrongly edited file and the deploy's record of the original")
        git(self.repo, "checkout", "-q", "w/branch")
        git(self.repo, "merge", "-q", "--no-edit", "nightly")

    def test_putting_back_the_applied_bytes_is_green(self):
        self.write(self.WORLD + "tunables_0001.sql", self.APPLIED)
        self.assertGreen()

    def test_any_other_change_is_still_red(self):
        self.write(self.WORLD + "tunables_0001.sql", "SOMETHING ELSE;\n")
        self.assertRed(self.WORLD + "tunables_0001.sql")

    def test_a_branch_cannot_list_its_own_edit(self):
        edited = "MY OWN EDIT;\n"
        self.write(self.WORLD + "tunables_0001.sql", edited)
        digest = hashlib.sha1(edited.encode()).hexdigest().upper()
        self.write(SQL + "/applied_migrations_dev.csv",
                   "path,sha1,provenance\ndb-world/updates/tunables_0001.sql," + digest + ",confirmed on dev\n")
        self.commit("the branch edits the file and records the edit as applied")
        self.assertRed(self.WORLD + "tunables_0001.sql")

    def test_a_delete_is_red_even_when_the_file_has_a_recorded_hash(self):
        (self.repo / (self.WORLD + "tunables_0001.sql")).unlink()
        self.assertRed(self.WORLD + "tunables_0001.sql")


class RefChoice(FixtureRepo):
    def test_a_missing_ref_is_not_found(self):
        self.assertEqual(existing_refs(self.repo), ["nightly"])

    def test_the_same_commit_under_both_refs_reports_a_path_once(self):
        git(self.repo, "update-ref", "refs/remotes/origin/nightly", "nightly")
        self.assertEqual(existing_refs(self.repo), ["nightly", "origin/nightly"])
        self.write(self.WORLD + "tunables_0001.sql", "x\n")
        found = violations(self.repo)
        self.assertEqual(len(found), 1, found)

    def test_each_ref_is_checked_when_they_differ(self):
        """origin/nightly ahead of a local nightly nobody fast-forwarded: a file only the newer one holds counts."""
        git(self.repo, "checkout", "-q", "nightly")
        self.write(self.WORLD + "items_0020.sql", "NEWER;\n")
        self.commit("pushed")
        git(self.repo, "update-ref", "refs/remotes/origin/nightly", "nightly")
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        git(self.repo, "checkout", "-q", "w/branch")
        git(self.repo, "merge", "-q", "--no-edit", "origin/nightly")
        self.write(self.WORLD + "items_0020.sql", "EDITED;\n")
        self.assertEqual(violations(self.repo, ["nightly"]), [])
        found = violations(self.repo)
        self.assertEqual(len(found), 1, found)
        self.assertIn("origin/nightly", found[0])

    def test_unrelated_history_is_reported_not_passed(self):
        git(self.repo, "checkout", "-q", "--orphan", "orphan")
        git(self.repo, "rm", "-rq", "--cached", ".")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "unrelated")
        found = violations(self.repo, ["nightly"])
        self.assertEqual(len(found), 1, found)
        self.assertIn("shares no history", found[0])


class OneNamedEdit(FixtureRepo):
    """3yvay: one file may change once, from named bytes to named bytes. Nothing else rides on it."""
    NAME = "tunables_0001.sql"
    OLD = "INSERT 1;\n"
    NEW = "INSERT 1 WIDER;\n"

    def entry(self, **changes):
        entry = {"bead": "test", "reason": "test", "old_sha256": hashlib.sha256(self.OLD.encode()).hexdigest(),
                 "new_sha256": hashlib.sha256(self.NEW.encode()).hexdigest()}
        entry.update(changes)
        return {self.WORLD + self.NAME: entry}

    def red(self, edits):
        return violations(self.repo, ["nightly"], edits)

    def test_the_named_change_is_green(self):
        self.write(self.WORLD + self.NAME, self.NEW)
        self.assertEqual(self.red(self.entry()), [])

    def test_without_the_entry_the_same_change_is_red(self):
        self.write(self.WORLD + self.NAME, self.NEW)
        self.assertEqual(len(self.red({})), 1)

    def test_other_bytes_are_red(self):
        self.write(self.WORLD + self.NAME, self.NEW + "MORE;\n")
        self.assertEqual(len(self.red(self.entry())), 1)

    def test_a_changed_new_hash_is_red(self):
        self.write(self.WORLD + self.NAME, self.NEW)
        self.assertEqual(len(self.red(self.entry(new_sha256="0" * 64))), 1)

    def test_a_changed_old_hash_is_red(self):
        self.write(self.WORLD + self.NAME, self.NEW)
        self.assertEqual(len(self.red(self.entry(old_sha256="0" * 64))), 1)

    def test_the_old_bytes_must_be_what_nightly_holds(self):
        git(self.repo, "checkout", "-q", "nightly")
        self.write(self.WORLD + self.NAME, "SOMETHING ELSE ON NIGHTLY;\n")
        self.commit("nightly holds other bytes")
        git(self.repo, "checkout", "-q", "w/branch")
        git(self.repo, "merge", "-q", "--no-edit", "nightly")
        self.write(self.WORLD + self.NAME, self.NEW)
        self.assertEqual(len(self.red(self.entry())), 1)

    def test_it_allows_no_other_file(self):
        self.write(self.WORLD + "items_0002.sql", self.NEW)
        self.assertEqual(len(self.red(self.entry())), 1)

    def test_a_delete_is_still_red(self):
        (self.repo / (self.WORLD + self.NAME)).unlink()
        self.assertEqual(len(self.red(self.entry())), 1)

    def test_a_staged_or_committed_named_change_is_green_too(self):
        self.write(self.WORLD + self.NAME, self.NEW)
        self.commit("the named edit")
        self.assertEqual(self.red(self.entry()), [])

    def test_the_default_list_is_the_one_real_entry_and_well_formed(self):
        self.assertEqual(list(ONE_TIME_EDITS), [SQL + "/db-world/updates/followers_0010_skill_values.sql"])
        entry = ONE_TIME_EDITS[SQL + "/db-world/updates/followers_0010_skill_values.sql"]
        self.assertEqual(sorted(entry), ["bead", "new_sha256", "old_sha256", "reason"])
        self.assertTrue(SHA256.match(entry["old_sha256"]) and SHA256.match(entry["new_sha256"]))
        self.assertNotEqual(entry["old_sha256"], entry["new_sha256"])
        self.assertEqual(entry["bead"], "diablocraft-3yvay")

    def test_the_real_file_is_the_named_bytes_or_untouched(self):
        # Where the named edit lives (this branch) the file is exactly the new bytes; once it is on nightly nothing differs.
        path = REPO / "mod-diablocraft/data/sql/db-world/updates/followers_0010_skill_values.sql"
        entry = ONE_TIME_EDITS[SQL + "/db-world/updates/followers_0010_skill_values.sql"]
        self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), (entry["old_sha256"], entry["new_sha256"]))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(verbosity=2, exit=False).result.wasSuccessful() else 1)

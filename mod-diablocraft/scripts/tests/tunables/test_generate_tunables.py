import tempfile
import unittest
from pathlib import Path

import hashlib
import re

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_tunables import (CATEGORIES, RETIRED, CURRENT_MIGRATION, DataError, FROM_D3, GENERATED_SQL, UPDATE_SQL,
                               MODULE_ROOT, NOT_CATEGORY_FILES, STATE_FILE,
                               current_migration, generate, read_all, sql)

HEADER = "name,d3_value,value,unit,notes\n"


class TunablesGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "data/tunables"
        self.folder.mkdir(parents=True)
        # Explicit, deliberately empty authority; the guard fails closed without it.
        (self.root / "data/sql").mkdir(parents=True, exist_ok=True)
        (self.root / "data/sql/applied_migrations.csv").write_text(
            "path,sha1,provenance\n", encoding="utf-8")
        (self.root / STATE_FILE).write_text(UPDATE_SQL + "\n", encoding="utf-8")

    def write(self, category, body=""):
        path = self.folder / (category + ".csv")
        path.write_text(HEADER + body, encoding="utf-8")
        return path

    # --- the shape section M ships -------------------------------------------

    def test_header_only_files_produce_a_table_and_no_insert(self):
        for category in CATEGORIES:
            self.write(category)
        rows, text = generate(self.root)
        self.assertEqual(rows, [])
        self.assertIn("CREATE TABLE IF NOT EXISTS `dc_tunables`", text)
        self.assertNotIn("INSERT INTO", text)
        self.assertIn("No rows yet", text)
        for folder, name in (("data/generated", GENERATED_SQL),
                             ("data/sql/db-world/updates", UPDATE_SQL)):
            self.assertEqual((self.root / folder / name).read_text(encoding="utf-8"), text)

    def test_row_becomes_one_insert_tuple_in_category_name_order(self):
        self.write("rifts", "rift_close_seconds,,30,seconds,Claude audit row 92\n"
                            "guardian_nova,,3,multiplier,Claude audit row 67\n")
        self.write("loot", "buffer_seconds,,60,seconds,Claude audit row 43 (06-loot L5)\n")
        rows, text = generate(self.root)
        self.assertEqual([(row[0], row[1]) for row in rows],
                         [("loot", "buffer_seconds"), ("rifts", "guardian_nova"),
                          ("rifts", "rift_close_seconds")])
        self.assertIn("('loot', 'buffer_seconds', NULL, 60.0, 'seconds', "
                      "'Claude audit row 43 (06-loot L5)')", text)
        self.assertIn("('rifts', 'rift_close_seconds', NULL, 30.0, 'seconds', "
                      "'Claude audit row 92')", text)

    def test_d3_value_and_blank_value_survive_as_null(self):
        self.write("loot", "magic_find_legendary_pct,10,,percent,drop_rates.csv magic_find\n")
        _, text = generate(self.root)
        self.assertIn("('loot', 'magic_find_legendary_pct', 10.0, NULL, 'percent', "
                      "'drop_rates.csv magic_find')", text)

    # --- the one rule the whole mechanism rests on ---------------------------

    def test_upsert_lets_the_csv_win_and_refreshes_the_rest(self):
        """ruling 2026-09-19: the sheet is the source of truth on every apply.

        COALESCE would keep whatever the table already had, which made a second
        edit to the CSV a silent no-op - the thing this task exists to fix.
        """
        self.write("rifts", "guardian_nova,,3,multiplier,Claude audit row 67\n")
        _, text = generate(self.root)
        self.assertIn("ON DUPLICATE KEY UPDATE `tuned_value` = VALUES(`tuned_value`)", text)
        self.assertNotIn("COALESCE", text)
        self.assertIn("`d3_value` = VALUES(`d3_value`)", text)
        self.assertIn("`unit` = VALUES(`unit`)", text)
        self.assertIn("`notes` = VALUES(`notes`)", text)
        self.assertNotIn("DROP TABLE", text)
        # Only a named retired row is ever deleted (diablocraft-t9fl); the table is never wiped.
        deletes = [line for line in text.splitlines() if line.startswith("DELETE FROM")]
        self.assertEqual(deletes, [f"DELETE FROM `dc_tunables` WHERE `category` = '{category}' AND `name` = '{name}';"
                                   for category, name in RETIRED])

    def test_changed_csv_value_is_what_a_reapply_writes(self):
        """Edit the sheet, regenerate, apply: the new number is what lands."""
        self.write("rifts", "guardian_nova,,3,multiplier,Claude audit row 67\n")
        _, first = generate(self.root)
        self.assertIn("('rifts', 'guardian_nova', NULL, 3.0, 'multiplier', "
                      "'Claude audit row 67')", first)
        self.write("rifts", "guardian_nova,,4.5,multiplier,Claude audit row 67\n")
        _, second = generate(self.root)
        self.assertIn("('rifts', 'guardian_nova', NULL, 4.5, 'multiplier', "
                      "'Claude audit row 67')", second)
        self.assertNotIn(", 3.0, 'multiplier'", second)
        # and the clause that makes the tuple win is still the plain one
        self.assertIn("`tuned_value` = VALUES(`tuned_value`)", second)

    def test_blanked_csv_value_clears_a_scratch_override_to_null(self):
        """A blank `value` is how a number is un-tuned back to d3_value."""
        self.write("loot", "magic_find_legendary_pct,10,25,percent,drop_rates.csv magic_find\n")
        _, first = generate(self.root)
        self.assertIn("('loot', 'magic_find_legendary_pct', 10.0, 25.0, 'percent', "
                      "'drop_rates.csv magic_find')", first)
        self.write("loot", "magic_find_legendary_pct,10,,percent,drop_rates.csv magic_find\n")
        _, second = generate(self.root)
        self.assertIn("('loot', 'magic_find_legendary_pct', 10.0, NULL, 'percent', "
                      "'drop_rates.csv magic_find')", second)
        self.assertIn("`tuned_value` = VALUES(`tuned_value`)", second)

    def applied(self, manifest, name, digest):
        (self.root / "data/sql" / manifest).write_text(
            f"path,sha1,provenance\ndb-world/updates/{name},{digest},test\n", encoding="utf-8")

    def test_a_dev_applied_current_migration_advances_to_the_next_free_number(self):
        """diablocraft-dan0c: dev applied tunables_0014 and the generator stopped every fold after it
        (f4aj1 raised). An applied current file keeps its bytes; a render that differs goes to the next free
        number in both folders and the run records it, in either manifest, live or dev."""
        updates, generated = self.root / "data/sql/db-world/updates", self.root / "data/generated"
        for manifest in ("applied_migrations.csv", "applied_migrations_dev.csv"):
            (self.root / "data/sql/applied_migrations.csv").write_text("path,sha1,provenance\n", encoding="utf-8")
            (self.root / "data/sql/applied_migrations_dev.csv").unlink(missing_ok=True)
            for folder in (updates, generated):
                for old in folder.glob("tunables_*.sql"):
                    old.unlink()
            (self.root / STATE_FILE).write_text("tunables_0014.sql\n", encoding="utf-8")
            self.write("rifts", "guardian_nova,,3,multiplier,Claude audit row 67\n")
            _, first = generate(self.root)
            digest = hashlib.sha1((updates / "tunables_0014.sql").read_bytes()).hexdigest().upper()
            self.applied(manifest, "tunables_0014.sql", digest)

            _, same = generate(self.root)  # applied and unchanged: no new number, nothing written
            self.assertEqual(same, first, manifest)
            self.assertEqual(current_migration(self.root), "tunables_0014.sql", manifest)
            self.assertFalse((updates / "tunables_0015.sql").exists(), manifest)

            self.write("rifts", "guardian_nova,,4.5,multiplier,Claude audit row 67\n")
            _, second = generate(self.root)
            self.assertNotEqual(second, first, manifest)
            self.assertEqual(current_migration(self.root), "tunables_0015.sql", manifest)
            for folder in (updates, generated):
                self.assertEqual((folder / "tunables_0014.sql").read_text(encoding="utf-8"), first, manifest)
                self.assertEqual((folder / "tunables_0015.sql").read_text(encoding="utf-8"), second, manifest)
                self.assertFalse((folder / "tunables_0016.sql").exists(), manifest)

            # 0015 is not applied: the next change renders into it in place, no 0016
            self.write("rifts", "guardian_nova,,6,multiplier,Claude audit row 67\n")
            _, third = generate(self.root)
            self.assertEqual(current_migration(self.root), "tunables_0015.sql", manifest)
            for folder in (updates, generated):
                self.assertEqual((folder / "tunables_0015.sql").read_text(encoding="utf-8"), third, manifest)
                self.assertEqual((folder / "tunables_0014.sql").read_text(encoding="utf-8"), first, manifest)
                self.assertFalse((folder / "tunables_0016.sql").exists(), manifest)

    def test_an_unapplied_current_migration_is_rendered_in_place(self):
        self.write("rifts", "guardian_nova,,3,multiplier,Claude audit row 67\n")
        generate(self.root)
        self.write("rifts", "guardian_nova,,4.5,multiplier,Claude audit row 67\n")
        _, text = generate(self.root)
        self.assertEqual(current_migration(self.root), UPDATE_SQL)
        for folder in ("data/sql/db-world/updates", "data/generated"):
            self.assertEqual([f.name for f in (self.root / folder).glob("tunables_*.sql")], [UPDATE_SQL])
            self.assertEqual((self.root / folder / UPDATE_SQL).read_text(encoding="utf-8"), text)

    def test_the_next_free_number_skips_every_number_in_use(self):
        """Above the current one, any file in the updates folder or the generated one (a gap, 0013, stays
        unused) and any a manifest lists although its file is gone from the tree: each source alone holds
        the highest number once."""
        updates, generated = self.root / "data/sql/db-world/updates", self.root / "data/generated"
        for where in ("updates", "generated", "manifest"):
            for folder in (updates, generated):
                for old in folder.glob("tunables_*.sql"):
                    old.unlink()
            (self.root / STATE_FILE).write_text("tunables_0014.sql\n", encoding="utf-8")
            self.write("rifts", "guardian_nova,,3,multiplier,Claude audit row 67\n")
            generate(self.root)
            digest = hashlib.sha1((updates / "tunables_0014.sql").read_bytes()).hexdigest().upper()
            extra = ""
            if where == "manifest":
                extra = f"db-world/updates/tunables_0017.sql,{'A' * 40},test\n"
            else:
                folder = updates if where == "updates" else generated
                (folder / "tunables_0017.sql").write_text("-- another branch's file\n", encoding="utf-8")
            (self.root / "data/sql/applied_migrations_dev.csv").write_text(
                f"path,sha1,provenance\ndb-world/updates/tunables_0014.sql,{digest},test\n{extra}", encoding="utf-8")
            self.write("rifts", "guardian_nova,,4.5,multiplier,Claude audit row 67\n")
            generate(self.root)
            self.assertEqual(current_migration(self.root), "tunables_0018.sql", where)
            self.assertTrue((updates / "tunables_0018.sql").is_file(), where)
            self.assertFalse((updates / "tunables_0013.sql").exists(), where)
            (self.root / "data/sql/applied_migrations_dev.csv").unlink()

    def test_a_number_dev_applied_from_a_branch_is_skipped(self):
        """diablocraft-2kmef: World's 71kk3 is on dev and dev applied its tunables_0015, but the file is not
        in nightly's tree, so the committed dev manifest holds a reserved row (the path, no hash) and nothing
        else. Fold D, rendering on nightly with 0014 applied, wrote its own 0015; it writes 0016."""
        updates, generated = self.root / "data/sql/db-world/updates", self.root / "data/generated"
        (self.root / STATE_FILE).write_text("tunables_0014.sql\n", encoding="utf-8")
        self.write("rifts", "guardian_nova,,3,multiplier,Claude audit row 67\n")
        generate(self.root)
        digest = hashlib.sha1((updates / "tunables_0014.sql").read_bytes()).hexdigest().upper()
        (self.root / "data/sql/applied_migrations_dev.csv").write_text(
            "path,sha1,provenance\n"
            f"db-world/updates/tunables_0014.sql,{digest},test\n"
            'db-world/updates/tunables_0015.sql,,"reserved on dev, branch: 71kk3"\n', encoding="utf-8")
        self.write("rifts", "guardian_nova,,4.5,multiplier,Claude audit row 67\n")
        generate(self.root)
        self.assertEqual(current_migration(self.root), "tunables_0016.sql")
        for folder in (updates, generated):
            self.assertTrue((folder / "tunables_0016.sql").is_file())
            self.assertFalse((folder / "tunables_0015.sql").exists())   # the branch's file is the branch's
        # without the reserved row the same run takes 0015: the row is what moves it
        for folder in (updates, generated):
            (folder / "tunables_0016.sql").unlink()
        (self.root / "data/sql/applied_migrations_dev.csv").write_text(
            f"path,sha1,provenance\ndb-world/updates/tunables_0014.sql,{digest},test\n", encoding="utf-8")
        (self.root / STATE_FILE).write_text("tunables_0014.sql\n", encoding="utf-8")
        generate(self.root)
        self.assertEqual(current_migration(self.root), "tunables_0015.sql")

    def test_a_missing_or_malformed_state_file_is_refused_and_writes_nothing(self):
        self.write("rifts", "guardian_nova,,3,multiplier,Claude audit row 67\n")
        (self.root / STATE_FILE).unlink()
        with self.assertRaisesRegex(DataError, "current_migration.txt"):
            generate(self.root)
        (self.root / STATE_FILE).write_text("tunables_14.sql\n", encoding="utf-8")
        with self.assertRaisesRegex(DataError, "not a tunables_NNNN.sql name"):
            generate(self.root)
        self.assertEqual(list((self.root / "data/sql").glob("db-world/**/*.sql")), [])

    # --- refusals -------------------------------------------------------------

    def test_unknown_category_file_is_refused(self):
        self.write("barbarian")
        (self.folder / "druid.csv").write_text(HEADER, encoding="utf-8")
        with self.assertRaisesRegex(DataError, "not one of the fifteen categories"):
            read_all(self.root)

    def test_wrong_header_is_refused(self):
        (self.folder / "loot.csv").write_text("name,value,unit,notes\n", encoding="utf-8")
        with self.assertRaisesRegex(DataError, "header is"):
            read_all(self.root)

    def test_bad_name_duplicate_unit_notes_and_number_are_refused(self):
        cases = [
            ("RiftClose,,30,seconds,note\n", "lower_snake_case"),
            # An empty name would collide with the sentinel row dc_tunables.cpp
            # uses to tell an empty table from a failed query.
            (",,30,seconds,note\n", "lower_snake_case"),
            ("a,,1,seconds,note\na,,2,seconds,note\n", "duplicate name"),
            ("a,,1,furlongs,note\n", "unit 'furlongs' is not one of"),
            ("a,,1,seconds,\n", "has no notes"),
            ("a,,oops,seconds,note\n", "'oops' is not a number"),
            ("a,,inf,seconds,note\n", "is not finite"),
            ("a,,1,seconds\n", "4 columns, expected 5"),
        ]
        for body, message in cases:
            with self.subTest(body=body):
                self.write("rifts", body)
                with self.assertRaisesRegex(DataError, message):
                    read_all(self.root)

    def test_blank_lines_are_skipped_and_negatives_are_allowed(self):
        self.write("rifts", "\nportal_z_offset,,-0.5,yards,a downward offset is still a number\n\n")
        rows, text = generate(self.root)
        self.assertEqual(len(rows), 1)
        self.assertIn("-0.5", text)

    def test_quotes_and_backslashes_in_notes_are_escaped(self):
        self.write("ui", "stash_action_range,,6.5,yards,\"the designer's slack, C:\\path\"\n")
        _, text = generate(self.root)
        self.assertIn("'the designer''s slack, C:\\\\path'", text)

    def test_a_refused_csv_writes_no_sql(self):
        self.write("rifts", "a,,oops,seconds,note\n")
        with self.assertRaises(DataError):
            generate(self.root)
        self.assertFalse((self.root / "data/generated" / GENERATED_SQL).exists())
        self.assertFalse((self.root / "data/sql/db-world/updates" / UPDATE_SQL).exists())

    def test_empty_file_without_a_header_is_refused(self):
        (self.folder / "loot.csv").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(DataError, "empty"):
            read_all(self.root)

    # --- the folder as it is in the repo -------------------------------------

    def test_the_repo_folder_holds_the_categories_and_the_own_table_sheets(self):
        """The live folder splits cleanly into categories and skipped sheets.

        Since the Architect's 2026-09-19 move, data/tunables/ holds two kinds of
        file: one CSV per category, and the sheets that came out of data/d3/ but
        kept their own generator and their own runtime table. Every file must be
        exactly one of those - a file that is neither is a typo, and a category
        file that also appears in the skip list would be silently dropped.
        """
        present = {path.name for path in (MODULE_ROOT / "data/tunables").glob("*.csv")}
        categories = {f"{name}.csv" for name in CATEGORIES}
        skipped = set(NOT_CATEGORY_FILES) | {FROM_D3}
        self.assertEqual(categories & skipped, set(),
                         "a skipped sheet cannot also be a category file")
        self.assertEqual(present - categories - skipped, set(),
                         "data/tunables/ holds a CSV that is neither a category "
                         "nor one of the sheets with their own table")
        self.assertEqual(categories - present, set(),
                         "a category has no CSV in data/tunables/")
        rows = read_all(MODULE_ROOT)
        self.assertIn("CREATE TABLE IF NOT EXISTS `dc_tunables`", sql(rows))

    def test_a_sheet_with_its_own_table_is_skipped_not_parsed(self):
        """The skip is by name, and it is what keeps the generator off them.

        ability_tunables.csv has its own header and would fail read_category on
        the first line. Proving the skip means proving that: drop a file with a
        skipped name and a header this generator would refuse, and the run must
        still succeed.
        """
        folder = self.folder
        (folder / "rifts.csv").write_text(
            "name,d3_value,value,unit,notes\nkept,,1,seconds,audit row\n", encoding="utf-8")
        (folder / "ability_tunables.csv").write_text(
            "skill,rune,parameter,value,notes\nWhirlwind,,radius,4,not this generator's\n",
            encoding="utf-8")
        rows = read_all(self.root)
        self.assertEqual([(row[0], row[1]) for row in rows], [("rifts", "kept")])



class FromD3ManifestTests(unittest.TestCase):
    """data/tunables/_from_d3.csv: pulling a published number out of data/d3.

    The manifest is the one thing that crosses between the two folders, so the
    tests are mostly refusals. A generator that guesses here does not fail, it
    writes a wrong number into a table the designer then tunes by hand, and nobody finds
    out until a drop rate is wrong.
    """

    MANIFEST = "source_file,row_key,column,category,name,unit\n"
    SOURCE = ("section,topic,value,off_class_pct,off_class_pct_source\n"
              "smart_loot,off-class drop chance,15% of items,15,this row's own value column\n"
              "smart_loot,stat filtering,prose,,\n")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data/tunables").mkdir(parents=True)
        (self.root / "data/d3").mkdir(parents=True)
        (self.root / "data/tunables/loot.csv").write_text(HEADER, encoding="utf-8")
        self.source("drop_rates.csv", self.SOURCE)

    def source(self, name, body):
        (self.root / "data/d3" / name).write_text(body, encoding="utf-8")

    def manifest(self, body):
        (self.root / "data/tunables" / FROM_D3).write_text(self.MANIFEST + body, encoding="utf-8")

    def refusal(self, body, fragment, source=None):
        if source is not None:
            self.source("drop_rates.csv", source)
        self.manifest(body)
        with self.assertRaises(DataError) as raised:
            read_all(self.root)
        self.assertIn(fragment, str(raised.exception))

    def test_a_sourced_cell_becomes_a_d3_value_with_no_tuned_value(self):
        self.manifest("drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                      "off_class_pct,loot,smart_loot_off_class_pct,percent\n")
        rows = read_all(self.root)
        self.assertEqual(len(rows), 1)
        category, name, d3_value, tuned, unit, notes = rows[0]
        self.assertEqual((category, name, unit), ("loot", "smart_loot_off_class_pct", "percent"))
        self.assertEqual(d3_value, 15.0)
        self.assertIsNone(tuned, "a pulled published number is never seeded as the designer's")
        self.assertIn("from drop_rates.csv:section=smart_loot|topic=off-class drop chance"
                      ".off_class_pct", notes)
        self.assertIn("this row's own value column", notes)
        statement = sql(rows)
        self.assertIn("15.0, NULL", statement)

    def test_the_manifest_is_not_read_as_a_category_file(self):
        self.manifest("")
        self.assertEqual(read_all(self.root), [])

    def test_an_ambiguous_row_key_is_refused(self):
        self.refusal("drop_rates.csv,section=smart_loot,off_class_pct,loot,x,percent\n",
                     "matches 2 rows")

    def test_a_row_key_that_matches_nothing_is_refused(self):
        self.refusal("drop_rates.csv,section=no_such_section,off_class_pct,loot,x,percent\n",
                     "matches 0 rows")

    def test_a_row_key_that_is_not_column_equals_value_is_refused(self):
        self.refusal("drop_rates.csv,smart_loot,off_class_pct,loot,x,percent\n",
                     "is not column=value")

    def test_keying_on_a_column_the_source_has_not_got_is_refused(self):
        self.refusal("drop_rates.csv,chapter=smart_loot,off_class_pct,loot,x,percent\n",
                     "has no column 'chapter'")

    def test_a_missing_numeric_column_is_refused(self):
        self.refusal("drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                     "no_such_column,loot,x,percent\n",
                     "has no column 'no_such_column'")

    def test_an_empty_cell_is_refused_rather_than_defaulted(self):
        self.refusal("drop_rates.csv,section=smart_loot|topic=stat filtering,"
                     "off_class_pct,loot,x,percent\n",
                     "never filled in from memory")

    def test_a_cell_that_is_not_a_number_is_refused(self):
        self.refusal("drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                     "value,loot,x,percent\n",
                     "is not a number")

    def test_a_number_with_no_citation_is_refused(self):
        self.refusal("drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                     "off_class_pct,loot,x,percent\n",
                     "has no citation",
                     source="section,topic,off_class_pct\n"
                            "smart_loot,off-class drop chance,15\n")

    def test_two_manifest_rows_cannot_share_a_name(self):
        self.refusal("drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                     "off_class_pct,loot,twice,percent\n"
                     "drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                     "off_class_pct,loot,twice,percent\n",
                     "duplicate loot/twice")

    def test_a_manifest_row_cannot_shadow_a_category_row(self):
        (self.root / "data/tunables/loot.csv").write_text(
            HEADER + "clash,,1,percent,audit row\n", encoding="utf-8")
        self.refusal("drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                     "off_class_pct,loot,clash,percent\n",
                     "is defined twice")

    def test_an_unknown_source_file_is_refused(self):
        self.refusal("nope.csv,section=smart_loot,off_class_pct,loot,x,percent\n",
                     "does not exist")

    def test_an_unknown_category_or_unit_is_refused(self):
        self.refusal("drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                     "off_class_pct,druid,x,percent\n",
                     "is not one of the categories")
        self.refusal("drop_rates.csv,section=smart_loot|topic=off-class drop chance,"
                     "off_class_pct,loot,x,furlongs\n",
                     "is not one of")

    def test_the_live_manifest_resolves_every_row(self):
        """Every row of the real _from_d3.csv finds its cell and its citation."""
        rows = [row for row in read_all(MODULE_ROOT)
                if row[5].startswith("from ")]
        self.assertTrue(rows, "the live manifest pulled nothing")
        for category, name, d3_value, tuned, unit, notes in rows:
            self.assertIsNotNone(d3_value, f"{category}/{name} pulled no number")
            self.assertIsNone(tuned, f"{category}/{name} seeded a tuned_value")
            self.assertGreater(len(notes.split(", ", 1)[1]), 10,
                               f"{category}/{name} has no real citation")


class ShippedCooldownRows(unittest.TestCase):
    """The respec and tier cooldowns reach the DB as tunables_0002 (q-0930-06, G1, G10); the
    per-player gaps join them in tunables_0003 (G1 gaps, applied and frozen); tunables_0004 (the Artisan and
    Jeweler window rows, diablocraft-488x) is applied and frozen; tunables_0005 (the item affix budgets and
    the dual-wield IAS, diablocraft-geyf) shipped in update 6 and is frozen; tunables_0006 (the Blacksmith's
    two-second bar) is frozen too. tunables_0007 adds the four approved stash-tab prices and is on dev (in release/update-8), so frozen;
    tunables_0008 deletes the retired enchant_material_count row and is applied (live 2026-10-07), so frozen;
    tunables_0009 adds Urshi's rows (diablocraft-z94g) and is applied (update 9, 2026-10-11), so frozen;
    tunables_0010 (diablocraft-hmnei's render) adds the pylon and shrine rows of P1 and P3 (diablocraft-plgq2, diablocraft-7h5tr)
    and the four open zones' entrances, and is frozen as nightly's; tunables_0011 adds pylons P2's rows (diablocraft-eok78) and is frozen as nightly's;
    tunables_0012 adds pylons P4's 13 rifts rows (diablocraft-0x640) and is frozen as dev applied it (fold E's bytes);
    tunables_0014 is the render dev applied (diablocraft-f4aj1; the generator moves on from it by itself, diablocraft-dan0c; it carries diablocraft-ivtf5's orb picks too: rifts nr_orb_display_id 9701, combat globe_display_id 8365; 0013 is unused)."""
    updates = MODULE_ROOT / "data/sql/db-world/updates"

    # update-2026-10-02-1 (update 6) applied tunables_0005; the PM lists it in applied_migrations.csv with its
    # live hash, until then this pin keeps it frozen.
    SHIPPED_0005_SHA1 = "1d2cf39ebbcef90f37c4b78018a018813bbd2e04"
    # tunables_0010 is nightly's render from diablocraft-hmnei (5a945c22), not yet in applied_migrations.csv: this pin keeps its bytes.
    NIGHTLY_0010_SHA1 = "d489fb93398ec82539378dfe5084d74283e3e0bc"
    # tunables_0011 is nightly's render from diablocraft-eok78 (b1e614fa), not yet applied: this pin keeps its bytes.
    NIGHTLY_0011_SHA1 = "a32b08552c1e207b6837085c6749081ed3c98cda"
    # tunables_0012 is the bytes dev applied (Combat legendary fold E, f0271ebf4; applied_migrations_dev.csv).
    DEV_0012_SHA1 = "a00c39a65e6fabc8658f124a1c823ce6bcfffabb"

    def test_applied_migrations_are_untouched_and_the_current_migration_is_0014_or_later(self):
        # the generator moves current_migration.txt on by itself once dev applies the file (diablocraft-dan0c)
        self.assertGreaterEqual(CURRENT_MIGRATION, "tunables_0014.sql")
        self.assertTrue((self.updates / CURRENT_MIGRATION).is_file())
        self.assertEqual(hashlib.sha1((self.updates / "tunables_0005.sql").read_bytes()).hexdigest(), self.SHIPPED_0005_SHA1)
        for folder in (self.updates, MODULE_ROOT / "data/generated"):
            self.assertEqual(hashlib.sha1((folder / "tunables_0010.sql").read_bytes()).hexdigest(), self.NIGHTLY_0010_SHA1, folder)
            self.assertEqual(hashlib.sha1((folder / "tunables_0011.sql").read_bytes()).hexdigest(), self.NIGHTLY_0011_SHA1, folder)
            self.assertEqual(hashlib.sha1((folder / "tunables_0012.sql").read_bytes()).hexdigest(), self.DEV_0012_SHA1, folder)
        applied = (MODULE_ROOT / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        for name in ("tunables_0001.sql", "tunables_0002.sql", "tunables_0003.sql", "tunables_0004.sql",
                     "tunables_0005.sql", "tunables_0006.sql", "tunables_0008.sql", "tunables_0009.sql"):
            recorded = re.search(re.escape(name) + r",([0-9A-Fa-f]{40}),", applied).group(1)
            actual = hashlib.sha1((self.updates / name).read_bytes()).hexdigest()
            self.assertEqual(actual.upper(), recorded.upper(), name)

    def test_the_current_migration_is_the_current_render_and_mirrored(self):
        rows = read_all(MODULE_ROOT)
        text = sql(rows, RETIRED)
        self.assertEqual((self.updates / CURRENT_MIGRATION).read_text(encoding="utf-8"), text)
        self.assertEqual((MODULE_ROOT / "data/generated" / CURRENT_MIGRATION).read_text(encoding="utf-8"), text)

    def test_the_blacksmith_bar_row_has_exactly_one_owner(self):
        """crafting.csv's blacksmith_cast_seconds reaches the DB through the tunables migration and only there:
        a second INSERT (the catalogue migration used to carry one) would depend on order."""
        row = "'crafting', 'blacksmith_cast_seconds', NULL, 2.0, 'seconds'"
        self.assertIn(row, (self.updates / "tunables_0006.sql").read_text(encoding="utf-8"))
        self.assertNotIn("blacksmith_cast_seconds", (self.updates / "tunables_0005.sql").read_text(encoding="utf-8"))
        owners = [f.name for f in self.updates.glob("*.sql") if "blacksmith_cast_seconds" in f.read_text(encoding="utf-8")]
        # Full-sheet tunables migrations replay the same source; other generators
        # must still not introduce their own owner of this price-independent row.
        # 0013 was never used; 0014 and every number the generator advanced to after it carry the sheet too
        later = [f.name for f in self.updates.glob("tunables_*.sql") if f.name >= "tunables_0014.sql"]
        self.assertEqual(sorted(owners), ["tunables_0006.sql", "tunables_0007.sql", "tunables_0008.sql", "tunables_0009.sql", "tunables_0010.sql",
                                          "tunables_0011.sql", "tunables_0012.sql"] + sorted(later))

    def test_0004_carries_the_window_rows_as_alex_set_them(self):
        text = (self.updates / "tunables_0004.sql").read_text(encoding="utf-8")
        for name, value in (("artisan_burst", 10), ("artisan_per_second", 5),
                            ("jeweler_burst", 10), ("jeweler_per_second", 5)):
            self.assertRegex(text, r"\('crafting', '%s', NULL, %d\.0, 'count'," % (name, value))

    def test_0005_carries_the_affix_budgets_and_the_dual_wield_ias(self):
        text = (self.updates / "tunables_0005.sql").read_text(encoding="utf-8")
        for category, name, d3, tuned in (("combat", "dual_wield_ias_pct", "15.0", "NULL"),
                                          ("loot", "full_roll_primary_affixes", "4.0", "NULL"),
                                          ("loot", "full_roll_secondary_affixes", "2.0", "NULL"),
                                          ("loot", "magic_primary_affixes", "NULL", "1.0"),
                                          ("loot", "magic_secondary_affixes", "NULL", "1.0")):
            self.assertRegex(text, r"\('%s', '%s', %s, %s, '" % (category, name, d3, tuned))

    def test_0003_carries_the_gap_rows(self):
        text = (self.updates / "tunables_0003.sql").read_text(encoding="utf-8")
        for category, name in (("combat", "skill_slot_gap_ms"), ("combat", "passive_slot_gap_ms"),
                               ("paragon", "allocate_gap_ms")):
            self.assertRegex(text, r"\('%s', '%s', NULL, 150\.0, 'milliseconds'," % (category, name))

    def test_0002_stays_as_shipped_and_0003_carries_both_values(self):
        self.assertNotIn("allocate_gap_ms", (self.updates / "tunables_0002.sql").read_text(encoding="utf-8"))
        text = (self.updates / "tunables_0003.sql").read_text(encoding="utf-8")
        self.assertRegex(text, r"\('paragon', 'respec_cooldown_ms', NULL, 1000\.0, 'milliseconds',")
        self.assertRegex(text, r"\('monsters', 'tier_change_cooldown_seconds', NULL, 10\.0, 'seconds',")

    def test_csv_values_are_the_rulings(self):
        by_name = {(row[0], row[1]): row[3] for row in read_all(MODULE_ROOT)}
        self.assertEqual(by_name[("paragon", "respec_cooldown_ms")], 1000.0)
        self.assertEqual(by_name[("monsters", "tier_change_cooldown_seconds")], 10.0)


if __name__ == "__main__":
    unittest.main()

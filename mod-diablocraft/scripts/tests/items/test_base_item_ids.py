"""K1 - base item entry ids are a published contract, not a row position.

`generate_sql.render_base_items` used to hand out `ENTRY_BASE + position` over
the rows sorted by `d3_id`. Adding one base item whose id sorted early moved
every entry after it, and an `item_template` entry is what a stash row, an
equipped item and a mail attachment all point at - so the renumbering would
have silently rewritten what saved characters own.

The sheet `data/d3/base_item_ids.csv` is the contract instead. These tests are
about the two halves of that: today's assignments are preserved exactly, and
the ways of breaking the contract are all rejected.
"""
import csv
import io
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_sql as g

MODULE = g.MODULE_ROOT
D3 = MODULE / "data" / "d3"
GENERATED = MODULE / "data" / "generated"
PUBLISHED = MODULE / "data" / "sql" / "db-world" / "updates" / "0002_dc_base_item.sql"
SHEET = D3 / "base_item_ids.csv"
# The base-item row's field positions with `entry` first: 12 is preset_affixes and 16 is
# designated_class (generate_sql.BASE_ITEM_PRESET_INDEX is the first of them).
DESIGNATED_INDEX = 16
CRAFT_ONLY_INDEX = 17
HELLFIRE_MIGRATION = g.BASE_CRAFT_ONLY_MIGRATION
ADDED_MIGRATION = PUBLISHED.parent / g.ADDED_BASE_MIGRATION


def added_in_migration():
    """{entry: d3_id} of the base items the added-base migration inserts into dc_base_item (the second record of what
    the database was told: 0002 is the first)."""
    text = ADDED_MIGRATION.read_text(encoding="utf-8").split("INSERT INTO `dc_base_item`", 1)[1].split(";\n", 1)[0]
    return {int(entry): d3_id.replace("''", "'") for entry, d3_id in g.re.findall(r"^\((\d+), '((?:[^']|'')*)'", text, g.re.M)}


def sheet_entries(path=SHEET):
    return [int(row["item_entry"]) for row in sheet_rows(path)]


def sheet_rows(path=SHEET):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def base_item_d3_ids():
    with (D3 / "base_items.csv").open(encoding="utf-8-sig", newline="") as stream:
        return [row["d3_id"] for row in csv.DictReader(stream, strict=True)]


class Preservation(unittest.TestCase):
    """The assignments themselves, against both records of what they were."""

    def test_the_sheet_agrees_with_the_migration_the_database_was_given(self):
        published = dict(g.re.findall(r"^\((\d+), '((?:[^']|'')*)'",
                                      PUBLISHED.read_text(encoding="utf-8"), g.re.M))
        self.assertTrue(published, "no rows parsed out of the published migration")
        mapping = {row["d3_id"]: row["item_entry"] for row in sheet_rows()}
        for entry, d3_id in published.items():
            self.assertEqual(mapping.get(d3_id.replace("''", "'")), entry, d3_id)
        # The sheet is 0002's rows and nothing but the rows the added-base migration inserts, at the ids it inserts them at.
        added = added_in_migration()
        self.assertTrue(added, "no rows parsed out of the added-base migration")
        self.assertEqual({int(entry) for entry in published} & set(added), set())
        for entry, d3_id in added.items():
            self.assertEqual(mapping.get(d3_id), str(entry), d3_id)
        self.assertEqual(len(published) + len(added), len(mapping))

    def test_the_generated_rows_are_byte_identical_to_todays(self):
        base_sql, template_sql, count = g.render_base_items(D3 / "base_items.csv")
        self.assertEqual(count, len(base_item_d3_ids()))
        self.assertEqual(base_sql.encode("utf-8"),
                         (GENERATED / "base_items.sql").read_bytes())
        self.assertEqual(template_sql.encode("utf-8"),
                         (GENERATED / "item_template.sql").read_bytes())

    def test_the_generated_rows_match_the_applied_migration_but_for_designations_and_presets(self):
        """0002 is applied and frozen (GitHub #65); only a re-designation or the G1 preset fix may differ.

        #67 re-designated three rows after 0002 shipped (their change reaches the world DB through
        the next crafting_NNNN migration, see below). G1 corrected two authored weapon presets
        (Atrophy wpnfire -> wpnfir, Hallowed Baton wpnholy -> wpnhol), carried by
        items_0017_base_item_weapon_presets.sql; items_0030_base_item_presets.sql (BASE_PRESET_MIGRATION) respelled
        five set shoulders' allres to resall. So the render may differ
        from 0002 in designated_class alone, plus preset_affixes rows that migration names; every entry
        id and every other column must still match.
        """
        base_sql, _, _ = g.render_base_items(D3 / "base_items.csv")
        applied = g.base_item_rows(PUBLISHED.read_text(encoding="utf-8"))
        current = g.base_item_rows(base_sql)
        self.assertEqual(set(current) - set(applied), set(added_in_migration()), "entries added since 0002 are the added migration's")
        self.assertEqual(set(applied) - set(current), set(), "entries removed against 0002")
        current = {entry: current[entry] for entry in applied}
        preset_changes, craft_only_changes, usable_by_changes = {}, {}, {}
        for entry in sorted(applied):
            new, old = current[entry], applied[entry]
            self.assertEqual(len(new), len(old), "row width changed for entry %d" % entry)
            for position, (a, b) in enumerate(zip(new, old)):
                if position == CRAFT_ONLY_INDEX and a != b:
                    craft_only_changes[entry] = a
                if position == g.BASE_ITEM_USABLE_BY_INDEX and a != b:
                    usable_by_changes[entry] = a
                if a == b or position in (g.BASE_ITEM_PRESET_INDEX, DESIGNATED_INDEX, CRAFT_ONLY_INDEX,
                                          g.BASE_ITEM_USABLE_BY_INDEX):
                    continue
                self.fail("base item %d: column %d differs from 0002 beyond "
                          "designated_class/preset_affixes/craft_only/usable_by" % (entry, position))
            if new[g.BASE_ITEM_PRESET_INDEX] != old[g.BASE_ITEM_PRESET_INDEX]:
                preset_changes[entry] = new[g.BASE_ITEM_PRESET_INDEX]
        # Hellfire Ring and Amulet became craft-only after 0002 shipped (diablocraft-0vt07.15): that column reaches the
        # world DB through its own migration, which names exactly the rows that differ.
        self.assertEqual(craft_only_changes, {100943: "yes", 101113: "yes"})
        marked = (PUBLISHED.parent / HELLFIRE_MIGRATION).read_text(encoding="utf-8")
        for entry in craft_only_changes:
            self.assertRegex(marked, r"SET `craft_only`='yes' WHERE `entry` IN \([\d, ]*\b%d\b" % entry)
        # The Shaman was listed on the draft's weapon types after 0002 shipped (diablocraft-xnrvn.3): usable_by reaches
        # the world DB through its own migration, and what it adds is her key alone.
        self.assertTrue(usable_by_changes)
        usable = (PUBLISHED.parent / g.BASE_USABLE_BY_MIGRATION).read_text(encoding="utf-8")
        for entry, value in usable_by_changes.items():
            self.assertTrue(value.endswith(";shaman") and value.count("shaman") == 1, (entry, value))
            self.assertRegex(usable, r"SET `usable_by`='%s' WHERE `entry` IN \([\d, ]*\b%d\b" % (value, entry))
        # The newest preset migration repeats every earlier one's UPDATEs (the respelling in items_0030 holds G1's too).
        migration = (PUBLISHED.parent / g.BASE_PRESET_MIGRATION).read_text(encoding="utf-8")
        for entry, value in preset_changes.items():
            self.assertIn("SET `preset_affixes`='%s' WHERE `entry`=%d;" % (value, entry), migration,
                          "every preset difference must ship in the base-preset migration")

    def test_the_craft_only_migration_is_what_the_generator_writes(self):
        """items_0056 is generated, not hand-written (diablocraft-j6g2v): rendering base_items.csv against the
        applied 0002 gives the committed file byte for byte, so nothing but generate_sql.py can have made it."""
        base_sql, _, _ = g.render_base_items(D3 / "base_items.csv")
        with tempfile.TemporaryDirectory() as scratch:
            written = g.emit_base_item_craft_only_delta(MODULE, base_sql, pathlib.Path(scratch))
            self.assertIsNotNone(written, "the CSV marks craft_only rows 0002 does not")
            self.assertEqual(written.name, g.BASE_CRAFT_ONLY_MIGRATION)
            self.assertEqual(written.read_bytes(), (PUBLISHED.parent / g.BASE_CRAFT_ONLY_MIGRATION).read_bytes())

    def test_a_craft_only_change_in_the_csv_yields_the_update(self):
        """Flip craft_only on one drop-pool row and on one craft-only row: the first becomes a 'yes' UPDATE and
        the second a 'no' one, against the applied 0002; with the CSV as it was, only the committed rows remain."""
        with (D3 / "base_items.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, strict=True))
            fields = list(rows[0])
        ids = {row["d3_id"]: int(row["item_entry"]) for row in sheet_rows()}
        dropped = next(row for row in rows if row["craft_only"] == "no")
        kept = next(row for row in rows if row["craft_only"] == "yes")
        dropped["craft_only"], kept["craft_only"] = "yes", "no"
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            (root / "data" / "d3").mkdir(parents=True)
            (root / "data" / "sql" / "db-world" / "updates").mkdir(parents=True)
            shutil.copyfile(PUBLISHED, root / "data" / "sql" / "db-world" / "updates" / PUBLISHED.name)
            for name in ("base_item_ids.csv", "item_display.csv"):
                shutil.copyfile(D3 / name, root / "data" / "d3" / name)
            flipped = root / "data" / "d3" / "base_items.csv"
            with flipped.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            flipped_sql, _, _ = g.render_base_items(flipped)
            changes = dict(g.base_item_changes(MODULE, flipped_sql, g.BASE_ITEM_CRAFT_ONLY_INDEX))
            self.assertEqual(changes[ids[dropped["d3_id"]]], "yes")
            self.assertEqual(changes[ids[kept["d3_id"]]], "no")
            written = g.emit_base_item_craft_only_delta(MODULE, flipped_sql, root)
            text = written.read_text(encoding="utf-8")
        self.assertIn("UPDATE `dc_base_item` SET `craft_only`='no' WHERE `entry` IN (%d);" % ids[kept["d3_id"]], text)
        self.assertRegex(text, r"SET `craft_only`='yes' WHERE `entry` IN \([\d, ]*\b%d\b" % ids[dropped["d3_id"]])

    def test_the_migrations_carry_every_designation(self):
        """Applied in name order, the migrations leave the CSV's designations.

        0002 creates the rows; each crafting migration then sets pool_version
        and designated_class for every row. A CSV designation edited without a
        new migration (the generator refusing to rewrite an applied one)
        would leave the world DB on the old value; this catches that.
        """
        updates = PUBLISHED.parent
        final = {}
        pattern = g.re.compile(r"^UPDATE dc_base_item SET pool_version='(?:yes|no)',"
                               r"designated_class='([a-z]*)' WHERE d3_id='((?:[^']|'')*)';$", g.re.M)
        for path in sorted(updates.glob("crafting_*.sql")):
            for designation, d3_id in pattern.findall(path.read_text(encoding="utf-8")):
                final[d3_id.replace("''", "'")] = designation
        with (D3 / "base_items.csv").open(encoding="utf-8", newline="") as stream:
            sheet = {row["d3_id"]: row["designated_class"] for row in csv.DictReader(stream)}
        # A base added after the crafting migrations is inserted with its designation, by the added-base migration.
        added = set(added_in_migration().values())
        self.assertEqual(set(final) | added, set(sheet))
        self.assertEqual(set(final) & added, set())
        stale = {d3_id: (final[d3_id], wanted) for d3_id, wanted in sheet.items() if d3_id in final and final[d3_id] != wanted}
        self.assertEqual(stale, {}, "migrated designation != base_items.csv; run generate_crafting.py")


class Rejections(unittest.TestCase):
    """Every way of breaking the contract, each one its own defect.

    The fixture is the real data copied into a temp tree, not a miniature, so a
    rejection here is the rejection the generator would actually make.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        self.d3 = root / "data" / "d3"
        self.d3.mkdir(parents=True)
        for name in ("base_items.csv", "base_item_ids.csv", "item_display.csv"):
            shutil.copyfile(D3 / name, self.d3 / name)
        updates = root / "data" / "sql" / "db-world" / "updates"
        updates.mkdir(parents=True)
        shutil.copyfile(PUBLISHED, updates / "0002_dc_base_item.sql")
        self.items = self.d3 / "base_items.csv"
        self.sheet = self.d3 / "base_item_ids.csv"

    def render(self):
        return g.render_base_items(self.items)

    def rewrite_sheet(self, rows):
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["d3_id", "item_entry"])
        for row in rows:
            writer.writerow([row["d3_id"], row["item_entry"]])
        self.sheet.write_text(out.getvalue(), encoding="utf-8")

    def test_the_fixture_renders_before_anything_is_broken(self):
        # Without this, a test below could pass because the fixture was wrong.
        base_sql, _, _ = self.render()
        self.assertEqual(base_sql.encode("utf-8"),
                         (GENERATED / "base_items.sql").read_bytes())

    def test_a_base_item_with_no_entry_is_rejected(self):
        rows = sheet_rows(self.sheet)
        dropped = rows.pop(400)
        self.rewrite_sheet(rows)
        with self.assertRaisesRegex(g.DataError, r"no item_entry for .*%s" % dropped["d3_id"]):
            self.render()

    def test_a_duplicated_d3_id_is_rejected(self):
        rows = sheet_rows(self.sheet)
        rows.append({"d3_id": rows[7]["d3_id"], "item_entry": "150000"})
        self.rewrite_sheet(rows)
        with self.assertRaisesRegex(g.DataError, "duplicate d3_id"):
            self.render()

    def test_two_items_sharing_an_entry_are_rejected(self):
        rows = sheet_rows(self.sheet)
        rows[9]["item_entry"] = rows[8]["item_entry"]
        self.rewrite_sheet(rows)
        with self.assertRaisesRegex(g.DataError, "is already"):
            self.render()

    def test_renumbering_a_published_entry_is_rejected(self):
        rows = sheet_rows(self.sheet)
        rows[3]["item_entry"] = "150000"
        self.rewrite_sheet(rows)
        with self.assertRaisesRegex(g.DataError, "append-only and never renumbered"):
            self.render()

    def test_swapping_two_published_entries_is_rejected(self):
        # Neither id is missing and neither is duplicated; only the pairing moved.
        rows = sheet_rows(self.sheet)
        rows[5]["item_entry"], rows[6]["item_entry"] = rows[6]["item_entry"], rows[5]["item_entry"]
        self.rewrite_sheet(rows)
        with self.assertRaisesRegex(g.DataError, "append-only and never renumbered"):
            self.render()

    def test_dropping_a_published_item_from_the_sheet_is_rejected(self):
        # Removing it from BOTH sheets passes the coverage check, so the
        # published migration is the only thing that still objects.
        rows = sheet_rows(self.sheet)
        gone = rows.pop(11)["d3_id"]
        self.rewrite_sheet(rows)
        text = self.items.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        kept = [text[0]] + [line for line in text[1:] if not line.startswith(gone + ",")]
        self.assertEqual(len(kept), len(text) - 1)
        self.items.write_text("".join(kept), encoding="utf-8")
        with self.assertRaisesRegex(g.DataError, "never removed"):
            self.render()

    def test_an_entry_inside_the_shell_block_is_rejected(self):
        rows = sheet_rows(self.sheet)
        rows[2]["item_entry"] = str(g.SHELL_ENTRY_BASE)
        self.rewrite_sheet(rows)
        with self.assertRaisesRegex(g.DataError, "item_entry must be between"):
            self.render()

    def test_a_non_numeric_entry_is_rejected(self):
        rows = sheet_rows(self.sheet)
        rows[2]["item_entry"] = "100000.5"
        self.rewrite_sheet(rows)
        with self.assertRaisesRegex(g.DataError, "whole number"):
            self.render()


class PublishedAuthority(unittest.TestCase):
    """The immutability check must never pass by having nothing to check.

    Found by the PM on the first version: a missing, empty or malformed
    published migration returned 0 and every append-only guarantee quietly
    stopped being enforced - failing open exactly when something had already
    gone wrong with the migration. A check with no authority is not a weaker
    check, it is no check.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.mapping = g.read_base_item_ids(SHEET, set())
        self.published = PUBLISHED.read_text(encoding="utf-8")

    def authority(self, text=None, name="0002_dc_base_item.sql"):
        path = self.root / name
        if text is not None:
            path.write_text(text, encoding="utf-8")
        return path

    def test_the_real_authority_passes_and_checks_every_published_row(self):
        # The positive half. Without it, every test below could pass because
        # the check rejects everything, which would be just as broken.
        checked = g.check_published_item_entries(self.mapping, PUBLISHED, SHEET)
        self.assertEqual(checked, len(sheet_rows()) - len(added_in_migration()))
        self.assertEqual(checked, self.published.count("\n(")
                         + self.published.startswith("("))

    def test_a_missing_authority_fails(self):
        with self.assertRaisesRegex(g.DataError, "migration is missing"):
            g.check_published_item_entries(self.mapping, self.authority(), SHEET)

    def test_an_empty_authority_fails(self):
        with self.assertRaisesRegex(g.DataError, "not a dc_base_item migration"):
            g.check_published_item_entries(self.mapping, self.authority(""), SHEET)

    def test_a_malformed_authority_fails(self):
        text = "-- truncated by a bad merge\nSET NAMES utf8mb4;\n"
        with self.assertRaisesRegex(g.DataError, "not a dc_base_item migration"):
            g.check_published_item_entries(self.mapping, self.authority(text), SHEET)

    def test_an_authority_for_the_wrong_table_fails(self):
        text = "INSERT INTO `item_template` VALUES\n(100000, 'Amulet16', 'x');\n"
        with self.assertRaisesRegex(g.DataError, "not a dc_base_item migration"):
            g.check_published_item_entries(self.mapping, self.authority(text), SHEET)

    def test_an_authority_whose_header_survives_but_whose_rows_do_not_fails(self):
        # The nastiest shape: it still looks like the right migration.
        text = "INSERT INTO `dc_base_item` (`entry`) VALUES\n-- rows lost\n"
        with self.assertRaisesRegex(g.DataError, "no published .* rows could be parsed"):
            g.check_published_item_entries(self.mapping, self.authority(text), SHEET)

    def test_rows_the_parser_cannot_read_are_not_silently_skipped(self):
        lines = self.published.splitlines(True)
        broken = ["".join([line[:8], line[8:].replace(", '", " '", 1)])
                  if line.startswith("(") and index % 2 else line
                  for index, line in enumerate(lines)]
        with self.assertRaisesRegex(g.DataError, r"parsed \d+ published rows but the file has"):
            g.check_published_item_entries(self.mapping, self.authority("".join(broken)), SHEET)

    def test_an_authority_that_publishes_one_id_twice_fails(self):
        first = self.published.index("\n(") + 1
        row = self.published[first:self.published.index("\n", first) + 1]
        text = self.published[:first] + row + self.published[first:]
        with self.assertRaisesRegex(g.DataError, "is published twice"):
            g.check_published_item_entries(self.mapping, self.authority(text), SHEET)

    def test_the_generator_itself_refuses_to_render_without_the_authority(self):
        # End to end, not just the helper: the wiring has to fail too.
        d3 = self.root / "data" / "d3"
        d3.mkdir(parents=True)
        for name in ("base_items.csv", "base_item_ids.csv", "item_display.csv"):
            shutil.copyfile(D3 / name, d3 / name)
        (self.root / "data" / "sql" / "db-world" / "updates").mkdir(parents=True)
        with self.assertRaisesRegex(g.DataError, "migration is missing"):
            g.render_base_items(d3 / "base_items.csv")


class Appending(unittest.TestCase):
    """The point of the whole change: a new item moves nothing."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        self.d3 = root / "data" / "d3"
        self.d3.mkdir(parents=True)
        for name in ("base_items.csv", "base_item_ids.csv", "item_display.csv"):
            shutil.copyfile(D3 / name, self.d3 / name)
        updates = root / "data" / "sql" / "db-world" / "updates"
        updates.mkdir(parents=True)
        shutil.copyfile(PUBLISHED, updates / "0002_dc_base_item.sql")
        self.items = self.d3 / "base_items.csv"
        self.sheet = self.d3 / "base_item_ids.csv"

    def add_item(self, d3_id, entry):
        """Copy an existing row under a new d3_id that sorts FIRST."""
        text = self.items.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        header = text[0].rstrip("\n").split(",")
        model = next(csv.reader([text[1]]))
        model[header.index("d3_id")] = d3_id
        out = io.StringIO(newline="")
        csv.writer(out, lineterminator="\n").writerow(model)
        self.items.write_text("".join(text) + out.getvalue(), encoding="utf-8")
        with self.sheet.open("a", encoding="utf-8", newline="") as stream:
            csv.writer(stream, lineterminator="\n").writerow([d3_id, entry])

    def entries_of(self, sql):
        return {d3_id: int(entry) for entry, d3_id
                in g.re.findall(r"^\((\d+), '((?:[^']|'')*)'", sql, g.re.M)}

    def test_an_appended_item_takes_the_next_id_and_moves_nothing(self):
        before = self.entries_of(g.render_base_items(self.items)[0])
        highest = max(before.values())
        # "AAA..." sorts before every real d3_id, which is exactly the case
        # that used to renumber all 1114 rows.
        self.add_item("AAA_new_base_item", highest + 1)
        after = self.entries_of(g.render_base_items(self.items)[0])

        self.assertEqual(after["AAA_new_base_item"], highest + 1)
        self.assertEqual(len(after), len(before) + 1)
        del after["AAA_new_base_item"]
        self.assertEqual(after, before, "an existing base item was renumbered")

    def test_the_old_rule_would_have_renumbered_them(self):
        # The defect this task removes, stated as a fact rather than a memory:
        # by position-in-sorted-order, a first-sorting insert moves everything.
        ids = sorted(base_item_d3_ids())
        was = {d3_id: g.ENTRY_BASE + position for position, d3_id in enumerate(ids)}
        now = {d3_id: g.ENTRY_BASE + position
               for position, d3_id in enumerate(sorted(ids + ["AAA_new_base_item"]))}
        moved = [d3_id for d3_id in ids if was[d3_id] != now[d3_id]]
        self.assertEqual(len(moved), len(ids))

    def test_the_delete_span_still_covers_an_out_of_order_append(self):
        highest = max(int(row["item_entry"]) for row in sheet_rows(self.sheet))
        self.add_item("AAA_new_base_item", highest + 1)
        _, template_sql, _ = g.render_base_items(self.items)
        # The DELETE is one range per run of consecutive entries (the set caches sit in the gap between the shipped base items
        # and the ones added since): it covers every entry, the appended one included, and nothing in a gap.
        spans = [(int(a), int(b)) for a, b in g.re.findall(r"DELETE FROM `item_template` WHERE `entry` BETWEEN (\d+) AND (\d+);",
                                                          template_sql)]
        entries = set(sheet_entries(self.sheet))
        covered = {e for a, b in spans for e in range(a, b + 1)}
        self.assertEqual(covered, entries)
        self.assertIn(highest + 1, covered)


if __name__ == "__main__":
    unittest.main(verbosity=2)

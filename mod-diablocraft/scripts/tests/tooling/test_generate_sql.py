import contextlib
import csv
import io
from pathlib import Path
import re
import shutil
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_sql
from generate_sql import (DataError, MODULE_ROOT, SHELL_ENTRY_BASE, SHELL_RARITIES, SHELL_SLOTS, TABLES,
                          generate, render_table, render_unidentified_shells, render_world_areas)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        scratch = MODULE_ROOT.parent / 'azerothcore-wotlk/build/_agent-scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='generator-test-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Explicit, deliberately empty authority: the guard fails closed on a
        # missing manifest, and an empty one means nothing is applied yet.
        (self.root / "data/sql").mkdir(parents=True, exist_ok=True)
        (self.root / "data/sql/applied_migrations.csv").write_text(
            "path,sha1,provenance\n", encoding="utf-8")

    def fixture(self, contents):
        path = self.root / "sample.csv"
        path.write_bytes(contents.encode("utf-8"))
        return path

    def test_numeric_precision_percentages_and_text(self):
        path = self.fixture("amount,life,xp_pct,notes,full_text\n"
                            '5000000000,62.5%,8590%,"30% untouched","O\'Brien, \\path"\n'
                            ',187.5%,0%,,"two\nlines"\n')
        sql, count = render_table(path, ("amount", "life xp_pct", "notes full_text"))
        self.assertEqual(count, 2)
        self.assertIn("`amount` BIGINT NULL", sql)
        self.assertIn("`life_pct` DECIMAL(4,1) NULL", sql)
        self.assertNotIn("xp_pct_pct", sql)
        self.assertIn("(5000000000, 62.5, 8590, '30% untouched',", sql)
        self.assertIn("(NULL, 187.5, 0, '',", sql)
        self.assertIn("4f27427269656e2c205c70617468", sql)
        self.assertIn("74776f0a6c696e6573", sql)

    def test_bad_first_or_later_numeric_value_reports_row(self):
        for contents, line in [("level\nnot-a-number\n1\n", 2),
                               ("level\n1\n2oops\n", 3)]:
            with self.subTest(contents=contents):
                with self.assertRaisesRegex(DataError, rf"sample.csv:{line}:.*expected number"):
                    render_table(self.fixture(contents), ("level", "", ""))

    def test_invalid_csv_and_missing_percentage_unit(self):
        for contents in ['value\n"unterminated\n', 'value\n1,2\n', 'value\n\n', 'value\n100\n']:
            with self.subTest(contents=contents):
                with self.assertRaises(DataError) as caught:
                    render_table(self.fixture(contents), ("", "value", ""))
                self.assertIn("Row:", str(caught.exception))

    def test_world_area_rules_reject_invalid_or_ambiguous_rows(self):
        header = "map_id,area_id,phase_scope,status,note\n"
        sql, count = render_world_areas(self.fixture(header + "1,876,all,open,GM Island\n"))
        self.assertEqual(count, 1)
        self.assertIn("(1, 876, 'all', 'open', 'GM Island')", sql)
        for row in ("1.5,876,all,open,test", "1,876,unknown,open,test",
                    "1,876,all,typo,test", ",876,all,open,test",
                    "1,876,all,open,test\n1,876,tier,closed,duplicate"):
            with self.subTest(row=row), self.assertRaisesRegex(DataError, "Row:"):
                render_world_areas(self.fixture(header + row + "\n"))

    def test_unidentified_shells_carry_no_limit(self):
        """P1 diablocraft-unid-shell-unique (ruling 2026-10-02): a second shell of
        the same slot and rarity must be pickable.

        Every shell renders maxcount 0 (the render used to write 1, which the core
        answers with EQUIP_ERR_ITEM_MAX_COUNT - reported to the player as the stock
        "Inventory is full."), the applied renders keep the 1 they were written
        with because they are immutable, and the change reaches a live database
        from the next-numbered items migration.
        """
        sql, count = render_unidentified_shells()
        self.assertEqual(count, len(SHELL_SLOTS) * len(SHELL_RARITIES))
        rows = re.findall(r"^\((.+)\)[,;]?$", sql, re.M)
        self.assertEqual(len(rows), count)
        for row in rows:
            fields = [field.strip() for field in row.split(",")]
            # entry, class, subclass, name, displayid, Quality, InventoryType,
            # ItemLevel, RequiredLevel, maxcount, stackable, bonding, spellid_1,
            # spelltrigger_1, description.
            self.assertEqual(len(fields), 15, row)
            self.assertEqual(fields[9], "0", "a shell must carry no limit: " + row)
            # stackable stays 1: in this core GetMaxStackSize() returns 0x7FFFFFFE
            # for Stackable <= 0 (ItemTemplate.h:729), so 0 means unlimited stacking.
            self.assertEqual(fields[10], "1", "a shell stacks one per slot: " + row)

        applied = (MODULE_ROOT / "data/sql/db-world/updates/items_0007_unidentified_shells.sql").read_text(
            encoding="utf-8")
        applied_entries = re.findall(r"^\((\d+), ", applied, re.M)
        self.assertEqual(len(applied_entries), count, "the applied render is the source of the limit")
        self.assertIn(", 1, 1, 0, 81203", applied, "and it still carries maxcount 1, as it was written")

        manifest = (MODULE_ROOT / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertIn("items_0007_unidentified_shells.sql", manifest,
                      "items_0007 is applied: it is never rewritten, the fix lands in a new migration")
        updates = MODULE_ROOT / "data/sql/db-world/updates"
        # Pinned BY NAME: the file is what shipped, whatever items migration follows it.
        path = updates / "items_0014_unidentified_shells_no_limit.sql"
        self.assertTrue(path.is_file(), "items_0014_unidentified_shells_no_limit.sql carries the change")
        migration = path.read_text(encoding="utf-8")
        self.assertEqual(len(applied_entries), 28, "the 28 shells the limit was written on")
        self.assertIn("SET `maxcount`=0 WHERE `maxcount`=1", migration)
        updates = [line for line in migration.splitlines() if line.startswith("UPDATE ")]
        self.assertTrue(updates, "the migration updates the rows")
        for line in updates:
            self.assertNotIn("stackable", line,
                             "stackable must not move: 1 already means one per slot in this core")
        for entry in applied_entries:
            self.assertIn(entry, migration, "every shell the limit was written on is named")

    def test_reruns_are_identical_and_validation_precedes_writes(self):
        shutil.copytree(MODULE_ROOT / "data/d3", self.root / "data/d3")
        shutil.copytree(MODULE_ROOT / "data/tunables", self.root / "data/tunables")
        published = Path("data/sql/db-world/updates/0002_dc_base_item.sql")
        (self.root / published).parent.mkdir(parents=True)
        shutil.copyfile(MODULE_ROOT / published, self.root / published)
        # The frozen class-start migration the legacy-character render compares
        # the sheet against (diablocraft-class-parity, Q2 option a).
        for frozen_starts in ("world_0012_class_starts.sql", "world_0040_class_starts.sql", "world_0048_class_starts.sql",
                             "world_0060_class_starts.sql", "world_0066_class_starts.sql", "world_0072_class_starts.sql",
                             "world_0078_class_starts.sql"):
            shutil.copyfile(MODULE_ROOT / "data/sql/db-world/updates" / frozen_starts,
                            self.root / "data/sql/db-world/updates" / frozen_starts)
        # And the applied template renders the Miscellaneous-armor subclass
        # UPDATEs are computed against (items_0009/items_0010).
        for frozen in ("0002_dc_item_template.sql", "items_0007_unidentified_shells.sql"):
            shutil.copyfile(MODULE_ROOT / "data/sql/db-world/updates" / frozen,
                            self.root / "data/sql/db-world/updates" / frozen)
        # 0002 is applied (as in the repo): frozen, so the rows base_items.csv holds beyond it are the added-base
        # migration's and a rerun finds the same split.
        import applied_migrations
        rows = ["path,sha1,provenance"] + [
            "db-world/updates/%s,%s,seeded as applied for the rerun test" % (
                name, applied_migrations.sha1((self.root / "data/sql/db-world/updates" / name).read_bytes()))
            for name in ("0002_dc_base_item.sql", "0002_dc_item_template.sql")]
        (self.root / "data/sql/applied_migrations.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            counts = generate(self.root)
            snapshot = {path.relative_to(self.root): path.read_bytes()
                        for path in self.root.rglob("*.sql")}
            # The existing 36 outputs plus the generated/applied class-starts
            # pair and the class-keyed base-stats pair (diablocraft-wizard-resource),
            # the seeded frozen world_0012 and the class-start legacy companion
            # (diablocraft-class-parity), and the seeded applied 0002 template
            # and items_0007 shell renders; 0002 is read, no longer written, and
            # the subclass UPDATEs are items_0009/items_0010, AllowableClass items_0011,
            # the item descriptions items_0013 and the shells' carry-limit fix
            # items_0014 (the 46th and 47th outputs), plus G1's new item outputs
            # in this root (the weapon-class table, the affix pool's weapon rows
            # and their data/generated mirror), and items_0020, the set pieces' wear
            # lock (diablocraft-9rhz), and items_0021, the base items' vendor sell price
            # (diablocraft-item-base-sell-price), and items_0022, where a sheathed weapon hangs
            # (diablocraft-b3gs1), and the seeded applied world_0040 (diablocraft-1cuvw: the
            # Monk's world_0048 profile renders against both), and items_0028, who may wear what once the Monk is
            # in class_map.csv, and the seeded applied world_0048, world_0060, world_0066 and world_0072 (the Necromancer's world_0060, the
            # Crusader's world_0066, the Demon Hunter's world_0072 and the Witch Doctor's world_0078 profiles render against them), and the added-base migration (the Shaman's item types,
            # diablocraft-xnrvn.3) for the rows base_items.csv holds beyond 0002, and (0002 being seeded as applied) its preset, craft_only
            # and usable_by delta migrations, and the seeded applied world_0078 (the Shaman's world_0087 profile renders against it); the pinned
            # count moves with them.
            self.assertEqual(len(snapshot), 63)
            self.assertIn(Path("data/sql/db-world/updates") / generate_sql.ADDED_BASE_MIGRATION, snapshot)
            self.assertIn(Path("data/sql/db-world/updates") / generate_sql.ADDED_WEAR_MIGRATION, snapshot)
            self.assertIn(Path("data/sql/db-world/updates/items_0020_set_wear_class.sql"), snapshot)
            self.assertIn(Path("data/sql/db-world/updates/items_0022_item_sheath.sql"), snapshot)
            self.assertIn(Path("data/sql/db-world/updates/items_0021_item_sell_price.sql"), snapshot)
            self.assertIn(Path("data/sql/db-world/updates/items_0013_item_descriptions.sql"), snapshot)
            self.assertIn(Path("data/sql/db-characters/updates") / generate_sql.CLASS_START_LEGACY_MIGRATION, snapshot)
            self.assertIn(Path("data/sql/db-world/updates/items_0009_item_template_misc_armor.sql"), snapshot)
            self.assertEqual(snapshot[Path("data/generated/class_base_stats.sql")],
                             snapshot[Path("data/sql/db-world/updates") / generate_sql.CLASS_BASE_MIGRATION])
            class_starts = Path("data/generated/class_starts.sql")
            class_migration = Path("data/sql/db-world/updates") / generate_sql.CLASS_START_MIGRATION
            self.assertIn(class_starts, snapshot)
            self.assertIn(class_migration, snapshot)
            self.assertEqual(snapshot[class_starts], snapshot[class_migration])
            self.assertEqual(counts["paragon_xp"], 800)
            self.assertEqual(counts["base_items"], 1117)
            for name in TABLES:
                self.assertEqual(snapshot[Path(f"data/generated/{name}.sql")],
                                 snapshot[Path(f"data/sql/db-world/updates/0001_dc_{name}.sql")])
            generate(self.root)
            self.assertEqual(snapshot, {path.relative_to(self.root): path.read_bytes()
                                       for path in self.root.rglob("*.sql")})
            path = self.root / "data/d3/barbarian_passives.csv"
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.reader(stream))
            rows[-1][1] = "invalid-level"
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerows(rows)
            with self.assertRaisesRegex(DataError, "invalid-level"):
                generate(self.root)
            self.assertEqual(snapshot, {path.relative_to(self.root): path.read_bytes()
                                       for path in self.root.rglob("*.sql")})


if __name__ == "__main__":
    unittest.main()

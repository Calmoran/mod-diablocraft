"""The legendary power table is what the generator renders, in both places it is committed.

One check for the whole table, in place of the copy every item test carried:

  * `data/generated/legendary_powers_NNNN_table.sql` and the migration of the same name in `data/sql/db-world/updates` are
    byte for byte what `generate_legendary_powers.render` writes from the sheets;
  * that migration is the newest full table, it is the only one in `data/generated`, and `scripts/fixture_mysql.sh` applies it.

The number is read from the one generated file, so a renumber edits no test. An item test keeps only what is its own: its
sheet row, its rules and the extra lines about an earlier table.  `Planted` feeds `problems` a table with each of these
broken in turn and requires it to say so.

    python mod-diablocraft/scripts/tests/legendaries/test_legendary_powers_table.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
GENERATED = MODULE / "data/generated"
UPDATES = MODULE / "data/sql/db-world/updates"
FIXTURE = MODULE / "scripts/fixture_mysql.sh"
PATTERN = "legendary_powers_*_table.sql"


def problems(rendered, generated, updates, fixture_text):
    """What is wrong with the committed tables next to `rendered` (the generator's output); [] when all is as it should be."""
    out = []
    here = sorted(p.name for p in generated.glob(PATTERN))
    if len(here) != 1:
        return ["data/generated holds %d full tables, it must hold exactly one: %s" % (len(here), here)]
    name = here[0]
    newest = sorted(p.name for p in updates.glob(PATTERN))
    if not newest or newest[-1] != name:
        out.append("the newest migration is %s, the generated table is %s" % (newest[-1] if newest else None, name))
    if name[:-len(".sql")] not in fixture_text:
        out.append("scripts/fixture_mysql.sh does not apply %s" % name)
    if rendered != (generated / name).read_text(encoding="utf-8"):
        out.append("data/generated/%s is not what the generator renders" % name)
    migration = updates / name
    if not migration.is_file():
        out.append("the migration %s is missing" % name)
    elif rendered != migration.read_text(encoding="utf-8"):
        out.append("the migration %s is not what the generator renders" % name)
    return out


class Table(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = generator.render(MODULE)

    def test_generated_and_migration_are_what_the_generator_renders(self):
        name = next(p.name for p in GENERATED.glob(PATTERN))
        self.assertEqual(self.rendered, (GENERATED / name).read_text(encoding="utf-8"))
        self.assertEqual(self.rendered, (UPDATES / name).read_text(encoding="utf-8"))

    def test_the_migration_is_the_newest_full_table(self):
        self.assertEqual([], problems(self.rendered, GENERATED, UPDATES, FIXTURE.read_text(encoding="utf-8")))


class Planted(unittest.TestCase):
    NAME = "legendary_powers_0100_table.sql"
    TEXT = "-- the rendered table\n"

    def folders(self, **changes):
        """A tiny generated folder and updates folder; `changes` break one thing in them."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        generated, updates = root / "generated", root / "updates"
        generated.mkdir()
        updates.mkdir()
        (generated / self.NAME).write_text(changes.get("generated", self.TEXT), encoding="utf-8")
        if changes.get("migration", self.TEXT) is not None:
            (updates / self.NAME).write_text(changes.get("migration", self.TEXT), encoding="utf-8")
        (updates / "legendary_powers_0099_table.sql").write_text("-- older\n", encoding="utf-8")
        for extra in changes.get("extra_generated", ()):
            (generated / extra).write_text(self.TEXT, encoding="utf-8")
        for extra in changes.get("extra_updates", ()):
            (updates / extra).write_text(self.TEXT, encoding="utf-8")
        return generated, updates

    def check(self, fixture="x legendary_powers_0100_table y", **changes):
        generated, updates = self.folders(**changes)
        return problems(self.TEXT, generated, updates, fixture)

    def test_a_table_that_is_all_right_is_all_right(self):
        self.assertEqual([], self.check())

    def test_each_broken_thing_is_seen(self):
        broken = {
            "the generated table differs from the render": dict(generated=self.TEXT + "-- edited\n"),
            "the migration differs from the render": dict(migration=self.TEXT + "-- edited\n"),
            "the migration is missing": dict(migration=None),
            "a second full table in data/generated": dict(extra_generated=["legendary_powers_0099_table.sql"]),
            "a newer migration than the generated table": dict(extra_updates=["legendary_powers_0101_table.sql"]),
        }
        for label, changes in broken.items():
            with self.subTest(label):
                self.assertNotEqual([], self.check(**changes), label + " was not seen")
        with self.subTest("the fixture does not apply it"):
            self.assertNotEqual([], self.check(fixture="x legendary_powers_0099_table y"))
        with self.subTest("no generated table"):
            generated, updates = self.folders()
            (generated / self.NAME).unlink()
            self.assertNotEqual([], problems(self.TEXT, generated, updates, "legendary_powers_0100_table"))


if __name__ == "__main__":
    unittest.main()

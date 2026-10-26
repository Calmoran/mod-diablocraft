"""The item power table's text columns are wide enough for what the generator writes, and the newest render really applies to a MySQL server.

Dev stopped at startup on `legendary_powers_0067_table.sql`: "ERROR 1406: Data too long for column fire_skills at row 234". Vambraces of Sescheron's
fire_skills list is longer than the column's VARCHAR(255), and nothing in the tests applied a render to a real server, so it got through.

  * **The widths.** generate_legendary_powers.py makes the table from one COLUMN_WIDTHS map and checks every row against it (`check_widths`): a cell longer than its
    column fails the generator, whichever text column it is in. Every VARCHAR column of the newest render is in the map at its width, and every row of the sheet
    fits.
  * **The server.** The render of every full-table migration from 0067 on (they replace the table and apply in order) is applied, in order, to a scratch database
    on the fixture mysqld, with the server's strict mode on, and the rows come back whole. The same render with the old width of fire_skills is refused
    by the server (a planted mutant: the test proves it would have caught the dev failure).

    python mod-diablocraft/scripts/tests/legendaries/test_legendary_powers_columns.py
"""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
UPDATES = MODULE / "data/sql/db-world/updates"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
FIRST_UNAPPLIED = 67          # 0067 on: dev's updater refused it, so none of them has applied anywhere (the widths are re-rendered in place)
DATABASE = "dc_columns_check_%d" % os.getpid()
VARCHAR = re.compile(r"(\w+) VARCHAR\((\d+)\)")


def full_tables():
    out = []
    for path in sorted(UPDATES.glob("legendary_powers_*_table.sql")):
        number = int(re.search(r"_(\d{4})_", path.name)[1])
        if number >= FIRST_UNAPPLIED:
            out.append(path)
    return out


def mysql(*sql_args, stdin=None):
    defaults = fixture_db.defaults_file()
    return subprocess.run([fixture_db.mysql_exe(), "--defaults-file=" + str(defaults), "--no-login-paths", *sql_args],
                          input=stdin, capture_output=True, text=True)


def ensure_server():
    if mysql("-e", "SELECT 1").returncode != 0:
        subprocess.run(["bash", str(MODULE / "scripts/fixture_mysql.sh"), "start"], capture_output=True, text=True)
    ping = mysql("-e", "SELECT 1")
    assert ping.returncode == 0, "the fixture mysqld is not answering (mod-diablocraft/scripts/fixture_mysql.sh start): " + ping.stderr.strip()


class Widths(unittest.TestCase):
    def test_every_varchar_column_of_the_render_is_in_the_map_at_its_width(self):
        found = dict((name, int(width)) for name, width in VARCHAR.findall(GENERATED.read_text(encoding="utf-8").split("INSERT INTO")[0]))
        self.assertEqual(generator.COLUMN_WIDTHS, found)

    def test_the_row_sheet_fits(self):
        table = generator.rows(MODULE)
        generator.check_widths(table)
        longest = max(len(row[13]) for row in table)
        self.assertGreater(longest, 255)                       # Vambraces of Sescheron's list: why the column is wider
        self.assertLessEqual(longest, generator.COLUMN_WIDTHS["fire_skills"])

    def test_a_cell_over_its_column_fails_the_generator_in_every_text_column(self):
        names = generator.COLUMN_ORDER
        row = ["O", 0, "skill", "S", "stat", 1.0, 1.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0]
        for column, width in generator.COLUMN_WIDTHS.items():
            at = names.index(column)
            fits, over = list(row), list(row)
            fits[at], over[at] = "x" * width, "x" * (width + 1)
            with self.subTest(column):
                generator.check_widths([tuple(fits)])
                with self.assertRaisesRegex(ValueError, "%s is %d characters, over the table's VARCHAR\\(%d\\)" % (column, width + 1, width)):
                    generator.check_widths([tuple(over)])

    def test_the_check_runs_before_the_render_is_written(self):
        source = Path(generator.__file__).read_text(encoding="utf-8")
        body = source[source.index("def render("):source.index("def generate(")]
        self.assertLess(body.index("check_widths(table)"), body.index("sql = ("))


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_server()
        cls.addClassCleanup(lambda: mysql("-e", "DROP DATABASE IF EXISTS `%s`" % DATABASE))

    def setUp(self):
        mysql("-e", "DROP DATABASE IF EXISTS `%s`; CREATE DATABASE `%s`" % (DATABASE, DATABASE))

    def apply(self, text):
        return mysql("--database=" + DATABASE, stdin=text)

    def test_the_full_table_renders_from_0067_on_apply_in_order_and_the_rows_come_back_whole(self):
        files = full_tables()
        self.assertGreaterEqual(len(files), 2)
        self.assertEqual(GENERATED.name, files[-1].name)
        self.assertEqual(GENERATED.read_bytes(), files[-1].read_bytes())
        for path in files:
            run = self.apply(path.read_text(encoding="utf-8"))
            self.assertEqual(0, run.returncode, "%s: %s" % (path.name, run.stderr.strip()))
        got = mysql("--database=" + DATABASE, "-N", "-e", "SELECT COUNT(*), MAX(CHAR_LENGTH(fire_skills)) FROM dc_legendary_power").stdout.split()
        self.assertEqual(len(generator.rows(MODULE)), int(got[0]))
        self.assertEqual(max(len(row[13]) for row in generator.rows(MODULE)), int(got[1]))     # the longest list is stored whole, not cut

    def test_the_old_width_is_refused_by_the_server(self):
        text = GENERATED.read_text(encoding="utf-8")
        old = text.replace("fire_skills VARCHAR(%d)" % generator.COLUMN_WIDTHS["fire_skills"], "fire_skills VARCHAR(255)")
        self.assertNotEqual(text, old)
        run = self.apply(old)
        self.assertNotEqual(0, run.returncode)
        self.assertIn("Data too long for column 'fire_skills'", run.stderr)


if __name__ == "__main__":
    unittest.main()

"""diablocraft-set-class-drop - the set_classes.csv sheet and its generator.

The sheet is checked against D3Planner's set data independently of the generator: every row's
cited line must be the line that names that class (or, for a classless set, the set's own name
line with no class key before the next set), the sheet must cover exactly the sets
base_items.csv has, and regenerating must change nothing. The drop distribution itself is
test_class_roll_rules.py; this proves the data it runs on.
"""
import csv
import pathlib
import re
import subprocess
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[2]
MODULE = SCRIPTS.parent
ROOT = MODULE.parent
sys.path.insert(0, str(SCRIPTS))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_set_class as gen  # noqa: E402

PLANNER = ROOT / "reference" / "d3planner" / "data_itemsets.js"
SHEET = MODULE / "data" / "d3" / "set_classes.csv"


def sheet_rows():
    with SHEET.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


class Sheet(unittest.TestCase):
    def test_every_cited_line_says_what_the_row_says(self):
        lines = PLANNER.read_text(encoding="utf-8").splitlines()

        def norm(text):
            return text.replace("\\u2019", "'").replace("\u2019", "'")

        def set_block(number):
            """(first, last) 1-based line numbers of the set that contains line `number`."""
            first = next(i for i in range(number, 0, -1) if re.match(r"^  \w+: \{$", lines[i - 1]))
            last = next((i for i in range(number + 1, len(lines) + 1) if re.match(r"^  \w+: \{$", lines[i - 1])), len(lines))
            return first, last - 1

        for row in sheet_rows():
            with self.subTest(set=row["set_name"]):
                number = int(row["source"].rsplit(":", 1)[1])
                first, last = set_block(number)
                block = lines[first - 1:last]
                names = [norm(m.group(1)) for m in (re.match(r'^    name: "(.*)",$', l) for l in block) if m]
                self.assertEqual(names, [norm(row["set_name"])], "the cited line is not inside this set")
                classes = [m.group(1) for m in (re.match(r'^    t?class: "(\w+)",$', l) for l in block) if m]
                if row["class_key"]:
                    self.assertRegex(lines[number - 1], r'^    t?class: "%s",$' % row["class_key"])
                    self.assertEqual(classes, [row["class_key"]])
                else:
                    self.assertRegex(lines[number - 1], r'^    name: ')
                    self.assertEqual(classes, [], "a classless set must name no class in the source")

    def test_the_counts_the_report_gives(self):
        rows = sheet_rows()
        self.assertEqual(len(rows), 57)
        self.assertEqual(sum(1 for r in rows if r["class_key"]), 42)
        self.assertEqual(sum(1 for r in rows if not r["class_key"]), 15)
        per_class = {}
        for r in rows:
            if r["class_key"]:
                per_class[r["class_key"]] = per_class.get(r["class_key"], 0) + 1
        self.assertEqual(sorted(per_class.values()), [6] * 7)

    def test_the_sheet_covers_exactly_the_sets_of_base_items(self):
        self.assertEqual([name for name, _ in gen.read_sheet()], [r["set_name"] for r in sheet_rows()])

    def test_a_bad_sheet_is_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            bad = pathlib.Path(folder) / "set_classes.csv"
            bad.write_text("set_name,class_key,source\nCain's Destiny,paladin,reference/d3planner/data_itemsets.js:1\n",
                           encoding="utf-8")
            with self.assertRaises(gen.DataError):
                gen.read_sheet(bad)

    def test_regenerating_writes_nothing_new(self):
        before = subprocess.run(["git", "status", "--short", "--", str(MODULE / "data")], cwd=ROOT, capture_output=True,
                                text=True).stdout
        done = subprocess.run([sys.executable, str(SCRIPTS / "generate/items/generate_set_class.py")], cwd=ROOT, capture_output=True,
                              text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        after = subprocess.run(["git", "status", "--short", "--", str(MODULE / "data")], cwd=ROOT, capture_output=True,
                               text=True).stdout
        self.assertEqual(before, after)

    def test_the_migration_and_the_mirror_are_the_render_of_the_sheet(self):
        sql = gen.render(gen.read_sheet())
        self.assertEqual((MODULE / "data" / "generated" / "set_class.sql").read_text(encoding="utf-8"), sql)
        self.assertEqual((MODULE / "data" / "sql" / "db-world" / "updates" / gen.MIGRATION).read_text(encoding="utf-8"), sql)


if __name__ == "__main__":
    unittest.main()

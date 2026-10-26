"""core-patches/README.md names every patch file, with its link, and links no patch that is not there.

One check for the whole folder: it replaces the README-row pins the 0022, 0025 and 0026 patch tests each carried. A row of a retired
patch has no link and names no file. The check is also run on broken copies of the README and of the folder.

    python3 core-patches/tests/test_readme_rows.py
"""
import re
import unittest
from pathlib import Path

PATCHES = Path(__file__).resolve().parents[1]
ROW = re.compile(r"^\| (\d{4}) \| \[([^\]]+)\]\(([^)]+)\) \|", re.M)


def problems(readme, names):
    """What is wrong between the README text and the patch file names (a set of 'NNNN-x.patch')."""
    out = []
    rows = ROW.findall(readme)
    linked = {name for _, name, _ in rows}
    for number, label, target in rows:
        if label != target:
            out.append("row %s: the link text %s is not its target %s" % (number, label, target))
        if not label.startswith(number + "-"):
            out.append("row %s links %s, which is another number's file" % (number, label))
        if label not in names:
            out.append("row %s links %s, which is not in the folder" % (number, label))
    for name in sorted(names - linked):
        out.append("%s has no README row" % name)
    numbers = [number for number, _, _ in rows]
    if len(numbers) != len(set(numbers)):
        out.append("a patch number has two rows")
    return out


class ReadmeRows(unittest.TestCase):
    readme = (PATCHES / "README.md").read_text(encoding="utf-8")
    names = {path.name for path in PATCHES.glob("[0-9][0-9][0-9][0-9]-*.patch")}

    def test_the_readme_and_the_folder_agree(self):
        self.assertGreater(len(self.names), 10)
        self.assertEqual(problems(self.readme, self.names), [])

    def test_a_patch_with_no_row_is_found(self):
        self.assertIn("9999-new.patch has no README row", problems(self.readme, self.names | {"9999-new.patch"}))

    def test_a_row_whose_file_is_gone_is_found(self):
        gone = sorted(self.names)[0]
        self.assertTrue([p for p in problems(self.readme, self.names - {gone}) if "not in the folder" in p])

    def test_a_row_with_the_wrong_link_is_found(self):
        name = sorted(self.names)[0]
        broken = self.readme.replace("](%s)" % name, "](other.patch)", 1)
        self.assertTrue(problems(broken, self.names))
        renumbered = self.readme.replace("| %s | [%s]" % (name[:4], name), "| 9998 | [%s]" % name, 1)
        self.assertTrue([p for p in problems(renumbered, self.names) if "another number's file" in p])

    def test_a_number_with_two_rows_is_found(self):
        name = sorted(self.names)[0]
        row = next(line for line in self.readme.splitlines() if line.startswith("| %s |" % name[:4]))
        self.assertTrue([p for p in problems(self.readme + row + "\n", self.names) if "two rows" in p])


if __name__ == "__main__":
    unittest.main()

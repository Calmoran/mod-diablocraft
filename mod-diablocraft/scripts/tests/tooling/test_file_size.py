#!/usr/bin/env python3
"""R4: a .cpp or .lua file past 1,500 lines is split along its sections (AGENTS.md "Where code goes").

    python3 mod-diablocraft/scripts/tests/tooling/test_file_size.py

A ratchet. A file newly past LIMIT fails, and so does a file in PAST_LIMIT that grows past the size listed for it.
PAST_LIMIT is the files that were already past the line when the ratchet began, at their size then; each split
bead removes its file's row, and a row for a file now at or under LIMIT (or gone) fails too, so the list only shrinks.

Scanned: every .cpp under mod-diablocraft/src, and every .lua under mod-diablocraft/lua, client-patch/addons/Torment and
client-patch/addons/ElvUI_Torment (tracked, or new and not ignored). Third-party addons (Bartender4, reference/) are not ours.
It also fails when it finds no .cpp or no .lua at all (a count over nothing proves nothing).

Counts physical lines (newline characters, plus a last line with no newline). Headers are not counted: a rules header
is compiled by a harness and kept whole (R6).
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCAN = {".cpp": ["mod-diablocraft/src"],
        ".lua": ["mod-diablocraft/lua", "client-patch/addons/Torment", "client-patch/addons/ElvUI_Torment"]}
LIMIT = 1500
# Past the limit when the ratchet began (nightly 18317d978): path -> lines. A split removes its row.
PAST_LIMIT = {
    "mod-diablocraft/lua/aio/dc_tooltip.lua": 1564,
}


def line_count(path):
    data = Path(path).read_bytes()
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def sizes(tree=REPO):
    """({repo path: lines} for every scanned file, {extension: files seen})."""
    sizes, seen = {}, {}
    for ext, roots in SCAN.items():
        ran = subprocess.run(["git", "-C", str(tree), "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *roots],
                             capture_output=True, text=True, check=True)
        files = [p for p in sorted(set(ran.stdout.split("\0"))) if p.endswith(ext) and (Path(tree) / p).is_file()]
        seen[ext] = len(files)
        sizes.update({p: line_count(Path(tree) / p) for p in files})
    return sizes, seen


def problems(measured, past=PAST_LIMIT, limit=LIMIT):
    """One line per break of the ratchet: a new long file, a listed file that grew, a row that no longer applies."""
    found = []
    for path, lines in sorted(measured.items()):
        if lines > limit and path not in past:
            found.append(f"R4 {path}: {lines} lines, past {limit}; split it along its sections into files of the same folder")
        elif path in past and lines > past[path]:
            found.append(f"R4 {path}: grew from {past[path]} to {lines} lines; a file past {limit} may not grow, split it")
    for path, lines in sorted(past.items()):
        if measured.get(path, 0) <= limit:
            found.append(f"R4 {path}: now {measured.get(path, 'gone')} lines, at or under {limit}; remove its row from PAST_LIMIT")
    return found


class Counter(unittest.TestCase):
    def test_lines_are_counted_the_way_an_editor_shows_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, data, want in (("empty", b"", 0), ("one", b"a", 1), ("two", b"a\nb\n", 2), ("noend", b"a\nb", 2)):
                path = Path(tmp) / name
                path.write_bytes(data)
                self.assertEqual(line_count(path), want, name)

    def test_the_limit_is_past_not_at_and_headers_and_other_trees_do_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            files = {"mod-diablocraft/src/at.cpp": LIMIT, "mod-diablocraft/src/past.cpp": LIMIT + 1,
                     "mod-diablocraft/src/past.h": LIMIT + 9, "mod-diablocraft/lua/aio/at.lua": LIMIT,
                     "mod-diablocraft/lua/aio/past.lua": LIMIT + 1, "client-patch/addons/Torment/past.lua": LIMIT + 2,
                     "client-patch/addons/ElvUI_Torment/past.lua": LIMIT + 3, "client-patch/addons/Bartender4/past.lua": LIMIT + 4}
            for rel, n in files.items():
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / rel).write_text("x\n" * n)
            measured, seen = sizes(tmp)
            self.assertEqual({p for p, n in measured.items() if n > LIMIT},
                             {"mod-diablocraft/src/past.cpp", "mod-diablocraft/lua/aio/past.lua",
                              "client-patch/addons/Torment/past.lua", "client-patch/addons/ElvUI_Torment/past.lua"})
            self.assertEqual(seen, {".cpp": 2, ".lua": 4})


class Ratchet(unittest.TestCase):
    PAST = {"old.cpp": 2000, "split.lua": 1600}

    def test_a_new_long_file_fails(self):
        self.assertEqual(len(problems({"old.cpp": 2000, "split.lua": 1600, "new.lua": LIMIT + 1}, self.PAST)), 1)
        self.assertEqual(problems({"old.cpp": 2000, "split.lua": 1600, "new.cpp": LIMIT}, self.PAST), [])

    def test_a_listed_file_may_shrink_but_not_grow(self):
        self.assertEqual(problems({"old.cpp": 1999, "split.lua": 1600}, self.PAST), [])
        grown = problems({"old.cpp": 2001, "split.lua": 1600}, self.PAST)
        self.assertEqual(len(grown), 1)
        self.assertIn("grew from 2000 to 2001", grown[0])

    def test_a_row_for_a_file_that_is_now_short_or_gone_fails(self):
        self.assertEqual(len(problems({"old.cpp": LIMIT, "split.lua": 1600}, self.PAST)), 1)
        self.assertEqual(len(problems({"old.cpp": 2000}, self.PAST)), 1)


class Tree(unittest.TestCase):
    def test_the_tree_keeps_the_ratchet(self):
        measured, seen = sizes()
        self.assertGreater(seen[".cpp"], 0, "no .cpp found under " + ", ".join(SCAN[".cpp"]))
        self.assertGreater(seen[".lua"], 0, "no .lua found under " + ", ".join(SCAN[".lua"]))
        self.assertEqual(problems(measured), [])


if __name__ == "__main__":
    unittest.main()

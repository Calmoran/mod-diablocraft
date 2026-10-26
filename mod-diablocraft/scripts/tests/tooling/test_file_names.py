#!/usr/bin/env python3
"""R3: a file or folder is named for what it holds, never for a bead, a date or a person (AGENTS.md "Where code goes").

    python3 mod-diablocraft/scripts/tests/tooling/test_file_names.py

Every file and folder under mod-diablocraft/src, lua, scripts and tests (tracked, or new and not ignored) is read
name by name; a name fails when one of its parts is

  * a bead id: `diablocraft-xxxxx`, or a bare 4-5 character id that mixes letters and digits (`ie3xd`, `k0k2`);
  * a date: 2026-10-14, 2026_10_14, 20261014, 2026-10;
  * a person: alex, claude, haiku, deepseek, architect, planner, reviewer, calmoran (the lane and role
    names; `pm_watch.sh` is a tool named for the watch it runs, not for a worker, and stays).

The bead goes in the file's banner comment, not in its name. Not covered: a name that spells an id in words, a bead id
shorter than 4 characters, a name outside those four folders (docs/ keeps its dated files on purpose). A real
word that mixes letters and digits is listed in WORDS below with what it is.
"""
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCAN = ["mod-diablocraft/src", "mod-diablocraft/lua", "mod-diablocraft/scripts", "mod-diablocraft/tests"]

PEOPLE = {"alex", "claude", "haiku", "deepseek", "architect", "planner", "reviewer", "calmoran"}
# A part that is a real word or a standard name with both letters and digits (lower case): name it here with what it is.
WORDS = {
    "utf8": "the encoding",
    "win32": "the Windows API",
    "win64": "the Windows API",
    "lua51": "the Lua version",
}
DATE = re.compile(r"(?<!\d)(?:20\d\d[-_]?[01]\d[-_]?[0-3]\d|20\d\d[-_][01]\d)(?!\d)")
BEAD = re.compile(r"diablocraft-[a-z0-9]+")


def offences(name):
    """[why] for a file or folder name (no slashes)."""
    stem = name
    bad = []
    if BEAD.search(stem):
        bad.append("a bead id (" + BEAD.search(stem).group(0) + ")")
    if DATE.search(stem):
        bad.append("a date (" + DATE.search(stem).group(0) + ")")
    for part in re.split(r"[_\-. ]+", stem):
        low = part.lower()
        if low in PEOPLE:
            bad.append("a person (" + part + ")")
        elif 4 <= len(part) <= 5 and low not in WORDS and re.search(r"\d", part) and re.search(r"[A-Za-z]", part):
            bad.append("a bead id, bare (" + part + ")")
    return bad


def tree_names(tree=REPO):
    """The repo paths under SCAN that git tracks or would add (an ignored file is not code)."""
    ran = subprocess.run(["git", "-C", str(tree), "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *SCAN],
                         capture_output=True, text=True, check=True)
    return sorted(set(path for path in ran.stdout.split("\0") if path))


def findings(paths):
    """[(path, component, why)] for every folder or file name in `paths` that breaks R3."""
    found, seen = [], set()
    for path in paths:
        parts = path.split("/")
        for i, part in enumerate(parts):
            prefix = "/".join(parts[:i + 1])
            if prefix in seen:
                continue
            seen.add(prefix)
            for why in offences(part):
                found.append((prefix, part, why))
    return found


class Checker(unittest.TestCase):
    def test_a_bead_id_in_a_name_is_caught(self):
        for name in ("test_archon_algalon_ie3xd.py", "test_item_power_k0k2.py", "item_power_k0k2", "dc_monk_passives_m6v00.cpp",
                     "test_whirlwind_bladestorm_vz49.py", "fix-diablocraft-pl8fc.md", "diablocraft-xq7ft.csv"):
            self.assertTrue(offences(name), name)
        # a bead named in words has no digit-and-letter part: only the diablocraft-<name> form catches it
        self.assertEqual(offences("potion_diablocraft-shared-cooldown.md"), ["a bead id (diablocraft-shared)"])

    def test_a_date_in_a_name_is_caught(self):
        for name in ("notes-2026-10-14.md", "dump_20261014.csv", "run_2026_10_14.log", "batch-2026-10.csv"):
            self.assertTrue(offences(name), name)

    def test_a_person_in_a_name_is_caught(self):
        for name in ("alex-picks-batch1.csv", "claude_notes.md", "Haiku.py", "deepseek-run.lua", "architect_card.csv"):
            self.assertTrue(offences(name), name)

    def test_a_name_for_what_it_holds_passes(self):
        for name in ("dc_monk_mantras.cpp", "test_item_power_k4.py", "test_wizard_aura_binding.py", "generate_d3_data.py",
                     "pm_watch.sh", "harness.cpp", "dc_combat_internal.h", "test_d3_parity.py", "monster_model_picks.csv",
                     "test_item_power_math.py", "a2.lua", "dc_aio_range.lua", "test_utf8_names.py", "x64"):
            self.assertEqual(offences(name), [], name)

    def test_a_folder_is_named_once_and_a_file_in_it_is_checked_on_its_own(self):
        found = findings(["mod-diablocraft/tests/item_power_k0k2/harness.cpp", "mod-diablocraft/tests/item_power_k0k2/other.cpp"])
        self.assertEqual([path for path, _, _ in found], ["mod-diablocraft/tests/item_power_k0k2"])


class Tree(unittest.TestCase):
    def test_all_four_folders_are_read(self):
        names = tree_names()
        for folder in SCAN:
            self.assertTrue(any(name.startswith(folder + "/") for name in names), folder + " has no file in the scan")

    def test_no_name_under_src_lua_scripts_or_tests_carries_a_bead_a_date_or_a_person(self):
        found = findings(tree_names())
        listing = "\n".join(f"  {path}: {why}" for path, _, why in found)
        self.assertEqual(found, [], "R3: rename to what the file holds (the bead goes in its banner comment):\n" + listing)


if __name__ == "__main__":
    unittest.main()

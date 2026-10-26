#!/usr/bin/env python3
"""Checks for client-extension/wowdecomp: the patch series, then the probes on top of it, apply at the pin.

The apply runs as the workflows run it (apply-patches.ps1): each patch in name order into an index, here a
throwaway index file, so reference/wowdecomp's own index and working tree are never written. Also checks that
both workflows and PINNED.md name the same pin.

Needs reference/wowdecomp checked out at the pin; skips the apply checks without it. Nothing is built.

Run: python3 client-extension/tests/test_wowdecomp_patches.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WOWDECOMP_DIR = HERE.parent / "wowdecomp"
PATCHES = WOWDECOMP_DIR / "patches"
PROBES = WOWDECOMP_DIR / "probes"
PINNED = HERE.parent / "PINNED.md"
WORKFLOWS = [REPO / ".github" / "workflows" / "client-rebuild.yml", REPO / ".github" / "workflows" / "client-rebuild-probe.yml"]


def find_reference() -> Path | None:
    # The main checkout keeps reference/; a worktree reaches it through the main checkout.
    for root in (REPO, Path.home() / "diablocraft"):
        candidate = root / "reference" / "wowdecomp"
        if (candidate / ".git").exists():
            return candidate
    return None


def pin_of(workflow: Path) -> str:
    match = re.search(r"^\s*WOWDECOMP_COMMIT:\s*([0-9a-f]{40})\s*$", workflow.read_text(), re.M)
    assert match, f"{workflow.name} names no WOWDECOMP_COMMIT"
    return match.group(1)


def series(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.patch"), key=lambda p: p.name)


class Pins(unittest.TestCase):
    def test_workflows_and_pinned_name_one_commit(self):
        pins = {pin_of(w) for w in WORKFLOWS}
        self.assertEqual(len(pins), 1, f"the workflows name different pins: {pins}")
        self.assertIn(pins.pop(), PINNED.read_text())


class Apply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = find_reference()
        if cls.reference is None:
            raise unittest.SkipTest("reference/wowdecomp is not checked out")
        cls.pin = pin_of(WORKFLOWS[0])

    def git(self, index: str, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, GIT_INDEX_FILE=index)
        return subprocess.run(["git", "-C", str(self.reference), *args], env=env, capture_output=True, text=True)

    def apply_in_order(self, folders: list[Path]) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            index = os.path.join(scratch, "index")
            read = self.git(index, "read-tree", self.pin)
            self.assertEqual(read.returncode, 0, f"the pin {self.pin} is not in reference/wowdecomp: {read.stderr}")
            for folder in folders:
                for patch in series(folder):
                    result = self.git(index, "apply", "--cached", str(patch))
                    self.assertEqual(result.returncode, 0, f"{folder.name}/{patch.name} does not apply: {result.stderr}")

    def test_series_applies_at_the_pin(self):
        self.apply_in_order([PATCHES])

    def test_probes_apply_on_the_series(self):
        # K0's retype probe is gone: K3 and K4 made its edits for real, so a probe that retypes them no longer applies.
        # The folder stays for the next compile probe (README); with none there is nothing to apply.
        if not series(PROBES):
            self.skipTest("no probe in the folder")
        self.apply_in_order([PATCHES, PROBES])

    def test_probes_move_no_line(self):
        # The probe workflow compares the two trees' diagnostics line for line, so a probe hunk keeps its
        # length: as many lines removed as added.
        for patch in series(PROBES):
            for hunk in re.finditer(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@", patch.read_text(), re.M):
                old, new = hunk.group(1) or "1", hunk.group(2) or "1"
                self.assertEqual(old, new, f"{patch.name}: a hunk changes the line count ({hunk.group(0)})")


def new_file_in_series(path: str) -> str | None:
    """The text a patch of the series adds as the new file at path, or None when none does."""
    for patch in series(PATCHES):
        match = re.search(
            rf"^diff --git a/{re.escape(path)} b/{re.escape(path)}\nnew file mode .*?\n(?:index .*\n)?--- /dev/null\n\+\+\+ b/.*?\n@@ .*? @@\n((?:\+.*\n)*)",
            patch.read_text(),
            re.M,
        )
        if match:
            return "".join(line[1:] + "\n" for line in match.group(1).splitlines())
    return None


def from_pragma(text: str) -> str:
    return text[text.index("#pragma once"):]


class CarriedCode(unittest.TestCase):
    # The rebuilt client carries the Torment module's key table as a copy (the module still builds from
    # client-extension/torment): the two must be the same code below their banners.
    def test_key_table_copy_matches_the_module(self):
        copy = new_file_in_series("Engine/Source/Os/KeyTable.h")
        self.assertIsNotNone(copy, "no patch adds Engine/Source/Os/KeyTable.h")
        module = (HERE.parent / "torment" / "KeyTable.hpp").read_text()
        self.assertEqual(from_pragma(copy), from_pragma(module))


if __name__ == "__main__":
    sys.exit(unittest.main())

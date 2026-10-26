"""Harness tests that build under aura-fixes/ never share a binary path, so run_tests.py's parallel jobs cannot collide.

Two tests building the same `aura-fixes/production` at once failed with
"OSError: [Errno 26] Text file busy" (the PM's full run): one linked over the binary the other was executing.
The tests that write under that folder are found by scanning the tests tree, and each is run twice at the same time
(two jobs of one runner, or a worker's and the Reviewer's worktrees, which share `_agent-scratch`), one round,
alongside every other one. Every run must pass and none may print "Text file busy".
"""
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve()
TESTS = HERE.parents[1]
SHARED = "_agent-scratch/aura-fixes"
ROUNDS = 1
COPIES = 2


def sharing_tests():
    return sorted(path for path in TESTS.rglob("test_*.py")
                  if path != HERE and SHARED in path.read_text(encoding="utf-8"))


def run(path):
    done = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=600)
    return path.name, done.returncode, done.stdout + done.stderr


class SharedScratch(unittest.TestCase):
    def test_the_scan_finds_the_tests_that_write_there(self):
        names = [path.name for path in sharing_tests()]
        for expected in ("test_wizard_marks.py", "test_aura_holds.py"):
            self.assertIn(expected, names)

    def test_parallel_runs_of_those_tests_do_not_collide(self):
        paths = sharing_tests()
        for round_number in range(ROUNDS):
            with ThreadPoolExecutor(max_workers=len(paths) * COPIES) as pool:
                results = list(pool.map(run, paths * COPIES))
            for name, code, output in results:
                busy = [line for line in output.splitlines() if "Text file busy" in line]
                self.assertEqual(busy, [], "round %d: %s" % (round_number, name))
                self.assertEqual(code, 0, "round %d: %s failed:\n%s" % (round_number, name, output[-2000:]))


if __name__ == "__main__":
    unittest.main()

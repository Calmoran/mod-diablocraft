#!/usr/bin/env python3
"""A test that imports scripts_path runs by a direct `python3 <test>.py` the way run_tests.py runs it (R5).

    python3 mod-diablocraft/scripts/tests/tooling/test_direct_run_imports.py

run_tests.py puts mod-diablocraft/scripts on PYTHONPATH; a direct call has only the test's own folder on
sys.path, so a test that does `import scripts_path` must put the scripts root there itself first. For every
test file that imports scripts_path this runs the file's top-level statements up to that import in a fresh
interpreter with no PYTHONPATH and the test's folder first on sys.path (a direct call's), and fails the
file when that raises ModuleNotFoundError.

Not covered: an import that comes later than scripts_path, and a failure in the statements that is not an
import (the test's own run reports those).
"""
import ast
import os
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
TESTS = REPO / "mod-diablocraft/scripts/tests"

RUNNER = r'''
import ast, sys
path = sys.argv[1]
sys.path.insert(0, str(__import__("pathlib").Path(path).parent))
tree = ast.parse(open(path).read(), path)
head = []
for node in tree.body:
    head.append(node)
    if isinstance(node, ast.Import) and any(a.name == "scripts_path" for a in node.names):
        break
module = ast.Module(body=head, type_ignores=[])
exec(compile(module, path, "exec"), {"__file__": path, "__name__": "__direct__"})
'''


def imports_scripts_path(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    return any(isinstance(n, ast.Import) and any(a.name == "scripts_path" for a in n.names) for n in tree.body)


def direct_import_error(path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    ran = subprocess.run([sys.executable, "-c", RUNNER, str(path)], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=120)
    if "ModuleNotFoundError" in ran.stderr:
        return ran.stderr.strip().splitlines()[-1]
    return None


class DirectRun(unittest.TestCase):
    def test_every_test_importing_scripts_path_finds_it_on_a_direct_run(self):
        files = [p for p in sorted(TESTS.glob("*/test_*.py")) if imports_scripts_path(p)]
        self.assertGreater(len(files), 50, "the scan found almost no test that imports scripts_path")
        with ThreadPoolExecutor(max_workers=8) as pool:
            errors = list(pool.map(direct_import_error, files))
        bad = {str(p.relative_to(REPO)): e for p, e in zip(files, errors) if e}
        self.assertEqual(bad, {}, "these tests cannot be run directly: put the scripts root on sys.path before the import")


if __name__ == "__main__":
    unittest.main()

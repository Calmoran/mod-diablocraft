"""scenario_problems.run: a clean run reaches the end of its scenario, a mutant run stops at the first problem.

    python3 mod-diablocraft/scripts/tests/tooling/test_scenario_problems.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import scenario_problems  # noqa: E402


class ScenarioProblems(unittest.TestCase):
    def body(self, steps):
        def body(problems):
            steps.append("one")
            problems.append("first")
            steps.append("two")
            problems.append("second")
            steps.append("three")
        return body

    def test_a_clean_run_collects_every_problem_and_reaches_the_end(self):
        steps = []
        self.assertEqual(scenario_problems.run(self.body(steps)), ["first", "second"])
        self.assertEqual(steps, ["one", "two", "three"])

    def test_a_mutant_run_stops_at_the_first_problem(self):
        steps = []
        self.assertEqual(scenario_problems.run(self.body(steps), first_only=True), ["first"])
        self.assertEqual(steps, ["one"])

    def test_a_scenario_with_no_problem_is_empty_either_way(self):
        for first_only in (False, True):
            self.assertEqual(scenario_problems.run(lambda problems: None, first_only), [])

    def test_an_error_in_the_scenario_is_not_swallowed(self):
        def broken(problems):
            raise RuntimeError("fixture")
        for first_only in (False, True):
            with self.assertRaises(RuntimeError):
                scenario_problems.run(broken, first_only)


if __name__ == "__main__":
    unittest.main()

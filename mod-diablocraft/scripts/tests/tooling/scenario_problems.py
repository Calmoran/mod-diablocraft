"""The problems list of a scenario-plus-mutants test (test_light_check, test_dev_log_check, test_dev_lane).

A scenario states every rule of a script and collects what is wrong. The clean run reads the whole list, so it must
reach the end. A mutant run only has to show one problem, so it stops at the first: `run(body, first_only=True)`
ends the scenario where the first problem is appended.
"""


class _Stop(Exception):
    pass


class _FirstProblem(list):
    def append(self, item):
        super().append(item)
        raise _Stop


def run(body, first_only=False):
    """The problems `body(problems)` found; with first_only, stopped at the first one."""
    problems = _FirstProblem() if first_only else []
    try:
        body(problems)
    except _Stop:
        pass
    return list(problems)

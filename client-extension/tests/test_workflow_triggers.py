#!/usr/bin/env python3
"""The CI workflows only start for what they should (diablocraft-60eq5).

The runners are the designer's PC, so a push must not build for nothing: pushes to nightly that touch the workflow's own
paths, launcher-v* tags, workflow_dispatch and the launcher's Monday audit start a job; a w/* branch, a
client-patch-N-stamp branch and a pull request (a fork's, ever) start none. Read from the YAML, and each pin is
run against a broken copy and must fail on it.

Run: python3 client-extension/tests/test_workflow_triggers.py
"""

from __future__ import annotations

import copy
import pathlib
import unittest

import yaml

WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
BUILDS = ("launcher", "client-extension", "client-rebuild", "client-rebuild-probe")


def triggers(name, root=WORKFLOWS):
    doc = yaml.safe_load((root / (name + ".yml")).read_text(encoding="utf-8"))
    return doc.get("on", doc.get(True))


def problems(name, on):
    """What is wrong with one workflow's triggers, as short sentences (empty when right)."""
    bad = []
    push = on.get("push") or {}
    if push.get("branches") != ["nightly"]:
        bad.append("push is not limited to the nightly branch")
    if not push.get("paths"):
        bad.append("push has no path filter")
    if "workflow_dispatch" not in on:
        bad.append("no workflow_dispatch")
    for event in ("pull_request", "pull_request_target"):
        if event in on:
            bad.append(event + " is on")
    if name == "launcher":
        if push.get("tags") != ["launcher-v*"]:
            bad.append("launcher-v* tags do not build")
        if not on.get("schedule"):
            bad.append("the Monday audit is gone")
    elif "tags" in push or "schedule" in on:
        bad.append("only the launcher builds on tags or a schedule")
    return bad


def runs_on_problems(runs_on):
    """A runs-on that is not exactly self-hosted + one OS label + torment, as a list (labels are case-insensitive)."""
    labels = [runs_on] if isinstance(runs_on, str) else list(runs_on)
    lower = [str(x).lower() for x in labels]
    if len(lower) != 3 or lower[0] != "self-hosted" or lower[2] != "torment" or lower[1] not in ("linux", "windows"):
        return ["runs-on is not [self-hosted, linux|windows, torment]: %s" % labels]
    return []


class Triggers(unittest.TestCase):
    def test_every_workflow_is_right(self):
        for name in BUILDS:
            self.assertEqual(problems(name, triggers(name)), [], name)

    def test_no_workflow_is_missing_from_the_list(self):
        found = sorted(p.stem for p in WORKFLOWS.glob("*.yml"))
        self.assertEqual(found, sorted(BUILDS))

    def test_no_job_runs_on_a_github_hosted_machine(self):
        # q-1021-82: builds on the designer's PC only, no GitHub-hosted fallback (billing stays as it is).
        for name in BUILDS:
            doc = yaml.safe_load((WORKFLOWS / (name + ".yml")).read_text(encoding="utf-8"))
            for job, spec in doc["jobs"].items():
                self.assertEqual(runs_on_problems(spec["runs-on"]), [], name + "/" + job)

    def test_runs_on_pin_fails_on_a_broken_copy(self):
        for broken in ("ubuntu-latest", "windows-latest", ["self-hosted", "linux"], ["linux", "torment"],
                       ["self-hosted", "mac", "torment"], ["ubuntu-latest", "self-hosted", "linux", "torment"]):
            self.assertTrue(runs_on_problems(broken), str(broken))

    def test_a_hand_run_does_nothing_extra_unless_asked(self):
        inputs = triggers("launcher")["workflow_dispatch"]["inputs"]
        self.assertIs(inputs["checks"]["default"], False)
        self.assertEqual(inputs["checks"]["type"], "boolean")

    def test_no_job_runs_sudo(self):
        for name in BUILDS:
            lines = (WORKFLOWS / (name + ".yml")).read_text(encoding="utf-8").splitlines()
            self.assertEqual([l for l in lines if "sudo" in l and not l.lstrip().startswith("#")], [], name)

    def test_the_monday_audit_runs_monday(self):
        self.assertEqual(triggers("launcher")["schedule"], [{"cron": "0 6 * * 1"}])

    def test_each_pin_fails_on_a_broken_copy(self):
        good = triggers("launcher")
        for label, mutate in (
            ("branches", lambda o: o["push"].update(branches=["**"])),
            ("paths", lambda o: o["push"].pop("paths")),
            ("dispatch", lambda o: o.pop("workflow_dispatch")),
            ("pull_request", lambda o: o.update(pull_request={"paths": ["launcher/**"]})),
            ("pull_request_target", lambda o: o.update(pull_request_target={})),
            ("tags", lambda o: o["push"].pop("tags")),
            ("schedule", lambda o: o.pop("schedule")),
        ):
            broken = copy.deepcopy(good)
            mutate(broken)
            self.assertTrue(problems("launcher", broken), label)
        stray = copy.deepcopy(triggers("client-rebuild"))
        stray["push"]["tags"] = ["v*"]
        self.assertTrue(problems("client-rebuild", stray), "a tag trigger on a client workflow")


if __name__ == "__main__":
    unittest.main()

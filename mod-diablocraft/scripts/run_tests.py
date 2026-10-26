#!/usr/bin/env python3
"""One runner for every test script: in parallel, and in the gate only the tests a change can reach.

    python3 mod-diablocraft/scripts/run_tests.py [--tree DIR] [--skip-list CSV] [--jobs N]
                                                 [--gate | --nightly] [--state FILE]
    python3 mod-diablocraft/scripts/run_tests.py --readers FILE [--state FILE]

It is the test step of `release_gate.sh` (docs/proposals/batch-updates.md 5, W3)
and works on its own. Exit 0 only when every selected test that is not on the
skip list passed and the skip list itself is sound. Anything else is red:

  * a test exits non-zero, or runs past --timeout;
  * a skip row has no bead, names a bead `bd` does not know, or names a closed
    bead (the reason is gone: run the test);
  * a skip row or a rules row names a test that no longer exists (a stale row hides
    nothing and means the list is out of date);
  * no test was discovered at all (a runner that finds nothing proves nothing).

Discovery (paths are relative to --tree):
  mod-diablocraft/scripts/test_*.py and mod-diablocraft/scripts/tests/*/test_*.py
  core-patches/tests/test_*.py, .claude/hooks/test_*.py     -> python3
  mod-diablocraft/scripts/test_*.lua, .../tests/*/test_*.lua -> lua
  mod-diablocraft/scripts/test_*.sh, .../tests/*/test_*.sh   -> bash
`test_*.ps1` is Windows-only and is not run here. Each test runs with the tree
root as its working directory; output is kept in --log-dir.

Three ways to run (faster process 3, diablocraft-igq1):
  plain      every test, no state. What a worker or the PM runs by hand.
  --gate     the update gate: only the tests a change can reach, minus the nightly-only ones.
             A test is selected when it has no files recorded, has no pass recorded, is marked
             `always`, or a file it read changed between its last pass and the tree's commit.
  --nightly  every test, each traced with strace, which records the files and folders it
             opened or looked up (the test's files). Nobody waits on it; it refreshes the
             files the gate selects by. A planted failure the gate skipped is caught here.
--gate and --nightly keep their memory in --state (JSON, outside git): the commit each test
last passed at, the files each test read, how long each took. Only a run on a clean git tree
writes it. A failed test loses its pass, so it runs again next time.

--readers FILE  prints the tests whose recorded files include FILE (a repo path), one per line, from
             the same --state (default: the main checkout's test-state/state.json). It runs nothing and
             writes nothing. With no trace for the file it says so and exits 0: that is "no data", never
             "nothing reads it" (a test the nightly has not traced yet, or a read outside the files, is
             invisible).

What the files cannot see: anything a test reads that is not a file of the tree (the
fixture database's rows, installed tools, the core, which git does not hold; the core
is stood in for by core-commit.txt, and for a change of it by the core patches: a test records the core paths
it read, and a changed patch selects it only when the patch touches one of them, or a folder it listed. A
test that ran a core build output (a library, the compile commands) is tied to every patch. The extracted server
data is tied to none). The nightly run covers what files cannot show.

Rules: CSV `test,rule,reason` (test_rules.csv beside the tests in the tree). `rule` is one
or more of, joined with `;`:
  nightly           own-tool test (release, deploy guard, hooks): never in the gate, always nightly
  always            no files tied: runs in every gate
  solo              runs alone, after the parallel ones (a timing test, or one that needs the machine)
  exclusive:<name>  never at the same time as another test with the same name (a shared
                    server, port or folder); everything else still runs in parallel

Skip list: CSV `test,bead,reason`; `test` is the discovered path. A skipped test
is not run. The list is printed in full on every run so a skip is never silent.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SKIPS = Path(__file__).resolve().with_name("release_gate_skips.csv")
BEAD_ID = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)+$")
HEADER = ["test", "bead", "reason"]
RULES_HEADER = ["test", "rule", "reason"]
RULES_FILE = "mod-diablocraft/scripts/test_rules.csv"  # in the tree under test
RULE_WORDS = {"nightly", "always", "solo"}
# A change to the runner itself can change what every test does: the gate runs them all.
RUNS_EVERYTHING = {"mod-diablocraft/scripts/run_tests.py"}
CORE = "azerothcore-wotlk"  # not in git: core-commit.txt stands in for it, the patches for a change of the files they touch
# Folders the python import system scans for every test: an added file there is not a reason to
# rerun a test (the test's own folder is left out the same way).
IMPORT_DIRS = ("mod-diablocraft/scripts", "mod-diablocraft/scripts/generate/*", "mod-diablocraft/scripts/tests/*")
WARN_PREFIX = "WARN "  # a passing test's line that starts with this is a warning
WARN_SHOWN = 20        # per test; the rest stay in its log
IGNORED = (CORE + "/build/_agent-scratch", ".git/", ".beads/", "__pycache__")

# (glob relative to the tree, interpreter argv prefix)
PATTERNS = [
    ("mod-diablocraft/scripts/test_*.py", ["python3"]),
    ("mod-diablocraft/scripts/tests/*/test_*.py", ["python3"]),
    ("core-patches/tests/test_*.py", ["python3"]),
    (".claude/hooks/test_*.py", ["python3"]),
    ("mod-diablocraft/scripts/test_*.lua", ["lua"]),
    ("mod-diablocraft/scripts/tests/*/test_*.lua", ["lua"]),
    ("mod-diablocraft/scripts/test_*.sh", ["bash"]),
    ("mod-diablocraft/scripts/tests/*/test_*.sh", ["bash"]),
]


# Files that match test_*.py but are not tests: each is printed with its reason on every
# run, so leaving one out is never silent. Nothing here is a failing test in hiding.
NOT_TESTS = {}  # empty: the two tools that were listed here are mod-diablocraft/scripts/potion_fixture.py and check_rift_spawn_log.py


def discover(tree):
    found = {}
    for pattern, argv in PATTERNS:
        for path in sorted(tree.glob(pattern)):
            rel = path.relative_to(tree).as_posix()
            if rel not in NOT_TESTS:
                found[rel] = argv
    return dict(sorted(found.items()))


def read_csv(path, header, what):
    """Return (rows, problems). A missing file is an empty list, not an error."""
    if not path.exists():
        return [], []
    rows, problems = [], []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        head = next(reader, None)
        if head != header:
            return [], [f"{path.name}: header must be {','.join(header)}"]
        for number, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != 3 or not all(cell.strip() for cell in row):
                problems.append(f"{path.name}:{number}: {what}")
                continue
            rows.append(dict(zip(header, (cell.strip() for cell in row))))
    return rows, problems


def read_skips(path):
    return read_csv(path, HEADER, "a skip needs test, bead and reason")


def read_rules(path, discovered):
    """Return ({test: {'nightly', 'always', 'solo', 'exclusive'}}, problems)."""
    rows, problems = read_csv(path, RULES_HEADER, "a rule needs test, rule and reason")
    rules = {}
    for row in rows:
        test = row["test"]
        if test not in discovered:
            problems.append(f"stale rule, no such test: {test}")
            continue
        if test in rules:
            problems.append(f"rule listed twice: {test}")
            continue
        found = {"nightly": False, "always": False, "solo": False, "exclusive": None}
        for word in row["rule"].split(";"):
            word = word.strip()
            if word in RULE_WORDS:
                found[word] = True
            elif word.startswith("exclusive:") and len(word) > len("exclusive:"):
                found["exclusive"] = word.split(":", 1)[1]
            else:
                problems.append(f"rule {test}: '{word}' is not nightly, always, solo or exclusive:<name>")
        rules[test] = found
    return rules, problems


def bead_status(bead, command, cwd):
    """The bead's status word, or None when `bd` does not know it."""
    argv = [part.replace("{bead}", bead) for part in command]
    try:
        ran = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if ran.returncode != 0:
        return None
    try:
        data = json.loads(ran.stdout)
    except ValueError:
        return None
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict) or data.get("id") != bead:
        return None
    return str(data.get("status") or "")


def check_skips(rows, discovered, command, cwd):
    problems = []
    seen = set()
    for row in rows:
        test, bead = row["test"], row["bead"]
        if test in seen:
            problems.append(f"skip listed twice: {test}")
        seen.add(test)
        if test not in discovered:
            problems.append(f"stale skip, no such test: {test}")
        if not BEAD_ID.match(bead):
            problems.append(f"skip {test}: '{bead}' is not a bead id")
            continue
        status = bead_status(bead, command, cwd)
        if status is None:
            problems.append(f"skip {test}: bead {bead} is unknown to bd")
        elif status == "closed":
            problems.append(f"skip {test}: bead {bead} is closed, so the skip is stale; run the test")
    return problems


# ---- the files a test read (strace) -----------------------------------------------------------

STRACE = ["strace", "-f", "-y", "-qq", "-s", "4096", "--seccomp-bpf", "-e", "trace=%file"]
# openat(AT_FDCWD</cwd>, "path", flags) and the other dirfd forms; then the plain-path forms.
AT_CALL = re.compile(r'^(\d+)\s+(?:openat2?|newfstatat|statx|faccessat2?|readlinkat)\((AT_FDCWD|\d+)(?:<([^>]*)>)?, "((?:[^"\\]|\\.)*)"(.*)')
PATH_CALL = re.compile(r'^(\d+)\s+(?:open|stat|lstat|access|readlink|execve)\("((?:[^"\\]|\\.)*)"(.*)')


def parse_trace(text, tree, test):
    """(files, dirs, core) the strace text names inside `tree`; files and dirs are tree-relative paths.

    A file is anything the test opened or looked up, found or not (a test that asserts a file is
    absent depends on it). A dir, with a trailing `/`, is a folder it opened to list: the
    files added to or removed from it matter, a change of a file in it does not (that file is its
    own entry if the test read it). A path under the core is not in git: `core` holds the ones the
    test used, relative to the core, and the caller stands core-commit.txt in for the core and the
    patches that touch those paths in for the change.
    """
    tree = str(tree)
    core_real = os.path.realpath(os.path.join(tree, CORE))
    cwd_of = {}
    files, dirs, core = set(), set(), set()
    for line in text.splitlines():
        match = AT_CALL.match(line)
        if match:
            pid, fd, fd_path, path, rest = match.groups()
            if fd == "AT_FDCWD":
                cwd_of[pid] = fd_path or tree
            elif not fd_path:
                continue
            base = fd_path or tree
        else:
            match = PATH_CALL.match(line)
            if not match:
                continue
            pid, path, rest = match.groups()
            base = cwd_of.get(pid, tree)
        if "\\" in path:
            continue
        full = os.path.normpath(path if path.startswith("/") else os.path.join(base, path))
        if full.startswith(core_real + "/"):
            rel = CORE + full[len(core_real):]
        elif full.startswith(tree + "/"):
            rel = full[len(tree) + 1:]
        else:
            continue
        if any(rel.startswith(skip) or ("/" + skip) in "/" + rel for skip in IGNORED):
            continue
        if rel.startswith(CORE + "/"):
            core.add(rel[len(CORE) + 1:])
        elif "O_DIRECTORY" in rest:
            if not any(fnmatch.fnmatchcase(rel, d) for d in IMPORT_DIRS) and rel != os.path.dirname(test):
                dirs.add(rel + "/")
        else:
            files.add(rel)
    return files, dirs, core


def patch_paths(text):
    """The paths a patch's text names, as written (both sides of a rename or copy; /dev/null is none)."""
    found = set()
    for line in text.splitlines():
        if line.startswith(("--- ", "+++ ")):
            names = [line[4:].split("\t")[0]]
        elif line.startswith("diff --git "):
            names = line[len("diff --git "):].split(" ")
        elif line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            found.add(line.split(" ", 2)[2])  # git writes these without the a/ b/ prefix
            continue
        else:
            continue
        found.update(name[2:] if name[:2] in ("a/", "b/") else name for name in names if name != "/dev/null")
    return found


def resolve_patch_paths(paths, tree):
    """`paths` as core-root paths: a patch for a module, or for the AIO checkout, names paths from its own root.

    A path that is not in the core and not already under modules/ is looked up in each module (every match
    counts: a module path is a superset). One that is nowhere (a file the patch adds) takes the module the
    patch's other paths resolved to; one outside the core tree altogether stays as written."""
    core = Path(tree, CORE)
    resolved, modules, loose = set(), set(), []
    for path in sorted(paths):
        resolved.add(path)
        if path.startswith("modules/") or (core / path).exists():
            continue
        found = [hit.relative_to(core).as_posix() for hit in core.glob("modules/*/" + path)]
        if found:
            resolved.update(found)
            modules.update("/".join(hit.split("/")[:2]) for hit in found)
        else:
            loose.append(path)
    for path in loose:
        resolved.update(module + "/" + path for module in modules)
    return resolved


def is_core_patch(path):
    return path.startswith("core-patches/") and path.endswith(".patch") and path.count("/") == 1


def touched_by_patch(tree, sha, path, status):
    """Every core path the patch at `path` touched at `sha` or touches now, or None when it cannot be read."""
    paths = _touched_texts(tree, sha, path, status)
    if paths is None:
        return None
    return resolve_patch_paths(paths, tree)


def _touched_texts(tree, sha, path, status):
    """The paths named by the patch's old and new text (as written), or None when a text cannot be read."""
    found = set()
    if status != "A":
        old = git_out(tree, "show", f"{sha}:{path}")
        if old is None:
            return None
        found |= patch_paths(old)
    if status != "D":
        try:
            found |= patch_paths(Path(tree, path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return None
    return found


def core_reached(core, touched):
    """True when a core path a test read is, or lies above, a path in `touched` (a folder read sees files added in it).

    The empty path is the whole core: a test that ran a build output reaches every patch."""
    if touched is None:
        return True
    reads = set(core)
    for path in touched:
        parts = path.split("/")
        if any("/".join(parts[:n]) in reads for n in range(len(parts) + 1)):
            return True
    return False


# Under the core's build/ folder, the extracted server data and the fixture's database settings do not come from
# the patched sources; everything else there (libraries, compile commands) is built from them.
NOT_BUILT = ("build/server/data/", "build/mysql/")


def reads_built_core(core):
    """True when a core path read is a build output: it changes whenever any patch does."""
    return any(path.startswith("build/") and not path.startswith(NOT_BUILT) for path in core)


def trace_deps(trace_file, tree, rel):
    text = trace_file.read_text(encoding="utf-8", errors="replace") if trace_file.exists() else ""
    files, dirs, core = parse_trace(text, tree, rel)
    files.add(rel)
    deps = {"files": sorted(files | ({"core-commit.txt"} if core else set())), "dirs": sorted(dirs)}
    if core:
        deps["core"] = sorted(core | ({""} if reads_built_core(core) else set()))  # "" is the whole core
    return deps


def readers_of(state_path, tree, name):
    """The test paths whose recorded files include `name` (a repo path, or a path under `tree`).

    For a core patch, also the tests that read a core path the patch touches."""
    name = os.path.normpath(os.path.relpath(name, tree) if os.path.isabs(name) else name)
    deps = load_state(state_path)["deps"]
    touched = touched_by_patch(tree, "", name, "A") if is_core_patch(name) else None
    return sorted(rel for rel, found in deps.items()
                  if name in (found.get("files") or []) or (touched is not None and found.get("core") and core_reached(found["core"], touched))), name


def default_state():
    """The main checkout's shared state, the one the gate and the nightly run use (from any worktree)."""
    common = git_out(REPO, "rev-parse", "--path-format=absolute", "--git-common-dir")
    main = Path(common.strip()).parent if common else REPO
    return main / CORE / "build/_agent-scratch/test-state/state.json"


def run_one(tree, rel, argv, timeout, log_dir, trace=False):
    log = log_dir / (rel.replace("/", "__") + ".log")
    trace_file = log_dir / (rel.replace("/", "__") + ".trace")
    started = time.monotonic()
    # Tests under *-tests/ import the generators that sit in scripts/, which is on
    # sys.path only for a test that lives there.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    scripts = str(tree / "mod-diablocraft" / "scripts")
    env["PYTHONPATH"] = scripts + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = (STRACE + ["-o", str(trace_file)] if trace else []) + argv + [rel]
    try:
        with log.open("wb") as out:
            ran = subprocess.run(command, cwd=tree, stdout=out, stderr=subprocess.STDOUT, env=env,
                                 timeout=timeout, stdin=subprocess.DEVNULL)
        code = ran.returncode
    except subprocess.TimeoutExpired:
        code = "timeout"
    except OSError as error:
        log.write_text(f"could not start {argv[0]}: {error}\n", encoding="utf-8")
        code = "error"
    deps = None
    if trace:
        deps = trace_deps(trace_file, tree, rel)
        trace_file.unlink(missing_ok=True)
    return code, time.monotonic() - started, log, deps


# ---- what the last runs left behind: pass shas, test files, durations ----------------------------

def load_state(path):
    """A missing or unreadable state is an empty one: every test then runs."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {key: data.get(key) if isinstance(data.get(key), dict) else {} for key in ("green", "deps", "seconds")}


def edit_state(path, edit):
    """Read, change and write the state under a lock, so a nightly and a gate never lose each other's rows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state(path)
        edit(state)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)


def git_out(tree, *argv):
    ran = subprocess.run(["git", "-C", str(tree), *argv], capture_output=True, text=True)
    return ran.stdout if ran.returncode == 0 else None


def clean_commit(tree):
    """The tree's commit sha, or None when it is not a git tree or has tracked changes."""
    if git_out(tree, "status", "--porcelain", "--untracked-files=no") != "":
        return None
    sha = git_out(tree, "rev-parse", "HEAD")
    return sha.strip() if sha else None


def changed_since(tree, sha):
    """{path: status letter} between `sha` and the working tree (renames count as delete + add), or None."""
    out = git_out(tree, "diff", "--name-status", "-z", "--no-renames", sha)
    if out is None:
        return None
    parts = out.split("\0")
    return {path: status for status, path in zip(parts[0::2], parts[1::2])}


def changed_core_paths(tree, sha, changed):
    """The core paths the changed patches touch, before or after the change (None when one cannot be read)."""
    found = set()
    for path, status in changed.items():
        if is_core_patch(path):
            touched = touched_by_patch(tree, sha, path, status)
            if touched is None:
                return None
            found |= touched
    return found


def reached_by(deps, changed, touched=frozenset()):
    """The first changed path a test's files cover, else None. `touched` is changed_core_paths for `changed`."""
    files = set(deps.get("files", []))
    for path, status in changed.items():
        if path in files:
            return path
        if status in ("A", "D"):
            for folder in deps.get("dirs", []):
                if path.startswith(folder):
                    return folder + " (" + ("added" if status == "A" else "removed") + " " + path.rsplit("/", 1)[-1] + ")"
    if deps.get("core") and core_reached(deps["core"], touched):
        return next((path for path in changed if is_core_patch(path)), None)
    return None


def select_for_gate(tree, tests, rules, state):
    """Split `tests` into ({test: why it runs}, {test: why it does not})."""
    run, off = {}, {}
    cache = {}
    for rel in tests:
        rule = rules.get(rel, {})
        if rule.get("nightly"):
            off[rel] = "nightly-only"
            continue
        if rule.get("always"):
            run[rel] = "always"
            continue
        deps = state["deps"].get(rel)
        green = state["green"].get(rel, {}).get("sha")
        if not deps:
            run[rel] = "no files recorded"
        elif not green:
            run[rel] = "no pass recorded"
        else:
            if green not in cache:
                changed = changed_since(tree, green)
                cache[green] = (changed, None if changed is None else changed_core_paths(tree, green, changed))
            changed, touched = cache[green]
            if changed is None:
                run[rel] = "last pass is not in this repository"
            elif any(path in RUNS_EVERYTHING for path in changed):
                run[rel] = "the runner changed"
            else:
                hit = reached_by(deps, changed, touched)
                if hit:
                    run[rel] = "changed: " + hit
                else:
                    off[rel] = f"unchanged since its pass at {green[:8]}"
    return run, off


# ---- running them -----------------------------------------------------------------------------

def schedule(selected, rules, seconds):
    """(units, solo): units run side by side, each unit's tests one after another; solo runs last, alone."""
    groups, solo = {}, []
    for rel in selected:
        rule = rules.get(rel, {})
        if rule.get("solo"):
            solo.append(rel)
        else:
            groups.setdefault(rule.get("exclusive") or rel, []).append(rel)
    units = sorted(groups.values(), key=lambda unit: -sum(seconds.get(rel, 20) for rel in unit))
    return units, solo

def warnings_in(path):
    """The lines of a log that start with WARN_PREFIX (a warning from a soft rule)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line for line in text if line.startswith(WARN_PREFIX)]


def tail(path, lines=15):
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return text[-lines:]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tree", type=Path, default=REPO, help="the tree to test (default: this checkout)")
    parser.add_argument("--skip-list", type=Path, default=DEFAULT_SKIPS)
    parser.add_argument("--rules", type=Path, default=None, help=f"default: {RULES_FILE} in the tree")
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=1200, help="seconds per test")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1), help="tests at the same time")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gate", action="store_true", help="only the tests a change can reach, no nightly-only ones")
    mode.add_argument("--nightly", action="store_true", help="every test, traced; refreshes the files the gate selects by")
    mode.add_argument("--readers", metavar="FILE", help="print the tests that read FILE, from the state, and stop")
    parser.add_argument("--state", type=Path, default=None,
                        help="the pass shas, test files and durations (required by --gate and --nightly)")
    parser.add_argument("--bead-cmd", nargs="+", default=["bd", "show", "{bead}", "--json"],
                        help="command that prints a bead as JSON; {bead} is replaced")
    parser.add_argument("--bead-cwd", type=Path, default=REPO, help="where the beads database lives")
    parser.add_argument("--list", action="store_true", help="print what would run and stop")
    args = parser.parse_args(argv)
    if (args.gate or args.nightly) and not args.state:
        parser.error("--gate and --nightly need --state FILE")

    tree = args.tree.resolve()
    if args.readers:
        found, name = readers_of(args.state or default_state(), tree, args.readers)
        print("\n".join(found) if found else f"no trace for {name}: the nightly trace has no test that read it (not the same as no readers)")
        return 0
    discovered = discover(tree)
    rows, problems = read_skips(args.skip_list)
    skips = {row["test"]: row for row in rows}
    problems += check_skips(rows, discovered, args.bead_cmd, args.bead_cwd)
    rules, rule_problems = read_rules(args.rules or tree / RULES_FILE, discovered)
    problems += rule_problems

    if not discovered:
        problems.append(f"no test found under {tree}")
    if args.nightly and not shutil.which(STRACE[0]):
        problems.append("strace is not installed: this run cannot record the files the tests read")
        args.nightly = False

    state = load_state(args.state) if args.state else None
    candidates = [rel for rel in discovered if rel not in skips]
    off = {}
    if args.gate:
        why, off = select_for_gate(tree, candidates, rules, state)
        selected = list(why)
    else:
        why, selected = {}, candidates

    skipped = [rel for rel in discovered if rel in skips]
    print(f"tests: {len(discovered)} discovered, {len(skipped)} skipped")
    for row in rows:
        print(f"  SKIP {row['test']}  [{row['bead']}] {row['reason']}")
    for rel, reason in NOT_TESTS.items():
        if (tree / rel).exists():
            print(f"  NOT A TEST {rel}: {reason}")
    if args.gate:
        nightly = sum(1 for reason in off.values() if reason == "nightly-only")
        print(f"select: {len(selected)} of {len(candidates)} tests (gate: reached by a change since their last pass); "
              f"{len(off) - nightly} unchanged, {nightly} nightly-only")
    if args.list:
        for rel in discovered:
            if rel in skips:
                print("skip " + rel)
            elif rel in off:
                print("off  " + rel + "  (" + off[rel] + ")")
            else:
                print("run  " + rel + (("  (" + why[rel] + ")") if rel in why else ""))
        for problem in problems:
            print(f"RED  {problem}")
        return 1 if problems else 0

    log_dir = args.log_dir or (tree / (CORE + "/build/_agent-scratch/release-gate-logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    warnings = {}  # test -> number of WARN lines in its passing run
    out = threading.Lock()

    def one(rel):
        # A nightly-only test is never selected by the gate, so its files are of no use; tracing the
        # ones that start thousands of processes (the hook tests) made them time out.
        traced = args.nightly and not rules.get(rel, {}).get("nightly")
        code, seconds, log, deps = run_one(tree, rel, discovered[rel], args.timeout, log_dir, trace=traced)
        note = ""
        if traced and code != 0:
            # strace can break a test (a sanitizer binary cannot check leaks under ptrace; a long one times
            # out): the untraced run answers, and the files from the traced one are kept.
            code, seconds, log, _ = run_one(tree, rel, discovered[rel], args.timeout, log_dir)
            note = "  [failed under strace, ran again without it]"
        with out:
            results[rel] = (code, seconds, deps)
            if code == 0:
                warned = warnings_in(log)
                if warned:
                    warnings[rel] = len(warned)
                print(f"PASS {rel} ({seconds:.0f}s)" + (f"  [{why[rel]}]" if rel in why else "") + note
                      + (f"  [{len(warned)} warnings]" if warned else ""), flush=True)
                for line in warned[:WARN_SHOWN]:
                    print("    " + line, flush=True)
                if len(warned) > WARN_SHOWN:
                    print(f"    ... {len(warned) - WARN_SHOWN} more WARN lines in the log: {log}", flush=True)
            else:
                print(f"FAIL {rel} ({seconds:.0f}s, exit {code}) log: {log}", flush=True)
                for line in tail(log):
                    print("    " + line, flush=True)

    units, solo = schedule(selected, rules, state["seconds"] if state else {})
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        list(pool.map(lambda unit: [one(rel) for rel in unit], units))
    for rel in solo:
        one(rel)
    wall = time.monotonic() - started

    failed = [rel for rel, (code, _, _) in results.items() if code != 0]
    passed = len(results) - len(failed)
    if args.state:
        sha = clean_commit(tree)
        if not sha:
            print("state: not updated (the tree is not a clean git commit)")
        else:
            def record(state):
                for rel, (code, seconds, deps) in results.items():
                    state["seconds"][rel] = round(seconds, 1)
                    if deps:
                        state["deps"][rel] = deps
                    if code == 0:
                        state["green"][rel] = {"sha": sha}
                    else:
                        state["green"].pop(rel, None)
                if args.nightly:
                    for table in state.values():
                        for gone in [rel for rel in table if rel not in discovered]:
                            del table[gone]
            edit_state(args.state, record)
            print(f"state: {len(results)} tests recorded at {sha[:8]} in {args.state}")

    for problem in problems:
        print(f"RED  {problem}")
    if warnings:
        plural = "test" if len(warnings) == 1 else "tests"
        print(f"warnings: {sum(warnings.values())} lines from {len(warnings)} {plural} (they do not fail the run)")
    print(f"time: {wall:.0f}s wall for {sum(seconds for _, seconds, _ in results.values()):.0f}s of tests on {args.jobs} jobs")
    print(f"tests: {passed} of {len(results)} passed, {len(failed)} failed, {len(problems)} skip-list problems")
    return 1 if failed or problems else 0


if __name__ == "__main__":
    sys.exit(main())

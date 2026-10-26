"""What the three tests of the Classes legendary fold 3 (Madawc's Sorrow, Saffron Wrap, Fragment of Destiny) share: the generated table, the generator run over a changed sheet and the compiled harness
(tests/item_power_mark_and_stack/harness.cpp) driven with cases. Not a test: pytest-style discovery skips a file that does not start with test_."""
import csv
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_mark_and_stack/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (REPO / name if name.startswith("docs/") else MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(owner, rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == owner]


def render_rows(owner, *sheet_rows, buffs=None):
    """generator.rows over the real module with `owner`'s rows replaced by the given ones (dicts of csv columns)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="markstack-gen-", dir=str(SCRATCH)))
    try:
        shutil.copytree(MODULE / "data/d3", work / "data/d3")
        shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
        if buffs is not None:
            (work / "data/legendary_power_buffs.csv").write_text(buffs, encoding="utf-8")
        sheet = read_csv("data/legendary_powers.csv")
        kept = [r for r in sheet if r["owner"] != owner]
        with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, list(sheet[0].keys()))
            writer.writeheader()
            writer.writerows(kept + list(sheet_rows))
        return generator.rows(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def sheet_row(owner, kind, stat, low, high=None, **cells):
    base = {"owner": owner, "pieces": "", "kind": kind, "skill": "", "stat": stat, "value_min": low, "value_max": high or low, "cond": "", "cond_arg": "",
            "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}
    base.update(cells)
    return base


def drive(cases, header_text, name, run=None):
    """(wanted, got) of the cases (lines, wanted-or-None) run through the harness built on `header_text`. `run` is the caller's harness_env.run (each test script is a registered runner)."""
    run = run or harness_env.run
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
    work = Path(tempfile.mkdtemp(prefix="itemmarkstack-%s-" % name, dir=str(SCRATCH)))
    try:
        (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
        result = run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return [w for _, w in cases if w is not None], result.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def function_body(text, signature):
    body = text[text.index(signature):]
    return body[:body.index("\n    }\n") + 7]

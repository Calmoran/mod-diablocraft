"""Validate a verified D3 reference CSV against its schema.

Usage:
    python mod-diablocraft/scripts/validate_csv.py [path.csv ...]

With no arguments every CSV that has a schema in data/d3/schema/ is checked.
A CSV with no schema is reported as skipped, never as a failure: only the
tables the game breaks without are schema'd (00b-tooling section 3).

Checks, in order, per file:
  header      the column list matches the schema exactly, including order
  rows        the table has not shrunk below the row count it was schema'd at
  empty       no empty cell outside the columns the schema allows to be empty
  numbers     number columns parse as numbers, percent columns as "N%" or N
  UNSURE      the marker appears only in a notes column

Exit code 0 when every file passes, 1 otherwise. Failures print one line each:
    FAIL <file>:<row> <column> <what is wrong>
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "mod-diablocraft" / "data" / "d3"
SCHEMA_DIR = DATA / "schema"


def _load_schema(csv_path: Path) -> dict[str, Any] | None:
    schema_path = SCHEMA_DIR / f"{csv_path.stem}.schema.json"
    if not schema_path.is_file():
        return None
    with schema_path.open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


def _is_number(value: str) -> bool:
    try:
        float(value.replace(",", ""))
    except ValueError:
        return False
    return True


def _is_percent(value: str) -> bool:
    return _is_number(value[:-1]) if value.endswith("%") else _is_number(value)


def check(csv_path: Path) -> list[str]:
    """Return one message per problem; an empty list means the file passed."""
    schema = _load_schema(csv_path)
    if schema is None:
        return []

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    name = csv_path.name
    problems: list[str] = []

    expected: list[str] = schema["columns"]
    actual: list[str] = list(rows[0].keys()) if rows else []
    if actual != expected:
        missing = [c for c in expected if c not in actual]
        added = [c for c in actual if c not in expected]
        detail = []
        if missing:
            detail.append(f"missing {missing}")
        if added:
            detail.append(f"unexpected {added}")
        if not detail:
            detail.append("columns are in a different order")
        problems.append(f"FAIL {name}:1 header {'; '.join(detail)}")
        return problems

    min_rows: int = schema.get("min_rows", 1)
    if len(rows) < min_rows:
        problems.append(f"FAIL {name}:1 rows {len(rows)} rows, schema was written at {min_rows}")

    allow_empty = set(schema.get("allow_empty", []))
    numbers = set(schema.get("number_columns", []))
    percents = set(schema.get("percent_columns", []))
    notes = set(schema.get("notes_columns", []))

    for index, row in enumerate(rows, start=2):
        for column in expected:
            value = (row.get(column) or "").strip()
            if not value:
                if column not in allow_empty:
                    problems.append(f"FAIL {name}:{index} {column} empty cell")
                continue
            if column in numbers and not _is_number(value):
                problems.append(f"FAIL {name}:{index} {column} not a number: {value!r}")
            elif column in percents and not _is_percent(value):
                problems.append(f"FAIL {name}:{index} {column} not a percentage: {value!r}")
            if "UNSURE" in value and column not in notes:
                problems.append(f"FAIL {name}:{index} {column} UNSURE outside a notes column")

    return problems


def main(argv: list[str]) -> int:
    if argv:
        targets = [Path(a) if Path(a).is_absolute() else REPO / a for a in argv]
    else:
        targets = sorted(
            DATA / f"{p.name.replace('.schema.json', '')}.csv" for p in SCHEMA_DIR.glob("*.schema.json")
        )

    failures: list[str] = []
    checked = 0
    for target in targets:
        if not target.is_file():
            failures.append(f"FAIL {target.name} file not found")
            continue
        if _load_schema(target) is None:
            print(f"skip {target.name} (no schema)")
            continue
        problems = check(target)
        checked += 1
        if problems:
            failures.extend(problems)
        else:
            print(f"ok   {target.name}")

    for line in failures:
        print(line, file=sys.stderr)
    print(f"{checked} checked, {len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

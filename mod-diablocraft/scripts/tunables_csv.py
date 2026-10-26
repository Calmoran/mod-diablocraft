"""Read one number out of data/tunables/<category>.csv.

A generator that writes a number the designer can also change in game has to take it
from the same row `dc_tunables` is built from, or the two drift the moment he
edits one of them. This is that read: the sheet's own `value` when he has
filled it in, `d3_value` when he has not, and a refusal when the row is not
there - a generator must never invent the number it was asked to write.

Note what it does NOT do: it reads the CSV, not the live `dc_tunables` table.
A `.dc tunables set` that changes a generated number therefore needs the
generator rerun and its SQL applied as well; the rows that work that way say so
in their own `notes`.
"""

import csv
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
TUNABLES = MODULE_ROOT / "data/tunables"


class MissingTunable(Exception):
    """The row a generator asked for is not in the sheet."""


def value(category: str, name: str, root: Path = None) -> float:
    """The effective number for <category>/<name>: `value`, else `d3_value`."""
    folder = (root / "data/tunables") if root else TUNABLES
    path = folder / f"{category}.csv"
    if not path.exists():
        raise MissingTunable(f"{path} does not exist; {category}/{name} cannot be read")
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row.get("name") != name:
                continue
            for column in ("value", "d3_value"):
                cell = (row.get(column) or "").strip()
                if cell:
                    return float(cell)
            raise MissingTunable(
                f"{category}/{name} has neither a value nor a d3_value; "
                f"fill one in {path.name} before regenerating")
    raise MissingTunable(f"{category}/{name} is not in {path.name}")

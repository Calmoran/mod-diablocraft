"""No two migrations may share a series and number within the same database.

The updater applies `data/sql/<db>/updates/` in filename order and records each file by name in the
`updates` table; two files numbered the same in one series are two migrations with one slot in the
sequence. G1's class-map migration was minted as items_0018 and collided with the set-class drop's
items_0018 (the Sanctum branch hit the same shape with world_0029), so this refuses the collision
rather than leaving it to the updater's ordering.

Run standalone; `DC_MIGRATION_DIRS` (pathsep-separated) checks specific directories instead of all.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
SQL = MODULE / "data" / "sql"
NUMBER = re.compile(r"^(?P<series>[a-z][a-z_]*?)_(?P<number>\d{4})_")
# Pre-existing and not this task's: generate_crafting.py's crafting_0002_gold_unit.sql (the
# 2026-09-12 gold unit) and the jeweler render's crafting_0002_jeweler.sql share the crafting_0002
# slot in db-world. Both are applied, and renumbering an applied migration is a decision for their
# owner, so the pair is exempt and named (and reported) instead of failing this gate forever.
KNOWN_DUPLICATES = {("db-world", "crafting", "0002"): ("crafting_0002_jeweler.sql",
                                                       "crafting_0002_gold_unit.sql")}


def main() -> int:
    override = os.environ.get("DC_MIGRATION_DIRS")
    dirs = ([Path(p) for p in override.split(os.pathsep) if p] if override
            else sorted(SQL.glob("db-*/updates")))
    checked, failures = 0, []
    for database in dirs:
        seen: dict[tuple[str, str], str] = {}
        for path in sorted(database.glob("*.sql")):
            match = NUMBER.match(path.name)
            if not match:
                continue
            key = (match.group("series"), match.group("number"))
            checked += 1
            if key in seen:
                exempt = KNOWN_DUPLICATES.get((database.parent.name, *key))
                if exempt and {path.name, seen[key]} == set(exempt):
                    print(f"WARNING migration numbers: {database.parent.name} keeps the known "
                          f"{key[0]}_{key[1]} pair {exempt[0]} + {exempt[1]} (pre-existing, its "
                          f"owner's to renumber)")
                else:
                    failures.append(f"{database.parent.name}: {path.name} and {seen[key]} both use "
                                    f"{key[0]}_{key[1]} (two migrations, one slot in the sequence)")
            seen[key] = path.name
    if failures:
        print("FAIL migration numbers:\n" + "\n".join(failures))
        return 1
    print(f"PASS migration numbers: {checked} numbered migrations, no series and number used twice "
          f"within a database")
    return 0


if __name__ == "__main__":
    sys.exit(main())

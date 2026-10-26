#!/usr/bin/env python3
"""Generate dc_affix_tunables (13-elite-affixes section 2).

Every number the elite affixes use lives in one world table, so the designer can fight a
pack with `.dc elite`, change a value, and fight it again without a restart. No
affix value is a compile-time constant in dc_rifts.cpp any more.

The table has two value columns per row:

  d3_value    what D3 published. Written by this script from
              data/tunables/elite_affix_parameters.csv and cross-checked against
              data/d3/elite_affix_mechanics.csv. Never hand-edited in the DB.
  tuned_value the designer's value, NULL when he has not set one. The server reads
              tuned_value when it is set and d3_value otherwise.

The generated INSERT is `ON DUPLICATE KEY UPDATE` and the CSV WINS on every
apply (ruling 2026-09-19, the same ruling as dc_tunables): the sheet's
tuned_value is written over whatever is in the table, and a blank one puts the
row back to d3_value. `.dc affix set` is a scratch override for the pack you
are fighting now - write the number into the CSV to keep it, because the next
apply of this migration takes it back.

Run from the repo root:

    python mod-diablocraft/scripts/generate/monsters/generate_affix_tunables.py

This script writes only dc_affix_tunables. dc_rift_affix is generate_rift_affixes.py's.
"""

import csv
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration

MODULE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE_ROOT.parent
DATA = MODULE_ROOT / "data/d3"
# Phase 2 (Architect, 2026-09-19): this sheet is the designer's numbers, not D3's
# published reference data, so it moved to data/tunables/ and out of
# data/d3/. Its runtime home is unchanged - it is still this generator's
# table, not dc_tunables. data/tunables/README.md says so under "Files with
# their own table".
TUNABLES = MODULE_ROOT / "data/tunables"
GENERATED = MODULE_ROOT / "data/generated"
UPDATES = MODULE_ROOT / "data/sql/db-world/updates"

# The one row that is not an affix: values shared by the whole pool.
GLOBAL = "_global"

UNITS = {"yards", "seconds", "percent", "count", "multiplier", "degrees", "flag",
         "ticks per second", "yards per second", "degrees per second", "damage"}


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def read_csv(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_tunables_csv(name):
    """One of the sheets that moved to data/tunables/ but kept its own table."""
    with (TUNABLES / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def number(text):
    """The CSV cell as a float, or None when it is blank."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        result = float(text)
        if not math.isfinite(result) or result < 0:
            raise ValueError
        return result
    except ValueError:
        raise SystemExit(f"elite_affix_parameters.csv: {text!r} is not a number")


def mechanics_index():
    """(affix, parameter) -> the mechanics row's published value, when numeric.

    elite_affix_mechanics.csv is mostly prose - "not published", "x2 per 0.5 s,
    max 10 stacks", "5 (trail); 18 (explosion)". Only the rows whose value is a
    plain number can be compared, and those are compared: a parameter row that
    names a mechanics row and disagrees with it is a data defect, not a tuning
    choice.
    """
    published = {}
    for row in read_csv("elite_affix_mechanics.csv"):
        key = (row["affix_name"].strip(), row["parameter"].strip())
        raw = row["value"].strip()
        try:
            published[key] = float(raw)
        except ValueError:
            published[key] = None            # present but not a bare number
    return published


def parameters():
    affixes = {row["affix_name"].strip() for row in read_csv("elite_affixes.csv")
               if row["affix_name"].strip()}
    published = mechanics_index()
    rows = read_tunables_csv("elite_affix_parameters.csv")
    if not rows:
        raise SystemExit("elite_affix_parameters.csv: empty")

    out, seen = [], set()
    for row in rows:
        affix = row["affix_name"].strip()
        parameter = row["parameter"].strip()
        if not affix or not parameter:
            raise SystemExit("elite_affix_parameters.csv: a row has no affix or parameter")
        if affix != GLOBAL and affix not in affixes:
            raise SystemExit(f"{affix}: not an affix in elite_affixes.csv")
        if (affix, parameter) in seen:
            raise SystemExit(f"{affix}/{parameter}: duplicate row")
        seen.add((affix, parameter))

        unit = row["unit"].strip()
        if unit not in UNITS:
            raise SystemExit(f"{affix}/{parameter}: unexpected unit {unit!r}")
        d3 = number(row["d3_value"])
        tuned = number(row["tuned_value"])

        source = row["mechanics_row"].strip()
        if source:
            if (affix, source) not in published:
                raise SystemExit(f"{affix}/{parameter}: mechanics_row {source!r} is not a row "
                                 f"of elite_affix_mechanics.csv for {affix}")
            known = published[(affix, source)]
            # Only a bare number can be compared; the prose rows carry their
            # figure inside a sentence and the CSV's notes column is the record.
            # Constant (Codex audit 141): floating-point equality tolerance, not tuning.
            if known is not None and d3 is not None and abs(known - d3) > 1e-9:
                raise SystemExit(f"{affix}/{parameter}: d3_value {d3} disagrees with "
                                 f"elite_affix_mechanics.csv {source} = {known}")
        out.append((affix, parameter, d3, tuned, unit, row["notes"].strip()))
    return out


def sql(rows):
    def value(number_or_none):
        return "NULL" if number_or_none is None else repr(number_or_none)

    lines = [
        # The path in the generated header below still says data/d3 on purpose:
        # this delta has already been applied, and an applied delta must stay
        # byte-identical - generate_bags.py has an explicit guard that refuses
        # exactly this. The sheet is at data/tunables/ now; the next numbered
        # delta is where the comment gets corrected.
        "-- Generated from data/d3/elite_affix_parameters.csv by",
        "-- generate_affix_tunables.py; edit the CSV and rerun. Apply to the world database.",
        "-- 13-elite-affixes section 2: every affix number, tunable at runtime.",
        "--",
        "-- CREATE TABLE IF NOT EXISTS and ON DUPLICATE KEY UPDATE, never DROP: this",
        "-- migration is re-applied whenever the CSV changes, and re-applying it writes",
        "-- the CSV's numbers over whatever is in the table (ruling 2026-09-19). A value",
        "-- set in game with `.dc affix set` is a scratch override and does not survive",
        "-- the next apply; a blank tuned_value puts the row back to its d3_value.",
        "SET NAMES utf8mb4;",
        "CREATE TABLE IF NOT EXISTS `dc_affix_tunables` (",
        "  `affix_name` VARCHAR(64) NOT NULL COMMENT 'An affix, or _global for the shared values',",
        "  `parameter` VARCHAR(48) NOT NULL COMMENT 'Matches elite_affix_mechanics.csv where D3 published one',",
        "  `d3_value` DOUBLE NULL COMMENT 'What D3 published. Regenerated from the CSVs; never hand-edited',",
        "  `tuned_value` DOUBLE NULL COMMENT 'the designer''s value. NULL means use d3_value. "
        "Never overwritten by generation',",
        "  `unit` VARCHAR(24) NOT NULL COMMENT 'yards | seconds | percent | count | multiplier | degrees | flag',",
        "  `notes` LONGTEXT NOT NULL COMMENT 'Source, or why the tuned value differs',",
        "  PRIMARY KEY (`affix_name`, `parameter`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "INSERT INTO `dc_affix_tunables` (`affix_name`, `parameter`, `d3_value`, `tuned_value`, "
        "`unit`, `notes`) VALUES",
    ]
    lines.append(",\n".join(
        "({}, {}, {}, {}, {}, {})".format(
            quote(affix), quote(parameter), value(d3), value(tuned), quote(unit), quote(notes))
        for affix, parameter, d3, tuned, unit, notes in rows))
    # The CSV wins, every apply (ruling 2026-09-19). The old clause adopted a CSV
    # number only for an "the designer sets" row that had never been filled and kept the
    # table's own value everywhere else, which made a second edit to the sheet a
    # no-op. Plain VALUES() is the ruling: the sheet is the source of truth, a
    # blank tuned_value clears a scratch `.dc affix set` back to d3_value, and
    # no CASE has to guess which rows the designer meant.
    lines.append("ON DUPLICATE KEY UPDATE `tuned_value` = VALUES(`tuned_value`), "
                 "`d3_value` = VALUES(`d3_value`), `unit` = VALUES(`unit`), `notes` = VALUES(`notes`);")
    # Retired decisions, not dormant tuning switches. These exact owned rows
    # must also disappear from databases which applied the round-one seed.
    lines.append("DELETE FROM `dc_affix_tunables` WHERE "
                 "(`affix_name`='_global' AND `parameter` IN "
                 "('damage_ground_tick','damage_burst','damage_discharge')) OR "
                 "(`affix_name`='Avenger' AND `parameter`='damage_taken_increase');")
    return "\n".join(lines) + "\n"


def main():
    rows = parameters()
    text = sql(rows)
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "affix_tunables.sql").write_bytes(text.encode("utf-8"))
    # rifts_0015 is applied and frozen (applied_migrations.csv); the sheet's render goes to the next number.
    target = UPDATES / "rifts_0027_affix_values.sql"
    wrote = write_migration(MODULE_ROOT, target, text)

    affixes = {row[0] for row in rows} - {GLOBAL}
    sourced = sum(1 for row in rows if row[2] is not None)
    tuned = sum(1 for row in rows if row[3] is not None)
    print(f"dc_affix_tunables: {len(rows)} parameters across {len(affixes)} affixes "
          f"plus {GLOBAL} ({sourced} with a published D3 value, {tuned} seeded with a tuned value)")
    print(f"  {'wrote' if wrote else 'kept'} {target.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()

#!/usr/bin/env python3
"""Generate dc_tunables from data/tunables/*.csv (tunables phase 2, section M).

One row per number that is the designer's rather than D3's, in one table, so he can
change it with `.dc tunables set` and the server picks it up without a restart.
This is the affix mechanism (`generate_affix_tunables.py`, 13-elite-affixes §2)
widened to every category; nothing about it is new.

The table has two value columns per row, exactly as dc_affix_tunables does:

  d3_value    what D3 published, when the same row also needs one. Written by
              this script from the CSV and never hand-edited in the DB.
  tuned_value the designer's value, NULL when he has not set one. The server reads
              tuned_value when it is set and d3_value otherwise.

The INSERT is `ON DUPLICATE KEY UPDATE` and the CSV WINS on every apply
(ruling 2026-09-19): `tuned_value = VALUES(tuned_value)`, so editing the sheet
and re-applying is what changes a number, and a `value` left blank puts the row
back to d3_value. `.dc tunables set` is a scratch override for the session you
are testing in; it is gone the next time this migration is applied, which is
the loop the designer asked for - edit the CSV on a dev branch, regenerate, apply,
reload, feel the difference, merge. See data/tunables/README.md.

Run from anywhere:

    python mod-diablocraft/scripts/generate/tunables/generate_tunables.py
"""

import csv
import math
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import (MIGRATION_FROZEN, load_manifest, migration_state, reserved_number,
                                write_coupled_outputs, write_migration)

MODULE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE_ROOT.parent

# The fifteen categories of the phase 1 brief, plus `combat` - the sixteenth,
# authorised by the Architect on 2026-09-19 for class-agnostic player combat
# numbers, which is where damage_formula.csv's values land. A seventeenth is
# The designer's call through the PM, not a file someone drops in the folder.
CATEGORIES = ("barbarian", "wizard", "monk", "necromancer", "crusader", "witchdoctor",
              "demonhunter", "monsters", "affixes", "loot", "economy", "crafting",
              "rifts", "paragon", "ui", "combat")

UNITS = {"yards", "seconds", "milliseconds", "percent", "count", "multiplier", "degrees",
         "flag", "damage", "yards per second", "degrees per second", "gold", "level", "pixels",
         "radians", "map"}

# Eight sheets that live in this folder but are NOT category files: each is a
# number of the designer's that already had its own generator and its own runtime table
# before phase 2, and the Architect's 2026-09-19 ruling moved the FILE out of
# data/d3/ without moving the numbers into dc_tunables. They keep their own
# shape, their own generator and their own `.dc` command; this generator must
# walk past them rather than fail on their headers. data/tunables/README.md
# lists which table and which command each one belongs to. Consolidating the
# files below into dc_tunables is a later task, not this one.
NOT_CATEGORY_FILES = {
    "ability_tunables.csv",        # dc_ability_tuning, generate_spells.py
    "primary_mechanics.csv",       # dc_barbarian_primary_data.h, generate_spells.py
    "ground_loot_parameters.csv",  # the generated ground-loot rows, generate_ground_loot.py
    "elite_affix_parameters.csv",  # dc_affix_tunables, generate_affix_tunables.py
    "loot_tuning.csv",             # dc_loot_tuning, generate_paragon.py and others
    "block.csv",                   # dc_block_tuning, generate_block.py
    "monster_targeting.csv",       # dc_monster_targeting, generate_monster_targeting.py
    "rift_survey.csv",             # the offline rift survey's inputs, generate_rift_survey.py (no runtime table)
    "monster_sets.csv",            # dc_monster_set and its members, generate_spawn_sheets.py
    "cluster_recipes.csv",         # dc_cluster_recipe, generate_spawn_sheets.py
    "monster_spawn.csv",           # dc_monster_spawn, generate_spawn_sheets.py
    "area_defaults.csv",           # dc_area_default, generate_spawn_sheets.py
    "bags.csv",                    # the generated container templates, generate_bags.py
    "class_resources.csv",         # dc_resource_data.h, generate_class_resources.py
    "monster_abilities.csv",       # dc_family_ability, generate_monster_models.py
    "monster_ability_ai.csv",      # dc_family_ability_ai, generate_family_ai.py
}

# The manifest, not a category file either: see read_from_d3().
FROM_D3 = "_from_d3.csv"
FROM_D3_HEADER = ["source_file", "row_key", "column", "category", "name", "unit"]

# Where a pulled number's citation comes from, in order. The first of these
# columns that the source row actually has and has filled wins, so a CSV that
# already carries a `source` column needs nothing added, and one that does not
# gets a `numeric_source` column beside the numbers when they are added.
SOURCE_COLUMNS = ("{column}_source", "numeric_source", "source", "notes", "details")

HEADER = ["name", "d3_value", "value", "unit", "notes"]
NAME = re.compile(r"^[a-z][a-z0-9_]*$")

class DataError(Exception):
    """A CSV the generator refuses to turn into SQL."""


# The migration the current render ships as, named in data/tunables/current_migration.txt (one line).
# Every new migration carries the whole sheet (the render is an idempotent CSV-wins upsert of every
# row). The file is rewritten in place on every fold UNTIL dev or live applies it. The moment
# applied_migrations.csv or applied_migrations_dev.csv lists it, its bytes are frozen: a render that
# differs goes to the next free number on its own (above every tunables_NNNN.sql in either folder and
# every one a manifest lists or reserves), the applied file stays as it was applied, and the run records the new
# number in current_migration.txt for the next run (diablocraft-dan0c). A render that still matches
# the applied file changes nothing. Two branches that each advance pick the same number and meet in
# a merge conflict on that one line (and on the file), which is the signal to renumber one of them.
STATE_FILE = "data/tunables/current_migration.txt"
MIGRATION_NAME = re.compile(r"^tunables_(\d{4})\.sql$")
UPDATES_DIR = "data/sql/db-world/updates"
GENERATED_DIR = "data/generated"


def current_migration(root):
    """The migration name the next render ships as, from root's current_migration.txt."""
    path = root / STATE_FILE
    if not path.is_file():
        raise DataError(f"{path} does not exist; it names the migration the current render ships as, "
                        f"one line such as tunables_0014.sql")
    name = path.read_text(encoding="utf-8").strip()
    if not MIGRATION_NAME.match(name):
        raise DataError(f"{path}: {name!r} is not a tunables_NNNN.sql name")
    return name


CURRENT_MIGRATION = current_migration(MODULE_ROOT)
GENERATED_SQL = CURRENT_MIGRATION
UPDATE_SQL = CURRENT_MIGRATION

# Rows that left the sheets because nothing reads them. The upsert never deletes, so the
# migration does, from the live table. Keep an entry until the migration that deletes it is
# applied everywhere; none may name a row a sheet still has (a test holds that).
RETIRED = (
    ("crafting", "enchant_material_count"),  # diablocraft-t9fl: the Mystic reads dc_mystic_rule
    ("monsters", "family_damage_plague_swarm"),  # diablocraft-yqlv: renamed family_damage_stinging_swarm
    # diablocraft-43j0 (monster spawning S3): the bar is D3's progress points now, one monster's own points per kill and
    # the orb counts and points per pack kind and mode (gr_orb_champion_count ... nr_orb_points)
    ("rifts", "progress_units_per_kill"),
    ("rifts", "gr_progress_weight_elite"),
    ("rifts", "gr_progress_weight_pack_member"),
    ("rifts", "gr_orb_count"),
    ("rifts", "gr_orb_progress_pct"),
    # diablocraft-dxpy (native 64-bit Life): the core holds Life whole, so the big-Life wire and its budgets are gone
    ("combat", "big_life_pull_burst"),
    ("combat", "big_life_pull_per_second"),
    ("combat", "big_life_window_ms"),
    ("combat", "big_life_hit_messages_per_second"),
    ("combat", "wall_of_man_shield_pct_of_max_life"),  # diablocraft-upwsv: Wall of Man is 25% off every hit, not a Life shield
)


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def number(path, line, column, text):
    """The cell as a float, or None when it is blank."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        raise DataError(f"{path.name}:{line}: {column} {text!r} is not a number")
    if not math.isfinite(result):
        raise DataError(f"{path.name}:{line}: {column} {text!r} is not finite")
    return result


def read_category(path):
    """Validate one category file and return its rows, sorted by name."""
    category = path.stem
    if category not in CATEGORIES:
        raise DataError(f"{path.name}: {category!r} is not one of the fifteen categories; "
                        f"ask the PM before adding one")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            header = next(reader)
        except StopIteration:
            raise DataError(f"{path.name}: empty; it needs at least the header row "
                            f"{','.join(HEADER)}")
        if [cell.strip() for cell in header] != HEADER:
            raise DataError(f"{path.name}: header is {header}, expected {HEADER}")
        rows, seen = [], set()
        for line, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) != len(HEADER):
                raise DataError(f"{path.name}:{line}: {len(cells)} columns, expected {len(HEADER)}")
            name, d3_text, value_text, unit, notes = (cell.strip() for cell in cells)
            if not NAME.match(name):
                raise DataError(f"{path.name}:{line}: {name!r} is not a lower_snake_case name")
            if len(name) > 64:
                raise DataError(f"{path.name}:{line}: {name!r} is longer than 64 characters")
            if name in seen:
                raise DataError(f"{path.name}:{line}: duplicate name {name!r}")
            seen.add(name)
            if unit not in UNITS:
                raise DataError(f"{path.name}:{line}: unit {unit!r} is not one of "
                                f"{', '.join(sorted(UNITS))}")
            if not notes:
                raise DataError(f"{path.name}:{line}: {name!r} has no notes; the notes column "
                                f"carries the audit row or decision the number came from")
            rows.append((category, name,
                         number(path, line, "d3_value", d3_text),
                         number(path, line, "value", value_text),
                         unit, notes))
    return sorted(rows, key=lambda row: row[1])


def match_row(path, rows, row_key):
    """The single source row a manifest `row_key` names.

    `row_key` is `column=value`, and `|`-separated when one column does not
    identify a row on its own: `section=magic_find|topic=item-based Magic Find`.
    Nothing here guesses - a key that matches no row, or more than one, is a
    refusal, because the alternative is a generator quietly pulling the wrong
    number into a table the designer then tunes.
    """
    wanted = []
    for clause in row_key.split("|"):
        if "=" not in clause:
            raise DataError(f"{FROM_D3}: row_key {row_key!r} is not column=value")
        column, _, text = clause.partition("=")
        wanted.append((column.strip(), text.strip()))
    for column, _ in wanted:
        if rows and column not in rows[0]:
            raise DataError(f"{FROM_D3}: {path.name} has no column {column!r} to key on")
    found = [row for row in rows
             if all((row.get(column) or "").strip() == text for column, text in wanted)]
    if len(found) != 1:
        raise DataError(f"{FROM_D3}: row_key {row_key!r} matches {len(found)} rows of "
                        f"{path.name}; it must match exactly one")
    return found[0]


def citation(row, column):
    """Where the pulled number came from, out of the source row itself.

    Required, not decorative: a published number with no citation beside it is
    indistinguishable from one somebody typed, and that is the whole thing the
    d3/tunables split exists to prevent. A source row that cannot say where its
    number came from is a refusal, not a row with an empty note.
    """
    for candidate in SOURCE_COLUMNS:
        name = candidate.format(column=column)
        text = (row.get(name) or "").strip()
        if text:
            return text
    return ""


def read_from_d3(root):
    """Pull the published numbers data/tunables/_from_d3.csv names out of data/d3.

    The Architect's 2026-09-19 ruling: a number D3 published stays authored in
    its own data/d3 CSV, and reaches dc_tunables as `d3_value` with `tuned_value`
    NULL, so the code has one way to read a number and the designer can still override a
    published one. This manifest is the only thing that crosses between the two
    folders, and it is six columns wide so that crossing is readable.
    """
    manifest = root / "data/tunables" / FROM_D3
    if not manifest.exists():
        return []
    d3 = root / "data/d3"
    cache = {}
    rows, seen = [], set()
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            header = next(reader)
        except StopIteration:
            raise DataError(f"{FROM_D3}: empty; it needs at least the header row "
                            f"{','.join(FROM_D3_HEADER)}")
        if [cell.strip() for cell in header] != FROM_D3_HEADER:
            raise DataError(f"{FROM_D3}: header is {header}, expected {FROM_D3_HEADER}")
        for line, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) != len(FROM_D3_HEADER):
                raise DataError(f"{FROM_D3}:{line}: {len(cells)} columns, "
                                f"expected {len(FROM_D3_HEADER)}")
            source_file, row_key, column, category, name, unit = (cell.strip() for cell in cells)
            if category not in CATEGORIES:
                raise DataError(f"{FROM_D3}:{line}: {category!r} is not one of the categories")
            if not NAME.match(name) or len(name) > 64:
                raise DataError(f"{FROM_D3}:{line}: {name!r} is not a lower_snake_case name")
            if (category, name) in seen:
                raise DataError(f"{FROM_D3}:{line}: duplicate {category}/{name}")
            seen.add((category, name))
            if unit not in UNITS:
                raise DataError(f"{FROM_D3}:{line}: unit {unit!r} is not one of "
                                f"{', '.join(sorted(UNITS))}")
            path = d3 / source_file
            if source_file not in cache:
                if not path.exists():
                    raise DataError(f"{FROM_D3}:{line}: data/d3/{source_file} does not exist")
                with path.open(encoding="utf-8-sig", newline="") as source:
                    cache[source_file] = list(csv.DictReader(source))
            source_row = match_row(path, cache[source_file], row_key)
            if column not in source_row:
                raise DataError(f"{FROM_D3}:{line}: {source_file} has no column {column!r}; "
                                f"add the numeric column under data/d3/.unlocked first")
            cell = (source_row.get(column) or "").strip()
            if not cell:
                raise DataError(f"{FROM_D3}:{line}: {source_file} {row_key} has no {column!r} "
                                f"value; a published number is never filled in from memory")
            published = number(path, line, column, cell)
            where = citation(source_row, column)
            if not where:
                raise DataError(
                    f"{FROM_D3}:{line}: {source_file} {row_key} has no citation for "
                    f"{column!r}; add a {column}_source column (or numeric_source, source, "
                    f"notes, details) saying where the number came from. A published number "
                    f"without its source is not published, it is typed")
            rows.append((category, name, published, None, unit,
                         f"from {source_file}:{row_key}.{column}, {where}"))
    return sorted(rows, key=lambda row: (row[0], row[1]))


def read_all(root):
    folder = root / "data/tunables"
    if not folder.is_dir():
        raise DataError(f"{folder} does not exist")
    files = sorted(path for path in folder.glob("*.csv")
                   if path.name not in NOT_CATEGORY_FILES and path.name != FROM_D3)
    if not files:
        raise DataError(f"{folder} holds no category CSV")
    rows = []
    for path in files:
        rows.extend(read_category(path))
    rows.extend(read_from_d3(root))
    names = {}
    for row in rows:
        key = (row[0], row[1])
        if key in names:
            raise DataError(f"{row[0]}/{row[1]} is defined twice: once in {names[key]} and once "
                            f"again; a manifest row and a category row cannot share a name")
        names[key] = f"{row[0]}.csv"
    return sorted(rows, key=lambda row: (row[0], row[1]))


def sql(rows, retired=()):
    def value(number_or_none):
        return "NULL" if number_or_none is None else repr(number_or_none)

    lines = [
        "-- Generated from data/tunables/*.csv by generate_tunables.py; edit the CSV",
        "-- and rerun. Apply to the world database.",
        "-- Tunables phase 2 section M: every number that is the designer's rather than D3's,",
        "-- in one table, tunable at runtime with `.dc tunables set`.",
        "--",
        "-- CREATE TABLE IF NOT EXISTS and ON DUPLICATE KEY UPDATE, never DROP: this",
        "-- migration is re-applied whenever a CSV changes, and re-applying it writes",
        "-- the CSV's numbers over whatever is in the table (ruling 2026-09-19). A value",
        "-- set in game with `.dc tunables set` is a scratch override and does not",
        "-- survive the next apply; a CSV `value` left blank puts the row back to its",
        "-- published d3_value.",
        "SET NAMES utf8mb4;",
        "CREATE TABLE IF NOT EXISTS `dc_tunables` (",
        "  `category` VARCHAR(24) NOT NULL COMMENT 'One of the fifteen data/tunables/ files',",
        "  `name` VARCHAR(64) NOT NULL COMMENT 'lower_snake_case, unique inside the category',",
        "  `d3_value` DOUBLE NULL COMMENT 'What D3 published, when the row has one. Regenerated from the CSV; never hand-edited',",
        "  `tuned_value` DOUBLE NULL COMMENT 'the designer''s value. NULL means use d3_value. Never overwritten by generation',",
        "  `unit` VARCHAR(24) NOT NULL COMMENT 'yards | seconds | milliseconds | percent | count | multiplier | degrees | flag | damage | gold | level | ...',",
        "  `notes` LONGTEXT NOT NULL COMMENT 'The audit row or decision this number came from',",
        "  PRIMARY KEY (`category`, `name`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
    ]
    if not rows:
        # Section M ships the table with no rows in it; the migrations fill the
        # CSVs. An INSERT with no VALUES is not SQL, so there is simply none.
        lines.append("-- No rows yet: every data/tunables/*.csv holds only its header.")
        return "\n".join(lines) + "\n"

    lines.append("INSERT INTO `dc_tunables` (`category`, `name`, `d3_value`, `tuned_value`, "
                 "`unit`, `notes`) VALUES")
    lines.append(",\n".join(
        "({}, {}, {}, {}, {}, {})".format(
            quote(category), quote(name), value(d3), value(tuned), quote(unit), quote(notes))
        for category, name, d3, tuned, unit, notes in rows))
    # The CSV wins, every apply (ruling 2026-09-19). Not COALESCE: a value that
    # only landed the first time a row was seeded made the sheet read-only in
    # practice, because the designer's second edit to it was silently ignored. Plain
    # VALUES() also means a blanked `value` clears a scratch `.dc tunables set`
    # back to d3_value, which is how a number is un-tuned.
    lines.append("ON DUPLICATE KEY UPDATE "
                 "`tuned_value` = VALUES(`tuned_value`), "
                 "`d3_value` = VALUES(`d3_value`), `unit` = VALUES(`unit`), "
                 "`notes` = VALUES(`notes`);")
    lines += [f"DELETE FROM `dc_tunables` WHERE `category` = {quote(category)} AND `name` = {quote(name)};"
              for category, name in retired]
    return "\n".join(lines) + "\n"


def next_free_migration(root, current):
    """tunables_NNNN.sql with NNNN one above every number in use under root.

    In use means the current name, any tunables_NNNN.sql in the updates or generated folder, and any
    the applied manifests list (a file applied on dev stays a taken number if its copy moved), and any
    the dev manifest reserves for a branch's migration that is not in this tree (diablocraft-2kmef).
    """
    taken = {int(MIGRATION_NAME.match(current).group(1)), reserved_number(root, "tunables")}
    for folder in (root / UPDATES_DIR, root / GENERATED_DIR):
        for path in folder.glob("tunables_*.sql"):
            match = MIGRATION_NAME.match(path.name)
            if match:
                taken.add(int(match.group(1)))
    for key in load_manifest(root):
        match = MIGRATION_NAME.match(Path(key).name)
        if match:
            taken.add(int(match.group(1)))
    return f"tunables_{max(taken) + 1:04d}.sql"


def choose_migration(root, text):
    """The name this render is written under: the current one, or the next free one if that is frozen.

    A current file listed as applied (live or dev) keeps its applied bytes. A render that matches
    them is a no-op under the same name; one that differs moves on (diablocraft-f4aj1 refused here,
    diablocraft-dan0c advances instead, so no fold stops after a dev deploy).
    """
    current = current_migration(root)
    if migration_state(root, root / UPDATES_DIR / current, text) != MIGRATION_FROZEN:
        return current
    chosen = next_free_migration(root, current)
    print(f"{current} is applied (applied_migrations*.csv) and this render differs: writing {chosen}, "
          f"{current} stays as it was applied")
    return chosen


def generate(root=MODULE_ROOT):
    """Write both copies of the migration and return (rows, text)."""
    rows = read_all(root)
    # Only this migration deletes retired rows; other generators call sql() for their own rows.
    text = sql(rows, RETIRED)
    name = choose_migration(root, text)
    generated = root / GENERATED_DIR
    updates = root / UPDATES_DIR
    generated.mkdir(parents=True, exist_ok=True)
    write_migration(root, updates / name, text)
    # The data/generated mirror follows the migration, never the other way round.
    write_coupled_outputs(root, updates / name, text, [(generated / name, text)],
                          label="tunables mirror")
    # Last, so a failed write leaves the state on the file that is still current.
    if name != current_migration(root):
        (root / STATE_FILE).write_text(name + "\n", encoding="utf-8")
    return rows, text


def main():
    try:
        rows, _ = generate()
    except DataError as error:
        raise SystemExit(str(error))
    categories = sorted({row[0] for row in rows})
    sourced = sum(1 for row in rows if row[2] is not None)
    tuned = sum(1 for row in rows if row[3] is not None)
    print(f"dc_tunables: {len(rows)} row(s) across {len(categories)} categor"
          f"{'y' if len(categories) == 1 else 'ies'} "
          f"({sourced} with a published D3 value, {tuned} seeded with the designer's value)")
    name = current_migration(MODULE_ROOT)
    for folder in (MODULE_ROOT / GENERATED_DIR, MODULE_ROOT / UPDATES_DIR):
        print(f"  wrote {(folder / name).relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()

#!/usr/bin/env python3
"""The spawn sheets (diablocraft-dt7c, docs/proposals/monster-spawning.md section 5, Part S1): CSV -> spawn_sheets_0001.sql.

    python3 mod-diablocraft/scripts/generate/monsters/generate_spawn_sheets.py

The designer's sheets, all in data/tunables/ (the sheet is the source; the knobs and orbs are rows of rifts.csv, which
generate_tunables.py turns into dc_tunables):
  monster_sets.csv    per set: name, weight, Nephalem and Greater switches, its roster monsters, a weight per family;
                      `source` is d3 (a seed cut from gr_monster_sets.csv) or alex (he edited it)
  cluster_recipes.csv per size (small, medium, large, patrol): bodies and a count range per role; a row with a
                      family overrides the size's row for that family (blank cells take the size's)
  monster_spawn.csv   per roster monster: solo yes or no, wander_yards (8; 0 stands still)
  area_defaults.csv   per tag S, M, L: anchors filled min-max and the cluster sizes it takes

It refuses a sheet that disagrees with the roster: a set member that is not a roster monster or has no creature row
(generate_monster_models.py HELD_BACK), a family weight list that is not exactly the members' families, a range whose
minimum passes its maximum, a monster list that is not the roster's. It writes the migration (six tables, replaced whole on
every apply, like rift_survey_0001.sql) with its data/generated mirror, and the report
data/generated/spawn_sheets_report.csv: per set, the families it can make clusters of and the monsters that stand as
solos (3.2: a family with no melee or ranged member, and every solo-flagged monster).

Roles are the roster's role words by their first word, "summoner" counted as caster (3.3).
"""
import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration  # noqa: E402
import generate_monster_models as models  # noqa: E402
from generate_rifts import quote  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
TUNABLES = MODULE / "data/tunables"
ROSTER = MODULE / "data/d3/monster_roster.csv"
PROGRESS = MODULE / "data/d3/gr_monster_progress.csv"
REPORT = MODULE / "data/generated/spawn_sheets_report.csv"
NAME = "spawn_sheets_0001.sql"
PROGRESS_NAME = "spawn_sheets_0002_progress.sql"
# Identities of the plan's model, not tunables: the four recipe sizes, the four roles, the three tags (3.1, 3.3).
SIZES = ("small", "medium", "large", "patrol")
ROLES = ("melee", "ranged", "caster", "big")
TAGS = ("S", "M", "L")
CLUSTER_ROLES = ("melee", "ranged")   # 3.2: a family with neither stands as solos
REPORT_COLUMNS = ("set_id", "name", "members", "clusterable_families", "solo_families", "solo_monsters", "skipped")


class DataError(ValueError):
    """A sheet the generator refuses to turn into SQL."""


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def role_of(role_word):
    first = role_word.split("/")[0].strip().lower()
    return "caster" if first == "summoner" else first


def yes_no(row, column, where):
    value = row[column].strip().lower()
    if value not in ("yes", "no"):
        raise DataError(f"{where}: {column} {row[column]!r} is yes or no")
    return 1 if value == "yes" else 0


def number(text, where, integer=False):
    try:
        value = float(text)
    except ValueError:
        raise DataError(f"{where}: {text!r} is not a number")
    if not math.isfinite(value) or value < 0:
        raise DataError(f"{where}: {text!r} is not a finite number of 0 or more")
    if integer:
        if value != int(value):
            raise DataError(f"{where}: {text!r} is not a whole number")
        return int(value)
    return value


def read_roster(path=ROSTER):
    entry = models.entries() if path == ROSTER else {r["name"]: models.FAMILY_ENTRY_BASE + i for i, r in enumerate(read_csv(path), 1)}
    return [dict(monster=r["name"], family=r["family"], role=role_of(r["role"]), warpath_name=r["warpath_name"],
                 entry=None if r["name"] in models.HELD_BACK else entry[r["name"]]) for r in read_csv(path)]


def parse_family_weights(text, where):
    out = {}
    for part in filter(None, (p.strip() for p in text.split(";"))):
        family, _, weight = part.partition("=")
        if family.strip() in out:
            raise DataError(f"{where}: family {family.strip()!r} twice")
        out[family.strip()] = number(weight, f"{where}: weight of {family.strip()}")
    return out


def check_sets(rows, spawn, roster):
    by_name = {m["monster"]: m for m in roster}
    sets, seen_id, seen_name = [], set(), set()
    for row in rows:
        where = f"monster_sets.csv set {row['set_id']}"
        set_id = number(row["set_id"], where + " set_id", integer=True)
        if set_id in seen_id or row["name"] in seen_name or not row["name"].strip():
            raise DataError(f"{where}: set_id and name are unique and not empty")
        seen_id.add(set_id), seen_name.add(row["name"])
        if row["source"] not in ("d3", "alex"):
            raise DataError(f"{where}: source {row['source']!r} is d3 or alex")
        members = [m.strip() for m in row["monsters"].split(";") if m.strip()]
        if not members or len(set(members)) != len(members):
            raise DataError(f"{where}: it needs monsters, each once")
        for m in members:
            if m not in by_name:
                raise DataError(f"{where}: {m!r} is not a roster monster")
            if by_name[m]["entry"] is None:
                raise DataError(f"{where}: {m!r} has no creature row (held back in generate_monster_models.py)")
        families = []
        for m in members:
            if by_name[m]["family"] not in families:
                families.append(by_name[m]["family"])
        weights = parse_family_weights(row["family_weights"], where)
        if set(weights) != set(families):
            raise DataError(f"{where}: family_weights names {sorted(weights)}, its monsters' families are {sorted(families)}")
        clusterable = [f for f in families if any(by_name[m]["family"] == f and by_name[m]["role"] in CLUSTER_ROLES
                                                  and not spawn[m]["solo"] for m in members)]
        sets.append(dict(set_id=set_id, name=row["name"], weight=number(row["weight"], where + " weight"),
                         nephalem=yes_no(row, "nephalem", where), greater=yes_no(row, "greater", where), source=row["source"],
                         d3_set=int(row["d3_set"]) if row["d3_set"].strip() else None, members=members, families=families,
                         family_weights=weights, clusterable=clusterable))
    return sets


def check_range(row, low, high, where):
    a, b = number(row[low], f"{where} {low}", integer=True), number(row[high], f"{where} {high}", integer=True)
    if a > b:
        raise DataError(f"{where}: {low} {a} is above {high} {b}")
    return a, b


def check_recipes(rows, roster):
    families = {m["family"] for m in roster}
    base, overrides = {}, {}
    for row in rows:
        size, family = row["size"].strip(), row["family"].strip()
        where = f"cluster_recipes.csv {size} {family or '(all)'}"
        if size not in SIZES or (family and family not in families):
            raise DataError(f"{where}: unknown size or family")
        target = overrides if family else base
        if (size, family) in target or (size in base and not family):
            raise DataError(f"{where}: twice")
        values = {}
        for column in ("bodies",) + ROLES:
            blank = not row[f"{column}_min"].strip() and not row[f"{column}_max"].strip()
            if blank and family and column != "bodies":
                values[column] = None
            else:
                values[column] = check_range(row, f"{column}_min", f"{column}_max", where)
        if values["bodies"][0] < 1:
            raise DataError(f"{where}: bodies_min is at least 1")
        target[(size, family) if family else size] = values
    if set(base) != set(SIZES):
        raise DataError(f"cluster_recipes.csv needs one all-family row for each of {SIZES}")
    out = [dict(size=s, family="", **base[s]) for s in SIZES]
    for (size, family), v in sorted(overrides.items(), key=lambda kv: (SIZES.index(kv[0][0]), kv[0][1])):
        out.append(dict(size=size, family=family, **{k: (v[k] or base[size][k]) for k in v}))
    for row in out:   # every row as it will be used, inherited cells included: the role minimums must fit the bodies and the maximums reach them
        if sum(row[r][0] for r in ROLES) > row["bodies"][1] or sum(row[r][1] for r in ROLES) < row["bodies"][0]:
            raise DataError(f"cluster_recipes.csv {row['size']} {row['family'] or '(all)'}: the role ranges cannot make {row['bodies']} bodies")
    return out


def check_spawn(rows, roster):
    if [r["monster"] for r in rows] != [m["monster"] for m in roster]:
        raise DataError("monster_spawn.csv must list the roster's monsters, in the roster's order")
    out = {}
    for row, m in zip(rows, roster):
        where = f"monster_spawn.csv {row['monster']}"
        if row["family"] != m["family"]:
            raise DataError(f"{where}: family {row['family']!r}, the roster says {m['family']!r}")
        out[row["monster"]] = dict(monster=row["monster"], entry=m["entry"], family=m["family"], role=m["role"],
                                   solo=yes_no(row, "solo", where), wander_yards=number(row["wander_yards"], where + " wander_yards"))
    return out


def check_progress(roster, rows):
    """Monster spawning S3 (3.9.4): each roster monster's D3 progress points, in hundredths, through the roster's warpath_name.

    A monster whose warpath_name is `none` has no row (the runtime counts it at rifts/monster_progress_default_points); a
    held-back monster has no creature entry and no row either. Warpath's points have two decimals at most, so a number
    that is not a whole count of hundredths is a bad cell."""
    points = {r["name"]: r["progress_points"] for r in rows}
    out = []
    for m in roster:
        name = m["warpath_name"]
        if name == "none" or m["entry"] is None:
            continue
        if name not in points:
            raise DataError(f"{m['monster']}: warpath_name {name!r} is not in gr_monster_progress.csv")
        value = number(points[name], f"gr_monster_progress.csv {name} progress_points")
        if abs(value * 100 - round(value * 100)) > 1e-6:
            raise DataError(f"gr_monster_progress.csv {name}: {points[name]} points is not a whole count of hundredths")
        out.append(dict(monster=m["monster"], entry=m["entry"], hundredths=round(value * 100)))
    return out


def check_areas(rows):
    if [r["tag"] for r in rows] != list(TAGS):
        raise DataError("area_defaults.csv needs the tags S, M, L, in that order")
    out = []
    for row in rows:
        where = f"area_defaults.csv {row['tag']}"
        low, high = check_range(row, "anchors_min", "anchors_max", where)
        sizes = {s: yes_no(row, s, where) for s in SIZES[:3]}
        if not any(sizes.values()):
            raise DataError(f"{where}: it takes at least one cluster size")
        out.append(dict(tag=row["tag"], anchors_min=low, anchors_max=high, **sizes))
    return out


def check_knobs(path=TUNABLES / "rifts.csv"):
    """The elite knobs of rifts.csv: percents are 0 to 100 and the floor's minimum is not above its maximum."""
    knobs = {r["name"]: r["value"].strip() for r in read_csv(path)}
    for name in ("elite_chance_pct", "elite_champion_pct", "solo_share_pct", "patrol_share_pct"):
        if knobs.get(name) and not 0 <= float(knobs[name]) <= 100:
            raise DataError(f"rifts.csv {name} {knobs[name]} is a percent, 0 to 100")
    low, high = knobs.get("elite_packs_min"), knobs.get("elite_packs_max")
    if low and high and float(low) > float(high):
        raise DataError(f"rifts.csv elite_packs_min {low} is above elite_packs_max {high}")


def load(directory=TUNABLES, roster_path=ROSTER, progress_path=PROGRESS):
    directory = Path(directory)
    roster = read_roster(roster_path)
    spawn = check_spawn(read_csv(directory / "monster_spawn.csv"), roster)
    return dict(roster=roster, spawn=spawn, sets=check_sets(read_csv(directory / "monster_sets.csv"), spawn, roster),
                recipes=check_recipes(read_csv(directory / "cluster_recipes.csv"), roster),
                areas=check_areas(read_csv(directory / "area_defaults.csv")),
                progress=check_progress(roster, read_csv(progress_path)))


def report(data):
    out = []
    by_name = {m["monster"]: m for m in data["roster"]}
    for s in data["sets"]:
        solo_families = [f for f in s["families"] if f not in s["clusterable"]]
        solos = [m for m in s["members"] if data["spawn"][m]["solo"] or by_name[m]["family"] in solo_families]
        out.append(dict(set_id=s["set_id"], name=s["name"], members=len(s["members"]), clusterable_families="; ".join(s["clusterable"]),
                        solo_families="; ".join(solo_families), solo_monsters="; ".join(solos),
                        skipped="yes" if not s["clusterable"] else "no"))
    return out


# -- the migration --------------------------------------------------------------------------------------------------------

def literal(value):
    return "NULL" if value is None else (quote(value) if isinstance(value, str) else repr(value))


def render(data):
    roles = {r: f"`{r}_min` INT UNSIGNED NOT NULL, `{r}_max` INT UNSIGNED NOT NULL" for r in ("bodies",) + ROLES}
    tables = [
        ("dc_monster_set", "`set_id` INT UNSIGNED NOT NULL, `name` VARCHAR(128) NOT NULL, `weight` DOUBLE NOT NULL, `nephalem` TINYINT UNSIGNED NOT NULL, "
         "`greater` TINYINT UNSIGNED NOT NULL, `source` VARCHAR(8) NOT NULL, `d3_set` INT UNSIGNED NULL, PRIMARY KEY (`set_id`)",
         ("set_id", "name", "weight", "nephalem", "greater", "source", "d3_set"), data["sets"]),
        ("dc_monster_set_member", "`set_id` INT UNSIGNED NOT NULL, `monster` VARCHAR(64) NOT NULL, PRIMARY KEY (`set_id`, `monster`)",
         ("set_id", "monster"), [dict(set_id=s["set_id"], monster=m) for s in data["sets"] for m in s["members"]]),
        ("dc_monster_set_family", "`set_id` INT UNSIGNED NOT NULL, `family` VARCHAR(32) NOT NULL, `weight` DOUBLE NOT NULL, "
         "`clusterable` TINYINT UNSIGNED NOT NULL, PRIMARY KEY (`set_id`, `family`)",
         ("set_id", "family", "weight", "clusterable"),
         [dict(set_id=s["set_id"], family=f, weight=s["family_weights"][f], clusterable=int(f in s["clusterable"]))
          for s in data["sets"] for f in s["families"]]),
        ("dc_cluster_recipe", "`size` VARCHAR(8) NOT NULL, `family` VARCHAR(32) NOT NULL DEFAULT '', " + ", ".join(roles.values()) + ", PRIMARY KEY (`size`, `family`)",
         ("size", "family") + tuple(c for r in ("bodies",) + ROLES for c in (f"{r}_min", f"{r}_max")),
         [dict(size=r["size"], family=r["family"], **{f"{k}_{i}": r[k][n] for k in ("bodies",) + ROLES for n, i in enumerate(("min", "max"))})
          for r in data["recipes"]]),
        ("dc_monster_spawn", "`monster` VARCHAR(64) NOT NULL, `entry` INT UNSIGNED NULL, `family` VARCHAR(32) NOT NULL, `role` VARCHAR(8) NOT NULL, "
         "`solo` TINYINT UNSIGNED NOT NULL, `wander_yards` DOUBLE NOT NULL, PRIMARY KEY (`monster`)",
         ("monster", "entry", "family", "role", "solo", "wander_yards"), list(data["spawn"].values())),
        ("dc_area_default", "`tag` CHAR(1) NOT NULL, `anchors_min` INT UNSIGNED NOT NULL, `anchors_max` INT UNSIGNED NOT NULL, `small` TINYINT UNSIGNED NOT NULL, "
         "`medium` TINYINT UNSIGNED NOT NULL, `large` TINYINT UNSIGNED NOT NULL, PRIMARY KEY (`tag`)",
         ("tag", "anchors_min", "anchors_max", "small", "medium", "large"), data["areas"]),
    ]
    parts = ["-- Generated by generate_spawn_sheets.py from the sheets in data/tunables (diablocraft-dt7c); never edit.",
             "-- The spawn sheets (docs/proposals/monster-spawning.md section 5, Part S1): monster sets, cluster recipes, per-monster",
             "-- solo and wander, area defaults. Replaced whole on every apply; the CSV wins. Nothing reads them until the spawner (S2).",
             "SET NAMES utf8mb4;"]
    for name, ddl, columns, rows in tables:
        cols = ", ".join(f"`{c}`" for c in columns)
        parts += [f"CREATE TABLE IF NOT EXISTS `{name}` ({ddl}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;", f"DELETE FROM `{name}`;"]
        values = ",\n".join("(" + ", ".join(literal(r[c]) for c in columns) + ")" for r in rows)
        parts.append(f"INSERT INTO `{name}` ({cols}) VALUES\n{values};")
    return "\n".join(parts) + "\n"


def render_progress(data):
    rows = ",\n".join(f"({literal(r['monster'])}, {r['entry']}, {r['hundredths']})" for r in data["progress"])
    return "\n".join([
        "-- Generated by generate_spawn_sheets.py from data/d3/gr_monster_progress.csv through the roster's warpath_name; never edit.",
        "-- Monster spawning S3 (docs/proposals/monster-spawning.md 3.9.4): each roster monster's D3 progress points in hundredths",
        "-- of a point (650 points = 65,000 = the whole bar). A monster with no row counts rifts/monster_progress_default_points.",
        "SET NAMES utf8mb4;",
        "CREATE TABLE IF NOT EXISTS `dc_monster_progress` (`monster` VARCHAR(64) NOT NULL, `entry` INT UNSIGNED NOT NULL, "
        "`hundredths` INT UNSIGNED NOT NULL, PRIMARY KEY (`monster`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
        "DELETE FROM `dc_monster_progress`;",
        f"INSERT INTO `dc_monster_progress` (`monster`, `entry`, `hundredths`) VALUES\n{rows};",
    ]) + "\n"


def write_report(rows, path=REPORT):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, REPORT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    check_knobs()
    data = load()
    sql = render(data)
    target = MODULE / "data/sql/db-world/updates" / NAME
    rows = report(data)
    write_migration(MODULE, target, sql)
    write_coupled_outputs(MODULE, target, sql, [(MODULE / "data/generated" / NAME, sql)], label="spawn sheet rows")
    progress_sql = render_progress(data)
    progress_target = MODULE / "data/sql/db-world/updates" / PROGRESS_NAME
    write_migration(MODULE, progress_target, progress_sql)
    write_coupled_outputs(MODULE, progress_target, progress_sql, [(MODULE / "data/generated" / PROGRESS_NAME, progress_sql)],
                          label="monster progress rows")
    write_report(rows)
    print(f"Generated {NAME}: {len(data['sets'])} sets, {len(data['recipes'])} recipes, {len(data['spawn'])} monsters, {len(data['areas'])} tags")
    print(f"Generated {PROGRESS_NAME}: {len(data['progress'])} monsters with D3 progress points "
          f"({len(data['spawn']) - len(data['progress'])} without a row count the default)")
    for r in rows:
        print(f"  set {r['set_id']:>2} {r['name'][:46]:<46} clusters: {r['clusterable_families'] or '-'}"
              + (f" | solos: {r['solo_monsters']}" if r["solo_monsters"] else "") + (" | SKIPPED" if r["skipped"] == "yes" else ""))


if __name__ == "__main__":
    main()

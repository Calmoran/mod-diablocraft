#!/usr/bin/env python3
"""Append newly applied module migrations to data/sql/applied_migrations.csv.

The manifest is the single applied-state authority (GitHub #65, decisions.md
2026-09-23). Generators read it through `applied_migrations.write_migration`;
this tool is its only writer. It runs after a deploy, reads the live `updates`
tables read-only, and appends each module migration they now record that the
manifest does not. Existing rows are never rewritten. A live hash that
disagrees with the repo bytes is a hard error, never a blessed row: an applied
migration whose file changed is exactly the bug the manifest exists to prevent.

Startup synchronization. The worldserver appender opens the log with mode `w`,
truncating it, and the `[DC version]` marker (written after the updater
finishes) can appear before this tool first looks. The deploy step therefore
captures `--since <epoch>` immediately BEFORE launching the server, and the
tool accepts a marker only when the log's mtime is at/after that boundary or a
truncation/replacement has been observed since the previous poll. A marker from
the previous run is never accepted. On any timeout, unreadable config or failed
read the tool exits non-zero and does not read the database, so a slow updater
cannot finish after the read and leave a migration unprotected.

Live mode reads the three connection strings from the worldserver config and
queries each `updates` table with the read-only `mysql` client (SELECT only,
password via `MYSQL_PWD`, bounded process timeout):

    refresh_applied_migrations.py --apply --conf <worldserver.conf> \
        --wait-log <Server.log> --since <launch-epoch>

Fixture mode performs no database or network access, and is how the tool is
tested:

    refresh_applied_migrations.py --evidence module-updates.csv --apply

Dev mode (--dev) reads the dev realm's `updates` tables the same way (its own
worldserver.conf through --conf) and appends to data/sql/applied_migrations_dev.csv,
the dev half of the guard (applied_migrations.py): a file dev has applied before
live. A path the live manifest already lists is skipped, so each applied file is
listed once, by the realm that applied it first.

The dev realm reads its world `updates` table through the refresh user's option file
(--cnf, with --world-db), which holds rights on that one database and nothing else, so
characters and auth migrations are not recorded there; dev_realm.sh runs it after the
dev worldserver starts. --merge-from carries rows another host wrote into this manifest
(a dev realm on another machine): it reads no database, appends the rows this manifest
lacks and treats a different hash for a listed path as a hard error. A row whose file is not in
this checkout is a branch's migration (dev runs unreviewed branches): it cannot carry a hash here
(test_applied_migrations hashes every row), so it is written as a RESERVED row, the path with a
blank sha1 and a provenance starting `reserved on dev, branch`. Its number stays taken for the
generators (applied_migrations.reserved_number, diablocraft-2kmef). The merge after the branch
lands replaces the reserved row with the real one.

Options:
  --apply              write the manifest (default: dry run, print additions)
  --dev                the dev realm: provenance says dev, the default manifest is
                       applied_migrations_dev.csv, rows the live manifest has are skipped
  --manifest PATH      manifest (default mod-diablocraft/data/sql/applied_migrations.csv,
                       or applied_migrations_dev.csv with --dev)
  --repo-root PATH     repository root (default: this file's grandparent)
  --evidence PATH      CSV with path,sha1[,state][,provenance]; no database access
  --conf PATH          worldserver.conf for the database connection strings
  --cnf PATH           mysql option file of a read-only user; reads one world database
  --world-db NAME      the database --cnf reads (the dev realm's world database)
  --merge-from PATH    append the rows of another manifest this one lacks; no database
  --wait-log PATH      wait for a '[DC version]' marker written at/after --since
  --since EPOCH        startup boundary captured before the server launch
  --wait SECONDS       bound on the marker wait (default 120)
  --query-timeout SEC  bound on one mysql process (default 30)
"""

import argparse
import csv
import datetime
import os
import pathlib
import subprocess
import sys
import time

from applied_migrations import DEV_MANIFEST, MANIFEST, RESERVED, SHA1, SQL_DIR, sha1

# (module database folder, worldserver.conf key). The database name itself comes
# from the connection string so nothing here hardcodes acore_*.
DATABASES = (
    ("world", "WorldDatabaseInfo"),
    ("characters", "CharacterDatabaseInfo"),
    ("auth", "LoginDatabaseInfo"),
)
DEFAULT_CONF = pathlib.Path("azerothcore-wotlk/build/server/configs/worldserver.conf")
RELEASED_STATES = ("MODULE", "RELEASED")
MARKER = "[DC version]"


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def read_conf(path):
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"')
    return values


def parse_connection(value):
    parts = value.split(";")
    if len(parts) != 5 or not all(parts):
        raise ValueError(f"expected host;port;user;password;database, got {len(parts)} field(s)")
    host, port, user, password, database = parts
    return {"host": host, "port": port, "user": user, "password": password, "database": database}


def query_updates(connection, timeout):
    """Read one `updates` table. The password goes through the environment (or the
    option file, which must be mysql's first option), the only statement is a
    SELECT, and the process is bounded by `timeout`."""
    tail = [f"--connect-timeout={max(1, int(timeout))}", "-N", "-B", "-e",
            "SELECT name, hash, state FROM updates;", connection["database"]]
    if "cnf" in connection:
        env = {key: value for key, value in os.environ.items() if key != "MYSQL_PWD"}
        command = ["mysql", f"--defaults-extra-file={connection['cnf']}"] + tail
    else:
        env = dict(os.environ, MYSQL_PWD=connection["password"])
        command = ["mysql", "-h", connection["host"], "-P", connection["port"],
                   "-u", connection["user"]] + tail
    try:
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"mysql read timed out after {timeout}s for "
                           f"{connection['database']}") from error
    if result.returncode != 0:
        raise RuntimeError(f"mysql read failed for {connection['database']}: "
                           f"{result.stderr.strip()}")
    rows = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            rows[parts[0]] = (parts[1].upper(), parts[2].upper())
    return rows


def wait_for_version(log, since, timeout, poll=1.0):
    """Wait until a '[DC version]' marker written at/after `since` is in `log`.

    The appender truncates the log on startup, so the file is accepted only when
    its mtime is at/after the launch boundary or a size drop has been seen since
    the previous poll. That rejects the previous run's marker even when it is
    already present, and still catches a marker written before the first poll.
    Returns (True, reason) or (False, reason); it never reads the database.
    """
    deadline = time.monotonic() + timeout
    seen_size = None
    while True:
        try:
            stat = log.stat()
        except FileNotFoundError:
            stat = None
        if stat is not None:
            size = stat.st_size
            truncated = seen_size is not None and size < seen_size
            fresh = truncated or stat.st_mtime >= since
            if fresh and size:
                with log.open(encoding="utf-8", errors="replace") as stream:
                    if MARKER in stream.read():
                        return True, f"'{MARKER}' seen in {log.name} after the launch boundary"
            seen_size = size
        if time.monotonic() >= deadline:
            return False, (f"no '{MARKER}' marker written after the launch boundary "
                           f"within {timeout}s")
        time.sleep(poll)


def conf_connections(args, repo_root):
    conf = pathlib.Path(args.conf) if args.conf else repo_root / DEFAULT_CONF
    if not conf.is_file():
        raise SystemExit(f"no worldserver config at {conf}; pass --conf or use --evidence")
    values = read_conf(conf)
    connections = {}
    for database, key in DATABASES:
        raw = values.get(key)
        if not raw:
            raise SystemExit(f"incomplete live config: {conf} has no {key}; refusing to treat a "
                             f"partially read set of databases as complete")
        try:
            connections[database] = parse_connection(raw)
        except ValueError as error:
            raise SystemExit(f"malformed {key} in {conf}: {error}")
    return connections


def live_rows(args, repo_root):
    if getattr(args, "cnf", None):
        if not args.world_db:
            raise SystemExit("--cnf needs --world-db <database>: the one database it reads")
        connections = {"world": {"cnf": args.cnf, "database": args.world_db}}
    else:
        connections = conf_connections(args, repo_root)
    if args.wait_log:
        if args.since is None:
            raise SystemExit("--wait-log needs --since <epoch> captured before the server start; "
                             "refusing to guess a startup boundary")
        ok, reason = wait_for_version(pathlib.Path(args.wait_log), args.since, args.wait)
        if not ok:
            raise SystemExit(f"startup not confirmed: {reason}")
        print(f"startup confirmed: {reason}")
    out = {}
    for database, connection in connections.items():
        stamp = utc_now()
        for name, (live_sha, state) in query_updates(connection, args.query_timeout).items():
            provenance = (f"confirmed against the {args.realm} updates table: {connection['database']}"
                          f".updates at {stamp}; state={state}")
            out.setdefault(database, {})[name] = (live_sha, state, provenance)
    return out


def evidence_rows(path, realm="live"):
    out = {}
    with pathlib.Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, strict=True):
            relative = row["path"]  # e.g. db-world/updates/foo.sql
            database = pathlib.Path(relative).parts[0][3:]  # strip "db-"
            name = pathlib.Path(relative).name
            state = (row.get("state") or "MODULE").upper()
            provenance = row.get("provenance")
            if not provenance:
                provenance = (f"confirmed against the {realm} updates table: acore_{database}"
                              f".updates at {utc_now()}; state={state}")
            out.setdefault(database, {})[name] = (row["sha1"].upper(), state, provenance)
    return out


def collect(repo_root, rows_by_database):
    """The applied module migrations the live data and the repo agree on, plus
    the paths where they disagree (a changed applied file is a failure)."""
    sql = repo_root / "mod-diablocraft" / SQL_DIR
    found, mismatches = {}, []
    for database, rows in rows_by_database.items():
        directory = sql / f"db-{database}" / "updates"
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.sql")):
            entry = rows.get(path.name)
            if not entry:
                continue
            live_sha, state, provenance = entry
            if state not in RELEASED_STATES:
                continue
            repo_sha = sha1(path.read_bytes())
            if repo_sha != live_sha:
                key = f"db-{database}/updates/{path.name}"
                mismatches.append(key)
                print(f"ERROR: {key} is applied as {live_sha} but the repo bytes hash to "
                      f"{repo_sha}; it changed after it was applied. Not added to the manifest.",
                      file=sys.stderr)
                continue
            found[f"db-{database}/updates/{path.name}"] = (repo_sha, provenance)
    return found, mismatches


def read_manifest(path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def write_manifest(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["path", "sha1", "provenance"])
        for row in sorted(rows, key=lambda item: item["path"]):
            writer.writerow([row["path"], row["sha1"], row["provenance"]])


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--repo-root")
    parser.add_argument("--evidence")
    parser.add_argument("--conf")
    parser.add_argument("--cnf")
    parser.add_argument("--world-db")
    parser.add_argument("--merge-from")
    parser.add_argument("--wait-log")
    parser.add_argument("--since", type=float,
                        help="launch boundary in epoch seconds, captured before the server start")
    parser.add_argument("--wait", type=int, default=120)
    parser.add_argument("--query-timeout", type=int, default=30)
    args = parser.parse_args()

    repo_root = pathlib.Path(args.repo_root).resolve() if args.repo_root \
        else pathlib.Path(__file__).resolve().parents[2]
    args.realm = "dev" if args.dev else "live"
    module = repo_root / "mod-diablocraft"
    manifest = pathlib.Path(args.manifest) if args.manifest \
        else module / (DEV_MANIFEST if args.dev else MANIFEST)

    if args.cnf and args.conf:
        parser.error("--cnf and --conf are two ways to log in; pass one")
    reserved = {}
    try:
        if args.merge_from:
            source = read_manifest(pathlib.Path(args.merge_from))
            for row in source:
                if not SHA1.fullmatch(row["sha1"] or ""):
                    raise ValueError(f"{args.merge_from}: {row['path']} has a malformed sha1")
            found = {row["path"]: (row["sha1"], row["provenance"]) for row in source}
            mismatches = []
            # A manifest row with a hash lists a file of this tree (test_applied_migrations hashes every
            # row). Dev also runs unreviewed branches, so the host's record can hold a file nightly lacks:
            # here it is a reserved row, its number taken and nothing frozen, until the branch lands.
            absent = sorted(path for path in found if not (module / SQL_DIR / path).is_file())
            for path in absent:
                provenance = found.pop(path)[1]
                if args.dev:  # the live manifest has no reserved rows
                    reserved[path] = f"{RESERVED}: {provenance}"
            if absent:
                print(f"{'Reserved' if args.dev else 'Skipped'} {len(absent)} row(s) whose file is not in this "
                      f"checkout (a branch's migration, " + ("a number taken, no hash" if args.dev else "not listed")
                      + "): " + ", ".join(absent))
        else:
            rows_by_database = evidence_rows(args.evidence, args.realm) if args.evidence \
                else live_rows(args, repo_root)
            found, mismatches = collect(repo_root, rows_by_database)
    except (RuntimeError, OSError, UnicodeError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.dev:
        # Live is the realm of record: a file it lists is frozen already, and its row stays there.
        live = {row["path"]: row["sha1"] for row in read_manifest(module / MANIFEST)}
        for path, (repo_sha, _provenance) in list(found.items()):
            if path in live:
                del found[path]
                if live[path] != repo_sha:
                    mismatches.append(path)
                    print(f"ERROR: {path} is applied on dev as {repo_sha} but on live as "
                          f"{live[path]}.", file=sys.stderr)

    existing = read_manifest(manifest)
    known = {row["path"]: row["sha1"] for row in existing}
    additions = []
    for path, provenance in sorted(reserved.items()):
        if path not in known:
            additions.append({"path": path, "sha1": "", "provenance": provenance})
    for path, (repo_sha, provenance) in sorted(found.items()):
        if path not in known:
            additions.append({"path": path, "sha1": repo_sha, "provenance": provenance})
        elif not known[path]:
            # The branch landed: its reserved row gives way to the real one.
            existing = [row for row in existing if row["path"] != path]
            additions.append({"path": path, "sha1": repo_sha, "provenance": provenance})
        elif known[path] != repo_sha:
            mismatches.append(path)
            print(f"ERROR: {path} is in the manifest as {known[path]} but is now applied as "
                  f"{repo_sha}; leaving the manifest row as it was.", file=sys.stderr)

    if additions and args.apply:
        write_manifest(manifest, existing + additions)
        print(f"Appended {len(additions)} row(s); manifest now has {len(existing) + len(additions)}.")
    elif additions:
        for row in additions:
            print(f"  + {row['path']} {row['sha1']}")
        print(f"Dry run: {len(additions)} row(s) would be appended; pass --apply to write.")
    else:
        print(f"Manifest up to date: {len(known)} applied migrations, nothing to append.")

    if mismatches:
        print(f"INCOMPLETE: {len(mismatches)} applied migration(s) changed after they were "
              f"applied; the manifest is not trustworthy until they are fixed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The single applied-state authority for generators (GitHub #65).

The designer's ruling, 2026-09-23 (docs/decisions.md): an applied migration file is
immutable. `mod-diablocraft/data/sql/applied_migrations.csv` -- `path,s ha1,
provenance` -- is the one source of truth for what is applied. It is
bootstrapped from fresh read-only reads of the live `updates` tables and is
thereafter maintained automatically by the deploy step
(`refresh_applied_migrations.py`); it is never hand-edited.

Dev applies nightly's migrations, and the work on dev, before live does, so a
file can be applied on dev and not yet on live. `data/sql/applied_migrations_dev.csv`
(same columns) lists those; `refresh_applied_migrations.py --dev` is its writer
(ruling 2026-10-16, decisions.md). The guard reads both: a path in either is
applied. The dev file may be absent (a checkout with no dev realm); when it is
there it must be well formed, as the live one.

Dev also runs unreviewed branches, and a branch's migration is not in nightly's
tree, so its row cannot carry a hash here. The dev refresh writes it as a
RESERVED row instead (diablocraft-2kmef): the path, a blank sha1 and a provenance
that starts `reserved on dev, branch`. A reserved row freezes nothing, but its
number is taken: `reserved_number` is what every generator that picks its own
next number reads, so two branches never render the same `tunables_0015`. When
the branch lands, the next refresh replaces the reserved row with the real one.

A generator may write a migration only when its path is NOT listed in the
manifest. A listed file whose render would differ is warned about and left
byte-identical, so the change ships as a new migration; a listed file whose
render matches is a no-op. An unlisted path is the task's own new,
not-yet-applied migration and may still be regenerated.

A companion output - a generated C++ header, a client DBC, art, a client
manifest or a `data/generated/` mirror - is coupled to its matching migration.
It may follow a changed sheet only together with a new migration carrying the
same change (docs/decisions.md 2026-09-23, F2). `write_coupled_outputs` holds
such outputs back and warns when the matching migration is applied and its
render differs, so a companion can never silently disagree with the DB rows.
`require_companion_migration` refuses a new migration path that is not directly
under the generator's own `updates/` directory (our approved generator contract,
stricter than the core, which also recurses into subdirectories) or that lacks
the exact `.sql` extension the core loads.

`schema.csv` keeps its release semantics and is never consulted here.
"""

from __future__ import annotations

import csv
import hashlib
import pathlib
import re

MANIFEST = pathlib.Path("data/sql/applied_migrations.csv")
DEV_MANIFEST = pathlib.Path("data/sql/applied_migrations_dev.csv")
SQL_DIR = pathlib.Path("data/sql")
HEADER = ["path", "sha1", "provenance"]
SHA1 = re.compile(r"[0-9A-F]{40}")
RESERVED = "reserved on dev, branch"


MIGRATION_NEW = "new"
MIGRATION_UNCHANGED = "unchanged"
MIGRATION_FROZEN = "frozen"


class AppliedStateError(RuntimeError):
    """The applied-state authority is missing, unreadable or malformed.

    The guard fails closed: without the manifest it cannot tell an applied
    migration from a new one, and guessing would overwrite history. Callers
    must stop rather than generate.
    """


class CompanionMigrationError(RuntimeError):
    """A companion output's migration is not one the core updater will read.

    The core loads files whose extension is exactly `.sql`, recursing into
    `updates/` subdirectories up to a depth limit (`UpdateFetcher.cpp:77-86`).
    Our approved generator contract is stricter: a new migration must sit
    directly in the generator's own default `updates/` folder, because that is
    what every generator and the deploy refresh already treat as the module's
    migrations. A path in `data/generated/`, a `db-world` path outside
    `updates/`, another database's `updates/`, or a wrong extension (`.txt`, no
    suffix, `.SQL`) would publish the companion while the DB rows never change,
    the exact mismatch the guard exists to prevent. The directory check is
    against the generator's default directory, not a global `data/sql` rule, so
    a fixture whose tree lives elsewhere still works.
    """


def _absolute(module_root, target):
    path = pathlib.Path(target)
    if not path.is_absolute():
        path = pathlib.Path(module_root) / path
    return path


def _encoded(content) -> bytes:
    return content if isinstance(content, bytes) else content.encode("utf-8")


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest().upper()


def manifest_key(module_root, target) -> str:
    """The module-relative manifest key for one migration file.

    `target` is either absolute or relative to `module_root`; the result is
    the repo-style path under `data/sql/`, e.g. `db-world/updates/foo.sql`.
    """
    root = pathlib.Path(module_root).resolve()
    path = pathlib.Path(target)
    if not path.is_absolute():
        path = root / path
    return path.resolve().relative_to((root / SQL_DIR).resolve()).as_posix()


def load_manifest(module_root) -> dict:
    """`path -> SHA1` for every migration applied on live or on dev.

    The live manifest is required and the dev one optional (see the module
    docstring); both are read by `_read_manifest`. A path listed in both with two
    different hashes raises: one file applied as two different byte strings is
    the changed-after-applied bug this guard exists to stop.
    """
    manifest = _read_manifest(pathlib.Path(module_root) / MANIFEST)
    dev = pathlib.Path(module_root) / DEV_MANIFEST
    if dev.is_file():
        for key, digest in _read_manifest(dev, set()).items():
            if manifest.get(key, digest) != digest:
                raise AppliedStateError(
                    f"{dev}: {key} is applied on dev as {digest} and on live as {manifest[key]}")
            manifest[key] = digest
    return manifest


def load_reserved(module_root) -> set:
    """The keys dev holds for a branch's migration that is not in this tree (reserved rows).

    Only the dev manifest may carry them. A key that is also applied (the branch landed and its
    real row is there) is not reserved any more.
    """
    dev = pathlib.Path(module_root) / DEV_MANIFEST
    if not dev.is_file():
        return set()
    reserved = set()
    _read_manifest(dev, reserved)
    return reserved - set(load_manifest(module_root))


def reserved_number(module_root, prefix) -> int:
    """The highest NNNN of a reserved `<prefix>_NNNN` migration, or 0 when none is reserved.

    A generator that picks its own next number takes the larger of this and what it finds in the
    tree, so a number a branch already applied on dev is skipped without reading the host.
    """
    pattern = re.compile(rf"{re.escape(prefix)}_(\d+)(?:_|\.)")
    numbers = [int(found.group(1)) for found in
               (pattern.match(pathlib.PurePosixPath(key).name) for key in load_reserved(module_root)) if found]
    return max(numbers, default=0)


def _read_manifest(path, reserved=None) -> dict:
    """`path -> SHA1` for every row of one manifest file.

    Fails closed. A missing, unreadable or malformed manifest raises
    `AppliedStateError`; returning `{}` would tell every generator that nothing
    is applied and let it overwrite history. The exact header
    `path,sha1,provenance` is required first, so a zero-byte or wrong-header
    file cannot pass as an empty authority, and every data row must carry a
    non-blank path and provenance and a well-formed SHA1. A file with exactly
    the header and no data rows is a valid, deliberately empty authority.

    Given a `reserved` set, a row with a blank sha1 and a provenance starting `RESERVED` is
    accepted into it and left out of the result; without one (the live manifest) that row is
    as malformed as any other blank hash.
    """
    if not path.is_file():
        raise AppliedStateError(
            f"{path}: the applied-state manifest is missing. It is the only thing that says "
            f"which migrations are frozen; restore it (the deploy step maintains it) instead "
            f"of generating without it.")
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                raise AppliedStateError(
                    f"{path}: the applied-state manifest is empty; it must start with the "
                    f"header {','.join(HEADER)}")
            if header != HEADER:
                raise AppliedStateError(
                    f"{path}: expected the header {','.join(HEADER)}, got {header!r}")
            rows = []
            for number, cells in enumerate(reader, start=2):
                if len(cells) != len(HEADER):
                    raise AppliedStateError(
                        f"{path}:{number}: expected {len(HEADER)} fields, got {len(cells)}")
                rows.append((number, dict(zip(HEADER, cells))))
    except (OSError, UnicodeError, csv.Error) as error:
        raise AppliedStateError(
            f"{path}: the applied-state manifest cannot be read: {error}") from error
    manifest = {}
    for number, row in rows:
        key, digest, provenance = row["path"].strip(), row["sha1"].strip(), row["provenance"].strip()
        if not key or not provenance:
            raise AppliedStateError(
                f"{path}:{number}: path and provenance must not be blank")
        if not digest and reserved is not None and provenance.startswith(RESERVED):
            reserved.add(key)
            continue
        if not SHA1.fullmatch(digest):
            raise AppliedStateError(
                f"{path}:{number}: sha1 must be 40 uppercase hex digits, got {digest!r}")
        manifest[key] = digest
    return manifest


def is_applied(module_root, target) -> bool:
    return _optional_key(module_root, target) in load_manifest(module_root)


def _optional_key(module_root, target):
    """The manifest key, or None when the target is outside `data/sql/`.

    A generator aimed at a directory that is not the module's own data/sql tree
    (a test fixture, say) has no migration to look up, so the file is written.
    """
    try:
        return manifest_key(module_root, target)
    except ValueError:
        return None


def migration_state(module_root, target, content) -> str:
    """Classify a rendered migration against the applied-state authority.

    One of `MIGRATION_NEW` (the path is unlisted, so it is a not-yet-applied
    migration that may be written), `MIGRATION_UNCHANGED` (listed and its render
    equals the bytes on disk, so there is nothing to write), or
    `MIGRATION_FROZEN` (listed and its render differs, so the applied file must
    not change). The manifest is read first, so a missing or unreadable
    authority raises `AppliedStateError` rather than guessing.
    """
    manifest = load_manifest(module_root)
    path = _absolute(module_root, target)
    encoded = _encoded(content)
    key = _optional_key(module_root, path)
    if key is None or key not in manifest:
        return MIGRATION_NEW
    current = path.read_bytes() if path.is_file() else b""
    return MIGRATION_UNCHANGED if current == encoded else MIGRATION_FROZEN


def require_companion_migration(module_root, migration, updates_dir) -> pathlib.Path:
    """Refuse a companion migration the core updater would never load.

    A companion generator's `--migration` argument exists so a change can ship
    as a new migration. A typo, a path the updater never reads, or a wrong
    extension would let every companion publish while the DB rows stay frozen,
    so this must run before any migration or companion is written. Two checks:

    * the extension must be exactly `.sql` (case-sensitive), matching the core's
      only filter (`UpdateFetcher.cpp:86`), so `.txt`, no suffix and `.SQL` are
      refused;
    * the target must resolve directly under the generator's own default
      migration directory (both sides resolved). This is our approved generator
      contract and is stricter than the core, which also recurses into `updates/`
      subdirectories; it is not a global `data/sql` ban, so a fixture tree
      outside `data/sql` still passes.

    Returns the resolved target for the caller.
    """
    target = _absolute(module_root, migration).resolve()
    expected = _absolute(module_root, updates_dir).resolve()
    if target.parent != expected:
        raise CompanionMigrationError(
            f"{target}: a companion migration must be written directly under {expected}; "
            f"a path the core updater never reads would publish companions without a DB change")
    if target.suffix != ".sql":
        raise CompanionMigrationError(
            f"{target}: a companion migration must end in exact `.sql`; the core updater loads "
            f"no other extension (`UpdateFetcher.cpp`), so companions would publish without a DB change")
    return target


def write_migration(module_root, target, content, *, label=None) -> bool:
    """Write one migration unless `target` is an applied migration.

    Returns True when bytes were written. A listed target is never written:
    a differing render prints a warning naming the file, a matching render is
    silent. An unlisted target (including one outside `data/sql/`) is written
    normally. The manifest is read first, so a missing or unreadable authority
    raises `AppliedStateError` before any migration is written.
    """
    state = migration_state(module_root, target, content)
    if state != MIGRATION_NEW:
        if state == MIGRATION_FROZEN:
            key = _optional_key(module_root, _absolute(module_root, target))
            print(f"WARNING: {key} is an applied migration; its render changed and was NOT "
                  f"written. Ship the change as a new migration (applied_migrations.csv).")
        return False
    path = _absolute(module_root, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encoded(content))
    return True


def write_coupled_outputs(module_root, migration, migration_content, outputs, *, label=None) -> bool:
    """Publish non-migration outputs coupled to one migration render.

    `outputs` is a sequence of `(path, content)` pairs: a generated C++ header,
    a client DBC, art, a client manifest or a `data/generated/` mirror. The
    repository rule (docs/decisions.md 2026-09-23, F2) is that a companion
    output may follow a changed sheet **only together with a new migration that
    carries the same change**. So these outputs are published only when the
    matching migration is new (unlisted) or its render is unchanged. When the
    migration is applied and its render differs, nothing is written and a
    warning names the frozen migration, because shipping a companion alone
    would leave it disagreeing with the DB rows.

    Returns True when the coupled outputs were published (or were already
    identical), False when they were held back. The manifest is read first, so
    a missing or unreadable authority raises `AppliedStateError` before any
    output is written.
    """
    path = _absolute(module_root, migration)
    if migration_state(module_root, path, migration_content) == MIGRATION_FROZEN:
        changed = False
        for target, content in outputs:
            target_path = _absolute(module_root, target)
            encoded = _encoded(content)
            if not target_path.is_file() or target_path.read_bytes() != encoded:
                changed = True
                break
        if not changed:
            return True
        key = _optional_key(module_root, path)
        print(f"WARNING: {label or 'companion outputs'} were not written: the matching migration "
              f"{key} is applied and its render changed. A companion output may follow a changed "
              f"sheet only with a new migration carrying the same change.")
        return False
    for target, content in outputs:
        target_path = _absolute(module_root, target)
        encoded = _encoded(content)
        if target_path.is_file() and target_path.read_bytes() == encoded:
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(encoded)
    return True

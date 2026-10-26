#!/usr/bin/env python3
"""Per-bead reservations of spell ids (diablocraft-syh98).

Two branches that each add a record used to take the same "next free" id from their own base (85921 and 83563 on 2026-10-23),
and the second to merge had to regenerate, rebuild the MPQ and renumber. Now an id is taken from a range reserved for the bead
before the bead was sent to a worker, and the ranges cannot overlap, so two branches cannot pick the same id and no merged id moves.

The sheet is data/spell_id_reservations.csv (bead, pool, first, last, note). It is written on nightly by the PM, who reserves
before dispatching a bead that adds spell ids (the PM extends it when a worker asks); a worker's branch never edits it.
A pool is a block of ids with one kind of owner:

    helper:<class>     the class's helper block, ids the generator picks and keeps in data/generated/spell_helper_ids.csv
    category:<class>   the class's cooldown categories, data/generated/spell_cooldown_categories.csv
    power_buff, gem, pylon   the shared-span blocks whose ids are written by hand in legendary_power_buffs.csv,
                       legendary_gem_spells.csv and pylon_buffs.csv

    spell_id_reservations.py show
    spell_id_reservations.py reserve --bead diablocraft-xyz --take helper:demon_hunter=10 --take power_buff=3 [--dry-run]
    spell_id_reservations.py reserve --bead diablocraft-xyz --take power_buff=83560-83562    (an explicit range, for an id already chosen)
    spell_id_reservations.py release --bead diablocraft-xyz     (after the merge: give back the ids the bead did not use)
    spell_id_reservations.py check [--bead diablocraft-xyz] [--base REV] [--allow-removed ID ...]

`check` is the gate a worker and the Reviewer run on a branch: every id new since the merge-base with nightly must lie in a range
reserved for this bead (or a bead merged into it), no id of the base may be gone or moved, and the sheet must not have been edited.
The generator itself takes new helper and category ids only from the current bead's ranges (generate_spells.py).
The current bead is $TORMENT_BEAD (comma separated) or the branch name w/<bead>.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SHEET_REL = "mod-diablocraft/data/spell_id_reservations.csv"
HEADER = ["bead", "pool", "first", "last", "note"]
BEAD_ID = re.compile(r"^diablocraft-[a-z0-9]+(\.[0-9]+)*$")
BASE_REFS = ("origin/nightly", "nightly")
SHEET_WRITERS = ("nightly", "master")  # the branches the sheet may change on: the PM's


class Refused(SystemExit):
    pass


@dataclass(frozen=True)
class Pool:
    name: str
    first: int
    last: int
    path: str                 # repo-relative; where the ids of this pool are kept
    column: str               # the csv column holding the id
    stem: str | None = None   # when set, only rows whose class column is this class count
    fixed: frozenset = field(default_factory=frozenset)  # ids taken by code, not by the file

    def ids(self, text: str) -> set[int]:
        """The ids of this pool in a copy of its file."""
        found = set()
        for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
            if self.stem is not None and (row.get("class") or "barbarian") != self.stem:
                continue
            found.add(int(row[self.column]))
        return found | set(self.fixed)


def pools_for(g) -> dict[str, Pool]:
    """Every pool, from generate_spells' own constants (g is that module): the blocks are named once, there."""
    helper_file, category_file = "mod-diablocraft/data/generated/spell_helper_ids.csv", "mod-diablocraft/data/generated/spell_cooldown_categories.csv"
    pools: dict[str, Pool] = {}
    blocks = {stem: (b.helpers, b.categories) for stem, b in g.CLASS_BLOCKS.items()}
    blocks.update({stem: (v[1], v[2]) for stem, v in g.RESERVED_BLOCKS.items()})
    for stem, (helpers, categories) in blocks.items():
        pools[f"helper:{stem}"] = Pool(f"helper:{stem}", *helpers, helper_file, "spell_id", stem)
        pools[f"category:{stem}"] = Pool(f"category:{stem}", *categories, category_file, "category", stem)
    pools["power_buff"] = Pool("power_buff", g.POWER_BUFF_ID_FIRST, g.POWER_BUFF_ID_LAST, "mod-diablocraft/data/legendary_power_buffs.csv", "spell_id")
    pools["gem"] = Pool("gem", g.GEM_ID_FIRST, g.GEM_ID_LAST, "mod-diablocraft/data/legendary_gem_spells.csv", "spell_id")
    pools["pylon"] = Pool("pylon", g.PYLON_ID_FIRST, g.PYLON_ID_LAST, "mod-diablocraft/data/pylon_buffs.csv", "spell_id",
                          fixed=frozenset({g.PYLON_CONDUIT_STRIKE, g.PYLON_SPEED_KNOCKUP, g.PYLON_SPEED_THROW}))
    return pools


@dataclass(frozen=True)
class Row:
    bead: str
    pool: str
    first: int
    last: int
    note: str = ""

    def ids(self) -> range:
        return range(self.first, self.last + 1)


def parse_sheet(text: str, pools: dict[str, Pool]) -> list[Row]:
    """The sheet, refused unless sound: a known bead and pool, a range inside the pool's block, no two ranges of a pool overlapping."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    lines = [line for line in reader if line]
    if not lines or lines[0] != HEADER:
        raise Refused(f"spell_id_reservations.csv: the header must be {','.join(HEADER)}")
    rows = []
    for number, line in enumerate(lines[1:], start=2):
        if len(line) != len(HEADER):
            raise Refused(f"spell_id_reservations.csv line {number}: {len(line)} columns, expected {len(HEADER)}")
        bead, pool, first, last, note = line
        if not BEAD_ID.match(bead):
            raise Refused(f"spell_id_reservations.csv line {number}: {bead!r} is not a bead id (diablocraft-<id>)")
        if pool not in pools:
            raise Refused(f"spell_id_reservations.csv line {number}: unknown pool {pool!r}")
        row = Row(bead, pool, int(first), int(last), note)
        block = pools[pool]
        if not block.first <= row.first <= row.last <= block.last:
            raise Refused(f"spell_id_reservations.csv line {number}: {pool} {row.first}-{row.last} is outside its block {block.first}-{block.last}")
        for other in rows:
            if other.pool == pool and row.first <= other.last and other.first <= row.last:
                raise Refused(f"spell_id_reservations.csv: {pool} {row.first}-{row.last} ({bead}) overlaps {other.first}-{other.last} ({other.bead})")
        rows.append(row)
    return rows


def format_sheet(rows: list[Row]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    for row in sorted(rows, key=lambda r: (r.pool, r.first)):
        writer.writerow([row.bead, row.pool, row.first, row.last, row.note])
    return out.getvalue()


def allowed_ids(rows: list[Row], pool: str, beads) -> list[int]:
    """The ids reserved in a pool for any of these beads, lowest first."""
    beads = set(beads)
    return sorted(i for row in rows if row.pool == pool and row.bead in beads for i in row.ids())


def holder_of(rows: list[Row], pool: str, identifier: int) -> str | None:
    return next((row.bead for row in rows if row.pool == pool and row.first <= identifier <= row.last), None)


def no_reservation_message(pool: str, beads) -> str:
    who = ", ".join(sorted(beads)) if beads else "no bead (not on a w/<bead> branch and TORMENT_BEAD is not set)"
    return (f"no free spell id reserved in {pool} for {who}. The PM reserves on nightly before a bead that adds spell ids is sent: "
            f"spell_id_reservations.py reserve --bead <bead> --take {pool}=<count> (docs/contracts/spell-id-reservations.md)")


# ---------------------------------------------------------------- the tree, git and the beads


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def file_at(root: Path, rev: str, rel: str) -> str:
    out = git(root, "show", f"{rev}:{rel}")
    return out.stdout if out.returncode == 0 else ""


def tree_file(root: Path, rel: str) -> str:
    path = root / rel
    return path.read_text(encoding="utf-8-sig") if path.is_file() else ""


def branch_of(root: Path) -> str:
    out = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return out.stdout.strip() if out.returncode == 0 else ""


def current_beads(root: Path = REPO, environ=None) -> list[str]:
    """$TORMENT_BEAD (comma separated) or the bead of the branch w/<bead>; empty when neither names one."""
    env = (environ if environ is not None else os.environ).get("TORMENT_BEAD", "")
    named = [b.strip() for b in env.split(",") if b.strip()]
    if named:
        return named
    branch = branch_of(root)
    return [branch[2:]] if branch.startswith("w/") and BEAD_ID.match(branch[2:]) else []


def base_of(root: Path, explicit: str | None = None) -> str | None:
    """The merge-base of HEAD with nightly (origin/nightly first): what 'already merged' means for this branch."""
    for ref in ([explicit] if explicit else list(BASE_REFS)):
        out = git(root, "merge-base", "HEAD", ref)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    return None


def beads_in_play(root: Path, base: str, environ=None) -> set[str]:
    """This branch's bead, any named in $TORMENT_BEAD, and every w/<bead> branch merged into HEAD but not into the base (a fold)."""
    beads = set(current_beads(root, environ))
    out = git(root, "for-each-ref", "--merged", "HEAD", "--format=%(refname:short)", "refs/heads/w/")
    for ref in out.stdout.split():
        bead = ref[2:]
        if BEAD_ID.match(bead) and git(root, "merge-base", "--is-ancestor", ref, base).returncode != 0:
            beads.add(bead)
    return beads


def check_tree(root: Path, pools: dict[str, Pool], *, base_ref: str | None = None, allow_removed=(), environ=None) -> tuple[list[str], list[str]]:
    """(problems, notes) for the working tree against its base. Problems fail the gate; a note says what was not checked."""
    problems, notes = [], []
    try:
        rows = parse_sheet(tree_file(root, SHEET_REL), pools)
    except Refused as e:
        return [str(e.code)], notes
    base = base_of(root, base_ref)
    if base is None:
        return problems, ["no nightly to compare with (no origin/nightly or nightly ref): new ids not checked"]
    beads = beads_in_play(root, base, environ)
    branch = branch_of(root)
    base_sheet = file_at(root, base, SHEET_REL)
    if branch not in SHEET_WRITERS and rows != (parse_sheet(base_sheet, pools) if base_sheet else []):
        problems.append(f"{SHEET_REL} has reservations nightly's does not: the PM writes the reservations on nightly, a branch never edits the sheet")
    for pool in pools.values():
        head = pool.ids(tree_file(root, pool.path))
        before = pool.ids(file_at(root, base, pool.path))
        for identifier in sorted(before - head - set(map(int, allow_removed))):
            problems.append(f"{pool.name}: id {identifier} was merged and is gone or moved (a merged id never moves; --allow-removed for a deliberate retirement)")
        for identifier in sorted(head - before):
            holder = holder_of(rows, pool.name, identifier)
            if holder in beads:
                continue
            where = f"reserved for {holder}" if holder else "in no reservation"
            problems.append(f"{pool.name}: id {identifier} is new on this branch and {where}; this branch's bead is {', '.join(sorted(beads)) or 'unknown'}")
    return problems, notes


# ---------------------------------------------------------------- reserve and release


def free_run(pool: Pool, taken: set[int], count: int) -> tuple[int, int]:
    run = 0
    for identifier in range(pool.first, pool.last + 1):
        run = 0 if identifier in taken else run + 1
        if run == count:
            return identifier - count + 1, identifier
    raise Refused(f"{pool.name}: no run of {count} free ids in {pool.first}-{pool.last}")


def reserve(rows: list[Row], pools: dict[str, Pool], used: dict[str, set[int]], bead: str, pool_name: str, how: str, note: str = "") -> Row:
    """One new row: `how` is a count (the first free run of that many ids) or FIRST-LAST (an explicit range, for an id already chosen)."""
    if not BEAD_ID.match(bead):
        raise Refused(f"{bead!r} is not a bead id (diablocraft-<id>)")
    if pool_name not in pools:
        raise Refused(f"unknown pool {pool_name!r}; pools: {', '.join(sorted(pools))}")
    pool = pools[pool_name]
    taken = set(used[pool_name]) | {i for row in rows if row.pool == pool_name for i in row.ids()}
    if re.fullmatch(r"\d+-\d+", how):
        first, last = (int(x) for x in how.split("-"))
        if not pool.first <= first <= last <= pool.last:
            raise Refused(f"{pool_name}: {first}-{last} is outside its block {pool.first}-{pool.last}")
        busy = sorted(i for i in range(first, last + 1) if i in taken)
        if busy:
            raise Refused(f"{pool_name}: {busy[0]} is already in use or reserved")
    elif re.fullmatch(r"[1-9]\d*", how):
        first, last = free_run(pool, taken, int(how))
    else:
        raise Refused(f"--take {pool_name}={how}: a count or FIRST-LAST")
    return Row(bead, pool_name, first, last, note)


def release(rows: list[Row], used: dict[str, set[int]], bead: str) -> list[Row]:
    """After the bead's merge: each of its ranges shrinks to the ids actually used (up to the highest), a range with none goes."""
    out = []
    for row in rows:
        if row.bead != bead:
            out.append(row)
            continue
        mine = [i for i in row.ids() if i in used[row.pool]]
        if mine:
            out.append(Row(row.bead, row.pool, row.first, max(mine), row.note))
    return out


# ---------------------------------------------------------------- the command line


def used_now(root: Path, pools: dict[str, Pool]) -> dict[str, set[int]]:
    return {name: pool.ids(tree_file(root, pool.path)) for name, pool in pools.items()}


def load(pools: dict[str, Pool], root: Path = REPO) -> list[Row]:
    return parse_sheet(tree_file(root, SHEET_REL), pools) if (root / SHEET_REL).is_file() else []


class Held:
    """What the generator asks: the ids reserved for the current bead in a pool."""

    def __init__(self, pools: dict[str, Pool], root: Path = REPO, environ=None):
        self.pools, self.root = pools, root
        self.rows = load(pools, root)
        self.beads = current_beads(root, environ)

    def allowed(self, pool: str) -> list[int]:
        return allowed_ids(self.rows, pool, self.beads)

    def shortfall(self, pool: str) -> str:
        return no_reservation_message(pool, self.beads)


def default_pools() -> dict[str, Pool]:
    sys.path.insert(0, str(HERE.parents[1]))
    import scripts_path  # noqa: F401
    import generate_spells
    return pools_for(generate_spells)


def main(argv=None, pools=None, root: Path = REPO) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("show", "reserve", "release", "check"))
    ap.add_argument("--bead")
    ap.add_argument("--take", action="append", default=[], metavar="POOL=COUNT|FIRST-LAST")
    ap.add_argument("--note", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--base", help="check: the ref to compare with (default origin/nightly, then nightly)")
    ap.add_argument("--allow-removed", nargs="*", default=[], help="check: ids deliberately retired")
    ap.add_argument("--root", default=str(root))
    a = ap.parse_args(argv)
    root = Path(a.root)
    pools = pools or default_pools()
    sheet_path = root / SHEET_REL

    if a.command == "check":
        problems, notes = check_tree(root, pools, base_ref=a.base, allow_removed=a.allow_removed,
                                     environ={"TORMENT_BEAD": a.bead} if a.bead else None)
        for note in notes:
            print("note: " + note)
        for problem in problems:
            print("FAIL: " + problem)
        print("spell ids: " + ("not sound" if problems else "sound"))
        return 1 if problems else 0

    rows = parse_sheet(tree_file(root, SHEET_REL), pools) if sheet_path.is_file() else []
    used = used_now(root, pools)
    if a.command == "show":
        for name, pool in pools.items():
            mine = [r for r in rows if r.pool == name]
            print(f"{name}: block {pool.first}-{pool.last}, {len(used[name])} in use" + "".join(f"\n    {r.bead}: {r.first}-{r.last} {r.note}" for r in mine))
        return 0
    if not a.bead:
        raise Refused(f"{a.command} needs --bead")
    if a.command == "reserve":
        if not a.take:
            raise Refused("reserve needs at least one --take POOL=COUNT or POOL=FIRST-LAST")
        for spec in a.take:
            pool_name, _, how = spec.partition("=")
            row = reserve(rows, pools, used, a.bead, pool_name, how, a.note)
            rows.append(row)
            print(f"{a.bead}: {row.pool} {row.first}-{row.last}")
    else:
        rows = release(rows, used, a.bead)
        print(f"{a.bead}: ranges shrunk to the ids in use")
    if a.dry_run:
        print("dry run: the sheet is not written")
        return 0
    sheet_path.write_text(format_sheet(rows), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as e:
        print(f"refused: {e.code}", file=sys.stderr)
        sys.exit(1)

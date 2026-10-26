"""Link a map's server files under a clone's id: Ulduar (603) as the Sanctum of Torment (750), or Kalimdor (1) as 751.

For one server data folder (the one that holds maps/, vmaps/ and mmaps/) this makes a relative symlink for
every file of the source map, named for the clone (the loaders' own name formats):

    maps/603XXYY.map        -> maps/750XXYY.map      (ids are three digits wide: map 1 is 001XXYY.map)
    vmaps/603.vmtree        -> vmaps/750.vmtree
    vmaps/603_XX_YY.vmtile  -> vmaps/750_XX_YY.vmtile
    mmaps/603.mmap          -> mmaps/750.mmap
    mmaps/603XXYY.mmtile    -> mmaps/750XXYY.mmtile

None of these formats carries a map id inside; the loaders find the files by the id in the name, so a link
loads as the clone (docs/research/ulduar-yogg-hub.md section 8e). The ids are the Map row of Combat's sheet,
data/d3/world_sanctum_dbc.csv (generate_hub_sanctum.py), the same source that writes the client and server
DBC rows; `--sheet` names another one with exactly one Map row (data/d3/world_open_rift_dbc.csv: Kalimdor as 751,
the whole continent, 2,341 links; diablocraft-kw18).

    python3 mod-diablocraft/scripts/link_map_clone.py --data <server data dir> [--sheet <sheet csv>] [--dry-run]

Checked before anything is made, and all or nothing: a clone-named path that is a real file, or a link that
points somewhere else, stops the run with nothing changed; so does a data folder that lacks a kind of source
file (a half-made clone would load without collision or without a navmesh). A link that already points at the
source is left alone, so rerunning is a no-op. The links are relative, so the data folder can move.

The server map files are not in a release (make_release.sh carries SQL, Lua, schema and the binary); they sit
in the folder the worldserver's DataDir names, as every other map file does. The PM runs this once on each data
folder (live, then the dev one), dry run first, before the worldserver starts with the hub on map 750. A worker
never runs it on a server.
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_hub_sanctum import SOURCE, SanctumError, read_rows, records  # noqa: E402

FOLDERS = ("maps", "vmaps", "mmaps")
# (folder, the source's file names; {id} is the source map id). The clone keeps everything after the id.
SHAPES = (
    ("maps", r"{id}(\d{{4}})\.map"),
    ("vmaps", r"{id}\.vmtree"),
    ("vmaps", r"{id}_(\d{{2}})_(\d{{2}})\.vmtile"),
    ("mmaps", r"{id}\.mmap"),
    ("mmaps", r"{id}(\d{{4}})\.mmtile"),
)
# Without these two the map loads without collision data or without a navmesh.
REQUIRED = (("vmaps", "{id}.vmtree"), ("mmaps", "{id}.mmap"))


def clone_ids(source=SOURCE):
    """(clone map id, source map id) from the sheet's one Map row."""
    maps = [(row_id, src) for (table, row_id), (src, _) in records(read_rows(source)).items() if table == "Map"]
    if len(maps) != 1:
        raise SanctumError(f"{source}: expected exactly one Map row, found {len(maps)}")
    return maps[0]


def plan(data, clone, source):
    """[(folder, source name, clone name)] for every source file under `data`."""
    data = Path(data)
    wide = f"{source:03d}"  # the loaders' own "%03u" in every file name
    missing = [f for f in FOLDERS if not (data / f).is_dir()]
    if missing:
        raise SanctumError(f"{data}: no {', '.join(missing)} folder; pass the server data dir that holds maps, vmaps, mmaps")
    steps = []
    for folder, shape in SHAPES:
        pattern = re.compile(shape.format(id=wide))
        for name in sorted(os.listdir(data / folder)):
            if pattern.fullmatch(name):
                steps.append((folder, name, f"{clone:03d}" + name[len(wide):]))
    empty = [f for f in FOLDERS if not any(step[0] == f for step in steps)]
    if empty:
        raise SanctumError(f"{data}: no map {source} files in {', '.join(empty)}; is this the right data dir?")
    absent = [f"{folder}/{name.format(id=wide)}" for folder, name in REQUIRED
              if not any(step[0] == folder and step[1] == name.format(id=wide) for step in steps)]
    if absent:
        raise SanctumError(f"{data}: {', '.join(absent)} not found; the clone would load half-made")
    return steps


def classify(data, folder, name, target):
    """'new', 'linked' (already ours) or the reason it is in the way."""
    path = Path(data) / folder / target
    if os.path.islink(path):
        return "linked" if os.readlink(path) == name else f"is a link to {os.readlink(path)}, not to {name}"
    if os.path.lexists(path):
        return "is a real file or folder and will not be overwritten"
    return "new"


def run(data, dry_run=False, source_csv=SOURCE, out=print):
    clone, source = clone_ids(source_csv)
    steps = plan(data, clone, source)
    states = [(step, classify(data, step[0], step[1], step[2])) for step in steps]
    refused = [(step, state) for step, state in states if state not in ("new", "linked")]
    if refused:
        for (folder, _, target), reason in refused:
            out(f"refuse {folder}/{target}: {reason}")
        out(f"nothing changed: {len(refused)} of {len(steps)} paths are in the way")
        return 1
    made = 0
    for (folder, name, target), state in states:
        if state == "linked":
            out(f"ok     {folder}/{target} (already linked)")
            continue
        out(f"{'would link' if dry_run else 'link'} {folder}/{target} -> {name}")
        if not dry_run:
            os.symlink(name, Path(data) / folder / target)
        made += 1
    out(f"map {source} -> {clone}: {len(steps)} files, {made} {'to link' if dry_run else 'linked'}, "
        f"{len(steps) - made} already linked" + (" (dry run, nothing written)" if dry_run else ""))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="server data dir that holds maps/, vmaps/, mmaps/")
    parser.add_argument("--sheet", default=str(SOURCE), help="the sheet whose one Map row names the clone (default: the Sanctum's)")
    parser.add_argument("--dry-run", action="store_true", help="list what would be linked and write nothing")
    args = parser.parse_args(argv)
    try:
        return run(args.data, dry_run=args.dry_run, source_csv=args.sheet)
    except SanctumError as error:
        print(f"link_map_clone: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

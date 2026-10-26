#!/usr/bin/env python3
"""Map-edit pipeline: Noggit ADTs in, client patch input and server map data out.

    mapedit.py check   EDITS                      # validate a folder or .zip, print the tiles
    mapedit.py run     --edits EDITS --client DIR --work DIR [--stage DIR]
                       [--tool-dir DIR] [--live-data DIR] [--dry-run]
    mapedit.py verify-packed [--stage DIR]        # the gate client-patch/build.sh runs

Design: docs/briefs/claude-world-noggit-map-edits-brief.md, guide docs/guide-map-editing.md.

What it does
  1. Refuses anything that is not an .adt under World/Maps/<allowed map>/ with a
     tile name we expect (see ALLOWED_MAPS).
  2. Copies the edited ADTs to <stage>/World/Maps/... (default client-patch/maps),
     which client-patch/build.sh packs into patch-4.MPQ.
  3. Re-extracts the server's map, vmap and mmap files. The stock tools cannot
     re-extract one tile: map_extractor, vmap4_extractor and vmap4_assembler always
     walk every map, and only mmaps_generator takes --tile. So the pipeline runs
     them on a scratch client whose Data folder is symlinks to the designer's client copy
     plus one extra archive (patch-5.MPQ) holding ALL staged edits, then keeps:
       per edited tile  .map, .mmtile, .vmtile;
       per neighbour    .mmtile that really changed;
       per map          the whole vmap set that differs from live: .vmtree, every
                        .vmtile whose bytes differ (a .vmtile stores an index into
                        the .vmtree, so tree and tiles travel together), and the
                        model files (.vmo) the tiles spawn that live lacks.
  4. Writes <stage>/server/{maps,vmaps,mmaps}/ and <stage>/stamp.json. build.sh
     runs `verify-packed` and refuses to pack an ADT whose stamp is missing, stale,
     whose server files are missing, altered or unstamped, whose .vmtree was not
     regenerated, or whose spawned models have no collision file.
  Live baseline: the DataDir of the running worldserver (worldserver.conf), read by
  default. --work must be under azerothcore-wotlk/build/_agent-scratch.

What it never does: publish a release, write the live server data (bin/data maps,
vmaps, mmaps), build the live patch-4.MPQ, or touch azerothcore-wotlk/. The PM
copies <stage>/server/* to the server and runs build.sh at deploy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH_DIR = HERE.parent
REPO = PATCH_DIR.parent
DEFAULT_STAGE = PATCH_DIR / "maps"
CORE = REPO / ("azerothcore" + "-wotlk")
SCRATCH = CORE / "build" / "_agent-scratch"  # every work folder and temp file lives here, never /tmp
WORLDSERVER_CONF = CORE / "build" / "server" / "etc" / "worldserver.conf"

# Map directory name in World/Maps/ -> map id. Add a map only with a ruling.
ALLOWED_MAPS = {"Expansion01": 530}
MAX_TILE = 63
MAX_ADT_BYTES = 16 * 1024 * 1024
MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_ZIP_FILES = 400
ADT_RE = re.compile(r"^(?P<map>[A-Za-z0-9]+)_(?P<x>\d{1,2})_(?P<y>\d{1,2})\.adt$", re.I)
DEFAULT_TOOL_DIR = Path.home() / "azerothcore" / "env" / "dist" / "bin"
EDIT_ARCHIVE = "patch-5.MPQ"  # read by map_extractor and vmap4_extractor, after our patch-4
NEIGHBOUR_CAP = 8  # more changed neighbour files than this means extractor drift, not the edit


class MapEditError(Exception):
    """A refusal, printed as one line."""


@dataclass(frozen=True)
class Tile:
    map_name: str
    map_id: int
    x: int  # first number of Map_X_Y.adt
    y: int
    sha256: str
    size: int

    @property
    def key(self) -> str:
        return f"{self.map_name}_{self.x}_{self.y}"

    @property
    def rel(self) -> str:
        return f"World/Maps/{self.map_name}/{self.key}.adt"

    def server_files(self) -> dict[str, str]:
        return tile_server_files(self.map_id, self.x, self.y)


def tile_server_files(map_id: int, x: int, y: int) -> dict[str, str]:
    """Server file names for ADT Map_<x>_<y>.adt, as the core names them.

    .map and .mmtile: {map:03}{y:02}{x:02}. .vmtile: {map:03}_{x:02}_{y:02}. Read from
    map_extractor/System.cpp (`{:03}{:02}{:02}`, y then x) and TerrainBuilder.cpp, and
    checked against the live data: every live 530 .vmtile a_b has .map and .mmtile
    files named b then a (docs/test-map-editing.md).
    """
    return {
        "map": f"maps/{map_id:03d}{y:02d}{x:02d}.map",
        "mmtile": f"mmaps/{map_id:03d}{y:02d}{x:02d}.mmtile",
        "vmtile": f"vmaps/{map_id:03d}_{x:02d}_{y:02d}.vmtile",
    }


def tile_of(x: float, y: float) -> tuple[int, int]:
    """ADT file numbers (Map_<first>_<second>.adt) for a world position, as .gps prints X and Y."""
    size = 533.33333333
    return int(32 - y / size), int(32 - x / size)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _check_adt_header(data: bytes, label: str) -> None:
    # Chunks are stored byte-reversed: MVER reads "REVM". Version 18 for 3.3.5, then MHDR.
    if len(data) < 24 or data[0:4] != b"REVM" or int.from_bytes(data[4:8], "little") != 4:
        raise MapEditError(f"{label}: not an ADT (no MVER chunk first)")
    if int.from_bytes(data[8:12], "little") != 18:
        raise MapEditError(f"{label}: ADT version {int.from_bytes(data[8:12], 'little')}, 3.3.5 needs 18")
    if data[12:16] != b"DHRM":
        raise MapEditError(f"{label}: ADT has no MHDR chunk after MVER")


def check_tree(root: Path, sub: str | None = None) -> list[Tile]:
    """Validate an edits folder (or only its `sub` folder); return its tiles or raise MapEditError."""
    root = Path(root)
    base = root / sub if sub else root
    if not base.is_dir():
        raise MapEditError(f"{base}: not a folder")
    tiles: dict[str, Tile] = {}
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        here = Path(dirpath)
        for name in dirnames:
            if (here / name).is_symlink():
                raise MapEditError(f"{(here / name).relative_to(root)}: a link, refused")
        for name in filenames:
            path = here / name
            rel = path.relative_to(root)
            if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                raise MapEditError(f"{rel}: not a plain file, refused")
            parts = rel.parts
            if path.suffix.lower() != ".adt":
                raise MapEditError(f"{rel}: file type {path.suffix or '(none)'} is not accepted, only .adt")
            if len(parts) != 4 or parts[0].lower() != "world" or parts[1].lower() != "maps":
                raise MapEditError(f"{rel}: expected World/Maps/<map>/<map>_<x>_<y>.adt")
            match = ADT_RE.match(parts[3])
            if not match:
                raise MapEditError(f"{rel}: not a tile name like Expansion01_21_35.adt")
            canon = {k.lower(): k for k in ALLOWED_MAPS}
            dir_map = canon.get(parts[2].lower())
            file_map = canon.get(match["map"].lower())
            if dir_map is None:
                raise MapEditError(f"{rel}: map {parts[2]} is not allowed (allowed: {', '.join(ALLOWED_MAPS)})")
            if dir_map != file_map:
                raise MapEditError(f"{rel}: file name map {match['map']} does not match its folder {parts[2]}")
            x, y = int(match["x"]), int(match["y"])
            if x > MAX_TILE or y > MAX_TILE:
                raise MapEditError(f"{rel}: tile {x},{y} is outside 0..{MAX_TILE}")
            size = path.stat().st_size
            if size > MAX_ADT_BYTES:
                raise MapEditError(f"{rel}: {size} bytes is over the {MAX_ADT_BYTES} limit")
            with open(path, "rb") as f:
                _check_adt_header(f.read(32), str(rel))
            tile = Tile(dir_map, ALLOWED_MAPS[dir_map], x, y, sha256_file(path), size)
            if tile.key in tiles:
                raise MapEditError(f"{rel}: tile {tile.key} appears twice")
            tiles[tile.key] = tile
    if not tiles:
        raise MapEditError(f"{base}: no .adt files found")
    return sorted(tiles.values(), key=lambda t: (t.map_id, t.x, t.y))


def scratch_dir(name: str) -> Path:
    """A fresh, empty folder under _agent-scratch (never /tmp)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def unpack_zip(zpath: Path, dest: Path) -> Path:
    """Extract a hand-over zip into a new, empty dest, refusing traversal, links and bombs."""
    if dest.exists():
        shutil.rmtree(dest)  # a previous run's ADTs must never come back
    dest.mkdir(parents=True)
    with zipfile.ZipFile(zpath) as z:
        infos = z.infolist()
        if len(infos) > MAX_ZIP_FILES:
            raise MapEditError(f"{zpath.name}: {len(infos)} entries is over the {MAX_ZIP_FILES} limit")
        if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
            raise MapEditError(f"{zpath.name}: unpacks to more than {MAX_ZIP_BYTES} bytes")
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/") or re.match(r"^[A-Za-z]:", name):
                raise MapEditError(f"{zpath.name}: entry {info.filename!r} escapes the folder")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise MapEditError(f"{zpath.name}: entry {info.filename!r} is a link")
            if name.endswith("/"):
                continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return dest


def load_edits(edits: Path, work: Path) -> tuple[Path, list[Tile]]:
    edits = Path(edits)
    if edits.is_file() and edits.suffix.lower() == ".zip":
        root = unpack_zip(edits, work / "edits-unpacked")
        return root, check_tree(root)
    return edits, check_tree(edits)


# --- vmap files -------------------------------------------------------------------------

def vmtile_models(path: Path) -> list[str]:
    """Model names a .vmtile spawns. Layout from ModelSpawn::readFromFile in the core:
    8 magic, u32 count, then per spawn u32 flags, u16 adt, u32 id, 3f pos, 3f rot, f scale,
    [6f bound if flags & 4], u32 nameLen, name, then u32 tree node index."""
    data = Path(path).read_bytes()
    try:
        if not data.startswith(b"VMAP"):
            raise ValueError("no VMAP magic")
        (count,) = struct.unpack_from("<I", data, 8)
        off, names = 12, []
        for _ in range(count):
            (flags,) = struct.unpack_from("<I", data, off)
            off += 4 + 2 + 4 + 12 + 12 + 4 + (24 if flags & 4 else 0)
            (n,) = struct.unpack_from("<I", data, off)
            off += 4
            if n > 500 or off + n + 4 > len(data):
                raise ValueError("bad name length")
            names.append(data[off:off + n].rstrip(b"\0").decode("utf-8"))
            off += n + 4
        if off != len(data):
            raise ValueError("trailing bytes")
        return names
    except (struct.error, ValueError, UnicodeDecodeError) as e:
        raise MapEditError(f"{Path(path).name}: not a readable vmtile ({e})")


def model_file(name: str) -> str:
    return f"vmaps/{name}.vmo"


# --- staging and stamp -----------------------------------------------------------------

def read_stamp(stage: Path) -> dict:
    p = Path(stage) / "stamp.json"
    if not p.is_file():
        return {"version": 2, "tiles": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def write_stamp(stage: Path, stamp: dict) -> None:
    (Path(stage) / "stamp.json").write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stamped_files(stamp: dict) -> dict[str, str]:
    """Every server file the stamp vouches for: relative path -> sha256."""
    files: dict[str, str] = {}
    for entry in stamp.get("tiles", {}).values():
        files.update(entry.get("server", {}))
    files.update(stamp.get("extra_server", {}))
    for v in stamp.get("vmaps", {}).values():
        files.update(v.get("files", {}))
    return files


def verify_packed(stage: Path) -> list[str]:
    """Problems that stop a build: an ADT packed without its regenerated server data."""
    stage = Path(stage)
    problems: list[str] = []
    adt_root = stage / "World"
    if not adt_root.exists() or not any(fs for _d, _s, fs in os.walk(adt_root)):
        return problems  # nothing to pack, nothing to gate
    try:
        tiles = check_tree(stage, sub="World")
    except MapEditError as e:
        return [str(e)]
    stamp = read_stamp(stage)
    server = stage / "server"
    for tile in tiles:
        entry = stamp.get("tiles", {}).get(tile.key)
        if not entry:
            problems.append(f"{tile.key}: no server map data was regenerated for this tile (no stamp entry)")
            continue
        if entry.get("adt_sha256") != tile.sha256:
            problems.append(f"{tile.key}: the ADT changed after its server data was regenerated")
        absent = set(entry.get("absent", []))
        for kind, rel in tile.server_files().items():
            if rel in absent:
                continue
            want = entry.get("server", {}).get(rel)
            if want is None or not (server / rel).is_file():
                problems.append(f"{tile.key}: server file {rel} is missing")
            elif sha256_file(server / rel) != want:
                problems.append(f"{tile.key}: server file {rel} does not match its stamp")
        if not entry.get("server", {}).get(tile.server_files()["map"]):
            problems.append(f"{tile.key}: the .map file is required and is not stamped")
    for map_id in sorted({t.map_id for t in tiles}):
        v = stamp.get("vmaps", {}).get(str(map_id))
        tree = f"vmaps/{map_id:03d}.vmtree"
        if not v or tree not in v.get("files", {}):
            problems.append(f"map {map_id}: {tree} was not regenerated (tile files point into the tree by index)")
            continue
        in_live = set(v.get("models_in_live", [])) | set(v.get("models_without_collision", []))
        for t in (t for t in tiles if t.map_id == map_id):
            vt = t.server_files()["vmtile"]
            if not (server / vt).is_file():
                continue  # reported above unless the tile legitimately has no models
            try:
                names = vmtile_models(server / vt)
            except MapEditError as e:
                problems.append(f"{t.key}: {e}")
                continue
            for name in sorted(set(names)):
                mf = model_file(name)
                if mf not in v["files"] and mf not in in_live:
                    problems.append(f"{t.key}: model {name} has no server collision file ({mf}) and is not recorded as collision-free")
    stamped = stamped_files(stamp)
    for rel, want in sorted(stamped.items()):
        path = server / rel
        if not path.is_file():
            problems.append(f"server file {rel} is missing")
        elif sha256_file(path) != want:
            problems.append(f"server file {rel} does not match its stamp")
    if server.is_dir():
        for dirpath, _d, files in os.walk(server):
            for f in files:
                rel = (Path(dirpath) / f).relative_to(server).as_posix()
                if rel not in stamped:
                    problems.append(f"server file {rel} is not in the stamp")
    return sorted(set(problems))


# --- tools -----------------------------------------------------------------------------

def _run(cmd: list, cwd: Path, log: Path, dry: bool) -> None:
    line = "$ (cd %s && %s)" % (cwd, " ".join(str(c) for c in cmd))
    print(line)
    if dry:
        return
    cwd.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as lf:
        lf.write((line + "\n").encode())
        res = subprocess.run([str(c) for c in cmd], cwd=cwd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    if res.returncode != 0:
        raise MapEditError(f"{cmd[0]} exited {res.returncode}; see {log}")


def _inside(path: Path, parent: Path) -> bool:
    path, parent = Path(os.path.abspath(path)), Path(os.path.abspath(parent))
    return path == parent or parent in path.parents


def default_live_data(conf: Path | None = None) -> Path:
    """The DataDir the running worldserver reads (worldserver.conf), not a guess."""
    conf = Path(conf) if conf else WORLDSERVER_CONF
    if not conf.is_file():
        raise MapEditError(f"{conf}: not found; pass --live-data with the running server's DataDir")
    m = re.search(r'(?m)^\s*DataDir\s*=\s*"([^"]+)"', conf.read_text(encoding="utf-8"))
    if not m:
        raise MapEditError(f"{conf}: no DataDir line; pass --live-data")
    path = Path(m.group(1))
    if not path.is_absolute():
        raise MapEditError(f"{conf}: DataDir {path} is relative; pass --live-data")
    return path


def guard_targets(work: Path, stage: Path, live: Path, tool_dir: Path) -> None:
    """The pipeline writes only to work (under _agent-scratch) and stage; never to live data,
    the tools or patch-4.MPQ."""
    if not _inside(work, SCRATCH) or Path(os.path.abspath(work)) == Path(os.path.abspath(SCRATCH)):
        raise MapEditError(f"--work {work} must be a folder under {SCRATCH}")
    for label, target in (("--work", work), ("--stage", stage)):
        if _inside(target, live) or _inside(live, target):
            raise MapEditError(f"{label} {target} overlaps the live server data {live}; refused")
        if _inside(target, tool_dir) or _inside(tool_dir, target):
            raise MapEditError(f"{label} {target} overlaps the tool folder {tool_dir}; refused")
    if _inside(work, stage) or _inside(stage, work):
        raise MapEditError("--work and --stage must be separate folders")
    if Path(os.path.abspath(stage)) == PATCH_DIR:
        raise MapEditError("--stage must not be client-patch itself")


def build_edit_archive(stage: Path, tiles: list[Tile], out: Path, dry: bool) -> None:
    smpq = shutil.which("smpq")
    if not smpq:
        raise MapEditError("smpq not found: sudo apt install smpq")
    _run([smpq, "--create", "--max-file-count", str(max(16, 2 * len(tiles))), out] + [t.rel for t in tiles],
         stage, out.parent / "log.txt", dry)


def link_client(client: Path, dest_data: Path) -> None:
    src_data = Path(client) / "Data"
    if not src_data.is_dir():
        raise MapEditError(f"{client}: no Data folder; give the folder that holds wow.exe")
    if not any(p.name.lower() == "common.mpq" for p in src_data.iterdir()):
        raise MapEditError(f"{src_data}: no common.MPQ, this is not a 3.3.5 client")
    for p in src_data.iterdir():
        if p.name.lower() == EDIT_ARCHIVE.lower():
            raise MapEditError(f"{p}: the client copy already has {EDIT_ARCHIVE}; take it out and run again")
    dest_data.mkdir(parents=True, exist_ok=True)
    for p in src_data.iterdir():
        link = dest_data / p.name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(p.resolve())


def neighbours(tile: Tile) -> list[tuple[int, int]]:
    return [(tile.x + dx, tile.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if (dx or dy) and 0 <= tile.x + dx <= MAX_TILE and 0 <= tile.y + dy <= MAX_TILE]


def mmaps_config(tool_dir: Path, data_dir: Path, dest: Path) -> None:
    src = tool_dir / "mmaps-config.yaml"
    if not src.is_file():
        raise MapEditError(f"{src}: not found; the mmaps_generator config is needed")
    text = src.read_text(encoding="utf-8")
    new, n = re.subn(r'(?m)^(\s*dataDir:\s*).*$', lambda m: f'{m.group(1)}"{data_dir}/"', text)
    if n != 1:
        raise MapEditError(f"{src}: expected one dataDir line, found {n}")
    dest.write_text(new, encoding="utf-8")


def _find_case(root: Path, t: Tile) -> Path:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".adt" and p.name.lower() == f"{t.key}.adt".lower():
            return p
    raise MapEditError(f"{t.key}: file vanished")


def run_pipeline(edits: Path, client: Path, work: Path, stage: Path, tool_dir: Path, live: Path, dry: bool) -> dict:
    work, stage = Path(work), Path(stage)
    guard_targets(work, stage, live, tool_dir)
    # Every run starts from nothing: an old ADT, fresh extract or Buildings folder must not come back.
    for name in ("edits-unpacked", "client", "fresh", "vm"):
        shutil.rmtree(work / name, ignore_errors=True)
    for name in ("mmaps-config.yaml", "log.txt"):
        (work / name).unlink(missing_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    edits_root, new_tiles = load_edits(edits, work)
    print("edited tiles:", ", ".join(t.key for t in new_tiles))

    # 1. Stage the ADTs for the client patch. The stage is the full set of edited tiles, so the
    #    archive the extractors read holds all of them: vmtree indexes and every vmtile are
    #    rebuilt for the whole map each time.
    if not dry:
        for t in new_tiles:
            dst = stage / t.rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            src = edits_root / t.rel
            shutil.copyfile(src if src.exists() else _find_case(edits_root, t), dst)
        tiles = check_tree(stage, sub="World")
    else:
        merged = {t.key: t for t in (check_tree(stage, sub="World") if (stage / "World").is_dir() else [])}
        merged.update({t.key: t for t in new_tiles})
        tiles = sorted(merged.values(), key=lambda t: (t.map_id, t.x, t.y))
    print(f"stage {stage}/World/Maps holds {len(tiles)} tile(s)" + (" (dry run: not written)" if dry else ""))

    # 2. Scratch client: Data symlinks plus all staged edits in patch-5.MPQ.
    scratch = work / "client"
    data = scratch / "Data"
    log = work / "log.txt"
    if dry:
        print(f"would link {client}/Data into {data} and build {EDIT_ARCHIVE}")
    else:
        link_client(client, data)
        build_edit_archive(stage, tiles, data / EDIT_ARCHIVE, dry)

    # 3. Extract. map_extractor -e 1 = maps only.
    fresh = work / "fresh"
    _run([tool_dir / "map_extractor", "-i", scratch, "-o", fresh, "-e", 1], work, log, dry)
    vm = work / "vm"
    _run([tool_dir / "vmap4_extractor", "-d", data], vm, log, dry)
    _run([tool_dir / "vmap4_assembler", "Buildings", fresh / "vmaps"], vm, log, dry)

    # 4. mmaps for each edited tile and its neighbours (a model near a border changes them).
    cfg = work / "mmaps-config.yaml"
    if not dry:
        mmaps_config(tool_dir, fresh, cfg)
    targets = {(t.map_id, t.x, t.y) for t in tiles}
    build_set = set(targets)
    for t in tiles:
        build_set.update((t.map_id, x, y) for x, y in neighbours(t))
    for map_id, x, y in sorted(build_set):
        if not dry and not (fresh / tile_server_files(map_id, x, y)["map"]).is_file():
            continue  # no terrain there, nothing to build
        _run([tool_dir / "mmaps_generator", map_id, "--tile", f"{x},{y}", "--config", cfg, "--silent"], work, log, dry)

    if dry:
        print("dry run: tools not run, nothing spliced or stamped")
        return {"dry_run": True, "tiles": [t.key for t in tiles]}
    return splice(tiles, targets, build_set, fresh, live, stage, vm / "Buildings")


def splice(tiles, targets, build_set, fresh: Path, live: Path, stage: Path, raw_dir: Path) -> dict:
    """Write <stage>/server and the stamp from a finished extraction.

    Per tile: .map, .mmtile, .vmtile of every edited tile. Per map, the vmaps as one unit:
    a .vmtile stores an index into the map's .vmtree, and the tree is rebuilt from every
    spawn, so the fresh .vmtree plus every fresh .vmtile that differs from live go together,
    plus the model files the tiles spawn that live does not have."""
    server = stage / "server"
    shutil.rmtree(server, ignore_errors=True)  # full regeneration: nothing from an earlier run stays
    stamp: dict = {"version": 2, "tiles": {}, "extra_server": {}, "vmaps": {}}
    drift: list[str] = []
    changed_neighbours: list[str] = []
    models_differing: list[str] = []
    new_no_collision: list[str] = []

    def copy(rel: str) -> str:
        dst = server / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fresh / rel, dst)
        return sha256_file(dst)

    def differs(rel: str) -> bool:
        lv = live / rel
        return not lv.is_file() or sha256_file(fresh / rel) != sha256_file(lv)

    for tile in tiles:
        entry: dict = {"adt_sha256": tile.sha256, "server": {}, "absent": []}
        for kind, rel in tile.server_files().items():
            if (fresh / rel).is_file():
                entry["server"][rel] = copy(rel)
            elif kind == "map":
                raise MapEditError(f"{tile.key}: the extractor produced no {rel}; the ADT is not being read")
            else:
                entry["absent"].append(rel)  # no models or no walkable ground on this tile
        stamp["tiles"][tile.key] = entry

    for map_id, x, y in sorted(build_set - targets):
        for kind, rel in tile_server_files(map_id, x, y).items():
            if kind == "vmtile" or not (fresh / rel).is_file():
                continue
            if differs(rel):
                (drift if kind == "map" else changed_neighbours).append(rel)  # an untouched .map differing is drift
    if len(changed_neighbours) > NEIGHBOUR_CAP or len(drift) > NEIGHBOUR_CAP:
        raise MapEditError(
            f"{len(changed_neighbours)} neighbour file(s) and {len(drift)} untouched .map file(s) differ from live: "
            "that is extractor or data drift, not your edit. Nothing was stamped. Ask the PM.")
    for rel in changed_neighbours:
        stamp["extra_server"][rel] = copy(rel)

    for map_id in sorted({t.map_id for t in tiles}):
        tree = f"vmaps/{map_id:03d}.vmtree"
        if not (fresh / tree).is_file():
            raise MapEditError(f"the assembler produced no {tree}")
        files = {tree: copy(tree)}
        remove: list[str] = []
        edited_vt = {t.server_files()["vmtile"] for t in tiles if t.map_id == map_id}
        fresh_vt = {p.relative_to(fresh).as_posix() for p in (fresh / "vmaps").glob(f"{map_id:03d}_*_*.vmtile")}
        for rel in sorted(fresh_vt):
            if rel in edited_vt or differs(rel):
                files[rel] = copy(rel)
        for p in sorted((live / "vmaps").glob(f"{map_id:03d}_*_*.vmtile")) if (live / "vmaps").is_dir() else []:
            rel = p.relative_to(live).as_posix()
            if rel not in fresh_vt:
                remove.append(rel)  # the edit left this tile with no models
        in_live: list[str] = []
        no_collision: list[str] = []
        for rel in sorted(fresh_vt):
            for name in sorted(set(vmtile_models(fresh / rel))):
                mf = model_file(name)
                if mf in files or mf in in_live:
                    continue
                if (fresh / mf).is_file() and not (live / mf).is_file():
                    files[mf] = copy(mf)
                elif (live / mf).is_file():
                    in_live.append(mf)
                    if (fresh / mf).is_file() and differs(mf):
                        models_differing.append(mf)
                elif (raw_dir / name).is_file():
                    raise MapEditError(f"{rel} spawns {name}: the extractor made collision geometry for it but the assembler wrote no {mf}")
                else:
                    no_collision.append(mf)  # the model has no collision mesh: it looks solid and blocks nothing
        for t in (t for t in tiles if t.map_id == map_id):
            rel = t.server_files()["vmtile"]
            if rel not in fresh_vt:
                continue
            before = set(vmtile_models(live / rel)) if (live / rel).is_file() else set()
            for name in sorted(set(vmtile_models(fresh / rel)) - before):
                if model_file(name) in no_collision:
                    new_no_collision.append(f"{t.key}: {name}")
        stamp["vmaps"][str(map_id)] = {"files": files, "remove": remove, "models_in_live": sorted(set(in_live)),
                                       "models_without_collision": sorted(set(no_collision))}
        navmesh = f"mmaps/{map_id:03d}.mmap"
        if (fresh / navmesh).is_file() and differs(navmesh):
            stamp["extra_server"][navmesh] = copy(navmesh)  # navmesh parameters: unexpected, PM must look
            changed_neighbours.append(navmesh)

    write_stamp(stage, stamp)
    problems = verify_packed(stage)
    if problems:
        raise MapEditError("; ".join(problems))
    report = {"dry_run": False, "tiles": [t.key for t in tiles], "neighbours_changed": changed_neighbours,
              "untouched_map_files_differing_from_live": drift,
              "vmap_files": {m: len(v["files"]) for m, v in stamp["vmaps"].items()},
              "vmap_files_to_remove": {m: v["remove"] for m, v in stamp["vmaps"].items()},
              "existing_models_differing_from_live": models_differing,
              "new_models_in_edited_tiles_without_collision": new_no_collision}
    print(json.dumps(report, indent=2))
    return report


def deploy_plan(stage: Path, live: Path) -> str:
    """Text for the PM: the copies to run at deploy, with the worldserver stopped. Nothing is run."""
    stamp = read_stamp(stage)
    lines = [f"# worldserver stopped; live DataDir {live}"]
    lines += [f"cp {stage}/server/{r} {live}/{r}" for r in sorted(stamped_files(stamp))]
    for v in stamp.get("vmaps", {}).values():
        lines += [f"rm {live}/{r}" for r in v.get("remove", [])]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("edits")
    r = sub.add_parser("run")
    r.add_argument("--edits", required=True)
    r.add_argument("--client", required=True)
    r.add_argument("--work", required=True, help="a folder under azerothcore-wotlk/build/_agent-scratch")
    r.add_argument("--stage", default=str(DEFAULT_STAGE))
    r.add_argument("--tool-dir", default=str(DEFAULT_TOOL_DIR))
    r.add_argument("--live-data", default=None, help="default: DataDir from the running worldserver.conf")
    r.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("tile", help="which ADT holds a world position (.gps X Y)")
    t.add_argument("x", type=float)
    t.add_argument("y", type=float)
    v = sub.add_parser("verify-packed")
    v.add_argument("--stage", default=str(DEFAULT_STAGE))
    d = sub.add_parser("deploy-plan")
    d.add_argument("--stage", default=str(DEFAULT_STAGE))
    d.add_argument("--live-data", default=None)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "check":
            src = Path(a.edits)
            if src.is_file():
                _root, tiles = load_edits(src, scratch_dir(f"mapedit-check-{os.getpid()}"))
                shutil.rmtree(SCRATCH / f"mapedit-check-{os.getpid()}", ignore_errors=True)
            else:
                tiles = check_tree(src)
            for t in tiles:
                print(f"{t.key}\tmap {t.map_id}\t{t.size} bytes\t" + "\t".join(t.server_files().values()))
            return 0
        if a.cmd == "run":
            live = Path(a.live_data) if a.live_data else default_live_data()
            run_pipeline(Path(a.edits), Path(a.client), Path(a.work), Path(a.stage), Path(a.tool_dir), live, a.dry_run)
            return 0
        if a.cmd == "tile":
            fx, fy = tile_of(a.x, a.y)
            print(f"Expansion01_{fx}_{fy}.adt  " + "  ".join(tile_server_files(530, fx, fy).values()))
            return 0
        if a.cmd == "verify-packed":
            problems = verify_packed(Path(a.stage))
            for p in problems:
                print("REFUSED:", p, file=sys.stderr)
            return 1 if problems else 0
        if a.cmd == "deploy-plan":
            live = Path(a.live_data) if a.live_data else default_live_data()
            print(deploy_plan(Path(a.stage), live))
            return 0
    except (MapEditError, zipfile.BadZipFile, OSError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())

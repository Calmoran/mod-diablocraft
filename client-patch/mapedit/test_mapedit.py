#!/usr/bin/env python3
"""Tests for mapedit.py: python3 client-patch/mapedit/test_mapedit.py

The extractor tools are replaced by small fake programs. They write files named and laid
out exactly as the real ones do (the .vmtile layout is the core's ModelSpawn), and they
learn which tiles were edited by listing the patch-5.MPQ the pipeline built, so a pipeline
that failed to hand the edits over would show up here. All temp files live under
_agent-scratch, never /tmp.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mapedit as M  # noqa: E402

SCRATCH = M.SCRATCH
LIVE_BIN = Path.home() / "azerothcore" / "env" / "dist" / "bin"  # the OLD tool folder; not the server's data


def adt_bytes(extra: bytes = b"") -> bytes:
    return b"REVM" + (4).to_bytes(4, "little") + (18).to_bytes(4, "little") + b"DHRM" + (64).to_bytes(4, "little") + bytes(64) + extra


def put(root: Path, rel: str, data: bytes = None) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(adt_bytes() if data is None else data)
    return p


def vmtile_bytes(names: list[str]) -> bytes:
    """A .vmtile as ModelSpawn::writeToFile lays it out (no bound flag)."""
    out = b"VMAP_7.0" + struct.pack("<I", len(names))
    for i, n in enumerate(names):
        nb = n.encode() + b"\0"
        out += struct.pack("<IHI", 1, 0, i) + bytes(28) + struct.pack("<I", len(nb)) + nb + struct.pack("<I", i)
    return out


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


FAKE_COMMON = '''
import subprocess, sys, pathlib, re, struct
def edited(archive):
    out = subprocess.run(["smpq", "--list", str(archive)], capture_output=True, text=True).stdout
    return sorted({(int(m[1]), int(m[2])) for m in re.finditer(r"_(\\d+)_(\\d+)\\.adt", out)})
def flag(name):
    return pathlib.Path(__file__).with_name(name).exists()
def vmtile(names):
    out = b"VMAP_7.0" + struct.pack("<I", len(names))
    for i, n in enumerate(names):
        nb = n.encode() + b"\\0"
        out += struct.pack("<IHI", 1, 0, i) + bytes(28) + struct.pack("<I", len(nb)) + nb + struct.pack("<I", i)
    return out
'''

FAKE_MAP_EXTRACTOR = FAKE_COMMON + '''
a = sys.argv
root = pathlib.Path(a[a.index("-i") + 1])
out = pathlib.Path(a[a.index("-o") + 1]) / "maps"
out.mkdir(parents=True, exist_ok=True)
ed = edited(root / "Data" / "patch-5.MPQ")
if not flag("skip_map"):
    for y in (34, 35, 36):
        for x in (20, 21, 22, 23):
            (out / f"530{y:02d}{x:02d}.map").write_bytes(b"map-%d-%d" % (x, y) + (b"-EDITED" if (x, y) in ed else b""))
'''
FAKE_VMAP_EXTRACTOR = FAKE_COMMON + '''
a = sys.argv
ed = edited(pathlib.Path(a[a.index("-d") + 1]) / "patch-5.MPQ")
pathlib.Path("Buildings").mkdir(exist_ok=True)
pathlib.Path("Buildings/edited.txt").write_text(repr(ed))
pathlib.Path("Buildings/Rock.m2").write_bytes(b"raw")
pathlib.Path("Buildings/Wall.m2").write_bytes(b"raw")
if flag("ghost_model"):
    pathlib.Path("Buildings/Ghost.m2").write_bytes(b"raw")
'''
FAKE_VMAP_ASSEMBLER = FAKE_COMMON + '''
dest = pathlib.Path(sys.argv[2]); dest.mkdir(parents=True, exist_ok=True)
ed = eval(pathlib.Path(sys.argv[1], "edited.txt").read_text())
(dest / "530.vmtree").write_bytes(b"VMAP_7.0tree-" + repr(ed).encode())
for x in (20, 21, 22, 23):
    for y in (34, 35, 36):
        names = ["Rock.m2"]
        if (x, y) in ed:
            names += ["Wall.m2"] + (["Ghost.m2"] if flag("ghost_model") else []) + (["Fluff.m2"] if flag("fluff_model") else [])
        if (x, y) == (22, 35) and flag("touch_neighbour"):
            names += ["Rock.m2"]
        if flag("shift_all"):
            names += ["Rock.m2"] * 2  # what a changed tree index does: every tile's bytes change
        if (x, y) == (21, 35) and flag("no_models_on_tile"):
            continue
        (dest / f"530_{x:02d}_{y:02d}.vmtile").write_bytes(vmtile(names))
(dest / "Rock.m2.vmo").write_bytes(b"rock-fresh" if flag("rock_differs") else b"rock")
(dest / "Wall.m2.vmo").write_bytes(b"wall")
'''
FAKE_MMAPS = FAKE_COMMON + '''
a = sys.argv
x, y = map(int, a[a.index("--tile") + 1].split(","))
cfg = pathlib.Path(a[a.index("--config") + 1]).read_text()
data = pathlib.Path(re.search(r'dataDir:\\s*"(.*)/"', cfg).group(1))
ed = edited(data.parent / "client" / "Data" / "patch-5.MPQ")
(data / "mmaps").mkdir(exist_ok=True)
(data / "mmaps" / "530.mmap").write_bytes(b"nav-CHANGED" if flag("navmesh_changes") else b"nav")
(data / "mmaps" / f"530{y:02d}{x:02d}.mmtile").write_bytes(b"mm-%d-%d" % (x, y) + (b"-EDITED" if (x, y) in ed else b""))
'''


def make_tools(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in (("map_extractor", FAKE_MAP_EXTRACTOR), ("vmap4_extractor", FAKE_VMAP_EXTRACTOR),
                       ("vmap4_assembler", FAKE_VMAP_ASSEMBLER), ("mmaps_generator", FAKE_MMAPS)):
        p = root / name
        p.write_text("#!/usr/bin/env python3\n" + body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    (root / "mmaps-config.yaml").write_text('mmapsConfig:\n  skipLiquid: false\n  dataDir: "./"\n')
    return root


def make_live(root: Path) -> Path:
    """What the running server already has: unedited versions of the tile grid."""
    for sub in ("maps", "mmaps", "vmaps"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    for y in (34, 35, 36):
        for x in (20, 21, 22, 23):
            (root / "maps" / f"530{y:02d}{x:02d}.map").write_bytes(b"map-%d-%d" % (x, y))
            (root / "mmaps" / f"530{y:02d}{x:02d}.mmtile").write_bytes(b"mm-%d-%d" % (x, y))
            (root / "vmaps" / f"530_{x:02d}_{y:02d}.vmtile").write_bytes(vmtile_bytes(["Rock.m2"]))
    (root / "vmaps" / "530.vmtree").write_bytes(b"VMAP_7.0tree-v1")
    (root / "vmaps" / "Rock.m2.vmo").write_bytes(b"rock")
    (root / "mmaps" / "530.mmap").write_bytes(b"nav")
    return root


class Base(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="mapedit_test_", dir=SCRATCH))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.edits = self.tmp / "edits"
        put(self.edits, "World/Maps/Expansion01/Expansion01_21_35.adt")


class TestRefusals(Base):
    def refused(self, rel: str, data: bytes = None, msg: str = ""):
        root = self.tmp / "bad"
        shutil.rmtree(root, True)
        put(root, rel, data)
        with self.assertRaises(M.MapEditError, msg=rel) as cm:
            M.check_tree(root)
        if msg:
            self.assertIn(msg, str(cm.exception))

    def test_good_tree(self):
        tiles = M.check_tree(self.edits)
        self.assertEqual([(t.map_id, t.x, t.y) for t in tiles], [(530, 21, 35)])

    def test_uppercase_extension_is_accepted(self):
        root = self.tmp / "up"
        put(root, "World/Maps/Expansion01/Expansion01_21_35.ADT")
        self.assertEqual(M.check_tree(root)[0].key, "Expansion01_21_35")

    def test_unexpected_file_types_are_refused(self):
        for name in ("Expansion01_21_35.blp", "Expansion01_21_35.dbc", "Expansion01_21_35.wdt", "run.exe",
                     "Expansion01_21_35.m2", "Expansion01_21_35_obj0.adt.bak", "notes.txt", "x.lua"):
            self.refused(f"World/Maps/Expansion01/{name}", msg="")

    def test_unexpected_map_is_refused(self):
        self.refused("World/Maps/Azeroth/Azeroth_21_35.adt", msg="not allowed")
        self.refused("World/Maps/Kalimdor/Kalimdor_1_1.adt", msg="not allowed")

    def test_file_name_map_must_match_folder(self):
        self.refused("World/Maps/Expansion01/Azeroth_21_35.adt", msg="does not match its folder")

    def test_bad_tile_names_and_layout(self):
        self.refused("World/Maps/Expansion01/Expansion01_64_1.adt", msg="outside")
        self.refused("World/Maps/Expansion01/Expansion01_a_1.adt", msg="tile name")
        self.refused("Expansion01_21_35.adt", msg="expected World/Maps")
        self.refused("World/Maps/Expansion01/sub/Expansion01_21_35.adt", msg="expected World/Maps")

    def test_not_an_adt(self):
        self.refused("World/Maps/Expansion01/Expansion01_21_35.adt", data=b"MZ" + bytes(60), msg="not an ADT")
        self.refused("World/Maps/Expansion01/Expansion01_21_35.adt",
                     data=b"REVM" + (4).to_bytes(4, "little") + (17).to_bytes(4, "little") + b"DHRM" + bytes(40), msg="needs 18")

    def test_links_are_refused(self):
        root = self.tmp / "lnk"
        target = put(self.tmp, "real.adt")
        d = root / "World/Maps/Expansion01"
        d.mkdir(parents=True)
        (d / "Expansion01_21_35.adt").symlink_to(target)
        with self.assertRaises(M.MapEditError):
            M.check_tree(root)

    def test_empty_is_refused(self):
        (self.tmp / "empty").mkdir()
        with self.assertRaises(M.MapEditError):
            M.check_tree(self.tmp / "empty")

    def test_zip_traversal_and_types(self):
        z = self.tmp / "bad.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("../evil.adt", adt_bytes())
        with self.assertRaises(M.MapEditError):
            M.load_edits(z, self.tmp / "w")
        z2 = self.tmp / "bad2.zip"
        with zipfile.ZipFile(z2, "w") as f:
            f.writestr("World/Maps/Expansion01/Expansion01_21_35.adt", adt_bytes())
            f.writestr("World/Maps/Expansion01/payload.exe", b"MZ")
        with self.assertRaises(M.MapEditError):
            M.load_edits(z2, self.tmp / "w2")

    def test_good_zip_and_unpack_starts_empty(self):
        z = self.tmp / "ok.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("World/Maps/Expansion01/Expansion01_21_35.adt", adt_bytes())
        work = self.tmp / "w3"
        put(work / "edits-unpacked", "World/Maps/Expansion01/Expansion01_22_35.adt")  # left by an earlier run
        _root, tiles = M.load_edits(z, work)
        self.assertEqual([t.key for t in tiles], ["Expansion01_21_35"])

    def test_check_on_a_zip_uses_scratch_not_tmp(self):
        z = self.tmp / "ok.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("World/Maps/Expansion01/Expansion01_21_35.adt", adt_bytes())
        self.assertNotIn("tempfile", (HERE / "mapedit.py").read_text())
        before = set(os.listdir(tempfile.gettempdir()))
        self.assertEqual(M.main(["check", str(z)]), 0)
        self.assertEqual(set(os.listdir(tempfile.gettempdir())) - before, set())
        self.assertFalse(any(p.name.startswith("mapedit-check-") for p in SCRATCH.iterdir()))


class TestNames(unittest.TestCase):
    def test_hub_tile_names(self):
        f = M.tile_server_files(530, 21, 35)
        self.assertEqual(f, {"map": "maps/5303521.map", "mmtile": "mmaps/5303521.mmtile",
                             "vmtile": "vmaps/530_21_35.vmtile"})

    def test_hub_points_are_in_tile_21_35(self):
        # spawn and town_portal from world_hub_points (world_0005_shattrath_hub.sql)
        self.assertEqual(M.tile_of(-2075.5803, 5501.261), (21, 35))
        self.assertEqual(M.tile_of(-2103.0986, 5491.8203), (21, 35))
        self.assertEqual(M.tile_of(-2140.0, 5500.0), (21, 36))  # lower X than -2133.3 (further south) is the next tile

    def test_vmtile_parser_reads_the_core_layout(self):
        p = SCRATCH / "vmtile_parser_probe.vmtile"
        SCRATCH.mkdir(parents=True, exist_ok=True)
        p.write_bytes(vmtile_bytes(["A.m2", "B.wmo", "A.m2"]))
        try:
            self.assertEqual(M.vmtile_models(p), ["A.m2", "B.wmo", "A.m2"])
            p.write_bytes(vmtile_bytes(["A.m2"])[:-3])
            with self.assertRaises(M.MapEditError):
                M.vmtile_models(p)
        finally:
            p.unlink()

    def test_default_live_data_is_the_worldserver_datadir(self):
        conf = SCRATCH / "test_worldserver.conf"
        SCRATCH.mkdir(parents=True, exist_ok=True)
        conf.write_text('# DataDir = "/wrong"\nDataDir = "/srv/x/data"\n')
        try:
            self.assertEqual(M.default_live_data(conf), Path("/srv/x/data"))
            conf.write_text('DataDir = "relative/data"\n')
            with self.assertRaises(M.MapEditError):
                M.default_live_data(conf)
        finally:
            conf.unlink()
        self.assertIsNone(M.build_parser().parse_args(["run", "--edits", "e", "--client", "c", "--work", "w"]).live_data)

    @unittest.skipUnless(M.WORLDSERVER_CONF.is_file(), "no worldserver.conf on this host")
    def test_default_live_data_on_this_host_is_not_the_old_tool_folder(self):
        live = M.default_live_data()
        m = re.search(r'(?m)^DataDir\s*=\s*"([^"]+)"', M.WORLDSERVER_CONF.read_text())
        self.assertEqual(str(live), m.group(1))
        self.assertNotEqual(live, LIVE_BIN)
        self.assertTrue((live / "vmaps").is_dir())

    @unittest.skipUnless(M.WORLDSERVER_CONF.is_file() and (M.default_live_data() / "vmaps").is_dir(), "no live data on this host")
    def test_naming_matches_live_data(self):
        """Every live 530 vmtile a_b has its .map and .mmtile named by the same rule (read only)."""
        live = M.default_live_data()
        seen = 0
        for p in (live / "vmaps").glob("530_*_*.vmtile"):
            a, b = map(int, re.match(r"530_(\d+)_(\d+)\.vmtile", p.name).groups())
            self.assertTrue((live / M.tile_server_files(530, a, b)["map"]).is_file(), p.name)
            seen += 1
        self.assertGreater(seen, 100)

    @unittest.skipUnless(M.WORLDSERVER_CONF.is_file() and (M.default_live_data() / "vmaps").is_dir(), "no live data on this host")
    def test_live_vmtiles_parse_and_their_models_exist(self):
        live = M.default_live_data()
        names = M.vmtile_models(live / "vmaps" / "530_21_35.vmtile")
        self.assertGreater(len(names), 100)
        missing = [n for n in set(names) if not (live / M.model_file(n)).is_file()]
        # decorations with no collision mesh have no .vmo at all: 13 of 233 on this tile today
        self.assertLess(len(missing), len(set(names)) // 4, missing)


class Pipeline(Base):
    def setUp(self):
        super().setUp()
        self.tools = make_tools(self.tmp / "tools")
        self.live = make_live(self.tmp / "live")
        self.client = self.tmp / "client"
        (self.client / "Data" / "enUS").mkdir(parents=True)
        (self.client / "Data" / "common.MPQ").write_bytes(b"")
        self.stage = self.tmp / "stage"
        self.work = self.tmp / "work"

    def flag(self, name: str):
        (self.tools / name).write_text("")

    def run_pipeline(self, edits=None, **kw):
        args = dict(edits=edits or self.edits, client=self.client, work=self.work, stage=self.stage,
                    tool_dir=self.tools, live=self.live, dry=False)
        args.update(kw)
        return M.run_pipeline(args["edits"], args["client"], args["work"], args["stage"],
                              args["tool_dir"], args["live"], args["dry"])

    def zip_of(self, name: str, *tiles: str) -> Path:
        z = self.tmp / name
        with zipfile.ZipFile(z, "w") as f:
            for t in tiles:
                f.writestr(f"World/Maps/Expansion01/Expansion01_{t}.adt", adt_bytes())
        return z

    def stamp_files(self, map_id="530"):
        return M.read_stamp(self.stage)["vmaps"][map_id]["files"]


@unittest.skipUnless(shutil.which("smpq"), "smpq not installed")
class TestRun(Pipeline):
    def test_full_run_then_gate_passes(self):
        report = self.run_pipeline()
        self.assertEqual(M.verify_packed(self.stage), [])
        self.assertTrue((self.stage / "World/Maps/Expansion01/Expansion01_21_35.adt").is_file())
        self.assertIn(b"EDITED", (self.stage / "server/maps/5303521.map").read_bytes())
        self.assertIn(b"EDITED", (self.stage / "server/mmaps/5303521.mmtile").read_bytes())
        self.assertIn("Wall.m2", M.vmtile_models(self.stage / "server/vmaps/530_21_35.vmtile"))
        self.assertTrue((self.work / "client/Data/patch-5.MPQ").is_file())
        self.assertTrue((self.work / "client/Data/common.MPQ").is_symlink())
        self.assertEqual(report["neighbours_changed"], [])

    def test_vmap_set_travels_together(self):
        """The tree, the new model and the edited tile are all in the bundle; a model live has is not."""
        self.run_pipeline()
        files = self.stamp_files()
        self.assertIn("vmaps/530.vmtree", files)
        self.assertIn("vmaps/530_21_35.vmtile", files)
        self.assertIn("vmaps/Wall.m2.vmo", files)          # new model: no server collision without it
        self.assertNotIn("vmaps/Rock.m2.vmo", files)       # live already has it
        self.assertIn("vmaps/Rock.m2.vmo", M.read_stamp(self.stage)["vmaps"]["530"]["models_in_live"])
        self.assertNotIn("vmaps/530_20_34.vmtile", files)  # identical to live: not copied
        self.assertTrue((self.stage / "server/vmaps/530.vmtree").is_file())
        self.assertTrue((self.stage / "server/vmaps/Wall.m2.vmo").is_file())

    def test_a_shifted_tree_index_carries_every_changed_tile(self):
        self.flag("shift_all")
        self.run_pipeline()
        files = self.stamp_files()
        self.assertEqual(len([f for f in files if f.endswith(".vmtile")]), 12)
        self.assertEqual(M.verify_packed(self.stage), [])

    def test_a_model_the_assembler_lost_stops_the_run(self):
        self.flag("ghost_model")
        with self.assertRaises(M.MapEditError) as cm:
            self.run_pipeline()
        self.assertIn("Ghost.m2", str(cm.exception))

    def test_a_new_model_without_collision_is_reported_not_hidden(self):
        """Like the 13 decorations already on the live hub tile: spawned, no .vmo, blocks nothing."""
        self.flag("fluff_model")
        report = self.run_pipeline()
        self.assertEqual(report["new_models_in_edited_tiles_without_collision"], ["Expansion01_21_35: Fluff.m2"])
        self.assertIn("vmaps/Fluff.m2.vmo", M.read_stamp(self.stage)["vmaps"]["530"]["models_without_collision"])
        self.assertEqual(M.verify_packed(self.stage), [])

    def test_a_tile_left_with_no_models_is_removed_from_live(self):
        self.flag("no_models_on_tile")
        self.run_pipeline()
        v = M.read_stamp(self.stage)["vmaps"]["530"]
        self.assertEqual(v["remove"], ["vmaps/530_21_35.vmtile"])
        self.assertIn(f"rm {self.live}/vmaps/530_21_35.vmtile", M.deploy_plan(self.stage, self.live))
        self.assertEqual(M.verify_packed(self.stage), [])

    def test_deploy_plan_targets_the_given_live_folder(self):
        self.run_pipeline()
        plan = M.deploy_plan(self.stage, self.live)
        self.assertIn(f"cp {self.stage}/server/vmaps/530.vmtree {self.live}/vmaps/530.vmtree", plan)
        self.assertIn(f"{self.live}/maps/5303521.map", plan)
        self.assertNotIn(str(LIVE_BIN), plan)

    def test_live_data_is_never_written(self):
        h = tree_hash(self.live)
        self.run_pipeline()
        self.assertEqual(tree_hash(self.live), h)

    def test_baseline_is_the_live_folder_given(self):
        """A tile identical to the given live folder is not carried; one that differs is."""
        (self.live / "vmaps" / "530_22_35.vmtile").write_bytes(vmtile_bytes(["Rock.m2", "Rock.m2", "Rock.m2"]))
        self.run_pipeline()
        self.assertIn("vmaps/530_22_35.vmtile", self.stamp_files())

    def test_changed_neighbour_is_carried(self):
        self.flag("touch_neighbour")
        report = self.run_pipeline()
        self.assertIn("vmaps/530_22_35.vmtile", self.stamp_files())
        self.assertEqual(M.verify_packed(self.stage), [])

    def test_changed_navmesh_parameters_are_reported(self):
        self.flag("navmesh_changes")
        report = self.run_pipeline()
        self.assertIn("mmaps/530.mmap", report["neighbours_changed"])

    def test_extractor_that_ignores_the_edit_stops_the_run(self):
        self.flag("skip_map")
        with self.assertRaises(M.MapEditError):
            self.run_pipeline()
        self.assertEqual(M.read_stamp(self.stage)["tiles"], {})

    def test_second_run_keeps_the_first_runs_edits(self):
        """The archive the extractors read holds every staged tile, so run 2 does not drop run 1's walls."""
        self.run_pipeline(edits=self.zip_of("one.zip", "21_35"))
        self.run_pipeline(edits=self.zip_of("two.zip", "22_35"))
        listing = subprocess.run(["smpq", "--list", str(self.work / "client/Data/patch-5.MPQ")], capture_output=True, text=True).stdout
        self.assertIn("Expansion01_21_35.adt", listing)
        self.assertIn("Expansion01_22_35.adt", listing)
        stamp = M.read_stamp(self.stage)
        self.assertEqual(sorted(stamp["tiles"]), ["Expansion01_21_35", "Expansion01_22_35"])
        self.assertIn("Wall.m2", M.vmtile_models(self.stage / "server/vmaps/530_21_35.vmtile"))
        self.assertIn("Wall.m2", M.vmtile_models(self.stage / "server/vmaps/530_22_35.vmtile"))
        self.assertEqual(M.verify_packed(self.stage), [])

    def test_a_run_clears_what_the_last_run_left(self):
        self.run_pipeline(edits=self.zip_of("one.zip", "21_35"))
        for stale in ("fresh/maps/STALE.map", "vm/Buildings/STALE.txt", "client/Data/STALE.MPQ"):
            put(self.work, stale, b"old")
        put(self.work, "edits-unpacked/World/Maps/Expansion01/Expansion01_23_35.adt")
        self.run_pipeline(edits=self.zip_of("two.zip", "22_35"))
        self.assertFalse((self.work / "fresh/maps/STALE.map").exists())
        self.assertFalse((self.work / "vm/Buildings/STALE.txt").exists())
        self.assertFalse((self.work / "client/Data/STALE.MPQ").exists())
        self.assertFalse((self.stage / "World/Maps/Expansion01/Expansion01_23_35.adt").exists())
        self.assertEqual(sorted(M.read_stamp(self.stage)["tiles"]), ["Expansion01_21_35", "Expansion01_22_35"])

    def test_server_folder_is_rebuilt_not_added_to(self):
        self.run_pipeline()
        put(self.stage / "server", "maps/9999999.map", b"stale")
        self.run_pipeline()
        self.assertFalse((self.stage / "server/maps/9999999.map").exists())

    def test_dry_run_writes_nothing(self):
        report = self.run_pipeline(dry=True)
        self.assertTrue(report["dry_run"])
        self.assertFalse(self.stage.exists())
        self.assertFalse((self.work / "client").exists())


class TestGuards(Pipeline):
    def test_work_outside_scratch_is_refused(self):
        with self.assertRaises(M.MapEditError):
            M.guard_targets(Path(tempfile.gettempdir()) / "w", self.stage, self.live, self.tools)
        with self.assertRaises(M.MapEditError):
            M.guard_targets(SCRATCH, self.stage, self.live, self.tools)

    def test_targets_inside_live_data_are_refused(self):
        with self.assertRaises(M.MapEditError):
            M.guard_targets(self.live / "scratch", self.stage, self.live, self.tools)
        with self.assertRaises(M.MapEditError):
            M.guard_targets(self.work, self.live / "maps", self.live, self.tools)
        with self.assertRaises(M.MapEditError):
            M.guard_targets(self.work, M.PATCH_DIR, self.live, self.tools)

    def test_the_old_tool_folder_is_never_written_either(self):
        with self.assertRaises(M.MapEditError):
            M.guard_targets(self.work, self.tools / "out", self.live, self.tools)


@unittest.skipUnless(shutil.which("smpq"), "smpq not installed")
class TestGate(Pipeline):
    """verify_packed is what build.sh runs before it packs anything."""

    def mutations(self):
        """Each of these must make the gate fail; every one is undone afterwards."""
        s = self.stage
        adt = s / "World/Maps/Expansion01/Expansion01_21_35.adt"
        stamp_path = s / "stamp.json"
        good_stamp = stamp_path.read_text()

        def undo_stamp():
            stamp_path.write_text(good_stamp)

        cases = {}
        put(s, "World/Maps/Expansion01/Expansion01_23_35.adt")
        cases["ADT with no stamp entry"] = M.verify_packed(s)
        (s / "World/Maps/Expansion01/Expansion01_23_35.adt").unlink()

        keep = adt.read_bytes()
        adt.write_bytes(adt_bytes(b"newer"))
        cases["ADT edited after its data was made"] = M.verify_packed(s)
        adt.write_bytes(keep)

        for rel in ("mmaps/5303521.mmtile", "vmaps/530_21_35.vmtile", "vmaps/530.vmtree", "vmaps/Wall.m2.vmo"):
            f = s / "server" / rel
            data = f.read_bytes()
            f.unlink()
            cases[f"{rel} deleted"] = M.verify_packed(s)
            f.write_bytes(data)
            f.write_bytes(b"stale-copy")
            cases[f"{rel} swapped for another version"] = M.verify_packed(s)
            f.write_bytes(data)

        stamp = json.loads(good_stamp)
        del stamp["vmaps"]["530"]["files"]["vmaps/530.vmtree"]
        stamp_path.write_text(json.dumps(stamp))
        cases["vmtree not stamped"] = M.verify_packed(s)
        undo_stamp()

        stamp = json.loads(good_stamp)
        del stamp["vmaps"]["530"]["files"]["vmaps/Wall.m2.vmo"]
        stamp_path.write_text(json.dumps(stamp))
        cases["new model not stamped"] = M.verify_packed(s)
        undo_stamp()

        stamp = json.loads(good_stamp)
        del stamp["vmaps"]
        stamp_path.write_text(json.dumps(stamp))
        cases["no vmap section"] = M.verify_packed(s)
        undo_stamp()

        put(s / "server", "maps/stray.map", b"x")
        cases["file in server/ the stamp does not know"] = M.verify_packed(s)
        (s / "server/maps/stray.map").unlink()

        stamp_path.rename(s / "stamp.bak")
        cases["no stamp file"] = M.verify_packed(s)
        (s / "stamp.bak").rename(stamp_path)
        return cases

    def test_gate_refuses_every_mutation(self):
        self.run_pipeline()
        self.assertEqual(M.verify_packed(self.stage), [])
        for label, problems in self.mutations().items():
            self.assertTrue(problems, f"gate passed with: {label}")
        self.assertEqual(M.verify_packed(self.stage), [])

    def test_no_stage_no_gate_problem(self):
        self.assertEqual(M.verify_packed(self.tmp / "nothing"), [])
        (self.tmp / "emptyworld/World/Maps").mkdir(parents=True)
        self.assertEqual(M.verify_packed(self.tmp / "emptyworld"), [])

    def test_build_sh_end_to_end_refuses_then_packs(self):
        """A copy of build.sh in a scratch tree: refuses an unstamped tile, packs a stamped one."""
        root = self.tmp / "repo"
        cp = root / "client-patch"
        (cp / "dbc").mkdir(parents=True)
        (root / "VERSION").write_text("client_patch=1\n")
        (cp / "dbc" / "X.dbc").write_bytes(b"WDBC")
        for name in ("build.sh", "stamp_client_patch.sh"):
            shutil.copy(M.PATCH_DIR / name, cp / name)
        shutil.copytree(HERE, cp / "mapedit", ignore=shutil.ignore_patterns("__pycache__"))
        put(cp / "maps", "World/Maps/Expansion01/Expansion01_21_35.adt")
        out = self.tmp / "out.MPQ"
        res = subprocess.run(["bash", str(cp / "build.sh"), "--output", str(out)], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0, res.stdout)
        self.assertIn("no server map data", res.stderr)
        self.assertFalse(out.exists())
        # regenerate through the pipeline, staging straight into the scratch repo
        self.run_pipeline(stage=cp / "maps")
        res = subprocess.run(["bash", str(cp / "build.sh"), "--output", str(out)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        listing = subprocess.run(["smpq", "--list", str(out)], capture_output=True, text=True).stdout
        self.assertIn("Expansion01_21_35.adt", listing)
        self.assertNotIn("5303521.map", listing)  # server data never goes to players
        self.assertNotIn(".vmo", listing)
        # an upper-case .ADT is gated and packed the same way
        a = cp / "maps/World/Maps/Expansion01"
        (a / "Expansion01_21_35.adt").rename(a / "Expansion01_21_35.ADT")
        out.unlink()
        res = subprocess.run(["bash", str(cp / "build.sh"), "--output", str(out)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("21_35.adt", subprocess.run(["smpq", "--list", str(out)], capture_output=True, text=True).stdout.lower())
        # and the same upper-case file, edited after regeneration, is refused
        (a / "Expansion01_21_35.ADT").write_bytes(adt_bytes(b"newer"))
        out.unlink()
        res = subprocess.run(["bash", str(cp / "build.sh"), "--output", str(out)], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)

    def test_build_sh_runs_the_gate_before_packing(self):
        text = (M.PATCH_DIR / "build.sh").read_text()
        gate = text.find("mapedit.py")
        self.assertGreater(gate, 0, "build.sh does not call mapedit.py verify-packed")
        self.assertIn("verify-packed", text)
        self.assertLess(gate, text.find("smpq --create"), "the gate must run before the archive is created")
        line = [ln for ln in text.splitlines() if "verify-packed" in ln][0]
        self.assertTrue("||" in line or "if !" in line or "exit" in line, line)
        self.assertIn("-iname '*.adt'", text)


if __name__ == "__main__":
    unittest.main(verbosity=1)

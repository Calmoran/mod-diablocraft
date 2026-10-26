"""diablocraft-976b: link_map_clone.py links Ulduar's server files under map 750, safely.

    python3 mod-diablocraft/scripts/tests/world/test_link_map_clone.py

Runs only on a throwaway tree of small fake files; the script is never pointed at a real server folder here.
Pinned: the clone and source ids come from Combat's sheet, the five file shapes and their clone names (the
core's loader formats), a dry run that lists and writes nothing, a real run whose relative links read back the
source bytes, a rerun that changes nothing, all-or-nothing refusal when a clone-named path is a real file or a
link elsewhere, refusal of a folder with no source files or a missing folder, and files that only look similar
(another map, other extensions) left alone.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import link_map_clone as link  # noqa: E402
from generate_hub_sanctum import SanctumError  # noqa: E402

SOURCE_FILES = {
    "maps": ["6032832.map", "6032731.map"],
    "vmaps": ["603.vmtree", "603_32_28.vmtile", "603_31_27.vmtile"],
    "mmaps": ["603.mmap", "6032832.mmtile", "6032731.mmtile"],
}
CLONES = {
    "maps": ["7502832.map", "7502731.map"],
    "vmaps": ["750.vmtree", "750_32_28.vmtile", "750_31_27.vmtile"],
    "mmaps": ["750.mmap", "7502832.mmtile", "7502731.mmtile"],
}
LOOKALIKES = {"maps": ["6042832.map", "603283.map", "6032832.map.bak", "603.txt"],
              "vmaps": ["604.vmtree", "603_32_28.vmo", "6.vmtree", "603_32_2.vmtile"],
              "mmaps": ["604.mmap", "6032832.mmtile.old", "603283.mmtile"]}


def tree():
    root = Path(tempfile.mkdtemp(prefix="link_clone_"))
    for folder, names in SOURCE_FILES.items():
        (root / folder).mkdir()
        for name in names + LOOKALIKES[folder]:
            (root / folder / name).write_bytes(f"{folder}/{name}".encode())
    return root


def run(root, **kwargs):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = link.run(root, out=print, **kwargs)
    return code, buffer.getvalue()


def listing(root):
    return sorted((str(p.relative_to(root)), os.path.islink(p)) for p in Path(root).rglob("*"))


class KalimdorAsMap751(unittest.TestCase):
    """diablocraft-kw18: map 1's files are named with a three-digit id (001XXYY.map), the clone 751."""
    FILES = {"maps": ["0014332.map", "0014735.map"], "vmaps": ["001.vmtree", "001_32_43.vmtile"],
             "mmaps": ["001.mmap", "0014332.mmtile"]}
    ALIKE = {"maps": ["0024332.map", "014332.map"], "vmaps": ["002.vmtree", "01.vmtree"], "mmaps": ["010.mmap"]}

    def make(self):
        root = Path(tempfile.mkdtemp(prefix="link_kalimdor_"))
        for folder, names in self.FILES.items():
            (root / folder).mkdir()
            for name in names + self.ALIKE[folder]:
                (root / folder / name).write_bytes(f"{folder}/{name}".encode())
        return root

    def test_the_sheet_names_751_as_a_clone_of_1(self):
        self.assertEqual(link.clone_ids(HERE.parent / "data/d3/world_open_rift_dbc.csv"), (751, 1))

    def test_the_names_are_three_digits_wide_and_the_rest_is_kept(self):
        steps = link.plan(self.make(), 751, 1)
        self.assertEqual(sorted((f, s, t) for f, s, t in steps), [
            ("maps", "0014332.map", "7514332.map"), ("maps", "0014735.map", "7514735.map"),
            ("mmaps", "001.mmap", "751.mmap"), ("mmaps", "0014332.mmtile", "7514332.mmtile"),
            ("vmaps", "001.vmtree", "751.vmtree"), ("vmaps", "001_32_43.vmtile", "751_32_43.vmtile")])

    def test_the_run_reads_back_the_source_and_leaves_look_alikes(self):
        root = self.make()
        code, _ = run(root, source_csv=HERE.parent / "data/d3/world_open_rift_dbc.csv")
        self.assertEqual(code, 0)
        self.assertEqual((root / "maps" / "7514332.map").read_bytes(), b"maps/0014332.map")
        self.assertEqual(len([p for p in Path(root).rglob("*") if os.path.islink(p)]), 6)

    def test_the_command_line_takes_the_sheet(self):
        source = Path(link.__file__).read_text(encoding="utf-8")
        self.assertIn("source_csv=args.sheet", source)


class LinkMapClone(unittest.TestCase):
    def test_ids_come_from_the_sheet(self):
        self.assertEqual(link.clone_ids(), (750, 603))

    def test_plan_has_every_shape_and_nothing_else(self):
        steps = link.plan(tree(), 750, 603)
        self.assertEqual(sorted((f, t) for f, _, t in steps),
                         sorted((f, n) for f, names in CLONES.items() for n in names))
        self.assertEqual({(f, s): t for f, s, t in steps}[("maps", "6032832.map")], "7502832.map")

    def test_dry_run_lists_and_writes_nothing(self):
        root = tree()
        before = listing(root)
        code, output = run(root, dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(listing(root), before)
        for names in CLONES.values():
            for name in names:
                self.assertIn(name, output)
        self.assertIn("dry run", output)
        self.assertNotIn("\nlink ", "\n" + output)

    def test_run_links_every_file_to_the_source_bytes(self):
        root = tree()
        code, _ = run(root)
        self.assertEqual(code, 0)
        for folder, names in CLONES.items():
            for name, source in zip(names, SOURCE_FILES[folder]):
                path = root / folder / name
                self.assertTrue(os.path.islink(path), name)
                self.assertFalse(os.path.isabs(os.readlink(path)), "links are relative so the folder can move")
                self.assertEqual(path.read_bytes(), (root / folder / source).read_bytes())

    def test_look_alikes_are_left_alone(self):
        root = tree()
        before = {p.name: p.read_bytes() for f in LOOKALIKES for p in (root / f).iterdir()}
        run(root)
        for folder, names in LOOKALIKES.items():
            for name in names:
                self.assertFalse(os.path.islink(root / folder / name), name)
                self.assertEqual((root / folder / name).read_bytes(), before[name])
        self.assertEqual(len([p for p in Path(root).rglob("*") if os.path.islink(p)]),
                         sum(map(len, CLONES.values())), "no other clone name was made")

    def test_rerun_changes_nothing(self):
        root = tree()
        run(root)
        before = listing(root)
        code, output = run(root)
        self.assertEqual(code, 0)
        self.assertEqual(listing(root), before)
        self.assertIn(", 0 linked, 8 already linked", output)
        self.assertNotIn("\nlink ", "\n" + output)

    def test_a_real_file_is_refused_and_nothing_is_made(self):
        root = tree()
        (root / "vmaps" / "750_32_28.vmtile").write_bytes(b"a real tile")
        before = listing(root)
        code, output = run(root)
        self.assertEqual(code, 1)
        self.assertEqual(listing(root), before, "all or nothing")
        self.assertEqual((root / "vmaps" / "750_32_28.vmtile").read_bytes(), b"a real tile")
        self.assertIn("refuse vmaps/750_32_28.vmtile", output)

    def test_a_link_elsewhere_is_refused(self):
        root = tree()
        os.symlink("604.mmap", root / "mmaps" / "750.mmap")
        before = listing(root)
        code, output = run(root)
        self.assertEqual(code, 1)
        self.assertEqual(listing(root), before)
        self.assertIn("604.mmap", output)

    def test_a_link_that_already_points_at_the_source_is_kept(self):
        root = tree()
        os.symlink("603.mmap", root / "mmaps" / "750.mmap")
        code, _ = run(root)
        self.assertEqual(code, 0)
        self.assertEqual(os.readlink(root / "mmaps" / "750.mmap"), "603.mmap")

    def test_a_folder_without_the_source_files_is_refused(self):
        root = tree()
        for folder, names in SOURCE_FILES.items():
            for name in names:
                (root / folder / name).unlink()
        with self.assertRaises(SanctumError):
            link.plan(root, 750, 603)

    def test_a_missing_folder_is_refused(self):
        root = tree()
        for path in (root / "mmaps").iterdir():
            path.unlink()
        (root / "mmaps").rmdir()
        with self.assertRaises(SanctumError) as raised:
            link.plan(root, 750, 603)
        self.assertIn("mmaps", str(raised.exception))

    def test_a_source_file_missing_from_one_folder_is_refused(self):
        # The clone needs all three kinds of file; a tree that lacks one would load the map half-made.
        for folder, only in (("maps", "maps"), ("vmaps", "vmaps"), ("mmaps", "mmaps")):
            root = tree()
            for name in SOURCE_FILES[folder]:
                (root / folder / name).unlink()
            with self.assertRaises(SanctumError) as raised:
                link.plan(root, 750, 603)
            self.assertIn(only, str(raised.exception))

    def test_a_sheet_without_exactly_one_map_row_is_refused(self):
        # Which map to clone is the sheet's one Map row; none, or two, would leave the choice to the file order.
        header = "table,id,source_id,field,value,note\n"
        rows = {"no Map row": "AreaTable,4273,4273,AreaName_Lang_enUS,Sanctum of Torment,x\n",
                "two Map rows": "Map,750,603,InstanceType,0,x\nMap,751,603,InstanceType,0,x\n"}
        for label, text in rows.items():
            with self.subTest(label), tempfile.TemporaryDirectory(prefix="link_sheet_") as folder:
                sheet = Path(folder) / "world_sanctum_dbc.csv"
                sheet.write_text(header + text, encoding="utf-8")
                with self.assertRaises(SanctumError) as raised:
                    link.clone_ids(sheet)
                self.assertIn("exactly one Map row", str(raised.exception))

    def test_the_tree_and_navmesh_header_files_are_required(self):
        # Tiles alone are not enough: no .vmtree means no collision for the map, no .mmap no navmesh.
        for folder, header in (("vmaps", "603.vmtree"), ("mmaps", "603.mmap")):
            root = tree()
            (root / folder / header).unlink()
            with self.assertRaises(SanctumError) as raised:
                link.plan(root, 750, 603)
            self.assertIn(f"{folder}/{header}", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

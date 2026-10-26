#!/usr/bin/env python3
"""Tests for build.sh: python3 client-patch/test_build.py

A copy of build.sh in a temporary tree (honours TMPDIR) packs a fake art folder;
the archive listing must hold the art and none of the files the client never
reads (diablocraft-3e4v), packed as MPQ version 2 (diablocraft-t4f3). Needs smpq.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

SHIPPED = ["ui/rift/rift.blp", "ui/hud/hud.m2", "ui/elvui/frame.skin"]
SKIPPED = ["ui/elvui/mock_hud_art.py", "ui/hud/README.md", "ui/tooltip/manifest.json",
           "ui/bug/manifest.json", "ui/x-manifest.json", ".gitkeep", "ui/source/raw.png",
           "__pycache__/x.pyc", "ui/elvui/__pycache__/mock_hud_art.cpython-312.pyc", "ui/hud/y.pyc"]


class BuildShTest(unittest.TestCase):
    def test_packs_only_what_the_client_reads(self):
        with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
            root = Path(tmp)
            cp = root / "client-patch"
            (cp / "dbc").mkdir(parents=True)
            (root / "VERSION").write_text("client_patch=1\n")
            (cp / "dbc" / "X.dbc").write_bytes(b"WDBC")
            for name in ("build.sh", "stamp_client_patch.sh"):
                shutil.copy(HERE / name, cp / name)
            for rel in SHIPPED + SKIPPED:
                p = cp / "art" / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x")
            out = root / "out.MPQ"
            res = subprocess.run(["bash", str(cp / "build.sh"), "--output", str(out)],
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            listing = subprocess.run(["smpq", "--list", str(out)], capture_output=True,
                                     text=True).stdout.replace("\\", "/")
            for rel in SHIPPED + ["DBFilesClient/X.dbc"]:
                self.assertIn(rel, listing)
            for rel in SKIPPED:
                self.assertNotIn(rel, listing)
            # MPQ version 2 is header format 1; world editors refuse anything newer
            # (diablocraft-t4f3).
            head = out.read_bytes()[:16]
            self.assertEqual(head[:4], b"MPQ\x1a")
            self.assertEqual(struct.unpack("<H", head[12:14])[0], 1)

    def test_a_long_listing_never_loses_a_file(self):
        """diablocraft-9jft9: the check read the listing through printf | grep -Fqx under pipefail; grep -q left at the first match, printf
        took SIGPIPE, and a file that was in the archive was reported missing at random. A stand-in smpq lists the packed files first, then
        a long tail, so the old pipe broke nearly every time; 50 builds in a row must pass."""
        with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
            root = Path(tmp)
            cp = root / "client-patch"
            (cp / "dbc").mkdir(parents=True)
            (root / "VERSION").write_text("client_patch=1\n")
            (cp / "dbc" / "X.dbc").write_bytes(b"WDBC")
            for name in ("build.sh", "stamp_client_patch.sh"):
                shutil.copy(HERE / name, cp / name)
            (cp / "art" / "ui").mkdir(parents=True)
            (cp / "art" / "ui" / "a.blp").write_bytes(b"x")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake = bin_dir / "smpq"
            fake.write_text("""#!/usr/bin/env bash
# --create ... <output> <files>: a header-only archive; --list <archive>: the files it was given, then a long tail.
if [ "$1" = --create ]; then
    shift 5; out="$1"; shift; printf '%s\\n' "$@" > "$out.names"; printf 'MPQ\\032' > "$out"
elif [ "$1" = --list ]; then
    while IFS= read -r f; do printf '1 2026-10-12 00:00 %s\\n' "$f"; done < "$2.names"
    for i in $(seq 1 6000); do printf '1 2026-10-12 00:00 Interface/filler/padding_file_%05d.blp\\n' "$i"; done
fi
""")
            fake.chmod(0o755)
            env = dict(os.environ, PATH="%s:%s" % (bin_dir, os.environ["PATH"]))
            out = root / "out.MPQ"
            for run in range(50):
                res = subprocess.run(["bash", str(cp / "build.sh"), "--output", str(out)], capture_output=True, text=True, env=env)
                self.assertEqual(res.returncode, 0, "run %d: %s" % (run, res.stderr))
                self.assertNotIn("missing from the built archive", res.stderr)


REPO = HERE.parent


class SignedInterfaceTests(unittest.TestCase):
    """build.sh packs Interface/GlueXML and Interface/FrameXML only with a rebuilt-client build whose pin in
    launcher/engine/src/allow.rs PINNED carries the glue-unlock flag: the one rule manifest.py check_mpq holds the
    release to. Everything runs in a scratch tree; the exe is scratch bytes pinned in a scratch allow.rs written
    in the real one's PINNED shape, never anything the release could ship."""

    DLL = b"MZ scratch build"

    def tree(self, tmp, glue, flag, dll=DLL):
        """A scratch repo with one art file under Interface/<glue>, an allow.rs whose WowClient64.exe row pins `dll`
        with `flag`, and the unpacked client-rebuild folder holding that exe. Returns (client-patch, ext, out)."""
        root = Path(tmp)
        cp = root / "client-patch"
        (cp / "dbc").mkdir(parents=True)
        (root / "VERSION").write_text("client_patch=1\n")
        (cp / "dbc" / "X.dbc").write_bytes(b"WDBC")
        for name in ("build.sh", "stamp_client_patch.sh", "manifest.py", "glue_unlock_run"):
            shutil.copy(HERE / name, cp / name)
        art = cp / "art" / "Interface" / glue / "CharacterCreate.lua"
        art.parent.mkdir(parents=True)
        art.write_text("x")
        allow = root / "launcher/engine/src/allow.rs"
        allow.parent.mkdir(parents=True)
        src = (REPO / "launcher/engine/src/allow.rs").read_text()
        self.assertRegex(src, r'const PINNED: \[\(&str, &str, bool\); \d+\] = \[\n\s*\("WowClient64\.exe", ',
                         "the real allow.rs keeps its PINNED rows, the exe's among them")
        rows = [("WowClient64.exe", hashlib.sha256(self.DLL).hexdigest(), "true" if flag else "false")]
        rows += [(n, hashlib.sha256(n.encode()).hexdigest(), "false") for n in ("XvidDecoder.dll", "msvcp140.dll")]
        allow.write_text("const PINNED: [(&str, &str, bool); %d] = [\n%s];\n"
                         % (len(rows), "".join('    ("%s", "%s", %s),\n' % r for r in rows)))
        ext = root / "ext"
        ext.mkdir()
        (ext / "WowClient64.exe").write_bytes(dll)
        return cp, ext, root / "out.MPQ"

    def run_id(self):
        return (HERE / "glue_unlock_run").read_text().strip()

    def fake_gh(self, tmp, ext=None):
        """A `gh` on PATH that records its arguments and, when `ext` is given, 'downloads' that folder; else it fails like a gh that is not logged in."""
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir(exist_ok=True)
        gh = bin_dir / "gh"
        copy = ('cp -r "%s"/. "$out"/' % ext) if ext else "echo 'gh: not logged in' >&2; exit 4"
        gh.write_text('#!/usr/bin/env bash\necho "$@" >> "%s/gh.log"\nwhile [ $# -gt 0 ]; do [ "$1" = -D ] && out="$2"; shift; done\n%s\n' % (tmp, copy))
        gh.chmod(0o755)
        return bin_dir

    def build(self, cp, out, *extra, path=None):
        """Runs build.sh in the scratch tree; the shared artefact folder is the tree's own (DC_CLIENT_EXT_ROOT), never the real scratch folder."""
        env = dict(os.environ, DC_CLIENT_EXT_ROOT=str(Path(cp).parent / "shared"))
        env["PATH"] = (str(path) + os.pathsep if path else "") + env["PATH"]
        return subprocess.run(["bash", str(cp / "build.sh"), "--output", str(out), *extra],
                              capture_output=True, text=True, timeout=60, env=env)

    def listing(self, out):
        return subprocess.run(["smpq", "--list", str(out)], capture_output=True, text=True).stdout.replace("\\", "/")

    def refused(self, res, out):
        self.assertNotEqual(res.returncode, 0, res.stdout)
        self.assertIn("refusing to pack a signed interface file", res.stderr)
        self.assertIn("glue-unlock", res.stderr)
        self.assertFalse(out.exists())

    def test_no_extension_and_no_artefact_refuses_loudly(self):
        """No --client-rebuild, nothing at the shared path and a gh that fails: the build stops, says why, and builds nothing."""
        for glue in ("GlueXML", "FrameXML"):
            with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
                cp, _, out = self.tree(tmp, glue, flag=True)
                res = self.build(cp, out, path=self.fake_gh(tmp))
                self.refused(res, out)
                self.assertIn("gh run download", res.stderr)
                self.assertIn(self.run_id(), res.stderr)
                self.assertIn("not logged in", res.stderr)
                self.assertEqual("run download %s -n client-rebuild -D" % self.run_id(),
                                 (Path(tmp) / "gh.log").read_text().split(" /")[0].strip())

    def test_the_default_is_fetched_once_to_the_shared_path_and_lets_the_build_through(self):
        for glue in ("GlueXML", "FrameXML"):
            with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
                cp, ext, out = self.tree(tmp, glue, flag=True)
                res = self.build(cp, out, path=self.fake_gh(tmp, ext))
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertIn("Interface/%s/CharacterCreate.lua" % glue, self.listing(out))
                shared = Path(tmp) / "shared" / ("client-rebuild-run" + self.run_id())
                self.assertEqual(self.DLL, (shared / "WowClient64.exe").read_bytes())
                self.assertEqual([p.name for p in shared.parent.iterdir()], [shared.name])      # no half-fetched folder left behind
                out.unlink()
                again = self.build(cp, out, path=self.fake_gh(tmp))                              # a gh that would fail is not asked again
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertEqual(1, len((Path(tmp) / "gh.log").read_text().strip().splitlines()))

    def test_a_default_run_without_the_flag_still_refuses(self):
        with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
            cp, ext, out = self.tree(tmp, "GlueXML", flag=False)
            self.refused(self.build(cp, out, path=self.fake_gh(tmp, ext)), out)

    def test_an_explicit_artefact_wins_and_gh_is_never_asked(self):
        with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
            cp, ext, out = self.tree(tmp, "GlueXML", flag=True)
            res = self.build(cp, out, "--client-rebuild", str(ext), path=self.fake_gh(tmp))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertFalse((Path(tmp) / "gh.log").exists())
            self.assertFalse((Path(tmp) / "shared").exists())

    def test_a_build_without_signed_files_never_fetches(self):
        with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
            cp, _, out = self.tree(tmp, "GlueXML", flag=True)
            shutil.rmtree(cp / "art" / "Interface")
            (cp / "art" / "Interface" / "AddOns").mkdir(parents=True)
            (cp / "art" / "Interface" / "AddOns" / "x.lua").write_text("x")
            res = self.build(cp, out, path=self.fake_gh(tmp))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertFalse((Path(tmp) / "gh.log").exists())

    @staticmethod
    def pinned_exe_runs():
        """The client-rebuild run ids allow.rs's PINNED doc names for its WowClient64.exe pin."""
        text = (REPO / "launcher/engine/src/allow.rs").read_text()
        doc = text[:text.index("const PINNED:")]
        doc = doc[doc.rindex("const FILE_TARGETS"):]
        return re.findall(r"WowClient64\.exe\b[^`]{0,120}?client-rebuild run (\d+)", doc)

    def test_the_default_run_is_the_one_the_exe_pin_names(self):
        """glue_unlock_run names the client-rebuild run allow.rs gives as the source of its WowClient64.exe pin, the
        flagged build: moving the pin without the file fails here, so the default never drifts to a run the launcher
        does not pin. The real artefact is not downloaded; where the shared folder already holds that run's copy, it
        is asked of manifest.ships_glue_unlock (the pin's own rows)."""
        run = (HERE / "glue_unlock_run").read_text().strip()
        self.assertRegex(run, r"^\d{6,}$")
        self.assertEqual([run], self.pinned_exe_runs())
        import sys
        sys.path.insert(0, str(HERE))
        import manifest
        copy = REPO / "azerothcore-wotlk/build/_agent-scratch" / ("client-rebuild-run" + run)
        pinned = (REPO / "launcher/engine/src/allow.rs").read_text()
        if copy.is_dir() and "PIN_PENDING" not in pinned:
            self.assertTrue(manifest.ships_glue_unlock(copy, REPO))

    def test_a_run_file_pointed_at_another_run_goes_red(self):
        """The guard's own mutant: a run id allow.rs does not name for the exe pin is not the default."""
        run = (HERE / "glue_unlock_run").read_text().strip()
        self.assertNotEqual([str(int(run) + 1)], self.pinned_exe_runs())

    def test_a_missing_run_file_stops_the_build(self):
        with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
            cp, ext, out = self.tree(tmp, "GlueXML", flag=True)
            (cp / "glue_unlock_run").unlink()
            res = self.build(cp, out, path=self.fake_gh(tmp, ext))
            self.refused(res, out)
            self.assertIn("glue_unlock_run is missing or empty", res.stderr)
            self.assertFalse((Path(tmp) / "gh.log").exists())

    def test_an_unflagged_exe_refuses(self):
        for glue in ("GlueXML", "FrameXML"):
            with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
                cp, ext, out = self.tree(tmp, glue, flag=False)
                self.refused(self.build(cp, out, "--client-rebuild", str(ext)), out)

    def test_an_exe_that_is_not_the_flagged_pin_refuses(self):
        with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
            cp, ext, out = self.tree(tmp, "GlueXML", flag=True)
            (ext / "WowClient64.exe").write_bytes(b"MZ another build")
            self.refused(self.build(cp, out, "--client-rebuild", str(ext)), out)

    def test_a_flagged_exe_lets_both_folders_through(self):
        for glue in ("GlueXML", "FrameXML"):
            with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
                cp, ext, out = self.tree(tmp, glue, flag=True)
                res = self.build(cp, out, "--client-rebuild", str(ext))
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertIn("Interface/%s/CharacterCreate.lua" % glue, self.listing(out))

    def test_the_release_check_agrees_on_the_built_archive(self):
        """Cross-source: manifest.py check_mpq, the release's half of the rule, reads the same archive the same way."""
        import sys
        sys.path.insert(0, str(HERE))
        import manifest
        with tempfile.TemporaryDirectory(prefix="build_sh_test_") as tmp:
            cp, ext, out = self.tree(tmp, "GlueXML", flag=True)
            self.assertEqual(self.build(cp, out, "--client-rebuild", str(ext)).returncode, 0)
            self.assertEqual(len(manifest.check_mpq(out, glue_unlock=True)), 1)
            with self.assertRaises(manifest.ReleaseError):
                manifest.check_mpq(out, glue_unlock=False)
            self.assertTrue(manifest.ships_glue_unlock(ext, cp.parent))


if __name__ == "__main__":
    unittest.main()

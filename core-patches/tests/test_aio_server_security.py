"""0020: the AIO server security patch and the wrapper that installs it.

Runs mod-diablocraft/scripts/build_live_aio.sh, then drives the BUILT
AIO_Server/AIO.lua with aio_server_security_harness.lua: the .aio switches are
GM 3 only (G2) and incoming AIO block work is capped and budgeted (G1). The same
harness must fail on the unpAtched pin, so a green build run proves the patch is
what makes it pass. Also proves the wrapper refuses a bad patch and that
--compare fails on a changed line in a live folder.

    python core-patches/tests/test_aio_server_security.py
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "mod-diablocraft" / "scripts" / "build_live_aio.sh"
HARNESS = Path(__file__).resolve().parent / "aio_server_security_harness.lua"
PATCH = ROOT / "core-patches" / "0020-aio-server-security.patch"
LUA = shutil.which("lua")

AIO_CHECKOUT = Path(os.environ.get("AIO_CHECKOUT", Path.home() / "torment-aio"))
# Scratch belongs in the build tree (AGENTS.md), not the system temp.
SCRATCH = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "aio-security"


def pinned_commit() -> str:
    for line in (ROOT / "modules-commit.txt").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields and fields[0] == "AIO":
            return fields[1]
    raise AssertionError("modules-commit.txt has no AIO pin")


def run(command, env=None):
    return subprocess.run(command, cwd=str(ROOT), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


@unittest.skipUnless(LUA, "lua 5.2 interpreter is required")
@unittest.skipUnless((AIO_CHECKOUT / ".git").is_dir(), f"no AIO checkout at {AIO_CHECKOUT}")
class AioServerSecurity(unittest.TestCase):
    def export_pin(self, target: Path):
        target.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(
            ["git", "-C", str(AIO_CHECKOUT), "archive", pinned_commit(), "AIO_Server"],
            stdout=subprocess.PIPE, check=True)
        subprocess.run(["tar", "-x", "-C", str(target)], input=archive.stdout, check=True)
        return target / "AIO_Server"

    def build(self, target: Path, env=None):
        return run(["bash", str(SCRIPT), str(target)], env=env)

    def harness(self, built: Path):
        return run([LUA, str(HARNESS), str(built)])

    def test_build_applies_patch_and_passes_harness(self):
        with tempfile.TemporaryDirectory() as tmp:
            built = Path(tmp) / "patched"
            result = self.build(built)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("applied 0020-aio-server-security.patch", result.stdout)
            self.assertTrue((built / "AIO.lua").is_file())
            harness = self.harness(built)
            self.assertEqual(harness.returncode, 0, harness.stdout)
            self.assertIn("PASS", harness.stdout)

    def test_unpatched_pin_fails_harness(self):
        """The control: reverting the patch changes the built output and fails."""
        with tempfile.TemporaryDirectory() as tmp:
            unpAtched = self.export_pin(Path(tmp))
            result = self.harness(unpAtched)
            self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_compare_matches_pin_and_fails_on_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = self.export_pin(Path(tmp))
            same = run(["bash", str(SCRIPT), "--compare", str(live)])
            self.assertEqual(same.returncode, 0, same.stdout)
            with (live / "AIO.lua").open("a", encoding="utf-8") as handle:
                handle.write("\n-- tampered line\n")
            changed = run(["bash", str(SCRIPT), "--compare", str(live)])
            self.assertNotEqual(changed.returncode, 0, changed.stdout)
            self.assertIn("tampered", changed.stdout)

    def test_bad_patch_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "patches"
            bad.mkdir()
            (bad / "0001-aio-broken.patch").write_text("not a patch\n", encoding="utf-8")
            env = dict(os.environ, AIO_PATCH_DIR=str(bad))
            result = self.build(Path(tmp) / "out", env=env)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("does not apply", result.stdout)

    def test_patch_targets_the_aio_checkout_not_the_core(self):
        text = PATCH.read_text(encoding="utf-8")
        self.assertIn("087e279", text)
        self.assertIn("AIO_Server/AIO.lua", text)
        self.assertIn("NOT to the core tree", text)
        self.assertIn("+            if not player or not player.GetGMRank", text)
        self.assertIn("+local AIO_MAX_BLOCKS_PER_MSG", text)
        # Every drop clears the parse hook before it returns.
        self.assertIn("+        dropAndClear()", text)

    def make_live(self, tmp: Path) -> Path:
        """The pre-deploy live lua_scripts/AIO: both halves of the pin present."""
        pin = self.export_pin(tmp / "pin")
        live = tmp / "AIO"
        shutil.copytree(pin, live / "AIO_Server")
        shutil.copytree(pin, live / "AIO_Client")
        return live

    def test_install_makes_the_patched_server_the_engine_ale_loads(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="install-", dir=SCRATCH) as tmp:
            live = self.make_live(Path(tmp))
            backup = Path(tmp) / "pre-deploy-AIO"
            env = dict(os.environ, AIO_BACKUP=str(backup))
            result = run(["bash", str(SCRIPT), "--install", str(live)], env=env)
            self.assertEqual(result.returncode, 0, result.stdout)

            # The stray client half is gone, so only the patched server AIO.lua
            # remains for ALE's by-name loader.
            self.assertFalse((live / "AIO_Client").exists())
            aio_luas = sorted(p.relative_to(live).as_posix() for p in live.rglob("AIO.lua"))
            self.assertEqual(aio_luas, ["AIO_Server/AIO.lua"])
            self.assertIn("AIO_MAX_BLOCKS_PER_MSG", (live / "AIO_Server" / "AIO.lua").read_text(encoding="utf-8"))

            # The backup holds the pre-deploy folder and the restore command.
            self.assertTrue((backup / "AIO_Client" / "AIO.lua").is_file())
            self.assertIn("rollback: rm -rf", result.stdout)
            self.assertIn(str(backup), result.stdout)

            # And the engine ALE would now load passes the security harness.
            harness = self.harness(live / "AIO_Server")
            self.assertEqual(harness.returncode, 0, harness.stdout)
            self.assertIn("PASS", harness.stdout)

    def test_install_refuses_a_folder_that_is_not_the_live_aio(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="install-bad-", dir=SCRATCH) as tmp:
            result = run(["bash", str(SCRIPT), "--install", str(Path(tmp))])
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("not the live lua_scripts/AIO", result.stdout)

    def test_install_refuses_an_existing_backup(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="install-backup-", dir=SCRATCH) as tmp:
            live = self.make_live(Path(tmp))
            backup = Path(tmp) / "already-here"
            backup.write_text("do not overwrite\n", encoding="utf-8")
            env = dict(os.environ, AIO_BACKUP=str(backup))
            result = run(["bash", str(SCRIPT), "--install", str(live)], env=env)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("backup path already exists", result.stdout)
            self.assertTrue((live / "AIO_Client" / "AIO.lua").is_file())


if __name__ == "__main__":
    unittest.main()

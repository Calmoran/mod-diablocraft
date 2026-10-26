"""The tier login and phase policy, driven (diablocraft-deeh, diablocraft-ytfx): hub and party login for tiers 1-10 against the
production helpers out of dc_difficulty.cpp and the installed core's own phase comparison and Unit early return.

The harness is src/difficulty/tests/phase_login_tests.cpp.in and its CMakeLists.txt, which cut ApplyPhase, PlayerPhase and the
login's tier choice out of dc_difficulty.cpp, the Sanctum phase out of dc_world.h and the core's InSamePhase and Unit early
return out of the pinned sources, and stop with "re-audit" when a piece is gone. It used to be built only by hand (run.sh). This runs
the same CMake configure on the real tree, compiles the generated program through harness_env and runs it. Then each piece is
broken in a copy of the tree, and the harness must go red (or, for a piece that is gone, the configure must refuse).

    python3 mod-diablocraft/scripts/tests/difficulty/test_phase_login.py
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch"
CMAKE = shutil.which("cmake")

# Where each piece lives, relative to the repo root (the CMakeLists reads them from there).
DIFFICULTY = "mod-diablocraft/src/difficulty/dc_difficulty.cpp"
WORLD = "mod-diablocraft/src/common/dc_world.h"
UNIT = "azerothcore-wotlk/src/server/game/Entities/Unit/Unit.cpp"
OBJECT = "azerothcore-wotlk/src/server/game/Entities/Object/Object.h"
TEMPLATE_DIR = "mod-diablocraft/src/difficulty/tests"
FLAGS = ["-std=c++17", "-O1"]

# (what the mutant breaks, the file, the text in it, what it becomes); only the first occurrence is changed, the one the CMake regex takes
MUTANTS = [
    ("a same-phase apply goes the Unit way and skips the literal-phase hook", DIFFICULTY, "if (object->GetPhaseMask() == phase)", "if (false)"),
    ("the hub is not the Sanctum's phase", DIFFICULTY, "DC::World::IsInHub(player) ?", "false ?"),
    ("every tier is in tier 1's phase", DIFFICULTY, "tiers[CurrentTier(player)].phase", "tiers[0].phase"),
    ("a party login keeps its own saved tier", DIFFICULTY, "LeaderTier(player->GetGroup())", "SavedTier(player->GetGUID())"),
    ("a login forgets its saved tier", DIFFICULTY, ": SavedTier(player->GetGUID());", ": 1u;"),
    ("the core compares phases as one mask", OBJECT,
     "return m_useCombinedPhases ? GetPhaseMask() & phasemask : GetPhaseMask() == phasemask;", "return GetPhaseMask() == phasemask;"),
]
# a piece the CMake regex can no longer find: the configure must refuse
GONE = [
    ("PlayerPhase is renamed", DIFFICULTY, "uint32 PlayerPhase(Player const* player)", "uint32 PlayerPhases(Player const* player)"),
    ("ApplyPhase changes its signature", DIFFICULTY, "void ApplyPhase(WorldObject* object, uint32 phase, bool update)",
     "void ApplyPhase(WorldObject* object, uint32 phase)"),
    ("Unit stops skipping an unchanged phase", UNIT, "if (newPhaseMask == GetPhaseMask())\n        return;", ""),
    ("the Sanctum phase is no constexpr", WORLD, "constexpr unsigned SanctumPhase", "inline unsigned SanctumPhase"),
]


def tree_with(folder, changes):
    """A repo-shaped folder holding the five source files and the harness, with `changes` ({path: (old, new)}) applied once each."""
    for path in (DIFFICULTY, WORLD, UNIT, OBJECT):
        text = (ROOT / path).read_text(encoding="utf-8")
        if path in changes:
            old, new = changes[path]
            assert old in text, "the mutant's target moved: " + old
            text = text.replace(old, new, 1)
        target = Path(folder) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    shutil.copytree(ROOT / TEMPLATE_DIR, Path(folder) / TEMPLATE_DIR)


def configure(root, build):
    """The CMake configure of the harness under `root`: (it succeeded, its output). It writes the program into `build`."""
    done = subprocess.run([CMAKE, "--fresh", "-S", str(Path(root) / TEMPLATE_DIR), "-B", str(build), "-G", "Unix Makefiles",
                           "-DCMAKE_BUILD_TYPE=Release"], capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def passes(program):
    """Compile the generated program and run it: (it passed, its output)."""
    ran = harness_env.run([str(harness_env.build([program], flags=FLAGS))], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout + ran.stderr


@unittest.skipUnless(CMAKE, "no cmake")
class PhaseLogin(unittest.TestCase):
    def test_production_passes_every_login_and_phase_case(self):
        build = SCRATCH / "phase-login-tests" / "production"   # a fixed folder, so the generated program is one cached source
        build.mkdir(parents=True, exist_ok=True)
        ok, out = configure(ROOT, build)
        self.assertTrue(ok, out)
        ok, out = passes(build / "phase_login_tests.cpp")
        self.assertTrue(ok, out)
        self.assertIn("PASS: Sanctum shared phase for all tiers", out)

    def test_every_piece_fails_when_broken(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        for what, path, old, new in MUTANTS:
            with self.subTest(what), tempfile.TemporaryDirectory(prefix="phase-login-", dir=SCRATCH) as folder:
                tree_with(folder, {path: (old, new)})
                ok, out = configure(folder, Path(folder) / "build")
                self.assertTrue(ok, "the mutant should still configure: " + out)
                try:
                    ok, out = passes(Path(folder) / "build" / "phase_login_tests.cpp")
                except harness_env.BuildError:
                    continue  # a mutant that no longer compiles is red as well
                self.assertFalse(ok, "mutant survived: " + what)

    def test_a_piece_that_is_gone_stops_the_configure(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        for what, path, old, new in GONE:
            with self.subTest(what), tempfile.TemporaryDirectory(prefix="phase-login-", dir=SCRATCH) as folder:
                tree_with(folder, {path: (old, new)})
                ok, out = configure(folder, Path(folder) / "build")
                self.assertFalse(ok, "the configure did not refuse: " + what)
                self.assertIn("re-audit", out)


if __name__ == "__main__":
    unittest.main()

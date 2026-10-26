"""diablocraft-n9s4n: stat contributions of Source::Temporary (a buff's) are not kept across a logout.

Stats::Save writes every contribution; Stats::Load used to drop only Paragon's (rebuilt by its login hook), so a
buff up at the logout (a mantra, Tempest Rush's Tailwind, Blazing Fists, a pylon, Barbarian and Wizard buffs) came
back as a contribution nothing would ever remove. Load now hands the saved list to DropRebuiltSources
(dc_common.cpp), which drops Paragon and Temporary and keeps every other source.

  * tests/stats_temporary/harness.cpp compiles the real dc_common.cpp and runs the save/load round trip: Serialize,
    DeserializeContributions, DropRebuiltSources; the buffs are gone, every other source is kept as saved;
  * a source guard: Load calls DropRebuiltSources on what it read before it calculates the sheet;
  * planted differences in dc_common.cpp (Temporary kept, Paragon kept, another source dropped) fail the harness.

The live check (log out with a buff up, log back in, the stat is gone) is docs/test-diablocraft-n9s4n.md.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

MODULE = Path(__file__).resolve().parents[3]
COMMON = MODULE / "src/common"
HARNESS = MODULE / "tests/stats_temporary/harness.cpp"
STATS = MODULE / "src/stats/dc_stats.cpp"
DROP = "[](Contribution const& c)\n                                       { return c.source == Source::Paragon || c.source == Source::Temporary; }"


def run(common_cpp):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp)
        (tree / "src/common").mkdir(parents=True)
        (tree / "tests/stats_temporary").mkdir(parents=True)
        for header in COMMON.glob("*.h"):
            shutil.copy(header, tree / "src/common" / header.name)
        (tree / "src/common/dc_common.cpp").write_text(common_cpp, encoding="utf-8")
        shutil.copy(HARNESS, tree / "tests/stats_temporary/harness.cpp")
        binary = tree / "harness"
        built = subprocess.run([compiler, "-std=c++17", "-O0", "-UNDEBUG", "-o", str(binary),
                                str(tree / "tests/stats_temporary/harness.cpp"), str(tree / "src/common/dc_common.cpp")],
                               capture_output=True, text=True)
        if built.returncode:
            raise AssertionError("the harness did not compile:\n" + built.stderr[-4000:])
        return harness_env.run([str(binary)], capture_output=True, text=True)


class RoundTrip(unittest.TestCase):
    def test_a_buff_up_at_the_logout_is_gone_after_the_load(self):
        out = run((COMMON / "dc_common.cpp").read_text(encoding="utf-8"))
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        real = (COMMON / "dc_common.cpp").read_text(encoding="utf-8")
        self.assertEqual(1, real.count(DROP))
        mutants = {
            "temporary_kept": DROP.replace(" || c.source == Source::Temporary", ""),
            "paragon_kept": DROP.replace("c.source == Source::Paragon || ", ""),
            "passives_dropped_too": DROP.replace("c.source == Source::Temporary", "c.source == Source::Temporary || c.source == Source::Passives"),
            "everything_dropped": "[](Contribution const&) { return true; }",
        }
        for name, new in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(0, run(real.replace(DROP, new)).returncode, name + " survived")


class Wiring(unittest.TestCase):
    def test_load_drops_them_before_the_sheet_is_calculated(self):
        text = STATS.read_text(encoding="utf-8")
        load = text[text.index("void Load(Player* player)"):text.index("void Preload(Player* player)")]
        self.assertEqual(1, load.count("DropRebuiltSources(state.contributions);"))
        self.assertLess(load.index("state.contributions = DeserializeContributions("), load.index("DropRebuiltSources(state.contributions);"))
        self.assertLess(load.index("DropRebuiltSources(state.contributions);"), load.index("state.sheet = Calculate("))
        # one place decides it: no second filter beside it
        self.assertNotIn("remove_if", load)


if __name__ == "__main__":
    unittest.main()

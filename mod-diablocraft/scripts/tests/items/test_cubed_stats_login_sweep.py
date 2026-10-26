"""diablocraft-a491a: a stale Kanai's Cube or set stat contribution saved in dc_character_stats is swept at the login.

Items::RefreshCubedStats (dc_items_equip.cpp) removes only the contributions its in-memory list says it placed, and OnPlayerLogin forgets that
list, while Stats::Load brings back every saved Source::Items contribution. So a cubed power taken out of the Cube while the character was
away (or a crash between writes) left its stat on the sheet for good. The first refresh after the login now takes every saved Source::Items
contribution whose id ItemPower::CubedStatId names (a set stat's 3..255, a cubed power's 256..65535) as placed, so what is no longer wanted
is removed.

  * tests/cubed_stats_sweep/harness.cpp compiles the real dc_common.cpp and dc_item_power_math.h: a saved list with stale cubed and set
    stats round-trips like Save and Load, the sweep picks with the real CubedStatId and applies with the real RemoveContribution: the stale
    rows are gone, the weapon's 1 and 2, an item's own, another source's and the still-cubed power are kept;
  * planted differences in CubedStatId (nothing swept, the set stats left out, the weapon ids or an item's id taken in) fail the harness;
  * source guards for the server half, which cannot be compiled here: the login branch in RefreshCubedStats reads Stats::Contributions
    with the same filter, the list stays an entry when empty, and OnPlayerLogin still forgets it.

The live check is docs/test-diablocraft-a491a.md.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/cubed_stats_sweep/harness.cpp"
STATS = SRC / "stats/dc_stats.cpp"
RULE = "return id >= SetStatContributionId(0) && id <= CubeContributionId(CubeSlotLimit, 255);"


def run(math_h):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp)
        (tree / "src/common").mkdir(parents=True)
        (tree / "src/combat").mkdir(parents=True)
        for part in (SRC / "common").glob("*.h"):
            shutil.copy(part, tree / "src/common" / part.name)
        shutil.copy(SRC / "common/dc_common.cpp", tree / "src/common/dc_common.cpp")
        (tree / "src/combat/dc_item_power_math.h").write_text(math_h, encoding="utf-8")
        binary = tree / "harness"
        built = subprocess.run([compiler, "-std=c++17", "-O0", "-UNDEBUG", "-I", str(tree / "src"), "-o", str(binary), str(HARNESS),
                                str(tree / "src/common/dc_common.cpp")], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError("the harness did not compile:\n" + built.stderr[-4000:])
        return harness_env.run([str(binary)], capture_output=True, text=True)


class Sweep(unittest.TestCase):
    def test_a_stale_cubed_or_set_stat_is_gone_after_the_login(self):
        out = run(MATH.read_text(encoding="utf-8"))
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        real = MATH.read_text(encoding="utf-8")
        self.assertEqual(1, real.count(RULE))
        mutants = {
            "nothing_swept": "return false;",
            "set_stats_left": "return id >= 256 && id <= CubeContributionId(CubeSlotLimit, 255);",
            "weapon_taken": "return id >= 1 && id <= CubeContributionId(CubeSlotLimit, 255);",
            "item_taken": "return id >= SetStatContributionId(0) && id <= 65536;",
            "last_slot_left": "return id >= SetStatContributionId(0) && id < CubeContributionId(CubeSlotLimit, 255);",
        }
        for name, new in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(0, run(real.replace(RULE, new)).returncode, name + " survived")


class Wiring(unittest.TestCase):
    def refresh(self):
        text = items_source.read("dc_items_equip.cpp")
        start = text.index("void RefreshCubedStats(Player* player)")
        return text[start:text.index("\n}\n", start)]

    def test_the_first_refresh_reads_the_saved_sheet(self):
        body = self.refresh()
        self.assertEqual(1, body.count("for (Contribution const& saved : DC::Stats::Contributions(playerGuid))"))
        self.assertIn("if (saved.source == Source::Items && DC::Combat::ItemPower::CubedStatId(saved.id))", body)
        self.assertLess(body.index("if (!known)"), body.index("DC::Stats::Contributions(playerGuid)"))
        # the sweep feeds the same removal loop as a placed contribution
        self.assertLess(body.index("had.push_back({saved.stat, saved.id});"), body.index("for (auto const& [stat, id] : had)"))

    def test_an_empty_list_stays_an_entry(self):
        body = self.refresh()
        self.assertNotIn("cubedStats.erase(", body)
        self.assertIn("cubedStats[playerGuid] = placed;", body)
        self.assertIn("cubedStats[playerGuid];", body)

    def test_login_forgets_the_list_so_the_sweep_runs(self):
        text = items_source.read("dc_items.cpp")
        login = text[text.index("void OnPlayerLogin(Player* player) override", text.index("class ItemWorld")):]
        login = login[:login.index("void OnPlayerLogout")]
        self.assertIn("cubedStats.erase(player->GetGUID().GetRawValue());", login)

    def test_stats_hands_out_a_copy(self):
        text = STATS.read_text(encoding="utf-8")
        body = text[text.index("std::vector<Contribution> Contributions(std::uint64_t playerGuid)"):]
        body = body[:body.index("\n    }\n")]
        self.assertIn("std::lock_guard<std::mutex> lock(storeMutex);", body)
        self.assertIn("found->second.contributions;", body)


if __name__ == "__main__":
    unittest.main()

"""The source-text guards of kyoshiros soul: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_kyoshiros_soul.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_kyoshiros_soul import SRC  # noqa: E402


CODE = SRC / "classes/monk/dc_monk_sweeping_wind.cpp"


class Hooks(unittest.TestCase):
    def setUp(self):
        self.text = CODE.read_text(encoding="utf-8")
        tick = self.text[self.text.index("void Tick(Player* player, std::uint64_t stamp)"):]
        self.tick = tick[:tick.index("\n        }\n")]

    def test_the_tick_asks_the_item_before_its_lock_and_adds_up_to_the_maximum(self):
        ask = 'std::lround(ItemPowers::SkillSetTo(player, std::string(Skill), "idle_stacks_per_second", 0)));'
        self.assertEqual(1, self.text.count(ask))
        self.assertEqual(1, self.text.count('"idle_stacks_per_second"'))
        at = self.tick.index(ask)
        # after the vortex struck (so it knows whether it damaged anyone), before the lock it then takes
        self.assertLess(self.tick.index("struck.push_back(enemy);"), at)
        self.assertLess(at, self.tick.index("std::lock_guard<std::mutex> guard(mutex);", at))
        self.assertIn("vortex.stacks = std::min(vortex.stacks + IdleGain(vortex.quietMs, !struck.empty(), Millis(tick), idle),\n"
                      '                                         MaxStacks(Numbers::Num(spellId, "max_stacks_count"), raise));', self.tick)
        # the cap is Vengeful Wind's raised maximum (diablocraft-8iwwg), its raise asked before the lock too
        self.assertLess(self.tick.index("double const raise = Raise(player);"), self.tick.index("std::lock_guard<std::mutex> guard(mutex);", at))

    def test_a_new_cast_starts_the_quiet_second_over(self):
        self.assertIn("std::uint64_t quietMs = 0;", self.text)
        cast = self.text[self.text.index("void Cast(Player* player, std::uint32_t spellId)"):]
        self.assertIn("vortex = Vortex{};", cast[:cast.index("\n    }\n")])

    def test_the_item_name_stays_in_the_monks_folder(self):
        for path in SRC.rglob("*"):
            if path.suffix in (".cpp", ".h") and "classes/monk" not in path.as_posix():
                self.assertNotIn("idle_stacks_per_second", path.read_text(encoding="utf-8", errors="replace"), path)


if __name__ == "__main__":
    unittest.main()

"""The source-text guards of monk deadly reach: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_deadly_reach.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_deadly_reach import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.cast = (MODULE / "src/classes/monk/dc_monk_deadly_reach.cpp").read_text(encoding="utf-8")

    def test_the_monk_hands_deadly_reach_to_its_own_file(self):
        self.assertIn("return DeadlyReach::BasePct(spellId);", self.monk)
        self.assertIn("return DeadlyReach::Begin(player, spellId, primary);", self.monk)
        self.assertIn("return DeadlyReach::Cast(player, spellId, targets, punch);", self.monk)
        self.assertIn("DeadlyReach::Spent(player, spellId);", self.monk)
        # the discount is told of every cast, before any skill's own early return
        self.assertLess(self.monk.index("DeadlyReach::Spent(player, spellId);"),
                        self.monk.index("auto const* row = FistsOf(spellId);\n        if (!player || !row || targets.empty())"))

    def test_the_knock_up_is_the_stock_knockback_record_the_pylons_use(self):
        self.assertIn("player->CastSpell(enemy, Shells::PylonSpeedThrow, true);", self.cast)

    def test_the_third_hit_only(self):
        self.assertIn("punch.stage != 3", self.cast)

    def test_the_combo_uses_fists_window_tunables(self):
        for name in ("fists_combo_window_frames", "fists_combo_frames_per_second"):
            self.assertIn(f'"monk", "{name}"', self.cast)


if __name__ == "__main__":
    unittest.main()

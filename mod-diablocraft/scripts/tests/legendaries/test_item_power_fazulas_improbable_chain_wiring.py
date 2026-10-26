"""The source-text guards of fazulas improbable chain: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_fazulas_improbable_chain.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_fazulas_improbable_chain import SRC  # noqa: E402


WIZARD = SRC / "classes/wizard/dc_wizard_archon.cpp"


class Hooks(unittest.TestCase):
    def setUp(self):
        self.text = WIZARD.read_text(encoding="utf-8")

    def body(self, start):
        body = self.text[self.text.index(start):]
        return body[:body.index("\n    }\n")]

    def test_entering_archon_starts_the_stacks_at_the_items_number(self):
        enter = self.body("void EnterArchon(Player* player, uint32 form)")
        ask = 'unsigned const start = static_cast<unsigned>(std::lround(ItemPowers::SkillSetTo(player, "Archon", "start_stacks", 0)));'
        self.assertEqual(1, enter.count(ask))
        self.assertIn("StateOf(player).archonStacks = start;", enter)
        self.assertNotIn("archonStacks = 0", enter)
        # the item powers are asked before the Wizard's lock is taken
        self.assertLess(enter.index(ask), enter.index("std::lock_guard<std::recursive_mutex> guard(mutex);"))

    def test_leaving_clears_them_and_the_damage_reads_them(self):
        self.assertIn("StateOf(player).archonStacks = 0;", self.body("void LeaveArchon(Player* player)"))
        self.assertIn('factor *= 1 + Num(form, "damage_bonus_pct", "kill") * StateOf(player).archonStacks / 100;',
                      (SRC / "classes/wizard/dc_wizard_formula.cpp").read_text(encoding="utf-8"))
        self.assertEqual(1, self.text.count('"start_stacks"'))


if __name__ == "__main__":
    unittest.main()

"""The source-text guards of mykens ball of hate: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_mykens_ball_of_hate.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_mykens_ball_of_hate import MODULE  # noqa: E402


WIZARD = MODULE / "src/classes/wizard/dc_wizard_electrocute.cpp"


def jumps_failures(text):
    """What is wrong with Wizard::Jumps in `text` (the source guards; [] when it is right)."""
    start = text.index("std::vector<Unit*> Jumps(Player* player, std::uint32_t spellId, Unit* first)")
    body = text[start:text.index("\n    }\n", start)]
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("mayRehit is on while a jump_rehit source is worn (0 without it)",
         'bool const mayRehit = ItemPowers::SkillSetTo(player, "Electrocute", "jump_rehit", 0) > 0;' in body)
    need("the walk takes it", "first, jumps, mayRehit," in body)
    need("no fixed mayRehit is left", "bool const mayRehit = false;" not in body and "bool const mayRehit = true;" not in body)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_walk_takes_the_orb(self):
        self.assertEqual([], jumps_failures(WIZARD.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        real = WIZARD.read_text(encoding="utf-8")
        line = 'bool const mayRehit = ItemPowers::SkillSetTo(player, "Electrocute", "jump_rehit", 0) > 0;'
        mutants = {
            "never": (line, "bool const mayRehit = false;"),
            "always": (line, "bool const mayRehit = true;"),
            "base_one": ('"jump_rehit", 0) > 0;', '"jump_rehit", 1) > 0;'),
            "another_stat": ('"jump_rehit", 0) > 0;', '"pierces", 0) > 0;'),
            "another_skill": ('SkillSetTo(player, "Electrocute", "jump_rehit"', 'SkillSetTo(player, "Chain Lightning", "jump_rehit"'),
            "walk_ignores_it": ("first, jumps, mayRehit,", "first, jumps, false,"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(jumps_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()

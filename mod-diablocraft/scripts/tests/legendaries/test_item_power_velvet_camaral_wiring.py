"""The source-text guards of velvet camaral: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_velvet_camaral.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_velvet_camaral import MODULE  # noqa: E402


WIZARD = MODULE / "src/classes/wizard/dc_wizard_electrocute.cpp"


def jumps_failures(text):
    """What is wrong with Wizard::Jumps in `text` (the source guards; [] when it is right)."""
    start = text.index("std::vector<Unit*> Jumps(Player* player, std::uint32_t spellId, Unit* first)")
    body = text[start:text.index("\n    }\n", start)]
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    factor = 'unsigned(ItemPowers::SkillSetTo(player, "Electrocute", "jump_count_factor", 1))'
    need("the jumps are Electrocute's own times the hat's factor (1 without it)",
         'unsigned const jumps = Chain::JumpCount(row->rune, Num(spellId, "target_count")) *\n                               ' + factor + ";" in body)
    need("the walk takes those jumps", "first, jumps, mayRehit," in body)
    need("the item powers header is included", '#include "../../combat/dc_item_powers.h"' in text)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_walk_takes_the_doubled_jumps(self):
        self.assertEqual([], jumps_failures(WIZARD.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        real = WIZARD.read_text(encoding="utf-8")
        mutants = {
            "no_factor": (' *\n                               unsigned(ItemPowers::SkillSetTo(player, "Electrocute", "jump_count_factor", 1));', ";"),
            "base_zero": ('"jump_count_factor", 1))', '"jump_count_factor", 0))'),
            "another_stat": ('"jump_count_factor", 1))', '"pierces", 1))'),
            "another_skill": ('SkillSetTo(player, "Electrocute", "jump_count_factor"', 'SkillSetTo(player, "Chain Lightning", "jump_count_factor"'),
            "added_not_multiplied": ('Num(spellId, "target_count")) *\n', 'Num(spellId, "target_count")) +\n'),
            "walk_ignores_it": ("first, jumps, mayRehit,", "first, Chain::JumpCount(row->rune, Num(spellId, \"target_count\")), mayRehit,"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(jumps_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()

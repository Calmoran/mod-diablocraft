"""The source-text guards of cosmic strand: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_cosmic_strand.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source


def hook_rules(test, wizard):
    row = wizard[wizard.index("uint32 WormholeOf(Player* player, uint32 id)"):wizard.index("} // namespace", wizard.index("uint32 WormholeOf("))]
    test.assertIn('if (IsRune(id, "Wormhole"))\n                return id;', row)                         # chosen: the cast's row, once
    test.assertIn('ItemPowers::GrantsRune(player, "Teleport", "Wormhole")', row)
    test.assertIn('std::string_view("Teleport") == row.skill && std::string_view("Wormhole") == row.rune', row)
    cast = wizard[wizard.index("void Cast(Player* player, uint32 id)"):]
    window = cast[cast.index('if (uint32 const wormhole = WormholeOf(player, id))'):cast.index("} // namespace DC::Combat::Wizard::Teleport")]
    test.assertIn('double const seconds = Num(wormhole, "duration_seconds");', window)
    test.assertIn('state.wormholeLeft = unsigned(Num(wormhole, "cast_count"));', window)
    test.assertNotIn('Num(id,', window)                      # the chosen rune's row has no Wormhole numbers
    test.assertNotIn('IsRune(id, "Wormhole")', window)       # the rune is not required to be the chosen one
    test.assertIn("SendSkillCooldown(player, id, 0);", window)    # the cast's own cooldown is the one taken off


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wizard = wizard_source.CPP.read_text(encoding="utf-8")

    def test_a_given_wormhole_opens_the_window_with_the_wormhole_rows_numbers(self):
        hook_rules(self, self.wizard)

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "a_given_rune_is_not_asked": ('            if (!ItemPowers::GrantsRune(player, "Teleport", "Wormhole"))\n                return 0;\n', ""),
            "the_chosen_rune_is_required": ('if (uint32 const wormhole = WormholeOf(player, id))', 'if (uint32 const wormhole = IsRune(id, "Wormhole") ? id : 0)'),
            "the_cast_rows_duration": ('Num(wormhole, "duration_seconds")', 'Num(id, "duration_seconds")'),
            "the_cast_rows_count": ('Num(wormhole, "cast_count")', 'Num(id, "cast_count")'),
            "any_skill_gives_it": ('std::string_view("Teleport") == row.skill && ', ""),
            "a_chosen_wormhole_is_not_its_own_row": ('if (IsRune(id, "Wormhole"))\n                return id;', ""),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, self.wizard.count(old), name)
            with self.subTest(name), self.assertRaises((AssertionError, ValueError)):  # a guard text that is gone fails too
                hook_rules(self, self.wizard.replace(old, new))


if __name__ == "__main__":
    unittest.main()

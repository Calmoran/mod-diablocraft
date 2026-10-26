"""The source-text guards of warstaff of general quang: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_warstaff_of_general_quang.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_warstaff_of_general_quang import SRC  # noqa: E402


def hook_rules(test, rush):
    row = rush[rush.index("std::uint32_t TailwindOf(Player* player, std::uint32_t spellId)"):rush.index("double DamagePerSecond(")]
    test.assertIn('if (IsRune(spellId, "Tailwind"))\n                return spellId;', row)                # chosen: the cast's row, once
    test.assertIn('ItemPowers::GrantsRune(player, std::string(Skill), "Tailwind")', row)
    test.assertIn('Skill == row.skill && std::string_view("Tailwind") == row.rune', row)
    cast = rush[rush.index("void Cast(Player* player, std::uint32_t spellId)"):rush.index("void Stop(Player* player)")]
    test.assertIn("std::uint32_t const tailwind = TailwindOf(player, spellId);", cast[:cast.index("std::lock_guard")])  # outside the lock
    test.assertIn("run.tailwind = tailwind;", cast)
    speed = cast[cast.index("if (tailwind)"):cast.index("Stats::Recompute(player);")]
    test.assertIn('{Source::Temporary, Stat::MovementSpeed, tailwind,\n                                    Numbers::Num(tailwind, "movement_speed_pct")', speed)
    test.assertNotIn('IsRune(spellId, "Tailwind")', cast)     # the rune is not required to be the chosen one
    end = rush[rush.index("void End(Player* player)"):rush.index("// Flurry:")]
    test.assertIn("tailwind = found->second.tailwind;", end)   # what the press put on, not what the item gives now
    test.assertIn("if (tailwind)\n            {\n                Stats::RemoveContribution(player->GetGUID().GetRawValue(), Source::Temporary, Stat::MovementSpeed,\n"
                  "                                          tailwind);", end)


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rush = (SRC / "classes/monk/dc_monk_tempest_rush.cpp").read_text(encoding="utf-8")

    def test_a_given_tailwind_speeds_the_channel_with_the_tailwind_rows_number(self):
        hook_rules(self, self.rush)

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "a_given_rune_is_not_asked": ('            if (!ItemPowers::GrantsRune(player, std::string(Skill), "Tailwind"))\n                return 0;\n', ""),
            "the_chosen_rune_is_required": ("std::uint32_t const tailwind = TailwindOf(player, spellId);",
                                            'std::uint32_t const tailwind = IsRune(spellId, "Tailwind") ? spellId : 0;'),
            "the_cast_rows_speed": ('Numbers::Num(tailwind, "movement_speed_pct")', 'Numbers::Num(spellId, "movement_speed_pct")'),
            "any_skill_gives_it": ('Skill == row.skill && std::string_view("Tailwind")', 'std::string_view("Tailwind")'),
            "a_chosen_tailwind_is_not_its_own_row": ('if (IsRune(spellId, "Tailwind"))\n                return spellId;', ""),
            "the_end_takes_off_the_cast_row": ("                                          tailwind);", "                                          spellId);"),
            "the_end_asks_the_chosen_rune": ("            if (tailwind)\n            {\n                Stats::RemoveContribution",
                                             '            if (IsRune(spellId, "Tailwind"))\n            {\n                Stats::RemoveContribution'),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, self.rush.count(old), name)
            with self.subTest(name), self.assertRaises((AssertionError, ValueError)):  # a guard text that is gone fails too
                hook_rules(self, self.rush.replace(old, new))


if __name__ == "__main__":
    unittest.main()

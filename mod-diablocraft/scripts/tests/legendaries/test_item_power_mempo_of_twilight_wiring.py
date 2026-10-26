"""The source-text guards of mempo of twilight: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_mempo_of_twilight.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source


def hook_rules(test, wizard):
    row = wizard[wizard.index("uint32 ShowerOf(Player* player, uint32 id)"):wizard.index("void Impact(", wizard.index("uint32 ShowerOf("))]
    test.assertIn('if (IsRune(id, "Meteor Shower"))\n                return id;', row)                       # chosen: the cast's row, once
    test.assertIn('ItemPowers::GrantsRune(player, "Meteor", "Meteor Shower")', row)
    test.assertIn('std::string_view("Meteor") == row.skill && std::string_view("Meteor Shower") == row.rune', row)
    test.assertIn('if (IsSkill(id, "Meteor"))\n            return Meteor::Delayed(player, id, center, dynamo);', wizard)
    delayed = wizard[wizard.index("bool Delayed(Player* player, uint32 id, Position const& center, bool dynamo)"):
                     wizard.index("} // namespace DC::Combat::Wizard::Meteor")]
    test.assertIn("uint32 const shower = ShowerOf(player, id);", delayed)
    test.assertIn('double const delay = Num(shower ? shower : id, "delay_seconds");', delayed)      # the Shower's own first-impact delay
    test.assertLess(delayed.index("ShowerOf(player, id)"), delayed.index("double const delay"))
    shower = delayed[delayed.index("if (shower)"):delayed.index("double pct = Num(id")]
    test.assertIn('unsigned const count = unsigned(Num(shower, "spawn_count"));', shower)
    test.assertIn('Num(shower, "radius_yards", "spread")', shower)
    test.assertIn('Num(shower, "delay_seconds", "interval")', shower)
    test.assertIn("Impact(p, shower, at, Num(shower, \"damage_pct\"), dynamo)", shower)      # every meteor falls as the Shower's
    test.assertNotIn("Num(id,", shower)                                                         # the chosen rune's row is not the Shower's
    test.assertNotIn('IsRune(id, "Meteor Shower")', shower)                                     # the rune is not required to be the chosen one


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wizard = wizard_source.CPP.read_text(encoding="utf-8")

    def test_a_given_shower_takes_every_meteor_with_the_shower_rows_numbers(self):
        hook_rules(self, self.wizard)

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "a_given_rune_is_not_asked": ('            if (!ItemPowers::GrantsRune(player, "Meteor", "Meteor Shower"))\n                return 0;\n', ""),
            "the_chosen_rune_is_required": ("uint32 const shower = ShowerOf(player, id);", 'uint32 const shower = IsRune(id, "Meteor Shower") ? id : 0;'),
            "the_cast_rows_delay": ('Num(shower ? shower : id, "delay_seconds")', 'Num(id, "delay_seconds")'),
            "the_cast_rows_count": ('Num(shower, "spawn_count")', 'Num(id, "spawn_count")'),
            "the_cast_rows_spread": ('Num(shower, "radius_yards", "spread")', 'Num(id, "radius_yards", "spread")'),
            "the_cast_rows_interval": ('Num(shower, "delay_seconds", "interval")', 'Num(id, "delay_seconds", "interval")'),
            "the_cast_rows_impact": ("Impact(p, shower, at, Num(shower, \"damage_pct\"), dynamo)", "Impact(p, id, at, Num(shower, \"damage_pct\"), dynamo)"),
            "any_skill_gives_it": ('std::string_view("Meteor") == row.skill && ', ""),
            "a_chosen_shower_is_not_its_own_row": ('if (IsRune(id, "Meteor Shower"))\n                return id;', ""),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, self.wizard.count(old), name)
            with self.subTest(name), self.assertRaises((AssertionError, ValueError)):  # a guard text that is gone fails too
                hook_rules(self, self.wizard.replace(old, new))


if __name__ == "__main__":
    unittest.main()

"""The source-text guards of blackthornes battlegear: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_blackthornes_battlegear.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_blackthornes_battlegear import MODULE  # noqa: E402


POWERS = item_powers_source.CPP


def refresh_failures(text):
    """What is wrong with the immunity refresh in dc_item_powers.cpp `text` (the source guards; [] when it is right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    one = text[text.index("void Immunize(Player* player, std::string const& control, bool on)"):]
    one = one[:one.index("\n        }\n")]
    need("ground_effects never reaches the core's spell immunity",
         one.index('if (control == "ground_effects")') < one.index("ApplySpellImmune") if 'if (control == "ground_effects")' in one else False)
    need("and returns there", 'if (control == "ground_effects") // World\'s mark, set on every refresh below\n                return;' in one)
    every = text[text.index("void Immunize(Player* player)\n"):]
    every = every[:every.index("\n        }\n")]
    mark = 'DC::Rifts::SetGroundEffectImmune(player, now.count("ground_effects") > 0);'
    need("the mark follows the row on every refresh", every.count(mark) == 1)
    need("after the item powers' lock and after the diff", mark in every and every.index(mark) > every.rindex("Immunize(player, control, true);")
         and every.index(mark) > every.index("immune[guid] = now;\n            }"))
    need("unconditionally", mark in every and "if (" not in every[every.rindex("Immunize(player, control, true);"):every.index(mark)])
    need("the refresh reads the generic `immune` rows", "now = ItemPower::Immunities(Data().rows, CountsOf(guid), SituationOf(guid));" in every)
    need("no set name in the reader", '"Blackthorne' not in text)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_refresh_sets_worlds_mark(self):
        self.assertEqual([], refresh_failures(POWERS.read_text(encoding="utf-8")))
        self.assertIn("void SetGroundEffectImmune(Player const* player, bool immune);", (MODULE / "src/rifts/dc_rifts.h").read_text(encoding="utf-8"))
        self.assertIn('#include "../rifts/dc_rifts.h"', POWERS.read_text(encoding="utf-8"))

    def test_the_source_guards_fail_their_mutants(self):
        real = POWERS.read_text(encoding="utf-8")
        mark = 'DC::Rifts::SetGroundEffectImmune(player, now.count("ground_effects") > 0);'
        mutants = {
            "no_mark": (mark, ""),
            "always_marked": (mark, "DC::Rifts::SetGroundEffectImmune(player, true);"),
            "mark_on_the_change_only": ("            " + mark, "            if (now.count(\"ground_effects\") != before.count(\"ground_effects\"))\n                " + mark),
            "reaches_the_spell_immunity": ('            if (control == "ground_effects") // World\'s mark, set on every refresh below\n                return;\n', ""),
            "set_by_name": (mark, 'DC::Rifts::SetGroundEffectImmune(player, BonusActive(player, "Blackthorne\'s Battlegear", 4));'),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(refresh_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()

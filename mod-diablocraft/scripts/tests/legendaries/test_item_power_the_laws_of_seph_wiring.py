"""The source-text guards of the laws of seph: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_the_laws_of_seph.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_math import all_rows, planner, read_csv, tooltip
from test_item_power_the_laws_of_seph import SKILL, SRC  # noqa: E402


class Hooks(unittest.TestCase):
    """The C++ that runs in the server is compile-checked, not run here: these prove the path is there."""

    def test_every_blinding_flash_spell_is_a_shell_of_that_name(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        runes = [r["rune_name"] for r in read_csv("data/d3/monk_runes.csv") if r["skill_name"] == SKILL]
        self.assertEqual(5, len(runes))
        for rune in ["", *runes]:
            self.assertEqual(1, len(re.findall(r'\{\d+, "%s", "%s", ' % (SKILL, re.escape(rune)), shells)), rune)

    def test_a_pressed_cast_fires_the_cast_event(self):
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cast = powers[powers.index("void Cast(Player* player, std::uint32_t spellId)"):powers.index("void Hit(Player* player")]
        self.assertEqual(1, cast.count('Fire(player, "cast", skill->skill, 1.0);'))
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("if (player && row && !spell->IsTriggered())\n                    ItemPowers::Cast(player, info->Id);", combat)

    def test_the_refund_is_the_classs_primary_resource_and_a_monks_is_spirit(self):
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        refund = powers[powers.index('one.stat == "resource_refund"'):]
        refund = refund[:refund.index("Resources::Add")]
        self.assertIn("Resources::Of(Classes::ClassIdOf(player))", refund)
        self.assertEqual(["spirit"], [r["resource_key"] for r in read_csv("data/d3/class_resources.csv") if r["d3_class"] == "Monk"])
        self.assertEqual(["primary"], [r["role"] for r in read_csv("data/d3/class_resources.csv") if r["d3_class"] == "Monk"])


if __name__ == "__main__":
    unittest.main()

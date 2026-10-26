"""The source-text guards of shame of delsere: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_shame_of_delsere.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_math import all_rows, planner, read_csv, tooltip
from test_item_power_shame_of_delsere import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    """The C++ that runs in the server is compile-checked, not run here: these prove the calls are there."""

    def test_a_pressed_cast_fires_the_cast_event_once(self):
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cast = powers[powers.index("void Cast(Player* player, std::uint32_t spellId)"):powers.index("void Hit(Player* player")]
        self.assertEqual(1, cast.count('Fire(player, "cast", skill->skill, 1.0);'))
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertEqual(1, combat.count("ItemPowers::Cast(player, info->Id);"))
        self.assertIn("if (player && row && !spell->IsTriggered())\n                    ItemPowers::Cast(player, info->Id);", combat)

    def test_prodigy_is_paid_on_the_same_per_cast_footing(self):
        # Prodigy is the Wizard's (src/classes/wizard/dc_wizard_passives.cpp), paid from Wizard::Begin, which the cast hook calls once.
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertEqual(1, combat.count("Wizard::Begin(player, shell.spellId, GetExplTargetUnit());"))
        passives = (SRC / "classes/wizard/dc_wizard_passives.cpp").read_text(encoding="utf-8")
        self.assertIn('if (Signature(spellId) && Has(player, "Prodigy"))', passives)
        self.assertIn('Combat::GainResource(player, id, Num(id, "gain_resource"));', passives)
        wizard = (SRC / "classes/wizard/dc_wizard.cpp").read_text(encoding="utf-8")
        begin = wizard[wizard.index("void Begin(Player* player, std::uint32_t spellId, Unit* explicitTarget)"):wizard.index("void Cast(Player* player")]
        self.assertEqual(1, begin.count("Passive::Prodigy(player, spellId);"))

    def test_the_refund_is_the_classs_primary_resource_and_a_wizards_is_arcane_power(self):
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        refund = powers[powers.index('one.stat == "resource_refund"'):]
        refund = refund[:refund.index("Resources::Add")]
        self.assertIn("Resources::Of(Classes::ClassIdOf(player))", refund)
        self.assertIn('Find("Wizard", "arcane_power")', (SRC / "classes/dc_resources.h").read_text(encoding="utf-8"))
        self.assertEqual(["arcane_power"], [r["resource_key"] for r in read_csv("data/d3/class_resources.csv") if r["d3_class"] == "Wizard"])


if __name__ == "__main__":
    unittest.main()

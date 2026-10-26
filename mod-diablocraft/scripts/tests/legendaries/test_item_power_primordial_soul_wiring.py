"""The source-text guards of primordial soul: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_primordial_soul.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_primordial_soul import SRC, WIZARD, definition, target_factor  # noqa: E402


POWERS = item_powers_source.CPP


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = POWERS.read_text(encoding="utf-8")
        cls.wizard = WIZARD.read_text(encoding="utf-8")

    def test_the_wrapper_reads_the_worn_items_the_way_skill_set_to_does(self):
        wrapper = definition("double PassiveSetTo(Player const* player, std::string const& passive, std::string const& token, double base)", self.powers)
        for line in ("if (!player)\n            return base;", "ItemPower::Situation seen = Seen(player);", "std::lock_guard<std::mutex> lock(mutex);",
                     "std::uint64_t const guid = player->GetGUID().GetRawValue();",
                     "return ItemPower::PassiveSetTo(Data().rows, CountsOf(guid), passive, token, base, SituationOf(guid, std::move(seen)));"):
            self.assertIn(line, wrapper)
        self.assertIn("double PassiveSetTo(Player const*, std::string const& passive, std::string const& token, double base);",
                      (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))

    def test_target_factor_takes_the_number_before_its_lock(self):
        body = target_factor(self.wizard)
        call = 'double const perStack = ItemPowers::PassiveSetTo(player, "Elemental Exposure", "damage_taken_pct", Num(id, "damage_taken_pct"));'
        self.assertIn(call, body)
        self.assertLess(body.index("Has(player"), body.index(call))                         # only a wizard who has the passive
        self.assertLess(body.index(call), body.index("std::lock_guard<std::recursive_mutex> guard(mutex);"))   # the item powers take their own lock
        self.assertIn("return 1 + perStack *", body)
        self.assertIn('#include "../../combat/dc_item_powers.h"', self.wizard)

    def test_the_passive_stays_a_wizard_sheet_number(self):
        # the combat log's factor label and the bucket test read the same function
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("hit.targetFactor = Wizard::TargetFactor(player, target, hit.factors);", combat)
        named = definition("double TargetFactor(Player* player, Unit* target, Factors& out)", self.wizard)
        self.assertIn("double const factor = TargetFactor(player, target);", named)
        self.assertIn('if (factor != 1.0)\n            out.emplace_back("Elemental Exposure", factor);\n        return factor;', named)
        self.assertIn("Wizard::TargetFactor(player, target) / hit.targetFactor", combat)


if __name__ == "__main__":
    unittest.main()

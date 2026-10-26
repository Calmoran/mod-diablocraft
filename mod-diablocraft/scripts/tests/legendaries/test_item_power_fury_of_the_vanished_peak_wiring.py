"""The source-text guards of fury of the vanished peak: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_fury_of_the_vanished_peak.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_fury_of_the_vanished_peak import SRC  # noqa: E402


def hook_rules(test, powers):
    body = powers[powers.index("void CostAuras(Player* player)"):]
    body = body[:body.index("\n        }\n")]
    test.assertIn("for (Shells::SkillCostModifier const& row : Shells::SkillCostModifiers)", body)
    test.assertIn('ItemPower::SkillSum(Data().rows, CountsOf(guid), row.skill, "cost_reduction_pct", SituationOf(guid))', body)
    test.assertEqual(2, body.count("PutCostAura(player, row.id, pct);"))
    put = powers[powers.index("void PutCostAura(Player* player, std::uint32_t id, double pct)"):powers.index("void CostAuras(Player* player)")]
    test.assertIn("CostMath::ModifierAmount(pct)", put)                                  # whole percent, negative: a reduction
    test.assertIn("player->CastCustomSpell(player, id, &amount, nullptr, nullptr, true);", put)
    test.assertIn("player->RemoveAurasDueToSpell(id);", put)


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")

    def test_refresh_keeps_the_skill_auras_in_step(self):
        hook_rules(self, self.powers)

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "the_skill_auras_are_not_set": ("            for (Shells::SkillCostModifier const& row : Shells::SkillCostModifiers)",
                                            "            for (Shells::SkillCostModifier const& row : {Shells::SkillCostModifiers[0]})"),
            "the_element_sum": ('ItemPower::SkillSum(Data().rows, CountsOf(guid), row.skill, "cost_reduction_pct"',
                                'ItemPower::ElementSum(Data().rows, CountsOf(guid), row.skill, "cost_reduction_pct"'),
            "never_cast": ("player->CastCustomSpell(player, id, &amount, nullptr, nullptr, true);", ""),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, self.powers.count(old), name)
            with self.subTest(name), self.assertRaises((AssertionError, ValueError)):
                hook_rules(self, self.powers.replace(old, new))


if __name__ == "__main__":
    unittest.main()

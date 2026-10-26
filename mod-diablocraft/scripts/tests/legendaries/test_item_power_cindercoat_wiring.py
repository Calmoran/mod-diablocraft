"""The source-text guards of cindercoat: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_cindercoat.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_cindercoat import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_refresh_keeps_the_class_auras_in_step(self):
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        refresh = powers[powers.index("void Refresh(Player* player, Item* changed"):powers.index("std::vector<double> WornRolls(")]
        self.assertTrue(refresh.rstrip().endswith("Immunize(player);\n        CostAuras(player);\n        DropStacks(player);\n    }"))   # after both counts and worn items
        body = powers[powers.index("void CostAuras(Player* player)"):]
        body = body[:body.index("\n        }\n")]
        self.assertIn("for (Shells::ElementCostModifier const& row : Shells::ElementCostModifiers)", body)
        self.assertIn("if (row.classId != classId)", body)
        self.assertIn('ItemPower::ElementSum(Data().rows, CountsOf(guid), row.element, "cost_reduction_pct", SituationOf(guid))', body)
        self.assertIn("PutCostAura(player, row.id, pct);", body)
        # the aura is put by the helper the skill auras share (N-COST, diablocraft-e0pt4)
        put = powers[powers.index("void PutCostAura(Player* player, std::uint32_t id, double pct)"):powers.index("void CostAuras(Player* player)")]
        self.assertIn("CostMath::ModifierAmount(pct)", put)                                  # whole percent, negative: a reduction
        self.assertIn("player->CastCustomSpell(player, id, &amount, nullptr, nullptr, true);", put)
        self.assertIn("player->RemoveAurasDueToSpell(id);", put)


if __name__ == "__main__":
    unittest.main()

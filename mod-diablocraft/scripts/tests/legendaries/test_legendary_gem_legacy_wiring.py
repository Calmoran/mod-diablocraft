"""The source-text guards of legendary gem legacy: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_legendary_gem_legacy.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_legendary_gem_legacy import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.gems = (SRC / "combat/dc_gem_powers.cpp").read_text(encoding="utf-8")
        cls.items = item_powers_source.CPP.read_text(encoding="utf-8")

    @staticmethod
    def body(text, signature):
        start = text.index(signature)
        return text[start:text.index("\n    }\n", start)]

    def test_the_hit_takes_it_as_a_named_step_8_factor_once(self):
        compute = self.body(self.combat, "bool ComputeHit(")
        self.assertEqual(1, compute.count("GemPowers::Multipliers(player, hit.factors);"))
        multipliers = self.body(self.gems, "void Multipliers(Player* player, DC::Combat::Factors& out)")
        self.assertIn('"Legacy of Dreams", GemPower::LegacyFactor(powers, items)', multipliers)
        self.assertIn("LegacyItems(player, powers)", multipliers)
        every = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.cpp"))
        self.assertEqual(1, every.count("GemPower::LegacyFactor("))

    def test_both_damage_taken_paths_take_its_reduction(self):
        incoming = self.body(self.gems, "double IncomingFactor(Player* player, unsigned schoolMask, bool melee)")
        self.assertIn("GemPower::LegacyIncomingFactor(powers, LegacyItems(player, powers))", incoming)
        self.assertGreaterEqual(self.combat.count("GemPowers::IncomingFactor(victim->ToPlayer()"), 2)

    def test_the_count_reads_the_worn_legendaries_and_the_set_counter(self):
        reader = self.body(self.gems, "unsigned LegacyItems(Player const* player, GemPower::Powers const& powers)")
        self.assertIn("ItemPowers::WornLegendaries(player)", reader)
        self.assertIn("GemPower::LegacyItems(powers, worn.items, worn.ancients, worn.setBonusOn)", reader)
        worn = self.body(self.items, "Legendaries WornLegendaries(Player const* player)")
        self.assertIn("ItemPower::AnySetBonus(CountsOf(guid))", worn)

    def test_every_worn_legendary_is_kept_not_only_power_owners(self):
        refresh = self.body(self.items, "void Refresh(Player* player, Item* changed, bool equipping, Items::Instance const& instance)")
        kept = refresh.index("DC::Quality::Eligible(instance.rarity)")
        self.assertLess(kept, refresh.index("if (!setPiece && !owner)"))
        # a Primal is a Primal Ancient: every quality but normal counts twice
        self.assertIn('DC::Quality::Clean(instance.qualityTier) != "normal"', refresh)
        self.assertIn("mine.erase(changed->GetGUID().GetCounter());", refresh[kept:])
        self.assertIn("legendaries.erase(player->GetGUID().GetRawValue());", self.items)


if __name__ == "__main__":
    unittest.main()

"""The source-text guards of gungdo gear: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_gungdo_gear.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_gungdo_gear import SRC  # noqa: E402


def hook_rules(test, palm, powers, combat, monk):
    explode = palm[palm.index("void Explode(Player* player, Unit* dead, std::uint32_t spellId)"):palm.index("class dc_monk_exploding_palm_death")]
    fires = explode.index("ItemPowers::Exploded(player, enemy, std::string(Skill));")
    test.assertLess(fires, explode.index('if (IsRune(spellId, "Essence Burn"))'))          # before the burn's runs
    test.assertLess(fires, explode.index("Combat::StrikeArea(player, spellId, center, radius, pct)"))  # and before the blast's damage
    test.assertIn("for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))\n                if (enemy != dead)\n"
                  "                    ItemPowers::Exploded(", explode)
    apply_ = palm[palm.index("bool Apply(Player* player, Unit* enemy, std::uint32_t spellId)"):palm.index("void Cast(Player* player")]
    test.assertIn("!Row(spellId)", apply_)
    test.assertIn("Palm(player, enemy, spellId);\n        return true;", apply_)
    exploded = powers[powers.index("void Exploded(Player* player, Unit* enemy, std::string const& skill)"):]
    test.assertIn('Fire(player, "explosion", skill, 1.0, enemy);', exploded[:200])
    bleed = combat[combat.index("bool ApplySkillBleed(Player* player, Unit* target, std::uint32_t spellId)"):]
    test.assertLess(bleed.index("Monk::Apply(player, target, spellId)"), bleed.index("Abilities::Bleed("))
    test.assertIn("return ExplodingPalm::Apply(player, target, spellId);", monk)


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palm = (SRC / "classes/monk/dc_monk_exploding_palm.cpp").read_text(encoding="utf-8")
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.monk = (SRC / "classes/monk/dc_monk.cpp").read_text(encoding="utf-8")

    def sources(self):
        return {"palm": self.palm, "powers": self.powers, "combat": self.combat, "monk": self.monk}

    def test_the_explosion_applies_the_palm_through_the_effect(self):
        hook_rules(self, **self.sources())

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "the_explosion_fires_nothing": ("palm", "                    ItemPowers::Exploded(player, enemy, std::string(Skill));\n", ""),
            "the_dead_one_too": ("palm", "                if (enemy != dead)\n                    ItemPowers::Exploded(", "                    ItemPowers::Exploded("),
            "another_event": ("powers", 'Fire(player, "explosion", skill, 1.0, enemy);', 'Fire(player, "hit", skill, 1.0, enemy);'),
            "the_palm_is_not_applied": ("palm", "        Palm(player, enemy, spellId);\n        return true;", "        return true;"),
            "rend_only": ("combat", "        if (player && target && Monk::Apply(player, target, spellId))\n            return true;\n", ""),
            "the_monk_applies_nothing": ("monk", "return ExplodingPalm::Apply(player, target, spellId);", "return false;"),
        }
        for name, (where, old, new) in mutants.items():
            sources = self.sources()
            self.assertEqual(1, sources[where].count(old), name)
            sources[where] = sources[where].replace(old, new)
            with self.subTest(name), self.assertRaises((AssertionError, ValueError)):  # a guard text that is gone fails too
                hook_rules(self, **sources)


if __name__ == "__main__":
    unittest.main()

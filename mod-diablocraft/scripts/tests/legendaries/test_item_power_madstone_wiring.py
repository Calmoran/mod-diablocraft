"""The source-text guards of madstone: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_madstone.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_gungdo_gear_wiring import Hooks as GungdoHooks, hook_rules
from test_item_power_madstone import SRC  # noqa: E402


def strike_rules(test, strike, combat, passives, powers):
    test.assertIn("Combat::StrikeArea(player, id, target->GetPosition(), Numbers::Num(id, \"radius_yards\"))", strike)  # Fulminating Onslaught
    test.assertIn("else if (Combat::Strike(player, target, id))", strike)
    body = combat[combat.index("    bool Strike(Player* player, Unit* target, std::uint32_t spellId, std::optional<double> pct, bool periodic)"):]
    body = body[:body.index("    std::vector<Unit*> StrikeArea(")]
    test.assertIn("Passives::Hit(player, target, spellId, hit.school);", body)
    area = combat[combat.index("    std::vector<Unit*> StrikeArea(Player* player"):]
    test.assertIn("Strike(", area[:area.index("\n    }\n")])
    hit = passives[passives.index("    void Hit(Player* p, Unit* target, uint32 spellId, unsigned school)"):]
    test.assertIn("ItemPowers::Hit(p, target, spellId);", hit[:300])
    fire = powers[powers.index("    void Hit(Player* player, Unit* target, std::uint32_t spellId)"):]
    test.assertIn('Fire(player, "hit", name, scale, target);', fire[:600])
    test.assertIn('else if (one.stat == "apply_skill" && target)\n                    Abilities::ApplySkillBleed(player, target, one.skill.c_str());', powers)


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strike = (SRC / "classes/monk/dc_monk_seven_sided_strike.cpp").read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.passives = (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8")
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")

    def sources(self):
        return {"strike": self.strike, "combat": self.combat, "passives": self.passives, "powers": self.powers}

    def test_each_strike_reaches_the_hit_event_and_the_apply(self):
        strike_rules(self, **self.sources())

    def test_the_palm_is_applied_through_the_monks_own_apply(self):
        GungdoHooks.setUpClass()
        hook_rules(self, **GungdoHooks.sources(GungdoHooks))

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "a_strike_fires_no_hit": ("combat", "            Passives::Hit(player, target, spellId, hit.school);\n", ""),
            "the_items_skip_the_hit": ("passives", "        ItemPowers::Hit(p, target, spellId);\n", ""),
            "the_hit_is_another_event": ("powers", 'Fire(player, "hit", name, scale, target);', 'Fire(player, "hit_spender", name, scale, target);'),
            "the_apply_lost": ("powers", "Abilities::ApplySkillBleed(player, target, one.skill.c_str());", ";"),
            "a_strike_not_struck": ("strike", "else if (Combat::Strike(player, target, id))", "else if (true)"),
        }
        for name, (where, old, new) in mutants.items():
            sources = self.sources()
            self.assertEqual(1, sources[where].count(old), name)
            sources[where] = sources[where].replace(old, new)
            with self.subTest(name), self.assertRaises((AssertionError, ValueError)):
                strike_rules(self, **sources)


if __name__ == "__main__":
    unittest.main()

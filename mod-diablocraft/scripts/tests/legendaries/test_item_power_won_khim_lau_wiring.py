"""The source-text guards of won khim lau: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_won_khim_lau.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_won_khim_lau import SRC  # noqa: E402


def hook_rules(test, rush, combat, powers):
    start = rush.index("        void Hit(Player* player, std::uint32_t spellId)")
    tick = rush[start:rush.index("        void Tick(Player* player, std::uint64_t generation)", start)]
    test.assertIn("if (!Combat::Strike(player, enemy, spellId, pct))\n                    continue;\n                ++struck;", tick)
    test.assertIn("if (struck)\n                Combat::Connected(player, spellId, struck);\n        }", tick)
    test.assertEqual(1, rush.count("Combat::Connected("))
    connected = combat[combat.index("    void Connected(Player* player, std::uint32_t spellId, unsigned enemies)"):]
    test.assertIn("ItemPowers::Attack(player, spellId, enemies);", connected[:300])
    attack = powers[powers.index("    void Attack(Player* player, std::uint32_t spellId, unsigned enemies)"):]
    attack = attack[:attack.index("\n    }\n")]
    test.assertIn('Fire(player, "hit_spender", name, scale, nullptr, enemies);', attack)
    fire = powers[powers.index("        void Fire(Player* player, char const* event, std::string const& skill, double scale"):]
    read = fire.index('double const castCooldown = DC::Tunables::Get("monk", "won_khim_lau_cooldown_seconds");')
    test.assertLess(read, fire.index("std::lock_guard<std::mutex> lock(mutex);"))
    test.assertIn("situation.castCooldownSeconds = castCooldown;", fire[:fire.index("ItemPower::Fire(")])
    test.assertIn('else if (one.stat == "cast_skill")\n                    CastSkill(player, one.skill);', powers)
    cast = combat[combat.index("    bool CastSkill(Player* player, std::string const& skill, Unit* target)"):]
    test.assertIn("for (Classes::Slot const& slot : Classes::Bar(player))", cast[:400])
    test.assertIn("TRIGGERED_FULL_MASK", cast[:600])


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rush = (SRC / "classes/monk/dc_monk_tempest_rush.cpp").read_text(encoding="utf-8")
        cls.combat = (SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")

    def sources(self):
        return {"rush": self.rush, "combat": self.combat, "powers": self.powers}

    def test_a_tempest_rush_tick_is_a_spenders_hit_that_casts_cyclone_strike(self):
        hook_rules(self, **self.sources())

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "no_connected": ("rush", "            if (struck)\n                Combat::Connected(player, spellId, struck);\n", ""),
            "connected_per_enemy": ("rush", "                ++struck;\n", "                ++struck;\n                Combat::Connected(player, spellId, 1);\n"),
            "no_count": ("rush", "                ++struck;\n", ""),
            "the_tunable_unread": ("powers", "                situation.castCooldownSeconds = castCooldown;\n", ""),
            "the_cast_lost": ("powers", "                    CastSkill(player, one.skill);", "                    ;"),
            "connected_fires_no_item": ("combat", "        ItemPowers::Attack(player, spellId, enemies);\n", ""),
        }
        for name, (where, old, new) in mutants.items():
            sources = self.sources()
            self.assertEqual(1, sources[where].count(old), name)
            sources[where] = sources[where].replace(old, new)
            with self.subTest(name), self.assertRaises(AssertionError):
                hook_rules(self, **sources)


if __name__ == "__main__":
    unittest.main()

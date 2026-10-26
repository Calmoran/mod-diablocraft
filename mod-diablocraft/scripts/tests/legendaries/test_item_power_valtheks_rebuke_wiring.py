"""The source-text guards of valtheks rebuke: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_valtheks_rebuke.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_valtheks_rebuke import MODULE  # noqa: E402


TWISTER = MODULE / "src/classes/wizard/dc_wizard_energy_twister.cpp"


def start_failures(text):
    """What is wrong with EnergyTwister::Start in `text` (the source guards; [] when it is right)."""
    start = text.index("void Start(Player* player, uint32 id, Position const& center)")
    body = text[start:text.index("\n    }\n", start)]
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("straight is on while a straight_path source is worn (0 without it)",
         'bool const straight = ItemPowers::SkillSetTo(player, "Energy Twister", "straight_path", 0) > 0;' in body)
    need("the turn limit is 0 when straight, the tunable's otherwise",
         'double const limit = straight ? 0 : DC::Tunables::Get("wizard", "energy_twister_turn_limit_degrees");' in body)
    need("the path takes that limit", "twister.turnSeconds, limit, rolls);" in body)
    need("no fixed straight is left", "bool const straight = false;" not in body and "bool const straight = true;" not in body)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_start_takes_the_staff(self):
        self.assertEqual([], start_failures(TWISTER.read_text(encoding="utf-8")))

    def test_the_damage_term_reads_the_skill_of_the_shell(self):
        # the tick is Combat::StrikeArea(player, id, ...): the hit's skill is the shell row's, "Energy Twister" for the base skill and every rune,
        # and ComputeHit's legendary term multiplies its `damage_increase_pct` rows (dc_combat.cpp)
        text = TWISTER.read_text(encoding="utf-8")
        self.assertIn("Combat::StrikeArea(player, id, at, radius, pct, true);", text)
        combat = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct") * ItemPowers::DealtFactor(player)', combat)
        self.assertIn("std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;", combat)

    def test_the_source_guards_fail_their_mutants(self):
        real = TWISTER.read_text(encoding="utf-8")
        line = 'bool const straight = ItemPowers::SkillSetTo(player, "Energy Twister", "straight_path", 0) > 0;'
        mutants = {
            "never": (line, "bool const straight = false;"),
            "always": (line, "bool const straight = true;"),
            "base_one": ('"straight_path", 0) > 0;', '"straight_path", 1) > 0;'),
            "another_stat": ('"straight_path", 0) > 0;', '"jump_rehit", 0) > 0;'),
            "another_skill": ('SkillSetTo(player, "Energy Twister", "straight_path"', 'SkillSetTo(player, "Electrocute", "straight_path"'),
            "limit_ignores_it": ("double const limit = straight ? 0 :", "double const limit = false ? 0 :"),
            "limit_inverted": ("double const limit = straight ? 0 :", "double const limit = !straight ? 0 :"),
            "path_ignores_the_limit": ("twister.turnSeconds, limit, rolls);", "twister.turnSeconds, DC::Tunables::Get(\"wizard\", \"energy_twister_turn_limit_degrees\"), rolls);"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(start_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()

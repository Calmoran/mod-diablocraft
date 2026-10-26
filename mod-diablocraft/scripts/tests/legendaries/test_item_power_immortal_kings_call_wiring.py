"""The source-text guards of immortal kings call: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_immortal_kings_call.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source
from test_item_power_immortal_kings_call import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_hit_multiplies_the_dealt_factor_into_its_legendary_term(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct") * ItemPowers::DealtFactor(player) * CopyFactor();', combat)
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        dealt = powers[powers.index("double DealtFactor(Player const* player)"):powers.index("double PetSpeedFactor(")]
        self.assertIn('ItemPower::PlayerFactor(Data().rows, CountsOf(guid), "damage_dealt_pct", situation)', dealt)

    def test_the_two_skills_are_read_live_for_a_set_row(self):
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        # a skills_active row of any owner, a set's too, puts its skills in the watched list the situation looks at
        self.assertIn('if (row.cond == "skills_active")\n                            loaded.watched.insert(row.condSkills.begin(), row.condSkills.end());', powers)
        self.assertIn("if (SkillIsActive(player, skill))\n                    situation.active.insert(skill);", powers)
        abilities = barbarian_source.abilities((".cpp",))
        self.assertIn('if (skill == "Call of the Ancients")\n            return Classes::Ancients::Active(p);\n        return Buff(p, skill.c_str()) != nullptr;', abilities)
        self.assertIn('Buff(p, "Wrath of the Berserker")', abilities)


if __name__ == "__main__":
    unittest.main()

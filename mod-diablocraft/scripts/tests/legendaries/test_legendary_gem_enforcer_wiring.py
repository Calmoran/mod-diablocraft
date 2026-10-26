"""The source-text guards of legendary gem enforcer: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_legendary_gem_enforcer.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_legendary_gem_enforcer import MATH, SRC, enforcer_id, read_pets  # noqa: E402


class Hooks(unittest.TestCase):
    """Source guards: the call is there. The behaviour in game is docs/test-enforcer.md."""

    @classmethod
    def setUpClass(cls):
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.powers = (SRC / "combat/dc_gem_powers.cpp").read_text(encoding="utf-8")
        cls.header = (SRC / "combat/dc_gem_powers.h").read_text(encoding="utf-8")
        cls.ancients = (SRC / "classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8")

    def test_the_hit_formula_asks_for_the_pet_factor_in_step_8(self):
        self.assertIn("char const* petSkill = nullptr", (SRC / "combat/dc_combat.h").read_text(encoding="utf-8"))
        step8 = self.combat[self.combat.index("hit.standalone ="):]
        step8 = step8[:step8.index(";")]
        self.assertIn("GemPowers::PetFactor(player,", step8)

    def test_the_ancients_hits_name_their_skill_so_the_bonus_abilities_count(self):
        self.assertRegex(self.ancients, r"ComputeHit\(p, target, spell, hit, std::nullopt, false, [^;]*skill")

    def test_every_monster_hit_hook_gives_pets_their_reduction(self):
        # the swing, the spell and the periodic tick
        self.assertEqual(3, self.combat.count("GemPowers::PetIncoming(target"))

    def test_the_gem_code_names_no_skill_and_no_class_of_the_list(self):
        for path in (MATH, SRC / "combat/dc_gem_powers.cpp", SRC / "combat/dc_gem_powers.h"):
            text = path.read_text(encoding="utf-8")
            for r in read_pets():
                self.assertNotIn('"%s"' % r["skill"], text, "%s names %s" % (path.name, r["skill"]))
                self.assertNotIn('"%s"' % r["class"], text, "%s names %s" % (path.name, r["class"]))
            self.assertNotIn(enforcer_id(), text.replace('Enforcer = "%s"' % enforcer_id(), ""))

    def test_the_list_is_read_from_the_table_the_generator_makes(self):
        self.assertIn("dc_legendary_gem_pet", self.powers)
        self.assertRegex(self.header, r"PetFactor\(Player\*")
        self.assertRegex(self.header, r"PetIncoming\(Unit\*")


if __name__ == "__main__":
    unittest.main()

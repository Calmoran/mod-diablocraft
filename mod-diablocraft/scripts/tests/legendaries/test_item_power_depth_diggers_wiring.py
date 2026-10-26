"""The source-text guards of depth diggers: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_depth_diggers.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_depth_diggers import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_hit_reads_the_base_skill_name(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn('std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;', combat)
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', combat)


if __name__ == "__main__":
    unittest.main()

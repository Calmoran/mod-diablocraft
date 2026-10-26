"""The source-text guards of skull grasp: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_skull_grasp.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
from test_item_power_skull_grasp import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_hit_reads_the_base_skill_name(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn('std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;', combat)
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', combat)

    def test_a_whirlwind_tick_asks_compute_hit_for_each_target(self):
        abilities = barbarian_source.abilities((".cpp",))
        start = abilities.index("if(!PayWhirlwindTick(p,row->id,hand))")
        tick = abilities[start:abilities.index("Passives::Hit(p,target,row->id,hit.school);", start)]
        self.assertIn("ComputeHit(p,target,row->id,hit)", tick)
        self.assertIn("DealHit(p,target,row->id,hit)", tick)


if __name__ == "__main__":
    unittest.main()

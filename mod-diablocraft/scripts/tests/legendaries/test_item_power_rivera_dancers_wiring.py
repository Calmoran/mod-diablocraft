"""The source-text guards of rivera dancers: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_rivera_dancers.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_rivera_dancers import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_speed_reaches_the_swing_recovery_of_any_skill_with_a_shell(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        body = combat[combat.index("double HandAttacksPerSecond(Player* player, std::uint32_t spellId, bool offhand)"):]
        body = body[:body.index("\n    }\n")]
        self.assertIn("auto const ability = Shells::FindAbility(spellId);", body)
        self.assertIn('ItemPowers::SkillFactor(player, ability->skill, "attack_speed_pct")', body)
        recovery = combat[combat.index("std::uint32_t SwingRecoveryMilliseconds("):]
        self.assertIn("HandAttacksPerSecond(player, spellId, offhand)", recovery[:recovery.index("\n    }\n")])

    def test_the_damage_reaches_the_hit(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertRegex(combat, r'ItemPowers::SkillFactor\([^;]*"damage_increase_pct"\)')


if __name__ == "__main__":
    unittest.main()

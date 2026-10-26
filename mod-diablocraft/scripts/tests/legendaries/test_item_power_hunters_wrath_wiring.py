"""The source-text guards of hunters wrath: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_hunters_wrath.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_skill_swing_recovery import sql_rows
from test_item_power_hunters_wrath import MODULE, SRC, primaries  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_hit_and_the_swing_read_the_base_skill_name(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn('std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;', combat)
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', combat)
        speed = combat[combat.index("double HandAttacksPerSecond("):combat.index("std::pair<double, double> WeaponRange(")]
        self.assertIn('ItemPowers::SkillFactor(player, ability->skill, "attack_speed_pct")', speed)

    def test_a_primarys_swing_recovery_is_its_hands_attacks_per_second(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cooldown = combat[combat.index("std::uint32_t SkillCooldownMilliseconds("):combat.index("// C1: every skill WITHOUT")]
        self.assertIn("PrimaryData::Find(spellId)", cooldown)
        self.assertIn("HandAttacksPerSecond(player, spellId, offhand)", cooldown)

    def test_a_wizard_primary_states_no_cooldown_so_its_swing_recovery_is_the_speed_rows_target(self):
        # SwingEligible (dc_combat.cpp): a shell with no stated RecoveryTime / CategoryRecoveryTime gets one swing of recovery from
        # HandAttacksPerSecond, which is where attack_speed_pct is read (the Barbarian's primaries take PrimaryData's branch instead).
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        ids = {int(m[1]) for skill in primaries()[4:] for m in re.finditer(r'\{(\d+), "%s", "[^"]*", ' % re.escape(skill), shells)}
        self.assertGreaterEqual(len(ids), 4 * 5)       # each Wizard primary and its runes
        records = {int(r["ID"]): r for r in sql_rows((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"))}
        for spell in sorted(ids):
            self.assertEqual(("0", "0"), (records[spell]["RecoveryTime"], records[spell]["CategoryRecoveryTime"]), spell)
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        eligible = combat[combat.index("bool SwingEligible("):combat.index("// One swing at the attack speed")]
        self.assertIn("info->RecoveryTime || info->CategoryRecoveryTime", eligible)


if __name__ == "__main__":
    unittest.main()

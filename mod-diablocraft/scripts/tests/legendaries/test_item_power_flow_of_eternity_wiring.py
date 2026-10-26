"""The source-text guards of flow of eternity: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_flow_of_eternity.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_flow_of_eternity import MODULE  # noqa: E402


COMBAT = MODULE / "src/combat/dc_combat.cpp"


SEVEN = MODULE / "src/classes/monk/dc_monk_seven_sided_strike.cpp"


def reader_failures(combat, seven):
    """What is wrong with the paths Seven-Sided Strike's damage and cooldown take to the rules ([] when they are right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("ComputeHit's legendary term reads SkillFactor by the shell's skill",
         'std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;' in combat
         and re.search(r'hit\.legendary = ItemPowers::SkillFactor\(player, petName, "damage_increase_pct"\)', combat))
    need("every strike, Sudden Assault's area and Incinerate's burn deal through Combat::Strike or StrikeArea",
         seven.count("Combat::Strike(player, target, spellId, pct, true);") == 1 and "Combat::StrikeArea(player, id, target->GetPosition()" in seven
         and "else if (Combat::Strike(player, target, id))" in seven and "DealDamage" not in seven)
    need("the last strike starts the cooldown again through SkillCooldownMilliseconds (CooldownFactor's reader)",
         "Combat::SendSkillCooldown(player, id, Combat::SkillCooldownMilliseconds(player, id));" in seven)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_readers_reach_the_rules(self):
        self.assertEqual([], reader_failures(COMBAT.read_text(encoding="utf-8"), SEVEN.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        combat = COMBAT.read_text(encoding="utf-8")
        seven = SEVEN.read_text(encoding="utf-8")
        mutants = {
            "restart_at_the_base": (SEVEN, "Combat::SendSkillCooldown(player, id, Combat::SkillCooldownMilliseconds(player, id));",
                                    "Combat::SendSkillCooldown(player, id, std::uint32_t(Numbers::Num(id, \"cooldown_seconds\") * 1000));"),
            "burn_dealt_directly": (SEVEN, "Combat::Strike(player, target, spellId, pct, true);", "player->DealDamage(player, target, 1);"),
            "the_area_not_struck": (SEVEN, "Combat::StrikeArea(player, id, target->GetPosition()", "Combat::Enemies(player, id, target->GetPosition()"),
            "no_legendary_term": (COMBAT, 'hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")',
                                  'hit.legendary = ItemPowers::SkillFactor(player, "", "damage_increase_pct")'),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                text = combat if where == COMBAT else seven
                self.assertEqual(1, text.count(old), name + " does not apply once")
                mutated = text.replace(old, new)
                self.assertTrue(reader_failures(mutated if where == COMBAT else combat, mutated if where == SEVEN else seven), name + " survived")


if __name__ == "__main__":
    unittest.main()

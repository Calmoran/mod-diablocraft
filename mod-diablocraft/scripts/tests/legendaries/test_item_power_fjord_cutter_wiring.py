"""The source-text guards of fjord cutter: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_fjord_cutter.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_fjord_cutter import MODULE  # noqa: E402


COMBAT = MODULE / "src/combat/dc_combat.cpp"


POWERS = item_powers_source.CPP


def reader_failures(combat, powers):
    """What is wrong with the two readers of the target state (the source guards; [] when they are right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    compute = combat[combat.index("bool ComputeHit("):combat.index("std::string Hit::Describe()")]
    read = "hit.legendary *= ItemPowers::TargetFactor(player, target, petName);"
    need("ComputeHit multiplies the legendary term by the target's factor, with the hit's target", read in compute)
    need("once, after the term is set", read in compute and compute.index('hit.legendary = ItemPowers::SkillFactor(') < compute.index(read))
    need("nothing else reads it", combat.count("ItemPowers::TargetFactor(") == 1)
    reader = powers[powers.index("double TargetFactor(Player const* player, Unit const* target, std::string const& skill)"):]
    reader = reader[:reader.index("\n    }\n")]
    slow = "unsigned const states = target->GetMaxNegativeAuraModifier(SPELL_AURA_MOD_DECREASE_SPEED) < 0 ? ItemPower::TargetSlowed : 0u;"
    need("the target is slowed by its strongest slow below 0", slow in reader)
    need("no target, no factor", "if (!player || !target)\n            return 1.0;" in reader)
    need("the state is read before the lock", slow in reader and reader.index(slow) < reader.index("std::lock_guard<std::mutex> lock(mutex);"))
    need("the situation carries the state", "situation.targetControl = states;" in reader)
    need("the reader is the rule over the player's rows with that state",
         "return ItemPower::TargetFactor(Data().rows, CountsOf(guid), skill, situation);" in reader)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_readers_read_the_target(self):
        self.assertEqual([], reader_failures(COMBAT.read_text(encoding="utf-8"), POWERS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        combat = COMBAT.read_text(encoding="utf-8")
        powers = POWERS.read_text(encoding="utf-8")
        mutants = {
            "not_in_the_hit": (COMBAT, "        hit.legendary *= ItemPowers::TargetFactor(player, target, petName); // Fjord Cutter: by the target's state (N-TCTRL)\n", ""),
            "no_target": (COMBAT, "ItemPowers::TargetFactor(player, target, petName)", "ItemPowers::TargetFactor(player, nullptr, petName)"),
            "any_aura": (POWERS, "target->GetMaxNegativeAuraModifier(SPELL_AURA_MOD_DECREASE_SPEED) < 0", "target->GetMaxNegativeAuraModifier(SPELL_AURA_MOD_STUN) < 0"),
            "a_speed_up_counts": (POWERS, "GetMaxNegativeAuraModifier(SPELL_AURA_MOD_DECREASE_SPEED) < 0", "GetMaxNegativeAuraModifier(SPELL_AURA_MOD_DECREASE_SPEED) <= 0"),
            "state_dropped": (POWERS, "        situation.targetControl = states;\n", "        (void)states;\n"),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                text = combat if where == COMBAT else powers
                self.assertEqual(1, text.count(old), name + " does not apply once")
                mutated = text.replace(old, new)
                self.assertTrue(reader_failures(mutated if where == COMBAT else combat, mutated if where == POWERS else powers), name + " survived")


if __name__ == "__main__":
    unittest.main()

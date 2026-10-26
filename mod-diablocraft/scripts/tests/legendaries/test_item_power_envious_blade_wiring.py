"""The source-text guards of envious blade: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_envious_blade.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_envious_blade import SRC  # noqa: E402


POWERS = item_powers_source.CPP


POWERS_H = SRC / "combat/dc_item_powers.h"


COMBAT = SRC / "combat/dc_combat.cpp"


def crit_bonus(source=None):
    """ItemPowers::CritBonus's body, as written or as a mutant's."""
    text = POWERS.read_text(encoding="utf-8") if source is None else source
    body = text[text.index("double CritBonus("):]
    return body[:body.index("\n    }\n") + 7]


class Hooks(unittest.TestCase):
    def check(self, combat=None, powers=None, header=None):
        """The guards on the text of ComputeHit's crit sum and ItemPowers::CritBonus; raises AssertionError on a mutant."""
        combat = COMBAT.read_text(encoding="utf-8") if combat is None else combat
        powers = POWERS.read_text(encoding="utf-8") if powers is None else powers
        header = POWERS_H.read_text(encoding="utf-8") if header is None else header
        chc = next(line for line in combat.splitlines() if "double const chc = std::clamp(" in line)
        assert chc.count("ItemPowers::CritBonus(player, target)") == 1, "ComputeHit sums the item powers' crit bonus into the chance once"
        assert chc.index("ItemPowers::CritBonus") < chc.index("/ 100.0, 0.0, 1.0)"), "the bonus is inside the clamp, so more than certain is certain"
        assert combat.count("ItemPowers::CritBonus(") == 1, "nothing else reads it"
        body = crit_bonus(powers)
        assert "!player || !target" in body, "no player or no target gives nothing"
        assert re.search(r"double const life = target->GetMaxHealth\(\) \? 100\.0 \* target->GetHealth\(\) / target->GetMaxHealth\(\) : -1\.0;", body), "the target's Life percent of its maximum, -1 with none"
        assert body.index("double const life") < body.index("lock_guard"), "the Life is read before the lock"
        assert "seen.targetLifePct = life;" in body and body.index("lock_guard") < body.index("seen.targetLifePct = life;") < body.index("PlayerSum"), "handed to the situation before the rows are summed"
        assert re.search(r'ItemPower::PlayerSum\(Data\(\)\.rows, CountsOf\(guid\), "crit_chance_pct", SituationOf\(guid, std::move\(seen\)\)\)', body), "the sum of the rows"
        assert re.search(r"double CritBonus\(Player const\*, Unit const\* target\);", header), "declared"

    def test_the_crit_chance_takes_the_bonus_and_the_target_life_reaches_the_situation(self):
        self.check()

    def test_the_guards_fail_their_mutants(self):
        combat = COMBAT.read_text(encoding="utf-8")
        powers = POWERS.read_text(encoding="utf-8")
        header = POWERS_H.read_text(encoding="utf-8")
        mutants = {
            "not_in_the_chance": dict(combat=combat.replace("+ItemPowers::CritBonus(player, target)", "")),
            "read_twice": dict(combat=combat.replace("+ItemPowers::CritBonus(player, target)", "+ItemPowers::CritBonus(player, target)+ItemPowers::CritBonus(player, target)", 1)),
            "outside_the_clamp": dict(combat=combat.replace("+ItemPowers::CritBonus(player, target)", "").replace(
                ") / 100.0, 0.0, 1.0);", ") / 100.0, 0.0, 1.0) + ItemPowers::CritBonus(player, target) / 100.0;", 1)),
            "no_target_check": dict(powers=powers.replace("double CritBonus(Player const* player, Unit const* target)\n    {\n        if (!player || !target)", "double CritBonus(Player const* player, Unit const* target)\n    {\n        if (!player)", 1)),
            "life_not_a_percent": dict(powers=powers.replace("100.0 * target->GetHealth() / target->GetMaxHealth()", "1.0 * target->GetHealth() / target->GetMaxHealth()", 1)),
            "life_never_handed_over": dict(powers=powers.replace("        seen.targetLifePct = life;\n", "", 1)),
            "life_read_after_the_lock": dict(powers=powers.replace("        double const life = target->GetMaxHealth() ? 100.0 * target->GetHealth() / target->GetMaxHealth() : -1.0;\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n",
                                                                   "        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        double const life = target->GetMaxHealth() ? 100.0 * target->GetHealth() / target->GetMaxHealth() : -1.0;\n", 1)),
            "other_stat": dict(powers=powers.replace('CountsOf(guid), "crit_chance_pct"', 'CountsOf(guid), "damage_dealt_pct"', 1)),
            "undeclared": dict(header=header.replace("double CritBonus(Player const*, Unit const* target);", "", 1)),
        }
        for name, edit in mutants.items():
            with self.subTest(mutant=name):
                before = dict(combat=combat, powers=powers, header=header)
                self.assertNotEqual(before, {**before, **edit}, name + " did not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    self.check(**edit)


if __name__ == "__main__":
    unittest.main()

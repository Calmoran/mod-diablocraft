"""The source-text guards of lornelles sunstone: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_lornelles_sunstone.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_lornelles_sunstone import MATH, SRC  # noqa: E402


POWERS = item_powers_source.CPP_WITH_HEADER


COMBAT = SRC / "combat/dc_combat.cpp"


def body_of(text, signature):
    """A function's body as written: from `signature` to its closing brace at four spaces."""
    body = text[text.index(signature):]
    return body[:body.index("\n    }\n") + 7]


class Hooks(unittest.TestCase):
    def check(self, powers=None, combat=None, math=None):
        """The guards on how the Life reaches the rule: read when the number is read, never kept, before the hit lands; raises AssertionError on a mutant."""
        powers = POWERS.read_text(encoding="utf-8") if powers is None else powers
        combat = COMBAT.read_text(encoding="utf-8") if combat is None else combat
        math = MATH.read_text(encoding="utf-8") if math is None else math
        # Seen: the Life is read from the player's current and maximum Life, only when a row has the condition, and it starts the early return's test
        seen = body_of(powers, "ItemPower::Situation Seen(Player const* player)")
        assert "if (Data().watched.empty() && !Data().resource && !Data().life && !Data().moves)" in seen, "Seen does not stop early when a row reads the Life"
        assert re.search(r"if \(Data\(\)\.life && player->GetMaxHealth\(\)\)\s+situation\.lifePct = 100\.0 \* player->GetHealth\(\) / player->GetMaxHealth\(\);", seen), \
            "Seen takes the Life percent of the maximum, live"
        assert seen.index("situation.lifePct") > seen.index("lock_guard") and seen.rindex("return situation;") > seen.index("situation.lifePct"), "after the early return"
        assert 'loaded.life = loaded.life || row.cond == "life_missing" || row.cond == "own_life_below";' in powers, "the table notes that a row reads the Life"
        # kept nowhere: the Life percent is assigned once in the whole file, in Seen (not in the clocks, the worn values or any state)
        assert powers.count("lifePct") == 1 and powers.count("situation.lifePct =") == 1, "the Life is assigned once, in Seen"
        # the damage taken reads it per hit: IncomingFactor takes a fresh Seen and ReductionFactor reads the rows with it
        incoming = body_of(powers, "double IncomingFactor(Player const* player)")
        assert "ItemPower::Situation seen = Seen(player);" in incoming, "a fresh read of the player each time"
        assert "SituationOf(guid, std::move(seen))" in incoming, "the read reaches the situation"
        assert "ItemPower::ReductionFactor(Data().rows, CountsOf(guid), situation)" in incoming, "the reduction rows are read with it"
        # and it is asked for each hit before the hit lands, in both places that fold the player's damage taken
        mitigate = body_of(combat, "std::optional<double> Mitigate(")
        assert "ItemPowers::IncomingFactor(victim->ToPlayer())" in mitigate, "Mitigate asks for the factor of this hit"
        assert mitigate.index("ItemPowers::IncomingFactor(") < mitigate.index("ItemPowers::Hurt("), "before the hit is counted as taken"
        assert "ItemPowers::IncomingFactor(victim->ToPlayer())" in body_of(combat, "std::optional<double> DamageTakenFactor("), "the other fold of the factor reads it too"
        # the rule: the condition and its scale are one place each
        assert math.count('"life_missing"') == 2, "Holds and Counted are the readers of the condition"

    def test_the_life_is_read_when_the_number_is_read(self):
        self.check()

    def test_the_guards_fail_their_mutants(self):
        powers = POWERS.read_text(encoding="utf-8")
        combat = COMBAT.read_text(encoding="utf-8")
        math = MATH.read_text(encoding="utf-8")
        read = "                situation.lifePct = 100.0 * player->GetHealth() / player->GetMaxHealth();"
        mutants = {
            "no_early_return_test": dict(powers=powers.replace("&& !Data().resource && !Data().life && !Data().moves)", "&& !Data().resource && !Data().moves)", 1)),
            "life_not_a_percent": dict(powers=powers.replace("100.0 * player->GetHealth() / player->GetMaxHealth()", "1.0 * player->GetHealth() / player->GetMaxHealth()", 1)),
            "life_of_the_maximum_only": dict(powers=powers.replace("100.0 * player->GetHealth() / player->GetMaxHealth()", "100.0 * player->GetMaxHealth() / player->GetMaxHealth()", 1)),
            "life_read_always": dict(powers=powers.replace("if (Data().life && player->GetMaxHealth())", "if (player->GetMaxHealth())", 1)),
            "life_never_read": dict(powers=powers.replace(read, "", 1)),
            "life_kept_in_the_clock": dict(powers=powers.replace("bool hurt = false;\n        std::uint32_t lastHurt = 0;", "bool hurt = false;\n        double lifePct = 100;\n        std::uint32_t lastHurt = 0;", 1)),
            "life_assigned_a_second_time": dict(powers=powers.replace("            return situation;\n        }\n\n        // What a condition reads, for one player now", "            situation.lifePct = 100.0;\n            return situation;\n        }\n\n        // What a condition reads, for one player now", 1)),
            "flag_not_set": dict(powers=powers.replace('loaded.life = loaded.life || row.cond == "life_missing" || row.cond == "own_life_below";', "", 1)),
            "incoming_without_a_fresh_read": dict(powers=powers.replace("std::map<std::string, unsigned> const stacks = BuffStacks(player);\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        ItemPower::Situation const situation = SituationOf(guid, std::move(seen));\n        return ItemPower::PlayerFactor(Data().rows, CountsOf(guid), \"damage_taken_pct\"",
                                                                    "std::map<std::string, unsigned> const stacks = BuffStacks(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        ItemPower::Situation const situation = SituationOf(guid);\n        return ItemPower::PlayerFactor(Data().rows, CountsOf(guid), \"damage_taken_pct\"", 1)),
            "reduction_rows_not_read": dict(powers=powers.replace("               ItemPower::ReductionFactor(Data().rows, CountsOf(guid), situation) *\n", "", 1)),
            "mitigate_asks_after_the_hit": dict(combat=combat.replace("ItemPowers::IncomingFactor(victim->ToPlayer()) * Monk::TakenFactor(victim) * Shaman::TakenFactor(victim);\n        // Elite", "Monk::TakenFactor(victim) * Shaman::TakenFactor(victim);\n        // Elite", 1)),
            "a_second_reader_of_the_condition": dict(math=math + '\n// "life_missing" "life_missing"\n'),
        }
        for name, edit in mutants.items():
            with self.subTest(mutant=name):
                before = dict(powers=powers, combat=combat, math=math)
                self.assertNotEqual(before, {**before, **edit}, name + " did not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    self.check(**edit)


if __name__ == "__main__":
    unittest.main()

"""The source-text guards of binding of the lost: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_binding_of_the_lost.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_binding_of_the_lost import SRC  # noqa: E402


def cap_guard(text):
    cap = text[text.index("unsigned StackCap(ItemPower::Row const& row)"):]
    cap = cap[:cap.index("\n        }\n")]
    assert 'row.owner == "P61_Unique_Belt_03"' in cap, "the belt's own cap"
    assert 'DC::Tunables::Has("monk", "binding_of_the_lost_max_stacks")' in cap, "unset: the row's"
    assert 'DC::Tunables::Get("monk", "binding_of_the_lost_max_stacks"), 0.0, 255.0' in cap, "the tunable, within an aura's 255"
    assert "return row.stackMax;" in cap, "every other power: its row"
    stack = text[text.index("void StackBuff(Player* player, ItemPower::Row const& row, double add)"):]
    assert "ItemPower::Stacked(held, add, StackCap(row))" in stack[:stack.index("\n        }\n")], "the stacks are capped by it"


class Hooks(unittest.TestCase):
    def test_the_cap_is_read_where_the_stacks_are_added(self):
        cap_guard(item_powers_source.CPP.read_text(encoding="utf-8"))

    def test_the_source_mutants_fail_the_guard(self):
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        for name, (old, new) in {
            "another_owner": ('row.owner == "P61_Unique_Belt_03"', 'row.owner == "P61_Unique_Orb_004"'),
            "no_tunable": ('DC::Tunables::Get("monk", "binding_of_the_lost_max_stacks"), 0.0, 255.0', "0.0, 0.0, 255.0"),
            "the_row_ignored": ("ItemPower::Stacked(held, add, StackCap(row))", "ItemPower::Stacked(held, add, row.stackMax)"),
        }.items():
            with self.subTest(mutant=name):
                self.assertIn(old, text, name + " does not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    cap_guard(text.replace(old, new, 1))

    def test_a_seven_sided_strike_hit_reaches_the_hit_event(self):
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        hit = powers[powers.index("void Hit(Player* player, Unit* target, std::uint32_t spellId)"):powers.index("void Attack(Player* player")]
        self.assertIn('Fire(player, "hit", name, scale, target);', hit)
        self.assertIn("Combat::Strike(player, target, id)", (SRC / "classes/monk/dc_monk_seven_sided_strike.cpp").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

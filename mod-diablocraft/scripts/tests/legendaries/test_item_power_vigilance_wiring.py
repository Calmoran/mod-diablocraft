"""The source-text guards of vigilance: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_vigilance.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_vigilance import SRC  # noqa: E402


def taken_guard(powers, passives):
    """A monster's hit on the player reaches `taken` at proc coefficient 1, and a fired cast_skill casts the skill."""
    body = powers[powers.index("void Taken(Player* player)"):]
    body = body[:body.index("\n    }\n")]
    assert 'Fire(player, "taken", "", 1.0);' in body, "taken at proc coefficient 1"
    taken = passives[passives.index("void Taken(Player* p, unsigned school, bool ranged, double damage)"):]
    assert "ItemPowers::Taken(p);" in taken[:taken.index("\n    }\n")], "the passives' taken reaches the item powers"
    assert 'one.stat == "cast_skill"' in powers and "CastSkill(player, one.skill)" in powers, "the effect casts the skill"


class Hooks(unittest.TestCase):
    def test_a_hit_taken_reaches_the_event_and_the_cast(self):
        taken_guard(item_powers_source.CPP.read_text(encoding="utf-8"), (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8"))

    def test_the_source_mutants_fail_the_guard(self):
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        passives = (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8")
        for name, (old, new, where) in {
            "scaled_by_nothing": ('Fire(player, "taken", "", 1.0);', 'Fire(player, "taken", "", 0.0);', "powers"),
            "another_event": ('Fire(player, "taken", "", 1.0);', 'Fire(player, "hit", "", 1.0);', "powers"),
            "effect_not_cast": ("CastSkill(player, one.skill);", ";", "powers"),
            "passives_skip": ("        ItemPowers::Taken(p);\n", "", "passives"),
        }.items():
            with self.subTest(mutant=name):
                text = powers if where == "powers" else passives
                self.assertIn(old, text, name + " does not apply")
                text = text.replace(old, new, 1)
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    taken_guard(text if where == "powers" else powers, text if where == "passives" else passives)


if __name__ == "__main__":
    unittest.main()

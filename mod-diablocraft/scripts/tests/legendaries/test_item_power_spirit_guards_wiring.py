"""The source-text guards of spirit guards: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_spirit_guards.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_spirit_guards import SKILLS, SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def text(self, path):
        return (SRC / path).read_text(encoding="utf-8")

    def test_a_cast_of_a_monk_primary_reaches_the_cast_event(self):
        combat = self.text("combat/dc_combat.cpp")
        body = combat[combat.index("void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override"):]
        body = body[:body.index("void OnSpellCheckCast")]
        self.assertIn("auto row = Shells::FindAbility(info->Id);", body)
        self.assertIn("if (player && row && !spell->IsTriggered())", body)
        self.assertIn("ItemPowers::Cast(player, info->Id);", body)
        powers = item_powers_source.text()
        cast = powers[powers.index("void Cast(Player* player, std::uint32_t spellId)"):]
        cast = cast[:cast.index("\n    }\n")]
        self.assertIn('Fire(player, "cast", skill->skill, 1.0);', cast)
        # the four primaries have shell rows, so FindAbility answers for them (a rune answers with its skill)
        shells = self.text("combat/dc_spell_shells.h")
        for skill in SKILLS:
            self.assertIn('"%s"' % skill, shells)


if __name__ == "__main__":
    unittest.main()

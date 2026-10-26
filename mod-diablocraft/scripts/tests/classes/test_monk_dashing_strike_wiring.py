"""The source-text guards of monk dashing strike: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_dashing_strike.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_dashing_strike import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def test_the_monk_hands_dashing_strike_over_first(self):
        monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        for function, call in (("std::optional<double> BasePct(std::uint32_t spellId)\n    {",
                                "if (DashingStrike::Is(spellId))\n            return DashingStrike::BasePct(spellId);"),
                               ("void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Punch const& punch)\n    {",
                                "if (DashingStrike::Is(spellId))\n            return DashingStrike::Cast(player, spellId, targets);")):
            at = monk.index(function) + len(function)
            # no early return of another skill's comes before it (Deadly Reach's Spent and the Mantras' starter are
            # not returns: they may come first)
            self.assertIn(call, monk[at:at + 1500], function)
            # what comes before is another skill's own guarded dispatch (`if (X::Is(spellId))` then its return: it
            # cannot take a Dashing Strike id) or a call that returns nothing
            allowed = re.compile(r"\s*(if \(\w+::Is\(spellId\)\)|return \w+::\w+\(.*\);|\w+::\w+\(player(, spellId)?\);)")
            for line in monk[at:monk.index(call, at)].strip().splitlines():
                self.assertRegex(line, allowed, monk[at:at + 300])

    def test_the_cast_path_calls_the_monk_whatever_it_hit(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        at = combat.index("            Monk::Cast(player, shell.spellId, targets, punch);")
        self.assertNotIn("if", combat[combat.rindex("\n", 0, at - 1):at])

    def test_both_dodge_rolls_read_blinding_speed(self):
        # The melee roll (the attack table's dodge chance) and the spell roll: each adds the Monk's chance to the
        # Barbarian's, and they are the only two places Abilities::DodgeChance is rolled.
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertIn("int32((Abilities::DodgeChance(defender) + Monk::Dodge(defender)) * 100)", combat)
        self.assertIn("roll_chance_f(float(Abilities::DodgeChance(player) + Monk::Dodge(player)))", combat)
        self.assertEqual(combat.count("Abilities::DodgeChance("), 2)
        self.assertEqual(combat.count("Monk::Dodge("), 2)
        monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.assertIn("return DashingStrike::Dodge(unit) + Salvation::Dodge(unit) + Passives242::Dodge(unit);", monk)  # the one sum
        glue = (MODULE / "src/classes/monk/dc_monk_dashing_strike.cpp").read_text(encoding="utf-8")
        self.assertIn("return found == states.end() ? 0 : found->second.dodge.Total(Now());", glue)

    def test_every_rune_dashes_for_the_skills_damage(self):
        glue = (MODULE / "src/classes/monk/dc_monk_dashing_strike.cpp").read_text(encoding="utf-8")
        self.assertIn('return Numbers::Own(SkillId(), "damage_pct");', glue)
        for rune in ("Barrage", "Way of the Falling Star", "Radiance", "Blinding Speed"):
            self.assertIn(f'rune == "{rune}"', glue)


if __name__ == "__main__":
    unittest.main()

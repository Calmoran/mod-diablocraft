"""The source-text guards of monk tempest rush: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_tempest_rush.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_tempest_rush import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.cast = (MODULE / "src/classes/monk/dc_monk_tempest_rush.cpp").read_text(encoding="utf-8")

    def test_the_monk_hands_tempest_rush_to_its_own_file(self):
        self.assertIn("return TempestRush::BasePct(spellId);", self.monk)
        self.assertIn("return TempestRush::Begin(player, spellId);", self.monk)
        self.assertIn("return TempestRush::Cast(player, spellId);", self.monk)
        self.assertIn("return TempestRush::Toggle(player, spellId);", self.monk)

    def test_a_second_press_is_refused_beside_whirlwinds(self):
        self.assertIn("Monk::Toggle(player, spell->GetSpellInfo()->Id)", self.combat)
        toggle = self.combat.index("Monk::Toggle(player, spell->GetSpellInfo()->Id)")
        whirlwind = self.combat.index("Abilities::Toggle(player, spell->GetSpellInfo()->Id)")
        self.assertLess(abs(toggle - whirlwind), 1500)
        self.assertIn("SPELL_FAILED_DONT_REPORT", self.combat[toggle:toggle + 200])

    def test_the_press_pays_one_second_and_the_ticks_pay_after_it(self):
        self.assertIn("run.prepaid.Press(run.start, 1000);", self.cast)
        self.assertIn("prepaid.Covers(Now())", self.cast)

    def test_the_knockback_is_the_skills_not_bluster_s(self):
        knock = self.cast.index('Abilities::Knockback(player, enemy, Tune("tempest_rush_knockback_yards"))')
        bluster = self.cast.index('IsRune(spellId, "Bluster")')
        self.assertLess(knock, bluster)

    def test_the_channel_ends_on_the_empty_pool_and_on_death(self):
        self.assertIn("< std::uint32_t(units)", self.cast)
        self.assertIn("!player->IsAlive()", self.cast)


if __name__ == "__main__":
    unittest.main()

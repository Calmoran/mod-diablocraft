"""The source-text guards of monk effects: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_effects.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
from test_monk_effects import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

    def test_the_hit_reads_the_monks_bonuses_beside_the_wizards(self):
        self.assertEqual(self.combat.count("Monk::TargetBonus(player, target)"), 2)  # the hit and the periodic snapshot
        self.assertEqual(self.combat.count("Monk::DamageBonus(player, target, shell.spellId)"), 1)
        # the Wizard's sit in the same two sums
        self.assertEqual(self.combat.count("Wizard::TargetBonus(player, target, hit.school)"), 2)

    def test_every_incoming_factor_site_of_the_wizard_has_the_monks(self):
        wizard = self.combat.count("Wizard::IncomingFactor(attacker)")
        self.assertEqual(wizard, 4)
        self.assertEqual(self.combat.count("Wizard::IncomingFactor(attacker) * Monk::IncomingFactor(attacker)"), wizard)

    def test_the_snapshot_and_the_hit_add_the_same_terms(self):
        hit = self.combat.index("hit.targetBonus = Primaries::TargetBonus(target)")
        snapshot = self.combat.index("return hit.total * (hit.additive + (Primaries::TargetBonus(target)")
        for text in (self.combat[hit:hit + 400], self.combat[snapshot:snapshot + 500]):
            for term in ("Primaries::TargetBonus(target)", "Abilities::TargetBonus(target)",
                         "Wizard::TargetBonus(player, target, hit.school)", "Monk::TargetBonus(player, target)"):
                self.assertIn(term, text)

    def test_the_monk_is_not_named_in_other_shared_files(self):
        self.assertNotIn("Monk", barbarian_source.abilities())
        for path in (MODULE / "src/combat/dc_passives.cpp", barbarian_source.PASSIVES, MODULE / "src/classes/barbarian/dc_barbarian_primaries.cpp"):
            self.assertNotIn("Monk", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()

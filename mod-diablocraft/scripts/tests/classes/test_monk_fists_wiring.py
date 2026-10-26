"""The source-text guards of monk fists: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_fists.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
from test_monk_fists import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

    def test_the_cast_path_asks_the_monk(self):
        self.assertEqual(self.combat.count("Monk::Begin(player, shell.spellId,"), 1)
        self.assertIn("ResolveHit(player, target, punch.pct ? punched : shell, info)", self.combat)
        self.assertIn("Monk::Cast(player, shell.spellId, targets, punch);", self.combat)
        # Begin before the hits, Cast after them
        order = [self.combat.index(m) for m in ("Monk::Begin(", "ResolveHit(player, target, punch.pct", "Monk::Cast(")]
        self.assertEqual(order, sorted(order))

    def test_both_hit_paths_tell_the_monk(self):
        self.assertEqual(self.combat.count("Monk::Landed(player, target, shell.spellId);"), 1)
        self.assertEqual(self.combat.count("Monk::Landed(player, target, spellId);"), 1)

    def test_the_loader_asks_for_the_punch(self):
        self.assertIn("if (auto monk = Monk::BasePct(ability.id))", self.combat)

    def test_the_monk_is_not_named_in_the_barbarians_file(self):
        self.assertNotIn("Monk", barbarian_source.abilities())


if __name__ == "__main__":
    unittest.main()

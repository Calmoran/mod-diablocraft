"""The source-text guards of monk mantra of conviction: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_mantra_of_conviction.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_mantra_of_conviction import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")

    def body(self, signature):
        start = self.monk.index(signature)
        return self.monk[start:self.monk.index("\n    }\n", start)]

    def test_the_activation_reaches_conviction(self):
        body = self.body("void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets")
        self.assertLess(body.index("if (Conviction::Is(spellId))\n            return Conviction::Cast(player, spellId, targets);"),
                        body.index("FistsOf(spellId)"))

    def test_every_landed_hit_reaches_conviction(self):
        body = self.body("void Landed(Player* player, Unit* target, std::uint32_t spellId)")
        call = body.index("Conviction::Landed(player, target, spellId);")
        self.assertEqual(body.count("return", 0, call), 1)  # only the null guard comes before it


if __name__ == "__main__":
    unittest.main()

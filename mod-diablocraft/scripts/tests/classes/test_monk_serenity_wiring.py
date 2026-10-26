"""The source-text guards of monk serenity: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_serenity.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_serenity import D3, MODULE, SKILL, read, tunables  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.cpp = (MODULE / "src/classes/monk/dc_monk_serenity.cpp").read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")

    def test_every_name_the_code_reads_exists(self):
        names = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', self.cpp))
        self.assertEqual(names, {n for n in tunables() if n.startswith("serenity_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\(spellId, "([a-z_]+)"', self.cpp))
        self.assertEqual(tokens - {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}, set())

    def test_the_monk_dispatches_the_cast(self):
        self.assertEqual(self.monk.count("if (Serenity::Is(spellId))\n            return Serenity::Cast(player, spellId);"), 1)

    def test_the_health_globe_share_is_not_invented(self):
        # no Health Globe Healing Bonus stat exists yet: the sheet's healing_bonus_share_pct is not read
        self.assertNotIn("healing_bonus_share_pct", re.sub(r"//.*", "", self.cpp))

    def test_the_stat_sheet_is_not_touched(self):
        # a Temporary contribution is saved with the character; the shield is an aura and a mechanic immunity instead
        self.assertNotIn("AddContribution", self.cpp)


if __name__ == "__main__":
    unittest.main()

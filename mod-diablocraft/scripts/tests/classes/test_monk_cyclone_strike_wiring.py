"""The source-text guards of monk cyclone strike: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_cyclone_strike.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_cyclone_strike import D3, MODULE, SKILL, read, tunables  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.cpp = (MODULE / "src/classes/monk/dc_monk_cyclone_strike.cpp").read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

    def test_every_name_the_code_reads_exists(self):
        names = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', self.cpp))
        self.assertEqual(names, {n for n in tunables() if n.startswith("cyclone_strike_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\(spellId, "([a-z_]+)"', self.cpp))
        self.assertEqual(tokens - {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}, set())

    def test_the_cast_path_aims_before_it_begins(self):
        self.assertEqual(self.combat.count("Monk::Aim(player, shell.spellId, targets, explicitTarget);"), 1)
        order = [self.combat.index(m) for m in ("Monk::Aim(", "Monk::Begin(", "Monk::Cast(")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(self.monk.count("CycloneStrike::Aim(player, spellId, targets);"), 1)
        self.assertEqual(self.monk.count("CycloneStrike::Cast(player, spellId);"), 1)

    def test_the_health_globe_bonus_is_not_invented(self):
        # no Health Globe Healing Bonus stat exists yet: the share is not read, and the heal is the sheet's heal_life only
        self.assertNotIn("healing_bonus_share_pct", re.sub(r"//.*", "", self.cpp))


if __name__ == "__main__":
    unittest.main()

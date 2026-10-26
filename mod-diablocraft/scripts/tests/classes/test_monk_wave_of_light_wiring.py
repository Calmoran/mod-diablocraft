"""The source-text guards of monk wave of light: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_wave_of_light.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_wave_of_light import D3, MODULE, SKILL, read, tunables  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.cpp = (MODULE / "src/classes/monk/dc_monk_wave_of_light.cpp").read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

    def test_every_name_the_code_reads_exists(self):
        names = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', self.cpp))
        names |= set(re.findall(r'Tunables::Has\("monk", "([a-z0-9_]+)"\)', self.cpp))
        self.assertEqual(names, {n for n in tunables() if n.startswith("wave_of_light_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|BaseId\(\)), "([a-z_]+)"', self.cpp))
        self.assertEqual(tokens - {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}, set())

    def test_the_cast_path_tells_the_monk_the_ground_point(self):
        self.assertEqual(self.combat.count("Monk::Ground(player, shell.spellId, center);"), 1)
        order = [self.combat.index(m) for m in ("Monk::Cast(player, shell.spellId", "Monk::Ground(")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(self.monk.count("WaveOfLight::Cast(player, spellId, aimed);"), 1)

    def test_only_the_third_party_records_are_untouched(self):
        # the donors stay (monk_visuals.csv): this bead changes no record
        self.assertNotIn("Exorcism", self.cpp)


if __name__ == "__main__":
    unittest.main()

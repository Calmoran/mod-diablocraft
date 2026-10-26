"""The source-text guards of monk sweeping wind: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_sweeping_wind.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
from test_monk_sweeping_wind import CODE, MODULE, SKILL  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = CODE.read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

    def test_the_monk_hands_the_skill_over(self):
        self.assertIn("return Wind::BasePct(spellId);", self.monk)
        self.assertIn("return Wind::Cast(player, spellId);", self.monk)
        self.assertIn("Wind::Landed(player);", self.monk)
        self.assertIn("Wind::Attack(player, generated && *generated > 0);", self.monk)

    def test_the_stacks_come_from_the_spirit_generators_connected_hook_and_no_shared_file_changes(self):
        # Monk::Connected is called once per attack by Combat::Connected (dc_combat.cpp, unchanged by this bead): the
        # primaries' generated_resource rows are what mark a Spirit Generator.
        self.assertIn("Wind::Attack(", self.monk)
        # Way of the Hundred Fists' Monk::Critical hook is on the branch now: the stacks must not hang on it.
        self.assertNotIn("Wind::Critical", self.monk)
        self.assertNotIn("Critical", self.code)
        self.assertIn("Monk::Connected(player, spellId);", self.combat)

    def test_the_runes_do_what_their_sentence_says(self):
        self.assertIn('IsRune(spellId, "Inner Storm") && PaysSpirit(index, tick)', self.code)
        self.assertIn('IsRune(spellId, "Master of Wind")', self.code)
        self.assertIn('tornado = IsRune(spellId, "Cyclone") && SpawnsTornado(vortex.stacks, most, generates);', self.code)
        self.assertIn('Numbers::Num(spellId, "radius_yards")', self.code)
        self.assertIn('Numbers::Num(spellId, "damage_pct", "base")', self.code)
        # the vortex's ticks and the tornado's arcs are damage over time: they never add a stack
        self.assertEqual(len(re.findall(r"Combat::Strike\([^;]*, true\)", self.code)), 2)

    def test_the_cast_itself_deals_nothing(self):
        self.assertIn("std::optional<double>(0.0)", self.code)

    def test_the_wave_is_not_named_in_the_barbarians_file(self):
        self.assertNotIn(SKILL, barbarian_source.abilities())


if __name__ == "__main__":
    unittest.main()

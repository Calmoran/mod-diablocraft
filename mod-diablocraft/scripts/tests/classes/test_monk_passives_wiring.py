"""The source-text guards of monk passives: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_passives.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_passives import GLUE, MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def test_the_monk_calls_the_passives(self):
        monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.assertIn("DeadlyReach::Spent(player, spellId);\n        Passive::Cast(player, spellId);", monk)
        # (other skills' lines sit beside it: the call is in the function, not necessarily next to Hundred Fists')
        landed = monk[monk.index("void Landed(Player* player, Unit* target, std::uint32_t spellId)\n    {"):]
        self.assertIn("Passive::Landed(player, target, spellId);", landed[:landed.index("\n    }\n")])
        # the tick registers inside the one Monk::RegisterScripts (PM, decisions.md 2026-10-14), no second definition
        self.assertEqual(monk.count("void RegisterScripts()"), 1)
        register = monk[monk.index("void RegisterScripts()\n    {"):]
        self.assertIn("Passive::RegisterScripts();", register[:register.index("\n    }\n")])

    def test_the_scripts_are_registered_once_beside_the_wizards(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertEqual(combat.count("Monk::RegisterScripts();"), 1)
        self.assertIn("Wizard::RegisterScripts();\n        Monk::RegisterScripts();", combat)

    def test_the_first_look_clears_what_a_save_left(self):
        glue = GLUE.read_text(encoding="utf-8")
        self.assertIn("Reconcile(first ? (FleetFooted | ExaltedSoul | Seize) : state.applied, wanted)", glue)


if __name__ == "__main__":
    unittest.main()

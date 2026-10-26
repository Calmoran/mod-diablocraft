"""The source-text guards of monk inner sanctuary: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_inner_sanctuary.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_inner_sanctuary import MODULE, SOURCE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.source = (MODULE / SOURCE).read_text(encoding="utf-8")

    def mitigate(self):
        start = self.combat.index("std::optional<double> Mitigate(Unit* victim")
        return self.combat[start:self.combat.index("\n    }\n", start)]

    def test_mitigate_cuts_among_the_percentages_and_absorbs_last(self):
        body = self.mitigate()
        self.assertIn("ItemPowers::IncomingFactor(victim->ToPlayer()) * Monk::TakenFactor(victim) * Shaman::TakenFactor(victim);", body)
        self.assertTrue(body.rstrip().endswith("result = Monk::Absorb(victim, result);\n        result = Crusader::Redirect(victim, result);\n        result = Necromancer::Reduce(victim, result);\n        result = WitchDoctor::Reduce(victim, result);\n        result = Shaman::Reduce(victim, attacker, result);\n        return result;"), body[-200:])
        self.assertLess(body.index("Monk::TakenFactor"), body.index("BlockChance"))
        # The `.dc` preview (DamageTakenFactor) reads the same cut, so the two cannot drift apart.
        self.assertIn("*ItemPowers::IncomingFactor(victim->ToPlayer())*Monk::TakenFactor(victim)*Shaman::TakenFactor(victim);", self.combat)

    def test_dc_monk_hands_the_cast_to_the_skills_file(self):
        self.assertIn("if (Sanctuary::Is(spellId))\n            return Sanctuary::Cast(player, spellId);", self.monk)

    def test_the_ticks_ride_the_event_queue_and_the_immunity_its_holder(self):
        self.assertIn("player->m_Events.AddEventAtOffset([player, zone, tick] { Tick(player, zone, tick); }", self.source)
        self.assertIn("ally->m_Events.AddEventAtOffset(", self.source)
        self.assertIn("ControlImmunity::Set(ally, key, false);", self.source)

    def test_the_immunity_list_is_the_shared_one(self):
        # Temple of Protection gives the same list as Invigorating Gemstone: the one in ControlImmunity::Set, under the rune's own key.
        self.assertIn("ControlImmunity::Set(ally, id, true);", self.source)
        self.assertNotIn("ControlImpairing", self.source)
        self.assertNotIn("ApplySpellImmune", self.source)

    def test_the_skill_is_named_only_in_the_monks_folder(self):
        for path in (MODULE / "src").rglob("*"):
            if path.suffix in (".cpp", ".h") and "classes/monk" not in path.as_posix() and path.name not in (
                    "dc_spell_shells.h", "dc_spell_values.h"):
                text = path.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn("Inner Sanctuary", text, path)
                self.assertNotIn("Sanctuary::", text, path)


if __name__ == "__main__":
    unittest.main()

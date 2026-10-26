"""The source-text guards of band of rue chambers: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_band_of_rue_chambers.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_band_of_rue_chambers import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def text(self, path):
        return (SRC / path).read_text(encoding="utf-8")

    def test_the_factor_is_declared_and_reads_the_skill_of_the_spell(self):
        self.assertIn("double SpiritFactor(Player* player, std::uint32_t spellId);", self.text("classes/monk/dc_monk.h"))
        cpp = self.text("classes/monk/dc_monk.cpp")
        body = cpp[cpp.index("double SpiritFactor("):]
        body = body[:body.index("\n    }\n")]
        self.assertIn("Shells::FindAbility(spellId)", body)
        self.assertIn('ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct")', body)
        self.assertRegex(body, r": 1\.0\) \* ItemPowers::GenerationFactor\(player\);")   # the class-wide generation (Hexing Pants of Mr. Yan) multiplies the same pay

    # The Band multiplies only a Spirit Generator's OWN pay (PM ruling, diablocraft-4g6yl). Every other Monk gain of Spirit is deliberately
    # not multiplied; each is listed here, by file, with how many unmultiplied sites it has, so a new Generate( site anywhere in the Monk files
    # fails until it is multiplied or listed. (Strong Spirit gains through Resources::Energize, and the regeneration ticks of Epiphany, Inner Storm,
    # Air Ally, Chant of Resonance, Exalted Soul and Circular Breathing through Resources::Flow, not Generate; none of them is multiplied either.)
    NOT_THE_GENERATORS_PAY = {
        "dc_monk_breath_of_heaven.cpp": 1,   # Infused with Light's extra Spirit from every Spirit generating attack in its window
        "dc_monk_mantras.cpp": 1,            # Against All Odds' chance to restore Spirit when dealing damage
        "dc_monk_passives.cpp": 1,           # Chant of Resonance: the share of a mantra's cost paid back
        "dc_monk_mystic_ally.cpp": 1,        # Air Ally's Active's gain
    }

    def test_every_spirit_a_primary_pays_is_multiplied(self):
        paid = 0
        for path in sorted((SRC / "classes/monk").glob("*.cpp")):
            text = path.read_text(encoding="utf-8")
            plain = []
            for m in re.finditer(r"\bGenerate\(", text):
                statement = text[m.start():text.index(";", m.start())]
                if "SpiritFactor(player, spellId)" in statement:
                    paid += 1
                else:
                    plain.append(statement[:80])
            self.assertEqual(self.NOT_THE_GENERATORS_PAY.get(path.name, 0), len(plain),
                             "%s: a Spirit payment the Band cannot raise and the list does not know: %s" % (path.name, plain))
        self.assertGreaterEqual(paid, 2)   # Connected's per-attack pay and Rising Tide's per-enemy pay

    def test_infused_with_lights_extra_is_the_listed_unmultiplied_site(self):
        breath = (SRC / "classes/monk/dc_monk_breath_of_heaven.cpp").read_text(encoding="utf-8")
        self.assertEqual(1, len(re.findall(r"\bGenerate\(", breath)))
        self.assertNotIn("SpiritFactor", breath)      # deliberately not multiplied: not a Spirit Generator's own pay
        self.assertEqual(1, self.NOT_THE_GENERATORS_PAY["dc_monk_breath_of_heaven.cpp"])

    def test_the_stat_is_read_nowhere_else_for_a_class_that_has_no_spirit(self):
        for path in (SRC / "combat").glob("*.cpp"):
            self.assertNotIn("resource_generation_pct", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()

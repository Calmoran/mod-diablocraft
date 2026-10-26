"""The source-text guards of fist of az turrasq: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_fist_of_az_turrasq.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_fist_of_az_turrasq import SRC  # noqa: E402


PALM = SRC / "classes/monk/dc_monk_exploding_palm.cpp"


def explode(source=None):
    """Explode's body, as written or as a mutant's."""
    text = PALM.read_text(encoding="utf-8") if source is None else source
    body = text[text.index("void Explode("):]
    return body[:body.index("class dc_monk_exploding_palm_death")]


def palm(source=None):
    text = PALM.read_text(encoding="utf-8") if source is None else source
    body = text[text.index("void Palm("):]
    return body[:body.index("// The palm's enemy has died")]


class Hooks(unittest.TestCase):
    READ = 'ItemPowers::SkillFactor(player, std::string(Skill), "explosion_damage_pct")'

    def check(self, source=None):
        """The guards on the text of Explode and Palm; raises AssertionError on a mutant."""
        text = PALM.read_text(encoding="utf-8") if source is None else source
        body, bleed = explode(text), palm(text)
        assert body.count("SkillFactor(") == 1 and self.READ in body, "Explode reads the part once, on Exploding Palm's explosion_damage_pct"
        assert re.search(r'Run\(player, enemy, spellId, Burn, Numbers::Num\(spellId, "damage_pct", "explosion"\) \* part,', body), "Essence Burn's burn is multiplied"
        assert re.search(r"\*pct \*= part;", body) and body.index("*pct *= part;") < body.index("StrikeArea("), "the hit of the other runes is multiplied before it strikes"
        assert "explosion_damage_pct" not in bleed and "* part" not in bleed, "the bleed does not read the part"
        assert "SkillFactor" not in bleed, "the palm's cast reads no item factor of its own"
        assert re.search(r'#include "../../combat/dc_item_powers.h"', text), "the item powers header is included"

    def test_the_explosion_is_multiplied_and_the_bleed_is_not(self):
        self.check()

    def test_the_guards_fail_their_mutants(self):
        real = PALM.read_text(encoding="utf-8")
        mutants = {
            "burn_not_multiplied": real.replace('"damage_pct", "explosion") * part,', '"damage_pct", "explosion"),', 1),
            "hit_not_multiplied": real.replace("            if (pct)\n                *pct *= part;\n", "", 1),
            "read_for_every_hit": real.replace('"explosion_damage_pct")', '"damage_increase_pct")', 1),
            "the_bleed_reads_it": real.replace("            double const seconds = PalmSeconds(spellId);\n",
                                                 '            double const seconds = PalmSeconds(spellId) * ItemPowers::SkillFactor(player, std::string(Skill), "explosion_damage_pct");\n', 1),
            "no_include": real.replace('#include "../../combat/dc_item_powers.h"\n', "", 1),
            "the_part_read_twice": real.replace("            if (pct)\n", "            part;\n            ItemPowers::SkillFactor(player, std::string(Skill), \"explosion_damage_pct\");\n            if (pct)\n", 1),
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, mutant, name + " did not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    self.check(mutant)


if __name__ == "__main__":
    unittest.main()

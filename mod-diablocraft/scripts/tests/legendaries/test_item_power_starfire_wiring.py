"""The source-text guards of starfire: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_starfire.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import wizard_source
from test_item_power_starfire import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_hit_multiplies_the_factor_into_its_legendary_term(self):
        text = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("hit.legendary *= ItemPowers::DistanceFactor(player, target, shell.element);", text)
        # after the legendary term is set, before it is used
        self.assertLess(text.index('hit.legendary = ItemPowers::SkillFactor('), text.index("hit.legendary *= ItemPowers::DistanceFactor("))
        self.assertLess(text.index("hit.legendary *= ItemPowers::DistanceFactor("), text.index("hit.total = Total("))

    def test_the_distance_is_read_the_way_power_hungry_reads_it(self):
        wizard = wizard_source.CPP.read_text(encoding="utf-8")
        self.assertIn("double const distance = player->GetDistance(target);", wizard)
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        body = text[text.index("double DistanceFactor("):]
        body = body[:body.index("\n    }\n")]
        self.assertIn("player->GetDistance(target)", body)
        self.assertIn("ItemPower::DistanceFactor(Data().rows, CountsOf(guid), element,", body)
        # no target: nothing to measure, no bonus; the player's own state is read before the power lock (ElementBonus's order)
        self.assertRegex(body, r"if \(!player \|\| !target\)\s+return 1\.0;")
        self.assertLess(body.index("Seen(player)"), body.index("std::lock_guard"))

    def test_the_header_declares_it(self):
        self.assertIn("double DistanceFactor(Player const*, Unit const*, std::string const& element);",
                      (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

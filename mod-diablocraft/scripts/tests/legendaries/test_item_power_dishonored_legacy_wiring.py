"""The source-text guards of dishonored legacy: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_dishonored_legacy.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_dishonored_legacy import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_hit_multiplies_the_factor_into_its_legendary_term(self):
        text = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;", text)
        self.assertIn("hit.legendary *= ItemPowers::MissingResourceFactor(player, petName);", text)
        # after the legendary term is set, before it is used; the base skill name, so every rune of Cleave (and its explosion shells) takes it
        self.assertLess(text.index('hit.legendary = ItemPowers::SkillFactor('), text.index("hit.legendary *= ItemPowers::MissingResourceFactor("))
        self.assertLess(text.index("hit.legendary *= ItemPowers::MissingResourceFactor("), text.index("hit.total = Total("))

    def test_the_reader_looks_at_the_resource_before_the_power_lock(self):
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        body = text[text.index("double MissingResourceFactor("):]
        body = body[:body.index("\n    }\n")]
        self.assertRegex(body, r"if \(!player\)\s+return 1\.0;")
        self.assertIn("ItemPower::MissingResourceFactor(Data().rows, CountsOf(guid), skill,", body)
        self.assertLess(body.index("Seen(player)"), body.index("std::lock_guard"))

    def test_the_resource_is_read_when_a_row_names_the_stat(self):
        """Seen reads the primary resource only when `Data().resource`; the loader sets it for this stat as it does for `resource_above`."""
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        self.assertIn('row.stat == "damage_by_missing_resource_pct"', text[text.index("loaded.resource ="):][:200])
        seen = text[text.index("ItemPower::Situation Seen(Player const* player)"):][:2500]
        self.assertIn("situation.resourcePct = 100.0 * Resources::Units(player, *resource) / most;", seen)
        self.assertIn("Resources::Of(Classes::ClassIdOf(player))", seen)

    def test_the_header_declares_it(self):
        self.assertIn("double MissingResourceFactor(Player const*, std::string const& skill);",
                      (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

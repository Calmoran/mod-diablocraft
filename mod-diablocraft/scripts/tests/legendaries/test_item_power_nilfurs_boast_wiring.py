"""The source-text guards of Nilfur's Boast: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_nilfurs_boast.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)

SRC = Path(__file__).resolve().parents[3] / "src"


def strike_area(text):
    body = text[text.index("std::vector<Unit*> StrikeArea(Player* player"):]
    return body[:body.index("\n    }\n")]


def burst_rules(test, resolve, meteor):
    body = strike_area(resolve)
    test.assertIn("auto const area = Enemies(player, spellId, center, radius);", body)
    test.assertRegex(body, r"unsigned& enemies = ItemPowers::CastEnemies\(\);\s+unsigned const outer = enemies;\s+if \(!periodic\)\s+enemies = area\.size\(\);")
    test.assertRegex(body, r"for \(Unit\* target : area\)\s+if \(Strike\(player, target, spellId, pct, periodic\)\)\s+hit\.push_back\(target\);\s+enemies = outer;")
    test.assertLess(body.index("enemies = area.size();"), body.index("Strike(player, target"))
    test.assertLess(body.index("Strike(player, target"), body.index("enemies = outer;"))
    test.assertLess(body.index("enemies = outer;"), body.index("Connected(player, spellId"))
    test.assertEqual(1, body.count("Strike("))
    # the Meteor impact deals its hits through it, not through a loop of its own
    test.assertIn("auto hit = Combat::StrikeArea(player, id, at, Combat::TargetRadius(id), pct);", meteor)
    test.assertEqual(1, meteor.count("Strike"))


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolve = (SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        cls.meteor = (SRC / "classes/wizard/dc_wizard_meteor.cpp").read_text(encoding="utf-8")

    def test_a_burst_counts_its_area_around_its_hits_and_puts_it_back(self):
        burst_rules(self, self.resolve, self.meteor)

    def test_the_mutants_fail_the_same_guards(self):
        mutants = {
            "the_count_is_never_set": ("if (!periodic)\n            enemies = area.size();\n", "if (!periodic)\n            enemies = 0;\n"),
            "a_tick_counts_too": ("        if (!periodic)\n            enemies = area.size();\n", "        enemies = area.size();\n"),
            "the_count_is_not_put_back": ("        enemies = outer;\n        if (!hit.empty() && !periodic)", "        if (!hit.empty() && !periodic)"),
            "the_count_is_put_back_before_the_hits": ("        for (Unit* target : area)\n            if (Strike(player, target, spellId, pct, periodic))\n                hit.push_back(target);\n        enemies = outer;\n",
                                                      "        enemies = outer;\n        for (Unit* target : area)\n            if (Strike(player, target, spellId, pct, periodic))\n                hit.push_back(target);\n"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, self.resolve.count(old), name)
            with self.subTest(name), self.assertRaises((AssertionError, ValueError)):
                burst_rules(self, self.resolve.replace(old, new), self.meteor)
        with self.subTest("the_meteor_strikes_by_itself"), self.assertRaises(AssertionError):
            burst_rules(self, self.resolve, self.meteor.replace("Combat::StrikeArea(player, id, at, Combat::TargetRadius(id), pct)", "Combat::Strike(player, nullptr, id, pct)"))


if __name__ == "__main__":
    unittest.main()

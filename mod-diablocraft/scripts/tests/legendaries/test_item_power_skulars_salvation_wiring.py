"""The source-text guards of Skular's Salvation: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_skulars_salvation.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_skulars_salvation import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_boulder_toss_bursts_at_the_first_impact_through_its_area_list(self):
        """A projectile: Impact is per target, so the burst the first impact makes (the rune's own area) is where its hits are counted."""
        self.assertIn("return skill == \"Ancient Spear\" && rune == \"Boulder Toss\";",
                      (SRC / "classes/barbarian/dc_barbarian_ancient_spear.cpp").read_text(encoding="utf-8"))
        text = (SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        body = text[text.index("if (Abilities::BurstsAtFirstImpact(shell.skill, shell.rune))"):]
        body = body[:body.index("if (!impacted.insert(")]
        self.assertRegex(body, r"auto const area = AreaList\(player, GetSpellInfo\(\), target->GetPosition\(\), shell\.targeting\.radius\);")
        self.assertRegex(body, r"unsigned& enemies = ItemPowers::CastEnemies\(\);\s+unsigned const outer = enemies;\s+enemies = area\.size\(\);")
        self.assertRegex(body, r"for \(Unit\* u : area\)\s+hit \+= ResolveHit\(player, u, shell, GetSpellInfo\(\)\) \? 1 : 0;\s+enemies = outer;")
        self.assertEqual(1, body.count("ResolveHit("))

    def test_the_cast_loop_sets_the_count_around_its_hits_and_puts_it_back(self):
        text = (SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        body = text[text.index("void ResolveCast(Player* player, Shell const& shell"):]
        body = body[:body.index("\n        }\n")]
        self.assertRegex(body, r"unsigned& enemies = ItemPowers::CastEnemies\(\);\s+unsigned const outerEnemies = enemies;\s+enemies = distances\.size\(\);")
        self.assertLess(body.index("enemies = distances.size();"), body.index("connected += ResolveHit(player, target,"))
        self.assertLess(body.index("connected += ResolveHit(player, target,"), body.index("enemies = outerEnemies;"))
        self.assertLess(body.index("enemies = outerEnemies;"), body.index("Abilities::Cast(player, shell.spellId, targets"))

    def test_the_count_is_per_thread_and_read_into_every_situation(self):
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        self.assertRegex(text, r"unsigned& CastEnemies\(\)\s+\{\s+thread_local unsigned count = 0;\s+return count;\s+\}")
        situation = text[text.index("ItemPower::Situation SituationOf(std::uint64_t guid"):]
        situation = situation[:situation.index("return situation;")]
        self.assertIn("situation.castEnemies = CastEnemies();", situation)
        self.assertIn("unsigned& CastEnemies();", (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))

    def test_the_hit_reads_the_rune_row_beside_the_skills_own(self):
        text = (SRC / "combat/dc_combat.cpp").read_text(encoding="utf-8")
        own = 'hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")'
        rune = 'if (!shell.rune.empty())\n            hit.legendary *= ItemPowers::SkillFactor(player, hit.skillName, "damage_increase_pct");'
        self.assertIn('hit.skillName = shell.rune.empty() ? shell.skill : shell.skill + " - " + shell.rune;', text)
        self.assertIn(own, text)
        self.assertIn(rune, text)
        self.assertLess(text.index(own), text.index(rune))
        self.assertLess(text.index(rune), text.index("hit.total = Total("))


if __name__ == "__main__":
    unittest.main()

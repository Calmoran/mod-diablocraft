"""The source-text guards of girdle of giants: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_girdle_of_giants.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source
from test_item_power_girdle_of_giants import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    """The server half, read as source text (it cannot be compiled and run here): the calls are there, not proof that they run."""

    def test_a_pressed_cast_fires_the_cast_event_with_the_skills_name(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("if (player && row && !spell->IsTriggered())\n                    ItemPowers::Cast(player, info->Id);", combat)
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        self.assertIn('Fire(player, "cast", skill->skill, 1.0);', powers)

    def test_the_hit_reads_the_base_skill_name(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn('std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;', combat)
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', combat)

    def test_earthquake_snapshots_at_the_cast_and_ticks_copy_it(self):
        # the snapshot rule: the zone calls ComputeHit once, when Earthquake is cast, keeps that Hit and every tick copies it, so the 3 s window
        # is read at the cast: a cast inside it takes the bonus for the whole zone, one outside does not (and a later Slam does not add to it)
        abilities = barbarian_source.abilities((".cpp",))
        start = abilities.index("void ZoneStart(")
        zone = abilities[start:abilities.index("void Mark(", start)]
        self.assertEqual(1, zone.count("ComputeHit("))
        self.assertIn("if (!ComputeHit(p, nullptr, row.id, h) || h.skill <= 0)", zone)
        self.assertIn("zones.push_back({row.id, center, h,", zone)
        self.assertIn("Hit tick = zone.snapshot;", abilities)
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn('if (Abilities::LaunchesNoHit(shell.skill))', combat)
        self.assertIn("Abilities::Cast(player, shell.spellId, {}, &center);", combat)


if __name__ == "__main__":
    unittest.main()

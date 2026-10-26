"""The source-text guards of crystal fist: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_crystal_fist.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_girdle_of_giants import GENERATED, MIGRATION, MODULE, REPO, SRC, MATH, read_csv, read_csv_path, all_rows


class Hooks(unittest.TestCase):
    """The server half, read as source text (it cannot be compiled and run here): the calls are there, not proof that they run."""

    def test_a_pressed_cast_fires_the_cast_event_with_the_skills_name(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("if (player && row && !spell->IsTriggered())\n                    ItemPowers::Cast(player, info->Id);", combat)
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        self.assertIn('Fire(player, "cast", skill->skill, 1.0);', powers)

    def test_the_damage_a_player_takes_reads_the_reduction(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertGreaterEqual(combat.count("ItemPowers::IncomingFactor(victim->ToPlayer())"), 2)
        powers = item_powers_source.CPP.read_text(encoding="utf-8")
        body = powers[powers.index("double IncomingFactor(Player const* player)"):]
        self.assertIn("ItemPower::ReductionFactor(Data().rows, CountsOf(guid), situation)", body[:body.index("\n    }\n")])


if __name__ == "__main__":
    unittest.main()

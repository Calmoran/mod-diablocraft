"""The source-text guards of standoff: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_standoff.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator
from test_item_power_standoff import SRC, STAT  # noqa: E402


COMBAT = SRC / "combat/dc_combat.cpp"


POWERS = item_powers_source.CPP


def hook_failures(combat, powers):
    """What is wrong with the hit's use of the factor and with its reader ([] when they are right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    line = "hit.legendary *= ItemPowers::DerivedFactor(player, petName, *sheet);"
    compute = combat[combat.index("bool ComputeHit("):combat.index("std::string Hit::Describe()")]
    need("ComputeHit multiplies the factor into the legendary term with the hit's sheet", line in compute)
    need("after the legendary term is set and before the total",
         line in compute and compute.index("hit.legendary = ItemPowers::SkillFactor(") < compute.index(line) < compute.index("hit.total = Total("))
    reader = powers[powers.index("double DerivedFactor(Player const* player, std::string const& skill, DC::StatSheet const& sheet)"):]
    reader = reader[:reader.index("\n    }\n")]
    need("the stat is the sheet's Movement Speed", '{"damage_per_movement_speed_pct", Stat::MovementSpeed}' in reader)
    need("each mapped stat is read with its sheet value",
         "factor *= ItemPower::DerivedFactor(Data().rows, CountsOf(guid), skill, stat, sheet[sheetStat], situation);" in reader)
    need("the player is read before the power lock",
         "ItemPower::Situation seen = Seen(player);" in reader and "std::lock_guard<std::mutex> lock(mutex);" in reader
         and reader.index("Seen(player)") < reader.index("std::lock_guard"))
    need("no player, no power", re.search(r"if \(!player\)\s+return 1\.0;", reader) is not None)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_hit_and_the_reader(self):
        self.assertEqual([], hook_failures(COMBAT.read_text(encoding="utf-8"), POWERS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        combat = COMBAT.read_text(encoding="utf-8")
        powers = POWERS.read_text(encoding="utf-8")
        line = "        hit.legendary *= ItemPowers::DerivedFactor(player, petName, *sheet); // Standoff: by the bonus movement speed (N-DERIVED)\n"
        mutants = {
            "not_in_the_hit": (COMBAT, line, ""),
            "after_the_total": (COMBAT, line, ""),
            "another_sheet_stat": (POWERS, "Stat::MovementSpeed}}", "Stat::AttackSpeed}}"),
            "the_sheet_not_read": (POWERS, "skill, stat, sheet[sheetStat], situation", "skill, stat, 0.0, situation"),
            "seen_under_the_lock": (POWERS, "Stat::MovementSpeed}};\n        if (!player)\n            return 1.0;\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        ItemPower::Situation const situation",
                                    "Stat::MovementSpeed}};\n        if (!player)\n            return 1.0;\n        std::lock_guard<std::mutex> lock(mutex);\n        ItemPower::Situation seen = Seen(player);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        ItemPower::Situation const situation"),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                text = combat if where == COMBAT else powers
                self.assertEqual(1, text.count(old), name + " does not apply once")
                mutated = text.replace(old, new)
                if name == "after_the_total":
                    end = mutated.index(";\n", mutated.index("        hit.total = Total(")) + 2
                    mutated = mutated[:end] + line + mutated[end:]
                self.assertTrue(hook_failures(mutated if where == COMBAT else combat, mutated if where == POWERS else powers), name + " survived")

    def test_every_mapped_stat_is_one_the_generator_carries(self):
        """The seam: each `damage_per_<stat>_pct` the reader maps is a generator skill stat, and the generator carries no derived stat the reader lacks."""
        powers = POWERS.read_text(encoding="utf-8")
        reader = powers[powers.index("double DerivedFactor(Player const* player"):]
        mapped = re.findall(r'\{"(damage_per_\w+_pct)", Stat::\w+\}', reader[:reader.index("\n    }\n")])
        carried = [s for s in generator.SKILL_STATS if s.startswith("damage_per_") and s != "damage_per_distance_pct"]
        self.assertEqual([STAT], mapped)
        self.assertEqual(sorted(mapped), sorted(carried))

    def test_the_header_declares_it(self):
        header = (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")
        self.assertIn("double DerivedFactor(Player const*, std::string const& skill, DC::StatSheet const& sheet);", header)


if __name__ == "__main__":
    unittest.main()

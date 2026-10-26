"""The source-text guards of gesture of orpheus: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_gesture_of_orpheus.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_gesture_of_orpheus import MODULE  # noqa: E402


COMBAT = MODULE / "src/combat/dc_combat.cpp"


POWERS = item_powers_source.CPP


def reader_failures(combat, powers):
    """What is wrong with the two readers of the factor (the source guards; [] when they are right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    reduced = combat[combat.index("std::uint32_t ReducedCooldownMilliseconds(Player* player, std::uint32_t spellId,"):]
    reduced = reduced[:reduced.index("\n    }\n")]
    skill = combat[combat.index("std::uint32_t SkillCooldownMilliseconds(Player* player, std::uint32_t spellId, bool offhand)"):]
    skill = skill[:skill.index("\n    }\n")]
    scale = "return uint32(std::lround(ReducedCooldownMilliseconds(player, spellId, base) * ItemPowers::CooldownFactor(player, shell->skill)));"
    need("SkillCooldownMilliseconds scales the sheet-reduced cooldown by the skill's factor", scale in skill)
    need("ReducedCooldownMilliseconds does not (a send Cast's cut follows would take it twice)", "CooldownFactor" not in reduced)
    cast = powers[powers.index("    void Cast(Player* player, std::uint32_t spellId)\n"):]
    cast = cast[:cast.index("\n    }\n")]
    cut = "Abilities::ReduceSkillCooldown(player, skill->skill, left * (1.0 - factor));"
    need("Cast cuts the cooldown the core installed by the same factor",
         "if (double const factor = CooldownFactor(player, skill->skill); factor < 1.0)" in cast and cut in cast
         and "if (std::uint32_t const left = player->GetSpellCooldownDelay(spellId))" in cast)
    need("only a cooldown the record states is cut (after the primary and no-cooldown return)",
         cut in cast and cast.index('Classes::CategoryOf(spellId) == "Primary"') < cast.index(cut))
    need("the cut is taken outside the item powers' lock (the In-geom read after it, CooldownCut, takes it)",
         cut in cast and "std::lock_guard" not in cast and cast.index(cut) < cast.index("CooldownCut(player)"))
    reader = powers[powers.index("double CooldownFactor(Player const* player, std::string const& skill)"):]
    reader = reader[:reader.index("\n    }\n")]
    need("the reader is the rule over the player's rows", "ItemPower::CooldownFactor(Data().rows, CountsOf(guid), skill, SituationOf(guid));" in reader)
    need("the reader takes no Seen (the stat takes no condition)", "Seen(" not in reader)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_readers_apply_the_factor(self):
        self.assertEqual([], reader_failures("".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))]), POWERS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])
        powers = POWERS.read_text(encoding="utf-8")
        mutants = {
            "no_scale": (COMBAT, "return uint32(std::lround(ReducedCooldownMilliseconds(player, spellId, base) * ItemPowers::CooldownFactor(player, shell->skill)));",
                         "return ReducedCooldownMilliseconds(player, spellId, base);"),
            "taken_twice": (COMBAT, "        player->ApplySpellMod(spellId, SPELLMOD_COOLDOWN, value);\n",
                            "        player->ApplySpellMod(spellId, SPELLMOD_COOLDOWN, value);\n        value = int32(value * ItemPowers::CooldownFactor(player, \"Slow Time\"));\n"),
            "no_cut_at_cast": (POWERS, "Abilities::ReduceSkillCooldown(player, skill->skill, left * (1.0 - factor));", "(void)left;"),
            "cut_by_the_factor_not_its_rest": (POWERS, "left * (1.0 - factor)", "left * factor"),
            "reader_sees": (POWERS, "            return 1.0;\n        std::lock_guard<std::mutex> lock(mutex);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        return ItemPower::CooldownFactor(",
                            "            return 1.0;\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        return ItemPower::CooldownFactor("),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                text = combat if where == COMBAT else powers
                self.assertEqual(1, text.count(old), name + " does not apply once")
                mutated = text.replace(old, new)
                self.assertTrue(reader_failures(mutated if where == COMBAT else combat, mutated if where == POWERS else powers), name + " survived")


if __name__ == "__main__":
    unittest.main()

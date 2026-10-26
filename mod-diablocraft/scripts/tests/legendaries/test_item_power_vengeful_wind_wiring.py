"""The source-text guards of vengeful wind: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_vengeful_wind.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_vengeful_wind import SRC  # noqa: E402


WIND = SRC / "classes/monk/dc_monk_sweeping_wind.cpp"


COMBAT = SRC / "combat/dc_combat.cpp"


def reader_failures(text):
    """What is wrong with the vortex's reading of the raise in `text` (the source guards; [] when it is right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the item powers are included", '#include "../../combat/dc_item_powers.h"' in text)
    need("the raise is the item's max_stacks_add on the skill, base 0", 'ItemPowers::SkillSetTo(player, std::string(Skill), "max_stacks_add", 0)' in text)
    attack = text[text.index("void Attack(Player* player, bool generates)"):]
    need("Attack asks the raise before the lock", "double const raise = Raise(player);" in attack
         and attack.index("double const raise = Raise(player);") < attack.index("std::lock_guard<std::mutex> guard(mutex);"))
    need("Attack's cap is MaxStacks with the raise", 'unsigned const most = MaxStacks(Numbers::Num(spellId, "max_stacks_count"), raise);' in attack)
    need("the tornado and the stacks read that cap", "SpawnsTornado(vortex.stacks, most, generates)" in attack and "StacksAfter(vortex.stacks, most, generates)" in attack)
    need("no cap of the stacks bypasses MaxStacks", 'unsigned(Numbers::Num(spellId, "max_stacks_count"))' not in text)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_vortex_reads_the_raise(self):
        self.assertEqual([], reader_failures(WIND.read_text(encoding="utf-8")))

    def test_the_damage_is_the_standing_skill_multiplier(self):
        # S-DMG: every hit of the skill's shell (the vortex's ticks and Cyclone's tornado strike with Sweeping Wind's spell ids) takes
        # SkillFactor(damage_increase_pct) in hit.legendary.
        combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', combat)
        wind = WIND.read_text(encoding="utf-8")
        self.assertIn("Combat::Strike(player, enemy, spellId, pct, true)", wind)
        self.assertIn('Combat::Strike(player, enemies[pick], spellId, Numbers::Num(spellId, "damage_pct"), true)', wind)

    def test_the_monk_name_stays_in_the_monks_folder(self):
        for path in (SRC / "combat").rglob("*"):
            if path.suffix in (".cpp", ".h") and path.name != "dc_spell_shells.h":
                self.assertNotIn("max_stacks_add", path.read_text(encoding="utf-8", errors="replace"), path)

    def test_the_source_guards_fail_their_mutants(self):
        real = WIND.read_text(encoding="utf-8")
        mutants = {
            "no_raise": ('ItemPowers::SkillSetTo(player, std::string(Skill), "max_stacks_add", 0)', "0.0"),
            "raise_of_another_stat": ('"max_stacks_add", 0)', '"damage_increase_pct", 0)'),
            "raise_inside_the_lock": ("        double const raise = Raise(player);\n        {\n            std::lock_guard<std::mutex> guard(mutex);",
                                      "        {\n            std::lock_guard<std::mutex> guard(mutex);\n            double const raise = Raise(player);"),
            "cap_without_the_raise": ('unsigned const most = MaxStacks(Numbers::Num(spellId, "max_stacks_count"), raise);',
                                      'unsigned const most = unsigned(Numbers::Num(spellId, "max_stacks_count"));'),
            # Kyoshiro's Soul's idle cap in Tick (diablocraft-tvv2b) reads the same raised maximum
            "idle_cap_without_the_raise": (' MaxStacks(Numbers::Num(spellId, "max_stacks_count"), raise));',
                                           ' unsigned(Numbers::Num(spellId, "max_stacks_count")));'),
            "tornado_at_the_sheet": ("SpawnsTornado(vortex.stacks, most, generates)", "SpawnsTornado(vortex.stacks, 3, generates)"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(reader_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()

"""The source-text guards of legendary gem group b: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_legendary_gem_group_b.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import csv
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
from test_legendary_gem_group_b import MODULE, SRC  # noqa: E402


class Hooks(unittest.TestCase):
    """Source-text guards: the call is there. They do not run the C++."""

    @classmethod
    def setUpClass(cls):
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.passives = (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8")
        cls.abilities = barbarian_source.abilities((".cpp",))
        cls.powers = (SRC / "combat/dc_gem_powers.cpp").read_text(encoding="utf-8")

    def test_step_4_carries_taeguk_before_the_victim_debuff(self):
        self.assertRegex(self.combat, r"GemPowers::DamageBonus\(player\) \+\s+ItemPowers::DamageBonus\(player\) \+\s+hit\.targetBonus\)")

    def test_step_8_carries_the_per_target_gems(self):
        # (ml7y added Enforcer's pet factor after it: test_legendary_gem_enforcer.py)
        self.assertRegex(self.combat, r"GemPowers::SkillFactor\(player, shell\.spellId\) \*\s+GemPowers::TargetFactor\(player, target\)")

    def test_a_landed_hit_stacks_gogok_invigorating_and_stricken(self):
        self.assertRegex(self.passives, r"void Hit\(Player\* p, Unit\* target, uint32 spellId, unsigned school\)\s*\{\s*GemPowers::Hit\(p, target, spellId, school\);")

    def body(self, start, end):
        at = self.combat.index(start)
        return self.combat[at:self.combat.index(end, at)]

    def test_a_paid_channel_tick_stacks_taeguk(self):
        self.assertRegex(self.combat, r"SpendUnits\(player, Resources::ArcanePower, debit\.whole\);\s*ChannelSpent\(player, channel\.spellId\);")

    def test_a_paid_whirlwind_tick_stacks_taeguk_too(self):
        # diablocraft-egpv: Taeguk stacked only from the Wizard's channels
        body = self.body("bool PayWhirlwindTick(", "// A Wizard channel tick's Arcane Power")
        self.assertRegex(body, r"ChangeFury\(player, -cost\);\s*if \(cost > 0\)\s*ChannelSpent\(player, spellId\);")

    def test_a_channelled_skill_is_found_from_the_sheet_and_no_class_or_skill_is_named(self):
        helper = self.body("void ChannelSpent(Player* player, std::uint32_t spellId)", "// The payment itself")
        self.assertIn('Numbers::Has(spellId, "channel_tick_frames_count")', helper)
        for name in ("Whirlwind", "Wizard", "Barbarian", "Arcane", "Fury"):
            self.assertNotIn(name, helper.split("{", 1)[1])
        # the key is the sheet's own: Whirlwind and every Wizard channel carry it, nothing else needs to
        keyed = {row[0] for f in (MODULE / "data/d3").glob("*_skill_values.csv")
                 for row in csv.reader(io.StringIO(f.read_text(encoding="utf-8"))) if len(row) > 2 and row[2] == "channel_tick_frames_count"}
        self.assertIn("Whirlwind", keyed)
        self.assertTrue({"Ray of Frost", "Arcane Torrent", "Disintegrate"} <= keyed, keyed)

    def test_gogok_dodge_reaches_the_one_dodge_function(self):
        self.assertIn("std::clamp(chance + GemPowers::Dodge(p), 0.0, 100.0)", self.abilities)

    def test_the_kill_and_heal_hooks_are_registered_and_use_the_elite_test(self):
        self.assertIn("PLAYERHOOK_ON_CREATURE_KILL", self.powers)
        self.assertIn("killed->isElite() || DC::Rifts::IsPromotedElite(killed)", self.powers)
        self.assertIn("UNITHOOK_MODIFY_HEAL_RECEIVED", self.powers)
        self.assertIn("new Heals();", self.powers)

    def test_refresh_drops_the_buff_of_a_gem_taken_off(self):
        for field in ("powerful", "taeguk", "gogok", "invigorating"):
            self.assertIn("buffs.%s = {};" % field, self.powers)


if __name__ == "__main__":
    unittest.main()

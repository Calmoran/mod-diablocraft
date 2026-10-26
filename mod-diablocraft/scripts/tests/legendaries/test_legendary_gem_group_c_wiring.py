"""The source-text guards of legendary gem group c: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_legendary_gem_group_c.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
import wizard_source
from test_legendary_gem_group_c import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    """Source-text guards: the call is there. They do not run the C++."""

    @classmethod
    def setUpClass(cls):
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.passives = (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8")
        cls.abilities = barbarian_source.abilities((".cpp",))
        cls.primaries = (SRC / "classes/barbarian/dc_barbarian_primaries.cpp").read_text(encoding="utf-8")
        cls.powers = (SRC / "combat/dc_gem_powers.cpp").read_text(encoding="utf-8")
        cls.wizard = wizard_source.CPP.read_text(encoding="utf-8")

    def test_a_landed_hit_carries_its_spell_and_school_to_the_gems(self):
        self.assertRegex(self.passives, r"void Hit\(Player\* p, Unit\* target, uint32 spellId, unsigned school\)\s*\{\s*GemPowers::Hit\(p, target, spellId, school\);")
        self.assertIn("Passives::Hit(p,target,row->id,hit.school);", self.abilities)
        self.assertIn("Passives::Hit(player,target,GetSpellInfo()->Id,hit.school);", self.primaries)
        self.assertIn("Passives::Hit(player,target,shell.spellId,hit.school);", self.combat)
        self.assertIn("Passives::Hit(player, target, channel.spellId, hit.school);", self.combat)
        self.assertIn("Passives::Hit(player, target, spellId, hit.school);", self.combat)
        self.assertNotRegex("\n".join([self.combat, self.abilities, self.primaries]), r"Passives::Hit\(\s*\w+\s*,\s*target\s*\);")

    def test_every_critical_hit_reaches_pain_enhancer_before_the_abilities_lock(self):
        self.assertRegex(self.abilities, r"void CriticalHit\(Player\* p, Unit\* target, uint32 spellId, double damage\)\s*\{\s*(?:CriticalResource\(p, spellId\);[^\n]*\s*)?GemPowers::Critical\(p, target, spellId\);[^\n]*\n\s*std::lock_guard")

    def test_the_four_incoming_hit_paths_stagger_after_every_mitigation(self):
        for before in ("Wizard::Incoming(target ? target->ToPlayer() : nullptr, attacker, damage, Wizard::Attack::Melee);",
                       "Wizard::Incoming(target ? target->ToPlayer() : nullptr, attacker, damage, Wizard::Attack::Periodic);",
                       "Wizard::Incoming(victim, attacker, dealt, Wizard::Attack::Spell);"):
            at = self.combat.index(before)
            self.assertIn("GemPowers::Incoming(", self.combat[at:at + 400], before)
        self.assertRegex(self.combat, r"GemPowers::Incoming\(target \? target->ToPlayer\(\) : nullptr, attacker, taken\);\s*damage = int32\(taken\);")
        self.assertEqual(4, self.combat.count("GemPowers::Incoming("))
        # every one names whose hit it is: the payment is dealt in that name
        self.assertEqual(4, len(re.findall(r"GemPowers::Incoming\([^;]*, attacker, (?:damage|taken|dealt)\);", self.combat)))

    def pay_stagger(self):
        body = self.powers[self.powers.index("static void PayStagger"):self.powers.index("static void LapseGogok")]
        return re.sub(r"//[^\n]*", "", body)

    def test_the_payment_asks_the_shields_before_it_deals(self):
        body = self.pay_stagger()
        self.assertIn("Unit::CalcAbsorbResist(absorbing);", body)
        self.assertLess(body.index("Unit::CalcAbsorbResist(absorbing);"), body.index("DealSpellDamage"))
        self.assertIn("log.damage = absorbing.GetDamage();", body)
        self.assertIn("log.absorb = absorbing.GetAbsorb();", body)
        # Normal school, as DealMonsterHit asks: no resistance roll, every shield of ours absorbs all schools
        self.assertIn("SPELL_SCHOOL_MASK_NORMAL, SPELL_DIRECT_DAMAGE);", body)

    def test_the_payment_is_dealt_in_the_hitters_name_never_the_players_own(self):
        body = self.pay_stagger()
        self.assertNotRegex(body, r"player->DealSpellDamage|player->SendSpellNonMeleeDamageLog|log\(player, player")
        self.assertIn("source->DealSpellDamage(&log, true);", body)
        self.assertIn("ObjectAccessor::GetUnit(*player, from)", body)
        # a hitter that is gone leaves no attacker, never the player
        self.assertIn("Unit::DealDamage(nullptr, player,", body)
        self.assertRegex(self.powers, r"if \(owed > 0 && attacker\)\s*buffs\.staggerFrom = attacker->GetGUID\(\);")

    def test_the_two_readers_that_answer_a_hit_skip_the_payment(self):
        self.assertRegex(self.combat, r"if \(!GemPowers::PayingStagger\(\)\)\s*Abilities::Taken\(player,attacker,damage\);")
        sustain = (SRC / "stats/dc_sustain.cpp").read_text(encoding="utf-8")
        self.assertIn("if (resolvingThorns || DC::Combat::GemPowers::PayingStagger() ||", sustain)
        body = self.pay_stagger()
        self.assertEqual(1, body.count("payingStagger = true;"))
        self.assertLess(body.index("payingStagger = true;"), body.index("source->DealSpellDamage"))
        self.assertGreater(body.index("payingStagger = false;"), body.index("Unit::DealDamage(nullptr"))

    def test_the_gem_shells_are_loaded_as_combat_shells(self):
        self.assertRegex(self.combat, r"for \(auto const& gem : Shells::GemShells\)")

    def test_the_chill_of_the_wizard_carries_iceblinks_extra_slow_only_when_it_has_a_slow(self):
        self.assertIn("slow > 0 ? slow + GemPowers::ChillBonus(player) : slow", self.wizard)

    def test_the_gems_own_spells_set_nothing_off_and_the_tick_script_is_registered(self):
        self.assertRegex(self.powers, r"if \(!spellId \|\| IsGemShell\(spellId\)")
        self.assertIn("RegisterSpellScript(dc_gem_tick);", self.powers)
        self.assertRegex(self.powers, r"if \(!player \|\| !target \|\| !spellId \|\| IsGemShell\(spellId\)\)")

    def test_every_roll_is_scaled_by_the_hits_proc_coefficient(self):
        for gem in ("mirinaeChancePct", "wreathChancePct", "zeiStunChancePct"):
            self.assertIn("Proc::Rolls(coefficient, powers.%s, roll)" % gem, self.powers)
        self.assertIn("Combat::ProcCoefficient(spellId)", self.powers)   # the spell's, or the pet's own while a pet's blow lands

    def test_each_gem_numbers_come_from_the_gems_and_none_is_written_in_the_code(self):
        # the only numeric literals of the group C code are 0, 1, 100 and rounding: no gem number is typed in
        added = self.powers[self.powers.index("std::uint32_t ShellOf"):self.powers.index("void Contribute(")]
        literals = set(re.findall(r"(?<![\w.\"])(\d+\.?\d*)(?![\w\"])", re.sub(r"//[^\n]*", "", added)))
        self.assertLessEqual(literals, {"0", "1", "100.0", "1000.0", "0.0"}, literals)


if __name__ == "__main__":
    unittest.main()

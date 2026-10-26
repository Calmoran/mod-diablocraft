"""The source-text guards of legendary gem rank25: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_legendary_gem_rank25.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import test_legendary_gem_group_c as groupc
import wizard_source
from test_legendary_gem_rank25 import MATH, MODULE, SRC  # noqa: E402


class Hooks(unittest.TestCase):
    """Source-text guards: the call is there. They do not run the C++."""

    @classmethod
    def setUpClass(cls):
        cls.powers = (SRC / "combat/dc_gem_powers.cpp").read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.header = (SRC / "combat/dc_gem_powers.h").read_text(encoding="utf-8")
        cls.wizard = wizard_source.CPP.read_text(encoding="utf-8")
        cls.rows = {r["name"]: r for r in groupc.read(MODULE / "data/tunables/combat.csv")}
        cls.code = re.sub(r"//[^\n]*", "", cls.powers)

    def body(self, start, end):
        return self.code[self.code.index(start):self.code.index(end, self.code.index(start))]

    @staticmethod
    def terms(source, start):
        """The '+'-separated terms of the statement that opens with start (each class adds its own term)."""
        at = source.index(start) + len(start)
        return [" ".join(term.split()) for term in source[at:source.index(";", at)].split("+")]

    def test_the_hit_formula_reads_the_two_new_target_terms(self):
        self.assertIn("GemPowers::TargetBonus(target)", self.terms(self.combat, "hit.targetBonus ="))
        # the gem's term, then the other sources' (Envious Blade's ItemPowers::CritBonus, diablocraft-i2d92), then the clamp
        self.assertRegex(self.combat, r"\+GemPowers::CritBonus\(player, target\)(\+\w+::CritBonus\(player, target\))*\) / 100\.0, 0\.0, 1\.0\);")
        self.assertIn("double TargetBonus(Unit* target);", self.header)
        self.assertIn("double CritBonus(Player*, Unit* target);", self.header)

    def test_the_wizards_chill_is_read_through_one_public_question(self):
        self.assertRegex(self.wizard, r"bool ChilledBy\(Player\* player, Unit\* target\)\s*\{\s*return player && target && Chilled\(player, target\);")
        self.assertIn("Wizard::ChilledBy(player, target)", self.powers)

    def test_every_change_of_state_reaches_the_sheet_through_the_one_sync(self):
        for fn in ("void Refresh(", "void Hit(Player* player", "void ChannelSpent(", "static void LapseGogok"):
            at = self.code.index(fn)
            self.assertIn("Sync(player", self.code[at:at + 4600], fn)
        self.assertIn("Sync(owner->ToPlayer(), 1);", self.code)
        self.assertIn("Sync(owner->ToPlayer(), 0);", self.code)
        # the old one-off contribution of Gogok's Attack Speed is Wanted's now
        self.assertNotIn("Contribute(guid, Stat::AttackSpeed, 8, GemPower::AttackSpeedPct", self.code)

    def test_the_tick_script_puts_the_wreaths_speed_on_with_the_buff_and_takes_it_off_with_it(self):
        self.assertIn("AfterEffectApply += AuraEffectApplyFn(dc_gem_tick::Wear", self.code)
        self.assertIn("AfterEffectRemove += AuraEffectApplyFn(dc_gem_tick::Doff", self.code)
        # the remove handler runs while the aura is still on the unit: it must say so and not ask
        self.assertIn("Sync(owner->ToPlayer(), 0)", self.body("void Doff(", "void Tick("))

    def test_the_sync_publishes_only_what_changed_and_rebuilds_the_cooldown_aura(self):
        body = self.body("void Sync(", "void SetControlImmunity(")
        self.assertIn("if (want == before)\n                return;", body)
        self.assertIn("Passives::RefreshModifiers(player);", body)
        self.assertRegex(body, r"if \(want\.gogokCooldown != before\.gogokCooldown\)\s*Passives::RefreshModifiers")
        # one contribution id for each resisted element: RemoveContribution has no element key
        self.assertIn("ResistId + i", body)
        for stat in ("AttackSpeed, 8", "CooldownReduction, 8", "Armor, 15", "AttackSpeed, 6", "MovementSpeed, 4", "EliteDamage, 1"):
            self.assertIn("Stat::" + stat, body)
        self.assertIn("Bucket::Percent", body)

    def test_the_wreaths_movement_speed_is_outside_the_movement_cap(self):
        # stats.csv "Movement Speed": legendary procs add outside the 25% cap; dc_common.cpp clamps every Gems
        # MovementSpeed that is not Bucket::Uncapped into the capped bucket, where a character at the cap gains nothing.
        pattern = r"publish\(Stat::MovementSpeed, 4, [^;]*Bucket::Uncapped\);"
        body = self.body("void Sync(", "void SetControlImmunity(")
        self.assertRegex(body, pattern)
        for name, (old, new) in {
            "flat": ("want.wreathMovement, Bucket::Uncapped);", "want.wreathMovement);"),
            "percent": ("want.wreathMovement, Bucket::Uncapped);", "want.wreathMovement, Bucket::Percent);"),
        }.items():
            self.assertIn(old, body)
            self.assertIsNone(re.search(pattern, body.replace(old, new)), "mutant %s passed" % name)

    def test_each_contribution_id_is_its_gems_number_and_no_two_of_one_stat_share_one(self):
        ids = re.findall(r"publish\(Stat::(\w+), (\w+)", self.body("void Sync(", "void SetControlImmunity("))
        self.assertEqual(len(ids), len(set(ids)))
        gogok = int(re.search(r'Gogok = "Unique_Gem_0*(\d+)_x1"', MATH.read_text(encoding="utf-8")).group(1))
        taeguk = int(re.search(r'Taeguk = "Unique_Gem_0*(\d+)_x1"', MATH.read_text(encoding="utf-8")).group(1))
        self.assertIn("Stat::AttackSpeed, %d" % gogok, self.code)
        self.assertIn("Stat::Armor, %d" % taeguk, self.code)

    def test_the_control_immunity_is_the_stock_lists_and_stripped_on(self):
        # The stock lists, and stripping what is on when it goes on, are the shared Set's (test_control_immunity_shared.py); the gem gives it under key 0.
        body = self.body("void SetControlImmunity(", "void PutShield(")
        self.assertIn("ControlImmunity::Set(player, 0, on);", body)
        self.assertNotIn("ApplySpellImmune", body)
        self.assertIn("SetControlImmunity(player, powers.controlImmune);", self.body("void Refresh(", "std::vector<LegendaryGemItem::Socketed> Active("))

    def test_incoming_applies_the_attackers_state_before_the_stagger_and_for_every_victim(self):
        body = self.body("void Incoming(", "double ChillBonus(")
        self.assertLess(body.index("WeakenedFactor"), body.index("StaggerSplit"))
        self.assertLess(body.index("EliteIncomingFactor"), body.index("StaggerSplit"))
        self.assertLess(body.index("shieldArmed = true;"), body.index("StaggerSplit"))
        # a victim with no gem still gets a poisoned attacker's weakened hit: no early return on a missing state first
        self.assertLess(body.index("WeakenedFactor"), body.index("states.find"))
        self.assertIn("if (owed > 0 && attacker)\n                buffs.staggerFrom = attacker->GetGUID();", body)

    def test_a_payment_of_the_staggered_damage_is_a_damage_taken_for_the_shield(self):
        body = self.body("static void PayStagger", "static void LapseGogok")
        self.assertIn("Hurt(player);", body)
        self.assertGreater(body.index("Hurt(player);"), body.index("payingStagger = false;"))

    def test_the_kill_hook_rolls_moratoriums_clear_without_a_coefficient_and_keeps_the_elite_stack(self):
        body = self.body("void OnPlayerCreatureKill(", "private:")
        self.assertIn("GemPower::ChanceHits(powers.moratoriumClearChancePct, rand_chance())", body)
        self.assertIn("timed[guid].stagger = {};", body)
        self.assertIn("if (elite && powers.powerfulPct > 0)", body)
        self.assertIn("killed->isElite() || DC::Rifts::IsPromotedElite(killed)", body)

    def test_the_update_hook_runs_the_upkeep(self):
        body = self.body("void OnPlayerUpdate(", "static void PayStagger")
        self.assertIn("Upkeep(player);", body)

    def test_the_upkeep_acts_only_in_combat_and_searches_only_on_the_refresh_clock(self):
        body = self.body("void Upkeep(", "void Refresh(")
        self.assertIn("player->IsInCombat()", body)
        self.assertIn('Tune("gem_aura_refresh_ms")', body)
        self.assertRegex(body, r"if \(powers\.trappedYards > 0 && fighting\)")
        self.assertIn("SlowLastsRefreshes * refreshMs / 1000.0", body)
        self.assertIn("effect->ChangeAmount(-int32(std::lround(powers.trappedSlowPct)));", body)
        self.assertRegex(body, r"if \(enemy->IsInCombat\(\)\)\s*if \(Aura\* aura = Put\(player, enemy, shell,")
        # the searches are after the gate on the clock
        gate = body.index("if (!refresh)")
        for search in ("Enemies(player, shell,", "Enemies(player, bleed,"):
            self.assertGreater(body.index(search), gate, search)
        self.assertIn("enemy->HasAura(bleed, player->GetGUID())", body)
        # the clocks of Mirinae and the shield are not behind it
        self.assertLess(body.index("Smite(player, powers);"), gate)
        self.assertLess(body.index("PutShield(player,"), gate)
        self.assertIn("buffs.shieldArmed = false;", body)

    def test_simplicitys_heal_follows_a_primary_hit_even_when_it_killed(self):
        procs = self.body("void Procs(", "void Contribute(")
        self.assertIn("powers.simplicityHealPct > 0 && Classes::CategoryOf(spellId) == \"Primary\"", procs)
        self.assertLess(procs.index("simplicityHealPct"), procs.index("!target->IsAlive()"))
        self.assertGreater(procs.index("simplicityHealPct"), procs.index("IsGemShell(spellId)"))

    def test_the_boss_test_is_the_loots_and_the_rifts(self):
        body = self.body("double TargetFactor(", "double TargetBonus(")
        self.assertIn("creature->isWorldBoss() || creature->IsDungeonBoss() || DC::Rifts::IsGuardianEntry(creature->GetEntry())", body)

    def test_the_refresh_row_is_a_marked_placeholder_alex_sets(self):
        row = self.rows["gem_aura_refresh_ms"]
        self.assertEqual(("", "500"), (row["d3_value"], row["value"]))
        self.assertIn("PLACEHOLDER", row["notes"])
        self.assertIn("the designer sets it", row["notes"])
        self.assertIn("'gem_aura_refresh_ms'", (MODULE / "data/sql/db-world/updates/tunables_0008.sql").read_text(encoding="utf-8"))

    def test_the_three_new_shells_are_named_for_their_gems_and_in_the_header(self):
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for gem_id, effect in (("Unique_Gem_002_x1", "slow"), ("Unique_Gem_017_x1", "absorb"), ("Unique_Gem_013_x1", "heal")):
            self.assertRegex(header, r'\{834\d\d, "%s", "%s"\}' % (gem_id, effect))
        for const in ("Trapped", "Wildebeest", "Simplicity"):
            self.assertIn("ShellOf(GemPower::%s)" % const, self.code)

    def test_every_number_the_rank_25_code_uses_is_zero_one_or_a_unit_conversion(self):
        body = self.body("constexpr Element Resisted", "void Refresh(")
        literals = set(re.findall(r"(?<![\w.\"])(\d+\.?\d*)(?![\w\"])", body))
        # 0/1 bounds, 5 resisted elements, 160 (the contribution ids' base), 2.0 (refreshes the slow lasts), 1000.0
        # (ms in a second), the sheet's own ids (gem numbers) and the 4 contribution ids of Wanted, 100 not used
        self.assertLessEqual(literals, {"0", "1", "2.0", "5", "160", "1000.0", "0.0", "8", "15", "6", "4", "1"}, literals)


if __name__ == "__main__":
    unittest.main()

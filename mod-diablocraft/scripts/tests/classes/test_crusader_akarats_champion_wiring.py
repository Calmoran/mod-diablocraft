"""The source-text guards of Crusader Akarat's Champion: what the dispatch must call, and what the transformation gives.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in
test_crusader_akarats_champion.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_akarats_champion import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.hooks = squeeze((MODULE / "src/combat/dc_combat_hooks.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_skill_its_seams(self):
        self.assertEqual(self.crusader.count("AkaratsChampion::Cast(player, spellId);"), 1)
        self.assertEqual(self.crusader.count("AkaratsChampion::Landed(player, target, spellId);"), 1)
        self.assertEqual(self.crusader.count("AkaratsChampion::Multipliers(player, out);"), 1)
        self.assertEqual(self.crusader.count("AkaratsChampion::Fatal(player, damage);"), 1)
        self.assertIn("if (auto champion = AkaratsChampion::BasePct(spellId)) return champion;", self.crusader)

    def test_the_damage_hook_asks_the_crusader_before_an_items_save(self):
        hook = self.hooks[self.hooks.index("void OnDamage(Unit* attacker, Unit* victim, uint32& damage)"):]
        self.assertLess(hook.index("if (!player || !damage) return;"), hook.index("Crusader::Fatal(player, damage);"))
        self.assertLess(hook.index("Crusader::Fatal(player, damage);"), hook.index("ItemPowers::Fatal(player, damage);"))

    def test_the_cast_deals_no_damage_of_its_own(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_cast_begins_the_form_and_pays_the_wrath_by_the_payments_left(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn('Numbers::Num(spellId, "duration_seconds")', cast)
        self.assertIn("forms[player->GetGUID().GetRawValue()] = std::move(form);", cast)
        self.assertIn("Payments(seconds)", cast)
        self.assertIn('Numbers::Num(spellId, "regen_per_second_resource")', cast)
        pay = self.code[self.code.index("void Pay("):self.code.index("void Rally(")]
        self.assertIn("if (!player->IsInWorld() || !player->IsAlive() || left == 0) return;", pay)
        self.assertIn("GainWrath(player, spellId, points);", pay)
        self.assertIn("if (left > 1) player->m_Events.AddEventAtOffset", pay)
        self.assertNotIn("Now()", pay)

    def test_each_rune_gives_its_one_thing_at_the_cast(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        prophet = cast[cast.index("case Rune::Prophet:"):cast.index("case Rune::Hasteful:")]
        self.assertIn('Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1, seconds);', prophet)
        hasteful = cast[cast.index("case Rune::Hasteful:"):cast.index("case Rune::Rally:")]
        self.assertIn('Stat::AttackSpeed, Bucket::Flat, Numbers::Num(spellId, "attack_speed_pct"), 1, seconds', hasteful)
        self.assertIn('Rally(player, Numbers::Num(spellId, "cooldown_reduction_seconds"));', cast)

    def test_rally_cuts_every_other_ability_by_what_is_left(self):
        rally = self.code[self.code.index("void Rally("):self.code.index("bool Is(")]
        self.assertIn("if (Skill != row.skill)", rally)
        self.assertIn("player->GetSpellCooldownDelay(row.id)", rally)
        self.assertIn("player->ModifySpellCooldown(row.id, -static_cast<std::int32_t>(CutMs(left, seconds)))", rally)

    def test_fire_starter_burns_by_the_gap_and_only_while_the_form_lasts(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Multipliers(")]
        self.assertIn("RuneAt(form->spellId) != Rune::FireStarter", landed)
        self.assertIn('BurnGapMs(Combat::AttacksPerSecond(player), Tune("akarats_champion_fire_starter_icd_factor"))', landed)
        self.assertIn("BurnDue(", landed)
        self.assertIn("Dot::Burn(player, target, form->spellId, Numbers::Num(form->spellId, \"damage_pct\"),", landed)
        self.assertIn('Tune("akarats_champion_fire_starter_tick_seconds")', landed)

    def test_the_damage_bonus_is_a_multiplier_of_its_own_while_the_form_lasts(self):
        multipliers = self.code[self.code.index("void Multipliers("):self.code.index("void Fatal(")]
        self.assertIn("Current(player)", multipliers)
        self.assertIn('Numbers::Num(form->spellId, "damage_bonus_pct")', multipliers)
        self.assertIn('AddFactor(out, "Akarat\'s Champion", bonus);', multipliers)

    def test_prophet_turns_a_fatal_blow_into_nothing_and_full_life_once(self):
        fatal = self.code[self.code.index("void Fatal("):]
        self.assertIn("Saves(RuneAt(found->second.spellId), found->second.saved, damage, player->GetHealth())", fatal)
        self.assertIn("found->second.saved = true;", fatal)
        self.assertIn("player->SetHealth(player->GetMaxHealth());", fatal)
        self.assertIn("damage = 0;", fatal)

    def test_the_form_forgets_itself_once_its_time_is_over(self):
        current = self.code[self.code.index("std::optional<Form> Current("):self.code.index("void Pay(")]
        self.assertIn("if (!Active(Now(), found->second.until))", current)
        self.assertIn("forms.erase(found);", current)


if __name__ == "__main__":
    unittest.main()

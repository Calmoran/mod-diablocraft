"""The source-text guards of Crusader Laws of Valor and the Laws' shared mechanism: what the dispatch and the engine must call,
and what each rune does. They read the .cpp files and compile nothing; the compiled rules and their mutants are in
test_crusader_laws_of_valor.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_laws_of_valor import CODE, MECHANISM, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.laws = squeeze(MECHANISM.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.combat = squeeze((MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_law_its_seams(self):
        self.assertEqual(self.crusader.count("LawsOfValor::Cast(player, spellId, targets);"), 1)
        self.assertIn("if (auto valor = LawsOfValor::BasePct(spellId)) return valor;", self.crusader)
        registered = self.crusader[self.crusader.index("void RegisterScripts() {"):]
        registered = registered[:registered.index("}")]
        self.assertIn("LawsOfValor::Register();", registered)
        self.assertIn("Laws::RegisterScripts();", registered)
        self.assertIn("LawsOfJustice::Register();", registered)
        self.assertIn("LawsOfHope::Register();", registered)

    def test_the_combat_engine_registers_the_crusaders_hooks_beside_the_monks(self):
        self.assertIn("Monk::RegisterScripts(); Crusader::RegisterScripts();", self.combat)

    def test_the_law_deals_no_damage_of_its_own_on_the_cast(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_cast_empowers_then_pulses_at_once(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Register(")]
        self.assertLess(cast.index("Laws::Press(flavour, player, spellId, targets);"), cast.index("Pulse(player, spellId, true);"))
        press = self.laws[self.laws.index("void Press("):self.laws.index("void RegisterScripts(")]
        self.assertLess(press.index("Laws::Cast("), press.index("flavour.activate("))
        self.assertLess(press.index("flavour.activate("), press.index("StartPulse(flavour, player);"))
        self.assertIn('Millis(ActiveSeconds(player, Numbers::Num(base, flavour.window)))', press)
        self.assertIn("flavour.skill != row->skill", press)

    def test_every_holder_of_the_aura_wears_the_speed_of_the_form_the_law_is_in(self):
        pulse = self.code[self.code.index("void Pulse("):self.code.index("void Activate(")]
        self.assertIn('Laws::Number(boosted, Numbers::Num(base, "attack_speed_pct", "passive"), Numbers::Num(base, "attack_speed_pct", "active"))', pulse)
        self.assertIn("for (Player* holder : Laws::InAura(owner, Skill)) Laws::Hold(holder, Stat::AttackSpeed, Bucket::Flat, id, speed, now + Laws::PulseHoldMs());", pulse)
        self.assertIn("if (!boosted) return;", pulse)

    def test_each_rune_does_its_one_thing(self):
        pulse = self.code[self.code.index("void Pulse("):self.code.index("void Activate(")]
        self.assertIn('Laws::Hold(owner, Stat::LifePerHit, Bucket::Flat, id, Classes::HealAtLevel(Numbers::Num(slotted, "heal_per_hit_life"), owner->GetLevel()), until);', pulse)
        self.assertIn('Laws::Hold(owner, Stat::CritDamage, Bucket::Flat, id, Numbers::Num(slotted, "crit_damage_pct"), until);', pulse)
        self.assertIn("std::min(now + Laws::PulseHoldMs(), Laws::BoostEnd(owner->GetGUID().GetRawValue(), base))", pulse)
        activate = self.code[self.code.index("void Activate("):self.code.index("void Killed(")]
        frozen = activate[activate.index("case Rune::FrozenInTerror:"):activate.index("case Rune::UnstoppableForce:")]
        self.assertIn('Stuns(rand_chance(), Numbers::Num(spellId, "proc_chance_pct"))', frozen)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', frozen)
        self.assertIn('Numbers::Num(spellId, "radius_yards")', frozen)
        self.assertIn("Stun(player, enemy, seconds);", frozen)
        force = activate[activate.index("case Rune::UnstoppableForce:"):]
        self.assertIn("Laws::Hold(player, Stat::ResourceCostReduction, Bucket::Flat,", force)
        self.assertIn('Numbers::Num(spellId, "cost_reduction_pct")', force)
        self.assertIn('Laws::Now() + Millis(Laws::ActiveSeconds(player, Numbers::Num(spellId, "duration_seconds")))', force)
        killed = self.code[self.code.index("void Killed("):self.code.index("Laws::Flavour const flavour")]
        self.assertIn("RuneAt(slotted) != Rune::AnsweredPrayer", killed)
        self.assertIn('Millis(Numbers::Num(slotted, "duration_seconds", "per_kill"))', killed)
        self.assertIn('Millis(Numbers::Num(slotted, "duration_seconds", "max"))', killed)

    def test_the_pulse_runs_only_for_a_slotted_law_in_force(self):
        beat = self.laws[self.laws.index("void Beat("):self.laws.index("void StartPulse(")]
        self.assertIn("bool const on = slotted && On(guid, base);", beat)
        self.assertIn("flavour.pulse(owner, slotted, Boosted(guid, base, Now()));", beat)
        start = self.laws[self.laws.index("void StartPulse("):self.laws.index("// ---- the always-on hook")]
        self.assertIn("!On(guid, BaseId(flavour.skill)) || !Slotted(player, flavour.skill)", start)

    def test_a_held_number_lapses_unless_a_pulse_renews_it_and_a_cost_number_moves_the_cost_auras(self):
        self.assertIn("Passives::RefreshModifiers(target);", self.laws)
        lapse = self.laws[self.laws.index("void Lapse("):self.laws.index("// ---- the pulse")]
        self.assertIn("if (found->second.until > now) again = found->second.until - now; else holds.erase(found);", lapse)
        self.assertIn("Sheet(target, Stat(std::get<1>(key)), bucket, std::get<2>(key), 0, element);", lapse)

    def test_the_always_on_hook_polls_the_bar_forgets_at_logout_and_hears_the_kills(self):
        self.assertIn("{PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_CREATURE_KILL, PLAYERHOOK_ON_SPELL_CAST}", self.laws)
        self.assertIn("StartPulse(*flavour, player);", self.laws)
        self.assertIn("Forget(guid);", self.laws)
        self.assertIn("if (flavour->killed) flavour->killed(killer);", self.laws)

    def test_the_pulse_period_is_a_tunable_with_a_floor_in_the_code(self):
        self.assertIn('DC::Tunables::Get("crusader", "laws_pulse_seconds")', self.laws)
        self.assertIn("constexpr double DefaultPulseSeconds = 1.0;", self.laws)
        rows = (MODULE / "data/tunables/crusader.csv").read_text(encoding="utf-8").splitlines()
        row = [r for r in rows if r.startswith("laws_pulse_seconds,")]
        self.assertEqual(len(row), 1)
        self.assertTrue(row[0].startswith("laws_pulse_seconds,,1,seconds,"), "the designer's column is the standing default of 1 second")
        self.assertNotIn("PLACEHOLDER", row[0])
        self.assertIn("q-1021-27", row[0])

    def test_the_code_names_no_other_class(self):
        for text in (self.code, self.laws):
            for name in ("Monk", "Barbarian", "Wizard", "Necromancer"):
                self.assertNotIn(name + "::", text)


if __name__ == "__main__":
    unittest.main()

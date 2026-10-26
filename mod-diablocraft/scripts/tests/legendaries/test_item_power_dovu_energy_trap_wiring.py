"""The source-text guards of dovu energy trap: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_dovu_energy_trap.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source
import wizard_source
from test_item_power_dovu_energy_trap import SRC  # noqa: E402


SITES = {
    "classes/barbarian": ['Control(p, u, *r, Numbers::Num(b->id, "stun_duration_seconds") * ItemPowers::StunFactor(p));',
                                'Control(p, u, *r, Numbers::Num(r->id, "stun_duration_seconds") * ItemPowers::StunFactor(p));'],
    "classes/wizard": ['Apply(player, target, "Wizard - Stunned", seconds * ItemPowers::StunFactor(player));'],
    "combat/dc_gem_powers.cpp": ["Put(player, target, ShellOf(GemPower::Zei), powers.zeiStunSeconds * ItemPowers::StunFactor(player));"],
    "classes/monk/dc_monk_lashing_tail_kick.cpp": ['Hold(player, enemy, Stunned, 0, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));'],
    "classes/monk/dc_monk_wave_of_light.cpp": ['Stun(player, enemy, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));'],
    "classes/monk/dc_monk_epiphany.cpp": ['Stun(player, target, Numbers::Num(rune, "stun_duration_seconds") * ItemPowers::StunFactor(player));'],
    "classes/crusader/dc_crusader_blessed_shield.cpp": ['double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);'],
    "classes/crusader/dc_crusader_blessed_hammer.cpp": ['double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);'],
    "classes/crusader/dc_crusader_sweep_attack.cpp": ['double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);'],
    "classes/crusader/dc_crusader_shield_bash.cpp": ['Stun(player, aimed, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));'],
    "classes/crusader/dc_crusader_iron_skin.cpp": ['double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(victim);'],
    "classes/crusader/dc_crusader_justice.cpp": ['double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);'],
    "classes/crusader/dc_crusader_smite.cpp": ['stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);'],
    "classes/crusader/dc_crusader_slash.cpp": ['double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);'],
    "classes/shaman/dc_shaman_purge.cpp": ['double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);'],
    "classes/shaman/dc_shaman_thunderstorm.cpp": ['double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);',
                                                  'double const freeze = Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player);'],
    "classes/monk/dc_monk_mantras.cpp": ['Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(monk));'],
}


class Hooks(unittest.TestCase):
    def powers(self):
        return item_powers_source.CPP.read_text(encoding="utf-8")

    def site(self, path):
        if path == "classes/barbarian":
            return barbarian_source.abilities((".cpp",))
        if path == "classes/wizard":
            return wizard_source.source()
        return (SRC / path).read_text(encoding="utf-8")

    def check_reader_and_hook(self, text):
        self.assertIn("double StunFactor(Player const*);", (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))
        reader = text[text.index("double StunFactor(Player const* player)"):]
        self.assertIn('return PlayerFactor(player, "stun_duration_pct");', reader[:reader.index("\n    }\n")])
        hook = text[text.index("class StunDurations final : public AllSpellScript"):]
        hook = hook[:hook.index("\n        };\n")]
        self.assertIn("{ALLSPELLHOOK_ON_CALC_MAX_DURATION}", hook)
        self.assertIn("static constexpr std::uint32_t IceBlastHold = 15878;", hook)
        self.assertIn("info->Id == IceBlastHold", hook)
        self.assertIn("!info->HasAura(SPELL_AURA_MOD_STUN)", hook)
        self.assertIn("!(info->GetAllEffectsMechanicMask() & (1ULL << MECHANIC_STUN))", hook)
        self.assertIn("caster && caster->IsPlayer()", hook)
        self.assertIn("maxDuration = ItemPower::StunMilliseconds(maxDuration, StunFactor(caster->ToPlayer()));", hook)
        register = text[text.index("void RegisterEventScripts()"):]
        self.assertIn("new StunDurations();", register[:register.index("\n        }\n")])

    def test_the_reader_and_the_hook(self):
        self.check_reader_and_hook(self.powers())

    def test_every_stun_site_that_sets_its_own_seconds_multiplies_them(self):
        for path, calls in SITES.items():
            text = self.site(path)
            for call in calls:
                with self.subTest(site=path, call=call):
                    self.assertEqual(1, text.count(call))
        # no stun_duration_seconds read anywhere else in the module goes unstretched (the Wizard's reads go through its Stun helper, above)
        unstretched = []
        for path in sorted(SRC.rglob("*.cpp")):
            wizard = path.parent.relative_to(SRC).as_posix() == "classes/wizard"
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if '"stun_duration_seconds")' not in line or "StunFactor" in line or line.startswith("Numbers::Has("):
                    continue
                if wizard and line.startswith("Stun(player, target, Num("):
                    continue
                unstretched.append("%s: %s" % (path.relative_to(SRC), line))
        self.assertEqual([], unstretched)

    def test_the_hook_mutants_are_caught(self):
        text = self.powers()
        mutants = {
            "the_ice_blast_freeze_stretched": ("info->Id == IceBlastHold || ", ""),
            "any_aura_stretched": ("!info->HasAura(SPELL_AURA_MOD_STUN) ||", ""),
            "a_freeze_record_stretched": ("!(info->GetAllEffectsMechanicMask() & (1ULL << MECHANIC_STUN))", "false"),
            "a_creatures_stun_stretched": ("caster && caster->IsPlayer()", "caster"),
            "the_reader_not_asked": ("StunFactor(caster->ToPlayer())", "1.0"),
            "the_hook_not_registered": ("            new StunDurations();\n", ""),
            "the_reader_reads_another_stat": ('return PlayerFactor(player, "stun_duration_pct");', 'return PlayerFactor(player, "shield_potency_pct");'),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, text, name + " does not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    self.check_reader_and_hook(text.replace(old, new, 1))


if __name__ == "__main__":
    unittest.main()

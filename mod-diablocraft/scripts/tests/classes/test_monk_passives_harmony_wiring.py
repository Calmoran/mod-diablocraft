"""The source-text guards of monk passives harmony: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_passives_harmony.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_passives_harmony import CPP, MODULE, PASSIVES  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.effects = (MODULE / "src/classes/monk/dc_monk_effects.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.cpp = (MODULE / CPP).read_text(encoding="utf-8")

    def test_the_monk_hands_a_cast_and_a_connect_to_the_passives_first(self):
        self.assertIn("PassivesHarmony::Connected(player, spellId);", self.monk)
        self.assertIn("PassivesHarmony::Cast(player, spellId);", self.monk)
        # Cast first: before any of the skills' own dispatch returns.
        self.assertLess(self.monk.index("PassivesHarmony::Cast(player, spellId);"), self.monk.index("return DashingStrike::Cast(player, spellId, targets);"))

    def test_the_passives_are_separate_multipliers_not_the_additive_bucket(self):
        self.assertIn("void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);",
                      (MODULE / "src/classes/monk/dc_monk.h").read_text(encoding="utf-8"))
        self.assertIn("PassivesHarmony::Multipliers(player, spellId, out);", self.monk)
        self.assertIn("Wizard::Multipliers(player, shell.spellId, hit.factors);\n        Monk::Multipliers(player, target, shell.spellId, hit.factors);",
                      self.combat)
        # the effects' DamageBonus is the additive pool: nothing of these passives is in it
        self.assertNotIn("PassivesHarmony", self.effects)
        self.assertNotIn("DamageBonus", self.cpp)
        for name in ("Combination Strike", "Mythic Rhythm", "Momentum", "Unity", "Unity (ally)"):
            self.assertIn(f'AddFactor(out, "{name}"', self.cpp)

    def test_near_death_experience_knocks_enemies_back_in_yards(self):
        self.assertIn('Abilities::Knockback(player, enemy, Tune("near_death_experience_knockback_yards"))', self.cpp)
        self.assertIn('Tune("near_death_experience_knockback_radius_yards")', self.cpp)

    def test_the_scripts_are_registered(self):
        # registered inside the one Monk::RegisterScripts (dc_monk.cpp), no line of its own in dc_combat.cpp
        self.assertNotIn("PassivesHarmony::RegisterScripts();", self.combat)
        register = self.monk[self.monk.index("void RegisterScripts()\n    {"):]
        self.assertIn("PassivesHarmony::RegisterScripts();", register[:register.index("\n    }\n")])
        self.assertIn("UNITHOOK_ON_DAMAGE", self.cpp)
        self.assertIn("PLAYERHOOK_ON_UPDATE", self.cpp)

    def test_each_passive_is_asked_by_name(self):
        for name in PASSIVES:
            self.assertIn(f'Has(player, "{name}")', self.cpp)

    def test_harmony_reads_items_only_and_the_first_look_clears_a_saved_one(self):
        self.assertIn("Stats::Sum(guid, Source::Items, Stat::SingleResistance", self.cpp)
        self.assertIn("!state.harmonyChecked", self.cpp)

    def test_a_spender_spends_after_its_hit_and_a_generator_counts_when_it_connects(self):
        self.assertIn("state.rhythm.Spend();", self.cpp)
        self.assertIn("rhythm.Hit(", self.cpp)

    def test_mythic_rhythm_adds_no_spirit(self):
        # D3's text: "Every third hit from a Spirit Generator increases the damage of your next damaging Spirit Spender by 40%";
        # nothing in it pays Spirit, so the generator's hit counts and pays nothing of its own.
        connected = self.cpp[self.cpp.index("void Connected(Player* player, std::uint32_t spellId)"):]
        connected = connected[:connected.index("\n    }\n")]
        self.assertIn('unsigned(Tune("mythic_rhythm_generator_hits"))', connected)
        self.assertIn("rhythm.Hit(hitCount);", connected)
        self.assertNotIn("Generate(", connected)
        self.assertNotIn("Energize(", connected)
        self.assertNotIn("Generate(", self.cpp)


    def test_seven_sided_strike_spends_mythic_rhythm_with_its_cast(self):
        # diablocraft-2wf3x: Seven-Sided Strike's cast returns through Monk::Delayed before Monk::Cast, so the spend is
        # called there, and its strikes (dc_monk_seven_sided_strike.cpp, later on the event queue) read what it carried.
        delayed = self.monk[self.monk.index("bool Delayed(Player* player, std::uint32_t spellId"):]
        delayed = delayed[:delayed.index("\n    }\n")]
        self.assertIn("PassivesHarmony::Cast(player, spellId);", delayed)
        self.assertLess(delayed.index("PassivesHarmony::Cast(player, spellId);"), delayed.index("SevenSided::Start("))
        cast = self.cpp[self.cpp.index("void Cast(Player* player, std::uint32_t spellId)"):]
        cast = cast[:cast.index("\n    }\n")]
        self.assertIn("state.rhythm.Carry();", cast)
        self.assertIn("SevenSided::Is(spellId)", cast)
        multipliers = self.cpp[self.cpp.index("void Multipliers(Player* player, std::uint32_t spellId"):]
        multipliers = multipliers[:multipliers.index("\n    }\n")]
        self.assertIn("SevenSided::Is(spellId))", multipliers[multipliers.index("state.rhythm.Bonus("):])


if __name__ == "__main__":
    unittest.main()

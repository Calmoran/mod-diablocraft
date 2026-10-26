"""The source-text guards of Crusader Iron Skin: what the dispatch and the engine must call, and what each rune does.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_iron_skin.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_iron_skin import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.combat = squeeze((MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))
        self.hooks = squeeze((MODULE / "src/combat/dc_combat_hooks.cpp").read_text(encoding="utf-8"))

    def test_the_engine_tells_the_crusader_a_hit_was_taken_beside_the_monks(self):
        # The melee hit, the spell hit and a monster's hit; not the periodic tick, as the Monk's.
        self.assertEqual(self.hooks.count("if(damage>0)Monk::Taken(target,attacker); if(damage>0)Crusader::Taken(target,attacker,damage);"), 2)
        self.assertIn("if(damage>0)Monk::Taken(victim,attacker); if(damage>0)Crusader::Taken(victim,attacker,damage);", self.combat)
        self.assertEqual(self.hooks.count("Crusader::Taken("), 2)
        self.assertEqual(self.combat.count("Crusader::Taken("), 1)

    def test_the_dispatch_hands_the_skin_its_seams(self):
        self.assertEqual(self.crusader.count("IronSkin::Cast(player, spellId);"), 1)
        self.assertIn("if (auto skin = IronSkin::BasePct(spellId)) return skin;", self.crusader)
        self.assertIn("if (Player* player = victim ? victim->ToPlayer() : nullptr) { IronSkin::Taken(player);", self.crusader)
        self.assertLess(self.crusader.index("ShieldGlare::BasePct(spellId)"), self.crusader.index("IronSkin::BasePct(spellId)"))

    def test_the_skin_deals_no_damage_of_its_own_on_the_cast(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_skin_takes_the_sheets_damage_off_for_the_skins_seconds(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Taken(")]
        self.assertIn('Buffs::Stack(player, spellId, Stat::SpecificReduction, Bucket::Flat, Numbers::Num(spellId, "absorb_pct"), 1, seconds);', cast)
        self.assertIn("double const seconds = Lasts(spellId);", cast)
        lasts = self.code[self.code.index("double Lasts("):self.code.index("void Explode(")]
        self.assertIn('Seconds(RuneAt(spellId), Numbers::Num(spellId, "absorb_duration_seconds"), Numbers::Num(spellId, "duration_seconds"))', lasts)

    def test_each_rune_does_its_one_thing(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Taken(")]
        reflective = cast[cast.index("case Rune::ReflectiveSkin:"):cast.index("case Rune::ExplosiveSkin:")]
        self.assertIn('Buffs::Stack(player, spellId, Stat::Thorns, Bucket::Percent, Numbers::Num(spellId, "thorns_pct"), 1, seconds);', reflective)
        explosive = cast[cast.index("case Rune::ExplosiveSkin:"):]
        self.assertIn("Explode(player, spellId);", explosive)
        self.assertIn("std::uint64_t(seconds * 1000.0) + 2", explosive)
        explode = self.code[self.code.index("void Explode("):self.code.index("} // namespace")]
        self.assertIn("!Expired(Buffs::Stacks(player, spellId, Stat::SpecificReduction))", explode)
        self.assertIn('Numbers::Own(spellId, "damage_pct")', explode)
        self.assertIn('Numbers::Num(spellId, "radius_yards")', explode)
        taken = self.code[self.code.index("void Taken("):]
        self.assertIn("!Buffs::Stacks(victim, spellId, Stat::SpecificReduction)", taken)
        charged = taken[taken.index("case Rune::ChargedUp:"):taken.index("case Rune::Flash:")]
        self.assertIn('Procs(rand_chance(), Numbers::Num(spellId, "proc_chance_pct"))', charged)
        self.assertIn('double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(victim);', charged)
        flash = taken[taken.index("case Rune::Flash:"):]
        self.assertIn('Buffs::Stack(victim, spellId, Stat::MovementSpeed, Bucket::Uncapped, Numbers::Num(spellId, "movement_speed_pct"), 1, Numbers::Num(spellId, "duration_seconds"));', flash)


if __name__ == "__main__":
    unittest.main()

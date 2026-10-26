"""The source-text guards of Crusader Phalanx: what the dispatch must call, and what the avatars and each rune do.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_phalanx.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_phalanx import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def source(path):
    return squeeze((MODULE / path).read_text(encoding="utf-8"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = source("src/classes/crusader/dc_crusader.cpp")

    def test_the_dispatch_hands_phalanx_its_seams(self):
        self.assertEqual(self.crusader.count("Phalanx::Cast(player, spellId, targets);"), 1)
        self.assertEqual(self.crusader.count("Phalanx::Ground(player, spellId, center);"), 1)
        self.assertIn("if (auto phalanx = Phalanx::BasePct(spellId)) return phalanx;", self.crusader)
        registered = self.crusader[self.crusader.index("void RegisterScripts() {"):]
        registered = registered[:registered.index("}")]
        self.assertIn("Phalanx::RegisterScripts();", registered)
        self.assertIn("LawsOfValor::Register();", registered)
        self.assertIn("LawsOfJustice::Register();", registered)
        self.assertIn("LawsOfHope::Register();", registered)
        self.assertIn("Laws::RegisterScripts();", registered)

    def test_the_avatars_script_is_registered_with_the_combat_scripts(self):
        self.assertIn("Crusader::RegisterScripts();", source("src/combat/dc_combat.cpp"))
        self.assertIn("void RegisterScripts();", source("src/classes/crusader/dc_crusader.h"))
        self.assertIn('CreatureScript("dc_crusader_avatar")', self.code)

    def test_the_line_is_the_skills_percentage_for_the_charge_runes_and_nothing_for_the_rest(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn('HitsTheLine(RuneAt(spellId)) ? Numbers::Own(BaseId(Skill), "damage_pct").value_or(0.0) : 0.0', base)

    def test_stampede_stuns_with_the_stun_factor_and_the_gated_runes_start_their_cooldown_and_give_no_cost_back(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Ground(")]
        self.assertIn('Stuns(rune, rand_chance(), Numbers::Num(spellId, "proc_chance_pct"))', cast)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', cast)
        self.assertNotIn("GainWrath", cast)
        self.assertNotIn("CostGivenBack", self.code)
        self.assertIn('CooldownSeconds(rune, Numbers::Num(spellId, "internal_cooldown_seconds"))', cast)
        self.assertIn("SendSkillCooldown(player, spellId, std::uint32_t(Millis(cooldown)));", cast)

    def test_the_avatars_are_the_crusaders_and_fight_on_its_side(self):
        configure = self.code[self.code.index("void Configure("):self.code.index("void Run(")]
        for text in ("me->SetOwnerGUID(owner);", "me->SetCreatorGUID(owner);", "me->SetFaction(player->GetFaction());",
                     "me->SetReactState(REACT_PASSIVE);", "me->SetImmuneToAll(true);"):
            self.assertIn(text, configure)

    def test_the_charge_runs_to_the_point_and_shield_charge_bashes_once_where_it_arrives(self):
        run = self.code[self.code.index("void Run("):self.code.index("void Follow(")]
        self.assertIn("me->SetSpeedRate(MOVE_RUN, rate);", run)
        self.assertIn("me->GetMotionMaster()->MovePoint(1, end);", run)
        inform = self.code[self.code.index("void MovementInform("):self.code.index("void UpdateAI(")]
        self.assertIn("RuneAt(record) == Rune::ShieldCharge", inform)
        self.assertIn("!shared->bashed", inform)
        self.assertIn("shared->bashed = true;", inform)
        self.assertIn('Combat::StrikeArea(player, record, stop, Tune("phalanx_shield_charge_bash_radius_yards"), Numbers::Own(record, "damage_pct"));', inform)

    def test_bowmen_shoot_at_the_fire_rate_and_the_bodyguard_swings_at_the_crusaders_attack_speed(self):
        attend = self.code[self.code.index("void Attend("):self.code.index("class Script")]
        self.assertIn('ShotDue(clock, Tune("phalanx_bowmen_fire_seconds"))', attend)
        self.assertIn("Combat::AttacksPerSecond(player) * Combat::ItemPowers::PetSpeedFactor(player)", attend)
        self.assertIn("!me->IsWithinMeleeRange(target)", attend)
        self.assertEqual(attend.count('Combat::Strike(player, target, record, Numbers::Own(record, "damage_pct"));'), 2)

    def test_the_cast_summons_the_sheets_count_by_behavior(self):
        ground = self.code[self.code.index("void Ground("):self.code.index("void RegisterScripts(")]
        self.assertIn('unsigned(Numbers::Num(IdOf("Bodyguard"), "pet_count"))', ground)
        self.assertIn("RunShare(origin.GetExactDist2d(center), reach)", ground)
        self.assertIn('Tune("phalanx_charge_distance_yards")', ground)
        self.assertIn("rune == Rune::Stampede ? HorseEntry : AvatarEntry", ground)
        self.assertIn("mind->Run(across(end, side), rate, arrival);", ground)
        self.assertIn("case Behavior::Follow: case Behavior::Fight:", ground)
        self.assertIn("mind->Follow(i);", ground)
        self.assertIn("case Behavior::Stand:", ground)
        self.assertIn('Tune("phalanx_shield_bearers_seconds")', ground)
        self.assertEqual(ground.count("Arrival>()"), 1)  # one shared bash for the whole charge

    def test_shield_bearers_hold_their_place_against_crossing(self):
        ground = self.code[self.code.index("void Ground("):self.code.index("void RegisterScripts(")]
        self.assertIn("if (rune == Rune::ShieldBearers)", ground)
        self.assertIn('Tune("phalanx_shield_bearers_radius_yards")', ground)
        hold = self.code[self.code.index("void Hold("):self.code.index("bool Is(")]
        self.assertIn("Consecration::Crossed(seen->second.inside, distance, radius)", hold)
        self.assertIn("enemy->NearTeleportTo(", hold)
        self.assertIn("Now() >= until", hold)
        self.assertIn("CheckEvery()", hold)


if __name__ == "__main__":
    unittest.main()

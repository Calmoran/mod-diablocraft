"""The source-text guards of events: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_events.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source
import generate_legendary_powers as generator
from test_item_power_events import MATH, SRC  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.math = MATH.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.passives = (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8")
        cls.abilities = barbarian_source.abilities((".cpp",))
        cls.primaries = (SRC / "classes/barbarian/dc_barbarian_primaries.cpp").read_text(encoding="utf-8")

    def test_each_event_is_fired_from_one_place(self):
        fired = set(re.findall(r'Fire\(\w+, "(\w+)"', self.powers))
        # `resource_spent` (xf9oy) is not fired through Fire: ItemPowers::Spent drives SpentFires; test_item_power_immortal_kings_call_set.py pins its one call site.
        # The `control_*` events (n8m1a) are fired by one call with the name ItemPower::ControlEvent gives: test_item_power_hellrack.py pins it
        self.assertEqual(set(generator.EVENTS) - {"resource_spent"} - set(generator.CONTROL_EVENTS), fired)
        # the call sites: a pressed cast after the core installed the cooldown, a hit, a hit taken, a kill
        cast = self.combat[self.combat.index("void OnSpellCast("):self.combat.index("void OnSpellCheckCast(")]
        self.assertIn("if (player && row && !spell->IsTriggered())\n                    ItemPowers::Cast(player, info->Id);", cast)
        hit = self.passives[self.passives.index("void Hit(Player* p, Unit* target"):self.passives.index("void Taken(")]
        self.assertIn("ItemPowers::Hit(p, target, spellId);", hit)
        taken = self.passives[self.passives.index("void Taken("):self.passives.index("void RegisterScripts(")]
        self.assertIn("ItemPowers::Taken(p);", taken)
        self.assertIn("PLAYERHOOK_ON_CREATURE_KILL", self.powers)
        kill = self.powers[self.powers.index("void OnPlayerCreatureKill("):]
        kill = kill[:kill.index("void OnPlayerLogout(")]
        self.assertIn('Fire(killer, "kill", "", 1.0, killed);', kill)   # the killed creature is the event's enemy (Ahavarion's creature-type condition)
        self.assertIn("killed->isElite() || DC::Rifts::IsPromotedElite(killed)", kill)   # the elite test the loot and the damage formula use
        self.assertIn('Fire(killer, "kill_elite"', kill)

    def test_a_hit_is_classified_by_the_skill_sheets_numbers_and_rolls_by_its_coefficient(self):
        hit = self.powers[self.powers.index("void Hit(Player* player, Unit* target, std::uint32_t spellId)"):self.powers.index("void Taken(Player* player)")]
        for token in ("cost_resource", "generated_resource"):
            self.assertIn('"%s"' % token, hit)
        self.assertIn("Combat::ProcCoefficient(spellId)", hit)   # the spell's coefficient, or the pet's own while a pet's blow lands
        self.assertIn('Classes::CategoryOf(spellId) == "Primary"', hit)
        self.assertIn("coefficient && *coefficient > 0 ? *coefficient : 0", hit)   # no coefficient, no proc (dc_proc_math.h)

    def test_each_effect_has_its_executor_and_each_player_stat_its_reader(self):
        for stat in generator.EFFECT_STATS:
            self.assertIn('one.stat == "%s"' % stat, self.powers)
        self.assertIn("Abilities::CutRunningCooldown(player, one.value * 1000.0);", self.powers)   # seconds in, milliseconds out (waoo8)
        self.assertIn("Primaries::GrantFrenzy(player, static_cast<unsigned>(one.value));", self.powers)
        for stat in generator.PLAYER_STATS:
            self.assertTrue('"%s"' % stat in self.powers or '"%s"' % stat in self.math, stat)
        # the damage taken multiplies the reduction in
        incoming = self.powers[self.powers.index("double IncomingFactor(Player const* player)"):self.powers.index("double DealtFactor(")]
        self.assertIn("ItemPower::ReductionFactor(", incoming)

    def test_the_cooldown_a_skill_starts_is_cut_only_when_its_record_states_one(self):
        cast = self.powers[self.powers.index("void Cast(Player* player, std::uint32_t spellId)"):self.powers.index("void Hit(Player* player")]
        self.assertIn("info->RecoveryTime || info->CategoryRecoveryTime", cast)
        self.assertIn('Classes::CategoryOf(spellId) == "Primary"', cast)
        # the seconds are read in CooldownCut (one place for Cast and for Lut Socks' end of window, diablocraft-y27fd)
        self.assertIn("double const cut = CooldownCut(player);", cast)
        reader = self.powers[self.powers.index("double CooldownCut(Player* player)"):self.powers.index("void StartCooldown(")]
        self.assertIn('ItemPower::PlayerSum(Data().rows, CountsOf(guid), "cooldown_reduction_seconds"', reader)
        self.assertIn("Abilities::ReduceSkillCooldown(", cast)
        cut = self.abilities[self.abilities.index("bool CutRunningCooldown("):]
        cut = cut[:cut.index("void InvalidateBar(")]
        self.assertIn('Classes::CategoryOf(r.id) == "Primary"', cut)
        self.assertIn("info->RecoveryTime || info->CategoryRecoveryTime", cut)
        self.assertIn("urand(0, running.size() - 1)", cut)

    def test_frenzy_is_granted_to_its_maximum_and_with_a_fresh_timer(self):
        grant = self.primaries[self.primaries.index("void GrantFrenzy("):]
        grant = grant[:grant.index("class dc_primary_spell")]
        self.assertIn("unsigned const cap = MaxStacks(player);", grant)   # Frenzy's limit: its own 5, or Bastion's Revered's 10
        self.assertIn("std::min(std::max(held, stacks), cap)", grant)
        self.assertIn("buff.frenzyAt = getMSTime();", grant)
        self.assertIn("ShowFrenzy(player, shown);", grant)

    def test_the_fire_clock_is_per_player_and_forgotten_at_logout(self):
        self.assertIn("clocks[guid].fired = std::move(situation.fired);", self.powers)
        self.assertIn("situation.fired = mine->second.fired;", self.powers)
        self.assertIn("clocks.erase(player->GetGUID().GetRawValue());", self.powers)


if __name__ == "__main__":
    unittest.main()

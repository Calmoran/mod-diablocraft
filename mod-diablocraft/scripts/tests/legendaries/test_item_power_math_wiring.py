"""The source-text guards of math: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_math.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from split_sources import affixes_text
import barbarian_source
import generate_legendary_powers as generator
from test_item_power_math import REPO, SRC  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.abilities = barbarian_source.abilities((".cpp",))
        cls.ancients = (SRC / "classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8")

    def test_each_new_number_has_its_reader(self):
        speed = self.combat[self.combat.index("double HandAttacksPerSecond("):self.combat.index("std::pair<double, double> WeaponRange(")]
        self.assertIn('ItemPowers::SkillFactor(player, ability->skill, "attack_speed_pct")', speed)
        compute = self.combat[self.combat.index("bool ComputeHit("):self.combat.index("std::string Hit::Describe()")]
        elemental = compute[compute.index("hit.elemental = "):compute.index("hit.elite = ")]
        self.assertIn("ItemPowers::ElementBonus(player, shell.element)", elemental)       # into the elemental bonus, not a multiplier
        self.assertLess(compute.index("Wizard::Element(player, shell.spellId)"), compute.index("ItemPowers::ElementBonus"))   # Archon's element first
        self.assertIn('ItemPower::ElementSum(Data().rows, CountsOf(guid), element, "damage_pct"', self.powers)
        self.assertEqual(("damage_pct", "cost_reduction_pct", "damage_per_distance_pct", "distance_step_yards", "distance_cap_yards",
                          "damage_prevented_pct", "heal_of_prevented_pct"),
                         generator.ELEMENT_STATS)   # the second is Cindercoat's (5cqu3), the next three Starfire's (mcrtc), the last two Countess Julia's Cameo's (sjdct)
        self.assertIn("attack_speed_pct", generator.SKILL_STATS)
        self.assertEqual(("freeze", "root", "ground_effects"), generator.IMMUNITIES)   # the last is World's ground mark (vix14)

    def test_the_players_own_state_is_read_before_the_lock(self):
        # the summons answer under a lock of their own, so Seen runs before the item powers' mutex is taken, in every reader of a condition
        self.assertEqual(self.powers.count("SituationOf(guid, std::move(seen))"), self.powers.count("ItemPower::Situation seen = Seen(player);"))
        self.assertEqual(32, self.powers.count("ItemPower::Situation seen = Seen(player);"))   # the twenty-third and twenty-fourth are Blood Brother's BlockBonus and BlockedFactor (jxvsn); the tenth is PassiveSetTo (tt86k), the eleventh Starfire's (mcrtc), the twelfth Dishonored Legacy's (a2rln), the thirteenth and fourteenth Blade of the Warlord's ResourceSpend and SpentFactor (nsbac); the next is Pride of Cassius' DurationSeconds (yep9j); the sixteenth is Homing Pads' TownPortalFactor (9ebp6); the seventeenth Immortal King's Call's Spent (xf9oy); the eighteenth Serpent's Sparker's ActiveCount (1zocv); the nineteenth is Orb of Infinite Depth's DealtFactor; the twentieth Envious Blade's CritBonus (i2d92), the twenty-first Fjord Cutter's TargetFactor (5i88h), the twenty-second Standoff's DerivedFactor (r2lly); the twenty-fifth is Monkey King's Garb's PerStackFactor (w7wes); the twenty-sixth is Countess Julia's Cameo's Prevent (sjdct); the twenty-seventh is Gloves of Worship's ShrineSeconds (4y1jn); the twenty-eighth is Fleshrake's StackedSkillFactor (k2yzl); the twenty-ninth and thirtieth are Hexing Pants' DamageBonus and GenerationFactor (7ksnv)
        self.assertEqual(self.powers.count("ItemPower::Situation seen = Seen(player);"),
                         len(re.findall(r"ItemPower::Situation seen = Seen\(player\);\n\s*(?:\{\n\s*)?std::lock_guard<std::mutex> lock\(mutex\);", self.powers)))
        self.assertEqual(8, self.powers.count("SituationOf(guid)"))                          # the immunities, the element and the skill cost auras (5cqu3, e0pt4), Gesture of Orpheus's CooldownFactor (1i52b), Boots of Disregard's StandStill, Aether Walker's added cost aura (iv3xg), Ancient Parthan Defenders' StunScan (lqe1r), Heart of Iron's VitalityThorns (tgiih): no condition
        self.assertEqual(8, self.powers.count("SituationOf(guid)"))                          # the immunities, the element and the skill cost auras (5cqu3, e0pt4), Gesture of Orpheus's CooldownFactor (1i52b), Boots of Disregard's StandStill, Aether Walker's added cost aura (iv3xg), Pride's Fall's NoDamageCost (pruc8), Rogar's Huge Stone's MissingLifeRegen (sifvi): no condition
        seen = self.powers[self.powers.index("ItemPower::Situation Seen(Player const* player)"):self.powers.index("ItemPower::Situation SituationOf(")]
        self.assertIn("for (std::string const& skill : Data().watched)", seen)
        self.assertIn("if (Data().resource)", seen)
        self.assertIn("Resources::Of(Classes::ClassIdOf(player))", seen)                   # the class's own primary resource, no class named
        # lp4uv: nothing is looked at when no row reads it, or for a player who wears nothing that owns a power (every hit of every player
        # comes through here); both answers come before the skills are walked
        guard = seen.index("if (!clocks.count(guid) && !counts.count(guid))\n                    return situation;")
        self.assertLess(seen.index("if (Data().watched.empty() && !Data().resource && !Data().life && !Data().moves)\n                return situation;"), guard)
        self.assertLess(guard, seen.index("for (std::string const& skill : Data().watched)"))

    def test_an_active_skill_is_its_buff_or_its_living_ancients(self):
        active = self.abilities[self.abilities.index("bool SkillActive(Player const* p, std::string const& skill)"):self.abilities.index("bool WhirlwindActive(")]
        self.assertIn('if (skill == "Call of the Ancients")\n            return Classes::Ancients::Active(p);', active)
        self.assertIn("return Buff(p, skill.c_str()) != nullptr;", active)                # the file's own buff lookup, not a copy of it
        buff = self.abilities[self.abilities.index("Row const* Buff(Unit const* p, char const* skill)"):self.abilities.index("double Tune(char const* key)")]
        self.assertIn("p->HasAura(AuraId(r.id))", buff)
        body = self.ancients[self.ancients.index("bool Active(Player const* p)"):self.ancients.index("void Spent(")]
        self.assertIn("std::lock_guard<std::recursive_mutex> guard(mutex);", body)
        self.assertIn("!Living(p).empty()", body)

    def test_the_immunities_follow_the_worn_items_under_a_key_of_their_own(self):
        refresh = self.powers[self.powers.index("void Refresh(Player* player, Item* changed"):self.powers.index("std::vector<double> WornRolls(")]
        self.assertTrue(refresh.rstrip().endswith("Immunize(player);\n        CostAuras(player);\n        DropStacks(player);\n    }"))
        self.assertRegex(self.powers, r"constexpr std::uint32_t ImmuneKey = [1-9]\d*;")
        self.assertIn("player->ApplySpellImmune(ImmuneKey, IMMUNITY_MECHANIC, mechanic, on);", self.powers)
        self.assertIn("player->ApplySpellImmune(ImmuneKey, IMMUNITY_STATE, SPELL_AURA_MOD_ROOT, on);", self.powers)
        self.assertIn('Mechanics const mechanic = control == "freeze" ? MECHANIC_FREEZE : MECHANIC_ROOT;', self.powers)
        self.assertIn("immune.erase(player->GetGUID().GetRawValue());", self.powers)          # forgotten at logout

    def test_freeze_refuses_the_hold_torment_freezes_with(self):
        # lp4uv: Torment's freeze on a player is the Frozen elite's hold, landed by ApplyHold through AddAura (which asks IsImmunedToSpell).
        # Its record is a Stun-mechanic MOD_STUN, so MECHANIC_FREEZE does not refuse it: freeze also refuses it by id.
        elites = affixes_text()
        hold = int(re.search(r"constexpr std::uint32_t FREEZE_HOLD = (\d+);", elites).group(1))
        self.assertIn("ApplyHold(source, player, FREEZE_HOLD, h.freezeMs)", elites)
        apply = elites[elites.index("bool ApplyHold("):]
        self.assertIn("source->AddAura(donor, player)", apply[:apply.index("\n}\n")])
        self.assertEqual(hold, int(re.search(r"constexpr std::uint32_t FreezeHold = (\d+);", self.powers).group(1)))
        immunize = self.powers[self.powers.index("void Immunize(Player* player, std::string const& control, bool on)"):
                               self.powers.index("void Immunize(Player* player)\n")]
        self.assertIn('if (control == "freeze")\n                player->ApplySpellImmune(ImmuneKey, IMMUNITY_ID, FreezeHold, on);', immunize)
        # one already on goes when the boots go on: the hold by its id, a root aura by its type (the Jailer's 53077 carries no mechanic)
        self.assertIn("player->RemoveAurasDueToSpell(FreezeHold);", immunize)
        self.assertIn("player->RemoveAurasByType(SPELL_AURA_MOD_ROOT);", immunize)
        self.assertNotIn("MECHANIC_STUN", immunize)                                            # every other stun still lands
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if dbc.is_file():
            import struct
            raw = dbc.read_bytes()
            _, count, fields, size, _ = struct.unpack("<4s4I", raw[:20])
            records = {v[0]: v for v in (struct.unpack_from(f"<{fields}I", raw, 20 + i * size) for i in range(count))}
            self.assertEqual((12, 12), (records[hold][3], records[hold][95]))                    # mechanic STUN, aura MOD_STUN: not Freeze
            self.assertEqual((0, 26), (records[53077][3], records[53077][95]))                   # the Jailer's root: no mechanic, MOD_ROOT


if __name__ == "__main__":
    unittest.main()

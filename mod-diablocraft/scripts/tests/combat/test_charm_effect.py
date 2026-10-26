"""The shared charm: a monster charmed to fight for a player (src/combat/dc_charm_effect_math.h, dc_charm_effect.h and .cpp).

What this proves, and how:

  * **The rules that need no core type.** tests/charm_effect/harness.cpp compiles the real dc_charm_effect_math.h: an enemy
    monster is charmed; a player, a dead monster, a friend, a charmed one, a player's pet, a boss and a charm of no time are
    not; a roll charms under the chance and never at it; the monster is sent at the nearest foe. Fifteen mutations planted in
    a scratch copy must each make it fail.
  * **The apply path does what the rules say, in order.** The text of dc_charm_effect.cpp: the target is described from the
    core's own flags (enemy, charmed, player-controlled, world or dungeon boss, rift Guardian) and the rules answer before
    the aura is put on; the aura is the stock charm, the charm must be the master's before the length is set, and a charm
    that did not take hold takes its aura off; the monster is sent at the nearest enemy and the core carries on from there.
  * **The stock charm is what the code says.** The client's Spell.dbc: "Gnomish Mind Control Cap" (26740) is one apply-aura
    effect of SPELL_AURA_AOE_CHARM with the Charm mechanic, so the Juggernaut and the Guardian refuse it (the rifts' World
    contract names the mechanic 30, but the core's MECHANIC_CHARM is 1: 30 is Sapped).
  * **It names no class.** The shared folder holds no class name (AGENTS.md R1).

What it does not prove: the core's charm on a running server, and that the Juggernaut and the Guardian refuse it.

    python mod-diablocraft/scripts/tests/combat/test_charm_effect.py
"""

import csv
import re
import struct
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/combat/dc_charm_effect_math.h"
SOURCES = [HEADER, "tests/charm_effect/harness.cpp"]
CODE = MODULE / "src/combat/dc_charm_effect.cpp"
API = MODULE / "src/combat/dc_charm_effect.h"
CHARM_HOLD = 26740
SPELL_AURA_AOE_CHARM, MECHANIC_CHARM = 177, 1


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def uncertainty(token):
    rows = [r for r in read(D3 / "crusader_skill_values.csv")
            if (r["skill"], r["rune"], r["token"]) == ("Shield Glare", "Uncertainty", token)]
    assert len(rows) == 1, token
    return float(rows[0]["value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/charm_effect/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary), str(uncertainty("proc_chance_pct")), str(uncertainty("charm_duration_seconds"))],
                           capture_output=True, text=True)


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a charm of no time takes", (HEADER, "seconds > 0 && ", "")),
            ("a player is charmed", (HEADER, "target.creature && ", "")),
            ("a dead monster is charmed", (HEADER, "target.alive && ", "")),
            ("a friend is charmed", (HEADER, "target.hostile && ", "")),
            ("a charmed monster is charmed again", (HEADER, "!target.alreadyCharmed &&", "true &&")),
            ("a pet is charmed", (HEADER, "!target.controlledByPlayer && ", "")),
            ("a boss is charmed", (HEADER, "!target.boss;", "true;")),
            ("a roll at the chance charms", (HEADER, "roll < chancePct", "roll <= chancePct")),
            ("no chance charms", (HEADER, "chancePct > 0 && ", "")),
            ("a monster with a live fight is sent again", (HEADER, "return !hasVictim || !victimAlive;", "return !hasVictim && !victimAlive;")),
            ("a player charmer is nobody's master", (HEADER, "if (charmer.player)\n            return Master::Charmer;", "if (false)\n            return Master::Charmer;")),
            ("a holder a monster summoned is a master", (HEADER, "charmer.holder && charmer.summonerPlayer ?", "charmer.holder ?")),
            ("a player's other summon is a master", (HEADER, "charmer.holder && charmer.summonerPlayer ?", "charmer.summonerPlayer ?")),
            ("a tie goes to the last", (HEADER, "distances[i] < distances[*best]", "distances[i] <= distances[*best]")),
            ("the farthest foe is the target", (HEADER, "distances[i] < distances[*best]", "distances[i] > distances[*best]")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))

    def test_the_target_is_described_from_the_cores_flags(self):
        describe = self.code[self.code.index("Target Describe("):self.code.index("bool Send(")]
        for flag in ("master->IsValidAttackTarget(creature)", "creature->IsCharmed()", "creature->IsControlledByPlayer()",
                     "creature->isWorldBoss()", "creature->IsDungeonBoss()", "DC::Rifts::IsGuardianEntry(creature->GetEntry())",
                     "creature->IsAlive()"):
            self.assertIn(flag, describe)

    def test_the_rules_answer_before_anything_is_summoned_and_the_charm_must_be_the_holders(self):
        apply = self.code[self.code.index("bool Apply("):]
        self.assertIn("Creature* creature = target ? target->ToCreature() : nullptr;", apply)
        self.assertLess(apply.index("CanCharm(Describe(master, creature), seconds)"), apply.index("master->SummonCreature(Holder,"))
        self.assertLess(apply.index("master->SummonCreature(Holder,"), apply.index("holder->AddAura(CharmHold, creature)"))
        self.assertIn("if (!charm || creature->GetCharmerGUID() != holder->GetGUID())", apply)
        self.assertIn("creature->RemoveAura(charm);", apply)
        self.assertIn("holder->DespawnOrUnsummon();", apply)
        self.assertLess(apply.index("GetCharmerGUID() != holder->GetGUID()"), apply.index("charm->SetMaxDuration(int32(ms));"))
        self.assertIn("charm->SetDuration(int32(ms));", apply)
        self.assertLess(apply.index("SetDuration("), apply.index("Send(master, creature, spellId);"))

    def test_each_charm_has_a_holder_of_its_own_and_the_player_is_never_the_charmer(self):
        # The core gives a PLAYER one charm (Unit::SetCharmedBy ends the earlier one); a creature holds any number. So the
        # charmer is a holder summoned for this charm and on the player's side, never the player.
        self.assertEqual(self.code.count("master->SummonCreature(Holder,"), 1)
        self.assertIn("constexpr std::uint32_t Holder = 12999;", self.code)
        self.assertIn("holder->SetFaction(master->GetFaction());", self.code)
        self.assertNotIn("master->AddAura(", self.code)
        self.assertNotIn("StopCastingCharm", self.code)
        self.assertIn("TEMPSUMMON_TIMED_DESPAWN, ms + GraceMs)", self.code)

    def test_a_look_keeps_the_charm_to_its_master_and_its_aura(self):
        look = self.code[self.code.index("void Look("):self.code.index("bool Apply(")]
        for text in ("ObjectAccessor::GetPlayer(*holder, master)", "!player->IsAlive()", "!creature->IsAlive()",
                     "creature->GetCharmerGUID() != holder->GetGUID()", "holder->DespawnOrUnsummon();",
                     "Retarget(victim != nullptr, victim && victim->IsAlive())", "Send(player, creature, spellId)",
                     "holder->NearTeleportTo("):
            self.assertIn(text, look)
        self.assertIn("holder->m_Events.AddEventAtOffset(", look)

    def test_the_monster_is_sent_at_the_nearest_enemy_and_the_core_carries_on(self):
        send = self.code[self.code.index("bool Send("):self.code.index("void Look(")]
        self.assertIn("Combat::Enemies(master, spellId, creature->GetPosition(), creature->GetVisibilityRange())", send)
        self.assertIn("NearestFoe(distances)", send)
        self.assertIn("creature->GetCharmInfo()->SetIsCommandAttack(true);", send)
        self.assertIn("creature->Attack(foes[*nearest], true);", send)
        self.assertIn("creature->GetMotionMaster()->MoveChase(foes[*nearest]);", send)

    def test_the_apply_is_declared_with_the_master_the_target_the_spell_and_the_seconds(self):
        self.assertIn("bool Apply(Player* master, Unit* target, std::uint32_t spellId, double seconds);",
                      squeeze(API.read_text(encoding="utf-8")))

    def test_the_shared_charm_names_no_class_and_no_class_skill(self):
        for path in (CODE, API, MODULE / HEADER):
            text = path.read_text(encoding="utf-8")
            for name in ("Crusader", "Barbarian", "Monk", "Wizard", "Necromancer", "Witch Doctor", "Demon Hunter", "Stupefy",
                         "Uncertainty", "Shield Glare"):
                self.assertNotIn(name, text, f"{path.name} names {name}")


class TheCoresCharmSlots(unittest.TestCase):
    """Why each charm has a holder: the core limits a PLAYER charmer to one charm and a creature to none."""

    UNIT = REPO / "azerothcore-wotlk/src/server/game/Entities/Unit/Unit.cpp"

    def setUp(self):
        if not self.UNIT.is_file():
            raise unittest.SkipTest("no core source")
        self.text = self.UNIT.read_text(encoding="utf-8", errors="replace")

    def test_a_player_charmer_ends_its_earlier_charm_and_holds_one(self):
        charmed_by = self.text[self.text.index("bool Unit::SetCharmedBy("):self.text.index("void Unit::RemoveCharmedBy(")]
        block = charmed_by[charmed_by.index("// Charmer stop charming"):]
        guard = squeeze(block[:block.index("}")])
        self.assertIn("if (playerCharmer) { playerCharmer->StopCastingCharm(", guard)
        set_charm = self.text[self.text.index("void Unit::SetCharm("):]
        player_branch = set_charm[:set_charm.index("else\n        {")]
        self.assertIn("AddGuidValue(UNIT_FIELD_CHARM", player_branch)

    def test_a_creature_charmer_holds_any_number(self):
        set_charm = self.text[self.text.index("void Unit::SetCharm("):self.text.index("_isWalkingBeforeCharm = charm->IsWalking();")]
        creature_branch = set_charm[set_charm.index("else\n        {"):]
        self.assertNotIn("UNIT_FIELD_CHARM,", creature_branch)
        self.assertIn("m_Controlled.insert(charm);", self.text[self.text.index("void Unit::SetCharm("):][:3000])


class StockRecords(unittest.TestCase):
    def test_the_charm_hold_is_one_aoe_charm_with_the_charm_mechanic(self):
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if not dbc.is_file():
            raise unittest.SkipTest("no client Spell.dbc")
        self.assertIn(f"constexpr std::uint32_t CharmHold = {CHARM_HOLD};", CODE.read_text(encoding="utf-8"))
        data = dbc.read_bytes()
        _magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
        self.assertEqual(fields, 234)
        for i in range(count):
            row = struct.unpack_from("<%dI" % fields, data, 20 + i * size)
            if row[0] == CHARM_HOLD:
                self.assertEqual((row[71], row[72], row[73]), (6, 0, 0))       # one SPELL_EFFECT_APPLY_AURA
                self.assertEqual(row[95], SPELL_AURA_AOE_CHARM)
                self.assertEqual(row[3], MECHANIC_CHARM)
                return
        self.fail(f"no spell {CHARM_HOLD}")


if __name__ == "__main__":
    unittest.main()

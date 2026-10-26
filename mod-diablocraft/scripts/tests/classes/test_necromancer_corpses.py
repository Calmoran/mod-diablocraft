"""The Necromancer's side of the corpses: whose kills leave one, and for whom (src/classes/necromancer/dc_necromancer_corpses.cpp).

What this proves, and how (the text of the production files; the rules themselves are tests/corpses, test_corpses.py):

  * **A Necromancer is found from data.** The class is the Essence row's class id in dc_resource_data.h, which the
    resource generator writes from class_resources.csv; no WoW class constant is named.
  * **Whose kill it is.** The credited player is the killer, the player a minion or guardian belongs to, or the master of
    a charmed monster; a death with none leaves nothing.
  * **For whom.** Every Necromancer of that player's party on the dead monster's map, alive and in the world, gets one
    corpse at the death spot with the creature's entry and the guid of its dead body (diablocraft-cuqa4: the body is the
    corpse, and goes when the corpse is used or expires); the rule of which deaths leave one is the shared Leaves.
  * **It is wired.** The class's RegisterScripts is called from Combat's, beside the shared corpses' own.

What it does not prove: a kill on a running server, or the look of a corpse (a card for the designer).

    python mod-diablocraft/scripts/tests/classes/test_necromancer_corpses.py
"""

import csv
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
FOLDER = MODULE / "src/classes/necromancer"
CODE = FOLDER / "dc_necromancer_corpses.cpp"


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Kills(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))

    def test_the_class_is_the_essence_rows_class_not_a_constant(self):
        self.assertIn('Resources::Find("Necromancer", "essence")', self.code)
        self.assertIn("Classes::ClassIdOf(player) == essence.classId", self.code)
        self.assertNotRegex(self.code, r"\bCLASS_[A-Z]+\b")
        self.assertNotIn("getClass()", self.code)

    def test_the_essence_row_is_the_necromancers_in_the_class_map(self):
        with (MODULE / "data/d3/class_map.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = {row["d3_class"]: row for row in csv.DictReader(stream)}
        data = (MODULE / "src/classes/dc_resource_data.h").read_text(encoding="utf-8")
        match = re.search(r'\{(\d+), "Necromancer", "essence"', data)
        self.assertIsNotNone(match, "no Essence row")
        self.assertEqual(match.group(1), rows["Necromancer"]["class_id"])

    def test_the_credited_player_is_the_killer_the_owner_or_the_master(self):
        credited = self.code[self.code.index("Player* PlayerBehind("):self.code.index("// The killer and its party")]
        self.assertIn("killer->GetCharmerOrOwnerPlayerOrPlayerItself()", credited)
        self.assertIn("CharmEffect::MasterOf(killer)", credited)
        self.assertLess(credited.index("GetCharmerOrOwnerPlayerOrPlayerItself"), credited.index("MasterOf"))

    def test_the_party_is_on_the_dead_monsters_map_alive_and_in_the_world(self):
        party = self.code[self.code.index("std::vector<Player*> Party("):self.code.index("class Kills")]
        for text in ("killer->GetGroup()", "group->GetFirstMember()", "member != killer", "member->IsAlive()",
                     "member->IsInWorld()", "member->GetMap() == victim->GetMap()"):
            self.assertIn(text, party)

    def test_a_death_leaves_one_corpse_for_each_necromancer_at_the_death_spot(self):
        hook = self.code[self.code.index("void OnUnitDeath("):]
        self.assertIn("victim ? victim->ToCreature() : nullptr", hook)
        self.assertIn("death.controlledByPlayer = creature->IsControlledByPlayer();", hook)
        self.assertIn("if (!Corpses::Leaves(death)) return;", hook)
        self.assertLess(hook.index("Leaves(death)"), hook.index("Corpses::Leave(member"))
        # The corpse is the monster's own dead body (diablocraft-cuqa4): its guid is in the record, so the body goes with it.
        self.assertIn("if (IsNecromancer(member)) Corpses::Leave(member, creature->GetPosition(), creature->GetEntry(), "
                      "creature->GetGUID().GetRawValue());", hook)
        self.assertIn("if (!creature || !credited) return;", hook)

    def test_a_corpse_gives_no_progress_and_no_loot(self):
        for text in ("SummonCreature", "SummonGameObject", "loot", "Loot", "KilledMonsterCredit", "rift", "Rift"):
            self.assertNotIn(text, self.code)


class SkillMadeBodies(unittest.TestCase):
    def test_the_body_a_skill_makes_is_not_a_kill(self):
        """The dead body made for a skill's corpse (q-1021-63 b) dies by itself while the shared piece says it is being made; the kill hook
        leaves it out, so it never leaves a second corpse."""
        hook = squeeze((FOLDER / "dc_necromancer_corpses.cpp").read_text(encoding="utf-8"))
        self.assertIn("if (creature->GetGUID().GetRawValue() == Corpses::BodyBeingMade()) return;", hook)
        self.assertLess(hook.index("Corpses::BodyBeingMade()"), hook.index("Corpses::Leaves(death)"))

    def test_every_corpse_a_skill_makes_gets_a_body(self):
        """The four places a Necromancer skill makes a corpse call LeaveMade, never the bodiless Leave."""
        total = 0
        for path in FOLDER.glob("*.cpp"):
            text = squeeze(path.read_text(encoding="utf-8"))
            for call in re.findall(r"Corpses::Leave(?:Made)?\(", text):
                total += 1
            if path.name != "dc_necromancer_corpses.cpp":
                self.assertNotIn("Corpses::Leave(", text, path.name)
        self.assertEqual(total, 5)  # the kill hook's Leave, and the four skills' LeaveMade

    def test_a_skill_made_body_is_never_a_dead_monsters_own_entry(self):
        """Purgatory's corpse says which monster it was but its body is not that monster (Reviewer epdfp, diablocraft-y7597).

        A fresh summon of a family monster gets the family AI, whose death fires its death abilities (spiderlings, a suicide
        bomb, a hazard), and a stock creature runs its own scripts; so the only body a skill names is its own dc_minion
        template (the Golem's), and every other skill-made corpse gets the shared stand-in.
        """
        calls = {}
        for path in FOLDER.glob("*.cpp"):
            text = squeeze(path.read_text(encoding="utf-8"))
            for args in re.findall(r"Corpses::LeaveMade\(([^;]*)\);", text):
                calls.setdefault(path.name, []).append([a.strip() for a in args.split(",")])
        self.assertEqual(sorted(calls), ["dc_necromancer_blood_rush.cpp", "dc_necromancer_command_golem.cpp",
                                         "dc_necromancer_pets.cpp"])
        for name, found in calls.items():
            for args in found:
                if name == "dc_necromancer_command_golem.cpp":
                    self.assertEqual(args, ["player", "center", "GolemEntry", "GolemEntry"])
                else:
                    self.assertLessEqual(len(args), 3, f"{name}: no skill body named, so the stand-in is the body")
        scripts = {row["entry"]: row["script"] for row in csv.DictReader(
            (MODULE / "data/d3/necromancer_summons.csv").open(encoding="utf-8"))}
        self.assertEqual(scripts["900152"], "dc_minion")  # the Golem's template, the one body a skill names
        self.assertEqual(scripts["900153"], "dc_minion")  # the stand-in the tunable names


class Registered(unittest.TestCase):
    def test_the_class_registers_its_hook_and_combat_registers_the_class_and_the_shared_scripts(self):
        dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))
        self.assertIn("KillCorpses::RegisterScripts();", dispatch)
        combat = squeeze((MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))
        self.assertIn("Crusader::RegisterScripts(); Necromancer::RegisterScripts(); DemonHunter::RegisterScripts(); WitchDoctor::RegisterScripts(); Shaman::RegisterScripts(); Corpses::RegisterScripts();", combat)
        internal = (MODULE / "src/combat/dc_combat_internal.h").read_text(encoding="utf-8")
        self.assertIn('#include "../classes/necromancer/dc_necromancer.h"', internal)
        self.assertIn('#include "dc_corpses.h"', internal)


if __name__ == "__main__":
    unittest.main()

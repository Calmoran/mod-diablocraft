"""Ignore Pain and Nerves of Steel carry the control immunity on their records; Vanguard and the Armors follow the stock
rules (diablocraft-aura-fixes, aura review rows 5, 4 and 9; ruling q-1003-11 and 2026-10-03).

    python3 mod-diablocraft/scripts/tests/combat/test_control_immunity_records.py

Row 5 (R1): the module filled the core's immunity list with ApplySpellImmune and stripped holds by hand. Now the marker
records carry it: effect 2 is aura 147 (misc 96, amount 1: this core's stock "immune to every control" lookup, which
gives the aura types stun, root, fear, confuse and decrease-speed and twelve mechanics) and effect 3 is aura 77 for
silence, with SPELL_ATTR1_IMMUNITY_PURGES_EFFECT so the cast strips the holds already on. Knockout and daze are not
carried (ruling 2026-10-03; test_control_immunity_gap.py is the guard that nothing applies them).
Row 4: Vanguard 81195 was a second MOD_INCREASE_SPEED; it is a DUMMY display buff now, the speed is the aggregate's.
Row 9: the Wizard's Armors are one spell_group with the EXCLUSIVE stack rule, not a removal loop.

The records are read out of the generated spell_shells.sql (what the migration carries), and the immunity they give is
worked out the way the core does it (SpellInfo::_LoadImmunityInfo, restated below) and set against the aura types the
holds use. What this does not run: the core's loader, AddAura, or the client's tray.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_control_immunity_gap import insert_rows, number
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import wizard_source  # noqa: E402
import barbarian_source  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
GENERATED = MODULE / "data" / "generated" / "spell_shells.sql"
UPDATES = MODULE / "data/sql/db-world/updates"
FULL_REPLACEMENT = "DELETE FROM `spell_dbc` WHERE `ID` BETWEEN"   # what test_primaries calls a full spell migration
SHELLS_CSV = MODULE / "data" / "generated" / "spell_shells.csv"

SPELL_EFFECT_APPLY_AURA = 6
AURA_DUMMY, AURA_MOD_INCREASE_SPEED = 4, 31
AURA_MECHANIC_IMMUNITY, AURA_MECHANIC_IMMUNITY_MASK = 77, 147
ATTR1_IMMUNITY_PURGES_EFFECT = 0x8000
MECHANIC = {"charm": 1, "disoriented": 2, "fear": 5, "root": 7, "silence": 9, "sleep": 10, "snare": 11, "stun": 12,
            "freeze": 13, "knockout": 14, "polymorph": 17, "horror": 24, "turn": 23, "sapped": 30,
            "daze": 27}
# The aura types a hold is, and the donors the elite holds use (dc_rift_elites.cpp): fear, stun, root.
HOLD_AURA_TYPES = {7: "fear", 12: "stun", 26: "root"}


def immunity_of(row):
    """What a record's effects give a unit that carries the aura, restating the core's _LoadImmunityInfo for 147 and 77:
    147 with MiscValue 96 and a nonzero amount is the stock all-controls set; 77 is the one mechanic in MiscValue."""
    states, mechanics = set(), set()
    for slot in (1, 2, 3):
        if number(row.get("Effect_%d" % slot)) != SPELL_EFFECT_APPLY_AURA:
            continue
        aura, misc = number(row.get("EffectAura_%d" % slot)), number(row.get("EffectMiscValue_%d" % slot))
        amount = number(row.get("EffectBasePoints_%d" % slot)) + number(row.get("EffectDieSides_%d" % slot))
        if aura == AURA_MECHANIC_IMMUNITY_MASK and misc == 96 and amount:
            states |= {12, 33, 26, 5, 7}                      # stun, decrease speed, root, confuse, fear
            mechanics |= {MECHANIC[m] for m in ("snare", "root", "fear", "stun", "sleep", "charm", "sapped", "horror",
                                                 "polymorph", "disoriented", "freeze")}
            mechanics.add(23)                                  # turn
        elif aura == AURA_MECHANIC_IMMUNITY and misc >= 1:
            mechanics.add(misc)
    return states, mechanics


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = GENERATED.read_text(encoding="utf-8")
        cls.text = text
        cls.rows = {int(row["ID"]): row for row in insert_rows(text, "spell_dbc")}
        names = {}
        for line in SHELLS_CSV.read_text(encoding="utf-8").splitlines()[1:]:
            fields = line.split(",")
            names[int(fields[0])] = (fields[1], fields[4])
        cls.names = names
        cls.ignore_pain = sorted(i for i, (name, kind) in names.items() if name.startswith("Ignore Pain") and kind == "ability_aura")

    def test_every_ignore_pain_marker_and_nerves_of_steel_carry_the_immunity(self):
        self.assertGreaterEqual(len(self.ignore_pain), 5, "the skill and its runes")
        for spell in self.ignore_pain + [82301]:
            with self.subTest(spell):
                row = self.rows[spell]
                self.assertEqual(number(row["EffectAura_1"]), AURA_DUMMY, "the marker the module reads stays effect 1")
                self.assertEqual((number(row["Effect_2"]), number(row["EffectAura_2"]), number(row["EffectMiscValue_2"])),
                                 (SPELL_EFFECT_APPLY_AURA, AURA_MECHANIC_IMMUNITY_MASK, 96))
                self.assertEqual((number(row["Effect_3"]), number(row["EffectAura_3"]), number(row["EffectMiscValue_3"])),
                                 (SPELL_EFFECT_APPLY_AURA, AURA_MECHANIC_IMMUNITY, MECHANIC["silence"]))
                self.assertTrue(number(row["AttributesEx"]) & ATTR1_IMMUNITY_PURGES_EFFECT)

    def test_a_marker_that_is_not_ignore_pain_carries_none(self):
        for spell, (name, kind) in self.names.items():
            if kind == "ability_aura" and spell not in self.ignore_pain:
                self.assertNotEqual(number(self.rows[spell]["EffectAura_2"]), AURA_MECHANIC_IMMUNITY_MASK, name)

    def test_the_immunity_refuses_every_hold_the_module_applies(self):
        for spell in self.ignore_pain + [82301]:
            states, mechanics = immunity_of(self.rows[spell])
            for aura, hold in HOLD_AURA_TYPES.items():
                self.assertIn(aura, states, "%d does not refuse a %s (AddAura refuses by aura type)" % (spell, hold))
            for mechanic in ("fear", "stun", "root", "silence", "freeze", "snare"):
                self.assertIn(MECHANIC[mechanic], mechanics, "%d: %s" % (spell, mechanic))

    def test_knockout_and_daze_are_the_two_the_records_do_not_carry(self):
        """ruling 2026-10-03: kept silence, dropped these two. test_control_immunity_gap.py guards that nothing applies them."""
        for spell in self.ignore_pain + [82301]:
            _, mechanics = immunity_of(self.rows[spell])
            self.assertNotIn(MECHANIC["knockout"], mechanics)
            self.assertNotIn(MECHANIC["daze"], mechanics)

    def test_vanguard_is_a_display_buff_not_a_second_speed_carrier(self):
        row = self.rows[81195]
        self.assertEqual(number(row["EffectAura_1"]), AURA_DUMMY)
        # one MOD_INCREASE_SPEED carrier among the primaries' helpers: the aggregate (82408) only
        speed = [spell for spell, r in self.rows.items() if 81180 <= spell <= 81210
                 and AURA_MOD_INCREASE_SPEED in [number(r.get("EffectAura_%d" % s)) for s in (1, 2, 3)]]
        self.assertEqual(speed, [])
        self.assertIn(AURA_MOD_INCREASE_SPEED, [number(self.rows[82408].get("EffectAura_%d" % s)) for s in (1, 2, 3)])

    def test_the_armors_are_one_exclusive_spell_group(self):
        armors = sorted(spell for spell, (name, kind) in self.names.items()
                        if re.match(r"(Ice|Storm|Energy) Armor( - |$)", name) and kind in ("active", "rune"))
        self.assertGreaterEqual(len(armors), 15, "three skills, each with its runes")
        groups = {}
        for row in insert_rows(self.text, "spell_group"):
            groups.setdefault(row["id"], []).append(int(row["spell_id"]))
        rules = {row["group_id"]: number(row["stack_rule"]) for row in insert_rows(self.text, "spell_group_stack_rules")}
        self.assertEqual(len(groups), 1)
        (group, members), = groups.items()
        self.assertEqual(sorted(members), armors)
        self.assertEqual(rules[group], 1, "SPELL_GROUP_STACK_RULE_EXCLUSIVE")

    def test_the_migration_carries_the_same_rows(self):
        """combat_0044 first carried these rows. Every later spell migration replaces the whole block again (combat_0045
        zeroed the chain counts nobody owns), so what the server ends with is the newest one, and it is the generated SQL."""
        newest = [path for path in sorted(UPDATES.glob("combat_*.sql"))
                  if FULL_REPLACEMENT in path.read_text(encoding="utf-8")][-1]
        self.assertEqual(newest.read_text(encoding="utf-8"), self.text, newest.name)


class TheModuleNoLongerDoesItByHand(unittest.TestCase):
    def test_no_immunity_loop_and_no_manual_strip_remain(self):
        for name, text in (("the Barbarian files", barbarian_source.abilities()),
                           ("src/combat/dc_passives.cpp", (MODULE / "src/combat/dc_passives.cpp").read_text(encoding="utf-8")),
                           ("the Barbarian's passives", barbarian_source.PASSIVES.read_text(encoding="utf-8"))):
            self.assertNotIn("ApplySpellImmune", text, name)
            self.assertNotIn("RemoveAurasWithMechanic", text, name)
        self.assertNotIn("Immune(p,", (MODULE / "src/combat/dc_passives.cpp").read_text(encoding="utf-8"))
        self.assertNotIn("Immune(p,", barbarian_source.PASSIVES.read_text(encoding="utf-8"))

    def test_no_armor_removal_loop_remains(self):
        wizard = wizard_source.CPP.read_text(encoding="utf-8")
        self.assertNotIn("static bool Armor(", wizard)
        self.assertNotRegex(wizard, r"Armor\(row\.id\)")

    def test_the_generator_writes_the_group_and_the_records(self):
        generator = (MODULE / "scripts/generate/classes/generate_spells.py").read_text(encoding="utf-8")
        self.assertIn("carry_control_immunity(values)", generator)
        self.assertIn("WIZARD_ARMOR_GROUP = 90001", generator)


if __name__ == "__main__":
    unittest.main()

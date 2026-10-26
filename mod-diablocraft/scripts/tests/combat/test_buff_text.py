"""diablocraft-buff-text: a buff's tooltip says what the buff does.

The designer's ruling (q-1004-20, 2026-10-04): the player's own buffs show the sentence of
the skill they stand for - the Wizard's eight buff skills and every rune record of
them, the Barbarian's worn markers - and a rune's buff shows the base skill's
sentence first, then the rune's own. No Cost, Cooldown or Requires line (card q-1005-03,
option C, 2026-10-05: the two "Generate: N Fury" lines, Leap's and War Cry's, are kept);
nothing where there is no sentence; nothing on a debuff that sits on an enemy.

The expectation is TOTAL, like test_spell_records.aura_text_fields: every record of
every class is stated, so a tooltip on a record nobody approved fails as surely as
a missing or a wrong one. It is derived here from the records' own Description
field with its own small implementation, not from the generator's function; the
literal sentences below are the second witness.

    python mod-diablocraft/scripts/tests/combat/test_buff_text.py
"""
from __future__ import annotations

import csv
import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import test_spell_records as records_suite  # noqa: E402  (its SQL and variable-row readers)
from test_spell_records import (  # noqa: E402
    CRLF, SKILL_LINE, VARIABLE, WIZARD_WORN, ENEMY_SIDE, OLDER, expected_aura, unquote, worn_expectations)

GENERATED = records_suite.GENERATED
VARIABLES_DBC = records_suite.VARIABLES_DBC

def read_records():
    sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    names, rows = records_suite.parse(sql, every_class=True)
    return {name: index for index, name in enumerate(names)}, rows


class BuffTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not VARIABLES_DBC.is_file():
            raise unittest.SkipTest("the generated SpellDescriptionVariables.dbc is not here")
        cls.at, cls.rows = read_records()
        with (GENERATED / "spell_shells.csv").open(encoding="utf-8") as stream:
            cls.manifest = list(csv.DictReader(stream))
        cls.ids = {row["name"]: int(row["spell_id"]) for row in cls.manifest if row["kind"] in ("active", "rune")}
        cls.markers = {row["name"]: int(row["spell_id"]) for row in cls.manifest if row["kind"] == "ability_aura"}
        cls.variables = records_suite.parse_variables(VARIABLES_DBC.read_bytes())
        cls.desc = {identifier: unquote(values[cls.at["Description_Lang_enUS"]])
                    for identifier, values in cls.rows.items()}
        cls.wanted = worn_expectations(cls.manifest)

    def aura(self, identifier):
        return unquote(self.rows[identifier][self.at["AuraDescription_Lang_enUS"]])

    # --- the two cases the brief names, as literals ---------------------------

    def test_ice_armors_buff_carries_its_text(self):
        self.assertEqual(
            self.aura(self.ids["Ice Armor"]),
            "Surround yourself in a barrier of ice that reduces damage from melee attacks by $s1%. "
            "Melee attackers are either Chilled or Frozen for $<chill_duration_seconds> seconds. Lasts $d."
            + CRLF + "Only one Armor may be active at a time.")

    def test_a_rune_shows_the_base_sentence_then_its_own(self):
        base = self.ids["Ice Armor"]
        self.assertEqual(
            self.aura(self.ids["Ice Armor - Jagged Ice"]),
            "Surround yourself in a barrier of ice that reduces damage from melee attacks by $%ds1%%. "
            "Melee attackers are either Chilled or Frozen for $<base_chill_duration_seconds> seconds. "
            "Lasts $%dd." % (base, base)
            + CRLF + "Only one Armor may be active at a time."
            + CRLF + "Melee attackers also take $s2% weapon damage as Cold.")

    def test_a_barbarian_marker_points_at_the_record_it_mirrors(self):
        sprint, rush = self.ids["Sprint"], self.ids["Sprint - Rush"]
        self.assertEqual(self.aura(self.markers["Sprint"]),
                         "Increase movement speed by $%ds1%% for $%dd." % (sprint, sprint))
        self.assertEqual(self.aura(self.markers["Sprint - Rush"]),
                         "Increase movement speed by $%ds1%% for $%dd." % (sprint, sprint)
                         + CRLF + "Increase Dodge Chance by $%ds2%% while sprinting." % rush)

    def test_a_cost_or_requires_line_is_not_on_a_buff_but_the_fury_lines_are(self):
        # War Cry's sentence opens with "Generate: $s1 Fury", Leap's with "Generate: $s2 Fury"; Revenge's with "Cost: ...".
        war_cry = self.aura(self.markers["War Cry"])
        self.assertTrue(war_cry.startswith("Generate: $%ds1 Fury" % self.ids["War Cry"] + CRLF + "Unleash a rallying cry"), war_cry)
        leap = self.aura(self.markers["Leap - Iron Impact"])
        self.assertTrue(leap.startswith("Generate: $%ds2 Fury" % self.ids["Leap"]), leap)
        self.assertNotIn("Cost:", self.aura(self.markers["Revenge - Best Served Cold"]))
        self.assertNotIn("Requires", self.aura(self.ids["Magic Weapon"]))

    # --- the total expectation ------------------------------------------------

    def expected_for(self, identifier, name):
        if identifier in OLDER:
            return OLDER[identifier]
        if name in OLDER:
            return OLDER[name]
        if identifier in self.wanted:
            return expected_aura(identifier, self.wanted[identifier], self.desc)
        return ""

    def problems(self, rows=None):
        rows = rows or self.rows
        found = []
        names = {int(row["spell_id"]): row["name"] for row in self.manifest}
        for identifier, values in rows.items():
            text = unquote(values[self.at["AuraDescription_Lang_enUS"]])
            want = self.expected_for(identifier, names.get(identifier, ""))
            if text != want:
                found.append("%d %s: carries %r, should carry %r" % (identifier, names.get(identifier), text, want))
        return found

    def test_every_record_says_exactly_what_was_ruled(self):
        self.assertEqual(self.problems(), [])

    def test_the_set_is_the_set_that_was_ruled(self):
        # 8 Wizard skills and every rune record of them; the Barbarian worn markers.
        wizard = [i for i in self.wanted if i not in self.markers.values()]
        barbarian = [i for i in self.wanted if i in self.markers.values()]
        self.assertEqual(len(wizard), len(WIZARD_WORN) + sum(
            1 for row in self.manifest if row["kind"] == "rune"
            and row["name"].partition(" - ")[0] in WIZARD_WORN))
        self.assertGreaterEqual(len(barbarian), 20)
        for skill, runes in ENEMY_SIDE:
            for name, identifier in self.markers.items():
                if name.partition(" - ")[0] == skill and (runes is None or name.partition(" - ")[2] in runes):
                    self.assertEqual(self.aura(identifier), "", "%s is an enemy-side debuff" % name)

    def test_every_worn_buff_has_a_sentence_and_no_skill_line(self):
        for identifier in self.wanted:
            text = self.aura(identifier)
            self.assertTrue(text, "%d has no aura text" % identifier)
            for line in text.split(CRLF):
                self.assertFalse(SKILL_LINE.match(line), "%d carries the line %r" % (identifier, line))
            if identifier in self.markers.values():
                # A marker owns no number: every token it prints names the record that does.
                self.assertNotRegex(text, r"\$(?![0-9<{])", "%d has a token with no spell id" % identifier)

    def test_every_variable_a_buff_asks_for_is_in_its_row_with_the_source_value(self):
        for identifier in self.wanted:
            asked = VARIABLE.findall(self.aura(identifier))
            if not asked:
                continue
            row = self.variables[int(self.rows[identifier][self.at["SpellDescriptionVariableID"]])]
            for name in asked:
                self.assertIn(name, row, "%d asks for $<%s>, its row defines %s" % (identifier, name, sorted(row)))
                if name.startswith("base_"):
                    base = self.wanted[identifier][0][0]
                    base_row = self.variables[int(self.rows[base][self.at["SpellDescriptionVariableID"]])]
                    self.assertEqual(row[name], base_row[name[len("base_"):]])

    # --- mutants: each corrupts one rule and the total expectation must see it -

    def planted(self, identifier, text):
        rows = {key: list(values) for key, values in self.rows.items()}
        rows[identifier][self.at["AuraDescription_Lang_enUS"]] = "'%s'" % text.replace("'", "''")
        return self.problems(rows)

    def test_mutant_no_text_on_ice_armor(self):
        self.assertTrue(self.planted(self.ids["Ice Armor"], ""))

    def test_mutant_a_guess_where_there_is_no_sentence(self):
        # Hammer of the Ancients is a skill the player never wears a buff of.
        self.assertTrue(self.planted(self.markers["Hammer of the Ancients"], "Guessed text."))

    def test_mutant_text_on_an_enemy_side_debuff(self):
        marker = self.markers["Threatening Shout"]
        self.assertTrue(self.planted(marker, self.desc[self.ids["Threatening Shout"]]))

    def test_mutant_a_rune_that_drops_the_base_sentence(self):
        self.assertTrue(self.planted(self.ids["Ice Armor - Jagged Ice"],
                                     "Melee attackers also take $s2% weapon damage as Cold."))

    def test_mutant_a_base_sentence_with_no_spell_id(self):
        base = self.desc[self.ids["Ice Armor"]]
        own = self.desc[self.ids["Ice Armor - Jagged Ice"]]
        self.assertTrue(self.planted(self.ids["Ice Armor - Jagged Ice"], base + CRLF + own))

    def test_mutant_a_cost_line_left_on(self):
        marker = self.markers["Revenge - Best Served Cold"]
        self.assertTrue(self.planted(marker, "Cost: $81030s1 Fury" + CRLF + self.aura(marker)))

    def test_mutant_the_fury_line_dropped(self):
        marker = self.markers["War Cry"]
        self.assertTrue(self.planted(marker, self.aura(marker).partition(CRLF)[2]))

    def test_mutant_a_requires_line_left_on(self):
        self.assertTrue(self.planted(self.ids["Magic Weapon"], "Requires Weapon" + CRLF + self.aura(self.ids["Magic Weapon"])))


class GeneratorFunctionTests(unittest.TestCase):
    """The pure part of the writer, so the empty case needs no sheet to exist."""

    @classmethod
    def setUpClass(cls):
        cls.gen = records_suite.load_generator()

    def test_an_empty_sentence_is_no_text(self):
        self.assertEqual(self.gen.buff_sentence("", 83117, ""), ("", []))
        self.assertEqual(self.gen.buff_sentence("Cost: $s1 Fury", 83117, ""), ("", []))
        self.assertEqual(self.gen.buff_sentence("Requires Weapon", 83117, ""), ("", []))
        self.assertEqual(self.gen.buff_sentence("Generate: $s1 Fury", 83117, ""), ("Generate: $83117s1 Fury", []))

    def test_an_unknown_bare_token_stops_the_build(self):
        with self.assertRaises(SystemExit):
            self.gen.buff_sentence("Does $z9 things.", 83117, "")

    def test_tokens_gain_the_owner_and_variables_the_prefix(self):
        text, names = self.gen.buff_sentence(
            "Lasts $d, $s2% and ${$x1-1} for $<radius_yards> yards at $83318s1%.", 1234, "base_")
        self.assertEqual(text, "Lasts $1234d, $1234s2% and ${$1234x1-1} for $<base_radius_yards> yards at $83318s1%.")
        self.assertEqual(names, ["radius_yards"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""The skill-damage affix groups of a class D3Planner has no groups for (the Shaman), and the rule they come from.

D3Planner's data.json lists, per D3 class, which skills have a "+X% damage" affix on the head, torso and legs. The
Shaman is not a D3 class, so `generate_skill_affixes.py` builds its three groups from its own sheet by D3's slot rule.

What this proves, and what it does not:

  * The rule's **legs** half is checked against D3Planner for all seven D3 classes: the legs group is every Primary
    and only Primaries, and no Primary sits in a head or torso group. That is a cross-source check: the groups are
    read from data.json and the categories from each class's own sheet.
  * The Shaman's groups are spelled out here from reading `shaman_skills.csv`; a change to the sheet's categories
    or damage cells fails this test until the list is re-read.
  * The head against torso split is NOT D3's list. D3 has no category rule for it (its Secondaries are mostly in
    the head, a Witch Doctor's are in the torso); the Secondaries-in-head reading is the rule's, open for the designer.
"""
import csv
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_skill_affixes as affixes

MODULE = pathlib.Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
D3 = MODULE / "data/d3"
STAT_GROUPS = json.loads((ROOT / "reference/d3planner/data.json").read_text(encoding="utf-8"))["statGroups"]
D3_SHEETS = {"barbarian": "barbarian", "wizard": "wizard", "monk": "monk", "necromancer": "necromancer",
             "crusader": "crusader", "demonhunter": "demon_hunter", "witchdoctor": "witch_doctor"}
SHAMAN_CLASS_ID = 8

SHAMAN = {
    "skill_legs": ["Lightning Bolt", "Flame Shock", "Elemental Lash", "Frost Lance"],
    "skill_head": ["Chain Lightning", "Lava Burst", "Earthquake", "Elemental Blast"],
    "skill_torso": ["Searing Totem", "Spirit Link", "Spirit Wolves", "Fire Elemental", "Earth Elemental"],
}
# Damage-free or Defensive Shaman skills: no affix.
SHAMAN_LEFT_OUT = ["Thunderstorm", "Ghost Wolf", "Elemental Shield", "Purge", "Earthbind Totem", "Healing Stream Totem",
                   "Tempest Totem", "Elemental Weapon", "Call of the Ancestors", "Bloodlust", "Ascendance"]


def sheet(name):
    with (D3 / f"{name}_skills.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def d3_group(class_key, slot):
    return {affix.split("_", 2)[2] for affix in STAT_GROUPS[f"skill_{class_key}_{slot}"]}


def shaman_groups():
    """{group: [affix display skill names]} for class id 8, in choice order."""
    groups = {}
    for group, _index, _affix, class_id, _skill_id, skill, _name in affixes.definitions():
        if class_id == SHAMAN_CLASS_ID:
            groups.setdefault(group, []).append(skill)
    return groups


class LegsRuleMatchesD3(unittest.TestCase):
    def test_the_legs_group_is_every_primary_and_only_primaries(self):
        for class_key, stem in D3_SHEETS.items():
            primaries = {affixes.stem(row["skill_name"]) for row in sheet(stem) if row["category"] == "Primary"}
            self.assertEqual(d3_group(class_key, "legs"), primaries, class_key)

    def test_no_primary_sits_in_a_head_or_torso_group(self):
        for class_key, stem in D3_SHEETS.items():
            primaries = {affixes.stem(row["skill_name"]) for row in sheet(stem) if row["category"] == "Primary"}
            for slot in ("head", "torso"):
                self.assertFalse(primaries & d3_group(class_key, slot), (class_key, slot))

    def test_the_rule_reproduces_each_d3_legs_group(self):
        for class_key, stem in D3_SHEETS.items():
            by_rule = {affixes.stem(row["skill_name"]) for row in sheet(stem) if affixes.derived_slot(row) == "legs"}
            self.assertEqual(by_rule, d3_group(class_key, "legs"), class_key)


class ShamanGroups(unittest.TestCase):
    def test_the_three_groups_are_the_sheets_skills_by_the_rule(self):
        self.assertEqual(shaman_groups(), SHAMAN)

    def test_thirteen_rows_and_no_skill_in_two_groups(self):
        names = [skill for group in shaman_groups().values() for skill in group]
        self.assertEqual(len(names), 13)
        self.assertEqual(len(set(names)), 13)

    def test_a_defensive_or_damage_free_skill_has_no_affix(self):
        names = {skill for group in shaman_groups().values() for skill in group}
        self.assertFalse(names & set(SHAMAN_LEFT_OUT), names & set(SHAMAN_LEFT_OUT))
        # Every skill the sheet names is either in a group or in the left-out list: none dropped unread.
        sheet_names = {affixes.spells_source.shown_name(affixes.spells_source.shown_names(), row["skill_name"])
                       for row in sheet("shaman")}
        self.assertEqual(sheet_names, names | set(SHAMAN_LEFT_OUT))

    def test_earthquake_is_the_shamans_not_the_barbarians(self):
        """The Shaman's Earthquake is keyed 'Earthquake (Shaman)' and shown plain: the affix id, the display name and
        the target skill must follow the Shaman's record, and the Barbarian's own Earthquake affix stays."""
        rows = {affix: (class_id, skill_id, skill, name)
                for _g, _i, affix, class_id, skill_id, skill, name in affixes.definitions()}
        shaman = rows["skill_shaman_earthquake"]
        barbarian = rows["skill_barbarian_earthquake"]
        self.assertEqual(shaman[0], SHAMAN_CLASS_ID)
        self.assertEqual(barbarian[0], 1)
        self.assertNotEqual(shaman[1], barbarian[1])
        self.assertEqual(shaman[2:], ("Earthquake", "Earthquake Damage"))

    def test_every_affix_names_its_own_class(self):
        for _g, _i, affix, class_id, _skill_id, _skill, _name in affixes.definitions():
            if class_id == SHAMAN_CLASS_ID:
                self.assertTrue(affix.startswith("skill_shaman_"), affix)

    def test_the_shaman_sorts_last_so_no_applied_choice_index_moves(self):
        rows = affixes.definitions()
        for group in SHAMAN:
            others = [row[1] for row in rows if row[0] == group and row[3] != SHAMAN_CLASS_ID]
            shaman = [row[1] for row in rows if row[0] == group and row[3] == SHAMAN_CLASS_ID]
            self.assertGreater(min(shaman), max(others), group)
        applied = (MODULE / "data/sql/db-world/updates/items_0055_skill_affix_classes.sql").read_text(encoding="utf-8")
        new = (MODULE / "data/sql/db-world/updates" / affixes.CLASSES_MIGRATION).read_text(encoding="utf-8")
        old_rows = [line.rstrip(",;") for line in applied.splitlines() if line.startswith("('skill_")]
        new_rows = {line.rstrip(",;") for line in new.splitlines() if line.startswith("('skill_")}
        self.assertEqual(len(old_rows), 105)
        self.assertTrue(set(old_rows) <= new_rows)
        self.assertEqual(len(new_rows), 118)

    def test_the_applied_migration_is_not_the_one_written(self):
        self.assertNotEqual(affixes.CLASSES_MIGRATION, "items_0055_skill_affix_classes.sql")


class RuleMutants(unittest.TestCase):
    """Each constant of the rule, changed, must change the Shaman's groups."""

    def run_mutant(self, name, value):
        original = getattr(affixes, name)
        setattr(affixes, name, value)
        try:
            return shaman_groups()
        finally:
            setattr(affixes, name, original)

    def test_legs_category_changed_is_caught(self):
        self.assertNotEqual(self.run_mutant("LEGS_CATEGORY", "Secondary"), SHAMAN)

    def test_head_category_changed_is_caught(self):
        self.assertNotEqual(self.run_mutant("HEAD_CATEGORY", "Totems"), SHAMAN)

    def test_defensive_kept_out_changed_is_caught(self):
        self.assertNotEqual(self.run_mutant("NO_AFFIX_CATEGORY", "Nothing"), SHAMAN)

    def test_an_unknown_class_without_a_sheet_is_refused(self):
        with self.assertRaises(ValueError):
            affixes.sheet_skills("notaclass")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""B1+B2 - one class-keyed catalogue, and no class named in code.

`dc_classes.cpp` held three `dc_barbarian_*` tables and gated on
`CLASS_WARRIOR`; `dc_loot.cpp` decided at load time whether each base item was
"the Barbarian's" or "some other class's". A second class meant a second set of
tables and a second branch in every gate.

These tests are the two halves the brief asks for: the catalogue says what the
three tables said, and Barbarian behaviour is unchanged - proven against the
sheets themselves rather than against a copy of the answer.
"""
import csv
import io
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from class_names import item_key, sheet_stem  # noqa: E402
import barbarian_source  # noqa: E402
import generate_class_catalogue as gcc
import json
import primary_spells

ROOT = gcc.ROOT
D3 = gcc.D3
def source(path):
    return path.read_text(encoding="utf-8")


def code(text):
    """The source with comment lines removed.

    A comment saying which hardcoded test was REMOVED would otherwise fail the
    very assertion that proves it is gone - the same trap a commented-out call
    set on an earlier task.
    """
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        out.append(line.split("//")[0] if "//" in line else line)
    return "\n".join(out)


CLASSES_CPP = source(ROOT / "src" / "classes" / "dc_classes.cpp")
LOOT_CPP = source(ROOT / "src" / "loot" / "dc_loot.cpp")
CLASSES_CODE = code(CLASSES_CPP)
LOOT_CODE = code(LOOT_CPP)
PRIMARIES_CPP = (ROOT / "src" / "classes" / "barbarian" / "dc_barbarian_primaries.cpp").read_text(encoding="utf-8")
GENERATED = ROOT / "data" / "generated" / "class_catalogue.sql"
UPDATES = ROOT / "data" / "sql" / "db-world" / "updates"
# Applied catalogue migrations and the commit holding each one's receipt.
# world_0014: APPLIED 2026-09-22 (docs/deploy-release-20260922.md), at 268f5e8.
# world_0015: applied (data/sql/applied_migrations.csv, confirmed against the
# live updates table 2026-09-23); last written at 482f86e. world_0018 carries
# the Wizard's power_type Energy (diablocraft-resource-rollout-a item 4);
# applied 2026-09-26 (applied_migrations.csv), last written at 40af78b8.
APPLIED = {"world_0014_class_catalogue.sql": "268f5e8", "world_0015_class_catalogue.sql": "482f86e",
           "world_0018_class_catalogue.sql": "40af78b8", "world_0022_class_catalogue.sql": "97c09174",
           # world_0050 (the Monk's rows) went to dev and is not rewritten; last written at 09b37500b
           "world_0050_class_catalogue.sql": "09b37500b",
           # world_0062 (the Necromancer's rows) went to dev and is not rewritten; last written at 6f7a5f0dd
           "world_0062_class_catalogue.sql": "6f7a5f0dd",
           # world_0068 (the Crusader's rows) went to dev and is not rewritten; written at 8b99d423f
           "world_0068_class_catalogue.sql": "8b99d423f",
           # world_0074 (the Demon Hunter's rows) went to dev and is not rewritten; written at 3e2fdef1f
           "world_0074_class_catalogue.sql": "3e2fdef1f",
           # world_0080 (the Witch Doctor's rows) went to dev and is not rewritten; written at 7914e77ef
           "world_0080_class_catalogue.sql": "7914e77ef"}
# The window this task had to reproduce, pinned to the brief's commit: part 2
# removes CATEGORY_ORDER from dc_skillbar.lua on purpose, and the Barbarian
# baseline must outlive it rather than follow HEAD.
WINDOW_BASELINE = ("f390f2a0", "mod-diablocraft/lua/aio/dc_skillbar.lua")
D3PLANNER = ROOT.parent / "reference" / "d3planner" / "data.json"


def rows_of(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def built():
    return gcc.catalogue()


# diablocraft-wizard-records: the catalogue now holds a second class. The
# Barbarian's contract below is asserted for class_id 1 exactly as before, and
# the Wizard's rows are checked for what joined - never folded into a count
# that would let one class hide a change in the other. Both ids come from
# class_map.csv, the same file the generator reads.
# The Monk's records arrived with diablocraft-3mk78 (Monk 2.2), so it is listed here from world_0050 on.
CLASS_IDS = {row["d3_class"]: int(row["class_id"]) for row in
             csv.DictReader((D3 / "class_map.csv").open(encoding="utf-8-sig", newline=""))
             if (D3 / f"{sheet_stem(row['d3_class'])}_skills.csv").is_file()}
BARBARIAN = CLASS_IDS["Barbarian"]
WIZARD = CLASS_IDS["Wizard"]
MONK = CLASS_IDS["Monk"]
# The Necromancer's records arrived with diablocraft-im7mr.5 (Necromancer 2a): listed from world_0062 on.
NECROMANCER = CLASS_IDS["Necromancer"]
# The Crusader's records arrived with diablocraft-qulab (Crusader 2a): listed from world_0068 on.
CRUSADER = CLASS_IDS["Crusader"]
# The Demon Hunter's records arrived with diablocraft-vawmy.3 (Demon Hunter 2a): listed from world_0074 on.
DEMON_HUNTER = CLASS_IDS["Demon Hunter"]
# The Witch Doctor's records arrived with diablocraft-vxrcu.5 (Witch Doctor 2a): listed from world_0080 on.
WITCH_DOCTOR = CLASS_IDS["Witch Doctor"]
# The Shaman's records arrived with diablocraft-xnrvn.6 (Shaman 2a): listed from world_0087 on.
SHAMAN = CLASS_IDS["Shaman"]


def of_class(rows, class_id, column=0):
    return [row for row in rows if row[column] == class_id]


# The shell kind the Wizard's Archon form casts from. Those five records are
# the transformation's own skill set, not entries a player puts on a bar, so
# they are deliberately not in the catalogue.
ARCHON_KIND = "archon"


class Catalogue(unittest.TestCase):
    def setUp(self):
        (self.rows, self.passives, self.labels, self.passive_labels,
         self.class_map, self.playable, self.waiting, self.ambiguous) = built()

    def test_every_barbarian_skill_and_rune_has_exactly_one_row(self):
        skills, runes = rows_of("barbarian_skills.csv"), rows_of("barbarian_runes.csv")
        rows = of_class(self.rows, BARBARIAN)
        self.assertEqual(len(rows), len(skills) + len(runes))
        base = [row for row in rows if row[2] == 0]
        self.assertEqual(len(base), len(skills))
        self.assertEqual(len(rows) - len(base), len(runes))

    def test_every_passive_has_exactly_one_row(self):
        passives = of_class(self.passives, BARBARIAN)
        self.assertEqual(len(passives), len(rows_of("barbarian_passives.csv")))

    def test_every_wizard_skill_and_rune_has_exactly_one_row(self):
        # diablocraft-wizard-records: 26 skills and 130 runes join, and the
        # whole catalogue is the two classes and nothing else.
        skills, runes = rows_of("wizard_skills.csv"), rows_of("wizard_runes.csv")
        rows = of_class(self.rows, WIZARD)
        self.assertEqual(len(rows), len(skills) + len(runes))
        self.assertEqual(len([row for row in rows if row[2] == 0]), len(skills))
        self.assertEqual({row[0] for row in self.rows},
                         {BARBARIAN, WIZARD, MONK, NECROMANCER, CRUSADER, DEMON_HUNTER, WITCH_DOCTOR, SHAMAN})

    def test_every_wizard_passive_has_exactly_one_row(self):
        passives = of_class(self.passives, WIZARD)
        self.assertEqual(len(passives), len(rows_of("wizard_passives.csv")))

    def test_every_monk_skill_and_rune_has_exactly_one_row(self):
        # diablocraft-3mk78 (Monk 2.2): 22 skills and 110 runes join, in the six categories of class_skill_categories.csv.
        skills, runes = rows_of("monk_skills.csv"), rows_of("monk_runes.csv")
        rows = of_class(self.rows, MONK)
        self.assertEqual(len(rows), len(skills) + len(runes))
        self.assertEqual(len([row for row in rows if row[2] == 0]), len(skills))
        self.assertEqual(len(of_class(self.passives, MONK)), len(rows_of("monk_passives.csv")))

    def test_the_archon_records_are_not_catalogue_entries(self):
        # Five records of kind archon exist (83274-83278) and none of them may
        # reach a row, a passive or a label: Archon itself is the entry.
        archon = {int(row["spell_id"]) for row in csv.DictReader(
            gcc.SHELLS.open(encoding="utf-8", newline="")) if row["kind"] == ARCHON_KIND}
        self.assertEqual(archon, set(range(83274, 83279)))
        published = ({row[3] for row in self.rows} | {row[1] for row in self.passives}
                     | {row[0] for row in self.labels} | {row[0] for row in self.passive_labels})
        self.assertEqual(archon & published, set())

    def test_unlock_levels_are_the_sheets_own(self):
        # The catalogue must not quietly retune what the three tables said.
        # Each class is read from its own sheets (diablocraft-wizard-records).
        labels = {row[0]: row for row in self.labels}
        wanted = {}
        for d3_class, class_id in CLASS_IDS.items():
            stem = sheet_stem(d3_class)
            wanted.update({(class_id, r["skill_name"], ""): int(r["unlock_level"] or 1)
                           for r in rows_of(f"{stem}_skills.csv")})
            wanted.update({(class_id, r["skill_name"], r["rune_name"]): int(r["unlock_level"] or 1)
                           for r in rows_of(f"{stem}_runes.csv")})
        for class_id, skill_id, rune_id, spell_id, unlock, buff in self.rows:
            _, label_class, skill_name, rune_name, _, _ = labels[spell_id]
            self.assertEqual(label_class, class_id, spell_id)
            self.assertEqual(unlock, wanted[(class_id, skill_name, rune_name)],
                             (class_id, skill_name, rune_name))

    def test_spell_ids_are_the_published_index_and_not_a_second_list(self):
        index = gcc.shell_index()
        labels = {row[0]: row for row in self.labels}
        for class_id, skill_id, rune_id, spell_id, unlock, buff in self.rows:
            _, _, skill_name, rune_name, _, _ = labels[spell_id]
            if rune_id:
                self.assertEqual(spell_id, index["rune"][f"{skill_name} - {rune_name}"])
                self.assertEqual(rune_id, spell_id)
            else:
                self.assertEqual(spell_id, index["active"][skill_name])
            self.assertEqual(skill_id, index["active"][skill_name])

    def test_only_classes_with_generated_spells_are_playable(self):
        # A class with reference sheets and no shells is absent rather than
        # half-present (the Wizard was, until diablocraft-wizard-records
        # generated its records). Now both classes have shells, both are
        # playable; the Monk has its sheets (diablocraft-cwtc0) and no shells
        # yet, so it waits, reported and not in the catalogue. The Crusader (1a) was in class_map.csv with no skill
        # sheets until its records (2a, diablocraft-qulab); now it is playable too, and so are the Demon Hunter
        # (2a, diablocraft-vawmy.3), the Witch Doctor (2a, diablocraft-vxrcu.5) and the Shaman (2a, diablocraft-xnrvn.6).
        self.assertEqual(self.playable, ["Barbarian", "Wizard", "Monk", "Crusader", "Necromancer", "Demon Hunter",
                                         "Witch Doctor", "Shaman"])
        self.assertEqual(self.waiting, [])
        self.assertEqual([row[2] for row in self.class_map],
                         ["Barbarian", "Wizard", "Monk", "Crusader", "Necromancer", "Demon Hunter", "Witch Doctor", "Shaman"])

    def test_the_class_map_carries_the_stock_wow_class_id(self):
        # The Wizard plays on the Mage body, stock class 8.
        self.assertEqual([(row[0], row[2], row[3]) for row in self.class_map],
                         [(BARBARIAN, "Barbarian", 1), (WIZARD, "Wizard", 8), (MONK, "Monk", 12),
                          (CRUSADER, "Crusader", 2), (NECROMANCER, "Necromancer", 13), (DEMON_HUNTER, "Demon Hunter", 3),
                          (WITCH_DOCTOR, "Witch Doctor", 14), (SHAMAN, "Shaman", 7)])
        self.assertEqual((BARBARIAN, WIZARD, MONK, CRUSADER, NECROMANCER, DEMON_HUNTER, WITCH_DOCTOR, SHAMAN),
                         (1, 2, 3, 4, 5, 6, 7, 8))

    def test_the_key_and_the_label_are_separate_columns(self):
        # The regression this task was returned for: the key is what
        # usable_by/designated_class are written in; the label is for people.
        # test_class_eligibility.py runs the production predicates with it.
        for row in self.class_map:
            class_key, d3_class = row[1], row[2]
            # base_items.csv spells a class of two words without the space: the key is the items' spelling
            self.assertEqual(class_key, item_key(d3_class))
            self.assertNotEqual(class_key, d3_class)


class WornBuffs(unittest.TestCase):
    """indicator_spell_id, traced across execution rather than matched in one file.

    The first version regexed `dc_barbarian_primaries.cpp` alone, found two worn auras
    and asserted that was all of them. A regex over one file cannot support
    that claim: `dc_abilities.cpp` self-marks seven more skills, and the Frenzy
    stack buff belongs to the skill so every Frenzy rune wears it too. Two
    became thirty-four.

    The Architect's ruling of 2026-09-22 fixes what the column means: the ONE
    aura a player watches for that skill's duration or stacks, never a set. An
    entry may wear more than one; the extras are declared side auras. Frenzy
    and every Frenzy rune, Vanguard included, indicate with the stack buff.
    """

    def setUp(self):
        self.rows, _, self.labels, _, _, _, _, _ = built()
        self.by_id = {row[0]: row for row in self.labels}

    def entry(self, spell_id):
        _, _, skill_name, rune_name, _, _ = self.by_id[spell_id]
        return skill_name, rune_name

    def test_the_aura_id_formula_is_read_from_the_file_that_owns_it(self):
        first, last, marker = gcc.marker_formula()
        self.assertEqual((first, last, marker), (81000, 81137, 81310))
        abilities = barbarian_source.abilities((".cpp",))
        self.assertIn("return Marker + id - First;", abilities)

    def test_the_self_mark_declaration_matches_the_call_sites(self):
        """Re-derived from the Barbarian's ability files, skill by skill (a skill's file is named for it)."""
        found = set()
        for branch, text in barbarian_source.by_skill((".cpp",)):
            for line in text.splitlines():
                match = re.search(r'(?:else\s+)?if\s*\(skill == "([^"]+)"\)', line)
                if match:
                    branch = match.group(1)
                if re.search(r"\bMark\(\s*p\s*,\s*p\s*,", line):
                    found.add(branch)
        declared = set(gcc.SELF_MARK_SKILLS) | {skill for skill, _ in gcc.SELF_MARK_RUNES}
        self.assertEqual(found, declared)

    def test_thirty_four_entries_indicate_and_the_breakdown_is_the_trace(self):
        carried = {self.entry(row[3]): row[5] for row in self.rows if row[5]}
        self.assertEqual(len(carried), 34)
        frenzy = {key for key in carried if key[0] == "Frenzy"}
        unconditional = {key for key in carried if key[0] in gcc.SELF_MARK_SKILLS}
        runed = {key for key in carried if key in gcc.SELF_MARK_RUNES}
        # Frenzy base + 5 runes, 4 skills x 6 entries, 4 rune-conditional.
        self.assertEqual((len(frenzy), len(unconditional), len(runed)), (6, 24, 4))
        self.assertEqual(len(carried), len(frenzy) + len(unconditional) + len(runed))

    def test_every_frenzy_entry_indicates_with_the_stack_buff(self):
        # The counter belongs to the skill, so the runes wear it too - the
        # thing the first version got wrong by keying the declaration on names.
        # Per the ruling Vanguard is no exception: its own aura is a side one.
        frenzy = {self.entry(row[3])[1]: row[5] for row in self.rows
                  if self.entry(row[3])[0] == "Frenzy"}
        self.assertEqual(len(frenzy), 6)
        for rune, indicator in frenzy.items():
            self.assertEqual(indicator, primary_spells.FRENZY_BUFF, rune)

    def test_every_marker_is_this_entrys_own_aura_id(self):
        first, _, marker = gcc.marker_formula()
        for row in self.rows:
            skill_name, rune_name = self.entry(row[3])
            if skill_name == "Frenzy" or not row[5]:
                continue
            self.assertEqual(row[5], marker + row[3] - first, (skill_name, rune_name))

    # --- the entry that wears two, and the ruling that resolves it ----------

    def test_vanguard_wears_two_auras_and_indicates_with_the_skills(self):
        """The trace still says two. The ruling says which one the bar watches."""
        self.assertEqual(list(gcc.SIDE_AURAS), [("Frenzy", "Vanguard")])
        vanguard = [row for row in self.rows if self.entry(row[3]) == ("Frenzy", "Vanguard")]
        self.assertEqual(len(vanguard), 1)
        worn = gcc.worn_for("Frenzy", "Vanguard", vanguard[0][3], *gcc.marker_formula())
        self.assertEqual(worn, {primary_spells.FRENZY_BUFF, primary_spells.VANGUARD})
        self.assertEqual(vanguard[0][5], primary_spells.FRENZY_BUFF)

    def test_the_side_aura_is_the_indicator_of_no_entry(self):
        self.assertNotIn(primary_spells.VANGUARD, {row[5] for row in self.rows})

    def test_an_entry_with_no_single_indicator_stays_empty_and_is_logged(self):
        """The ruling: empty plus an explanation, never a guess.

        Drop the declaration and Vanguard has two undeclared candidates. It
        must emit 0 and be reported - not pick one, and not stop generation.
        """
        original = dict(gcc.SIDE_AURAS)
        gcc.SIDE_AURAS.clear()
        try:
            rows, _, labels, _, _, _, _, ambiguous = built()
            by_id = {row[0]: (row[2], row[3]) for row in labels}
            vanguard = [row for row in rows if by_id[row[3]] == ("Frenzy", "Vanguard")]
            self.assertEqual(vanguard[0][5], 0)
            self.assertEqual([(skill, rune) for skill, rune, _ in ambiguous],
                             [("Frenzy", "Vanguard")])
            self.assertEqual(ambiguous[0][2],
                             sorted([primary_spells.VANGUARD, primary_spells.FRENZY_BUFF]))
        finally:
            gcc.SIDE_AURAS.update(original)

    def test_a_side_aura_declared_on_an_entry_that_does_not_wear_it_is_refused(self):
        """A declaration is a claim about execution; a stale one must not pass."""
        original = dict(gcc.SIDE_AURAS)
        gcc.SIDE_AURAS[("Sprint", "Marathon")] = ("VANGUARD",)
        try:
            with self.assertRaisesRegex(ValueError, "but the traced auras for that entry"):
                built()
        finally:
            gcc.SIDE_AURAS.clear()
            gcc.SIDE_AURAS.update(original)

    def test_a_side_aura_declared_on_an_entry_that_does_not_exist_is_refused(self):
        original = dict(gcc.SIDE_AURAS)
        gcc.SIDE_AURAS[("Frenzy", "No Such Rune")] = ("VANGUARD",)
        try:
            with self.assertRaisesRegex(ValueError, "not in the catalogue"):
                built()
        finally:
            gcc.SIDE_AURAS.clear()
            gcc.SIDE_AURAS.update(original)

    def test_what_this_trace_does_not_cover(self):
        """Stated, not implied.

        The trace covers the two producers that add an aura to the player:
        dc_barbarian_primaries.cpp and dc_abilities.cpp's self-Mark. It does not cover
        auras a core spell effect applies on its own, nor anything a future
        file adds - a new producer needs a new branch here, and no test can
        notice one that does not exist yet.
        """
        producers = ("dc_barbarian_primaries.cpp", *(p.name for p in barbarian_source.files((".cpp",))))
        adders = set()
        for path in [*(ROOT / "src" / "combat").glob("*.cpp"), *barbarian_source.FOLDER.glob("*.cpp")]:
            text = path.read_text(encoding="utf-8")
            if re.search(r"(AddAura|CastCustomSpell|CastSpell)\([^;]*?\bplayer\b\s*,\s*true",
                         text) or re.search(r"Mark\(\s*p\s*,\s*p\s*,", text) \
                    or "AddAura(D::" in text:
                adders.add(path.name)
        self.assertTrue(adders <= set(producers) | {"dc_passives.cpp"},
                        "a combat file outside the traced producers adds a self aura: %s"
                        % sorted(adders - set(producers)))


class NoClassNamedInCode(unittest.TestCase):
    """The point of B1 and B2: no gate names a class."""

    def test_the_loot_roll_no_longer_hardcodes_the_warrior_class(self):
        self.assertNotIn("CLASS_WARRIOR", LOOT_CODE)
        self.assertNotIn('Lists(usable, "barbarian")', LOOT_CODE)
        self.assertNotIn('designation != "barbarian"', LOOT_CODE)

    def test_the_class_gates_no_longer_hardcode_the_warrior_class(self):
        self.assertNotIn("CLASS_WARRIOR", CLASSES_CODE)
        self.assertNotIn("Not a Barbarian.", CLASSES_CODE)

    def test_the_three_barbarian_tables_are_no_longer_selected_from(self):
        for table in ("dc_barbarian_skills", "dc_barbarian_runes", "dc_barbarian_passives"):
            self.assertNotIn(f"FROM {table}", CLASSES_CODE, table)

    def test_there_is_one_selection_path(self):
        self.assertIn("CatalogueEntry const* Entry(Player const* player", CLASSES_CPP)
        self.assertIn("FROM dc_class_catalogue c JOIN dc_class_label l", CLASSES_CPP)

    def test_both_files_refuse_to_start_without_the_class_map(self):
        for source, name in ((CLASSES_CPP, "dc_classes.cpp"), (LOOT_CPP, "dc_loot.cpp")):
            self.assertIn("dc_class_map is missing or empty", source, name)

    def test_the_comment_stripper_would_not_hide_a_real_hardcode(self):
        self.assertNotIn("CLASS_WARRIOR", code("// mentions CLASS_WARRIOR in a comment"))
        self.assertIn("CLASS_WARRIOR", code("if (x == CLASS_WARRIOR) return;"))
        self.assertIn("CLASS_WARRIOR", code("if (x == CLASS_WARRIOR) return;  // trailing"))

    def test_a_class_outside_the_map_rolls_nothing(self):
        # The behaviour a Mage has today, kept: D3Class is empty, RollLoot
        # returns before picking a pool rather than falling through to one.
        self.assertIn("std::string const d3 = D3Class(player);", LOOT_CPP)
        self.assertIn("if (d3.empty())", LOOT_CPP)


class BarbarianBehaviourUnchanged(unittest.TestCase):
    """The acceptance: the same items, for the same reasons."""

    def setUp(self):
        self.items = [row for row in rows_of("base_items.csv")]

    def own(self, usable, designation, d3):
        return ((not usable) or d3 in usable.split(";")) and \
               (not designation or designation == d3)

    def other(self, usable, designation, d3):
        return designation != d3 and \
               ((not usable) or any(token and token != d3 for token in usable.split(";")))

    def test_the_new_rule_picks_exactly_the_items_the_old_booleans_did(self):
        # The old load-time booleans, restated, against the same sheet.
        same_own = same_other = 0
        for item in self.items:
            usable, designation = item["usable_by"], item["designated_class"]
            old_own = (not usable or "barbarian" in usable.split(";")) and \
                      (not designation or designation == "barbarian")
            old_other = designation != "barbarian" and \
                        (not usable or any(t and t != "barbarian" for t in usable.split(";")))
            self.assertEqual(self.own(usable, designation, "barbarian"), old_own, item["d3_id"])
            self.assertEqual(self.other(usable, designation, "barbarian"), old_other,
                             item["d3_id"])
            same_own += old_own
            same_other += old_other
        # Measured from the sheet, so the numbers are evidence rather than a
        # shape assertion: 1114 base items, 588 a Barbarian's own, 1024 that
        # some other class may roll through L7's 15%.
        self.assertEqual(len(self.items), 1114 + 3)    # D3's plus the Shaman's Ritual Mace, Totem and start legendary (xnrvn.3)
        # The Shaman's three (xnrvn.3) are no Barbarian's own and are rolled through L7 by the others: 1024 + 3.
        self.assertEqual((same_own, same_other), (588, 1027))

    def test_the_catalogue_offers_the_same_starter_skills_as_the_old_query(self):
        # Both order by the same D3 category order, then unlock level, then name.
        order = ["Primary", "Secondary", "Defensive", "Might", "Tactics", "Rage"]
        rows, _, labels, _, _, _, _, _ = built()
        by_id = {row[0]: row for row in labels}
        # The old query was the Barbarian's; the Wizard's starters are its own
        # (diablocraft-wizard-records), so the comparison is class_id 1's.
        base = [(by_id[row[3]][4], row[4], by_id[row[3]][2])
                for row in of_class(rows, BARBARIAN) if row[2] == 0 and row[4] <= 1]
        sheet = [(r["category"], int(r["unlock_level"] or 1), r["skill_name"])
                 for r in rows_of("barbarian_skills.csv") if int(r["unlock_level"] or 1) <= 1]
        key = lambda row: (order.index(row[0]), row[1], row[2])
        self.assertEqual(sorted(base, key=key), sorted(sheet, key=key))


class SkillsWindow(unittest.TestCase):
    """diablocraft-skills-window-class-data: the rune element and the category
    order, class-keyed, so the skills window reads no dc_barbarian_* table and
    keeps no category list of its own."""

    def setUp(self):
        (self.rows, _, self.labels, _, self.class_map, _, _, _) = built()
        self.orders = gcc.category_orders(self.class_map)

    def sheet_elements(self):
        wanted = {}
        for d3_class, class_id in CLASS_IDS.items():
            stem = sheet_stem(d3_class)
            wanted.update({(class_id, r["skill_name"], ""): r["element"]
                           for r in rows_of(f"{stem}_skills.csv")})
            wanted.update({(class_id, r["skill_name"], r["rune_name"]): r["element"]
                           for r in rows_of(f"{stem}_runes.csv")})
        return wanted

    def test_every_rune_of_every_class_has_its_sheets_element(self):
        wanted = self.sheet_elements()
        runes = [label for label in self.labels if label[3]]
        self.assertEqual(len(runes), 115 + 130 + 110 + 105 + 120 + 120 + 115 + 120)
        for spell_id, class_id, skill_name, rune_name, _, element in runes:
            self.assertTrue(element, (class_id, skill_name, rune_name))
            self.assertEqual(element, wanted[(class_id, skill_name, rune_name)], spell_id)

    def test_every_skill_row_carries_the_skills_own_element(self):
        wanted = self.sheet_elements()
        skills = [label for label in self.labels if not label[3]]
        self.assertEqual(len(skills), 23 + 26 + 22 + 21 + 24 + 24 + 23 + 24)
        for spell_id, class_id, skill_name, _, _, element in skills:
            self.assertTrue(element, (class_id, skill_name))
            self.assertEqual(element, wanted[(class_id, skill_name, "")], spell_id)

    def test_every_category_a_class_uses_has_exactly_one_order(self):
        for class_id in {row[0] for row in self.class_map}:
            used = {label[4] for label in self.labels if label[1] == class_id and not label[3]}
            mine = [(category, order) for cid, category, order in self.orders if cid == class_id]
            self.assertEqual(sorted(category for category, _ in mine), sorted(used), class_id)
            self.assertEqual(sorted(order for _, order in mine), list(range(1, len(used) + 1)))
        self.assertEqual({row[0] for row in self.orders},
                         {BARBARIAN, WIZARD, MONK, NECROMANCER, CRUSADER, DEMON_HUNTER, WITCH_DOCTOR, SHAMAN})

    def test_the_barbarian_reproduces_what_its_window_shows_today(self):
        # The order: dc_skillbar.lua's CATEGORY_ORDER constant (:215) as it
        # stood at the brief's commit. A baseline that cannot be read is a
        # failure, not a pass.
        commit, path = WINDOW_BASELINE
        shown_lua = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT.parent,
                                   capture_output=True)
        self.assertEqual(shown_lua.returncode, 0,
                         f"the baseline {commit} has no {path}: "
                         f"{shown_lua.stderr.decode().strip()}")
        match = re.search(r"local CATEGORY_ORDER = \{([^}]*)\}",
                          shown_lua.stdout.decode("utf-8"))
        self.assertIsNotNone(match, f"{path} at {commit} has no CATEGORY_ORDER")
        window = re.findall(r'"([^"]+)"', match.group(1))
        self.assertEqual(window, ["Primary", "Secondary", "Defensive", "Might", "Tactics", "Rage"])
        self.assertEqual([category for cid, category, _ in self.orders if cid == BARBARIAN], window)
        # The element: dc_barbarian_runes.element, the column the window reads
        # (dc_skillbar.lua :84), as generated into barbarian_runes.sql.
        text = source(ROOT / "data" / "generated" / "barbarian_runes.sql")
        shown = {(skill.replace("''", "'"), rune.replace("''", "'")): element
                 for skill, rune, element in re.findall(
                     r"^\('((?:[^']|'')*)', '[A-E]', '((?:[^']|'')*)', \d+, '([^']*)'",
                     text, re.MULTILINE)}
        self.assertEqual(len(shown), 115)
        generated = {(label[2], label[3]): label[5] for label in self.labels
                     if label[1] == BARBARIAN and label[3]}
        self.assertEqual(generated, shown)

    def test_the_order_sheet_is_d3planners_skillcat_for_every_d3_class(self):
        # Pinned to the source the sheet names: data.json skillcat, key order,
        # with classes.<key>.name as the class. All seven classes, playable or not.
        # The Shaman is not a D3 class: its six rows are the brief's (test_the_shaman_order_is_the_briefs).
        planner = json.loads(D3PLANNER.read_text(encoding="utf-8"))
        expected = [(planner["classes"][key]["name"], label, order)
                    for key, cats in planner["skillcat"].items()
                    for order, label in enumerate(cats.values(), 1)]
        sheet = [(r["d3_class"], r["category"], int(r["display_order"]))
                 for r in rows_of("class_skill_categories.csv") if r["d3_class"] != "Shaman"]
        self.assertEqual(sheet, expected)
        self.assertEqual(len({row[0] for row in sheet}), 7)

    def test_the_wizard_order_is_d3s(self):
        self.assertEqual([category for cid, category, _ in self.orders if cid == WIZARD],
                         ["Primary", "Secondary", "Defensive", "Force", "Conjuration", "Mastery"])

    def test_the_monk_order_is_d3s(self):
        self.assertEqual([category for cid, category, _ in self.orders if cid == MONK],
                         ["Primary", "Secondary", "Defensive", "Techniques", "Focus", "Mantras"])

    def test_the_necromancer_order_is_d3s(self):
        self.assertEqual([category for cid, category, _ in self.orders if cid == NECROMANCER],
                         ["Primary", "Secondary", "Corpses", "Reanimation", "Curses", "Blood & Bone"])

    def test_the_crusader_order_is_d3s(self):
        self.assertEqual([category for cid, category, _ in self.orders if cid == CRUSADER],
                         ["Primary", "Secondary", "Defensive", "Utility", "Laws", "Conviction"])

    def test_the_demon_hunter_order_is_d3s(self):
        self.assertEqual([category for cid, category, _ in self.orders if cid == DEMON_HUNTER],
                         ["Primary", "Secondary", "Defensive", "Hunting", "Devices", "Archery"])

    def test_the_witch_doctor_order_is_d3s(self):
        self.assertEqual([category for cid, category, _ in self.orders if cid == WITCH_DOCTOR],
                         ["Primary", "Secondary", "Defensive", "Terror", "Decay", "Voodoo"])

    def test_the_shaman_order_is_the_briefs(self):
        # Step 2 of the Shaman build brief names the categories in this order; the class has no d3planner skillcat
        self.assertEqual([category for cid, category, _ in self.orders if cid == SHAMAN],
                         ["Primary", "Secondary", "Defensive", "Totems", "Ancestral", "Primal"])
        self.assertEqual([r["category"] for r in rows_of("class_skill_categories.csv") if r["d3_class"] == "Shaman"],
                         ["Primary", "Secondary", "Defensive", "Totems", "Ancestral", "Primal"])

    def test_every_class_with_an_order_row_is_published(self):
        # no class waits on its records now: each class in class_skill_categories.csv has its orders in the catalogue
        self.assertEqual({r["d3_class"] for r in rows_of("class_skill_categories.csv")}, set(CLASS_IDS))
        self.assertEqual({cid for cid, _, _ in self.orders}, set(CLASS_IDS.values()))

    def test_element_is_on_the_label_table_and_not_the_catalogue(self):
        # The catalogue stays all integers (test_a_row_carries_no_english).
        sql = GENERATED.read_text(encoding="utf-8")
        catalogue = sql.split("CREATE TABLE `dc_class_catalogue`")[1].split(";")[0]
        label = sql.split("CREATE TABLE `dc_class_label`")[1].split(";")[0]
        self.assertNotIn("element", catalogue)
        self.assertIn("`element` VARCHAR(32) NOT NULL", label)


def rendered(rows, passives, labels, passive_labels, class_map):
    return gcc.render(rows, passives, labels, passive_labels, class_map,
                      gcc.category_orders(class_map))


def without(built_result, *classes):
    """The five lists a render takes, with these classes' rows taken back out."""
    rows, passives, labels, passive_labels, class_map = built_result[:5]
    own = {row[1] for row in passives if row[0] in classes}
    return ([r for r in rows if r[0] not in classes], [r for r in passives if r[0] not in classes],
            [r for r in labels if r[1] not in classes], [r for r in passive_labels if r[0] not in own],
            [r for r in class_map if r[0] not in classes])


def without_monk(built_result):
    """The render of the classes world_0022 carried: the Monk's and every later class's rows taken back out."""
    return without(built_result, MONK, NECROMANCER, CRUSADER, DEMON_HUNTER, WITCH_DOCTOR, SHAMAN)


def without_window_data(sql):
    """Today's render minus exactly what diablocraft-skills-window-class-data
    added: the element column of dc_class_label and the dc_class_category
    section. What is left must be the applied migration byte for byte, so
    nothing else can have moved with the new data."""
    head, marker, tail = sql.partition("-- D3's fixed order of each class's skill categories")
    assert marker and tail.count("DROP TABLE") == 1, "dc_class_category is not the last section"
    out, in_labels = [], False
    for line in head.splitlines(keepends=True):
        if line.startswith("  -- The sheet's element") or line.startswith("  `element` VARCHAR"):
            continue
        if line.startswith("INSERT INTO `dc_class_label`"):
            in_labels = True
            line = line.replace(", `element`) VALUES", ") VALUES")
        elif in_labels:
            if not line.startswith("("):
                in_labels = False
            else:
                stripped = re.sub(r", '[^']*'\)([,;])$", r")\1", line.rstrip("\n"))
                assert stripped != line.rstrip("\n"), line
                line = stripped + "\n"
        out.append(line)
    return "".join(out)


class GeneratedFile(unittest.TestCase):
    def test_the_committed_sql_is_what_the_generator_writes(self):
        rows, passives, labels, passive_labels, class_map, _, _, _ = built()
        self.assertEqual(rendered(rows, passives, labels, passive_labels, class_map)
                         .encode("utf-8"), GENERATED.read_bytes())

    def test_rerunning_the_generator_changes_nothing(self):
        first = rendered(*built()[:5])
        second = rendered(*built()[:5])
        self.assertEqual(first, second)

    def test_the_migration_matches_the_generated_file(self):
        # world_0014, world_0015, world_0018, world_0022, world_0050, world_0062, world_0068, world_0074 and world_0080 are
        # written for good, so the catalogue publishes to world_0087 (the Shaman's rows) and that is the one that tracks the generator.
        self.assertEqual(gcc.MIGRATION, "world_0089_class_catalogue.sql")
        migration = UPDATES / gcc.MIGRATION
        self.assertEqual(migration.read_bytes(), GENERATED.read_bytes())

    def test_the_applied_migration_is_what_was_applied(self):
        """world_0014 went out with the Barbarian alone and is never rewritten.

        Pinned to the commit that holds the release receipt
        (docs/deploy-release-20260922.md), which does not move with HEAD. A
        reference that cannot be read is a failure, not a pass.
        """
        self.assertEqual(set(gcc.APPLIED_MIGRATIONS), set(APPLIED))
        for name, receipt in APPLIED.items():
            published = subprocess.run(
                ["git", "show", f"{receipt}:mod-diablocraft/data/sql/db-world/updates/{name}"],
                cwd=ROOT.parent, capture_output=True)
            self.assertEqual(published.returncode, 0,
                             f"the receipt {receipt} has no {name}: "
                             f"{published.stderr.decode().strip()}")
            self.assertEqual((UPDATES / name).read_bytes(), published.stdout,
                             f"{name} is applied history and has been rewritten")

    def test_the_barbarian_alone_still_renders_the_applied_migration(self):
        # The Barbarian's catalogue did not move: its rows alone, rendered by
        # today's generator, are byte for byte what world_0014 applied once the
        # skills window's two additions are taken back out.
        rows, passives, labels, passive_labels, class_map, _, _, _ = built()
        own = {row[1] for row in of_class(passives, BARBARIAN)}
        sql = rendered(of_class(rows, BARBARIAN), of_class(passives, BARBARIAN),
                       of_class(labels, BARBARIAN, 1),
                       [row for row in passive_labels if row[0] in own],
                       of_class(class_map, BARBARIAN))
        self.assertEqual(without_window_data(sql).encode("utf-8"),
                         (UPDATES / "world_0014_class_catalogue.sql").read_bytes())

    def test_only_the_window_data_moved_since_world_0018(self):
        # The two older classes: world_0022 is world_0018 plus the element column and
        # dc_class_category, and nothing else.
        self.assertEqual(without_window_data(rendered(*without_monk(built()))).encode("utf-8"),
                         (UPDATES / "world_0018_class_catalogue.sql").read_bytes())

    def test_the_older_classes_still_render_world_0022(self):
        # diablocraft-3mk78: the Monk's rows arrive in world_0050 and change nothing of the Barbarian's and the
        # Wizard's; their render, without the Monk, is byte for byte what world_0022 applied.
        self.assertEqual(rendered(*without_monk(built())).encode("utf-8"),
                         (UPDATES / "world_0022_class_catalogue.sql").read_bytes())

    def test_the_older_classes_still_render_world_0050(self):
        # diablocraft-im7mr.5: the Necromancer's rows arrive in world_0062 and change nothing of the three earlier
        # classes'; their render, without the Necromancer, is byte for byte what world_0050 holds.
        self.assertEqual(rendered(*without(built(), NECROMANCER, CRUSADER, DEMON_HUNTER, WITCH_DOCTOR, SHAMAN)).encode("utf-8"),
                         (UPDATES / "world_0050_class_catalogue.sql").read_bytes())

    def test_the_older_classes_still_render_world_0062(self):
        # diablocraft-qulab: the Crusader's rows arrive in world_0068 and change nothing of the four earlier
        # classes'; their render, without the Crusader, is byte for byte what world_0062 holds.
        self.assertEqual(rendered(*without(built(), CRUSADER, DEMON_HUNTER, WITCH_DOCTOR, SHAMAN)).encode("utf-8"),
                         (UPDATES / "world_0062_class_catalogue.sql").read_bytes())

    def test_the_older_classes_still_render_world_0068(self):
        # diablocraft-vawmy.3: the Demon Hunter's rows arrive in world_0074 and change nothing of the five earlier
        # classes'; their render, without the Demon Hunter, is byte for byte what world_0068 holds.
        self.assertEqual(rendered(*without(built(), DEMON_HUNTER, WITCH_DOCTOR, SHAMAN)).encode("utf-8"),
                         (UPDATES / "world_0068_class_catalogue.sql").read_bytes())

    def test_the_older_classes_still_render_world_0074(self):
        # diablocraft-vxrcu.5: the Witch Doctor's rows arrive in world_0080 and change nothing of the six earlier
        # classes'; their render, without the Witch Doctor, is byte for byte what world_0074 holds.
        self.assertEqual(rendered(*without(built(), WITCH_DOCTOR, SHAMAN)).encode("utf-8"),
                         (UPDATES / "world_0074_class_catalogue.sql").read_bytes())

    def test_the_older_classes_still_render_world_0080(self):
        # diablocraft-xnrvn.6: the Shaman's rows arrive in world_0087 and change nothing of the seven earlier
        # classes'; their render, without the Shaman, is byte for byte what world_0080 holds.
        self.assertEqual(rendered(*without(built(), SHAMAN)).encode("utf-8"),
                         (UPDATES / "world_0080_class_catalogue.sql").read_bytes())

    def test_the_strip_would_notice_a_moved_row(self):
        # The comparison above is only evidence if the strip keeps real changes.
        rows, passives, labels, passive_labels, class_map, _, _, _ = built()
        labels = list(labels)
        first = labels[0]
        labels[0] = (first[0], first[1], first[2], first[3], "Moved", first[5])
        self.assertNotEqual(
            without_window_data(rendered(rows, passives, labels, passive_labels, class_map))
            .encode("utf-8"), (UPDATES / "world_0018_class_catalogue.sql").read_bytes())


class Rejections(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        shutil.copytree(D3, self.root / "d3")
        self.saved = gcc.D3
        gcc.D3 = self.root / "d3"
        self.addCleanup(setattr, gcc, "D3", self.saved)

    def rewrite(self, name, change):
        path = gcc.D3 / name
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header, body = next(reader), list(reader)
        change(header, body)
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(body)
        path.write_text(out.getvalue(), encoding="utf-8")

    def test_the_fixture_builds_before_anything_is_broken(self):
        rows = built()[0]
        self.assertEqual(len(of_class(rows, BARBARIAN)), 138)
        self.assertEqual(len(rows), 138 + 156 + 132 + 126 + 144 + 144 + 138 + 144)

    def test_a_class_with_no_class_id_is_rejected(self):
        self.rewrite("class_map.csv", lambda header, body:
                     body[0].__setitem__(header.index("class_id"), ""))
        with self.assertRaisesRegex(ValueError, "has no class_id"):
            built()

    def test_a_non_numeric_class_id_is_rejected(self):
        self.rewrite("class_map.csv", lambda header, body:
                     body[0].__setitem__(header.index("class_id"), "first"))
        with self.assertRaisesRegex(ValueError, "class_id must be a positive"):
            built()

    def test_a_duplicate_class_id_is_rejected(self):
        self.rewrite("class_map.csv", lambda header, body:
                     body[1].__setitem__(header.index("class_id"),
                                         body[0][header.index("class_id")]))
        with self.assertRaisesRegex(ValueError, "duplicate class_id"):
            built()

    def test_a_skill_with_no_generated_shell_is_rejected(self):
        self.rewrite("barbarian_skills.csv", lambda header, body:
                     body[0].__setitem__(header.index("skill_name"), "Invented Skill"))
        with self.assertRaisesRegex(ValueError, "of 23 skills have shells"):
            built()

    def test_a_rune_whose_skill_does_not_exist_is_rejected(self):
        self.rewrite("barbarian_runes.csv", lambda header, body:
                     body[0].__setitem__(header.index("skill_name"), "No Such Skill"))
        with self.assertRaisesRegex(ValueError, "has no skill"):
            built()

    def test_a_passive_with_no_generated_shell_is_rejected(self):
        self.rewrite("barbarian_passives.csv", lambda header, body:
                     body[0].__setitem__(header.index("passive_name"), "Invented Passive"))
        with self.assertRaisesRegex(ValueError, "no passive shell"):
            built()


    # --- diablocraft-skills-window-class-data --------------------------------

    def orders(self):
        return gcc.category_orders(built()[4])

    def test_the_fixture_orders_before_anything_is_broken(self):
        self.assertEqual(len(self.orders()), 48)

    def test_a_class_with_generated_spells_but_no_order_row_fails(self):
        self.rewrite("class_skill_categories.csv", lambda header, body: body.__setitem__(
            slice(None), [row for row in body if row[header.index("d3_class")] != "Wizard"]))
        with self.assertRaisesRegex(ValueError, "Wizard has generated spells but no row"):
            self.orders()

    def test_a_used_category_with_no_order_fails(self):
        def drop(header, body):
            body[:] = [row for row in body if (row[0], row[1]) != ("Barbarian", "Rage")]
        self.rewrite("class_skill_categories.csv", drop)
        with self.assertRaisesRegex(ValueError, "no display order for categories \\['Rage'\\]"):
            self.orders()

    def test_a_category_ordered_twice_fails(self):
        self.rewrite("class_skill_categories.csv", lambda header, body:
                     body[1].__setitem__(header.index("category"), "Primary"))
        with self.assertRaisesRegex(ValueError, "orders 'Primary' twice"):
            self.orders()

    def test_a_repeated_or_gapped_order_fails(self):
        self.rewrite("class_skill_categories.csv", lambda header, body:
                     body[1].__setitem__(header.index("display_order"), "1"))
        with self.assertRaisesRegex(ValueError, "no gap or repeat"):
            self.orders()

    def test_an_order_for_a_category_no_skill_uses_fails(self):
        self.rewrite("class_skill_categories.csv", lambda header, body:
                     body.insert(6, ["Barbarian", "Fury", "7", "test fixture"]))
        with self.assertRaisesRegex(ValueError, "orders \\['Fury'\\], which no skill"):
            self.orders()

    def test_an_order_row_without_a_source_fails(self):
        self.rewrite("class_skill_categories.csv", lambda header, body:
                     body[0].__setitem__(header.index("source"), ""))
        with self.assertRaisesRegex(ValueError, "source are all required"):
            self.orders()

    def test_a_planned_class_is_shape_checked_too(self):
        def gap(header, body):
            for row in body:
                if row[0] == "Crusader" and row[1] == "Conviction":
                    row[header.index("display_order")] = "9"
        self.rewrite("class_skill_categories.csv", gap)
        with self.assertRaisesRegex(ValueError, "Crusader display_order must be 1..6"):
            self.orders()

    def test_a_rune_with_no_element_fails(self):
        self.rewrite("wizard_runes.csv", lambda header, body:
                     body[0].__setitem__(header.index("element"), ""))
        with self.assertRaisesRegex(ValueError, "Wizard: rune 'Magic Missile - Charged Blast' "
                                                "has no element"):
            built()

    def test_a_skill_with_no_element_fails(self):
        self.rewrite("barbarian_skills.csv", lambda header, body:
                     body[0].__setitem__(header.index("element"), " "))
        with self.assertRaisesRegex(ValueError, "Barbarian: skill 'Frenzy' has no element"):
            built()

if __name__ == "__main__":
    unittest.main(verbosity=2)

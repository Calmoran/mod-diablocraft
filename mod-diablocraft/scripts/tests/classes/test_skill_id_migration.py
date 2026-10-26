"""K3+K5 - saved picks and affix bridges resolve by spell id, not by English name.

What this suite does and does not prove, stated up front because the subject is
a migration that rewrites saved characters:

  * The **mapping** is checked against the catalogue the server loads, in full.
  * The **abort guard** is executed - the statements are lifted verbatim out of
    the generated migration and run, so the "fail loudly" claim is a measured
    behaviour rather than a reading of the SQL. SQLite stands in for MySQL for
    those two statements; they use nothing MySQL-specific, but the substitution
    is real and is named here rather than glossed over.
  * The **uniqueness choice** is executed the same way, because keying the
    once-per-bar rule on the wrong column is the kind of bug that looks correct.
  * The migration as a whole has **not been run against any database**. It has
    no `ENGINE`-free form, it rewrites saved characters, and applying it is the
    PM's step after review. Nothing here should be read as evidence that it has
    been applied or rehearsed end to end.
"""
import importlib
import io
import pathlib
import re
import sqlite3
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import generate_class_catalogue as gcc
import generate_skill_affixes as affixes
import generate_skill_id_migration as migration

MODULE = pathlib.Path(__file__).resolve().parents[3]
MIGRATION_PATH = MODULE / "data/sql/db-characters/updates" / migration.MIGRATION
CLASSES = (MODULE / "src/classes/dc_classes.cpp").read_text(encoding="utf-8")
ITEMS = items_source.source()
BONUSES = (MODULE / "src/items/dc_skill_bonuses.h").read_text(encoding="utf-8")
COMBAT = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])


def code(source):
    """Comments removed, so prose about a removed pattern cannot fail a test
    that proves the pattern is gone - the trap an earlier task walked into."""
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("--") or stripped.startswith("#"):
            continue
        lines.append(line.split("//")[0])
    return "\n".join(lines)


def statements(sql):
    """The migration split into statements, comments dropped."""
    body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [part.strip() for part in body.split(";") if part.strip()]


TARGETS = ("`dc_character_skillbar`", "`dc_character_passives`", "`characters`")


def all_statements():
    return statements(MIGRATION_PATH.read_text(encoding="utf-8"))


def abort_indices():
    """Where each guard sits in the file. The preflight pair reads the report
    table; the backstop pair reads the target tables after the conversion."""
    preflight, backstop = [], []
    for index, part in enumerate(all_statements()):
        if not part.lstrip().startswith("INSERT INTO `dc_skill_id_abort`"):
            continue
        (preflight if "`dc_skill_id_unresolved`" in part else backstop).append(index)
    return preflight, backstop


def abort_statements():
    """The preflight guard statements, verbatim from the generated file."""
    preflight, _ = abort_indices()
    return [f"{all_statements()[index]};" for index in preflight]


def mutates_a_target(statement):
    """True when this statement could change a table that already holds data."""
    head = statement.lstrip().upper()
    if head.startswith("ALTER TABLE") or head.startswith("UPDATE") or head.startswith("DELETE"):
        return any(target in statement for target in TARGETS)
    if head.startswith("INSERT"):
        # An INSERT INTO one of the target tables; reading them in a SELECT is
        # not a mutation, so only the destination counts.
        destination = statement.split("(")[0]
        return any(target in destination for target in TARGETS)
    return False


class Mapping(unittest.TestCase):
    def setUp(self):
        self.actives, self.passives = migration.mapping()
        (rows, passives, self.labels,
         self.passive_labels, self.class_map, _, _, _) = gcc.catalogue()
        # diablocraft-wizard-records: the catalogue holds every class, but the
        # applied migration converts only the classes that had saved rows to
        # convert - the Barbarian - and must stay byte-identical. The mapping
        # is checked in full against exactly those classes' entries.
        self.rows = [row for row in rows if row[0] in migration.CONVERTED_CLASS_IDS]
        self.catalogue_passives = [row for row in passives
                                   if row[0] in migration.CONVERTED_CLASS_IDS]

    def test_only_the_barbarian_is_converted(self):
        """classes_0004 was applied Barbarian-only; a second class widening the
        mapping would rewrite an applied migration (diablocraft-wizard-records)."""
        self.assertEqual(migration.CONVERTED_CLASS_IDS, (1,))
        self.assertTrue(self.rows, "the catalogue has no Barbarian entry to convert")

    def test_every_catalogue_entry_can_be_converted(self):
        self.assertEqual(len(self.actives), len(self.rows))
        self.assertEqual(len(self.passives), len(self.catalogue_passives))
        label_of = {(l[1], l[0]): (l[2], l[3]) for l in self.labels}
        wow = {row[0]: row[3] for row in self.class_map}
        expected = {(wow[c], *label_of[(c, spell)]) for c, _s, _r, spell, _u, _i in self.rows}
        self.assertEqual({row[:3] for row in self.actives}, expected)

    def test_the_pair_saved_today_maps_to_both_ids(self):
        """A bar row stores the base skill and the cast shell; both come back."""
        by_pair = {row[:3]: row[3:] for row in self.actives}
        for class_id, skill_id, rune_id, spell_id, _unlock, _indicator in self.rows:
            label = {(l[1], l[0]): (l[2], l[3]) for l in self.labels}[(class_id, spell_id)]
            wow = {row[0]: row[3] for row in self.class_map}[class_id]
            self.assertEqual(by_pair[(wow, *label)], (skill_id, spell_id))
            if rune_id:
                self.assertNotEqual(skill_id, spell_id)
            else:
                self.assertEqual(skill_id, spell_id)

    def test_no_name_pair_maps_to_two_different_ids(self):
        keys = [row[:3] for row in self.actives]
        self.assertEqual(len(keys), len(set(keys)))
        passive_keys = [row[:2] for row in self.passives]
        self.assertEqual(len(passive_keys), len(set(passive_keys)))

    def test_a_colliding_name_pair_is_refused(self):
        """Two entries with one name but different ids must stop the generator."""
        original = gcc.catalogue

        def collide():
            rows, passives, labels, passive_labels, class_map, playable, waiting, amb = original()
            # Relabel the second entry to the first one's name, keeping its ids.
            first, second = labels[0], labels[1]
            labels[1] = (second[0], second[1], first[2], first[3], second[4])
            return rows, passives, labels, passive_labels, class_map, playable, waiting, amb

        gcc.catalogue = collide
        try:
            with self.assertRaisesRegex(ValueError, "maps to both"):
                migration.mapping()
        finally:
            gcc.catalogue = original


class AbortGuard(unittest.TestCase):
    """The guard, executed. SQLite stands in for MySQL on these two statements."""

    def build(self, unresolved_skillbar, unresolved_passives):
        """The state the preflight leaves behind: a report table holding one
        row per pick that would not convert."""
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE `dc_skill_id_abort` (`reason` VARCHAR(190) NOT NULL PRIMARY KEY)")
        db.execute("CREATE TABLE `dc_skill_id_unresolved` (`source` TEXT NOT NULL, "
                   "`guid` INTEGER NOT NULL, `slot` INTEGER NOT NULL, `pick` TEXT NOT NULL, "
                   "`reason` TEXT NOT NULL)")
        rows = [("dc_character_skillbar", n, n, "Bash", "name not in catalogue")
                for n in range(unresolved_skillbar)]
        rows += [("dc_character_passives", n, n, "Ruthless", "no character row")
                 for n in range(unresolved_passives)]
        db.executemany("INSERT INTO `dc_skill_id_unresolved` VALUES (?, ?, ?, ?, ?)", rows)
        return db

    def test_there_are_two_preflight_guards_and_two_backstops(self):
        preflight, backstop = abort_indices()
        self.assertEqual(len(preflight), 2)
        self.assertEqual(len(backstop), 2)

    # --- the PM return: DDL commits, so the guard must come first -----------

    def test_nothing_touches_a_target_table_before_the_preflight_aborts(self):
        """MySQL commits DDL implicitly, so a guard placed after the ALTER
        cannot undo it. This is the property that makes a refused run a no-op:
        no statement up to and including the abort can change a table that
        already holds data."""
        preflight, _ = abort_indices()
        self.assertTrue(preflight, "there is no preflight guard at all, so nothing is checked "
                                   "before the schema changes")
        for index, statement in enumerate(all_statements()[:max(preflight) + 1]):
            self.assertFalse(mutates_a_target(statement),
                             f"statement {index} runs before the abort and mutates a target:\n"
                             f"{statement[:200]}")

    def test_the_schema_change_and_conversion_come_after_the_abort(self):
        preflight, _ = abort_indices()
        self.assertTrue(preflight, "there is no preflight guard before the schema changes")
        mutating = [index for index, statement in enumerate(all_statements())
                    if mutates_a_target(statement)]
        self.assertTrue(mutating, "the migration changes nothing at all")
        self.assertGreater(min(mutating), max(preflight))

    def test_the_backstop_runs_after_the_conversion_and_names_the_recovery(self):
        preflight, backstop = abort_indices()
        self.assertTrue(preflight and backstop, "both guards must exist")
        mutating = [index for index, statement in enumerate(all_statements())
                    if mutates_a_target(statement)]
        self.assertGreater(min(backstop), max(preflight))
        self.assertGreater(min(backstop), min(mutating))
        body = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("Restore both tables from the backup before retrying", body)

    def test_the_mutating_statements_are_the_ones_expected(self):
        """Named, so a new one cannot quietly join them."""
        mutating = [statement.lstrip().split("\n")[0]
                    for statement in all_statements() if mutates_a_target(statement)]
        self.assertEqual(mutating, [
            "ALTER TABLE `dc_character_skillbar`",
            "ALTER TABLE `dc_character_passives`",
            "UPDATE `dc_character_skillbar` s",
            "UPDATE `dc_character_passives` p",
            "ALTER TABLE `dc_character_skillbar`",
            "ALTER TABLE `dc_character_passives`",
        ])

    def test_a_fully_resolved_database_passes_the_guard(self):
        db = self.build(0, 0)
        for statement in abort_statements():
            db.execute(statement)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM `dc_skill_id_abort`").fetchone()[0], 0)

    def test_one_unresolved_skillbar_row_aborts(self):
        db = self.build(1, 0)
        with self.assertRaises(sqlite3.IntegrityError):
            for statement in abort_statements():
                db.execute(statement)

    def test_one_unresolved_passive_row_aborts(self):
        db = self.build(0, 1)
        with self.assertRaises(sqlite3.IntegrityError):
            for statement in abort_statements():
                db.execute(statement)

    def test_many_unresolved_rows_abort(self):
        db = self.build(7, 5)
        with self.assertRaises(sqlite3.IntegrityError):
            for statement in abort_statements():
                db.execute(statement)

    def test_no_string_literal_carries_a_semicolon(self):
        """What makes splitting this file on semicolons safe, asserted rather
        than hoped for - and what the first version of the abort message got
        wrong, which is how this test exists."""
        body = MIGRATION_PATH.read_text(encoding="utf-8")
        for literal in re.findall(r"'((?:[^']|'')*)'", body):
            self.assertNotIn(";", literal, literal)

    def test_the_abort_message_says_where_to_look(self):
        for statement in abort_statements():
            self.assertIn("MIGRATION ABORTED", statement)
            self.assertIn("dc_skill_id_unresolved", statement)

    def test_the_report_table_survives_the_migration(self):
        """It is the evidence the abort message points at, so it is not dropped."""
        body = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE `dc_skill_id_unresolved`", body)
        self.assertNotIn("DROP TABLE IF EXISTS `dc_skill_id_unresolved`;\n\nDROP", body)
        self.assertEqual(body.count("DROP TABLE IF EXISTS `dc_skill_id_unresolved`;"), 1)

    def test_the_report_separates_a_stale_row_from_an_unknown_name(self):
        body = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("no character row", body)
        self.assertIn("name not in catalogue", body)


class OnceOnTheBar(unittest.TestCase):
    """K6 keys on the base skill. Keying it on the cast shell looks right and
    is not: two runes of one skill would both be allowed onto the bar."""

    def runes_of_one_skill(self):
        rows, _, labels, _, _, _, _, _ = gcc.catalogue()
        by_skill = {}
        for class_id, skill_id, rune_id, spell_id, _u, _i in rows:
            if rune_id:
                by_skill.setdefault(skill_id, []).append(spell_id)
        skill_id, spells = next(iter(sorted(by_skill.items())))
        return skill_id, spells[:2]

    def test_two_runes_of_one_skill_share_a_skill_id_and_differ_in_spell_id(self):
        skill_id, spells = self.runes_of_one_skill()
        self.assertEqual(len(spells), 2)
        self.assertNotEqual(spells[0], spells[1])
        self.assertNotIn(skill_id, spells)

    def test_the_key_the_migration_uses_refuses_the_second_rune(self):
        skill_id, spells = self.runes_of_one_skill()
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE bar (guid INT, slot INT, skill_id INT, spell_id INT, "
                   "UNIQUE (guid, skill_id))")
        db.execute("INSERT INTO bar VALUES (1, 0, ?, ?)", (skill_id, spells[0]))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO bar VALUES (1, 1, ?, ?)", (skill_id, spells[1]))

    def test_keying_on_the_cast_shell_would_have_let_both_through(self):
        """The bug this choice avoids, demonstrated rather than asserted."""
        skill_id, spells = self.runes_of_one_skill()
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE bar (guid INT, slot INT, skill_id INT, spell_id INT, "
                   "UNIQUE (guid, spell_id))")
        db.execute("INSERT INTO bar VALUES (1, 0, ?, ?)", (skill_id, spells[0]))
        db.execute("INSERT INTO bar VALUES (1, 1, ?, ?)", (skill_id, spells[1]))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM bar").fetchone()[0], 2)

    def test_the_migration_keys_the_bar_on_skill_id(self):
        body = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("ADD UNIQUE KEY `uk_dc_skillbar_once` (`guid`, `skill_id`)", body)
        self.assertIn("ADD UNIQUE KEY `uk_dc_passives_once` (`guid`, `spell_id`)", body)


class ProductionJoinsOnIds(unittest.TestCase):
    def test_the_bar_is_read_by_id(self):
        self.assertIn("SELECT slot, skill_id, spell_id FROM dc_character_skillbar", code(CLASSES))
        self.assertNotIn("SELECT slot, skill, rune FROM dc_character_skillbar", code(CLASSES))

    def test_passives_are_read_by_id(self):
        self.assertIn("SELECT slot, spell_id FROM dc_character_passives", code(CLASSES))
        self.assertNotIn("SELECT slot, passive FROM dc_character_passives", code(CLASSES))

    def test_the_once_per_bar_delete_matches_on_skill_id(self):
        body = code(CLASSES)
        self.assertIn("OR skill_id={}", body)
        self.assertNotIn("OR skill='{}'", body)
        self.assertIn("OR spell_id={}", body)
        self.assertNotIn("OR passive='{}'", body)

    def test_the_class_loader_no_longer_reads_spell_dbc_names(self):
        """The K3 defect itself: the English name was the join key."""
        body = code(CLASSES)
        self.assertNotIn("Name_Lang_enUS", body)
        # Since diablocraft-wizard-resource the shells a class learns are its
        # own catalogue and passive ids, joined to spell_dbc by id - still no
        # name - rather than the Barbarian's id range for every class.
        self.assertIn("JOIN spell_dbc s ON s.ID = c.spell_id", body)
        self.assertIn("JOIN spell_dbc s ON s.ID = p.spell_id", body)
        self.assertNotIn("shellIds", body)

    def test_the_only_name_resolution_left_is_typed_input(self):
        """ShellFor is reached from a player typing a name, and it answers from
        the catalogue rather than from Spell.dbc."""
        body = code(CLASSES)
        self.assertIn("bool ShellFor(Player const* player", body)
        self.assertIn("Entry(player, Key(skill, rune))", body)
        # It kept the lock the name lookup has always taken.
        shell = body[body.index("bool ShellFor(Player const* player"):]
        self.assertIn("std::lock_guard<std::mutex> lock(dataMutex);",
                      shell[:shell.index("\n}")])


class AffixBridge(unittest.TestCase):
    def setUp(self):
        self.rows = affixes.definitions()
        catalogue_rows, _, _, _, _, _, _, _ = gcc.catalogue()
        self.skill_ids = {row[1] for row in catalogue_rows}
        self.base_ids = {row[1] for row in catalogue_rows if row[2] == 0}

    def test_every_affix_names_a_real_base_skill(self):
        # diablocraft-class-roll-rules: every playable class's D3Planner groups
        # (Barbarian 15, Wizard 16), not the Barbarian's alone; diablocraft-3mk78 makes the Monk playable and adds
        # its 13 (the Monk's skill_<slot> groups in D3Planner's data.json).
        by_class = {}
        for row in self.rows:
            by_class[row[3]] = by_class.get(row[3], 0) + 1
        # The Necromancer (class id 5) adds its 13, the Crusader (class id 4) its 14, the Demon Hunter (class id 6) its 17, the Witch Doctor (class id 7) its 17, the Shaman (class id 8) its 13 (test_skill_affix_groups.py).
        self.assertEqual(by_class, {1: 15, 2: 16, 3: 13, 4: 14, 5: 13, 6: 17, 7: 17, 8: 13})
        self.assertEqual(len(self.rows), 15 + 16 + 13 + 14 + 13 + 17 + 17 + 13)
        self.assertEqual(len([row for row in self.rows if row[3] in affixes.APPLIED_CLASS_IDS]), 15)
        for _group, _index, affix, class_id, skill_id, _skill, _name in self.rows:
            self.assertIn(skill_id, self.base_ids, affix)
            self.assertTrue(class_id)

    def test_the_bridge_is_loaded_and_used_by_id(self):
        self.assertIn("class_id,skill_id FROM dc_skill_affix", code(ITEMS))
        self.assertIn("skillId = found->second.skillId", code(ITEMS))
        self.assertIn("double SkillDamageBonus(std::uint64_t playerGuid, std::uint32_t skillId)",
                      code(ITEMS))

    def test_a_row_without_a_skill_id_is_refused_at_load(self):
        self.assertIn("dc_skill_affix row has no skill_id", ITEMS)

    def test_the_bonus_container_is_keyed_by_id(self):
        body = code(BONUSES)
        self.assertIn("std::unordered_map<std::uint32_t, double> totals;", body)
        self.assertIn("void Set(std::uint64_t id, std::uint32_t skillId, double value)", body)
        self.assertIn("double Get(std::uint32_t skillId) const", body)
        self.assertNotIn("std::string const& skill", body)

    def test_combat_asks_for_the_base_skill_of_the_cast_shell(self):
        self.assertIn("Classes::SkillIdOf(shell.spellId)", code(COMBAT))

    def test_a_normalised_name_collision_is_refused(self):
        """Two skills that normalise alike must stop the generator, not pick one."""
        original = gcc.catalogue

        def collide():
            rows, passives, labels, passive_labels, class_map, playable, waiting, amb = original()
            base = [i for i, l in enumerate(labels) if not l[3]]
            first, second = labels[base[0]], labels[base[1]]
            # Same letters, different punctuation: identical once normalised.
            labels[base[1]] = (second[0], second[1], first[2].upper() + "!", second[3], second[4])
            return rows, passives, labels, passive_labels, class_map, playable, waiting, amb

        gcc.catalogue = collide
        try:
            with self.assertRaisesRegex(ValueError, "normalise to"):
                affixes.definitions()
        finally:
            gcc.catalogue = original

    def test_the_applied_repair_migration_is_unchanged(self):
        """items_0005 is already applied; regenerating must not move a byte."""
        path = MODULE / "data/sql/db-characters/updates/items_0005_resolve_skill_affixes.sql"
        before = path.read_bytes()
        affixes.main()
        self.assertEqual(path.read_bytes(), before)


class GeneratedFile(unittest.TestCase):
    def test_the_committed_migration_is_what_the_generator_writes(self):
        before = MIGRATION_PATH.read_bytes()
        sql, _, _ = migration.generate()
        self.assertEqual(MIGRATION_PATH.read_bytes(), before)
        self.assertEqual(sql.encode("utf-8"), before)

    def test_regenerating_twice_is_identical(self):
        first = migration.render(*migration.mapping())
        second = migration.render(*migration.mapping())
        self.assertEqual(first, second)

    def test_the_migration_carries_every_mapping_row_as_a_literal(self):
        """No cross-database join: the catalogue is not reachable from here."""
        body = MIGRATION_PATH.read_text(encoding="utf-8")
        actives, passives = migration.mapping()
        self.assertEqual(body.count("\n("), len(actives) + len(passives))
        self.assertNotIn("acore_world", body)
        self.assertNotIn("DELIMITER", body)
        self.assertNotIn("SIGNAL", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)

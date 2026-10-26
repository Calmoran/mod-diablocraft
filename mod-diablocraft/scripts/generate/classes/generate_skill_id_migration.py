"""K3 - convert saved skill, rune and passive picks from English names to ids.

`dc_character_skillbar` and `dc_character_passives` store what a player chose
as text, and `dc_classes.cpp` turned that text back into a spell by looking the
English name up in Spell.dbc. Renaming a skill in the sheets would therefore
orphan every saved pick that used it.

This writes the one migration that converts the existing rows. Two constraints
shape it, and both were checked against the repository rather than assumed:

  * **No cross-database join.** The saved picks live in the characters
    database and the catalogue lives in the world database; no migration in
    this module references another schema, and the schema names are
    configurable. So the mapping travels *inside* the migration, as literals
    generated from the same catalogue that the server reads.
  * **No stored procedure.** Nothing in `data/sql` uses `DELIMITER` or
    `SIGNAL`, so the "fail loudly" requirement is met with a statement that
    cannot succeed when an unresolved row exists: it selects the same abort
    message twice per offending row into a primary key, so one unresolved row
    is a duplicate-key error quoting the message, and zero unresolved rows
    insert nothing at all. That behaviour does not depend on `sql_mode`.

The class comes from `characters.class` - the same database - matched against
`wow_class_id` from `class_map.csv`, so no class is named here either.

Nothing in this script applies anything. It writes a file for the PM to
review.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_class_catalogue as catalogue_source
from applied_migrations import write_migration

ROOT = pathlib.Path(__file__).resolve().parents[3]
MIGRATION = 'classes_0004_skill_ids.sql'
# The classes this migration converted. It was applied on 2026-09-22
# (docs/deploy-release-20260922.md) when the Barbarian was the only class with
# records, and an applied migration is never regenerated with new content. A
# class that joins later has no saved skill rows to convert - its characters
# pick from the catalogue - so it stays out of this file
# (diablocraft-wizard-records).
CONVERTED_CLASS_IDS = (1,)

# The message a duplicate-key abort quotes back. It has to fit the key length
# and say what to do next, because for whoever runs the migration this string
# IS the error report.
#
# It carries NO semicolon. A semicolon inside a string literal breaks any tool
# that splits a script on semicolons, and a migration that rewrites saved
# characters should not depend on how carefully its runner parses SQL.
ABORT_SKILLBAR = ('MIGRATION ABORTED - a saved skill bar row did not resolve to a spell id. '
                  'See table dc_skill_id_unresolved and apply nothing further')
ABORT_PASSIVES = ('MIGRATION ABORTED - a saved passive row did not resolve to a spell id. '
                  'See table dc_skill_id_unresolved and apply nothing further')
# The backstop past the point of no return. It names the recovery, because by
# then the DDL is committed and only the backup can undo it.
ABORT_BACKSTOP = ('MIGRATION ABORTED AFTER SCHEMA CHANGE - a row was not converted although the '
                  'preflight passed. Restore both tables from the backup before retrying')


def quote(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "''") + "'"


def mapping():
    """(wow_class_id, skill_name, rune_name, skill_id, spell_id) per entry, and
    the passive equivalent, straight from the catalogue the server loads."""
    rows, passives, labels, passive_labels, class_map, _, _, _ = catalogue_source.catalogue()
    wow_class = {row[0]: row[3] for row in class_map}          # class_id -> wow_class_id
    label_of = {(label[1], label[0]): (label[2], label[3]) for label in labels}
    actives = []
    for class_id, skill_id, _rune_id, spell_id, _unlock, _indicator in rows:
        if class_id not in CONVERTED_CLASS_IDS:
            continue
        skill_name, rune_name = label_of[(class_id, spell_id)]
        actives.append((wow_class[class_id], skill_name, rune_name, skill_id, spell_id))
    passive_name = {label[0]: label[1] for label in passive_labels}
    passive_rows = [(wow_class[class_id], passive_name[spell_id], spell_id)
                    for class_id, spell_id, _unlock in passives
                    if class_id in CONVERTED_CLASS_IDS]

    # A name pair that maps to two different ids would convert saved rows at
    # random, so it is an error here rather than a surprise in the database.
    for name, seen in (('skill', {}), ('passive', {})):
        source = actives if name == 'skill' else passive_rows
        for row in source:
            key = row[:3] if name == 'skill' else row[:2]
            target = row[3:] if name == 'skill' else row[2:]
            if seen.setdefault(key, target) != target:
                raise ValueError(f'{name} {key!r} maps to both {seen[key]!r} and {target!r}; '
                                 f'saved rows could not be converted unambiguously')
    return actives, passive_rows


def render(actives, passive_rows):
    """The file, in an order that matters.

    Everything that can refuse the migration runs BEFORE anything that changes
    a target table. MySQL commits DDL implicitly, so a guard placed after the
    `ALTER TABLE` cannot undo it: an unresolved row would abort having already
    added the columns and half-converted the rows, and the rerun would then die
    on the duplicate column instead of on the real problem. So the preflight
    resolves every saved row against the mapping by NAME - which needs no new
    column - and aborts there. Past that point the conversion cannot fail for
    the reason the preflight tests.
    """
    lines = [
        '-- K3. Saved skill, rune and passive picks become spell ids.',
        '--',
        '-- Generated by generate_skill_id_migration.py from the class catalogue.',
        '-- Do not hand-edit: regenerate it. Review before applying; this file',
        '-- rewrites saved character choices.',
        '--',
        '-- ORDER MATTERS. MySQL commits DDL implicitly, so nothing here can be',
        '-- rolled back once it has run. Every check that can refuse this',
        '-- migration therefore runs BEFORE the first ALTER TABLE, and the only',
        '-- thing a refused run leaves behind is the report table.',
        '--',
        '-- The name columns are KEPT and still written, as display text and as',
        '-- the audit trail that makes this convertible back. Nothing joins on',
        '-- them any more: the server reads skill_id and spell_id.',
        '--',
        '-- The mapping is carried here as literals because the catalogue lives',
        '-- in the world database and the schema names are configurable, so a',
        '-- cross-database join would not be portable.',
        'SET NAMES utf8mb4;',
        '',
        '-- 1. The mapping, generated from the catalogue. Session-scoped: a',
        '--    TEMPORARY table is not a change to anything that survives.',
        'DROP TEMPORARY TABLE IF EXISTS `dc_skill_id_map`;',
        'CREATE TEMPORARY TABLE `dc_skill_id_map` (',
        '  `wow_class_id` TINYINT UNSIGNED NOT NULL,',
        '  `skill` VARCHAR(64) NOT NULL,',
        '  `rune` VARCHAR(64) NOT NULL,',
        '  `skill_id` INT UNSIGNED NOT NULL,',
        '  `spell_id` INT UNSIGNED NOT NULL,',
        '  PRIMARY KEY (`wow_class_id`, `skill`, `rune`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
        'INSERT INTO `dc_skill_id_map` (`wow_class_id`, `skill`, `rune`, `skill_id`, `spell_id`) VALUES',
    ]
    lines.append(',\n'.join('(' + ', '.join(
        (str(field) if isinstance(field, int) else quote(field)) for field in row) + ')'
        for row in actives) + ';')
    lines += [
        '',
        'DROP TEMPORARY TABLE IF EXISTS `dc_passive_id_map`;',
        'CREATE TEMPORARY TABLE `dc_passive_id_map` (',
        '  `wow_class_id` TINYINT UNSIGNED NOT NULL,',
        '  `passive` VARCHAR(64) NOT NULL,',
        '  `spell_id` INT UNSIGNED NOT NULL,',
        '  PRIMARY KEY (`wow_class_id`, `passive`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
        'INSERT INTO `dc_passive_id_map` (`wow_class_id`, `passive`, `spell_id`) VALUES',
    ]
    lines.append(',\n'.join('(' + ', '.join(
        (str(field) if isinstance(field, int) else quote(field)) for field in row) + ')'
        for row in passive_rows) + ';')
    lines += [
        '',
        '-- 2. PREFLIGHT. Resolve every saved row by NAME, which needs no new',
        '--    column, and record the ones that would not convert. This is the',
        '--    only table a refused run leaves behind, and no saved row and no',
        '--    target column has been touched at this point.',
        '--',
        '--    A row can fail for two different reasons and the fix differs, so',
        '--    the report says which: the character is gone (a stale row that',
        '--    should be deleted) or the name is not in the catalogue (a real',
        '--    unresolved pick that must be investigated before applying).',
        'DROP TABLE IF EXISTS `dc_skill_id_unresolved`;',
        'CREATE TABLE `dc_skill_id_unresolved` (',
        '  `source` VARCHAR(32) NOT NULL,',
        '  `guid` BIGINT UNSIGNED NOT NULL,',
        '  `slot` TINYINT UNSIGNED NOT NULL,',
        '  `pick` VARCHAR(160) NOT NULL,',
        '  `reason` VARCHAR(32) NOT NULL',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
        'INSERT INTO `dc_skill_id_unresolved` (`source`, `guid`, `slot`, `pick`, `reason`)',
        "  SELECT 'dc_character_skillbar', s.`guid`, s.`slot`,",
        "         CONCAT(s.`skill`, CASE WHEN s.`rune` = '' THEN '' ELSE CONCAT(' - ', s.`rune`) END),",
        "         CASE WHEN c.`guid` IS NULL THEN 'no character row' ELSE 'name not in catalogue' END",
        '  FROM `dc_character_skillbar` s',
        '  LEFT JOIN `characters` c ON c.`guid` = s.`guid`',
        '  LEFT JOIN `dc_skill_id_map` m ON m.`wow_class_id` = c.`class`',
        '   AND m.`skill` = s.`skill` AND m.`rune` = s.`rune`',
        '  WHERE m.`spell_id` IS NULL;',
        'INSERT INTO `dc_skill_id_unresolved` (`source`, `guid`, `slot`, `pick`, `reason`)',
        "  SELECT 'dc_character_passives', p.`guid`, p.`slot`, p.`passive`,",
        "         CASE WHEN c.`guid` IS NULL THEN 'no character row' ELSE 'name not in catalogue' END",
        '  FROM `dc_character_passives` p',
        '  LEFT JOIN `characters` c ON c.`guid` = p.`guid`',
        '  LEFT JOIN `dc_passive_id_map` m ON m.`wow_class_id` = c.`class`',
        '   AND m.`passive` = p.`passive`',
        '  WHERE m.`spell_id` IS NULL;',
        '',
        '-- 3. ABORT, still before any change to a target table. No stored',
        '--    procedure is available, so this aborts by selecting the same',
        '--    message twice for every unresolved row into a primary key: one',
        '--    such row is a duplicate-key error quoting the message, and none',
        '--    inserts nothing. It does not depend on sql_mode.',
        '--',
        '--    If this fires, the database is EXACTLY as it was. Read',
        '--    dc_skill_id_unresolved, fix the rows, and run the file again.',
        'DROP TEMPORARY TABLE IF EXISTS `dc_skill_id_abort`;',
        'CREATE TEMPORARY TABLE `dc_skill_id_abort` (',
        '  `reason` VARCHAR(190) NOT NULL,',
        '  PRIMARY KEY (`reason`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
        'INSERT INTO `dc_skill_id_abort` (`reason`)',
        f"  SELECT {quote(ABORT_SKILLBAR)} FROM `dc_skill_id_unresolved`",
        "   WHERE `source` = 'dc_character_skillbar'",
        '  UNION ALL',
        f"  SELECT {quote(ABORT_SKILLBAR)} FROM `dc_skill_id_unresolved`",
        "   WHERE `source` = 'dc_character_skillbar';",
        'INSERT INTO `dc_skill_id_abort` (`reason`)',
        f"  SELECT {quote(ABORT_PASSIVES)} FROM `dc_skill_id_unresolved`",
        "   WHERE `source` = 'dc_character_passives'",
        '  UNION ALL',
        f"  SELECT {quote(ABORT_PASSIVES)} FROM `dc_skill_id_unresolved`",
        "   WHERE `source` = 'dc_character_passives';",
        '',
        '-- 4. Past the guard, and only now. Every saved row is known to',
        '--    resolve, so the columns and the conversion cannot fail for the',
        '--    reason the preflight tests. The default of 0 means "not',
        '--    converted"; step 6 proves none is left.',
        'ALTER TABLE `dc_character_skillbar`',
        "  ADD COLUMN `skill_id` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'dc_class_catalogue.skill_id, the base skill' AFTER `slot`,",
        "  ADD COLUMN `spell_id` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'dc_class_catalogue.spell_id, the shell actually cast' AFTER `skill_id`;",
        'ALTER TABLE `dc_character_passives`',
        "  ADD COLUMN `spell_id` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'dc_class_passive.spell_id' AFTER `slot`;",
        '',
        '-- 5. Convert. The join is the same one the preflight used, so what it',
        '--    matches here is what it counted there.',
        'UPDATE `dc_character_skillbar` s',
        '  JOIN `characters` c ON c.`guid` = s.`guid`',
        '  JOIN `dc_skill_id_map` m ON m.`wow_class_id` = c.`class`',
        '   AND m.`skill` = s.`skill` AND m.`rune` = s.`rune`',
        '  SET s.`skill_id` = m.`skill_id`, s.`spell_id` = m.`spell_id`;',
        'UPDATE `dc_character_passives` p',
        '  JOIN `characters` c ON c.`guid` = p.`guid`',
        '  JOIN `dc_passive_id_map` m ON m.`wow_class_id` = c.`class`',
        '   AND m.`passive` = p.`passive`',
        '  SET p.`spell_id` = m.`spell_id`;',
        '',
        '-- 6. Backstop, not a rollback. If the preflight and the conversion',
        '--    ever disagreed, this stops before the keys change. It should be',
        '--    unreachable; DDL above is already committed if it does fire, so',
        '--    the recovery is the backup, which is why the backup is required.',
        'INSERT INTO `dc_skill_id_abort` (`reason`)',
        f"  SELECT {quote(ABORT_BACKSTOP)} FROM `dc_character_skillbar` WHERE `spell_id` = 0",
        '  UNION ALL',
        f"  SELECT {quote(ABORT_BACKSTOP)} FROM `dc_character_skillbar` WHERE `spell_id` = 0;",
        'INSERT INTO `dc_skill_id_abort` (`reason`)',
        f"  SELECT {quote(ABORT_BACKSTOP)} FROM `dc_character_passives` WHERE `spell_id` = 0",
        '  UNION ALL',
        f"  SELECT {quote(ABORT_BACKSTOP)} FROM `dc_character_passives` WHERE `spell_id` = 0;",
        '',
        '-- 7. The once-per-bar rule keys on the BASE skill, so it moves to',
        '--    skill_id and NOT to spell_id - two runes of one skill share a',
        '--    skill_id but not a spell_id, and keying on spell_id would',
        '--    silently let both onto the bar.',
        'ALTER TABLE `dc_character_skillbar`',
        '  DROP INDEX `uk_dc_skillbar_once`,',
        '  ADD UNIQUE KEY `uk_dc_skillbar_once` (`guid`, `skill_id`);',
        'ALTER TABLE `dc_character_passives`',
        '  DROP INDEX `uk_dc_passives_once`,',
        '  ADD UNIQUE KEY `uk_dc_passives_once` (`guid`, `spell_id`);',
        '',
        'DROP TEMPORARY TABLE IF EXISTS `dc_skill_id_map`;',
        'DROP TEMPORARY TABLE IF EXISTS `dc_passive_id_map`;',
        'DROP TEMPORARY TABLE IF EXISTS `dc_skill_id_abort`;',
        '-- dc_skill_id_unresolved is deliberately LEFT BEHIND. It is empty on a',
        '-- clean run, and on a failed one it is the report, so dropping it here',
        '-- would delete the evidence the abort message points at.',
        '',
    ]
    return '\n'.join(lines)


def generate(root=ROOT):
    actives, passive_rows = mapping()
    sql = render(actives, passive_rows)
    path = root / 'data/sql/db-characters/updates' / MIGRATION
    write_migration(root, path, sql)
    print(f'Skill-id migration: {len(actives)} skill/rune pairs and {len(passive_rows)} '
          f'passives mapped, for review before apply.')
    return sql, actives, passive_rows


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()

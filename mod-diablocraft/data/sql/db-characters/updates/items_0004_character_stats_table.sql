-- dc_character_stats before items_0011 reads it. The updater applies these files in filename order, and
-- items_0011_clear_weapon_gem_flat sorts before stats_0001_character_stats, so on an empty characters database the
-- clear ran against a table that did not exist yet. This is stats_0001's CREATE, statement for statement; on a
-- database that already has the table it does nothing, and stats_0001 (also IF NOT EXISTS) does nothing after it.
-- stats_0002 still adds current_life on a fresh database.
CREATE TABLE IF NOT EXISTS `dc_character_stats` (
  `guid` BIGINT UNSIGNED NOT NULL,
  `level` TINYINT UNSIGNED NOT NULL,
  `max_life` INT UNSIGNED NOT NULL,
  `armor` DOUBLE NOT NULL,
  `sheet` LONGTEXT NOT NULL COMMENT 'Versioned numeric snapshot; all D3 stats and derived values',
  `contributions` LONGTEXT NOT NULL COMMENT 'Versioned source/stat/id/bucket/element contributions',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

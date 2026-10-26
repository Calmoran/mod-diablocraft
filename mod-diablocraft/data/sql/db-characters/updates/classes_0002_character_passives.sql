-- 04-classes §3 (K2). Four passive slots, unlocked at character level 10, 20,
-- 30 and 70; each passive also has its own unlock level in the CSV.
CREATE TABLE IF NOT EXISTS `dc_character_passives` (
  `guid` BIGINT UNSIGNED NOT NULL,
  `slot` TINYINT UNSIGNED NOT NULL COMMENT '0-3, gated at level 10/20/30/70',
  `passive` VARCHAR(64) NOT NULL COMMENT 'barbarian_passives.passive_name',
  PRIMARY KEY (`guid`, `slot`),
  UNIQUE KEY `uk_dc_passives_once` (`guid`, `passive`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 04-classes §3 (C4, K5, K6). Six active slots per character, each a skill plus
-- the rune chosen for it. Elective Mode is always on, so any skill may sit in
-- any slot; the once-per-bar rule is enforced by the unique key on (guid, skill).
CREATE TABLE IF NOT EXISTS `dc_character_skillbar` (
  `guid` BIGINT UNSIGNED NOT NULL,
  `slot` TINYINT UNSIGNED NOT NULL COMMENT '0-5, maps to action bar keys 1-6',
  `skill` VARCHAR(64) NOT NULL COMMENT 'barbarian_skills.skill_name',
  `rune` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'barbarian_runes.rune_name, empty for the base skill',
  PRIMARY KEY (`guid`, `slot`),
  UNIQUE KEY `uk_dc_skillbar_once` (`guid`, `skill`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

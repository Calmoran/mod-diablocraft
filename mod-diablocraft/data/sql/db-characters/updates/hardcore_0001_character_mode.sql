-- 11-hardcore section 2. One row per character, written once when the player
-- answers the first-login prompt (H4) and never changed after: the mode is
-- permanent. `dead` is the H1 lock; a dead hardcore character keeps its gear and
-- its paragon allocation and is only ever deleted by its owner.
CREATE TABLE IF NOT EXISTS `dc_character_mode` (
  `guid` INT UNSIGNED NOT NULL,
  `mode` ENUM('normal','hardcore') NOT NULL,
  `dead` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `died_at` TIMESTAMP NULL DEFAULT NULL,
  `killed_by` VARCHAR(100) NOT NULL DEFAULT '' COMMENT 'What killed it, plus the rift and tier it died in',
  `chosen_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`guid`),
  KEY `idx_dc_character_mode_dead` (`mode`, `dead`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11-hardcore section 4 (H2). Cosmetic unlocks are the one thing shared across
-- both modes, so this table deliberately has no mode column. Stub: 05-items §7
-- owns what a cosmetic_id means and nothing grants rows yet.
CREATE TABLE IF NOT EXISTS `dc_account_cosmetics` (
  `account_id` INT UNSIGNED NOT NULL,
  `cosmetic_id` VARCHAR(64) NOT NULL COMMENT '05-items §7 cosmetic; sources are a later doc',
  `unlocked_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`account_id`, `cosmetic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration (no generator owns these tables, the 2026-09-16
-- rule). The Bounty Board moved off the web into the game
-- (diablocraft-bounty-ingame, docs/contracts/bounty-board-messages.md, the designer
-- 2026-10-04): staff post bounties from Discord, players claim one, and a
-- submission is reviewed Yes/No by staff. The bot (diablocraft-bounty-bot-staff)
-- reads and writes dc_bounty and dc_bounty_submission with its own MySQL user and
-- never touches dc_bounty_claim: on a No verdict it sets dc_bounty.status='open'
-- and the server clears the stale claim row.
CREATE TABLE IF NOT EXISTS `dc_bounty` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'The board tag: B-<id>',
  `title` VARCHAR(128) NOT NULL,
  `description` VARCHAR(2048) NOT NULL DEFAULT '',
  `class` VARCHAR(32) NOT NULL DEFAULT 'Any' COMMENT 'dc_class_map.wow_class, or Any for every class',
  `category` VARCHAR(32) NOT NULL COMMENT 'One GitHub area label: core, skill, ui, enemy-ai, loot, rift, crafting, client-patch, data',
  `urgent` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Staff-set; sorts first, draws a red outline',
  `status` ENUM('open','claimed','review','done') NOT NULL DEFAULT 'open' COMMENT 'done is a Yes verdict and never shows on the board',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'New tag while younger than 24 hours',
  PRIMARY KEY (`id`),
  KEY `idx_dc_bounty_status_urgent_created` (`status`, `urgent`, `created_at`) COMMENT 'The board query and the release tick'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `dc_bounty_claim` (
  `bounty_id` BIGINT UNSIGNED NOT NULL COMMENT 'One claim per bounty',
  `account` INT UNSIGNED NOT NULL COMMENT 'One claim per account (the brief): the UNIQUE key decides a race',
  `guid` INT UNSIGNED NOT NULL COMMENT 'The character that claimed',
  `name` VARCHAR(64) NOT NULL DEFAULT '',
  `claimed_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`bounty_id`),
  UNIQUE KEY `uk_dc_bounty_claim_account` (`account`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `dc_bounty_submission` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `bounty_id` BIGINT UNSIGNED NOT NULL,
  `account` INT UNSIGNED NOT NULL,
  `guid` INT UNSIGNED NOT NULL,
  `name` VARCHAR(64) NOT NULL DEFAULT '',
  `result` ENUM('passed','problems') NOT NULL COMMENT 'The only two answers the window offers',
  `body` VARCHAR(2048) NOT NULL DEFAULT '' COMMENT 'What was tested and what happened; trimmed, at most 2000 characters',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `verdict` ENUM('yes','no') NULL DEFAULT NULL COMMENT 'The bot writes it; NULL until staff answer',
  `reviewed_at` TIMESTAMP NULL DEFAULT NULL,
  `issue_number` INT UNSIGNED NULL DEFAULT NULL COMMENT 'GitHub issue the Yes filed, written once',
  PRIMARY KEY (`id`),
  KEY `idx_dc_bounty_submission_pending` (`verdict`, `created_at`) COMMENT 'The bot reads verdict IS NULL, oldest first',
  KEY `idx_dc_bounty_submission_bounty` (`bounty_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

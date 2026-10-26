-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration (no generator owns this table, the 2026-09-16
-- rule). One row per in-game /bug report the AIO handler accepted
-- (diablocraft-sn9c, docs/briefs/ingame-bug-report-brief.md). Everything but
-- `body` and `addon_version` is filled from the server's own state, never from
-- the client; the client sends only the text and its addon version.
--
-- The handler enforces the 5-per-account-per-rolling-hour limit with a COUNT on
-- this table, so the limit survives a server restart. The poster service
-- (launcher/server, lane-website) selects rows whose `issue_number` is NULL,
-- files one `player-report` GitHub issue each and writes the number back; it
-- only ever reads and UPDATEs `issue_number`.
CREATE TABLE IF NOT EXISTS `dc_bug_report` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account` INT UNSIGNED NOT NULL COMMENT 'player:GetAccountId()',
  `guid` INT UNSIGNED NOT NULL COMMENT 'player:GetGUIDLow()',
  `name` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Character name',
  `class` VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'dc_class_map.wow_class for the character class',
  `level` INT UNSIGNED NOT NULL DEFAULT 0,
  `paragon` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'dc_account_paragon.level for the account mode',
  `realm` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'realmlist.name for the server realm',
  `map_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `zone` VARCHAR(128) NOT NULL DEFAULT '',
  `subzone` VARCHAR(128) NOT NULL DEFAULT '',
  `pos_x` FLOAT NOT NULL DEFAULT 0,
  `pos_y` FLOAT NOT NULL DEFAULT 0,
  `pos_z` FLOAT NOT NULL DEFAULT 0,
  `difficulty` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'dc_character_tier.tier (Torment level)',
  `rift_id` BIGINT UNSIGNED NULL DEFAULT NULL COMMENT 'dc_rift.id while enrolled in a live run',
  `rift_level` INT UNSIGNED NULL DEFAULT NULL COMMENT 'dc_rift.tier of that run',
  `target_name` VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Current selection name, empty when none',
  `target_entry` INT UNSIGNED NOT NULL DEFAULT 0,
  `equipped` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Comma-separated equipped item entry ids, slot 0..18',
  `build` VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Deployed commit: the release MANIFEST cut: sha, else the VERSION identity (module/schema/client_patch)',
  `addon_version` VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Client-reported, untrusted',
  `body` VARCHAR(2048) NOT NULL COMMENT 'The report text, trimmed; at most 2000 characters',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `issue_number` INT UNSIGNED NULL DEFAULT NULL COMMENT 'GitHub issue number, set by the poster once filed',
  PRIMARY KEY (`id`),
  KEY `idx_dc_bug_report_account_time` (`account`, `created_at`) COMMENT 'The 5-per-hour rate limit count',
  KEY `idx_dc_bug_report_issue` (`issue_number`) COMMENT 'The poster picks up rows with a NULL issue number'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

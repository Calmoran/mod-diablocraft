-- 09-rifts section 6. One row per opened rift, alive until the leader closes it
-- or the instance resets. instance_id ties it to the WoW instance so a relog
-- rejoins the same rift rather than opening a second one.
CREATE TABLE IF NOT EXISTS `dc_rift` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `instance_id` INT UNSIGNED NOT NULL,
  `map_id` INT UNSIGNED NOT NULL,
  `dungeon_id` INT UNSIGNED NOT NULL COMMENT 'dc_rift_dungeon.dungeon_id',
  `leader_guid` BIGINT UNSIGNED NOT NULL,
  `tier` TINYINT UNSIGNED NOT NULL COMMENT 'Leader tier at open (03 D5); fixed for the run',
  `kills` INT UNSIGNED NOT NULL DEFAULT 0,
  `required` INT UNSIGNED NOT NULL,
  `state` ENUM('open','guardian','complete','closed') NOT NULL DEFAULT 'open',
  `opened_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dc_rift_instance` (`instance_id`),
  KEY `idx_dc_rift_leader` (`leader_guid`, `state`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

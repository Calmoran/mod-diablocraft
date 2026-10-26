-- 06-loot §3. One-time per-character flags; the first user is the act-boss
-- first-kill guaranteed legendary (L11), keyed as 'boss_first_kill:<entry>'.
CREATE TABLE IF NOT EXISTS `dc_character_flags` (
  `guid` BIGINT UNSIGNED NOT NULL,
  `flag` VARCHAR(64) NOT NULL,
  `value` BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (`guid`, `flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

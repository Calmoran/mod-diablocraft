-- 03-difficulty section 5 elite look. One row per promoted champion or rare
-- pack, written by src/rifts on promotion and removed when the pack dies or its
-- rift map is destroyed. It exists because the pack lives in C++ and the AIO
-- nameplate overlay (lua/aio/dc_elite.lua) is Lua: this table is the only thing
-- the Lua side is allowed to read about a promotion.
-- Runtime state, never a data source: the module clears it at startup.
-- `elite_rank` rather than `rank`, which is reserved in MySQL 8.
CREATE TABLE IF NOT EXISTS `dc_rift_elite` (
  `instance_id` INT UNSIGNED NOT NULL,
  `creature_guid` BIGINT UNSIGNED NOT NULL,
  `entry` INT UNSIGNED NOT NULL,
  `elite_rank` VARCHAR(16) NOT NULL,
  `name` VARCHAR(100) NOT NULL,
  `affixes` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`instance_id`, `creature_guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Apply to the CHARACTERS database.
--
-- Hand-written like items_0001 and items_0002: a schema migration no generator
-- owns, which the designer's 2026-09-16 rule allows under data/sql/*/updates. No data
-- row is hand-written here.
--
-- decisions.md 2026-09-17 "Unidentified items are ROLLED AT IDENTIFY": a
-- legendary or set drop is delivered as an UNROLLED SHELL. The roll has not
-- happened yet, so the item deliberately has NO dc_item_instance row and NO
-- dc_item_affix rows - that absence is what already makes Items::Get return
-- nullopt and the Mystic and Jeweler refuse it, with no new code path in
-- crafting. This table holds everything the roller will need when the player
-- finally identifies it.
--
-- Lifecycle: one row per undelivered roll, keyed by the shell's item guid.
-- Deleted when the shell is identified (the roll happens then), salvaged, or
-- destroyed. A shell with no row, or a row with no item, is a repair case for
-- the login sweep and is never silently rolled.
CREATE TABLE IF NOT EXISTS `dc_item_unidentified` (
  `item_guid` BIGINT UNSIGNED NOT NULL COMMENT 'The shell item in the bag; not a dc_item_instance guid, that row does not exist yet',
  `base_item` BIGINT UNSIGNED NOT NULL COMMENT 'item_template.entry of the REAL item, hidden from the client until identify',
  `item_level` INT UNSIGNED NOT NULL COMMENT '06-loot L8: item level = monster level at the drop',
  `rarity` VARCHAR(16) NOT NULL COMMENT 'legendary | set. Rares and below are never shells',
  `drop_source` VARCHAR(32) NOT NULL COMMENT 'dc_loot_tuning.source the drop came from: normal | elite | boss | rift_guardian | chest',
  `tier` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'Difficulty tier at the drop; the roller takes it, not the tier at identify',
  `owner_guid` BIGINT UNSIGNED NOT NULL COMMENT 'Who it dropped for (06-loot L12 personal loot). The IDENTIFYING player decides smart loot, which may differ after a trade',
  `dropped_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`item_guid`),
  KEY `idx_dc_item_unidentified_owner` (`owner_guid`) COMMENT 'The login sweep and the tome both read every shell a character holds'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

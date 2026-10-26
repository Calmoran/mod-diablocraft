-- 05-items §3. One row per rolled affix on an item instance, in display order.
-- range_min/range_max are the bracket the value was rolled in and are what the
-- tooltip shows after the value (05 §6). A socket row carries no value; a gem
-- row is a child of the socket row that precedes it (05 §5).
CREATE TABLE IF NOT EXISTS `dc_item_affix` (
  `item_guid` BIGINT UNSIGNED NOT NULL,
  `seq` SMALLINT UNSIGNED NOT NULL COMMENT 'Display order; also the parent seq a gem row hangs from',
  `affix_id` VARCHAR(64) NOT NULL COMMENT 'dc_affix_pool.affix_id, or dc_gem.gem_id on a gem row',
  `value` DOUBLE NOT NULL DEFAULT 0,
  `range_min` DOUBLE NOT NULL DEFAULT 0,
  `range_max` DOUBLE NOT NULL DEFAULT 0,
  `kind` ENUM('primary','secondary','socket','gem','preset') NOT NULL,
  `rerolled` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '07-crafting: only one affix per item may ever be rerolled',
  PRIMARY KEY (`item_guid`, `seq`),
  KEY `idx_dc_item_affix_guid` (`item_guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

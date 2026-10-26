-- 06-loot §3 (L5). A drop that could not fit in the bag waits here for 60 s and
-- is delivered as soon as a slot frees; after that it is lost. The payload is
-- the base item to hand to the 05-items roller, not a rolled item: nothing is
-- rolled until it can actually be delivered, so a lost buffer entry leaves no
-- orphan dc_item_instance rows.
CREATE TABLE IF NOT EXISTS `dc_loot_buffer` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `guid` BIGINT UNSIGNED NOT NULL COMMENT 'Owning character guid',
  `base_item` BIGINT UNSIGNED NOT NULL COMMENT 'item_template.entry to roll on delivery',
  `item_level` SMALLINT UNSIGNED NOT NULL,
  `expires_at` TIMESTAMP NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_dc_loot_buffer_guid` (`guid`, `expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

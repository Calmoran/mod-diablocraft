-- 05-items §3. One row per rolled item instance, keyed by the core's item guid.
-- Rows follow the guid through bags, bank, mail and trade; they are deleted when
-- the item is destroyed.
CREATE TABLE IF NOT EXISTS `dc_item_instance` (
  `item_guid` BIGINT UNSIGNED NOT NULL,
  `base_item` BIGINT UNSIGNED NOT NULL COMMENT 'item_template.entry, our 100000+ range',
  `quality_tier` ENUM('normal','ancient','primal') NOT NULL DEFAULT 'normal' COMMENT 'I9: always normal at launch',
  `rolled_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `enchant_locked` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '07-crafting: set once the Mystic has bound a reroll to one affix',
  `enchant_attempts` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '07-crafting: Mystic reroll count, drives the cost curve',
  PRIMARY KEY (`item_guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

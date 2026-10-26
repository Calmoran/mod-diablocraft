-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration (no generator owns the table). No data: the module writes a row when it delivers a cache.
--
-- Bounties W4 (diablocraft-dm9vg.4; docs/research/bounties.md 5.5, PM answers on the bead 2026-10-12 point 2). One row a
-- Horadric Cache item: the column it was earned on and the member's tier when that column completed, which is what the
-- cache pays at when it is opened (D3's cache keeps the difficulty it was earned at). Keyed by the item's guid, which a
-- move into or out of the account stash keeps (dc_stash.cpp Park). The row is written in the same transaction that
-- stores the item, and deleted in the same transaction that opens it.
--   item_guid  item_instance.guid of the cache
--   col        1 to 5, dc_bounties_cache.col (world)
--   tier       1 to 20, the member's difficulty tier at the column's completion (dc_difficulty_tiers order)
CREATE TABLE IF NOT EXISTS `dc_bounties_cache_item` (
  `item_guid` INT UNSIGNED NOT NULL,
  `col` TINYINT UNSIGNED NOT NULL,
  `tier` TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (`item_guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

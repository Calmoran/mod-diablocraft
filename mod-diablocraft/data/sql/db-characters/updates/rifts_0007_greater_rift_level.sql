-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration, like rifts_0001-0006 (the 2026-09-16 rule allows it where
-- no generator owns the table). No data: the start level and the cap are tunables
-- (rifts/greater_rift_start_level, rifts/greater_rift_max_level); a character with no row
-- is at the start level with nothing beaten.
--
-- Greater Rifts part 1 (docs/briefs/greater-rifts-brief.md, docs/proposals/greater-rifts.md
-- ruling 1). One row per character per realm mode (the character's dc_character_mode, the
-- realm's setting while it has none). `unlocked` is the highest level the character may open;
-- `beaten` is the highest it has beaten in time, 0 for none. The Greater Rift level of one
-- run is dc_rift.gr_rank (rifts_0005), which already exists.
CREATE TABLE IF NOT EXISTS `dc_character_gr` (
  `guid` BIGINT UNSIGNED NOT NULL,
  `mode` ENUM('normal','hardcore') NOT NULL,
  `unlocked` SMALLINT UNSIGNED NOT NULL,
  `beaten` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`guid`, `mode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

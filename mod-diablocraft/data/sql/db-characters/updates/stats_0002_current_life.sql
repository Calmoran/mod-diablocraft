-- 01 section 3 makes max Life ours, so current Life has to be ours too: the core
-- restores its own saved health inside Player::LoadFromDB against whatever max is
-- in place at that moment, which is not the D3 max. current_life over max_life in
-- the same row is the share restored at login. 0 means no saved D3 Life yet, and
-- every row that predates this column starts full.
ALTER TABLE `dc_character_stats`
  ADD COLUMN `current_life` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `max_life`;

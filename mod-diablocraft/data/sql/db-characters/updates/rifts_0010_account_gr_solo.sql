-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration, like rifts_0007 and rifts_0009 (no generator owns the table). No data.
--
-- Kadala part 1 (diablocraft-gw9h; docs/proposals/kadala.md 4.2, ruling q-1007-08). The Blood Shard cap
-- is 500 plus 10 for each Greater Rift level the ACCOUNT has beaten alone in time, its best in that
-- mode, and the raise is permanent: it stays when the character that earned it is deleted
-- (dc_character_gr goes with its character). One row per account per realm mode, raised with
-- GREATEST whenever a character's beaten_solo is written; nothing lowers it.
CREATE TABLE IF NOT EXISTS `dc_account_gr_solo` (
  `account_id` INT UNSIGNED NOT NULL,
  `mode` ENUM('normal','hardcore') NOT NULL,
  `beaten_solo` SMALLINT UNSIGNED NOT NULL DEFAULT 0
    COMMENT 'Best Greater Rift level any character of the account beat alone in time in this mode; 0 none',
  PRIMARY KEY (`account_id`, `mode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

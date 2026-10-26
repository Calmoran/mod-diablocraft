-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration (no generator owns the table). No data: the module draws a board the first time a
-- player or a party needs one.
--
-- Bounties, first set W1 (diablocraft-dm9vg.1; docs/research/bounties.md 5.1 and 5.4, brief
-- bounties-first-set-2026-10-11). One row a live cell of a board. A party plays its leader's board, copied when the
-- party forms and kept by the party through joins, leaves and leader changes; a solo player has their own, kept as it
-- was while they are in a party. A new table: the retired dc_bounty* tables (bounties_0004) are never reused.
--   owner_kind   0 a player (owner_id their low guid), 1 a party (owner_id groups.guid)
--   col, cell    the column (1 to 5, an act, dc_bounties.col) and its cell (1 to 5)
--   objectives   a Click bounty's drawn spots, bit n-1 for dc_bounties_spot.spot n; 0 for Kill
--   need         what the bounty asks for besides its end: a Kill's monsters (rifts tunable bounty_kill_monster_count at the
--                draw), a Click's objective count
--   progress     how many of `need` are done
--   done         the bounty is complete
CREATE TABLE IF NOT EXISTS `dc_bounties_board` (
  `owner_kind` TINYINT UNSIGNED NOT NULL COMMENT '0 player, 1 party',
  `owner_id` INT UNSIGNED NOT NULL,
  `col` TINYINT UNSIGNED NOT NULL,
  `cell` TINYINT UNSIGNED NOT NULL,
  `bounty_id` INT UNSIGNED NOT NULL COMMENT 'dc_bounties.bounty_id (world)',
  `objectives` INT UNSIGNED NOT NULL DEFAULT 0,
  `need` INT UNSIGNED NOT NULL DEFAULT 0,
  `progress` INT UNSIGNED NOT NULL DEFAULT 0,
  `done` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`owner_kind`, `owner_id`, `col`, `cell`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

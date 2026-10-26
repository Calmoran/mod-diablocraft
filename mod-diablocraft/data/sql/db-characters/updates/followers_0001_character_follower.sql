-- Followers: which follower a character has hired. One row per character with a follower hired; no row means none.
-- Written by the hub gossip (hire, dismiss) and read at login; the follower is out beside the character whenever the
-- character is alone (contract docs/contracts/followers.md).
CREATE TABLE IF NOT EXISTS `dc_character_follower` (
  `guid` INT UNSIGNED NOT NULL,
  `follower` TINYINT UNSIGNED NOT NULL COMMENT '1 Templar, 2 Scoundrel, 3 Enchantress',
  PRIMARY KEY (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

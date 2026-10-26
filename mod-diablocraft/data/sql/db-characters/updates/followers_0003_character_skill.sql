-- Followers: the skill a character has picked in each tier for each follower (contract docs/contracts/followers.md). One row per
-- (character, follower, tier); the Templar, the Scoundrel and the Enchantress keep their own picks, and switching the hired follower
-- touches none of them. skill_id is the id in the world table dc_follower_skill; a tier with no row has no pick.
CREATE TABLE IF NOT EXISTS `dc_character_follower_skill` (
  `guid` INT UNSIGNED NOT NULL,
  `follower` TINYINT UNSIGNED NOT NULL COMMENT '1 Templar, 2 Scoundrel, 3 Enchantress',
  `tier` TINYINT UNSIGNED NOT NULL COMMENT '1 to 4',
  `skill_id` VARCHAR(32) NOT NULL,
  PRIMARY KEY (`guid`, `follower`, `tier`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

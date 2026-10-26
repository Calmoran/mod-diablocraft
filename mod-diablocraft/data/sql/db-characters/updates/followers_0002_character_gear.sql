-- Followers: what each follower of a character wears. One row per (character, follower, slot): the Templar, the Scoundrel and
-- the Enchantress each keep their own set, and switching the hired follower touches none of them (contract
-- docs/contracts/followers.md). The worn item is parked, not in a bag: its item_instance row keeps the character as owner and no
-- character_inventory row, so it is on no bag screen and in no other follower's slot, and its dc_item_instance / dc_item_affix
-- rows stay as they were.
CREATE TABLE IF NOT EXISTS `dc_character_follower_gear` (
  `guid` INT UNSIGNED NOT NULL,
  `follower` TINYINT UNSIGNED NOT NULL COMMENT '1 Templar, 2 Scoundrel, 3 Enchantress',
  `slot` VARCHAR(12) NOT NULL COMMENT 'relic head shoulders chest gloves bracers belt pants boots ring1 ring2 neck mainhand offhand',
  `item_guid` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`guid`, `follower`, `slot`),
  UNIQUE KEY `dc_character_follower_gear_item` (`item_guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

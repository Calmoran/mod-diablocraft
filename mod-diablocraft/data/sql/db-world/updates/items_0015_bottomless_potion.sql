-- diablocraft-potion-regeneration: the first legendary potion, Bottomless
-- Potion of Regeneration (data/d3/legendary_potions.csv row
-- HealthPotionLegendary_03). Hand-written: no generator builds potion rows,
-- and the sheet at data/d3/base_item_ids.csv owns 100000-101113 only.
--
-- The item is the thing the character sheet's potion slot takes. It has NO
-- on-use spell (spellid_1 stays 0), so nothing can drink it from the bags; it
-- is for the slot, which swaps bar slot 7 to its own shell, 81205 (spell_dbc,
-- combat_0043; Potion::SpellFor maps this entry to it). Its legendary power
-- is not built: the tooltip shows the power line and says it is inactive.
--
-- GM-only: pool_version 'no' keeps it out of every affix and loot pool, and no
-- loot, vendor or kit row names it. Display 24152 is the stock INV_Potion_54,
-- the same icon the shell carries.
SET NAMES utf8mb4;
DELETE FROM `item_template` WHERE `entry` = 102200;
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `maxcount`, `stackable`, `Material`, `bonding`, `ItemLevel`, `RequiredLevel`, `description`)
VALUES
  (102200, 0, 1, 'Bottomless Potion of Regeneration', 24152, 5, 0, 1, 0, 0, 0, 0, 1, 3, 0, 61, 61,
   CONCAT('Restores an additional 75000–100000 Life over 5 seconds.', CHAR(10),
          '“Does Your Majesty know what would serve his armies better than mere healing? Healing combined with more healing!” -Royal Apothecary Jentulf, advising His Majesty in council.'));

DELETE FROM `dc_base_item` WHERE `entry` = 102200;
INSERT INTO `dc_base_item`
  (`entry`, `d3_id`, `d3_name`, `slot`, `type`, `rarity`, `usable_by`, `item_level`, `level_req`, `weapon_min`, `weapon_max`,
   `weapon_aps`, `preset_affixes`, `set_name`, `source_file`, `pool_version`, `designated_class`, `craft_only`)
VALUES
  (102200, 'HealthPotionLegendary_03', 'Bottomless Potion of Regeneration', 'potion', 'Potion', 'legendary', '', 61, 61,
   NULL, NULL, NULL, '', '', 'legendary_potions.csv', 'no', '', 'no');

-- The tooltip's power and flavour (dc_tooltip.lua joins dc_base_item to this
-- on d3_id). The roll range is written out: nothing rolls it yet.
DELETE FROM `dc_item_tooltip` WHERE `d3_id` = 'HealthPotionLegendary_03';
INSERT INTO `dc_item_tooltip` (`d3_id`, `set_id`, `power_text`, `flavour`) VALUES
  ('HealthPotionLegendary_03', '', 'Restores an additional 75000–100000 Life over 5 seconds.',
   '“Does Your Majesty know what would serve his armies better than mere healing? Healing combined with more healing!” -Royal Apothecary Jentulf, advising His Majesty in council.');

-- 09-rifts F7. The Greater Rift Keystone as a currency item, same shape as the
-- five crafting materials in loot_0003_currency_items.sql. Its CurrencyTypes.dbc
-- row (id 1005, BitIndex 35) is built by client-patch/dbc/build_currencytypes.py;
-- without it the core strips the currency bag-family bit at load.
--
-- Unused until Greater Rifts arrive (F6); it only accumulates for now.
SET NAMES utf8mb4;
DELETE FROM `item_template` WHERE `entry` = 102005;
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `maxcount`, `stackable`, `BagFamily`, `Material`, `bonding`, `ItemLevel`, `description`)
VALUES
  (102005, 10, 0, 'Greater Rift Keystone', 41435, 4, 2048, 1, 0, 0, 0, 0, 2147483647, 8192, 4, 1, 70,
   'Opens a Greater Rift at the obelisk.');

-- 06-loot L10. The five crafting materials as WoW currency items.
--
-- A currency in 3.3.5a is an ordinary item whose entry appears in
-- CurrencyTypes.dbc; the client then lists it in the Currency tab of the
-- character window instead of the bags. The matching DBC rows are built by
-- client-patch/dbc/build_currencytypes.py (ids 1000-1004, BitIndex 30-34).
-- Without those rows the core strips BagFamily's currency bit at load and the
-- items fall back to being ordinary bag items.
--
-- Entries 102000-102004 sit in the 100000-199999 range 05-items §10 reserves
-- for us; 100000-101113 is base_items, so the currencies start at 102000.
--
-- Column values mirror the stock currency tokens (Emblem of Heroism 40752,
-- Stone Keeper's Shard 43228): class 10 Money, no inventory slot, bind on
-- pickup, unlimited stack, BagFamily 8192. displayid reuses stock icons so no
-- ItemDisplayInfo.dbc patch is needed.
SET NAMES utf8mb4;
DELETE FROM `item_template` WHERE `entry` BETWEEN 102000 AND 102004;
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `maxcount`, `stackable`, `BagFamily`, `Material`, `bonding`, `ItemLevel`, `description`)
VALUES
  (102000, 10, 0, "Death's Breath", 51567, 1, 2048, 1, 0, 0, 0, 0, 2147483647, 8192, 4, 1, 70,
   'The last exhalation of a slain elite.'),
  (102001, 10, 0, 'Reusable Parts',  32278, 1, 2048, 1, 0, 0, 0, 0, 2147483647, 8192, 4, 1, 70,
   'Salvaged from common equipment.'),
  (102002, 10, 0, 'Arcane Dust',     32276, 1, 2048, 1, 0, 0, 0, 0, 2147483647, 8192, 4, 1, 70,
   'Salvaged from magic equipment.'),
  (102003, 10, 0, 'Veiled Crystal',  54441, 1, 2048, 1, 0, 0, 0, 0, 2147483647, 8192, 4, 1, 70,
   'Salvaged from rare equipment.'),
  (102004, 10, 0, 'Forgotten Soul',  58368, 1, 2048, 1, 0, 0, 0, 0, 2147483647, 8192, 4, 1, 70,
   'Salvaged from legendary and set equipment.');

-- Every race can create a Barbarian (Warrior) and a Wizard (Mage) (diablocraft-race-class-unlock).
-- Stock has no Mage for Orc (2), Dwarf (3), Night Elf (4) or Tauren (6): the core refuses a pair
-- with no playercreateinfo row. Each new row is placed at the hub, like the Barbarian rows; the
-- class start (dc_class_start*, class-keyed) gives the kit, skills and spells to every race alike.
-- Racial stats are per race in the pinned core, so no stats rows are needed.
INSERT INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT r.`race`, 8, h.`map_id`, h.`area_id`, h.`x`, h.`y`, h.`z`, h.`o`
FROM (SELECT 2 AS `race` UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 6) r
JOIN `dc_world_hub` h ON h.`id` = 1
ON DUPLICATE KEY UPDATE `map`=VALUES(`map`), `zone`=VALUES(`zone`), `position_x`=VALUES(`position_x`),
  `position_y`=VALUES(`position_y`), `position_z`=VALUES(`position_z`), `orientation`=VALUES(`orientation`);

-- No action rows for the four new Wizards: the class start rewrites buttons 0-7 on every login
-- (dc_classes.cpp WriteActionBar: six skills, the potion, Town Portal), so a Fireball, Frost Armor or
-- racial row in slots 0-2 would be removed at once. Existing Wizards' rows are dead the same way.

-- The Blood Elf Barbarian had no action rows (world_0003 added the row only). Buttons 72, 73, 84 and 96
-- lie outside the 0-7 the login rewrites, so they are what the core hands out at creation and they
-- persist, as for the other Barbarians: Attack (6603) on three buttons and Heroic Strike (78). A Blood Elf Warrior has no
-- racial button: Arcane Torrent is not taught to the Warrior class.
DELETE FROM `playercreateinfo_action` WHERE `class`=1 AND `race`=10;
INSERT INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) VALUES
(10,1,72,6603,0),(10,1,73,78,0),(10,1,84,6603,0),(10,1,96,6603,0);

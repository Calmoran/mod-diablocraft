-- Generated from data/d3/rift_dungeons.csv by generate_rifts.py; edit the
-- CSV and rerun. Apply to the world database.
-- 09-rifts F1: the stage 1 rift pool, recommended rows only.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_rift_dungeon`;
CREATE TABLE `dc_rift_dungeon` (
  `dungeon_id` INT NOT NULL,
  `map_id` INT NOT NULL,
  `name` LONGTEXT NOT NULL,
  `entry_x` DOUBLE NOT NULL,
  `entry_y` DOUBLE NOT NULL,
  `entry_z` DOUBLE NOT NULL,
  `entry_o` DOUBLE NOT NULL,
  `kills_required` INT NOT NULL COMMENT 'Tunable; derived from approximate_length',
  `approximate_length` LONGTEXT NOT NULL,
  PRIMARY KEY (`dungeon_id`),
  KEY `idx_dc_rift_dungeon_map` (`map_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_rift_dungeon` (`dungeon_id`, `map_id`, `name`, `entry_x`, `entry_y`, `entry_z`, `entry_o`, `kills_required`, `approximate_length`) VALUES
(1, 389, 'Ragefire Chasm', 3.81, -14.82, -17.84, 4.39, 60, 'short'),
(2, 34, 'The Stockade', 54.23, 0.28, -18.34, 6.26, 60, 'short'),
(3, 47, 'Razorfen Kraul', 1943.0, 1544.63, 82.0, 1.38, 90, 'medium'),
(4, 189, 'Scarlet Monastery - Graveyard', 1688.99, 1053.48, 18.68, 0.0012, 60, 'short'),
(5, 189, 'Scarlet Monastery - Library', 255.35, -209.09, 18.68, 6.2666, 90, 'medium'),
(6, 129, 'Razorfen Downs', 2592.55, 1107.5, 51.29, 4.74, 90, 'medium'),
(7, 429, 'Dire Maul - East', 44.45, -154.82, -2.71, 0.0, 90, 'medium'),
(8, 543, 'Hellfire Ramparts', -1355.24, 1641.12, 68.25, 0.6687, 60, 'short'),
(9, 542, 'The Blood Furnace', -4.0, 14.64, -44.8, 4.8875, 60, 'short'),
(10, 540, 'The Shattered Halls', -40.87, -19.75, -13.81, 1.1113, 90, 'medium'),
(11, 547, 'The Slave Pens', 120.1, -131.96, -0.8, 1.4757, 90, 'medium'),
(12, 546, 'The Underbog', 9.71, -16.2, -2.75, 5.5708, 90, 'medium'),
(13, 545, 'The Steamvault', -13.84, 6.75, -4.26, 0.0, 90, 'medium'),
(14, 557, 'Mana-Tombs', 0.02, 0.95, -0.95, 3.0316, 60, 'short'),
(15, 558, 'Auchenai Crypts', -21.9, 0.16, -0.12, 0.0353, 60, 'short'),
(16, 556, 'Sethekk Halls', -4.68, -0.09, 0.01, 0.0353, 60, 'short'),
(17, 555, 'Shadow Labyrinth', 0.49, -0.22, -1.13, 3.1589, 130, 'long'),
(18, 554, 'The Mechanar', -28.91, 0.68, -1.81, 0.0346, 60, 'short'),
(19, 553, 'The Botanica', 40.04, -28.61, -1.12, 2.3586, 90, 'medium'),
(20, 585, 'Magisters'' Terrace', 7.09, -0.45, -2.8, 0.05, 90, 'medium'),
(21, 574, 'Utgarde Keep', 153.79, -86.55, 12.55, 0.304, 60, 'short'),
(22, 575, 'Utgarde Pinnacle', 584.12, -327.97, 110.14, 3.122, 90, 'medium'),
(23, 576, 'The Nexus', 145.87, -10.55, -16.64, 1.528, 90, 'medium'),
(24, 601, 'Azjol-Nerub', 413.31, 795.97, 831.35, 5.5, 60, 'short'),
(25, 619, 'Ahn''kahet: The Old Kingdom', 333.35, -1109.94, 69.77, 0.553, 90, 'medium'),
(26, 600, 'Drak''Tharon Keep', -517.34, -487.98, 11.01, 4.831, 90, 'medium'),
(27, 602, 'Halls of Lightning', 1331.47, 259.62, 53.4, 4.772, 90, 'medium'),
(28, 604, 'Gundrak', 1891.84, 832.17, 176.67, 2.109, 90, 'medium'),
(29, 632, 'The Forge of Souls', 4922.86, 2175.63, 638.73, 2.0036, 60, 'short'),
(30, 658, 'Pit of Saron', 435.74, 212.41, 528.71, 6.2565, 90, 'medium');

-- Generated from data/d3/starter_kit.csv; edit the CSV and rerun generate_sql.py.
-- Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_starter_kit`;
CREATE TABLE `dc_starter_kit` (
  `slot` LONGTEXT NOT NULL,
  `rarity` LONGTEXT NOT NULL,
  `count` BIGINT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_starter_kit` (`slot`, `rarity`, `count`) VALUES
('mainhand', 'legendary', 1),
('head', 'rare', 1),
('neck', 'rare', 1),
('shoulders', 'rare', 1),
('torso', 'rare', 1),
('waist', 'rare', 1),
('legs', 'rare', 1),
('feet', 'rare', 1),
('wrists', 'rare', 1),
('hands', 'rare', 1),
('finger', 'rare', 2),
('offhand', 'rare', 1);

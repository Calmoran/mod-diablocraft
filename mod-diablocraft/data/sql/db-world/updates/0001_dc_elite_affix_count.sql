-- Generated from data/d3/elite_affix_count.csv; edit the CSV and rerun generate_sql.py.
-- Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_elite_affix_count`;
CREATE TABLE `dc_elite_affix_count` (
  `hero_level_min` BIGINT NULL,
  `hero_level_max` BIGINT NULL,
  `affixes_per_pack` BIGINT NULL,
  `applies_to` LONGTEXT NOT NULL,
  `source_url` LONGTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_elite_affix_count` (`hero_level_min`, `hero_level_max`, `affixes_per_pack`, `applies_to`, `source_url`) VALUES
(1, 29, 1, 'champion and rare', 'https://maxroll.gg/d3/resources/elite-affixes'),
(30, 49, 2, 'champion and rare', 'https://maxroll.gg/d3/resources/elite-affixes'),
(50, 59, 3, 'champion and rare', 'https://maxroll.gg/d3/resources/elite-affixes'),
(60, 70, 4, 'champion and rare', 'https://maxroll.gg/d3/resources/elite-affixes');

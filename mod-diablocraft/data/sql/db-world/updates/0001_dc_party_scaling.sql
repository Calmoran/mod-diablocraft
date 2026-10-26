-- Generated from data/d3/party_scaling.csv; edit the CSV and rerun generate_sql.py.
-- Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_party_scaling`;
CREATE TABLE `dc_party_scaling` (
  `context` LONGTEXT NOT NULL,
  `players` BIGINT NULL,
  `monster_life_multiplier_pct` DECIMAL(4,1) NULL,
  `monster_damage_multiplier_pct` BIGINT NULL,
  `source_url` LONGTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_party_scaling` (`context`, `players`, `monster_life_multiplier_pct`, `monster_damage_multiplier_pct`, `source_url`) VALUES
('open_world', 1, 100, 100, 'https://maxroll.gg/d3/resources/social'),
('open_world', 2, 150, 100, 'https://maxroll.gg/d3/resources/social'),
('open_world', 3, 200, 100, 'https://maxroll.gg/d3/resources/social'),
('open_world', 4, 250, 100, 'https://maxroll.gg/d3/resources/social'),
('greater_rift', 1, 62.5, 100, 'https://maxroll.gg/d3/resources/social'),
('greater_rift', 2, 125, 100, 'https://maxroll.gg/d3/resources/social'),
('greater_rift', 3, 187.5, 100, 'https://maxroll.gg/d3/resources/social'),
('greater_rift', 4, 250, 100, 'https://maxroll.gg/d3/resources/social');

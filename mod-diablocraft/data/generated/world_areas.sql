-- Generated from data/d3/world_areas.csv; edit the CSV and rerun generate_sql.py.
-- Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_world_areas`;
CREATE TABLE `dc_world_areas` (
  `map_id` BIGINT NULL,
  `area_id` BIGINT NULL,
  `phase_scope` LONGTEXT NOT NULL,
  `status` LONGTEXT NOT NULL,
  `note` LONGTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_world_areas` (`map_id`, `area_id`, `phase_scope`, `status`, `note`) VALUES
(1, 876, 'all', 'closed', 'Former GM Island hub'),
(530, 3703, 'all', 'closed', 'Former Shattrath hub at Scryer''s Tier; closed when the hub moved to the Sanctum of Torment (diablocraft-976b)'),
(530, 3898, 'all', 'closed', 'Former Scryer''s Tier hub subarea; closed with it (diablocraft-976b)'),
(750, 4273, 'all', 'open', 'The hub: the Sanctum of Torment, Yogg-Saron''s arena as map 750, a clone of map 603 (diablocraft-976b)');

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
(1, 876, 'all', 'open', 'GM Island temporary hub');

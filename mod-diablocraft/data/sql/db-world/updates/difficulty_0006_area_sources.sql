-- Area-resolved source snapshots and stable ownership for area-only copies.
CREATE TABLE IF NOT EXISTS dc_area_source (
 map_id INT UNSIGNED NOT NULL, area_id INT UNSIGNED NOT NULL, kind CHAR(1) NOT NULL,
 source_guid INT UNSIGNED NOT NULL, entry INT UNSIGNED NOT NULL, source_phase INT UNSIGNED NOT NULL,
 position_x FLOAT NOT NULL, position_y FLOAT NOT NULL, position_z FLOAT NOT NULL, orientation FLOAT NOT NULL,
 PRIMARY KEY(map_id,area_id,kind,source_guid)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS dc_area_spawn (
 map_id INT UNSIGNED NOT NULL, area_id INT UNSIGNED NOT NULL, kind CHAR(1) NOT NULL,
 source_guid INT UNSIGNED NOT NULL, tier TINYINT UNSIGNED NOT NULL, spawn_guid INT UNSIGNED NOT NULL,
 PRIMARY KEY(map_id,area_id,kind,source_guid,tier), UNIQUE KEY(kind,spawn_guid)
) ENGINE=InnoDB;

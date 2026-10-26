-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration, like rifts_0007, rifts_0009 and rifts_0010 (no generator owns the table). No data:
-- the module writes floor 1 of every new run when its instance is created.
--
-- Rift floors, Part F1 (diablocraft-p8m7; docs/proposals/rift-floors.md 4.2, the designer's rulings in docs/decisions.md
-- 2026-10-08, card q-1008-08). A run (dc_rift) holds one instance per floor. dc_rift keeps floor 1's instance, map
-- and dungeon, so old rows, the website's clear times and the logs read as before; this table is the run's floors,
-- floor 1 included. Runs from before it have no rows (alpha runs are disposable).
--   monster_set  the set the floor rolled (dc_monster_set.set_id, spawning plan S2); 0 until sets are rolled
--   closed_at    the floor's map was destroyed, or the worldserver started over it
CREATE TABLE IF NOT EXISTS `dc_rift_floor` (
  `run_id` BIGINT UNSIGNED NOT NULL COMMENT 'dc_rift.id',
  `floor` TINYINT UNSIGNED NOT NULL COMMENT '1 is where the run starts',
  `instance_id` INT UNSIGNED NOT NULL,
  `map_id` INT UNSIGNED NOT NULL,
  `dungeon_id` INT UNSIGNED NOT NULL COMMENT 'dc_rift_dungeon.dungeon_id',
  `monster_set` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'dc_monster_set.set_id; 0 none',
  `opened_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `closed_at` TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY (`run_id`, `floor`),
  KEY `idx_dc_rift_floor_instance` (`instance_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Generated from data/d3/rift_open_zones.csv and data/tunables/rifts.csv (open_rift_entry_*) by generate_rifts.py; edit the
-- sheets and rerun. Apply to the world database.
-- Rift floors Part F5 (docs/proposals/rift-floors.md 4.14): an open zone joins the rift pool as one more floor map. The name is the
-- zone's, as the spawner's and the exit spots' rows name it; the arrival point is the designer's entrance. Nothing reads kills_required.
SET NAMES utf8mb4;
DELETE FROM `dc_rift_dungeon` WHERE `dungeon_id` >= 1000;
INSERT INTO `dc_rift_dungeon` (`dungeon_id`, `map_id`, `name`, `entry_x`, `entry_y`, `entry_z`, `entry_o`, `kills_required`, `approximate_length`) VALUES
(1001, 751, 'Un''Goro Crater', -7900.5913, -2135.8982, -249.10184, 0.6463665, 0, 'open');

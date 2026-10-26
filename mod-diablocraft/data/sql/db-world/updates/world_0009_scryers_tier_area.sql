-- Generated from data/d3/world_areas.csv by generate_sql.py --world-areas.
-- Reloaded at worldserver startup; no C++ rebuild required.
SET NAMES utf8mb4;
START TRANSACTION;
DELETE FROM `dc_world_areas` WHERE `map_id`=1 AND `area_id`=876;
INSERT INTO `dc_world_areas` (`map_id`,`area_id`,`phase_scope`,`status`,`note`) VALUES (1,876,'all', 'closed', 'Former GM Island hub');
DELETE FROM `dc_world_areas` WHERE `map_id`=530 AND `area_id`=3703;
INSERT INTO `dc_world_areas` (`map_id`,`area_id`,`phase_scope`,`status`,`note`) VALUES (530,3703,'all', 'open', 'Shattrath hub at Scryer''s Tier; native area spawns removed by world_0005');
DELETE FROM `dc_world_areas` WHERE `map_id`=530 AND `area_id`=3898;
INSERT INTO `dc_world_areas` (`map_id`,`area_id`,`phase_scope`,`status`,`note`) VALUES (530,3898,'all', 'open', 'Scryer''s Tier hub subarea; map and area verified by the designer''s in-game .gps 2026-09-11');
COMMIT;

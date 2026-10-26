-- Generated from data/d3/rift_open_zones.csv by generate_rifts.py (diablocraft-hmnei); edit the sheet and rerun. Apply to the world
-- database. The open zones of the rift copy: the zone a copy is sealed to, the word `.dc openrift` takes, and the rifts.csv prefix of
-- the zone's entrance (<entry_tunable>_x/_y/_z/_o; blank: the zone is off), and its bounty act (the board's column, 1 to 5;
-- diablocraft-hyoic.1). Sheet order is the order the command lists them in. The table is the sheet's alone, so it is rebuilt whole.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_rift_open_zone`;
CREATE TABLE `dc_rift_open_zone` (`key` VARCHAR(32) NOT NULL, `name` VARCHAR(64) NOT NULL, `map_id` INT UNSIGNED NOT NULL, `zone_id` INT UNSIGNED NOT NULL, `entry_tunable` VARCHAR(64) NOT NULL, `act` TINYINT UNSIGNED NOT NULL, `seq` INT UNSIGNED NOT NULL, PRIMARY KEY (`key`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_rift_open_zone` (`key`, `name`, `map_id`, `zone_id`, `entry_tunable`, `act`, `seq`) VALUES
('ungoro', 'Un''Goro Crater', 751, 490, 'open_rift_entry', 2, 1),
('tanaris', 'Tanaris', 751, 440, 'open_rift_entry_tanaris', 2, 2),
('thousandneedles', 'Thousand Needles', 751, 400, 'open_rift_entry_thousandneedles', 2, 3),
('azshara', 'Azshara', 751, 16, 'open_rift_entry_azshara', 1, 4),
('moonglade', 'Moonglade', 751, 493, 'open_rift_entry_moonglade', 1, 5),
('darkshore', 'Darkshore', 751, 148, 'open_rift_entry_darkshore', 1, 6),
('winterspring', 'Winterspring', 751, 618, 'open_rift_entry_winterspring', 1, 7),
('felwood', 'Felwood', 751, 361, 'open_rift_entry_felwood', 1, 8),
('ashenvale', 'Ashenvale', 751, 331, 'open_rift_entry_ashenvale', 1, 9),
('durotar', 'Durotar', 751, 14, 'open_rift_entry_durotar', 1, 10),
('stonetalonmountains', 'Stonetalon Mountains', 751, 406, 'open_rift_entry_stonetalonmountains', 1, 11),
('silithus', 'Silithus', 751, 1377, 'open_rift_entry_silithus', 2, 12),
('feralas', 'Feralas', 751, 357, 'open_rift_entry_feralas', 2, 13),
('desolace', 'Desolace', 751, 405, 'open_rift_entry_desolace', 2, 14),
('dustwallowmarsh', 'Dustwallow Marsh', 751, 15, 'open_rift_entry_dustwallowmarsh', 2, 15),
('thebarrens', 'The Barrens', 751, 17, 'open_rift_entry_thebarrens', 2, 16),
('westernplaguelands', 'Western Plaguelands', 752, 28, 'open_rift_entry_westernplaguelands', 3, 17),
('easternplaguelands', 'Eastern Plaguelands', 752, 139, 'open_rift_entry_easternplaguelands', 3, 18),
('tirisfalglades', 'Tirisfal Glades', 752, 85, 'open_rift_entry_tirisfalglades', 3, 19),
('silverpineforest', 'Silverpine Forest', 752, 130, 'open_rift_entry_silverpineforest', 3, 20),
('alteracmountains', 'Alterac Mountains', 752, 36, 'open_rift_entry_alteracmountains', 3, 21),
('hillsbradfoothills', 'Hillsbrad Foothills', 752, 267, 'open_rift_entry_hillsbradfoothills', 3, 22),
('thehinterlands', 'The Hinterlands', 752, 47, 'open_rift_entry_thehinterlands', 3, 23),
('wetlands', 'Wetlands', 752, 11, 'open_rift_entry_wetlands', 4, 24),
('lochmodan', 'Loch Modan', 752, 38, 'open_rift_entry_lochmodan', 4, 25),
('dunmorogh', 'Dun Morogh', 752, 1, 'open_rift_entry_dunmorogh', 4, 26),
('badlands', 'Badlands', 752, 3, 'open_rift_entry_badlands', 4, 27),
('burningsteppes', 'Burning Steppes', 752, 46, 'open_rift_entry_burningsteppes', 4, 28),
('redridgemountains', 'Redridge Mountains', 752, 44, 'open_rift_entry_redridgemountains', 4, 29),
('elwynnforest', 'Elwynn Forest', 752, 12, 'open_rift_entry_elwynnforest', 4, 30),
('swampofsorrows', 'Swamp of Sorrows', 752, 8, 'open_rift_entry_swampofsorrows', 4, 31),
('westfall', 'Westfall', 752, 40, 'open_rift_entry_westfall', 4, 32),
('stranglethornvale', 'Stranglethorn Vale', 752, 33, 'open_rift_entry_stranglethornvale', 4, 33),
('hellfirepeninsula', 'Hellfire Peninsula', 753, 3483, 'open_rift_entry_hellfirepeninsula', 5, 34),
('zangarmarsh', 'Zangarmarsh', 753, 3521, 'open_rift_entry_zangarmarsh', 5, 35),
('nagrand', 'Nagrand', 753, 3518, 'open_rift_entry_nagrand', 5, 36),
('terokkarforest', 'Terokkar Forest', 753, 3519, 'open_rift_entry_terokkarforest', 5, 37),
('shadowmoonvalley', 'Shadowmoon Valley', 753, 3520, 'open_rift_entry_shadowmoonvalley', 5, 38),
('netherstorm', 'Netherstorm', 753, 3523, 'open_rift_entry_netherstorm', 5, 39),
('bladesedgemountains', 'Blade''s Edge Mountains', 753, 3522, 'open_rift_entry_bladesedgemountains', 5, 40);

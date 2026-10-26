-- Generated from mystic_rules.csv and mystic_cost_scalars.csv by generate_crafting.py --mystic-rules.
-- diablocraft-xw2m: the Mystic rebuilt the D3 way; the price is mystic_base_gold times the scalar for the roll.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_mystic_rule`;
CREATE TABLE `dc_mystic_rule` (rarity VARCHAR(20) NOT NULL,slot VARCHAR(20) NOT NULL,payment_kind VARCHAR(8) NOT NULL,material_1_entry INT UNSIGNED NOT NULL,material_2_entry INT UNSIGNED NOT NULL,material_count INT UNSIGNED NOT NULL,gem_tier VARCHAR(40) NOT NULL,gem_count_rule VARCHAR(80) NOT NULL,PRIMARY KEY(rarity,slot)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_mystic_rule` VALUES ('rare','*','gold',102002,102003,3,'','');
INSERT INTO `dc_mystic_rule` VALUES ('rare','neck','gold',102002,102003,2,'','');
INSERT INTO `dc_mystic_rule` VALUES ('rare','finger','gold',102002,102003,2,'','');
INSERT INTO `dc_mystic_rule` VALUES ('legendary','*','gold',102002,102003,3,'','');
INSERT INTO `dc_mystic_rule` VALUES ('legendary','neck','gem',0,0,0,'Imperial','mystic_jewelry_gem_count');
INSERT INTO `dc_mystic_rule` VALUES ('legendary','finger','gem',0,0,0,'Imperial','mystic_jewelry_gem_count');
INSERT INTO `dc_mystic_rule` VALUES ('set','*','gold',102002,102003,3,'','');
INSERT INTO `dc_mystic_rule` VALUES ('set','neck','gem',0,0,0,'Imperial','mystic_jewelry_gem_count');
INSERT INTO `dc_mystic_rule` VALUES ('set','finger','gem',0,0,0,'Imperial','mystic_jewelry_gem_count');
DROP TABLE IF EXISTS `dc_mystic_scalar`;
CREATE TABLE `dc_mystic_scalar` (use_count INT UNSIGNED NOT NULL,scalar_tenths INT UNSIGNED NOT NULL,PRIMARY KEY(use_count)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_mystic_scalar` VALUES (1,12);
INSERT INTO `dc_mystic_scalar` VALUES (2,14);
INSERT INTO `dc_mystic_scalar` VALUES (5,20);
INSERT INTO `dc_mystic_scalar` VALUES (10,60);
INSERT INTO `dc_mystic_scalar` VALUES (20,180);
INSERT INTO `dc_mystic_scalar` VALUES (40,540);
INSERT INTO `dc_mystic_scalar` VALUES (80,1620);
INSERT INTO `dc_mystic_scalar` VALUES (160,4860);
INSERT INTO `dc_mystic_scalar` VALUES (320,14580);
INSERT INTO `dc_mystic_scalar` VALUES (640,43740);

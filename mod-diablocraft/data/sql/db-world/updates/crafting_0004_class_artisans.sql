-- Generated from blacksmith_rules.csv and mystic_rules.csv by generate_crafting.py --artisan-rules.
-- No class eligibility gate: class is an input to the item roll only.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_blacksmith_rule`;
CREATE TABLE `dc_blacksmith_rule` (recipe_slot VARCHAR(20) NOT NULL,base_slot VARCHAR(20) NOT NULL,base_rarity VARCHAR(20) NOT NULL,output_rarity VARCHAR(20) NOT NULL,PRIMARY KEY(recipe_slot,base_slot)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_blacksmith_rule` VALUES ('head','head','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('shoulders','shoulders','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('torso','torso','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('waist','waist','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('hands','hands','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('wrists','wrists','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('legs','legs','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('feet','feet','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('mainhand','onehand','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('mainhand','twohand','','rare');
INSERT INTO `dc_blacksmith_rule` VALUES ('offhand','offhand','','rare');
DROP TABLE IF EXISTS `dc_mystic_rule`;
CREATE TABLE `dc_mystic_rule` (rarity VARCHAR(20) NOT NULL,slot VARCHAR(20) NOT NULL,payment_kind VARCHAR(8) NOT NULL,material_1_entry INT UNSIGNED NOT NULL,material_2_entry INT UNSIGNED NOT NULL,material_count_key VARCHAR(80) NOT NULL,gem_tier VARCHAR(40) NOT NULL,gem_count_rule VARCHAR(80) NOT NULL,PRIMARY KEY(rarity,slot)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_mystic_rule` VALUES ('rare','*','gold',102003,102000,'enchant_material_count','','');
INSERT INTO `dc_mystic_rule` VALUES ('rare','neck','gem',102003,102000,'enchant_material_count','Imperial','mystic_jewelry_gem_count');
INSERT INTO `dc_mystic_rule` VALUES ('rare','finger','gem',102003,102000,'enchant_material_count','Imperial','mystic_jewelry_gem_count');
INSERT INTO `dc_mystic_rule` VALUES ('legendary','*','gold',102004,102000,'enchant_material_count','','');
INSERT INTO `dc_mystic_rule` VALUES ('legendary','neck','gem',102004,102000,'enchant_material_count','Imperial','mystic_jewelry_gem_count');
INSERT INTO `dc_mystic_rule` VALUES ('legendary','finger','gem',102004,102000,'enchant_material_count','Imperial','mystic_jewelry_gem_count');
INSERT INTO `dc_mystic_rule` VALUES ('set','*','gold',102004,102000,'enchant_material_count','','');
INSERT INTO `dc_mystic_rule` VALUES ('set','neck','gem',102004,102000,'enchant_material_count','Imperial','mystic_jewelry_gem_count');
INSERT INTO `dc_mystic_rule` VALUES ('set','finger','gem',102004,102000,'enchant_material_count','Imperial','mystic_jewelry_gem_count');

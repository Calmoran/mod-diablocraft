-- Generated from data/d3/class_starts.csv by generate_sql.py --class-starts.
-- Class-keyed equivalents for rolled starter items and login proficiency repair.
-- Native learnSpell/LearnDefaultSkill and item roll/equip APIs remain authoritative.
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS dc_class_start (class_id TINYINT UNSIGNED PRIMARY KEY, class_key VARCHAR(40) NOT NULL UNIQUE, class_name VARCHAR(80) NOT NULL) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS dc_class_starter_kit (class_id TINYINT UNSIGNED NOT NULL, slot VARCHAR(20) NOT NULL, rarity VARCHAR(20) NOT NULL, count INT UNSIGNED NOT NULL, base_type VARCHAR(80) NOT NULL DEFAULT '', base_slot VARCHAR(20) NOT NULL DEFAULT '', designated_class VARCHAR(40) NOT NULL DEFAULT '', PRIMARY KEY(class_id,slot)) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS dc_class_start_skill (class_id TINYINT UNSIGNED NOT NULL, spell_id INT UNSIGNED NOT NULL, skill_id INT UNSIGNED NOT NULL, PRIMARY KEY(class_id,spell_id), UNIQUE KEY(class_id,skill_id)) ENGINE=InnoDB;
START TRANSACTION;
DELETE FROM dc_class_start_skill;
DELETE FROM dc_class_starter_kit;
DELETE FROM dc_class_start;
INSERT INTO dc_class_start VALUES (1,'barbarian','Barbarian');
INSERT INTO dc_class_starter_kit VALUES (1,'mainhand','legendary',1,'Mighty Weapon','onehand','barbarian');
INSERT INTO dc_class_starter_kit VALUES (1,'head','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'neck','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'shoulders','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'torso','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'waist','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'legs','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'feet','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'wrists','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'hands','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'finger','rare',2,'','','');
INSERT INTO dc_class_starter_kit VALUES (1,'offhand','rare',1,'Shield','offhand','');
INSERT INTO dc_class_start_skill VALUES (1,196,44);
INSERT INTO dc_class_start_skill VALUES (1,197,172);
INSERT INTO dc_class_start_skill VALUES (1,198,54);
INSERT INTO dc_class_start_skill VALUES (1,199,160);
INSERT INTO dc_class_start_skill VALUES (1,200,229);
INSERT INTO dc_class_start_skill VALUES (1,201,43);
INSERT INTO dc_class_start_skill VALUES (1,202,55);
INSERT INTO dc_class_start_skill VALUES (1,227,136);
INSERT INTO dc_class_start_skill VALUES (1,9116,433);
INSERT INTO dc_class_start_skill VALUES (1,15590,473);
INSERT INTO dc_class_start_skill VALUES (1,1180,173);
INSERT INTO dc_class_start_skill VALUES (1,750,293);
INSERT INTO dc_class_start_skill VALUES (1,674,118);
INSERT INTO dc_class_start VALUES (2,'crusader','Crusader');
INSERT INTO dc_class_starter_kit VALUES (2,'mainhand','legendary',1,'Flail','onehand','crusader');
INSERT INTO dc_class_starter_kit VALUES (2,'head','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'neck','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'shoulders','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'torso','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'waist','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'legs','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'feet','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'wrists','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'hands','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'finger','rare',2,'','','');
INSERT INTO dc_class_starter_kit VALUES (2,'offhand','rare',1,'Crusader Shield','offhand','crusader');
INSERT INTO dc_class_start_skill VALUES (2,201,43);
INSERT INTO dc_class_start_skill VALUES (2,196,44);
INSERT INTO dc_class_start_skill VALUES (2,198,54);
INSERT INTO dc_class_start_skill VALUES (2,202,55);
INSERT INTO dc_class_start_skill VALUES (2,199,160);
INSERT INTO dc_class_start_skill VALUES (2,197,172);
INSERT INTO dc_class_start_skill VALUES (2,1180,173);
INSERT INTO dc_class_start_skill VALUES (2,200,229);
INSERT INTO dc_class_start VALUES (3,'demonhunter','Demon Hunter');
INSERT INTO dc_class_starter_kit VALUES (3,'mainhand','legendary',1,'Bow','twohand','demonhunter');
INSERT INTO dc_class_starter_kit VALUES (3,'head','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'neck','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'shoulders','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'torso','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'waist','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'legs','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'feet','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'wrists','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'hands','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'finger','rare',2,'','','');
INSERT INTO dc_class_starter_kit VALUES (3,'offhand','rare',1,'Quiver','offhand','demonhunter');
INSERT INTO dc_class_start_skill VALUES (3,201,43);
INSERT INTO dc_class_start_skill VALUES (3,196,44);
INSERT INTO dc_class_start_skill VALUES (3,264,45);
INSERT INTO dc_class_start_skill VALUES (3,198,54);
INSERT INTO dc_class_start_skill VALUES (3,1180,173);
INSERT INTO dc_class_start_skill VALUES (3,5011,226);
INSERT INTO dc_class_start VALUES (8,'wizard','Wizard');
INSERT INTO dc_class_starter_kit VALUES (8,'mainhand','legendary',1,'Wand','onehand','wizard');
INSERT INTO dc_class_starter_kit VALUES (8,'head','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'neck','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'shoulders','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'torso','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'waist','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'legs','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'feet','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'wrists','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'hands','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'finger','rare',2,'','','');
INSERT INTO dc_class_starter_kit VALUES (8,'offhand','rare',1,'Source','offhand','wizard');
INSERT INTO dc_class_start_skill VALUES (8,201,43);
INSERT INTO dc_class_start_skill VALUES (8,196,44);
INSERT INTO dc_class_start_skill VALUES (8,264,45);
INSERT INTO dc_class_start_skill VALUES (8,198,54);
INSERT INTO dc_class_start_skill VALUES (8,202,55);
INSERT INTO dc_class_start_skill VALUES (8,227,136);
INSERT INTO dc_class_start_skill VALUES (8,199,160);
INSERT INTO dc_class_start_skill VALUES (8,197,172);
INSERT INTO dc_class_start_skill VALUES (8,1180,173);
INSERT INTO dc_class_start_skill VALUES (8,5011,226);
INSERT INTO dc_class_start_skill VALUES (8,5009,228);
INSERT INTO dc_class_start VALUES (12,'monk','Monk');
INSERT INTO dc_class_starter_kit VALUES (12,'mainhand','legendary',1,'Fist Weapon','onehand','monk');
INSERT INTO dc_class_starter_kit VALUES (12,'head','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'neck','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'shoulders','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'torso','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'waist','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'legs','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'feet','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'wrists','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'hands','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'finger','rare',2,'','','');
INSERT INTO dc_class_starter_kit VALUES (12,'offhand','rare',1,'Fist Weapon','onehand','monk');
INSERT INTO dc_class_start_skill VALUES (12,196,44);
INSERT INTO dc_class_start_skill VALUES (12,197,172);
INSERT INTO dc_class_start_skill VALUES (12,198,54);
INSERT INTO dc_class_start_skill VALUES (12,199,160);
INSERT INTO dc_class_start_skill VALUES (12,200,229);
INSERT INTO dc_class_start_skill VALUES (12,201,43);
INSERT INTO dc_class_start_skill VALUES (12,202,55);
INSERT INTO dc_class_start_skill VALUES (12,227,136);
INSERT INTO dc_class_start_skill VALUES (12,15590,473);
INSERT INTO dc_class_start_skill VALUES (12,1180,173);
INSERT INTO dc_class_start_skill VALUES (12,674,118);
INSERT INTO dc_class_start VALUES (13,'necromancer','Necromancer');
INSERT INTO dc_class_starter_kit VALUES (13,'mainhand','legendary',1,'Scythe','onehand','necromancer');
INSERT INTO dc_class_starter_kit VALUES (13,'head','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'neck','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'shoulders','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'torso','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'waist','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'legs','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'feet','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'wrists','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'hands','rare',1,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'finger','rare',2,'','','');
INSERT INTO dc_class_starter_kit VALUES (13,'offhand','rare',1,'Phylactery','offhand','necromancer');
INSERT INTO dc_class_start_skill VALUES (13,196,44);
INSERT INTO dc_class_start_skill VALUES (13,197,172);
INSERT INTO dc_class_start_skill VALUES (13,198,54);
INSERT INTO dc_class_start_skill VALUES (13,199,160);
INSERT INTO dc_class_start_skill VALUES (13,200,229);
INSERT INTO dc_class_start_skill VALUES (13,201,43);
INSERT INTO dc_class_start_skill VALUES (13,202,55);
INSERT INTO dc_class_start_skill VALUES (13,227,136);
INSERT INTO dc_class_start_skill VALUES (13,264,45);
INSERT INTO dc_class_start_skill VALUES (13,1180,173);
INSERT INTO dc_class_start_skill VALUES (13,5009,228);
INSERT INTO dc_class_start_skill VALUES (13,5011,226);
COMMIT;
-- Generated from data/tunables/*.csv by generate_tunables.py; edit the CSV
-- and rerun. Apply to the world database.
-- Tunables phase 2 section M: every number that is the designer's rather than D3's,
-- in one table, tunable at runtime with `.dc tunables set`.
--
-- CREATE TABLE IF NOT EXISTS and ON DUPLICATE KEY UPDATE, never DROP: this
-- migration is re-applied whenever a CSV changes, and re-applying it writes
-- the CSV's numbers over whatever is in the table (ruling 2026-09-19). A value
-- set in game with `.dc tunables set` is a scratch override and does not
-- survive the next apply; a CSV `value` left blank puts the row back to its
-- published d3_value.
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_tunables` (
  `category` VARCHAR(24) NOT NULL COMMENT 'One of the fifteen data/tunables/ files',
  `name` VARCHAR(64) NOT NULL COMMENT 'lower_snake_case, unique inside the category',
  `d3_value` DOUBLE NULL COMMENT 'What D3 published, when the row has one. Regenerated from the CSV; never hand-edited',
  `tuned_value` DOUBLE NULL COMMENT 'the designer''s value. NULL means use d3_value. Never overwritten by generation',
  `unit` VARCHAR(24) NOT NULL COMMENT 'yards | seconds | milliseconds | percent | count | multiplier | degrees | flag | damage | gold | level | ...',
  `notes` LONGTEXT NOT NULL COMMENT 'The audit row or decision this number came from',
  PRIMARY KEY (`category`, `name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_tunables` (`category`, `name`, `d3_value`, `tuned_value`, `unit`, `notes`) VALUES
('paragon', 'starting_paragon_level', NULL, 200.0, 'level', 'ruling 2026-09-28; account-mode floor on character creation; 0 disables the floor.')
ON DUPLICATE KEY UPDATE `tuned_value` = VALUES(`tuned_value`), `d3_value` = VALUES(`d3_value`), `unit` = VALUES(`unit`), `notes` = VALUES(`notes`);

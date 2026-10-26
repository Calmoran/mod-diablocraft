-- Generated from data/d3/class_starts.csv by generate_sql.py --class-starts.
-- Class-keyed equivalents for rolled starter items and login proficiency repair.
-- Native learnSpell/LearnDefaultSkill and item roll/equip APIs remain authoritative.
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS dc_class_start (class_id TINYINT UNSIGNED PRIMARY KEY, class_key VARCHAR(40) NOT NULL UNIQUE, class_name VARCHAR(80) NOT NULL) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS dc_class_starter_kit (class_id TINYINT UNSIGNED NOT NULL, slot VARCHAR(20) NOT NULL, rarity VARCHAR(20) NOT NULL, count INT UNSIGNED NOT NULL, PRIMARY KEY(class_id,slot)) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS dc_class_start_skill (class_id TINYINT UNSIGNED NOT NULL, spell_id INT UNSIGNED NOT NULL, skill_id INT UNSIGNED NOT NULL, PRIMARY KEY(class_id,spell_id), UNIQUE KEY(class_id,skill_id)) ENGINE=InnoDB;
START TRANSACTION;
DELETE FROM dc_class_start_skill;
DELETE FROM dc_class_starter_kit;
DELETE FROM dc_class_start;
INSERT INTO dc_class_start VALUES (1,'barbarian','Barbarian');
INSERT INTO dc_class_starter_kit VALUES (1,'mainhand','legendary',1);
INSERT INTO dc_class_starter_kit VALUES (1,'head','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'neck','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'shoulders','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'torso','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'waist','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'legs','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'feet','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'wrists','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'hands','rare',1);
INSERT INTO dc_class_starter_kit VALUES (1,'finger','rare',2);
INSERT INTO dc_class_starter_kit VALUES (1,'offhand','rare',1);
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
COMMIT;

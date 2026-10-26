-- Generated from data/d3/rift_guardian_models.csv by generate_rift_affixes.py;
-- edit the CSV and rerun. Apply to the world database.
-- 09-rifts F5 / section 4: the three stage-1 guardians and the two mapped
-- abilities each, as shell ids the module casts in place of the stock AI.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_rift_guardian`;
CREATE TABLE `dc_rift_guardian` (
  `guardian` VARCHAR(64) NOT NULL,
  `creature_id` INT NOT NULL COMMENT 'wow_creature_id from the CSV',
  `display_id` INT NOT NULL,
  `ability_1` VARCHAR(64) NOT NULL,
  `ability_1_shell` INT NOT NULL,
  `ability_1_wow_spell` INT NOT NULL COMMENT 'The spell the shell clones',
  `ability_1_behaviour` VARCHAR(16) NOT NULL COMMENT 'nova | leap | frenzy',
  `ability_2` VARCHAR(64) NOT NULL,
  `ability_2_shell` INT NOT NULL,
  `ability_2_wow_spell` INT NOT NULL,
  `ability_2_behaviour` VARCHAR(16) NOT NULL,
  PRIMARY KEY (`guardian`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_rift_guardian` (`guardian`, `creature_id`, `display_id`, `ability_1`, `ability_1_shell`, `ability_1_wow_spell`, `ability_1_behaviour`, `ability_2`, `ability_2_shell`, `ability_2_wow_spell`, `ability_2_behaviour`) VALUES
('Bloodmaw', 36612, 31119, 'Leap Rage', 81170, 6544, 'leap', 'Frenzy', 81171, 28131, 'frenzy'),
('Agnidox', 12056, 12129, 'Fireball Volley', 81168, 11988, 'nova', 'Flame Nova', 81169, 1535, 'nova'),
('Cold Snap', 34797, 29263, 'Cold Nova', 81172, 122, 'nova', 'Charge', 81173, 52305, 'leap');

-- Generated from data/d3/barbarian_skills.csv; edit the CSV and rerun generate_sql.py.
-- Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_barbarian_skills`;
CREATE TABLE `dc_barbarian_skills` (
  `skill_name` LONGTEXT NOT NULL,
  `category` LONGTEXT NOT NULL,
  `unlock_level` BIGINT NULL,
  `fury_cost` BIGINT NULL,
  `fury_generation` BIGINT NULL,
  `cooldown_seconds` BIGINT NULL,
  `damage_pct_weapon_damage` BIGINT NULL,
  `element` LONGTEXT NOT NULL,
  `full_tooltip_text` LONGTEXT NOT NULL,
  `notes` LONGTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_barbarian_skills` (`skill_name`, `category`, `unlock_level`, `fury_cost`, `fury_generation`, `cooldown_seconds`, `damage_pct_weapon_damage`, `element`, `full_tooltip_text`, `notes`) VALUES
('Frenzy', 'Primary', 11, NULL, 4, NULL, 220, 'Physical', 'Generate: 4 Fury per attack | Swing for 220% weapon damage. Frenzy''s attack speed increases by 15% for 4 seconds with each swing. This effect stacks up to 5 times. | Primary | Unlocked at level 11.', ''),
('Weapon Throw', 'Primary', 17, NULL, 6, NULL, 275, 'Physical', 'Generate: 6 Fury per attack | Hurl a throwing weapon at an enemy dealing 275% weapon damage. | Primary | Unlocked at level 17.', ''),
('Bash', 'Primary', 1, NULL, 6, NULL, 320, 'Physical', 'Generate: 6 Fury per attack | Brutally smash an enemy for 320% weapon damage. | Primary | Unlocked at level 1.', ''),
('Cleave', 'Primary', 3, NULL, 6, NULL, 200, 'Physical', 'Generate: 6 Fury per attack | Swing your weapon in a wide arc to deal 200% weapon damage to all enemies caught in the swing. | Primary | Unlocked at level 3.', ''),
('Whirlwind', 'Secondary', 20, 10, NULL, NULL, 340, 'Physical', 'Cost: 10 Fury | Deliver multiple attacks to everything in your path for 340% weapon damage. | While whirlwinding, you move at 100% movement speed. | Secondary | Unlocked at level 20.', ''),
('Ancient Spear', 'Secondary', 26, 25, NULL, NULL, 500, 'Physical', 'Cost: 25 Fury | Throw a spear that pierces enemies and deals 500% weapon damage. | Secondary | Unlocked at level 26.', ''),
('Seismic Slam', 'Secondary', 12, 30, NULL, NULL, 620, 'Physical', 'Cost: 30 Fury | Slam the ground and cause a wave of destruction that deals 620% weapon damage to enemies up to 50 yards in front of you. | Secondary | Unlocked at level 12.', ''),
('Hammer of the Ancients', 'Secondary', 2, 20, NULL, NULL, 535, 'Physical', 'Cost: 20 Fury | Call forth a massive hammer to smash enemies directly in front of you for 535% weapon damage. Hammer of the Ancients has a 1% increased Critical Hit Chance for every 5 Fury that you have. | Secondary | Unlocked at level 2.', ''),
('Rend', 'Secondary', 5, 20, NULL, NULL, 1100, 'Physical', 'Cost: 20 Fury | A sweeping strike causes all enemies within 12 yards to Bleed for 1100% weapon damage as Physical over 5 seconds. | Secondary | Unlocked at level 5.', ''),
('Sprint', 'Defensive', 16, 20, NULL, NULL, NULL, 'Physical', 'Cost: 20 Fury | Increase movement speed by 30% for 3 seconds. | Defensive | Unlocked at level 16.', ''),
('Ignore Pain', 'Defensive', 22, NULL, NULL, 30, NULL, 'Physical', 'Cooldown: 30 seconds | Reduce all damage taken by 50% and gain Immunity to all control-impairing effects for 5 seconds. | Defensive | Unlocked at level 22.', ''),
('Ground Stomp', 'Defensive', 4, NULL, 15, 12, NULL, 'Physical', 'Generate: 15 Fury | Cooldown: 12 seconds | Smash the ground, stunning all enemies within 14 yards for 4 seconds. | Defensive | Unlocked at level 4.', ''),
('Leap', 'Defensive', 8, NULL, 15, 10, 180, 'Physical', 'Generate: 15 Fury | Cooldown: 10 seconds | Leap into the air, dealing 180% weapon damage to all enemies within 10 yards of your destination and slowing their movement speed by 60% for 3 seconds. | Defensive | Unlocked at level 8.', ''),
('Furious Charge', 'Might', 21, NULL, 15, NULL, 600, 'Physical', 'Cost: 1 Charge | Generate: 15 Fury | Rush forward knocking back and dealing 600% weapon damage to enemies along your path. | You gain a charge every 10 seconds and can have up to 1 charge stored at a time. | Might | Unlocked at level 21.', ''),
('Avalanche', 'Might', 61, NULL, NULL, 30, 2400, 'Physical', 'Cooldown: 30 seconds | Cause a massive avalanche of rocks to fall on an area dealing 2400% weapon damage to all enemies caught in its path. | Cooldown is reduced by 1 second for every 25 Fury you spend. | Might | Unlocked at level 61.', ''),
('Overpower', 'Might', 9, NULL, NULL, 12, 380, 'Physical', 'Cooldown: 12 seconds | Deal 380% weapon damage to all enemies within 9 yards. | Critical Hits have a chance to reduce the cooldown of Overpower by 1 second. | Might | Unlocked at level 9.', ''),
('Revenge', 'Might', 13, NULL, NULL, NULL, 300, 'Physical', 'Cost: 1 charge | Deal 300% weapon damage to all nearby enemies. You heal 4% of your maximum Life for each enemy hit. | Revenge has a 15% chance to gain a charge each time you are hit. Maximum 2 charges. | Might | Unlocked at level 13.', ''),
('War Cry', 'Tactics', 28, NULL, 20, 20, NULL, 'Physical', 'Generate: 20 Fury | Cooldown: 20 seconds | Unleash a rallying cry to increase Armor for you and all allies within 100 yards by 20% for 120 seconds. | Tactics | Unlocked at level 28.', ''),
('Battle Rage', 'Tactics', 22, 20, NULL, NULL, NULL, 'Physical', 'Cost: 20 Fury | Enter a rage which increases your damage by 10% and Critical Hit Chance by 3%. Lasts 120 seconds. | Tactics | Unlocked at level 22.', ''),
('Threatening Shout', 'Tactics', 14, NULL, 15, 10, NULL, 'Physical', 'Generate: 15 Fury | Cooldown: 10 seconds | Shout with great ferocity, reducing damage done by enemies within 25 yards by 20% for 15 seconds. | Tactics | Unlocked at level 14.', ''),
('Wrath of the Berserker', 'Rage', 30, NULL, NULL, 120, NULL, 'Physical', 'Cooldown: 120 seconds | Enter a berserker rage which raises several attributes for 20 seconds. | Critical Hit Chance: 10% | Attack Speed: 25% | Dodge Chance: 20% | Movement Speed: 20% | Rage | Unlocked at level 30.', ''),
('Call of the Ancients', 'Rage', 25, NULL, NULL, 120, 270, 'Physical', 'Cooldown: 120 seconds | Summon the ancient Barbarians Talic, Korlic, and Madawc to fight alongside you for 20 seconds. Each deals 270% weapon damage per swing in addition to bonus abilities. | Talic wields a sword and shield and uses Whirlwind and Leap. | Korlic wields a massive polearm and uses Cleave and Furious Charge. | Madawc dual-wields axes and uses Weapon Throw and Seismic Slam. | Rage | Unlocked at level 25.', ''),
('Earthquake', 'Rage', 19, 25, NULL, 60, 4800, 'Fire', 'Cost: 25 Fury | Cooldown: 60 seconds | Shake the ground violently, dealing 4800% weapon damage as Fire over 8 seconds to all enemies within 18 yards. | Rage | Unlocked at level 19.', '');

-- Generated from data/d3/elite_affixes.csv by generate_rift_affixes.py;
-- edit the CSV and rerun. Apply to the world database.
-- 09-rifts section 2 step 2: the elite affix pool for rift packs.
-- behaviour is empty for the affixes that are name-only in stage 1.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_rift_affix`;
CREATE TABLE `dc_rift_affix` (
  `affix_name` VARCHAR(64) NOT NULL,
  `appears_on` VARCHAR(16) NOT NULL COMMENT 'both | champion | rare',
  `min_tier` INT NOT NULL COMMENT 'From min_difficulty; 1=Normal, 5=Torment I',
  `min_hero_level` INT NOT NULL COMMENT 'From min_difficulty',
  `element` VARCHAR(16) NOT NULL COMMENT 'damage_type mapped by 01-stats S9',
  `behaviour` VARCHAR(16) NOT NULL COMMENT 'Empty when the affix is name-only',
  `shell_spell` INT NOT NULL COMMENT '0 when name-only',
  `pool` VARCHAR(16) NOT NULL COMMENT 'offensive | defensive | crowd_control (13 S4.2)',
  `level_60_limited` TINYINT NOT NULL COMMENT 'One of the eleven a level 60+ pack may take at most three of',
  `rollable` TINYINT NOT NULL COMMENT '0 keeps the affix out of the roll pool',
  `minion_inherits` TINYINT NOT NULL COMMENT 'elite_affix_eligibility.csv minion column; 0 is leader-only',
  `effect` LONGTEXT NOT NULL,
  PRIMARY KEY (`affix_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_rift_affix` (`affix_name`, `appears_on`, `min_tier`, `min_hero_level`, `element`, `behaviour`, `shell_spell`, `pool`, `level_60_limited`, `rollable`, `minion_inherits`, `effect`) VALUES
('Arcane Enchanted', 'both', 1, 31, 'arcane', 'beam', 81174, 'offensive', 1, 1, 1, 'Spawns a purple orb with a 2-second arming delay that emits a rotating 25-yard beam of arcane energy dealing continuous heavy damage for 10 seconds.'),
('Avenger', 'champion', 1, 51, 'physical', 'avenger', 0, 'defensive', 0, 1, 0, 'When one member of a Champion pack dies, the remaining Champions gain increased physical size, attack speed, movement speed, and damage.'),
('Desecrator', 'both', 1, 22, 'physical', 'desecrator', 81175, 'offensive', 1, 1, 0, 'Spawns a pool of burning void on the ground directly beneath the player that arms after 1 second and deals rapid stacking damage over time.'),
('Electrified', 'both', 1, 10, 'lightning', 'reflect', 81165, 'offensive', 0, 1, 1, 'When struck by any player attack, the monster discharges sparks and charged bolts in 4 directions that travel outward. Leaves a lingering electric orb on death.'),
('Fast', 'both', 1, 10, 'physical', 'fast', 0, 'offensive', 0, 1, 1, 'Passively increases monster movement speed by 40%, attack speed by 20%, and skill cast speed by 10%.'),
('Fire Chains', 'champion', 1, 31, 'fire', 'chains', 81176, 'defensive', 1, 1, 0, 'Connects all Champions in the pack with links of burning fire. Players touching or crossing between the fire chains take continuous extreme Fire damage.'),
('Frozen', 'both', 1, 10, 'cold', 'cluster', 81164, 'offensive', 1, 1, 1, 'Drops clusters of pulsating ice crystals near the player that grow for 2.5 to 3 seconds and explode, dealing heavy Cold damage and freezing players for 2.5 seconds.'),
('Frozen Pulse', 'both', 1, 31, 'cold', 'pulse', 81177, 'offensive', 1, 1, 0, 'Spawns a tracking icy sphere that follows the player, locks onto a location, and continuously pulses a 15-yard radial chilling blast for 10 seconds, dealing heavy Cold damage and slowing by 60%.'),
('Health Link', 'champion', 1, 51, 'physical', 'healthlink', 0, 'defensive', 0, 1, 0, 'Links the health pools of all Champion pack members together. Damage dealt to any single Champion is distributed equally among all living pack members.'),
('Horde', 'rare', 1, 51, 'physical', 'horde', 0, 'defensive', 0, 1, 0, 'Doubles the number of minions that spawn alongside the Rare Elite: the rolled base of 2 to 4 becomes 4 to 8. Minions do not inherit all Rare affixes.'),
('Illusionist', 'both', 1, 22, 'physical', 'illusionist', 0, 'defensive', 0, 1, 1, 'When damaged, the monster summons 2 to 3 illusory duplicates of itself that have reduced health, copy the monster''s appearance, and can cast minor abilities.'),
('Jailer', 'both', 1, 10, 'physical', 'jailer', 81178, 'crowd_control', 0, 1, 1, 'Traps the player inside a stationary circular bone prison, immobilizing them for 2 seconds and dealing an initial burst of Physical damage on cast.'),
('Juggernaut', 'rare', 5, 60, 'physical', 'juggernaut', 0, 'defensive', 0, 1, 0, 'The Rare monster is permanently immune to all crowd control effects (stuns, slows, freezes, knockbacks) and moves 30% slower, but takes 30% more damage from all sources. It gets no health bonus.'),
('Knockback', 'both', 1, 10, 'physical', 'knockback', 0, 'crowd_control', 0, 1, 1, 'Monster attacks push the player away several yards, slow movement speed by 60% for 1.5 seconds, and interrupt channeled abilities.'),
('Missile Dampening', 'rare', 1, 22, 'physical', '', 0, 'defensive', 0, 0, 0, 'Generates a massive translucent spherical bubble around the Rare monster that slows all player projectiles passing through it by 90%.'),
('Molten', 'both', 1, 10, 'fire', 'trail', 81163, 'offensive', 1, 1, 1, 'Leaves a burning trail of lava behind the monster that deals continuous Fire damage. When the monster dies, it leaves an explosive magma core that detonates after 3 seconds for lethal Fire damage.'),
('Mortar', 'both', 1, 22, 'fire', 'mortar', 81179, 'offensive', 1, 1, 1, 'Launches high-arcing lobbed fireballs towards players outside melee range (creates a dead zone in close melee where mortar shells cannot land).'),
('Nightmarish', 'both', 1, 10, 'physical', 'nightmarish', 0, 'crowd_control', 0, 1, 1, 'Monster hits have a chance to inflict Fear on the player for 2 seconds, forcing the character to run uncontrollably away.'),
('Orbiter', 'both', 1, 31, 'lightning', 'orbiter', 81180, 'offensive', 1, 1, 0, 'Spawns a central electrical focal point that releases dozens of small electric spheres in an expanding spiral and circular orbit, dealing Lightning damage on contact.'),
('Plagued', 'both', 1, 10, 'poison', 'pool', 81166, 'offensive', 1, 1, 1, 'Drops persistent puddles of toxic green sludge beneath the monster that stack and deal continuous Poison damage for up to 9 seconds.'),
('Poison Enchanted', 'both', 1, 31, 'poison', 'poisonenchanted', 81181, 'offensive', 1, 1, 0, 'Spawns a central poison projectile that arms and shoots 4 lines of toxic gas outward in an expanding cross formation, dealing heavy Poison damage.'),
('Reflects Damage', 'both', 1, 10, 'physical', 'reflectsdamage', 81182, 'offensive', 0, 1, 1, 'Periodically activates a spiky visual aura. When active, any player attack hitting the monster reflects homing projectiles back at the player dealing damage matching the attack''s element.'),
('Shielding', 'both', 1, 22, 'physical', 'shielding', 0, 'defensive', 0, 1, 1, 'Periodically grants the monster an impenetrable energy shield for 5 seconds, making it completely immune to all damage. Only one monster in a pack can shield at a time.'),
('Teleporter', 'both', 1, 10, 'physical', 'teleporter', 0, 'offensive', 0, 1, 1, 'Periodically teleports the monster directly towards or away from the player, clearing player targeting and repositioning.'),
('Thunderstorm', 'both', 1, 31, 'lightning', 'thunderstorm', 81183, 'offensive', 0, 1, 0, 'Calls down lightning strikes directly on the player''s location with near-zero warning delay, dealing immediate Lightning damage.'),
('Vortex', 'both', 1, 22, 'physical', 'vortex', 0, 'crowd_control', 0, 1, 0, 'Periodically casts a gravity pull that pulls the player directly into the monster''s melee range and interrupts active skills.'),
('Waller', 'both', 1, 10, 'physical', '', 0, 'offensive', 0, 1, 0, 'Spawns physical stone walls in the arena to block movement and line of sight. Champions summon a single wall; Rares summon a U-shaped barrier trapping the player.'),
('Wormhole', 'both', 1, 31, 'arcane', '', 0, 'crowd_control', 1, 1, 0, 'Spawns two interconnected swirling purple portals on the ground. Walking into or standing in a portal teleports the player to the destination portal after a 1-second transfer time.');

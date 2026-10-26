-- Generated from data/d3/rift_quests.csv by generate_rifts.py; edit the
-- CSV and rerun. Apply to the world database.
-- 09-rifts section 7 (Phase A): Nephalem Rifts on the quest system.
--
-- Zero rewards of every kind (7.5): no items, choices, money, honor,
-- reputation, title, talents, arena points, reward spell or mail, and
-- RewardXPDifficulty 0. XP is additionally zeroed in the module's
-- OnPlayerQuestComputeXP, because RewardXPDifficulty is a DBC index and
-- an index of 0 does not by itself mean zero XP. The closing reward is
-- paid by the module, never by the quest.
--
-- Repeatable is quest_template_addon.SpecialFlags = 1, not a quest flag.
SET NAMES utf8mb4;

-- The synthetic kill objective's target (7.3). A valid, module-owned,
-- never-spawned creature_template: the loader clears objectives whose
-- creature entry does not exist, so a fabricated missing entry is not an
-- option. It is given no model on purpose - nothing ever spawns it, and a
-- display row would only be one more thing to keep true.
--
-- Cloned from a stock row rather than inserted column by column, the way
-- generate_hub.py builds its artisans: creature_template has a hundred
-- columns and this migration must not depend on which of them carry a
-- DEFAULT. Only identity and behaviour are overridden; nothing of the
-- source's gossip, loot, quests or script survives on 910015.
DELETE FROM `creature_template` WHERE `entry` = 910015;
CREATE TEMPORARY TABLE `dc_rift_credit_template` LIKE `creature_template`;
INSERT INTO `dc_rift_credit_template` SELECT * FROM `creature_template` WHERE `entry` = 2840;
UPDATE `dc_rift_credit_template` SET
  `entry` = 910015, `name` = 'Rift Progress', `subname` = '',
  `npcflag` = 0, `ScriptName` = '', `AIName` = '', `gossip_menu_id` = 0,
  `lootid` = 0, `pickpocketloot` = 0, `skinloot` = 0,
  `KillCredit1` = 0, `KillCredit2` = 0;
INSERT INTO `creature_template` SELECT * FROM `dc_rift_credit_template`;
DROP TEMPORARY TABLE `dc_rift_credit_template`;
DELETE FROM `creature_template_model` WHERE `CreatureID` = 910015;

-- The run-owned entrance portal beside the obelisk (7.9.7), now a POOL of
-- looks with one rolled per rift (ruling 2026-09-17). Summoned and removed
-- by the module like the town portal halves; never spawned from the
-- `gameobject` table. Every row is named the same, because that name is
-- what a player reads on the portal; the look's own name is the designer's label
-- and lives in dc_rift_portal below.
--
-- The single-display 910014 is retired and goes here, so a world
-- database that already carries it does not keep a template nothing rolls.
DELETE FROM `gameobject_template` WHERE `entry` = 910014;
DELETE FROM `gameobject_template` WHERE `entry` IN (910030, 910031, 910032, 910033, 910034, 910035, 910036, 910037, 910038, 910039, 910040, 910041, 910042, 910043, 910044, 910045, 910046);
INSERT INTO `gameobject_template`
  (`entry`, `type`, `displayId`, `name`, `IconName`, `castBarCaption`, `unk1`, `size`,
   `Data0`, `Data1`, `Data2`, `Data3`, `Data4`, `Data5`, `Data6`, `Data7`, `Data8`, `Data9`,
   `Data10`, `Data11`, `Data12`, `Data13`, `Data14`, `Data15`, `Data16`, `Data17`, `Data18`,
   `Data19`, `Data20`, `Data21`, `Data22`, `Data23`, `AIName`, `ScriptName`, `VerifiedBuild`)
VALUES
  -- Darnassus
  (910030, 22, 4393, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Orgrimmar
  (910031, 22, 4395, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Undercity
  (910032, 22, 4398, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Silvermoon
  (910033, 22, 6956, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Dalaran
  (910034, 22, 8111, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Ironforge
  (910035, 22, 4394, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Thunder Bluff
  (910036, 22, 4397, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Exodar
  (910037, 22, 6955, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Shattrath
  (910038, 22, 7146, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Isle of Quel'Danas
  (910039, 22, 7628, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Blasted Lands
  (910040, 22, 8948, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Wintergrasp
  (910041, 22, 8506, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Stonard
  (910042, 22, 7849, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Inner Maraudon
  (910043, 22, 5231, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Caverns of Time
  (910044, 22, 8475, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Theramore
  (910045, 22, 7848, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  -- Karazhan
  (910046, 22, 6831, 'Rift Entrance', '', '', '', 1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340);

-- What the module rolls from. The display and the scale are already on the
-- templates above; they are repeated here so `.dc shatter list` and the
-- startup log can name a look without reading gameobject_template, and so a
-- row that loses its template is a loud startup failure rather than an
-- invisible portal.
DROP TABLE IF EXISTS `dc_rift_portal`;
CREATE TABLE `dc_rift_portal` (
  `entry` INT NOT NULL,
  `display_id` INT NOT NULL,
  `name` LONGTEXT NOT NULL COMMENT 'The look, for the designer and the GM preview; never shown to a player',
  `scale` DOUBLE NOT NULL COMMENT 'the designer''s tunable, per look',
  PRIMARY KEY (`entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_rift_portal` (`entry`, `display_id`, `name`, `scale`) VALUES
  (910030, 4393, 'Darnassus', 1.0),
  (910031, 4395, 'Orgrimmar', 1.0),
  (910032, 4398, 'Undercity', 1.0),
  (910033, 6956, 'Silvermoon', 1.0),
  (910034, 8111, 'Dalaran', 1.0),
  (910035, 4394, 'Ironforge', 1.0),
  (910036, 4397, 'Thunder Bluff', 1.0),
  (910037, 6955, 'Exodar', 1.0),
  (910038, 7146, 'Shattrath', 1.0),
  (910039, 7628, 'Isle of Quel''Danas', 1.0),
  (910040, 8948, 'Blasted Lands', 1.0),
  (910041, 8506, 'Wintergrasp', 1.0),
  (910042, 7849, 'Stonard', 1.0),
  (910043, 5231, 'Inner Maraudon', 1.0),
  (910044, 8475, 'Caverns of Time', 1.0),
  (910045, 7848, 'Theramore', 1.0),
  (910046, 6831, 'Karazhan', 1.0);

-- The six fixed variants (7.3). Three denominators, two modes; the
-- Greater rows are emitted and unused until Phase B.
DELETE FROM `quest_template_addon` WHERE `ID` IN (910020, 910021, 910022, 910023, 910024, 910025);
DELETE FROM `quest_template` WHERE `ID` IN (910020, 910021, 910022, 910023, 910024, 910025);
INSERT INTO `quest_template`
  (`ID`, `QuestType`, `QuestLevel`, `MinLevel`, `QuestSortID`, `QuestInfoID`,
   `SuggestedGroupNum`, `TimeAllowed`, `AllowableRaces`, `Flags`, `RewardXPDifficulty`,
   `RewardMoney`, `RewardMoneyDifficulty`, `LogTitle`, `LogDescription`, `QuestDescription`,
   `QuestCompletionLog`, `RequiredNpcOrGo1`, `RequiredNpcOrGoCount1`, `ObjectiveText1`)
VALUES
  (910020, 2, -1, 0, 0, 0, 0, 0, 0, 256, 0, 0, 0, 'Nephalem Rift', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'The rift is closing.', 910015, 1200, 'Rift progress'),
  (910021, 2, -1, 0, 0, 0, 0, 0, 0, 256, 0, 0, 0, 'Nephalem Rift', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'The rift is closing.', 910015, 1800, 'Rift progress'),
  (910022, 2, -1, 0, 0, 0, 0, 0, 0, 256, 0, 0, 0, 'Nephalem Rift', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'The rift is closing.', 910015, 2600, 'Rift progress'),
  (910023, 2, -1, 0, 0, 0, 0, 900, 0, 256, 0, 0, 0, 'Greater Rift', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'The rift is closing.', 910015, 1200, 'Rift progress'),
  (910024, 2, -1, 0, 0, 0, 0, 900, 0, 256, 0, 0, 0, 'Greater Rift', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'The rift is closing.', 910015, 1800, 'Rift progress'),
  (910025, 2, -1, 0, 0, 0, 0, 900, 0, 256, 0, 0, 0, 'Greater Rift', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'Enter the rift, fill its progress and slay the Rift Guardian, then report to the Rift Keeper.', 'The rift is closing.', 910015, 2600, 'Rift progress');

-- Repeatable, and nothing else: no prerequisite, exclusive group or mail.
INSERT INTO `quest_template_addon` (`ID`, `SpecialFlags`) VALUES
  (910020, 1),
  (910021, 1),
  (910022, 1),
  (910023, 1),
  (910024, 1),
  (910025, 1);

-- 7.2: the obelisk STARTS the rift quest, the Keeper ENDS it. The reverse
-- relations are deliberately not written - both entities starting and
-- ending every run is not what 'quest givers' means here. Greater Rift
-- variants get no relation until Phase B decides how Queue offers them.
DELETE FROM `gameobject_queststarter` WHERE `id` = 910011;
INSERT INTO `gameobject_queststarter` (`id`, `quest`) VALUES
  (910011, 910020),
  (910011, 910021),
  (910011, 910022);
DELETE FROM `creature_questender` WHERE `id` = 910003;
INSERT INTO `creature_questender` (`id`, `quest`) VALUES
  (910003, 910020),
  (910003, 910021),
  (910003, 910022);

-- Reasserted here; see the generator docstring for why this migration
-- owns two rows it did not create.
UPDATE `gameobject_template` SET `type` = 2
  WHERE `entry` = 910011;
UPDATE `creature_template` SET `npcflag` = 3
  WHERE `entry` = 910003;

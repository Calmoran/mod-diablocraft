-- Generated from data/d3/rift_quests.csv by generate_rifts.py; edit the CSV and rerun.
-- Apply to the world database, after rifts_0011 and rifts_0018.
-- Monster spawning S3 (docs/proposals/monster-spawning.md 3.9.4): one rift quest per mode, counting
-- hundredths of a D3 progress point; 65,000 = the 650 points that fill the bar, inside the core's
-- 16-bit quest counter. The kills_required variants are retired.
SET NAMES utf8mb4;
DELETE FROM `quest_template_addon` WHERE `ID` IN (910021, 910022, 910024, 910025);
DELETE FROM `quest_template` WHERE `ID` IN (910021, 910022, 910024, 910025);
DELETE FROM `gameobject_queststarter` WHERE `id` = 910011 AND `quest` IN (910021, 910022, 910024, 910025);
DELETE FROM `creature_questender` WHERE `id` = 910003 AND `quest` IN (910021, 910022, 910024, 910025);
UPDATE `quest_template` SET `RequiredNpcOrGoCount1` = 65000 WHERE `ID` = 910020;
UPDATE `quest_template` SET `RequiredNpcOrGoCount1` = 65000 WHERE `ID` = 910023;

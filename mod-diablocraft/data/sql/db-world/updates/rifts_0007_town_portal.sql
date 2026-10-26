-- 09-rifts F3 / section 2: the two halves of the town portal.
--
-- Type 10 (GOOBER) is what the hub obelisk uses, and it is what makes a click
-- reach AllGameObjectScript::CanGameObjectGossipHello, where the module does the
-- teleport. Display 4396 is the stock blue mage portal (gameobject_template
-- 176296, "Portal to Stormwind"), so it reads as a portal without new art.
--
-- Neither is ever spawned from the `gameobject` table: the module summons the
-- rift half where the caster stands and the hub half beside the obelisk, and
-- removes both when the rift closes.
--
-- Apply to the world database.
SET NAMES utf8mb4;

DELETE FROM `gameobject_template` WHERE `entry` IN (910012, 910013);
INSERT INTO `gameobject_template`
  (`entry`, `type`, `displayId`, `name`, `IconName`, `castBarCaption`, `unk1`, `size`,
   `Data0`, `Data1`, `Data2`, `Data3`, `Data4`, `Data5`, `Data6`, `Data7`, `Data8`, `Data9`,
   `Data10`, `Data11`, `Data12`, `Data13`, `Data14`, `Data15`, `Data16`, `Data17`, `Data18`,
   `Data19`, `Data20`, `Data21`, `Data22`, `Data23`, `AIName`, `ScriptName`, `VerifiedBuild`)
VALUES
  (910012, 10, 4396, 'Town Portal', '', '', '', 1,
   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340),
  (910013, 10, 4396, 'Rift Portal', '', '', '', 1,
   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340);

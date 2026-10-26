-- Generated from data/d3/rift_quests.csv by generate_rifts.py; edit the CSV and rerun.
-- Apply to the world database.
-- Greater Rift: the Rift Keeper ends the Greater Rift quests as it ends the Nephalem ones
-- (09-rifts 7.2, 7.9.7; diablocraft-b3wi). The obelisk still starts none of them: the ready check
-- gives the quest.
DELETE FROM `creature_questender` WHERE `id` = 910003 AND `quest` IN (910023, 910024, 910025);
INSERT INTO `creature_questender` (`id`, `quest`) VALUES
  (910003, 910023),
  (910003, 910024),
  (910003, 910025);

-- Generated from data/d3/rift_quests.csv by generate_rifts.py; edit the CSV and rerun.
-- Apply to the world database, after rifts_0019.
-- Ruling 2026-10-16 (diablocraft-owe7u): the rift progress target is 30,000 hundredths of a
-- D3 progress point (300 points fill the bar), down from the 65,000 rifts_0019 set. Both bar quests.
UPDATE `quest_template` SET `RequiredNpcOrGoCount1` = 30000 WHERE `ID` = 910020;
UPDATE `quest_template` SET `RequiredNpcOrGoCount1` = 30000 WHERE `ID` = 910023;

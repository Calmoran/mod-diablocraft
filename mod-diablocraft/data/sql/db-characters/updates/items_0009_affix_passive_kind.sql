-- diablocraft-enuxm: the class passive the Hellfire Amulet grants is stored as a dc_item_affix row of kind
-- 'passive' (affix_id the passive's name), which the ENUM from items_0007 did not hold; strict mode would refuse
-- the row and fail the whole account operation it rides in (see items_0007 / diablocraft-obdh9).
-- Hand-written schema migration (ALTER only), applied by the core updater to the characters database;
-- MODIFY to the same type is a no-op, so a re-run changes nothing. Existing rows are unchanged.
ALTER TABLE dc_item_affix MODIFY COLUMN `kind` ENUM('primary','secondary','socket','gem','preset','power','passive') NOT NULL;

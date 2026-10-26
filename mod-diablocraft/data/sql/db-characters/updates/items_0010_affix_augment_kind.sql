-- diablocraft-wpt7l.8: Caldesann's Despair stores its bonus as a dc_item_affix row of kind 'augment' (affix_id the attribute,
-- value the amount), which the ENUM from items_0009 did not hold; strict mode would refuse the row and fail the whole account
-- operation it rides in (see items_0007 / diablocraft-obdh9, items_0009).
-- Hand-written schema migration (ALTER only), applied by the core updater to the characters database;
-- MODIFY to the same type is a no-op, so a re-run changes nothing. Existing rows are unchanged.
ALTER TABLE dc_item_affix MODIFY COLUMN `kind` ENUM('primary','secondary','socket','gem','preset','power','passive','augment') NOT NULL;

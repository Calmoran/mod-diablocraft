-- diablocraft-obdh9: a legendary power's per-item roll (diablocraft-ddnqh) is stored as a dc_item_affix
-- row of kind 'power', which the ENUM from items_0002 did not hold. Strict mode refused the row
-- ("Data truncated for column 'kind'", errno 1265), failing the whole account operation it rode in
-- (slot-vendor take, set-cache open) and kicking the player. Adds 'power'; existing rows are unchanged.
-- Hand-written schema migration (ALTER only), applied by the core updater to the characters database;
-- MODIFY to the same type is a no-op, so a re-run changes nothing.
ALTER TABLE dc_item_affix MODIFY COLUMN `kind` ENUM('primary','secondary','socket','gem','preset','power') NOT NULL;

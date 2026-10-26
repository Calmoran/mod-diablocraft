-- diablocraft-1z5ye: the potion slot keeps the potion's legendary power roll. A Bottomless potion rolls its power once per
-- item (dc_item_affix kind 'power', contract legendary-powers.md "Per-item rolls"); putting it in the slot destroys the item
-- with its rows, so the slot keeps the roll here and taking the potion off writes it back onto the returned item
-- (dc_inventory.cpp ChangePotion). NULL: no potion, or a potion that has no roll (a fixed power, or one that never rolled).
-- Hand-written schema migration (ALTER only), applied by the core updater to the characters database; it sorts after
-- classes_0003_character_potion.sql, which creates the table. Idempotent: the column is added only when it is missing.
SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_character_potion' AND column_name='power_roll');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_character_potion ADD COLUMN `power_roll` DOUBLE NULL DEFAULT NULL','DO 0');
PREPARE dc_potion_roll_ddl FROM @dc_ddl;
EXECUTE dc_potion_roll_ddl;
DEALLOCATE PREPARE dc_potion_roll_ddl;

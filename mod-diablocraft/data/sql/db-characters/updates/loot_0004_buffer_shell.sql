-- Apply to the CHARACTERS database. Hand-written schema, like loot_0003.
--
-- 06-loot L5: a drop that arrives with the bags full waits in dc_loot_buffer.
-- decisions.md 2026-09-17 makes a legendary or set drop an unrolled shell, and
-- a shell needs more than (base_item, item_level) to build: the roller will
-- want the rarity, the source it dropped from and the tier it dropped at, and
-- none of those can be recovered later. Without these columns a legendary that
-- waited in the buffer would come back as something else.
--
-- Idempotent ADD COLUMN, the same prepared-statement shape loot_0003 uses, so
-- re-applying the migration is a no-op. Existing rows keep the defaults, which
-- read as "not a shell" and deliver exactly as they do today.
SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='rarity');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN rarity VARCHAR(16) NOT NULL DEFAULT ''''','DO 0');
PREPARE dc_buffer_ddl FROM @dc_ddl;
EXECUTE dc_buffer_ddl;
DEALLOCATE PREPARE dc_buffer_ddl;

SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='drop_source');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN drop_source VARCHAR(32) NOT NULL DEFAULT ''''','DO 0');
PREPARE dc_buffer_ddl FROM @dc_ddl;
EXECUTE dc_buffer_ddl;
DEALLOCATE PREPARE dc_buffer_ddl;

SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='tier');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN tier TINYINT UNSIGNED NOT NULL DEFAULT 1','DO 0');
PREPARE dc_buffer_ddl FROM @dc_ddl;
EXECUTE dc_buffer_ddl;
DEALLOCATE PREPARE dc_buffer_ddl;

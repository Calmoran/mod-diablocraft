-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration (CREATE/ALTER only) that no generator owns,
-- which AGENTS.md allows under data/sql/*/updates. No data row is written.
--
-- diablocraft-class-roll-rules rule 4 (decisions.md 2026-09-23, brief d1561a1):
-- a drop's roll class - the dc_class_map class_key it rolled for, the looter's
-- or an off-class one - survives pickup, trade, stash and identify. It is
-- stored on the unidentified shell's row and on a held or ground drop's buffer
-- row. Rows written before this migration keep '' and fall back to the looter
-- they dropped for (dc_roll_class.h ShellClass), never to whoever identifies.
-- Idempotent: each column is added only when it is missing.
SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_item_unidentified' AND column_name='roll_class');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_item_unidentified ADD COLUMN `roll_class` VARCHAR(64) NOT NULL DEFAULT '''' COMMENT ''dc_class_map.class_key the drop rolled for - identify rolls this class''','DO 0');
PREPARE dc_roll_class_ddl FROM @dc_ddl;
EXECUTE dc_roll_class_ddl;
DEALLOCATE PREPARE dc_roll_class_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='roll_class');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `roll_class` VARCHAR(64) NOT NULL DEFAULT '''' COMMENT ''dc_class_map.class_key a rolled drop rolls for at delivery''','DO 0');
PREPARE dc_roll_class_ddl FROM @dc_ddl;
EXECUTE dc_roll_class_ddl;
DEALLOCATE PREPARE dc_roll_class_ddl;

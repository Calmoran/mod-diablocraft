-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration (ALTER only) that no generator owns, which AGENTS.md allows under
-- data/sql/*/updates. No data row is written.
--
-- diablocraft-t3t8 (decisions.md 2026-10-10 Ancient and Primal Ancient items): the quality tier of a
-- Legendary or Set drop is decided AT THE DROP, so it has to survive everything between the drop and the
-- identify: the unidentified shell's row, and a held, ground or corpse drop's buffer row. Identify then
-- writes it to dc_item_instance.quality_tier (items_0001, which has had the column since I9).
-- Rows written before this migration keep 'normal'. Idempotent: each column is added only when missing.
SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_item_unidentified' AND column_name='quality_tier');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_item_unidentified ADD COLUMN `quality_tier` ENUM(''normal'',''ancient'',''primal'') NOT NULL DEFAULT ''normal'' COMMENT ''decided at the drop - identify rolls in the bracket of this quality''','DO 0');
PREPARE dc_quality_ddl FROM @dc_ddl;
EXECUTE dc_quality_ddl;
DEALLOCATE PREPARE dc_quality_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='quality_tier');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `quality_tier` ENUM(''normal'',''ancient'',''primal'') NOT NULL DEFAULT ''normal'' COMMENT ''decided at the drop - the shell this drop becomes carries it''','DO 0');
PREPARE dc_quality_ddl FROM @dc_ddl;
EXECUTE dc_quality_ddl;
DEALLOCATE PREPARE dc_quality_ddl;

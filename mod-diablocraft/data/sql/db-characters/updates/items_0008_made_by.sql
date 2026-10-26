-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration, like items_0006 and items_0007 (no generator owns dc_item_instance). No data.
--
-- diablocraft-wpt7l.3 (Kanai's Cube, the made-by mark; plan docs/research/kanais-cube.md 6.4): the name of the character
-- who made the item, written when the mark is set (dc_items.cpp MarkMade) next to the 3.3.5 creator field, and drawn by
-- the tooltip as "<Made by Name>" (lua/aio/dc_tooltip.lua). Kept as text so the line outlives a deleted maker. Empty for
-- every item nobody made; the one-worn rule reads the creator field, not this.
-- Guarded as loot_0011 is, so a second apply changes nothing.
SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_item_instance' AND column_name='made_by');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_item_instance ADD COLUMN `made_by` VARCHAR(12) NOT NULL DEFAULT '''' COMMENT ''the maker''''s character name when the item was made (Kanai''''s Cube); empty otherwise'' AFTER `quality_tier`','DO 0');
PREPARE dc_stmt FROM @dc_ddl;
EXECUTE dc_stmt;
DEALLOCATE PREPARE dc_stmt;

-- Generated from data/d3/loot_tuning.csv by generate_rift_affixes.py;
-- edit the CSV and rerun. Apply to the world database.
-- 03-difficulty section 5 / decisions.md 2026-09-07: how many champions a
-- champion pack holds in total, the promoted spawn included. The designer's tunable.
SET NAMES utf8mb4;
SET @dc_has_pack=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_tuning' AND column_name='champion_pack_size');
SET @dc_ddl_pack=IF(@dc_has_pack=0,'ALTER TABLE dc_loot_tuning ADD COLUMN champion_pack_size INT NULL','DO 0');
PREPARE dc_stmt_pack FROM @dc_ddl_pack;
EXECUTE dc_stmt_pack;
DEALLOCATE PREPARE dc_stmt_pack;
UPDATE dc_loot_tuning SET champion_pack_size=3 WHERE source='elite';

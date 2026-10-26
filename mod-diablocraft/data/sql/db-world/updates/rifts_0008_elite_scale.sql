-- Generated from data/d3/loot_tuning.csv by generate_rift_affixes.py;
-- edit the CSV and rerun. Apply to the world database.
-- 03-difficulty section 5: how much larger a promoted pack is than the
-- creature it was made from. The designer's tunables.
SET NAMES utf8mb4;
SET @dc_has_0=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_tuning' AND column_name='elite_scale_champion');
SET @dc_ddl_0=IF(@dc_has_0=0,'ALTER TABLE dc_loot_tuning ADD COLUMN elite_scale_champion DECIMAL(4,2) NULL','DO 0');
PREPARE dc_stmt_0 FROM @dc_ddl_0;
EXECUTE dc_stmt_0;
DEALLOCATE PREPARE dc_stmt_0;
SET @dc_has_1=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_tuning' AND column_name='elite_scale_rare');
SET @dc_ddl_1=IF(@dc_has_1=0,'ALTER TABLE dc_loot_tuning ADD COLUMN elite_scale_rare DECIMAL(4,2) NULL','DO 0');
PREPARE dc_stmt_1 FROM @dc_ddl_1;
EXECUTE dc_stmt_1;
DEALLOCATE PREPARE dc_stmt_1;
SET @dc_has_2=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_tuning' AND column_name='elite_scale_minion');
SET @dc_ddl_2=IF(@dc_has_2=0,'ALTER TABLE dc_loot_tuning ADD COLUMN elite_scale_minion DECIMAL(4,2) NULL','DO 0');
PREPARE dc_stmt_2 FROM @dc_ddl_2;
EXECUTE dc_stmt_2;
DEALLOCATE PREPARE dc_stmt_2;
UPDATE dc_loot_tuning SET elite_scale_champion=1.15, elite_scale_rare=1.30, elite_scale_minion=1.00 WHERE source='elite';

-- CHARACTERS only: ground descriptors; no item or affix exists before pickup.
SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='carrier_guid');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `carrier_guid` BIGINT UNSIGNED NULL','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='content_kind');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `content_kind` VARCHAR(16) NOT NULL DEFAULT ''rolled''','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='map_id');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `map_id` INT UNSIGNED NOT NULL DEFAULT 0','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='instance_id');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `instance_id` INT UNSIGNED NOT NULL DEFAULT 0','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='phase_mask');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `phase_mask` INT UNSIGNED NOT NULL DEFAULT 1','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='drop_x');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `drop_x` FLOAT NOT NULL DEFAULT 0','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='drop_y');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `drop_y` FLOAT NOT NULL DEFAULT 0','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='drop_z');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `drop_z` FLOAT NOT NULL DEFAULT 0','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='drop_o');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `drop_o` FLOAT NOT NULL DEFAULT 0','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='in_rift');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN `in_rift` TINYINT UNSIGNED NOT NULL DEFAULT 0','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND index_name='dc_ground_carrier');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD UNIQUE KEY dc_ground_carrier(map_id,instance_id,carrier_guid)','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;
-- Same MySQL 8 CHECK/ROW_COUNT guard as dc_account_economy_check.
-- Insert after conditional row deletion; valid=0 rolls the entire reward back.
CREATE TABLE IF NOT EXISTS dc_loot_claim_check (id BIGINT UNSIGNED NOT NULL PRIMARY KEY,valid TINYINT NOT NULL,CONSTRAINT dc_loot_claim_valid CHECK(valid=1)) ENGINE=InnoDB;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND column_name='drop_count');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD COLUMN drop_count INT UNSIGNED NOT NULL DEFAULT 1','DO 0');
PREPARE dc_ground_ddl FROM @dc_ddl;
EXECUTE dc_ground_ddl;
DEALLOCATE PREPARE dc_ground_ddl;

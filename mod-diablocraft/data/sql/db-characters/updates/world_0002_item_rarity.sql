-- Rolled rarity is distinct from the ancient/primal quality tier.
SET @dc_has_rarity = (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_item_instance' AND column_name='rarity');
SET @dc_add_rarity = IF(@dc_has_rarity=0,'ALTER TABLE dc_item_instance ADD COLUMN rarity VARCHAR(16) NOT NULL DEFAULT ''''','SELECT 1');
PREPARE dc_rarity_stmt FROM @dc_add_rarity;
EXECUTE dc_rarity_stmt;
DEALLOCATE PREPARE dc_rarity_stmt;

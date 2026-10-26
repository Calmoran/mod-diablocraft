-- CHARACTERS only: corpse loot rows (docs/proposals/corpse-loot-minimum.md M1).
-- A corpse holds several owners' several rows, so the one-row-per-carrier key of
-- loot_0006 goes and a plain index takes its place. Rows of kind 'corpse' reuse the
-- ground descriptor columns (carrier_guid is the corpse's guid).
SET @dc_unique=(SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND index_name='dc_ground_carrier' AND non_unique=0);
SET @dc_ddl=IF(@dc_unique>0,'ALTER TABLE dc_loot_buffer DROP INDEX dc_ground_carrier','DO 0');
PREPARE dc_corpse_ddl FROM @dc_ddl;
EXECUTE dc_corpse_ddl;
DEALLOCATE PREPARE dc_corpse_ddl;

SET @dc_exists=(SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='dc_loot_buffer' AND index_name='dc_loot_carrier');
SET @dc_ddl=IF(@dc_exists=0,'ALTER TABLE dc_loot_buffer ADD KEY dc_loot_carrier(map_id,instance_id,carrier_guid,guid)','DO 0');
PREPARE dc_corpse_ddl FROM @dc_ddl;
EXECUTE dc_corpse_ddl;
DEALLOCATE PREPARE dc_corpse_ddl;

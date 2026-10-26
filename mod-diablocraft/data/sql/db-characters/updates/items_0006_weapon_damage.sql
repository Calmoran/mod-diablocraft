-- G1 (diablocraft-weapon-elemental-build): a weapon elemental damage affix rolls TWO numbers
-- (D3's Min + Delta). value2 is the second endpoint (max = value + delta); range_min2/range_max2
-- are the second bracket [c,d] it was rolled in, beside range_min/range_max for the first. A
-- single-part affix keeps all three at 0, so every existing row is unchanged.
-- Hand-written schema migration (CREATE/ALTER only), applied by the core updater to the
-- characters database. Not a schema.csv row: that running-server check reads WorldDatabase only.
SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_item_affix' AND column_name='value2');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_item_affix ADD COLUMN value2 DOUBLE NOT NULL DEFAULT 0','DO 0');
PREPARE dc_weapon_damage_ddl FROM @dc_ddl;
EXECUTE dc_weapon_damage_ddl;
DEALLOCATE PREPARE dc_weapon_damage_ddl;
SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_item_affix' AND column_name='range_min2');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_item_affix ADD COLUMN range_min2 DOUBLE NOT NULL DEFAULT 0','DO 0');
PREPARE dc_weapon_damage_ddl FROM @dc_ddl;
EXECUTE dc_weapon_damage_ddl;
DEALLOCATE PREPARE dc_weapon_damage_ddl;
SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_item_affix' AND column_name='range_max2');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_item_affix ADD COLUMN range_max2 DOUBLE NOT NULL DEFAULT 0','DO 0');
PREPARE dc_weapon_damage_ddl FROM @dc_ddl;
EXECUTE dc_weapon_damage_ddl;
DEALLOCATE PREPARE dc_weapon_damage_ddl;
